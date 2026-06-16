"""M-I — Observatory UI integration of M-G/M-H.

The UI consumes the model's intervention fields; it never recomputes engine
behaviour. These lock in that the model exposes the intervention state the UI
binds to, that a controlled run carries manual_override provenance into the model
and the static export, and that the cockpit page (with the live console) still
builds. No browser is launched (Pyodide is tens of MB); the cockpit JS is
syntax-checked separately and the browser path is a documented checklist.
"""

import os
from pathlib import Path

from inn import metrics as M
from inn import observatory as OB
from inn import observe as O
from inn.config import load_inn_config
from inn.intervention import ACTION_PALETTE, ControlState
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")

SUBJECT = "welf"
TARGET = "halgrim"
TICK = 200
NT = 320
INSULT = [{"t": TICK, "subject": SUBJECT, "verb": "insult", "target": TARGET}]


def _auto_model(tmp_path):
    run_session(CFG, "control", tmp_path, seed=7, n_ticks=NT)
    return O.build_model(M.load_records(tmp_path / "trace.jsonl.gz"), CFG)


def _manual(tmp_path, script=INSULT):
    run_session(CFG, "control", tmp_path, seed=7, n_ticks=NT,
                control=ControlState(SUBJECT, "manual"), interventions=script)
    return M.load_records(tmp_path / "trace.jsonl.gz")


# 1 — the model always exposes the intervention UI descriptor (palette + llm flag).
def test_model_exposes_intervention_ui(tmp_path):
    m = _auto_model(tmp_path)
    ui = m["intervention_ui"]
    verbs = {p["verb"] for p in ui["palette"]}
    assert verbs == set(ACTION_PALETTE)            # valid_actions = the palette
    assert "rest" not in verbs and "seek_activity" not in verbs
    assert ui["controlled_subjects"] == []          # autonomous run
    assert ui["summary"] is None
    assert "interventions" not in m                 # none present -> key omitted


# 2 + 3 — a controlled run carries manual_override provenance + engine suggestion
#         into the model the UI renders.
def test_model_carries_override_provenance(tmp_path):
    recs = _manual(tmp_path)
    m = O.build_model(recs, CFG)
    assert m["intervention_ui"]["controlled_subjects"] == [SUBJECT]
    ovr = [x for x in m["interventions"] if x["selected_by"] == "manual_override"]
    assert ovr and ovr[0]["user_selected_action"] == "insult"
    assert ovr[0]["target"] == TARGET
    # engine suggestion is read straight from the recorded autonomous selection,
    # never recomputed: personas[subject].action at the override tick.
    tick_rec = next(t for t in m["ticks"] if t["t"] == TICK)
    assert ovr[0]["engine_would_have_selected"] == tick_rec["personas"][SUBJECT]["action"]


# 4 — engine suggestion present per-tick for the controlled subject.
def test_engine_suggestion_available(tmp_path):
    m = O.build_model(_manual(tmp_path), CFG)
    sub = m["intervention_ui"]["controlled_subjects"][0]
    assert all("action" in t["personas"][sub] for t in m["ticks"])


# 5 — LLM disabled state appears when no provider/key is configured.
def test_llm_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("EQUILIBRIUM_INN_LLM_PROVIDER", raising=False)
    m = _auto_model(tmp_path)
    assert m["intervention_ui"]["llm_enabled"] is False


def test_llm_enabled_flag_follows_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EQUILIBRIUM_INN_LLM_PROVIDER", "openai")
    m = _auto_model(tmp_path)
    assert m["intervention_ui"]["llm_enabled"] is True


# 6 — summary counts are exposed for the UI report section.
def test_intervention_summary_counts(tmp_path):
    m = O.build_model(_manual(tmp_path), CFG)
    sm = m["intervention_ui"]["summary"]
    assert sm["n_overrides"] == 1 and sm["by_action"] == {"insult": 1}
    assert sm["targets"] == {TARGET: 1}


# 7 — the static export renders an intervention trace (panel + data embedded).
def test_static_export_renders_interventions(tmp_path):
    _manual(tmp_path)
    out = OB.export_html(tmp_path, tmp_path / "run.html", stride=2)
    html = out.read_text(encoding="utf-8")
    assert 'id="intvpanel"' in html
    assert '"intervention_ui"' in html and '"interventions"' in html
    assert "renderInterventions" in html and "Engine suggestion" in html


# 8 — the cockpit page (with the live intervention console) still builds.
def test_cockpit_index_builds():
    import observatory.build_bundle as B
    p = B.build_index()
    html = p.read_text(encoding="utf-8")
    assert "buildIntvConsole" in html and "run_live_controlled" in html
    assert "iv_presentWith" in html  # valid-target filtering present


# 9 — valid-target data is available to the UI (presence per tick in the model).
def test_valid_targets_derivable_from_model(tmp_path):
    m = O.build_model(_manual(tmp_path), CFG)
    tick_rec = next(t for t in m["ticks"] if t["t"] == TICK)
    room = tick_rec["personas"][SUBJECT]["room"]
    present = [p for p in m["cast"]
               if p != SUBJECT and tick_rec["personas"][p]["room"] == room]
    assert TARGET in present  # the UI can offer only present targets


# 10 — autonomous model is unaffected aside from the additive UI descriptor.
def test_autonomous_model_has_no_overrides(tmp_path):
    m = _auto_model(tmp_path)
    assert "interventions" not in m
    assert m["intervention_ui"]["summary"] is None
