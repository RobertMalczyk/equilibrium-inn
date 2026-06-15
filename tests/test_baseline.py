"""Baseline cast (CLAUDE.md M-E): a fair control that reuses the world layer with
an automaton+bark brain. It must emit the SAME trace schema as the engine so every
metric/observation reads it, be deterministic, and behave like a dumb baseline
(rigid schedule, single triggered barks — no priming cascades)."""

from pathlib import Path

import pytest

from inn import metrics as M
from inn import observe as O
from inn.baseline import run_baseline
from inn.config import load_inn_config
from inn.engine_surface import GLOBAL_STATES

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")


@pytest.fixture(scope="module")
def base_records(tmp_path_factory):
    out = tmp_path_factory.mktemp("baseline")
    run_baseline(CFG, "impulse", out, n_ticks=717)
    return M.load_records(out / "trace.jsonl.gz")


def test_baseline_config_block_present():
    assert CFG.baseline["bark_threshold"] == 0.45


def test_baseline_emits_engine_compatible_schema(base_records):
    rec = base_records[300]
    for pid in (c.id for c in CFG.cast):
        tt = rec["personas"][pid]
        assert tt["state_after_post"]["mode"] in O.MODE_LABEL
        assert set(GLOBAL_STATES) <= set(tt["state_after_post"]["global"])
        assert "action" in tt["selection"]
    for key in ("t", "day", "clock", "night", "presence", "transductions",
                "offers", "contention_losers"):
        assert key in rec


def test_metrics_and_observe_read_baseline(base_records):
    incs = M.incidents(base_records, ("outburst",))
    assert incs, "the impulse insult should trigger at least one bark"
    model = O.build_model(base_records, CFG, stride=4)
    assert model["cast"] == [c.id for c in CFG.cast]
    assert "metrics" in model and model["inputs"], "marta insult is an input"


def test_baseline_is_a_flat_control(base_records):
    """The dumb baseline barks but does not prime a propagating cascade: every
    incident is a root (no reaction-to-reaction depth) — the engine's contrast."""
    incs = M.incidents(base_records, ("outburst",))
    cs = M.cascade_stats(incs)
    assert cs["max_depth"] <= 1


def test_baseline_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    ha = run_baseline(CFG, "impulse", a, n_ticks=717)
    hb = run_baseline(CFG, "impulse", b, n_ticks=717)
    assert ha["trace_sha256"] == hb["trace_sha256"]


def test_baseline_sleeps_and_works(base_records):
    from collections import Counter
    modes = Counter(O.mode_of(r, "halgrim") for r in base_records)
    assert modes["SLEEP"] > 0 and modes["BUSY"] > 0
