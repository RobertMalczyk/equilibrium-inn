"""Behavioural validation tests (CLAUDE.md M-D §8): the trace must SHOW the
engine's living-world dynamics — boredom->seeking->activity->fatigue->rest/
sleep->recovery — and the reports must be derivable from a trace WITHOUT
rerunning the simulation. These assert direction, not tuned magnitudes (this
pass changes no dynamics). A failure here is a finding, not a reason to tune."""

import copy
from pathlib import Path

import pytest

from inn import metrics as M
from inn import observe as O
from inn.config import load_inn_config
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")
CAST = [c.id for c in CFG.cast]


@pytest.fixture(scope="module")
def records(tmp_path_factory):
    out = tmp_path_factory.mktemp("validation")
    run_session(CFG, "impulse", out)  # full 3 days -> two nights present
    return M.load_records(out / "trace.jsonl.gz")


def _mean_at(records, state, when):
    vals = [O.state_of(r, p, state) for r in records for p in CAST if when(r, p)]
    return sum(vals) / len(vals) if vals else None


def test_idle_raises_boredom_busy_lowers_it(records):
    idle = lambda r, p: O.mode_of(r, p) == "IDLE"
    busy = lambda r, p: O.action_of(r, p) in ("self_activity", "external")
    d_idle = O._mean_delta(records, "welf", "boredom", idle)
    d_busy = O._mean_delta(records, "welf", "boredom", busy)
    assert d_idle is not None and d_idle > 0, "boredom should rise while idle"
    if d_busy is not None:
        assert d_busy < d_idle, "engaged activity should relieve boredom vs idling"


def test_boredom_leads_to_seeking(records):
    r = O.report_boredom_activity(records, CAST)
    assert sum(p["seek_starts"] for p in r["per_persona"].values()) > 0


def test_activity_raises_fatigue(records):
    r = O.report_activity_fatigue(records, CAST)
    deltas = [p["fatigue_delta_busy"] for p in r["per_persona"].values()
              if p["fatigue_delta_busy"] is not None]
    assert deltas and sum(deltas) / len(deltas) > 0


def test_fatigue_precedes_rest(records):
    """Rest is chosen at above-average fatigue (fatigue -> rest tendency)."""
    rest = lambda r, p: O.action_of(r, p) == "rest"
    overall = lambda r, p: True
    f_rest = _mean_at(records, "fatigue", rest)
    f_all = _mean_at(records, "fatigue", overall)
    assert f_rest is not None, "no rest actions observed"
    assert f_rest >= f_all


def test_night_recovers_fast_states(records):
    r = O.report_rest_sleep_recovery(records, CAST)
    drops = [p["night_recovery"]["fatigue"] for p in r["per_persona"].values()
             if p["night_recovery"]["fatigue"] is not None]
    assert drops and sum(drops) / len(drops) < 0, "night should reduce fatigue"


def test_daily_summary_is_deterministic(records):
    a = {p: O.daily_summary(records, p, 1, ("outburst",)).to_dict() for p in CAST}
    b = {p: O.daily_summary(records, p, 1, ("outburst",)).to_dict() for p in CAST}
    assert a == b


def test_ambient_summary_does_not_mutate_state(records):
    span = records[200:240]
    before = copy.deepcopy(span)
    O.ambient_summary(span, O.high_thresholds(CFG), CAST)
    assert span == before


def test_reports_build_from_trace_without_rerun(records):
    """Every report builder consumes the already-loaded records — no session
    is run here (the canonical 'analysis reads only the trace' guarantee)."""
    from experiments import (report_activity_fatigue, report_boredom_activity,
                             report_persona_contrast, report_rest_sleep_recovery)
    assert report_boredom_activity.render(records)[0].startswith("# Boredom")
    assert report_activity_fatigue.render(records)[0].startswith("# Activity")
    assert report_rest_sleep_recovery.render(records)[0].startswith("# Rest")
    assert report_persona_contrast.render(records)[0].startswith("# Persona")
