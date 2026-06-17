"""M-I live-frontier model (CLAUDE.md M-G/M-I).

The observer influences the world ONLY at the live frontier; the future emerges
from that new state. These pin the honest contracts:

  * incremental live-frontier driving == a batch run with the same (control,
    interventions) — byte-for-byte, so determinism / the golden are untouched;
  * target validation happens at EXECUTION time against the frontier (no
    telepathy, no future-queue);
  * the cockpit UI disables intervention away from the frontier, exposes no
    future scheduler, and never embeds an API key.

The behavioural rules are tested through inn.live.LiveSession (the SAME class the
Pyodide cockpit imports). The UI rules are asserted against the built cockpit
HTML (no browser is launched — Pyodide is tens of MB).
"""

import json
from pathlib import Path

import pytest

from inn import metrics as M
from inn.config import load_inn_config
from inn.engine_surface import believable_day_layout
from inn.intervention import ControlState
from inn.live import LiveSession
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")
DAY = believable_day_layout()["day_ticks"]

SUBJECT = "welf"
TARGET = "halgrim"
F = 200          # a daytime frontier where the subject has company
NT = 320


def _present_target(s: LiveSession) -> str:
    present = s.present_with()
    assert present, "expected the subject to have company at this frontier"
    return present[0]


# 1 — live-frontier driving is byte-identical to a batch run with the same
#     (control, interventions). The live UX is honest: no hidden recompute drift.
def test_live_frontier_equals_batch(tmp_path):
    run_session(CFG, "control", tmp_path, seed=7, n_ticks=NT,
                control=ControlState(SUBJECT, "manual"),
                interventions=[{"t": F, "subject": SUBJECT,
                                "verb": "insult", "target": TARGET}])
    batch = M.load_records(tmp_path / "trace.jsonl.gz")

    s = LiveSession(CFG, "game_semantic_profile", "control", 7, NT,
                    subject=SUBJECT, mode="manual")
    s.advance(F)
    assert s.frontier == F
    assert s.intervene("insult", TARGET, advance=NT) is None
    assert s.frontier == NT

    assert json.dumps(s.records, sort_keys=True) == json.dumps(batch, sort_keys=True)


# 2 — an intervention is applied at the CURRENT frontier tick, never a future
#     tick chosen ahead of time (no future-queue).
def test_intervention_fires_at_the_frontier(tmp_path):
    s = LiveSession(CFG, "game_semantic_profile", "control", 7, NT,
                    subject=SUBJECT, mode="manual")
    s.advance(F)
    assert s.intervene("insult", TARGET, advance=4) is None
    overrides = [r for r in s.records
                 if r.get("intervention", {}).get("selected_by") == "manual_override"]
    assert len(overrides) == 1
    assert overrides[0]["t"] == F           # fired AT the frontier, not later


# 3 — target validation happens at execution time against the live frontier;
#     a non-co-located target is rejected (no telepathy).
def test_target_validated_at_frontier_no_telepathy():
    s = LiveSession(CFG, "game_semantic_profile", "control", 7, 720,
                    subject=SUBJECT, mode="manual")
    s.advance(560)                          # a night frontier — sparse company
    present = s.present_with()
    absent = next(p for p in CFG.cast if p.id != SUBJECT and p.id not in present)
    err = s.validate("insult", absent.id)
    assert err is not None and "isn't with" in err
    # and the rejection blocks execution — no override recorded
    assert s.intervene("insult", absent.id, advance=0) == err
    assert not any(r.get("intervention", {}).get("selected_by") == "manual_override"
                   for r in s.records)


# 4 — self-targeting and target-less verbs are validated at the frontier too.
def test_self_and_targetless_validation():
    s = LiveSession(CFG, "game_semantic_profile", "control", 7, NT,
                    subject=SUBJECT, mode="manual")
    s.advance(F)
    assert "themselves" in s.validate("insult", SUBJECT)
    assert s.validate("observe", None) is None          # observe takes no target
    assert s.validate("observe", _present_target(s)) is not None  # rejects a target


# 5 — intervening before taking control, or past the end, is refused.
def test_intervene_requires_subject_and_unfinished_run():
    s = LiveSession(CFG, "game_semantic_profile", "control", 7, NT)
    s.advance(F)
    assert "Take control" in s.intervene("insult", TARGET)   # no subject
    s.take_control(SUBJECT, "manual")
    s.advance_all()
    assert s.at_end()
    assert "end" in s.intervene("insult", TARGET).lower()    # nothing left to run


