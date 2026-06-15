"""Controlled Subject / Intervention Mode (CLAUDE.md M-G).

The observer may take manual control of ONE existing cast member (the
*controlled subject*). The engine STILL ticks that persona every tick and
computes its full interior (boredom/fatigue/anger/relations/potentials) — this
module never reads or writes engine state. In MANUAL mode the observer overrides
only the persona's OUTWARD action; the loop routes that action through the SAME
world/transducer + probe path the engine's own actions take, so the rest of the
cast perceives and reacts normally (one-tick latency). The engine's autonomous
selection is still recorded (engine_would_have_selected) but is not transduced —
override is *replace*. With no `act` issued on a tick the subject is socially
silent (a noop); its interior keeps evolving.

This file owns only DATA + VALIDATION (a finite, engine-compatible action
palette and target rules). The loop hook lives in inn/loop.py. No LLM here.

Routing — two clean paths, both already in the world layer:
  * route="transduce": actions that map to an engine action with a transducer
    row (insult/help/praise/complain/refuse/cold). The loop synthesises an
    ActionSelection for that engine action and runs it through transduce(),
    addressed to the observer-chosen target (the same target-inference field the
    engine path uses). Carries the transducer's witnessing/floor policy.
  * route="probe": `command` (engine action command_other is silent in the
    table) and `serve` (food_given is a perceivable INPUT event with no reactive
    row). These reuse the existing player-probe path with source = the subject,
    so the target perceives "the subject commanded/served me".

Known seam (documented, not a bug): the palette is necessarily asymmetric —
reactive engine-surface actions go via the transduce swap, perceivable input
events go via subject-sourced probes. Anything that cannot route cleanly through
one of these two paths is intentionally left out of the palette (future work).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from inn.config import InnConfig

ROUTE_TRANSDUCE = "transduce"
ROUTE_PROBE = "probe"
ROUTE_NONE = "noop"


@dataclass
class ControlState:
    """The live control register, shared by reference between the CLI and the
    InnLoop so `auto`/`manual`/`control`/`release` take effect on later ticks.
    MUTABLE by design (the loop reads it each tick)."""
    subject: str | None = None
    mode: str = "auto"  # "auto" | "manual"


@dataclass(frozen=True)
class PaletteEntry:
    verb: str
    route: str
    engine_action: str | None  # transduce route: engine action id with a row
    probe_type: str | None     # probe route: perceivable event type
    intensity: float           # transduce: synthesised selection score; probe: event intensity
    public: bool
    needs_target: bool


# The finite, safe action palette. Every entry routes ONLY through an existing
# transducer row or the existing probe path — no invented event types.
ACTION_PALETTE: dict[str, PaletteEntry] = {
    "observe": PaletteEntry("observe", ROUTE_NONE, None, None, 0.0, False, False),
    "noop":    PaletteEntry("noop", ROUTE_NONE, None, None, 0.0, False, False),
    "seek_activity": PaletteEntry("seek_activity", ROUTE_NONE, None, None, 0.0, False, False),
    "rest":    PaletteEntry("rest", ROUTE_NONE, None, None, 0.0, False, False),
    # transduce route (engine action -> transducer row)
    "insult":  PaletteEntry("insult", ROUTE_TRANSDUCE, "outburst", None, 0.8, True, True),
    "help":    PaletteEntry("help", ROUTE_TRANSDUCE, "cooperate", None, 0.8, False, True),
    "praise":  PaletteEntry("praise", ROUTE_TRANSDUCE, "positive_response", None, 0.8, False, True),
    "complain": PaletteEntry("complain", ROUTE_TRANSDUCE, "complain", None, 0.6, False, True),
    "refuse":  PaletteEntry("refuse", ROUTE_TRANSDUCE, "refuse", None, 0.6, True, True),
    "cold":    PaletteEntry("cold", ROUTE_TRANSDUCE, "cold_response", None, 0.5, False, True),
    "cold_reply": PaletteEntry("cold_reply", ROUTE_TRANSDUCE, "cold_response", None, 0.5, False, True),
    # probe route (subject-sourced perceivable input event)
    "command": PaletteEntry("command", ROUTE_PROBE, None, "command", 1.0, True, True),
    "serve":   PaletteEntry("serve", ROUTE_PROBE, None, "food_given", 1.0, False, True),
}

PALETTE_VERBS: tuple[str, ...] = tuple(ACTION_PALETTE)


@dataclass(frozen=True)
class InterventionAction:
    """A resolved manual action for the controlled subject at one tick."""
    verb: str
    route: str
    engine_action: str | None
    probe_type: str | None
    target: str | None
    intensity: float
    public: bool
    llm: dict | None = None  # M-H provenance (no secrets), when LLM-sourced

    def to_event(self) -> dict | None:
        """The structured action that was executed, for trace/provenance."""
        if self.route == ROUTE_NONE:
            return None
        return {"action": self.verb, "target": self.target,
                "intensity": self.intensity}


def make_intervention(verb: str, target: str | None = None,
                      llm: dict | None = None) -> InterventionAction:
    """Resolve a palette verb (+ optional target) into a routed action.
    Raises ValueError on an unknown verb — callers validate first."""
    e = ACTION_PALETTE.get(verb)
    if e is None:
        raise ValueError(f"unknown action {verb!r}")
    return InterventionAction(
        verb=e.verb, route=e.route, engine_action=e.engine_action,
        probe_type=e.probe_type, target=(target if e.needs_target else None),
        intensity=e.intensity, public=e.public, llm=llm)


def validate_target(cfg: InnConfig, presence, subject: str, verb: str,
                    target: str | None) -> str | None:
    """Return an error message if the action/target is not allowed, else None.

    Rules (no accidental telepathy): the verb must be in the palette; target-less
    verbs reject a target and target verbs require one; the target must be a cast
    member, present/reachable in the subject's current room, and not the subject
    itself."""
    from inn.chronicle import who  # local import: display only
    e = ACTION_PALETTE.get(verb)
    if e is None:
        return (f"'{verb}' is not a controlled-subject action. "
                f"palette: {', '.join(PALETTE_VERBS)}.")
    if not e.needs_target:
        if target is not None:
            return f"`{verb}` takes no target."
        return None
    if target is None:
        return f"`{verb}` needs a target ({verb} <name>)."
    cast_ids = {c.id for c in cfg.cast}
    if target not in cast_ids:
        return f"no cast member called '{target}'."
    if target == subject:
        return f"{who(subject)} can't {verb} themselves."
    present = presence.cohort(presence.room_of(subject))
    if target not in present:
        here = ", ".join(who(p) for p in present if p != subject) or "no one"
        return (f"{who(target)} isn't with {who(subject)}. "
                f"Present here: {here}.")
    return None


def serialize(t: int, subject: str, action: InterventionAction) -> dict:
    """A replayable injected-event record (session log / determinism tuple)."""
    rec = {"t": t, "subject": subject, "verb": action.verb,
           "target": action.target, "route": action.route}
    if action.llm is not None:
        rec["llm"] = action.llm
    return rec
