"""Per-persona inbox: the engine takes ONE event per tick, the world can
produce several. Policy (inn.yaml inbox_policy): deterministic priority +
bounded deferral, never merging. Deferred events deliver on later ticks with
their t rewritten; events older than max_defer_ticks are dropped LOUDLY into
the trace as dropped_event records. delivery_delay is logged per delivery so
metrics can quantify how often the one-tick latency stretches.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from inn.config import InboxPolicy
from inn.engine_surface import RawEvent


@dataclass(frozen=True)
class QueuedEvent:
    event: RawEvent
    enqueued_t: int
    provenance_id: str | None  # transduction provenance, if social


@dataclass(frozen=True)
class Delivery:
    event: RawEvent
    delay: int
    provenance_id: str | None


@dataclass(frozen=True)
class DroppedEvent:
    event: RawEvent
    enqueued_t: int
    dropped_t: int
    provenance_id: str | None


class Inbox:
    def __init__(self, policy: InboxPolicy, cast_order: dict[str, int]):
        self.policy = policy
        self.cast_order = cast_order
        self._queue: list[QueuedEvent] = []

    def push(self, ev: RawEvent, enqueued_t: int, provenance_id: str | None = None) -> None:
        self._queue.append(QueuedEvent(ev, enqueued_t, provenance_id))

    def _key(self, q: QueuedEvent):
        prio = self.policy.priority
        type_rank = prio.index(q.event.type) if q.event.type in prio else len(prio)
        src_rank = self.cast_order.get(q.event.source or "", len(self.cast_order))
        return (type_rank, -q.event.intensity, src_rank, q.enqueued_t)

    def pop_for_tick(self, t: int) -> tuple[Delivery | None, list[DroppedEvent]]:
        dropped = [DroppedEvent(q.event, q.enqueued_t, t, q.provenance_id)
                   for q in self._queue
                   if t - q.enqueued_t > self.policy.max_defer_ticks]
        self._queue = [q for q in self._queue
                       if t - q.enqueued_t <= self.policy.max_defer_ticks]
        if not self._queue:
            return None, dropped
        self._queue.sort(key=self._key)
        head = self._queue.pop(0)
        delivery = Delivery(event=replace(head.event, t=t),
                            delay=t - head.enqueued_t,
                            provenance_id=head.provenance_id)
        return delivery, dropped

    def __len__(self) -> int:
        return len(self._queue)
