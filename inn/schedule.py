"""Schedule compiler: day-blocks -> per-persona event streams and planned rooms.

Owns time arithmetic only. It OFFERS (meals as food_given, work blocks as
scheduled activity ids the loop routes through the economy, nightfall); the
engine decides how the day is performed. It never reads persona state.
"""

from __future__ import annotations

from dataclasses import dataclass

from inn.clock import Clock
from inn.config import InnConfig, ScheduleBlock
from inn.engine_surface import RawEvent


@dataclass(frozen=True)
class CompiledDay:
    """Per-persona, per-day-offset lookups (same for every day in v0)."""
    room_by_offset: tuple[str, ...]          # len = day_ticks; night -> room_home
    activity_by_offset: tuple[str | None, ...]
    meal_offsets: tuple[int, ...]            # block-start offsets of meal blocks
    meal_slot_by_offset: dict[int, int]      # offset -> slot index (0=breakfast..)


class ScheduleStream:
    def __init__(self, cfg: InnConfig, clock: Clock):
        self.cfg = cfg
        self.clock = clock
        self._days: dict[str, CompiledDay] = {
            pid: self._compile(pid, blocks) for pid, blocks in cfg.schedules.items()
        }

    def _compile(self, pid: str, blocks: tuple[ScheduleBlock, ...]) -> CompiledDay:
        home = next(c.room_home for c in self.cfg.cast if c.id == pid)
        room = [home] * self.clock.day_ticks
        act: list[str | None] = [None] * self.clock.day_ticks
        meal_offsets: list[int] = []
        spans = []
        for b in blocks:
            o0, o1 = self.clock.hhmm_to_offset(b.start), self.clock.hhmm_to_offset(b.end)
            if o1 <= o0:
                raise ValueError(f"schedule {pid}: empty block {b.start}-{b.end}")
            spans.append((o0, o1))
            for o in range(o0, o1):
                room[o] = b.room
                act[o] = b.activity
            if b.meal:
                meal_offsets.append(o0)
        spans.sort()
        for (a0, a1), (b0, _b1) in zip(spans, spans[1:]):
            if b0 < a1:
                raise ValueError(f"schedule {pid}: overlapping blocks")
        meal_offsets.sort()
        return CompiledDay(
            room_by_offset=tuple(room),
            activity_by_offset=tuple(act),
            meal_offsets=tuple(meal_offsets),
            meal_slot_by_offset={o: i for i, o in enumerate(meal_offsets)},
        )

    def planned_room(self, pid: str, t: int) -> str:
        return self._days[pid].room_by_offset[self.clock.offset_in_day(t)]

    def scheduled_activity(self, pid: str, t: int) -> str | None:
        if self.clock.is_night(t):
            return None
        return self._days[pid].activity_by_offset[self.clock.offset_in_day(t)]

    def events_for(self, pid: str, t: int) -> list[RawEvent]:
        """Schedule-sourced events arising at tick t: meals and nightfall."""
        out: list[RawEvent] = []
        day = self.clock.day_of(t)
        off = self.clock.offset_in_day(t)
        cd = self._days[pid]
        slot = cd.meal_slot_by_offset.get(off)
        if slot is not None:
            n_slots = max(1, len(cd.meal_offsets))
            item = self.cfg.menu_rotation[((day - 1) * n_slots + slot) % len(self.cfg.menu_rotation)]
            out.append(RawEvent(type="food_given", t=t, source=self.cfg.meal_source,
                                item=item, intensity=self.cfg.meal_intensity))
        if off == self.clock.waking_ticks:
            out.append(RawEvent(type="nightfall", t=t))
        return out
