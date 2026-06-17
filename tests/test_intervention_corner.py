"""Corner-case / scenario tests for M-G/M-H/M-I — the adversarial boundaries a
reviewer would poke at before merge:

  * telepathy / self / target-less validation,
  * switching the controlled subject mid-run,
  * two manual acts queued on one tick (last wins),
  * overrides on the first and last ticks,
  * every palette route emitting its expected world event,
  * AUTO-only vs manual-noop-only runs in the UI model,
  * reaction attribution + mixed-route replay determinism,
  * LLM mapping corners (fenced JSON, non-object, missing/OOR fields, threshold,
    confirm-with-nothing, say-without-subject).

Deterministic: fixed seed + the calm `control` plan. No real LLM calls (fakes).
"""

import json
from pathlib import Path

import pytest

from inn import metrics as M
from inn import observe as O
from inn import llm_seam
from inn.cli import CliSession
from inn.config import load_inn_config
from inn.intervention import ACTION_PALETTE, ControlState, validate_target
from inn.session import replay, run_session

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")
CAST = [c.id for c in CFG.cast]

SUBJECT = "welf"
TARGET = "halgrim"        # co-located with welf in the yard at mid-day
ELSEWHERE = "cichy"       # NOT in welf's room at TICK (verified)
TICK = 200
NT = 240


def _controlled(tmp, script, mode="manual"):
    run_session(CFG, "control", tmp, seed=7, n_ticks=NT,
                control=ControlState(SUBJECT, mode), interventions=script)
    return M.load_records(tmp / "trace.jsonl.gz")


def _auto(tmp):
    run_session(CFG, "control", tmp, seed=7, n_ticks=NT)
    return M.load_records(tmp / "trace.jsonl.gz")


def _cli_at(tmp, t=TICK):
    s = CliSession(CFG, seed=7, out_dir=tmp)
    s.do(f"wait {t}")
    return s


# --- validation corners ------------------------------------------------------

def test_cross_room_target_rejected_no_telepathy(tmp_path):
    s = _cli_at(tmp_path)
    s.do("control welf"); s.do("manual")
    assert ELSEWHERE not in s._present_to(SUBJECT)
    out = s.do(f"act insult {ELSEWHERE}")
    assert "isn't with" in out[0]
    # nothing was queued / executed
    assert not s.interventions
    assert validate_target(CFG, s.loop.presence, SUBJECT, "insult", ELSEWHERE)


def test_self_target_rejected(tmp_path):
    s = _cli_at(tmp_path)
    s.do("control welf"); s.do("manual")
    assert validate_target(CFG, s.loop.presence, SUBJECT, "insult", SUBJECT)
    out = s.do("act insult welf")
    assert "can't insult" in out[0].lower() or "isn't with" in out[0]


def test_targetless_and_required_target_rules(tmp_path):
    s = _cli_at(tmp_path)
    # observe/noop take no target; insult requires one
    assert validate_target(CFG, s.loop.presence, SUBJECT, "observe", TARGET)  # error
    assert validate_target(CFG, s.loop.presence, SUBJECT, "observe", None) is None
    assert validate_target(CFG, s.loop.presence, SUBJECT, "insult", None)     # error
    assert validate_target(CFG, s.loop.presence, SUBJECT, "nonsense", TARGET) # unknown


# --- control lifecycle corners ----------------------------------------------

def test_switch_controlled_subject_midrun(tmp_path):
    s = _cli_at(tmp_path)
    s.do("control welf"); s.do("manual")
    s.do(f"act insult {TARGET}")
    assert s.control.subject == "welf"
    s.do("release")
    assert s.control.subject is None
    s.do("control halgrim")
    assert s.control.subject == "halgrim" and s.control.mode == "auto"
    # the earlier override is still in the record under the first subject
    assert any(r.get("intervention", {}).get("subject") == "welf"
               and r["intervention"]["selected_by"] == "manual_override"
               for r in s.records)


def test_two_acts_same_tick_last_wins(tmp_path):
    # both queued for TICK; one manual action per tick -> the later overwrites.
    recs = _controlled(tmp_path, [
        {"t": TICK, "subject": SUBJECT, "verb": "command", "target": TARGET},
        {"t": TICK, "subject": SUBJECT, "verb": "insult", "target": TARGET}])
    iv = recs[TICK]["intervention"]
    assert iv["selected_by"] == "manual_override"
    assert iv["user_selected_action"] == "insult" and iv["route"] == "transduce"
    # the discarded command-probe never fired
    assert not [p for p in recs[TICK].get("probes", [])
                if p["probe"].split(":")[1] == SUBJECT
                and p["probe"].split(":")[2] == "command"]


def test_override_on_first_and_last_tick(tmp_path):
    recs = _controlled(tmp_path, [
        {"t": 0, "subject": SUBJECT, "verb": "insult", "target": TARGET},
        {"t": NT - 1, "subject": SUBJECT, "verb": "insult", "target": TARGET}])
    assert recs[0]["intervention"]["selected_by"] == "manual_override"
    assert recs[NT - 1]["intervention"]["selected_by"] == "manual_override"


# --- routing coverage --------------------------------------------------------

TRANSDUCE_EXPECT = {"insult": "insult", "help": "help", "praise": "help",
                    "complain": "complaint", "refuse": "refusal",
                    "cold": "cold_reply", "cold_reply": "cold_reply"}


