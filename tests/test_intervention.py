"""M-G — Controlled Subject / Intervention Mode acceptance tests.

The 12 acceptance criteria (CLAUDE.md M-G) plus the load-bearing invariants:
manual-noop silence, one-tick-latency attribution, probe-route delivery, and
replay reproducibility. Deterministic: fixed seed + the calm `control` plan.
"""

from pathlib import Path

from inn import metrics as M
from inn import observe as O
from inn.cli import CliSession
from inn.config import load_inn_config
from inn.intervention import (
    ACTION_PALETTE,
    ControlState,
    make_intervention,
    validate_target,
)
from inn.session import replay, run_session

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")
GOLDEN = ROOT / "tests" / "golden" / "canonical_session.sha256"
INCIDENT_ACTIONS = tuple(CFG.g0["incident_def"]["actions"])

SUBJECT = "welf"
TARGET = "halgrim"   # co-located with welf in the common room at mid-day
TICK = 200
NT = 320

INSULT = [{"t": TICK, "subject": SUBJECT, "verb": "insult", "target": TARGET}]
COMMAND = [{"t": TICK, "subject": SUBJECT, "verb": "command", "target": TARGET}]


def _auto(d: Path) -> list[dict]:
    run_session(CFG, "control", d, seed=7, n_ticks=NT)
    return M.load_records(d / "trace.jsonl.gz")


def _manual(d: Path, script: list[dict], mode: str = "manual") -> list[dict]:
    run_session(CFG, "control", d, seed=7, n_ticks=NT,
                control=ControlState(SUBJECT, mode), interventions=script)
    return M.load_records(d / "trace.jsonl.gz")


def _session_at(tmp_path: Path, tick: int = TICK) -> CliSession:
    s = CliSession(CFG, seed=7, out_dir=tmp_path)
    s.do(f"wait {tick}")
    return s


# 1 — autonomous (no control) run stays byte-identical to the golden trace.
def test_autonomous_run_matches_golden(tmp_path):
    h = run_session(CFG, "control", tmp_path / "g")
    assert GOLDEN.is_file()
    assert h["trace_sha256"] == GOLDEN.read_text().strip()


# 2 — selecting a controlled NPC.
def test_control_selects_subject(tmp_path):
    s = CliSession(CFG, seed=7, out_dir=tmp_path)
    s.do("control welf")
    assert s.control.subject == "welf" and s.control.mode == "auto"


# 3 — controlled NPC remains a normal runtime persona (full engine interior).
def test_controlled_subject_keeps_full_interior(tmp_path):
    ctrl = _manual(tmp_path / "b", INSULT)
    g = ctrl[TICK]["personas"][SUBJECT]["state_after_post"]["global"]
    assert {"boredom", "fatigue", "anger", "frustration", "stress"} <= set(g)


# 4 — AUTO mode preserves autonomous behaviour (only the annotation differs).
def test_auto_preserves_autonomous_behaviour(tmp_path):
    auto = _auto(tmp_path / "a")
    ctrl = _manual(tmp_path / "b", [], mode="auto")
    for ra, rc in zip(auto, ctrl):
        assert ra["personas"] == rc["personas"]
        assert ra["transductions"] == rc["transductions"]
    assert ctrl[TICK]["intervention"]["selected_by"] == "engine"


# 5 — MANUAL mode records manual_override provenance.
def test_manual_records_override_provenance(tmp_path):
    ctrl = _manual(tmp_path / "b", INSULT)
    iv = ctrl[TICK]["intervention"]
    assert iv["selected_by"] == "manual_override"
    assert iv["user_selected_action"] == "insult"
    assert iv["target"] == TARGET
    assert iv["route"] == "transduce"


# 6 — engine_would_have_selected is captured (and equals the autonomous choice).
def test_engine_would_have_selected_captured(tmp_path):
    auto = _auto(tmp_path / "a")
    ctrl = _manual(tmp_path / "b", INSULT)
    iv = ctrl[TICK]["intervention"]
    assert iv["engine_would_have_selected"] == \
        auto[TICK]["personas"][SUBJECT]["selection"]["action"]


# 7 — manual action goes through the normal world/transducer path; the target
#     reacts with one-tick latency, attributed back to the subject.
def test_manual_action_routes_through_world(tmp_path):
    ctrl = _manual(tmp_path / "b", INSULT)
    fired = [r["t"] for r in ctrl for tr in r.get("transductions", [])
             if tr["actor"] == SUBJECT and tr["as"] == "insult"
             and tr["target_inferred"] == TARGET and tr["role"] == "target"]
    assert fired and fired[0] == TICK
    reaction = [r["t"] for r in ctrl for tr in r.get("transductions", [])
                if tr["actor"] == TARGET and tr.get("target_inferred") == SUBJECT
                and r["t"] > TICK]
    assert reaction, "target should react to the manual insult"


