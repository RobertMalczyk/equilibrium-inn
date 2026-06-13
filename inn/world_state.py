"""World states: standalone one-pole integrators owned by the world.

Declared world physics (CLAUDE.md section 4.2). In M-A they are trace-only
observables — no mapper channel exists for them and none is invented here.
"""

from __future__ import annotations

import math

from inn.config import WorldStateSpec


class WorldStates:
    def __init__(self, specs: tuple[WorldStateSpec, ...], dt: float):
        self.specs = specs
        self._decay = {s.name: 0.5 ** (dt / s.half_life_s) for s in specs}
        self.values: dict[str, dict[str, float]] = {
            s.name: {room: 0.0 for room in s.rooms} for s in specs
        }

    def step(self, conflict_by_room: dict[str, float]) -> None:
        for s in self.specs:
            decay = self._decay[s.name]
            for room in s.rooms:
                x = self.values[s.name][room] * decay
                x += s.gain_per_conflict_intensity * conflict_by_room.get(room, 0.0)
                self.values[s.name][room] = min(1.0, max(0.0, x))

    def snapshot(self) -> dict[str, dict[str, float]]:
        return {name: {r: round(v, 9) for r, v in rooms.items()}
                for name, rooms in self.values.items()}
