"""The inn loop: sole caller of engine tick(). Three-phase synchronous tick
with one-tick social latency (CLAUDE.md section 4.3, frozen):

  Phase A — deliver frozen inboxes for tick t (schedule + probes + offers +
            last tick's social events); call tick() for every persona.
  Phase B — collect ActionSelections.
  Phase C — transduce through presence and witnessing; stamp provenance;
            deliver resulting events to inboxes for t+1; emit society record.

Order-invariance holds by construction: nothing produced in Phase A/B of
tick t can reach another persona before t+1.
"""

from __future__ import annotations

import random
from typing import Callable

from inn.clock import Clock
from inn.config import InnConfig, Probe
from inn.economy import Economy
from inn.engine_surface import (
    ENGINE_ROOT,
    Mode,
    PersonaRuntime,
    RawEvent,
    believable_day_layout,
    init_runtime,
    load_eval_persona_timescale,
    load_persona,
    tick,
    timescale_overrides,
)
from inn.inbox import Inbox
from inn.presence import Presence
from inn.schedule import ScheduleStream
from inn.trace import TraceWriter
from inn.transducer import transduce
from inn.world_state import WorldStates

# Historical default, used only when inn.yaml omits the `world` block. The live
# set is config-driven (cfg.provoking_event_types) so closing a social gap needs
# no code change here — see config.load_inn_config and CLAUDE.md S4.2.
DEFAULT_PROVOKING_TYPES = ("insult", "command")


def _deep_merge(a: dict, b: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in a.items()}
    for k, v in b.items():
        out[k] = (_deep_merge(out[k], v)
                  if isinstance(v, dict) and isinstance(out.get(k), dict) else v)
    return out


def make_persona_loader(engine_overrides: dict,
                        extra: dict | None = None) -> Callable[[str], object]:
    """Believable-timescale loader with inn.yaml engine_overrides stacked on
    top (and optional sweep-axis extras on top of that)."""
    ov = _deep_merge(timescale_overrides(), engine_overrides)
    if extra:
        ov = _deep_merge(ov, extra)
    if not engine_overrides and not extra:
        return load_eval_persona_timescale

    def loader(pid: str):
        return load_persona(ENGINE_ROOT / "data" / "personas" / f"{pid}.yaml",
                            ENGINE_ROOT / "calibration" / "defaults.yaml",
                            param_overrides=ov)
    return loader