@pytest.mark.parametrize("verb,as_event", list(TRANSDUCE_EXPECT.items()))
def test_transduce_route_emits_mapped_event(tmp_path, verb, as_event):
    recs = _controlled(tmp_path, [{"t": TICK, "subject": SUBJECT,
                                   "verb": verb, "target": TARGET}])
    fired = [tr for r in recs for tr in r.get("transductions", [])
             if tr["actor"] == SUBJECT and tr["as"] == as_event
             and tr["target_inferred"] == TARGET]
    assert fired, f"{verb} should transduce to a {as_event} event"


@pytest.mark.parametrize("verb,etype", [("command", "command"), ("serve", "food_given")])
def test_probe_route_emits_perceivable_event(tmp_path, verb, etype):
    recs = _controlled(tmp_path, [{"t": TICK, "subject": SUBJECT,
                                   "verb": verb, "target": TARGET}])
    probes = [p["probe"] for r in recs for p in r.get("probes", [])
              if p["probe"].split(":")[1] == SUBJECT
              and p["probe"].split(":")[2] == etype]
    assert probes and recs[TICK]["intervention"]["route"] == "probe"


def test_reaction_attributed_to_subject(tmp_path):
    recs = _controlled(tmp_path, [{"t": TICK, "subject": SUBJECT,
                                   "verb": "insult", "target": TARGET}])
    reaction = [r["t"] for r in recs for tr in r.get("transductions", [])
                if tr["actor"] == TARGET and tr.get("target_inferred") == SUBJECT
                and r["t"] > TICK]
    assert reaction, "target should react, attributed back to the subject"


# --- UI-model corners --------------------------------------------------------

def test_auto_only_controlled_run_leaves_no_overrides_in_model(tmp_path):
    recs = _controlled(tmp_path, [], mode="auto")
    m = O.build_model(recs, CFG)
    # every tick is engine-selected -> nothing for the override log to show
    assert "interventions" not in m
    assert m["intervention_ui"]["controlled_subjects"] == []
    assert m["intervention_ui"]["summary"] is None


def test_manual_noop_only_shows_subject_zero_overrides(tmp_path):
    recs = _controlled(tmp_path, [], mode="manual")   # controlled but never acts
    m = O.build_model(recs, CFG)
    assert "interventions" in m  # manual_noop entries are recorded
    assert m["intervention_ui"]["controlled_subjects"] == [SUBJECT]
    assert m["intervention_ui"]["summary"]["n_overrides"] == 0


# --- replay determinism with mixed routes -----------------------------------

def test_replay_mixed_routes_deterministic(tmp_path):
    script = [{"t": 200, "subject": SUBJECT, "verb": "command", "target": TARGET},
              {"t": 205, "subject": SUBJECT, "verb": "insult", "target": TARGET},
              {"t": 210, "subject": SUBJECT, "verb": "serve", "target": TARGET}]
    h1 = run_session(CFG, "control", tmp_path / "a", seed=7, n_ticks=NT,
                     control=ControlState(SUBJECT, "manual"), interventions=script)
    h2 = replay(tmp_path / "a" / "session.json", ROOT / "inn.yaml", tmp_path / "b")
    assert h1["trace_sha256"] == h2["trace_sha256"]
    auto = run_session(CFG, "control", tmp_path / "c", seed=7, n_ticks=NT)
    assert h1["trace_sha256"] != auto["trace_sha256"]


# --- LLM mapping corners (fake client; never a real call) -------------------

class _Fake:
    def __init__(self, payload): self.payload = payload
    def complete(self, system, user): return self.payload


def _presence(tmp_path):
    s = _cli_at(tmp_path)
    return s.loop.presence


def _cand(**over):
    d = {"action": "command", "target": TARGET, "intensity": 0.4,
         "public": True, "confidence": 0.82, "rationale": "x"}
    d.update(over)
    return json.dumps(d)


def test_llm_fenced_json_is_accepted(tmp_path):
    pres = _presence(tmp_path)
    fenced = "```json\n" + _cand() + "\n```"
    r = llm_seam.map_text("order it", cfg=CFG, presence=pres, subject=SUBJECT,
                          client=_Fake(fenced))
    assert r.ok and r.candidate.action == "command"


def test_llm_non_object_rejected(tmp_path):
    r = llm_seam.map_text("x", cfg=CFG, presence=_presence(tmp_path), subject=SUBJECT,
                          client=_Fake("[1,2,3]"))
    assert r.ok is False


def test_llm_missing_action_rejected(tmp_path):
    r = llm_seam.map_text("x", cfg=CFG, presence=_presence(tmp_path), subject=SUBJECT,
                          client=_Fake("{}"))
    assert r.ok is False


def test_llm_intensity_out_of_range_rejected(tmp_path):
    r = llm_seam.map_text("x", cfg=CFG, presence=_presence(tmp_path), subject=SUBJECT,
                          client=_Fake(_cand(action="insult", intensity=5)))
    assert r.ok is False and "intensity" in r.message


def test_llm_confidence_threshold_enforced(tmp_path):
    r = llm_seam.map_text("x", cfg=CFG, presence=_presence(tmp_path), subject=SUBJECT,
                          client=_Fake(_cand(confidence=0.3)), confidence_threshold=0.9)
    assert r.ok is False and "confidence" in r.message


def test_confirm_without_pending(tmp_path):
    s = _cli_at(tmp_path)
    assert "nothing to confirm" in s.do("confirm")[0].lower()


def test_say_without_subject(tmp_path, monkeypatch):
    monkeypatch.setenv("EQUILIBRIUM_INN_LLM_PROVIDER", "openai")
    s = CliSession(CFG, seed=7, out_dir=tmp_path)   # no subject controlled
    out = s.do('say "tell halgrim to rest"')
    assert "control a subject" in out[0].lower()
