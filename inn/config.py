"""Load and validate inn.yaml into typed config objects.

Every behavior-shaping number lives in inn.yaml (CLAUDE.md section 4.1);
modules receive these objects and hold no literals of their own. The loader
rejects unknown keys so a typo cannot silently become a default.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from inn.engine_surface import (
    ENGINE_ACTIONS,
    ENGINE_ROOT,
    GLOBAL_STATES,
    PERCEIVABLE_EVENTS,
    PINNED_COMMIT,
)


def _check_keys(d: dict, allowed: set[str], where: str) -> None:
    unknown = set(d) - allowed
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}")


def deep_merge(a: dict, b: dict) -> dict:
    """Recursive dict overlay (b wins). Used to stack profile/sweep deltas on
    the base engine_overrides without mutating either input."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in a.items()}
    for k, v in b.items():
        out[k] = (deep_merge(out[k], v)
                  if isinstance(v, dict) and isinstance(out.get(k), dict) else v)
    return out


@dataclass(frozen=True)
class CastMember:
    id: str
    room_home: str


@dataclass(frozen=True)
class ScheduleBlock:
    start: str  # "HH:MM"
    end: str
    room: str
    activity: str | None = None
    meal: bool = False


@dataclass(frozen=True)
class ActivityEntry:
    id: str
    room: str
    kind: str  # work | leisure | social
    window: tuple[str, str]
    capacity: int
    novelty_start: float
    deplete_per_offer: float
    replenish_per_tick: float
    min_novelty: float
    offer_latency: int
    outdoor: bool


@dataclass(frozen=True)
class TransducerRow:
    action: str
    as_event: str
    floor: float
    witness_attenuation: float | None  # None = witnesses receive nothing
    witness_public: bool


@dataclass(frozen=True)
class TransducerTable:
    shape: str
    scale: float
    floor_policy: str  # "all" | "roots_only"
    rows: dict[str, TransducerRow]
    declared_gaps: tuple[str, ...]
    silent: tuple[str, ...]


@dataclass(frozen=True)
class WorldStateSpec:
    name: str
    rooms: tuple[str, ...]
    half_life_s: float
    gain_per_conflict_intensity: float


@dataclass(frozen=True)
class InboxPolicy:
    rule: str
    max_defer_ticks: int
    priority: tuple[str, ...]


@dataclass(frozen=True)
class Probe:
    day: int  # 1-based
    hhmm: str
    type: str
    intensity: float
    source: str | None = None
    target: str | None = None  # persona the probe is delivered to
    item: str | None = None
    room: str | None = None
    context: dict = field(default_factory=dict)
    until_hhmm: str | None = None  # for repeating probes (weather step)
    every_ticks: int | None = None


@dataclass(frozen=True)
class ProfileSpec:
    """A named instrument character (CLAUDE.md DEC-1). Selects an
    engine_overrides delta (deep-merged onto the base) plus a set of catalog
    entries to disable, so the same inn.yaml yields the frozen hearth-stable
    profile or the scarcity-faithful semantic profile."""
    name: str
    engine_overrides: dict
    disable_activities: tuple[str, ...]


@dataclass(frozen=True)
class InnConfig:
    days: int
    engine_commit: str
    cast: tuple[CastMember, ...]
    cast_order: dict[str, int]
    event_sources: tuple[str, ...]
    rooms: tuple[str, ...]
    schedules: dict[str, tuple[ScheduleBlock, ...]]
    meal_source: str
    menu_rotation: tuple[str, ...]
    meal_intensity: float
    activities: dict[str, ActivityEntry]
    transducer: TransducerTable
    co_located_attenuation: float
    world_states: tuple[WorldStateSpec, ...]
    contention_rule: str
    inbox: InboxPolicy
    probes: dict[str, tuple[Probe, ...]]
    provoking_event_types: tuple[str, ...]
    g0: dict
    engine_overrides: dict
    burst_overlay: bool
    profiles: dict[str, ProfileSpec]
    default_profile: str | None
    observation: dict
    baseline: dict
    yaml_sha256: str

    def resolved_engine_overrides(self, profile: str | None) -> dict:
        """Base engine_overrides with the named profile's delta stacked on top.
        profile=None -> the bare base (historical/no-profile behavior)."""
        if profile is None:
            return self.engine_overrides
        if profile not in self.profiles:
            raise ValueError(f"unknown profile {profile!r}")
        return deep_merge(self.engine_overrides, self.profiles[profile].engine_overrides)

    def disabled_activities(self, profile: str | None) -> frozenset[str]:
        if profile is None:
            return frozenset()
        if profile not in self.profiles:
            raise ValueError(f"unknown profile {profile!r}")
        return frozenset(self.profiles[profile].disable_activities)


