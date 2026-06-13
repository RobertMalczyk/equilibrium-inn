"""Transducer: ActionSelection -> perceivable events, per the inn.yaml table.

Owns the intensity policy (linear in selection potential with a per-action
floor, scaled by world attenuation — user decision at section 10.3) and
provenance stamping. It never reads or writes persona state and can only emit
events the mapper perceives (enforced at config load).

Declared lossiness: actions in declared_gaps (refuse, cold_response,
complain) emit NOTHING. The gap rows are still logged so the chronicle can
surface them.

Target inference: the engine does not expose the reaction target; the world
infers target = provoking event's source (CLAUDE.md section 2). The inference
is recorded in provenance so G1 can audit misattributions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from inn.config import InnConfig
from inn.engine_surface import ActionSelection, RawEvent


@dataclass(frozen=True)
class Provenance:
    event_id: str            # "{t}:{actor}:{action}" — stable, unique per tick/actor
    action: str
    actor: str
    t: int
    provoked_by: str | None  # provenance/event id of the provoking delivery
    target_inferred: str | None
    selection_score: float


@dataclass(frozen=True)
class Addressed:
    recipient: str
    event: RawEvent
    provenance: Provenance
    role: str  # "target" | "witness"


@dataclass(frozen=True)
class GapRecord:
    """A socially-real action that the table cannot transduce (declared gap)."""
    event_id: str
    action: str
    actor: str
    t: int
    provoked_by: str | None


@dataclass
class TransductionResult:
    addressed: list[Addressed] = field(default_factory=list)
    gaps: list[GapRecord] = field(default_factory=list)
    conflict_intensity: float = 0.0  # input to world states (room tension)


def transduce(cfg: InnConfig, t: int, actor: str, sel: ActionSelection,
              provoking_source: str | None, provoking_id: str | None,
              cohort: list[str], scale: float | None = None) -> TransductionResult:
    """Transduce one persona's selection at tick t.

    cohort: personas co-located with the actor (cast order), actor included.
    scale: override of table scale (G0 sweep axis); default from inn.yaml.
    """
    table = cfg.transducer
    scale = table.scale if scale is None else scale
    out = TransductionResult()
    event_id = f"{t}:{actor}:{sel.action}"

    if sel.action in table.declared_gaps:
        out.gaps.append(GapRecord(event_id, sel.action, actor, t, provoking_id))
        return out
    row = table.rows.get(sel.action)
    if row is None:
        return out  # silent action (no social surface in MVP)

    prov = Provenance(event_id=event_id, action=sel.action, actor=actor, t=t,
                      provoked_by=provoking_id, target_inferred=provoking_source,
                      selection_score=sel.score)
    # roots_only: the floor backs reactions to EXTERNAL provocations (probes,
    # player, or unprovoked discharge); reaction-to-reaction hops carry pure
    # scale*potential so cascades decay geometrically (G0 finding F2).
    is_root = provoking_id is None or provoking_id.endswith(":probe")
    if table.floor_policy == "roots_only" and not is_root:
        base = scale * sel.score
    else:
        base = max(row.floor, scale * sel.score)

    target = provoking_source
    if target is not None and target != actor:
        ctx = {"public": True} if row.witness_attenuation is not None else {}
        out.addressed.append(Addressed(
            recipient=target,
            event=RawEvent(type=row.as_event, t=t, source=actor,
                           intensity=base, context=ctx),
            provenance=prov, role="target"))
    if row.witness_attenuation is not None:
        for pid in cohort:
            if pid in (actor, target):
                continue
            out.addressed.append(Addressed(
                recipient=pid,
                event=RawEvent(type=row.as_event, t=t, source=actor,
                               intensity=base * row.witness_attenuation,
                               context={"public": True}),
                provenance=prov, role="witness"))
    if row.as_event == "insult":
        out.conflict_intensity = base
    return out
