"""G1 semantic-audit contract tests.

These lock the engine<->world boundary invariants the G1 audit relies on:
action-coverage completeness, public-event fan-out (target + co-located
witnesses, nobody else), declared-gap trace-visibility, and the player/marta
non-interior contract. They are deterministic; they do not depend on LLM
believability judging.

See experiments/out/g0/G1_audit.md for the audit these tests back.
"""

from pathlib import Path

import pytest

from inn.config import load_inn_config
from inn.engine_surface import ENGINE_ACTIONS, ActionSelection
from inn.config import Probe
from inn.loop import InnLoop
from inn.trace import TraceWriter
from inn.transducer import transduce

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")


def _sel(action, score):
    return ActionSelection(action=action, score=score, kind=None,
                           interrupted=False, post_effects=None, explanation="")


# -- 1. action-coverage completeness ---------------------------------------

def test_every_engine_action_is_accounted():
    """Every action the engine can select is transduced, a declared gap, or
    declared silent — nothing falls through transduce() untraced."""
    t = CFG.transducer
    accounted = set(t.rows) | set(t.declared_gaps) | set(t.silent)
    assert ENGINE_ACTIONS <= accounted, ENGINE_ACTIONS - accounted


def test_no_phantom_actions_in_table():
    """The table names no action the engine never emits (catches dead config
    like the removed `hostile_action`)."""
    t = CFG.transducer
    named = set(t.rows) | set(t.declared_gaps) | set(t.silent)
    assert named <= set(ENGINE_ACTIONS), named - set(ENGINE_ACTIONS)


def test_neutral_default_is_declared_silent():
    """`neutral` is the selector's idle/no-op default and the most-emitted
    action; it must be explicitly silent, not an undeclared fall-through."""
    assert "neutral" in CFG.transducer.silent


def _mutate_yaml(tmp_path, old, new):
    src = (ROOT / "inn.yaml").read_text(encoding="utf-8")
    assert old in src
    bad = tmp_path / "inn.yaml"
    bad.write_text(src.replace(old, new), encoding="utf-8")
    return bad


def test_coverage_gate_rejects_uncovered_action(tmp_path):
    # drop `neutral` from the silent list -> an engine action is now uncovered
    bad = _mutate_yaml(
        tmp_path,
        "silent: [neutral, sleep, seek_stimulus",
        "silent: [sleep, seek_stimulus")
    with pytest.raises(ValueError, match="does not account for engine actions"):
        load_inn_config(bad)


def test_coverage_gate_rejects_phantom_action(tmp_path):
    # re-introduce a phantom action the engine never emits
    bad = _mutate_yaml(
        tmp_path,
        "silent: [neutral,",
        "silent: [hostile_action, neutral,")
    with pytest.raises(ValueError, match="never emits"):
        load_inn_config(bad)


def test_s3_gap_is_closed():
    """The S3 one-way-authority gap is now CLOSED (engine 0b7df59 Social Event
    Mapper Pack): the three negative social actions have real transducer rows
    and there are no declared gaps left. Re-opening a gap is a G1 decision; this
    test fails loudly if the set drifts."""
    assert CFG.transducer.declared_gaps == ()
    assert CFG.transducer.rows["refuse"].as_event == "refusal"
    assert CFG.transducer.rows["cold_response"].as_event == "cold_reply"
    assert CFG.transducer.rows["complain"].as_event == "complaint"


# -- 2. declared-gap trace-visibility --------------------------------------

def test_target_reaction_now_feeds_the_social_world():
    """With the S3 gap closed, a direct target that answers with cold_response
    (e.g. Halgrim to an insult) now emits a real cold_reply back to the
    provoker — the authority loop closes both ways. A truly silent action
    (neutral) still leaves NOTHING; the distinction the audit turns on is
    preserved (silence is strictly emptier than a transduced reaction)."""
    r = transduce(CFG, 100, "halgrim", _sel("cold_response", 0.6),
                  provoking_source="marta", provoking_id="99:marta:insult:probe",
                  cohort=["halgrim", "welf"])
    assert r.gaps == []
    assert [a.role for a in r.addressed] == ["target"]  # direct-only, no witnesses
    assert r.addressed[0].recipient == "marta"
    assert r.addressed[0].event.type == "cold_reply"
    assert r.addressed[0].provenance.provoked_by == "99:marta:insult:probe"
    # a truly silent action leaves NOTHING — neutral is strictly emptier
    silent = transduce(CFG, 100, "halgrim", _sel("neutral", 0.0),
                       provoking_source=None, provoking_id=None, cohort=["halgrim"])
    assert silent.addressed == [] and silent.gaps == []


# -- 3. public-event fan-out (target + co-located witnesses, nobody else) ---

def _loop(tmp_path, plan="control"):
    return InnLoop(CFG, seed=7, probe_plan=plan,
                   trace=TraceWriter(tmp_path / "t.jsonl.gz"))


def _public_insult(loop, room, target):
    t = loop.clock.tick_at(1, "10:00")  # mid-morning: cohorts differ by room
    loop.presence.update(t)
    probe = Probe(day=1, hhmm="10:00", type="insult", intensity=0.8,
                  source="marta", target=target, room=room,
                  context={"public": True})
    loop._deliver_probe(t, probe)
    return t


def test_public_probe_reaches_target_full_and_witnesses_attenuated(tmp_path):
    loop = _loop(tmp_path)
    t = loop.clock.tick_at(1, "10:00")
    loop.presence.update(t)
    cohort = loop.presence.cohort("common_room")
    assert "wojslaw" in cohort and "welf" in cohort  # both scheduled here at 10:00
    _public_insult(loop, "common_room", "wojslaw")
    # target: full intensity
    d_target, _ = loop.inboxes["wojslaw"].pop_for_tick(t)
    assert d_target is not None and d_target.event.intensity == pytest.approx(0.8)
    # co-located witness: attenuated by co_located_attenuation (0.5)
    d_wit, _ = loop.inboxes["welf"].pop_for_tick(t)
    assert d_wit is not None
    assert d_wit.event.intensity == pytest.approx(0.8 * CFG.co_located_attenuation)
    assert d_wit.event.context.get("public") is True


def test_public_probe_does_not_reach_other_rooms(tmp_path):
    loop = _loop(tmp_path)
    t = loop.clock.tick_at(1, "10:00")
    loop.presence.update(t)
    # halgrim/cichy/edda are NOT in common_room at 10:00 (yard/stable/kitchen)
    for pid in ("halgrim", "cichy", "edda"):
        assert loop.presence.room_of(pid) != "common_room"
    _public_insult(loop, "common_room", "wojslaw")
    for pid in ("halgrim", "cichy", "edda"):
        d, _ = loop.inboxes[pid].pop_for_tick(t)
        assert d is None, f"{pid} (other room) must not witness the scene"


# -- 4. player / marta non-interior contract -------------------------------

def test_event_sources_have_no_runtime_or_inbox(tmp_path):
    """player and marta are event SOURCES with a room/id but no equilibrium
    interior: they are never cast runtimes and never have inboxes (CLAUDE.md
    section 1, 4.2). They cannot be an 8th persona."""
    loop = _loop(tmp_path)
    cast_ids = {c.id for c in CFG.cast}
    assert set(loop.runtimes) == cast_ids
    for label in CFG.event_sources:  # marta, player
        assert label not in loop.runtimes
        assert label not in loop.inboxes