# 6 — engine suggestion is read straight from the recorded autonomous selection,
#     never recomputed, and present at the frontier.
def test_engine_would_is_read_only():
    s = LiveSession(CFG, "game_semantic_profile", "control", 7, NT,
                    subject=SUBJECT, mode="auto")
    s.advance(F)
    eng = s.engine_would()
    assert eng == s.records[-1]["personas"][SUBJECT]["selection"]["action"]


# 7 — an autonomous live session (subject=None) is byte-identical to a plain run.
def test_autonomous_live_matches_plain_run(tmp_path):
    run_session(CFG, "control", tmp_path, seed=7, n_ticks=NT)
    plain = M.load_records(tmp_path / "trace.jsonl.gz")
    s = LiveSession(CFG, "game_semantic_profile", "control", 7, NT)
    s.advance_all()
    assert json.dumps(s.records, sort_keys=True) == json.dumps(plain, sort_keys=True)
    # …and carries no intervention records at all
    assert not any("intervention" in r for r in s.records)


# ---- UI contracts (asserted on the built cockpit HTML) ----------------------

@pytest.fixture(scope="module")
def cockpit_html():
    import observatory.build_bundle as B
    return B.build_index().read_text(encoding="utf-8")


# 8 — controls are disabled away from the frontier (history is read-only).
def test_cockpit_disables_controls_in_history(cockpit_html):
    assert "updateLiveControls" in cockpit_html
    assert "REVIEWING HISTORY — interventions disabled" in cockpit_html
    assert "LIVE FRONTIER — interventions enabled" in cockpit_html
    assert "atFrontier=frame>=(window.FRONTIER||0)" in cockpit_html
    assert ".disabled=!atFrontier" in cockpit_html


# 9 — the time picker is a read-only history scrubber, not a future scheduler.
def test_cockpit_has_no_future_scheduler(cockpit_html):
    assert "Re-run with queued" not in cockpit_html
    assert 'id="iv_tick"' not in cockpit_html        # the old future time-picker
    assert "Apply intervention" in cockpit_html      # live-frontier action only
    assert "Start live intervention" in cockpit_html # the interactive-mode entry


# 10 — the palette never presents rest/seek_activity as real commands, and the
#      honest no-ops are labelled as silence.
def test_cockpit_palette_is_honest(cockpit_html):
    assert "seek_activity" not in cockpit_html and ">rest<" not in cockpit_html
    assert "stay silent" in cockpit_html             # observe/noop labelled


# 11 — the LLM box is disabled in the browser, intentionally; the finite palette
#      stays usable and the message points to the CLI for natural language.
def test_cockpit_llm_disabled_in_browser(cockpit_html):
    assert "Browser cockpit uses safe action buttons" in cockpit_html
    assert "available in the CLI" in cockpit_html
    assert "no provider/key is available there" in cockpit_html


# 12 — no API key is embedded in the cockpit HTML (it is never built into the
#      page, the bundle, or the model).
def test_no_api_key_in_cockpit_html(tmp_path, monkeypatch):
    monkeypatch.setenv("EQUILIBRIUM_INN_LLM_PROVIDER", "openai")
    monkeypatch.setenv("EQUILIBRIUM_INN_LLM_API_KEY", "sk-SECRET-should-not-leak")
    import observatory.build_bundle as B
    html = B.build_index().read_text(encoding="utf-8")
    assert "sk-SECRET-should-not-leak" not in html
    assert "EQUILIBRIUM_INN_LLM_API_KEY" not in html


# 13 — the static export stays read-only: it embeds the live render layer but
#      none of the cockpit's live-driving Python API.
def test_static_export_is_read_only(tmp_path):
    import observatory.build_bundle as B  # noqa: F401 (ensures import parity)
    from inn import observatory as OB
    run_session(CFG, "control", tmp_path, seed=7, n_ticks=NT,
                control=ControlState(SUBJECT, "manual"),
                interventions=[{"t": F, "subject": SUBJECT,
                                "verb": "insult", "target": TARGET}])
    out = OB.export_html(tmp_path, tmp_path / "run.html", stride=2)
    html = out.read_text(encoding="utf-8")
    assert "renderInterventions" in html          # the read-only console renders
    assert "live_intervene" not in html           # but no live driver
    assert "loadPyodide" not in html              # and no in-browser sim


# 14 — frame-aware Why: the render layer keys off the current playhead.
def test_why_is_frame_aware(cockpit_html):
    assert "cur=MODEL.ticks[frame].t" in cockpit_html
    assert "most recent notable" in cockpit_html