class InnLoop:
    def __init__(self, cfg: InnConfig, seed: int, probe_plan: str,
                 trace: TraceWriter,
                 transducer_scale: float | None = None,
                 richness_mults: dict | None = None,
                 persona_loader: Callable[[str], object] | None = None,
                 extra_events: list[tuple[int, str, RawEvent]] | None = None):
        self.cfg = cfg
        self.clock = Clock.from_layout(believable_day_layout())
        self.stream = ScheduleStream(cfg, self.clock)
        self.presence = Presence(cfg, self.stream, self.clock)
        self.economy = Economy(cfg, self.clock, richness_mults)
        self.world = WorldStates(cfg.world_states, self.clock.dt)
        self.trace = trace
        self.scale = transducer_scale
        self.rng = random.Random(seed)  # reserved for inherited stochastic choices
        loader = persona_loader or make_persona_loader(cfg.engine_overrides)
        self.runtimes: dict[str, PersonaRuntime] = {
            c.id: init_runtime(loader(c.id)) for c in cfg.cast
        }
        self.inboxes: dict[str, Inbox] = {
            c.id: Inbox(cfg.inbox, cfg.cast_order) for c in cfg.cast
        }
        # last provoking delivery per persona: (event_id, source, tick).
        # Expires after max_defer_ticks so a reaction is never attributed to
        # a provocation from a different episode (e.g. across a night).
        self._last_prov: dict[str, tuple[str | None, str | None, int]] = {
            c.id: (None, None, -1) for c in cfg.cast
        }
        # Config-driven provoking-event set (falls back to the historical default
        # only if inn.yaml omits it). A delivery of one of these types records
        # its source as the recipient's current provocation for target inference.
        self._provoking_types: frozenset[str] = frozenset(
            cfg.provoking_event_types or DEFAULT_PROVOKING_TYPES)
        self._engaged: dict[str, str | None] = {c.id: None for c in cfg.cast}
        self._probe_schedule = self._expand_probes(cfg.probes[probe_plan])
        self._weather_spans = self._weather_spans_of(cfg.probes[probe_plan])
        # injected events (player verbs later): (tick, recipient, event)
        self._extra = extra_events or []

    # -- probe expansion ----------------------------------------------------

    def _expand_probes(self, probes: tuple[Probe, ...]) -> dict[int, list[Probe]]:
        out: dict[int, list[Probe]] = {}
        for p in probes:
            t0 = self.clock.tick_at(p.day, p.hhmm)
            if p.until_hhmm and p.every_ticks:
                t1 = self.clock.tick_at(p.day, p.until_hhmm)
                for t in range(t0, t1, p.every_ticks):
                    out.setdefault(t, []).append(p)
            else:
                out.setdefault(t0, []).append(p)
        return out

    def _weather_spans_of(self, probes: tuple[Probe, ...]) -> list[tuple[int, int]]:
        return [(self.clock.tick_at(p.day, p.hhmm),
                 self.clock.tick_at(p.day, p.until_hhmm))
                for p in probes
                if p.type == "weather" and p.until_hhmm is not None]

    def _deliver_probe(self, t: int, p: Probe) -> list[dict]:
        """Push a probe into inboxes; returns trace records of the injections."""
        records = []
        pid_id = f"{t}:{p.source or 'world'}:{p.type}:probe"
        if p.type == "weather":
            for c in self.cfg.cast:
                self.inboxes[c.id].push(
                    RawEvent(type="weather", t=t, item=p.item,
                             intensity=p.intensity), t, pid_id)
            records.append({"probe": pid_id, "recipients": "all"})
            return records
        # targeted social probe: full intensity to target, attenuated to
        # co-located witnesses when public (CLAUDE.md witnessing policy)
        target = p.target
        if target is not None:
            self.inboxes[target].push(
                RawEvent(type=p.type, t=t, source=p.source, item=p.item,
                         intensity=p.intensity, context=dict(p.context)), t, pid_id)
            recipients = [target]
            if p.context.get("public") and p.room:
                att = self.cfg.co_located_attenuation
                for w in self.presence.cohort(p.room):
                    if w == target:
                        continue
                    self.inboxes[w].push(
                        RawEvent(type=p.type, t=t, source=p.source, item=p.item,
                                 intensity=p.intensity * att,
                                 context=dict(p.context)), t, pid_id)
                    recipients.append(w)
            records.append({"probe": pid_id, "recipients": recipients})
        return records

    # -- main loop ----------------------------------------------------------

    def run(self, n_ticks: int) -> None:
        for t in range(n_ticks):
            self._step(t)

    def _step(self, t: int) -> None:
        cfg = self.cfg
        self.presence.update(t)
        in_rain = any(a <= t < b for a, b in self._weather_spans)
        self.economy.set_weather_closed(in_rain)

        # schedule + probes + injected events into inboxes for this tick
        probe_records = []
        for c in cfg.cast:
            for ev in self.stream.events_for(c.id, t):
                self.inboxes[c.id].push(ev, t)
        for p in self._probe_schedule.get(t, []):
            probe_records += self._deliver_probe(t, p)
        for (et, recipient, ev) in self._extra:
            if et == t:
                self.inboxes[recipient].push(ev, t)

        # activity offers for current seekers (engine state from end of t-1)
        offers_rec = []
        seekers = []
        for c in cfg.cast:
            rt = self.runtimes[c.id]
            if rt.mode != Mode.SEEKING:
                continue
            scheduled = self.stream.scheduled_activity(c.id, t)
            if scheduled is not None:
                ev = self.economy.offer_scheduled(t, c.id, scheduled)
                if ev is not None:
                    self.inboxes[c.id].push(ev, t)
                    offers_rec.append({"pid": c.id, "activity": scheduled,
                                       "via": "schedule"})
            else:
                urge = rt.global_state.get("boredom", 0.0)
                seekers.append((c.id, urge, rt.seeking_since))
        if seekers:
            granted = self.economy.answer_seekers(t, seekers, self.presence.room_of)
            for pid, ev in granted.items():
                self.inboxes[pid].push(ev, t)
                offers_rec.append({"pid": pid, "activity": ev.item, "via": "seek"})
        contention_losers = [s[0] for s in seekers
                             if not any(r["pid"] == s[0] for r in offers_rec)]

        # Phase A: deliver + tick every persona (order irrelevant by construction)
        tick_traces = {}
        deliveries = {}
        dropped_records = []
        for c in cfg.cast:
            delivery, dropped = self.inboxes[c.id].pop_for_tick(t)
            for d in dropped:
                dropped_records.append({
                    "recipient": c.id, "type": d.event.type,
                    "source": d.event.source, "enqueued_t": d.enqueued_t,
                    "dropped_t": d.dropped_t, "provenance": d.provenance_id})
            ev = delivery.event if delivery else None
            tick_traces[c.id] = tick(self.runtimes[c.id], t, ev)
            deliveries[c.id] = delivery
            if ev is not None and ev.type in self._provoking_types and ev.source is not None:
                prov_id = (delivery.provenance_id
                           or f"{ev.t}:{ev.source}:{ev.type}:probe")
                self._last_prov[c.id] = (prov_id, ev.source, t)

        # engagement bookkeeping (presence + economy capacity)
        for c in cfg.cast:
            rt = self.runtimes[c.id]
            d = deliveries[c.id]
            if (rt.mode == Mode.BUSY and d is not None
                    and d.event.type == "activity"
                    and d.event.context.get("activity_id")):
                aid = d.event.context["activity_id"]
                self._engaged[c.id] = aid
                self.economy.set_engaged(c.id, aid)
                self.presence.set_engaged(c.id, aid)
            elif rt.mode != Mode.BUSY and self._engaged[c.id] is not None:
                self._engaged[c.id] = None
                self.economy.set_engaged(c.id, None)
                self.presence.set_engaged(c.id, None)

        # Phase B + C: transduce selections; deliver to t+1; world states
        transduction_records = []
        gap_records = []
        conflict_by_room: dict[str, float] = {}
        for c in cfg.cast:
            sel = tick_traces[c.id].selection
            prov_id, prov_source, prov_t = self._last_prov[c.id]
            if prov_id is not None and t - prov_t > cfg.inbox.max_defer_ticks:
                prov_id, prov_source = None, None
                self._last_prov[c.id] = (None, None, -1)
            result = transduce(cfg, t, c.id, sel,
                               provoking_source=prov_source,
                               provoking_id=prov_id,
                               cohort=self.presence.cohort(self.presence.room_of(c.id)),
                               scale=self.scale)
            for a in result.addressed:
                # recipients without an interior (marta, player) are socially
                # real but have no inbox; the transduction is still recorded
                if a.recipient in self.inboxes:
                    self.inboxes[a.recipient].push(a.event, t, a.provenance.event_id)
                transduction_records.append({
                    "event_id": a.provenance.event_id,
                    "action": a.provenance.action,
                    "actor": a.provenance.actor,
                    "as": a.event.type,
                    "recipient": a.recipient,
                    "role": a.role,
                    "intensity": round(a.event.intensity, 9),
                    "provoked_by": a.provenance.provoked_by,
                    "target_inferred": a.provenance.target_inferred,
                    "score": round(a.provenance.selection_score, 9),
                })
            for g in result.gaps:
                gap_records.append({"event_id": g.event_id, "action": g.action,
                                    "actor": g.actor,
                                    "provoked_by": g.provoked_by})
            if result.conflict_intensity > 0.0:
                room = self.presence.room_of(c.id)
                conflict_by_room[room] = (conflict_by_room.get(room, 0.0)
                                          + result.conflict_intensity)
        self.world.step(conflict_by_room)
        self.economy.replenish_idle()

        self.trace.emit({
            "t": t,
            "day": self.clock.day_of(t),
            "clock": self.clock.clock_str(t),
            "night": self.clock.is_night(t),
            "personas": {pid: tt.to_dict() for pid, tt in tick_traces.items()},
            "delivery_delays": {pid: d.delay for pid, d in deliveries.items()
                                if d is not None},
            "presence": self.presence.snapshot(),
            "world": self.world.snapshot(),
            "budgets": self.economy.budgets(),
            "offers": offers_rec,
            "contention_losers": contention_losers,
            "probes": probe_records,
            "transductions": transduction_records,
            "gaps": gap_records,
            "dropped": dropped_records,
            "rain": in_rain,
        })
