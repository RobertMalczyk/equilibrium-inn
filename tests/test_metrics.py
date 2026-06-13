from pathlib import Path

import pytest

from inn import metrics as M
from inn.config import load_inn_config
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")


@pytest.fixture(scope="module")
def impulse_records(tmp_path_factory):
    out = tmp_path_factory.mktemp("impulse")
    # one waking day is enough to contain the day-1 20:00 impulse? No — the
    # probe lands at day1 20:00; run through the first night.
    run_session(CFG, "impulse", out, n_ticks=717)
    return M.load_records(out / "trace.jsonl.gz")


def test_incidents_and_cascades(impulse_records):
    incs = M.incidents(impulse_records, ("outburst",))
    assert incs, "the impulse probe must produce at least one incident"
    cs = M.cascade_stats(incs)
    assert cs["n_cascades"] >= 1
    assert cs["max_depth"] >= 1
    # every incident is reachable from some root
    assert sum(c["size"] for c in cs["cascades"]) == cs["n_incidents"]


def test_envelopes_and_clamp_dwell(impulse_records):
    env = M.envelopes(impulse_records)
    assert set(env) == {c.id for c in CFG.cast}
    assert 0.0 <= env["halgrim"]["anger"]["max"] <= 1.0
    cd = M.clamp_dwell(impulse_records)
    assert all(0.0 <= v <= 1.0 for per in cd.values() for v in per.values())


def test_adherence_and_entropy(impulse_records):
    adh = M.routine_adherence(impulse_records)
    assert all(0.0 <= v <= 1.0 for v in adh.values())
    ent = M.action_entropy(impulse_records)
    assert all(v >= 0.0 for v in ent.values())


def test_fft(impulse_records):
    f = M.fft_dominant(impulse_records, dt=120.0)
    assert "anger" in f["halgrim"]
