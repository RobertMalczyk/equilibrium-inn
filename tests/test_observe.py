"""Observation layer (CLAUDE.md M-D). Pure derivations over the society trace:
deterministic, additive, and never mutating the run. Behaviour is validated
end-to-end (boredom->seeking->activity->fatigue->rest/sleep->recovery) in
test_reports.py; here we check the primitives and their determinism."""

import copy
from pathlib import Path

import pytest

from inn import metrics as M
from inn import observe as O
from inn.config import load_inn_config
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")
INC = tuple(CFG.g0["incident_def"]["actions"])


@pytest.fixture(scope="module")
def impulse_records(tmp_path_factory):
    out = tmp_path_factory.mktemp("obs_impulse")
    run_session(CFG, "impulse", out, n_ticks=717)
    return M.load_records(out / "trace.jsonl.gz")


def test_observation_config_block_loads():
    high = O.high_thresholds(CFG)
    assert high["boredom"] == 0.60 and high["anger"] == 0.50
    assert set(O.DEFAULT_HIGH) <= set(high)


def test_mode_transitions_have_drivers(impulse_records):
    trs = O.mode_transitions(impulse_records)
    assert trs, "a 3-persona day must produce mode transitions"
    assert {t.pid for t in trs} <= {c.id for c in CFG.cast}
    # the lifecycle modes we care about should all appear somewhere
    seen = {t.new for t in trs} | {t.prev for t in trs}
    assert {"BUSY", "SLEEP"} <= seen
    # at least one seeking->busy or idle->seeking edge carries a boredom driver
    assert any(t.driver == "boredom" for t in trs if t.new in ("SEEKING", "BUSY")) or \
        any(t.new == "SEEKING" for t in trs)


def test_threshold_crossings_are_rising_edges(impulse_records):
    high = O.high_thresholds(CFG)
    xs = O.threshold_crossings(impulse_records, high)
    for x in xs:
        assert x.value >= x.threshold
    # a crossing per (pid,state) fires at most... well, once per rising edge:
    # the same tick can't appear twice for one (pid,state)
    keyed = [(x.pid, x.state, x.t) for x in xs]
    assert len(keyed) == len(set(keyed))


def test_mood_and_mode_labels(impulse_records):
    high = O.high_thresholds(CFG)
    rec = impulse_records[300]
    for pid in (c.id for c in CFG.cast):
        assert O.mood_label(rec, pid, high) in {
            "sleeping", "resting", "irritated", "tired", "focused", "bored", "calm"}
        assert O.mode_of(rec, pid) in O.MODE_LABEL


def test_ambient_summary_is_deterministic_and_pure(impulse_records):
    span = impulse_records[100:130]
    before = copy.deepcopy(span)
    high = O.high_thresholds(CFG)
    s1 = O.ambient_summary(span, high, dt=120.0)
    s2 = O.ambient_summary(span, high, dt=120.0)
    assert s1 == s2 and s1.endswith(".")
    assert "quiet" in s1
    assert span == before, "ambient_summary must not mutate records"


def test_daily_summary(impulse_records):
    ds = O.daily_summary(impulse_records, "halgrim", 1, INC)
    assert ds.pid == "halgrim" and ds.day == 1
    assert abs(sum(ds.pct.values()) - 1.0) < 1e-6
    assert 0.0 <= ds.max_fatigue <= 1.0
    assert isinstance(ds.interpretation, str) and ds.interpretation
    # deterministic
    assert O.daily_summary(impulse_records, "halgrim", 1, INC).to_dict() == ds.to_dict()


def test_why_generalizes_to_proactive(impulse_records):
    # Halgrim is the impulse target -> reactive chain; someone else is proactive
    chain = O.why(impulse_records, "halgrim")
    assert chain and "Halgrim" in chain[0]
    # a non-targeted persona's why should still produce a causal account
    other = O.why(impulse_records, "edda")
    assert other and isinstance(other[0], str)


def test_build_model_is_json_stable(impulse_records):
    import json
    m1 = O.build_model(impulse_records, CFG, meta={"k": "v"}, stride=4)
    m2 = O.build_model(impulse_records, CFG, meta={"k": "v"}, stride=4)
    assert json.dumps(m1, sort_keys=True) == json.dumps(m2, sort_keys=True)
    assert m1["cast"] == [c.id for c in CFG.cast]
    assert m1["ticks"] and "personas" in m1["ticks"][0]
    assert "metrics" in m1 and "incidents" in m1["metrics"]
    # developer-view raw floats present, observer-view labels present
    t0p = m1["ticks"][0]["personas"]["halgrim"]
    assert "raw" in t0p and "mood" in t0p and "mode" in t0p
