"""M-I pre-merge polish: observer-facing wording, suggest-before-first-tick, the
`report interventions` CLI view, clock/quiet consistency, and the build-script
import path. Display/UX only — no dynamics."""

from pathlib import Path

import pytest

from inn import metrics as M
from inn import observe as O
from inn.chronicle import event_line, manual_action_line, observer_action_label
from inn.cli import CliSession
from inn.config import load_inn_config
from inn.intervention import ControlState
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")
SUBJECT, TARGET, TICK, NT = "welf", "halgrim", 200, 220


def _controlled(tmp, verb):
    run_session(CFG, "control", tmp, seed=7, n_ticks=NT,
                control=ControlState(SUBJECT, "manual"),
                interventions=[{"t": TICK, "subject": SUBJECT, "verb": verb,
                                "target": TARGET}])
    return M.load_records(tmp / "trace.jsonl.gz")


# 1 — manual action prose is clear and declarative (not the engine reaction tier).
def test_manual_action_prose_lines():
    assert manual_action_line("praise", "welf", "halgrim") == "Welf praises Halgrim warmly"
    assert manual_action_line("help", "welf", "halgrim") == "Welf helps Halgrim"
    assert manual_action_line("insult", "welf", "halgrim") == "Welf insults Halgrim"
    assert manual_action_line("command", "welf", "halgrim") == "Welf gives Halgrim a firm command"
    assert manual_action_line("complain", "welf", "halgrim") == "Welf complains to Halgrim"
    assert manual_action_line("refuse", "welf", "halgrim") == "Welf refuses Halgrim"
    assert manual_action_line("cold", "welf", "halgrim") == "Welf answers Halgrim coldly"
    assert manual_action_line("serve", "welf", "halgrim") == "Welf serves Halgrim"


def test_manual_praise_beat_is_not_garbled(tmp_path):
    recs = _controlled(tmp_path, "praise")
    line = event_line(recs[TICK])
    assert line == "(your intervention) Welf praises Halgrim warmly"
    # the broken engine-reaction phrasing must not appear for a manual praise
    assert "thanks them gladly" not in line and "visibly warmed" not in line


def test_manual_insult_beat_is_clean(tmp_path):
    assert event_line(_controlled(tmp_path, "insult")[TICK]) == \
        "(your intervention) Welf insults Halgrim"


# 2 — Observer View avoids the bare word "idle" (engine mode stays IDLE).
def test_observer_mode_relabels_idle():
    assert O.observer_mode("idle") == "unoccupied"
    assert O.observer_mode("busy") == "busy" and O.observer_mode("sleep") == "sleep"
    assert O.MODE_LABEL["IDLE"] == "idle"  # raw label (Developer view) unchanged


def test_ambient_summary_says_unoccupied_not_idles(tmp_path):
    run_session(CFG, "control", tmp_path, seed=7, n_ticks=40)
    recs = M.load_records(tmp_path / "trace.jsonl.gz")
    text = O.ambient_summary(recs[:20], O.high_thresholds(CFG),
                             [c.id for c in CFG.cast])
    assert "idles" not in text
    assert "unoccupied" in text


def test_cli_observe_card_uses_unoccupied(tmp_path):
    s = CliSession(CFG, seed=7, out_dir=tmp_path)
    s.do("wait 10")
    card = "\n".join(s.do("observe all"))
    # at least one persona is unoccupied early on; the word "idle" never shows
    assert "unoccupied" in card


# 3 — suggest before the first tick gives guidance, not "?".
def test_suggest_before_first_tick(tmp_path):
    s = CliSession(CFG, seed=7, out_dir=tmp_path)
    s.do("control welf")
    out = "\n".join(s.do("suggest")).lower()
    assert "?" not in out
    assert "no engine suggestion yet" in out


# 4 — manual silence reads as silence, not "noop".
def test_noop_reads_as_manual_silence():
    assert observer_action_label("noop") == "manual silence (no outward action)"
    assert observer_action_label("observe") == "manual silence (no outward action)"
    assert observer_action_label("insult") == "insult"


def test_why_noop_says_silence(tmp_path):
    s = CliSession(CFG, seed=7, out_dir=tmp_path)
    s.do("wait 200"); s.do("control welf"); s.do("manual"); s.do("act observe")
    out = "\n".join(s.do("why welf")).lower()
    assert "manual silence" in out and "you chose: noop" not in out


# 5 — the footer clock advances with the quiet summary.
def test_clock_advances_after_wait(tmp_path):
    s = CliSession(CFG, seed=7, out_dir=tmp_path)
    before = s._now()
    s.do("wait 1")
    assert s._now() != before  # 2 minutes (one tick) elapsed, footer reflects it


# 6 — `report intervention(s)` summarises overrides.
def test_report_interventions(tmp_path):
    s = CliSession(CFG, seed=7, out_dir=tmp_path)
    s.do("wait 200"); s.do("control welf"); s.do("manual")
    s.do(f"act insult {TARGET}")
    for verb in ("report intervention", "report interventions"):
        out = "\n".join(s.do(verb)).lower()
        assert "manual override" in out
        assert "by action" in out and "insult" in out
        assert "engine would have" in out


def test_report_interventions_when_none(tmp_path):
    s = CliSession(CFG, seed=7, out_dir=tmp_path)
    s.do("wait 50")
    assert "none" in "\n".join(s.do("report interventions")).lower()


# 7 — build_bundle.py puts the repo root on sys.path BEFORE importing inn.*,
#     so it runs from the repo root with no PYTHONPATH / editable install.
def test_build_bundle_syspath_precedes_inn_import():
    src = (ROOT / "observatory" / "build_bundle.py").read_text(encoding="utf-8")
    assert src.index("sys.path.insert") < src.index("import inn.observatory")
