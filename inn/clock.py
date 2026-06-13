"""Tick/time arithmetic shared by the world layer.

The waking day runs 06:00-23:00 (waking_ticks ticks); the remainder of
day_ticks is night. Tick 0 of each day is 06:00. All conversions go through
the engine's believable_day_layout(); nothing here duplicates dt.
"""

from __future__ import annotations

from dataclasses import dataclass

WAKE_HHMM = "06:00"
_WAKE_S = 6 * 3600


@dataclass(frozen=True)
class Clock:
    dt: float
    day_ticks: int
    waking_ticks: int

    @classmethod
    def from_layout(cls, layout: dict) -> "Clock":
        return cls(dt=layout["dt"], day_ticks=layout["day_ticks"],
                   waking_ticks=layout["waking_ticks"])

    def day_of(self, t: int) -> int:
        """1-based day index."""
        return t // self.day_ticks + 1

    def offset_in_day(self, t: int) -> int:
        return t % self.day_ticks

    def is_night(self, t: int) -> bool:
        return self.offset_in_day(t) >= self.waking_ticks

    def hhmm_to_offset(self, hhmm: str) -> int:
        """Offset within the day of a wall-clock time (>= 06:00)."""
        h, m = map(int, hhmm.split(":"))
        seconds = h * 3600 + m * 60 - _WAKE_S
        if seconds < 0:
            raise ValueError(f"{hhmm} is before the 06:00 day start")
        return int(seconds // self.dt)

    def tick_at(self, day: int, hhmm: str) -> int:
        """Absolute tick of day (1-based) at wall-clock time."""
        return (day - 1) * self.day_ticks + self.hhmm_to_offset(hhmm)

    def clock_str(self, t: int) -> str:
        off = self.offset_in_day(t)
        seconds = _WAKE_S + int(off * self.dt)
        h, rem = divmod(seconds, 3600)
        return f"{h % 24:02d}:{rem // 60:02d}"