def _parse_probe(p: dict) -> Probe:
    _check_keys(p, {"t", "type", "source", "target", "intensity", "room",
                    "context", "item", "until", "every_ticks"}, "probe")
    day_s, hhmm = p["t"].split()
    if not day_s.startswith("day"):
        raise ValueError(f"probe t must be 'day<N> HH:MM', got {p['t']!r}")
    until = p.get("until")
    if until is not None:
        u_day, until = until.split()
        if u_day != day_s:
            raise ValueError("probe 'until' must be on the same day")
    return Probe(
        day=int(day_s[3:]), hhmm=hhmm, type=p["type"],
        intensity=float(p["intensity"]), source=p.get("source"),
        target=p.get("target"), item=p.get("item"), room=p.get("room"),
        context=dict(p.get("context", {})), until_hhmm=until,
        every_ticks=p.get("every_ticks"),
    )


def load_inn_config(path: str | Path) -> InnConfig:
    path = Path(path)
    raw_bytes = path.read_bytes()
    doc = yaml.safe_load(raw_bytes)
    _check_keys(doc, {"meta", "cast", "event_sources", "rooms", "schedules",
                      "meals", "activities", "transducer", "witnessing",
                      "world", "world_states", "contention", "inbox_policy",
                      "probes", "g0", "engine_overrides", "profiles",
                      "burst_overlay", "observation", "baseline"}, "inn.yaml")

    meta = doc["meta"]
    if meta["engine_commit"] != PINNED_COMMIT:
        raise ValueError("inn.yaml engine_commit does not match the seam pin")

    cast = tuple(CastMember(**c) for c in doc["cast"])
    cast_ids = [c.id for c in cast]
    if len(set(cast_ids)) != len(cast_ids):
        raise ValueError("duplicate cast ids")
    rooms = tuple(doc["rooms"])

    for c in cast:
        persona_yaml = ENGINE_ROOT / "data" / "personas" / f"{c.id}.yaml"
        if not persona_yaml.is_file():
            raise ValueError(f"cast member {c.id} has no persona YAML in the engine")
        if c.room_home not in rooms:
            raise ValueError(f"{c.id}: unknown room_home {c.room_home}")

    activities: dict[str, ActivityEntry] = {}
    for a in doc["activities"]:
        entry = ActivityEntry(
            id=a["id"], room=a["room"], kind=a["kind"],
            window=(a["window"][0], a["window"][1]), capacity=int(a["capacity"]),
            novelty_start=float(a["novelty_start"]),
            deplete_per_offer=float(a["deplete_per_offer"]),
            replenish_per_tick=float(a["replenish_per_tick"]),
            min_novelty=float(a["min_novelty"]),
            offer_latency=int(a["offer_latency"]), outdoor=bool(a["outdoor"]),
        )
        if entry.room not in rooms:
            raise ValueError(f"activity {entry.id}: unknown room {entry.room}")
        if entry.kind not in ("work", "leisure", "social"):
            raise ValueError(f"activity {entry.id}: bad kind {entry.kind}")
        activities[entry.id] = entry

    schedules: dict[str, tuple[ScheduleBlock, ...]] = {}
    for pid, blocks in doc["schedules"].items():
        if pid not in cast_ids:
            raise ValueError(f"schedule for non-cast persona {pid}")
        parsed = []
        for b in blocks:
            _check_keys(b, {"from", "to", "room", "activity", "meal"}, f"schedule {pid}")
            blk = ScheduleBlock(start=b["from"], end=b["to"], room=b["room"],
                                activity=b.get("activity"), meal=bool(b.get("meal", False)))
            if blk.room not in rooms:
                raise ValueError(f"schedule {pid}: unknown room {blk.room}")
            if blk.activity is not None:
                if blk.activity not in activities:
                    raise ValueError(f"schedule {pid}: unknown activity {blk.activity}")
                if activities[blk.activity].room != blk.room:
                    raise ValueError(f"schedule {pid}: activity {blk.activity} not in {blk.room}")
            parsed.append(blk)
        schedules[pid] = tuple(parsed)
    missing = set(cast_ids) - set(schedules)
    if missing:
        raise ValueError(f"cast without schedules: {sorted(missing)}")

    t = doc["transducer"]
    rows: dict[str, TransducerRow] = {}
    for action, r in t["rows"].items():
        if r["as"] not in PERCEIVABLE_EVENTS:
            raise ValueError(f"transducer row {action}: '{r['as']}' not perceivable")
        wit = r.get("witnesses")
        rows[action] = TransducerRow(
            action=action, as_event=r["as"], floor=float(r["floor"]),
            witness_attenuation=None if wit is None else float(wit["attenuation"]),
            witness_public=bool(wit["public"]) if wit else False,
        )
    floor_policy = t["intensity"].get("floor_policy", "all")
    if floor_policy not in ("all", "roots_only"):
        raise ValueError(f"transducer: bad floor_policy {floor_policy}")
    table = TransducerTable(
        shape=t["intensity"]["shape"], scale=float(t["intensity"]["scale"]),
        floor_policy=floor_policy,
        rows=rows, declared_gaps=tuple(t["declared_gaps"]), silent=tuple(t["silent"]),
    )
    overlap = set(rows) & set(table.declared_gaps)
    if overlap:
        raise ValueError(f"actions both transduced and declared gaps: {sorted(overlap)}")

    # G1 coverage gate: every action the engine can select must be accounted
    # for — transduced, declared a gap, or declared silent — and no entry may
    # name a phantom action the engine never emits (that catches dead config
    # like the removed `hostile_action`). Without this, a selectable action the
    # table forgets falls through transduce() untraced (semantic-correctness
    # regression). See engine_surface.ENGINE_ACTIONS.
    accounted = set(rows) | set(table.declared_gaps) | set(table.silent)
    uncovered = ENGINE_ACTIONS - accounted
    if uncovered:
        raise ValueError(
            f"transducer does not account for engine actions {sorted(uncovered)} "
            "(add each to rows, declared_gaps, or silent)")
    phantom = accounted - set(ENGINE_ACTIONS)
    if phantom:
        raise ValueError(
            f"transducer references actions the engine never emits {sorted(phantom)} "
            "(remove them or re-verify ENGINE_ACTIONS against the engine pin)")

    world_states = tuple(
        WorldStateSpec(name=name, rooms=tuple(w["rooms"]),
                       half_life_s=float(w["half_life_s"]),
                       gain_per_conflict_intensity=float(w["gain_per_conflict_intensity"]))
        for name, w in doc["world_states"].items()
    )

    ip = doc["inbox_policy"]
    for ev_type in ip["priority"]:
        if ev_type not in PERCEIVABLE_EVENTS:
            raise ValueError(f"inbox priority lists non-perceivable type {ev_type}")

    # Provoking event types: the perceivable events that, when delivered, become
    # a persona's current provocation source for reactive target inference
    # (loop._last_prov -> transducer target). Config-driven so closing a social
    # gap (e.g. the S3 mapper events) needs no code change. Absent `world` block
    # falls back to the historical safe default (insult + command only). Every
    # configured name must be perceivable, so a typo or an event the mapper does
    # not know fails loudly rather than silently never provoking.
    world = doc.get("world") or {}  # absent or comment-only block -> default
    _check_keys(world, {"provoking_event_types"}, "world")
    provoking = tuple(world.get("provoking_event_types", ("insult", "command")))
    for ev_type in provoking:
        if ev_type not in PERCEIVABLE_EVENTS:
            raise ValueError(
                f"world.provoking_event_types lists non-perceivable type {ev_type!r}")

    # Profiles (CLAUDE.md DEC-1): named instrument characters. Each overlays an
    # engine_overrides delta + disables some catalog entries. `default` names the
    # shipped profile. Absent block -> no profiles, no default (bare base config).
    prof_doc = doc.get("profiles") or {}
    default_profile = prof_doc.get("default")
    profiles: dict[str, ProfileSpec] = {}
    for pname, pspec in prof_doc.items():
        if pname == "default":
            continue
        pspec = pspec or {}
        _check_keys(pspec, {"engine_overrides", "disable_activities"}, f"profile {pname}")
        eo = dict(pspec.get("engine_overrides", {}))
        for state in eo.get("idle_recovery", {}):
            if state not in GLOBAL_STATES:
                raise ValueError(
                    f"profile {pname}: idle_recovery state {state!r} is not a global state")
        da = tuple(pspec.get("disable_activities", ()))
        for aid in da:
            if aid not in activities:
                raise ValueError(f"profile {pname}: disable_activities unknown id {aid!r}")
        profiles[pname] = ProfileSpec(name=pname, engine_overrides=eo, disable_activities=da)
    if default_profile is not None and default_profile not in profiles:
        raise ValueError(f"profiles.default {default_profile!r} is not a defined profile")

    # Observation block (CLAUDE.md M-D): DISPLAY-ONLY thresholds for mood labels
    # and threshold-crossing markers. Read by inn.observe, NEVER by the loop, so
    # adding/altering it cannot change the trace (golden stays valid). Validated
    # only enough to catch typos: `high` keys must be real global states.
    observation = dict(doc.get("observation") or {})
    _check_keys(observation, {"high"}, "observation")
    for state in (observation.get("high") or {}):
        if state not in GLOBAL_STATES:
            raise ValueError(f"observation.high: {state!r} is not a global state")

    # Baseline cast (CLAUDE.md M-E): the fair control NPC's automaton/bark
    # tunables. Behaviour-shaping numbers live here as data (hard rule 0.3), not
    # in inn/baseline.py. Read only by the baseline loop; never by the engine path.
    baseline = dict(doc.get("baseline") or {})

    sources = tuple(doc["event_sources"])
    probes = {name: tuple(_parse_probe(p) for p in plist)
              for name, plist in doc["probes"].items()}
    for name, plist in probes.items():
        for p in plist:
            if p.source is not None and p.source not in sources and p.source not in cast_ids:
                raise ValueError(f"probe in {name}: unknown source {p.source}")
            if p.target is not None and p.target not in cast_ids:
                raise ValueError(f"probe in {name}: unknown target {p.target}")
            if p.day < 1 or p.day > int(meta["days"]):
                raise ValueError(f"probe in {name}: day {p.day} out of range")

    return InnConfig(
        days=int(meta["days"]),
        engine_commit=meta["engine_commit"],
        cast=cast,
        cast_order={cid: i for i, cid in enumerate(cast_ids)},
        event_sources=sources,
        rooms=rooms,
        schedules=schedules,
        meal_source=doc["meals"]["source"],
        menu_rotation=tuple(doc["meals"]["menu_rotation"]),
        meal_intensity=float(doc["meals"]["intensity"]),
        activities=activities,
        transducer=table,
        co_located_attenuation=float(doc["witnessing"]["co_located_attenuation"]),
        world_states=world_states,
        contention_rule=doc["contention"]["rule"],
        inbox=InboxPolicy(rule=ip["rule"], max_defer_ticks=int(ip["max_defer_ticks"]),
                          priority=tuple(ip["priority"])),
        probes=probes,
        provoking_event_types=provoking,
        g0=doc["g0"],
        engine_overrides=dict(doc.get("engine_overrides", {})),
        burst_overlay=bool(doc.get("burst_overlay", False)),
        profiles=profiles,
        default_profile=default_profile,
        observation=observation,
        baseline=baseline,
        yaml_sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )
