"""Activity economy: the supply side of stimulation, all parameters from
inn.yaml. Generalizes eval/mock_world.py's single novelty budget into one
budget per catalog entry, plus capacity and time windows.

The engine keeps perceived staleness (repetition/novelty history) itself —
the activity id is passed as the event item; no duplicated bookkeeping here.

Contention rule (inn.yaml contention.rule = highest_urge_then_cast_order):
multiple seekers, limited capacity -> highest current urge wins, ties broken
by cast order. Losers get nothing; their timeout-frustration is intended.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from inn.clock import Clock
from inn.config import ActivityEntry, InnConfig
from inn.engine_surface import RawEvent

# Engine-side activity kinds (mock_world vocabulary): work transduces to
# "external", leisure/social to "self_activity".
_ENGINE_KIND = {"work": "external", "leisure": "self_activity", "social": "self_activity"}


@dataclass
class ActivitySource:
    entry: ActivityEntry
    budget: float = field(init=False)
    engaged: set[str] = field(init=False, default_factory=set)
    closed: bool = False  # weather closure (outdoor entries in rain)

    def __post_init__(self):
        self.budget = self.entry.novelty_start

    def in_window(self, clock: Clock, t: int) -> bool:
        if clock.is_night(t):
            return False
        off = clock.offset_in_day(t)
        return (clock.hhmm_to_offset(self.entry.window[0]) <= off
                < clock.hhmm_to_offset(self.entry.window[1]))

    def available(self, clock: Clock, t: int) -> bool:
        return (not self.closed
                and self.in_window(clock, t)
                and len(self.engaged) < self.entry.capacity
                and self.budget >= self.entry.min_novelty)

    def make_offer(self, t: int, pid: str) -> RawEvent:
        ev = RawEvent(
            type="activity", t=t, item=self.entry.id,
            intensity=1.0,
            context={"kind": _ENGINE_KIND[self.entry.kind],
                     "novelty": min(1.0, self.budget),
                     "activity_id": self.entry.id},
        )
        self.budget = max(0.0, self.budget - self.entry.deplete_per_offer)
        return ev

    def replenish(self) -> None:
        self.budget = min(self.entry.novelty_start,
                          self.budget + self.entry.replenish_per_tick)


class Economy:
    def __init__(self, cfg: InnConfig, clock: Clock,
                 richness_mults: dict | None = None,
                 disabled_activities: frozenset[str] = frozenset()):
        self.cfg = cfg
        self.clock = clock
        self.sources: dict[str, ActivitySource] = {}
        for aid, entry in cfg.activities.items():
            if aid in disabled_activities:  # profile (e.g. semantic) drops the hearth
                continue
            src = ActivitySource(entry)
            if richness_mults:
                src.budget = entry.novelty_start * richness_mults.get("novelty_start_mult", 1.0)
            self.sources[aid] = src
        self._replenish_mult = (richness_mults or {}).get("replenish_mult", 1.0)

    def set_weather_closed(self, closed: bool) -> None:
        for src in self.sources.values():
            if src.entry.outdoor:
                src.closed = closed

    def set_engaged(self, pid: str, activity_id: str | None) -> None:
        for src in self.sources.values():
            src.engaged.discard(pid)
        if activity_id is not None:
            self.sources[activity_id].engaged.add(pid)

    def offer_scheduled(self, t: int, pid: str, activity_id: str) -> RawEvent | None:
        """Directed offer for a schedule work block. Engine decides engagement."""
        src = self.sources[activity_id]
        if src.available(self.clock, t):
            return src.make_offer(t, pid)
        return None

    def answer_seekers(self, t: int,
                       seekers: list[tuple[str, float, int | None]],
                       room_of) -> dict[str, RawEvent]:
        """seekers: (pid, urge, seeking_since). room_of: pid -> room.

        Offers honor each source's offer_latency (ticks the persona must have
        been seeking) and are granted in contention order.
        """
        order = sorted(seekers,
                       key=lambda s: (-s[1], self.cfg.cast_order[s[0]]))
        offers: dict[str, RawEvent] = {}
        for pid, _urge, seeking_since in order:
            room = room_of(pid)
            waited = 0 if seeking_since is None else t - seeking_since
            for aid in self.cfg.activities:  # catalog order: deterministic
                src = self.sources.get(aid)  # None if disabled by the profile
                if src is None or src.entry.room != room or not src.available(self.clock, t):
                    continue
                if waited < src.entry.offer_latency:
                    continue
                offers[pid] = src.make_offer(t, pid)
                break
        return offers

    def replenish_idle(self) -> None:
        """Replenish all sources nobody is consuming (mock_world semantics:
        options regenerate while attention is elsewhere)."""
        for src in self.sources.values():
            if not src.engaged:
                src.budget = min(src.entry.novelty_start,
                                 src.budget + src.entry.replenish_per_tick * self._replenish_mult)

    def budgets(self) -> dict[str, float]:
        return {aid: round(src.budget, 6) for aid, src in self.sources.items()}
