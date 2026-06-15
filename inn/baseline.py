"""Baseline cast (CLAUDE.md §7, M-E): a deliberately FAIR control implementation —
the industry-standard NPC, run side-by-side with the engine on the same schedule,
the same world layer, and the same probes, so the comparison isolates the *brain*.

The baseline brain is the games baseline named in §1: a **schedule automaton**
(work the scheduled block, eat at meals, sleep at night) plus a **trigger→bark
table** (received insult → maybe an outburst, gated by a fixed anger threshold and
cooldown — no priming, no integration of grudges, no variety). It reuses the inn's
world layer unchanged (ScheduleStream, Presence, the transducer + witnessing,
WorldStates, the society trace), so it emits the SAME trace schema and every metric
in inn.metrics / inn.observe reads it identically. No engine, no LLM.

All behaviour-shaping numbers live in inn.yaml's `baseline` block (hard rule 0.3).
Deterministic: a baseline run is fully determined by (inn.yaml, probe plan).
"""

from __future__ import annotations

from dataclasses import dataclass

from inn.clock import Clock
from inn.config import InnConfig, Probe
from inn.engine_surface import GLOBAL_STATES, RawEvent, believable_day_layout
from inn.presence import Presence
from inn.schedule import ScheduleStream
from inn.trace import TraceWriter
from inn.transducer import transduce
from inn.world_state import WorldStates

# Defaults if inn.yaml omits the `baseline` block (kept here only as a documented
# fallback; the shipped values live in inn.yaml so they are auditable as data).
_DEFAULTS = {
    "anger_gain": 0.6, "bark_threshold": 0.45, "bark_score": 0.8,
    "cooldown_ticks": 15, "vent": 0.5,
    "boredom_rise": 0.010, "boredom_relief": 0.020,
    "fatigue_rise": 0.012, "fatigue_relief_idle": 0.004,
    "hunger_rise": 0.006, "night_recover": 0.05, "sleep_pressure_rise": 0.004,
}


@dataclass
class _Sel:
    """Minimal duck-typed ActionSelection — transduce() reads only these."""
    action: str
    score: float


def run_baseline(cfg: InnConfig, probe_plan: str, out_dir, n_ticks=None,
                 transducer_scale: float | None = None) -> dict:
    """Run one baseline session; write session.json + trace.jsonl.gz (same shape
    as inn.session.run_session) and return the header. Deterministic."""
    import json
    from pathlib import Path
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    layout = believable_day_layout()
    n_ticks = n_ticks or cfg.days * layout["day_ticks"]
    writer = TraceWriter(out_dir / "trace.jsonl.gz")
    BaselineLoop(cfg, probe_plan, writer, transducer_scale).run(n_ticks)
    sha = writer.close()
    header = {"baseline": True, "inn_yaml_sha256": cfg.yaml_sha256,
              "probe_plan": probe_plan, "n_ticks": n_ticks,
              "trace_sha256": sha}
    (out_dir / "session.json").write_text(json.dumps(header, indent=2),
                                          encoding="utf-8")
    return header


