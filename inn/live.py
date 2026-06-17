"""Live-frontier intervention session (CLAUDE.md M-G/M-I).

An incremental driver over `InnLoop` for the Observatory cockpit. The observer
influences the world ONLY at the *live frontier* — the latest computed tick —
and the future then emerges from that new state. There is deliberately NO
future-queue: an intervention is validated against the frontier state at
EXECUTION time and applied at the frontier tick, then the simulation advances
forward from there.

Why a real module (not JS): the live-frontier rules — frontier tracking,
execution-time target validation (no telepathy), and the byte-for-byte
equivalence with a batch run carrying the same (control, interventions) — are
behavioural contracts and must be unit-testable in CPython. The Pyodide cockpit
imports this exact class, so the browser path runs the same code the tests pin.

This module owns NO dynamics: it only drives `InnLoop._step` tick by tick (the
same call `InnLoop.run` makes) and mutates the shared, mutable `ControlState`
(the same register the CLI's auto/manual/control/release toggle). Stepping
incrementally yields the identical trace to `InnLoop.run` over the same ticks,
so determinism and the golden are untouched.
"""

from __future__ import annotations

from inn.config import InnConfig
from inn.intervention import (
    ControlState,
    InterventionAction,
    make_intervention,
    validate_target,
)
from inn.loop import InnLoop


class _Records:
    """A minimal in-memory trace sink (TraceWriter-shaped: emit/close)."""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def emit(self, record: dict) -> None:
        self.records.append(record)

    def close(self) -> str:  # pragma: no cover - parity hashing not used live
        return ""


class LiveSession:
    """Drive one inn run forward incrementally, intervening only at the frontier.

    `frontier` is the number of ticks already computed; the next tick to run (the
    live frontier the observer acts on) is exactly `frontier`. The observer may
    intervene only there — never at an arbitrary future tick.
    """

    def __init__(self, cfg: InnConfig, profile: str | None, plan: str, seed: int,
                 total: int, subject: str | None = None, mode: str = "auto"):
        self.cfg = cfg
        self.total = int(total)
        self.mem = _Records()
        # Always construct WITH a ControlState (subject may be None). With
        # subject=None the loop never matches the controlled branch, so the run
        # is byte-identical to an autonomous run — taking control later is just a
        # mutation of this shared, mutable register (CLAUDE.md M-G).
        self.control = ControlState(subject, mode)
        self.loop = InnLoop(cfg, seed=int(seed), probe_plan=plan, trace=self.mem,
                            profile=profile, control=self.control)
        self.frontier = 0

    # -- state ---------------------------------------------------------------

    @property
    def records(self) -> list[dict]:
        return self.mem.records

    @property
    def subject(self) -> str | None:
        return self.control.subject

    @property
    def mode(self) -> str:
        return self.control.mode

    def at_end(self) -> bool:
        return self.frontier >= self.total

    # -- advancing -----------------------------------------------------------

    def advance(self, n: int = 1) -> int:
        """Step the live simulation forward up to `n` ticks (clamped to the run
        length). Returns the new frontier. This is the SAME per-tick call
        `InnLoop.run` makes, so the trace is identical to a batch run."""
        end = min(self.total, self.frontier + max(0, int(n)))
        for t in range(self.frontier, end):
            self.loop._step(t)
        self.frontier = end
        return self.frontier

    def advance_all(self) -> int:
        return self.advance(self.total - self.frontier)

    # -- control register ----------------------------------------------------

    def take_control(self, subject: str | None, mode: str = "manual") -> None:
        """Take (or change) control of a subject at the frontier. Affects only
        later ticks — already-computed history is immutable."""
        self.control.subject = subject
        self.control.mode = mode

    def release(self) -> None:
        self.control.subject = None
        self.control.mode = "auto"

    def set_mode(self, mode: str) -> None:
        self.control.mode = mode

    # -- frontier inspection (for the UI) ------------------------------------

    def present_with(self, subject: str | None = None) -> list[str]:
        """Cast members co-located with the subject AT THE LIVE FRONTIER — the
        only valid targets. Computed from presence at the frontier tick."""
        subject = subject or self.control.subject
        if subject is None:
            return []
        self.loop.presence.update(self.frontier)
        room = self.loop.presence.room_of(subject)
        return [p for p in self.loop.presence.cohort(room) if p != subject]

    def engine_would(self, subject: str | None = None) -> str | None:
        """What the engine selected for the subject on the most recent computed
        tick — read-only reference (never recomputed, never forced)."""
        subject = subject or self.control.subject
        if subject is None or not self.records:
            return None
        sel = self.records[-1]["personas"].get(subject, {}).get("selection", {})
        return sel.get("action")

    # -- intervening at the frontier -----------------------------------------

    def validate(self, verb: str, target: str | None) -> str | None:
        """Validate an action+target AT THE LIVE FRONTIER (execution-time, against
        current presence). Returns an error message or None. No telepathy: a
        target that is not co-located at the frontier is rejected."""
        subject = self.control.subject
        if subject is None:
            return "Take control of a subject first."
        if self.at_end():
            return "The simulation is already at its end — nothing left to run."
        self.loop.presence.update(self.frontier)
        return validate_target(self.cfg, self.loop.presence, subject, verb, target)

    def intervene(self, verb: str, target: str | None = None,
                  advance: int = 8, llm: dict | None = None) -> str | None:
        """Apply a manual override at the live frontier and continue.

        Validates at execution time, requires MANUAL mode (so the override
        actually replaces the outward action — the M-G contract), applies it at
        the frontier tick, then advances `advance` ticks so the world responds.
        Returns an error string on rejection, else None.
        """
        err = self.validate(verb, target)
        if err is not None:
            return err
        if self.control.mode != "manual":
            self.control.mode = "manual"
        action: InterventionAction = make_intervention(verb, target, llm=llm)
        # Queue at the frontier tick (NOT an arbitrary future tick) and run it.
        self.loop.queue_intervention(self.frontier, action)
        self.advance(1)
        if advance > 0:
            self.advance(advance)
        return None