# 8 — target validation rejects absent / unreachable / illegal targets.
def test_target_validation_rejects_bad_targets(tmp_path):
    s = _session_at(tmp_path)
    s.do("control welf")
    s.do("manual")
    assert "don't know" in s.do("act insult nobody")[0].lower()
    present = set(s._present_to(SUBJECT))
    absent = [c.id for c in CFG.cast if c.id != SUBJECT and c.id not in present]
    assert absent, "expected at least one cast member elsewhere at mid-day"
    out = s.do(f"act insult {absent[0]}")
    assert "isn't with" in out[0]
    # direct validator: no telepathy, no self-targeting, target-less actions
    assert validate_target(CFG, s.loop.presence, SUBJECT, "insult", absent[0])
    assert validate_target(CFG, s.loop.presence, SUBJECT, "insult", SUBJECT)
    assert validate_target(CFG, s.loop.presence, SUBJECT, "rest", TARGET)
    assert validate_target(CFG, s.loop.presence, SUBJECT, "insult", None)


# 9 — manual override does NOT mutate engine state (interior identical at the
#     override tick: the engine ticked the subject exactly as it would have).
def test_override_does_not_mutate_engine_state(tmp_path):
    auto = _auto(tmp_path / "a")
    ctrl = _manual(tmp_path / "b", INSULT)
    assert auto[TICK]["personas"][SUBJECT]["state_after_post"] == \
        ctrl[TICK]["personas"][SUBJECT]["state_after_post"]


# 10 — release returns the NPC to autonomous behaviour.
def test_release_returns_to_autonomous(tmp_path):
    s = CliSession(CFG, seed=7, out_dir=tmp_path)
    s.do("control welf")
    out = s.do("release")
    assert s.control.subject is None and "release" in out[0].lower()


# 11 — `why <npc>` explains manual vs autonomous causality.
def test_why_distinguishes_manual_from_autonomous(tmp_path):
    ctrl = _manual(tmp_path / "b", INSULT)
    # ask "why" at the moment of the override (before later autonomous reactions)
    lines = O.why(ctrl[:TICK + 1], SUBJECT)
    assert any("MANUAL OVERRIDE" in ln for ln in lines)
    assert any("engine would have selected" in ln for ln in lines)
    # a non-controlled persona still gets the ordinary autonomous account
    other = O.why(ctrl, TARGET)
    assert not any("MANUAL OVERRIDE" in ln for ln in other)


# 12 — reports count manual interventions.
def test_report_counts_interventions(tmp_path):
    ctrl = _manual(tmp_path / "b", INSULT)
    auto = _auto(tmp_path / "a")
    cast = [c.id for c in CFG.cast]
    r = O.report_intervention(ctrl, auto, cast, INCIDENT_ACTIONS)
    assert r["n_overrides"] == 1
    assert r["by_action"] == {"insult": 1}
    assert r["targets"] == {TARGET: 1}
    assert r["incidents_manual"] >= r["incidents_auto"]


# --- load-bearing invariants beyond the numbered list ----------------------

def test_manual_noop_is_silent(tmp_path):
    """A MANUAL tick with no `act` emits nothing through the transducer."""
    ctrl = _manual(tmp_path / "b", [])
    subj_trans = [tr for r in ctrl for tr in r.get("transductions", [])
                  if tr["actor"] == SUBJECT]
    assert subj_trans == []
    assert ctrl[TICK]["intervention"]["selected_by"] == "manual_noop"


def test_probe_route_command_reaches_target(tmp_path):
    ctrl = _manual(tmp_path / "b", COMMAND)
    probes = [p["probe"] for r in ctrl for p in r.get("probes", [])
              if p["probe"].split(":")[1] == SUBJECT
              and p["probe"].split(":")[2] == "command"]
    assert probes
    assert ctrl[TICK]["intervention"]["route"] == "probe"


def test_palette_routes_only_through_known_paths(tmp_path):
    """Every transduce-route action maps to an existing transducer row; every
    probe-route action maps to a perceivable event — no invented surfaces."""
    rows = set(CFG.transducer.rows)
    from inn.engine_surface import PERCEIVABLE_EVENTS
    for verb, e in ACTION_PALETTE.items():
        if e.route == "transduce":
            assert e.engine_action in rows, verb
        elif e.route == "probe":
            assert e.probe_type in PERCEIVABLE_EVENTS, verb


def test_replay_reproduces_interventions(tmp_path):
    h1 = run_session(CFG, "control", tmp_path / "a", seed=7, n_ticks=NT,
                     control=ControlState(SUBJECT, "manual"), interventions=INSULT)
    h2 = replay(tmp_path / "a" / "session.json", ROOT / "inn.yaml", tmp_path / "b")
    assert h2["trace_sha256"] == h1["trace_sha256"]
    auto = run_session(CFG, "control", tmp_path / "c", seed=7, n_ticks=NT)
    assert h1["trace_sha256"] != auto["trace_sha256"]


def test_make_intervention_unknown_verb_raises():
    try:
        make_intervention("teleport", "halgrim")
    except ValueError:
        return
    raise AssertionError("expected ValueError for an unknown palette verb")