class BaselineLoop:
    """Same three-phase tick + one-tick social latency as InnLoop, but with the
    automaton/bark brain instead of engine.tick(). Sole caller of the brain."""

    def __init__(self, cfg: InnConfig, probe_plan: str, trace: TraceWriter,
                 transducer_scale: float | None = None):
        self.cfg = cfg
        self.p = {**_DEFAULTS, **(cfg.baseline or {})}
        self.clock = Clock.from_layout(believable_day_layout())
        self.stream = ScheduleStream(cfg, self.clock)
        self.presence = Presence(cfg, self.stream, self.clock)
        self.world = WorldStates(cfg.world_states, self.clock.dt)
        self.trace = trace
        self.scale = transducer_scale
        self.cast = [c.id for c in cfg.cast]
        # per-persona fast states (subset of GLOBAL_STATES the automaton moves)
        self.state = {p: {"boredom": 0.0, "fatigue": 0.0, "hunger": 0.0,
                          "anger": 0.0, "sleep_pressure": 0.0} for p in self.cast}
        self._cooldown = {p: -10**9 for p in self.cast}
        self._last_prov = {p: (None, None, -1) for p in self.cast}
        # inbox: tick -> pid -> list[(RawEvent, provenance_id)]
        self._inbox: dict[int, dict[str, list[tuple[RawEvent, str | None]]]] = {}
        self._probe_schedule = self._expand_probes(cfg.probes[probe_plan])
        self._provoking = frozenset(cfg.provoking_event_types or ("insult", "command"))

    # -- probes (same delivery shape as InnLoop, minimal) ------------------

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

    def _push(self, t: int, pid: str, ev: RawEvent, prov: str | None) -> None:
        self._inbox.setdefault(t, {}).setdefault(pid, []).append((ev, prov))

    def _deliver_probe(self, t: int, p: Probe) -> list[dict]:
        pid_id = f"{t}:{p.source or 'world'}:{p.type}:probe"
        if p.type == "weather":
            for c in self.cast:
                self._push(t, c, RawEvent(type="weather", t=t, item=p.item,
                                          intensity=p.intensity), pid_id)
            return [{"probe": pid_id, "recipients": "all"}]
        if p.target is None:
            return []
        self._push(t, p.target, RawEvent(type=p.type, t=t, source=p.source,
                   item=p.item, intensity=p.intensity, context=dict(p.context)), pid_id)
        recipients = [p.target]
        if p.context.get("public") and p.room:
            att = self.cfg.co_located_attenuation
            for w in self.presence.cohort(p.room):
                if w == p.target:
                    continue
                self._push(t, w, RawEvent(type=p.type, t=t, source=p.source,
                           item=p.item, intensity=p.intensity * att,
                           context=dict(p.context)), pid_id)
                recipients.append(w)
        return [{"probe": pid_id, "recipients": recipients}]

    # -- the brain (schedule automaton + trigger->bark) -------------------

    def _brain(self, pid: str, t: int, inbox: list[tuple[RawEvent, str | None]]):
        """Return (mode, selection, event_seen). Updates self.state[pid]."""
        s = self.state[pid]
        P = self.p
        # absorb deliveries: anger from insults, hunger reset on food, track prov
        seen = inbox[0][0] if inbox else None
        for ev, prov in inbox:
            if ev.type in ("insult", "refusal", "complaint", "cold_reply"):
                s["anger"] = min(1.0, s["anger"] + P["anger_gain"] * ev.intensity)
                if ev.type in self._provoking and ev.source:
                    self._last_prov[pid] = (
                        prov or f"{ev.t}:{ev.source}:{ev.type}:probe", ev.source, t)
            elif ev.type == "food_given":
                s["hunger"] = 0.0

        if self.clock.is_night(t):              # automaton: sleep at night
            r = P["night_recover"]
            for k in ("boredom", "fatigue", "anger", "sleep_pressure"):
                s[k] = max(0.0, s[k] - r)
            return "SLEEP", _Sel("sleep", 0.0), seen

        # trigger->bark: a fresh provocation + anger over threshold + off cooldown
        prov_id, prov_src, prov_t = self._last_prov[pid]
        fresh = prov_id is not None and t - prov_t <= 1
        if (fresh and s["anger"] >= P["bark_threshold"]
                and t - self._cooldown[pid] >= P["cooldown_ticks"]):
            self._cooldown[pid] = t
            s["anger"] = max(0.0, s["anger"] - P["vent"])
            return "IDLE", _Sel("outburst", P["bark_score"]), seen

        activity = self.stream.scheduled_activity(pid, t)
        if activity is not None:                # automaton: do the scheduled work
            kind = self.cfg.activities[activity].kind
            s["fatigue"] = min(1.0, s["fatigue"] + P["fatigue_rise"])
            s["boredom"] = max(0.0, s["boredom"] - P["boredom_relief"])
            act = "external" if kind == "work" else "self_activity"
            return "BUSY", _Sel(act, 0.0), seen

        # idle (incl. meal blocks): boredom drifts up, fatigue eases
        s["boredom"] = min(1.0, s["boredom"] + P["boredom_rise"])
        s["fatigue"] = max(0.0, s["fatigue"] - P["fatigue_relief_idle"])
        s["hunger"] = min(1.0, s["hunger"] + P["hunger_rise"])
        s["sleep_pressure"] = min(1.0, s["sleep_pressure"] + P["sleep_pressure_rise"])
        return "IDLE", _Sel("neutral", 0.0), seen

    # -- the loop ----------------------------------------------------------

    def run(self, n_ticks: int) -> None:
        for t in range(n_ticks):
            self._step(t)

    def _step(self, t: int) -> dict:
        self.presence.update(t)
        probe_records = []
        for p in self._probe_schedule.get(t, []):
            probe_records += self._deliver_probe(t, p)
        # schedule meals/nightfall into inboxes
        for c in self.cast:
            for ev in self.stream.events_for(c, t):
                self._push(t, c, ev, None)

        inboxes = self._inbox.pop(t, {})
        personas, selections, events = {}, {}, {}
        for c in self.cast:
            inbox = inboxes.get(c, [])
            mode, sel, seen = self._brain(c, t, inbox)
            selections[c] = sel
            events[c] = seen
            personas[c] = self._persona_dict(c, mode, sel, seen)

        # Phase C: transduce barks, deliver to t+1, world states
        transduction_records, gap_records = [], []
        conflict_by_room: dict[str, float] = {}
        for c in self.cast:
            sel = selections[c]
            prov_id, prov_src, prov_t = self._last_prov[c]
            if prov_id is not None and t - prov_t > 1:
                prov_id, prov_src = None, None
            res = transduce(self.cfg, t, c, sel, provoking_source=prov_src,
                            provoking_id=prov_id,
                            cohort=self.presence.cohort(self.presence.room_of(c)),
                            scale=self.scale)
            for a in res.addressed:
                self._push(t + 1, a.recipient, a.event, a.provenance.event_id)
                transduction_records.append({
                    "event_id": a.provenance.event_id, "action": a.provenance.action,
                    "actor": a.provenance.actor, "as": a.event.type,
                    "recipient": a.recipient, "role": a.role,
                    "intensity": round(a.event.intensity, 9),
                    "provoked_by": a.provenance.provoked_by,
                    "target_inferred": a.provenance.target_inferred,
                    "score": round(a.provenance.selection_score, 9)})
            if res.conflict_intensity > 0.0:
                room = self.presence.room_of(c)
                conflict_by_room[room] = conflict_by_room.get(room, 0.0) + res.conflict_intensity
        self.world.step(conflict_by_room)

        record = {
            "t": t, "day": self.clock.day_of(t), "clock": self.clock.clock_str(t),
            "night": self.clock.is_night(t), "personas": personas,
            "delivery_delays": {}, "presence": self.presence.snapshot(),
            "world": self.world.snapshot(), "budgets": {},
            "offers": [], "contention_losers": [], "probes": probe_records,
            "transductions": transduction_records, "gaps": gap_records,
            "dropped": [], "rain": False, "baseline": True,
        }
        self.trace.emit(record)
        return record

    def _persona_dict(self, pid: str, mode: str, sel: _Sel, ev) -> dict:
        s = self.state[pid]
        g = {k: 0.0 for k in GLOBAL_STATES}
        for k, v in s.items():
            g[k] = round(v, 9)
        kind = ("reactive" if sel.action == "outburst"
                else "idle" if sel.action == "neutral" else "proactive")
        return {
            "event": ({"type": ev.type, "source": ev.source} if ev else None),
            "selection": {"action": sel.action, "score": round(sel.score, 9),
                          "kind": kind, "interrupted": False, "explanation": ""},
            "state_after_post": {"global": g, "relations": {}, "mode": mode},
            "potentials": {}, "urges": {},
        }
