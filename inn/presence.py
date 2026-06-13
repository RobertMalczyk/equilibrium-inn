"""Presence: room label per persona per tick. No geometry, no travel time.

Room = scheduled room, unless the persona is engaged (BUSY) on a catalog
activity located in another room, in which case the activity's room wins.
At night everyone is at room_home (sleep).
"""

from __future__ import annotations

from inn.clock import Clock
from inn.config import InnConfig
from inn.schedule import ScheduleStream


class Presence:
    def __init__(self, cfg: InnConfig, stream: ScheduleStream, clock: Clock):
        self.cfg = cfg
        self.stream = stream
        self.clock = clock
        self._home = {c.id: c.room_home for c in cfg.cast}
        self._rooms: dict[str, str] = {c.id: c.room_home for c in cfg.cast}
        # engaged_activity: pid -> activity id while the engine is BUSY on it
        self._engaged: dict[str, str] = {}

    def set_engaged(self, pid: str, activity_id: str | None) -> None:
        if activity_id is None:
            self._engaged.pop(pid, None)
        else:
            self._engaged[pid] = activity_id

    def update(self, t: int) -> None:
        for c in self.cfg.cast:
            if self.clock.is_night(t):
                self._rooms[c.id] = self._home[c.id]
                continue
            act = self._engaged.get(c.id)
            if act is not None:
                self._rooms[c.id] = self.cfg.activities[act].room
            else:
                self._rooms[c.id] = self.stream.planned_room(c.id, t)

    def room_of(self, pid: str) -> str:
        return self._rooms[pid]

    def cohort(self, room: str) -> list[str]:
        """Personas currently in a room, in cast (tiebreak) order."""
        return [c.id for c in self.cfg.cast if self._rooms[c.id] == room]

    def snapshot(self) -> dict[str, str]:
        return dict(self._rooms)
