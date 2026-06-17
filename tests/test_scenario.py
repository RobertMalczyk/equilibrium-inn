"""M-J — lossless scenario dump + replay, and the burst_overlay toggle.

A scenario stores INPUTS ONLY (no simulation results) and embeds the exact inn.yaml
so it reproduces a run bit-for-bit later, even if the repo's inn.yaml has moved on.
The burst overlay is an opt-in behaviour toggle (ships OFF — the default run is
unchanged, so the golden is safe).
"""

from pathlib import Path

import pytest

from inn.config import load_inn_config
from inn.intervention import ControlState
from inn.scenario import dump_scenario, replay_scenario
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")
NT = 300


# 1 — a dump is INPUT-ONLY: it embeds inn.yaml + params and carries no results.
def test_dump_is_input_only():
    sc = dump_scenario(CFG, seed=7, probe_plan="impulse", n_ticks=NT)
    assert sc["inn_yaml"] and sc["inn_yaml_sha256"] == CFG.yaml_sha256
    assert sc["engine_commit"] and sc["calibration_hashes"]
    # no simulation results may leak into a scenario
    assert "trace_sha256" not in sc and "trace" not in sc and "personas" not in sc
    assert "burst_overlay" in sc and "injected_events" in sc


# 2 — replay reproduces the identical trace SHA of an equivalent run_session.
def test_replay_reproduces(tmp_path):
    base = run_session(CFG, "impulse", tmp_path / "base", seed=7, n_ticks=NT)
    sc = dump_scenario(CFG, seed=7, probe_plan="impulse", n_ticks=NT)
    header = replay_scenario(sc, tmp_path / "rep")
    assert header["trace_sha256"] == base["trace_sha256"]


# 3 — replay reproduces a controlled run with manual overrides, too.
def test_replay_reproduces_with_overrides(tmp_path):
    iv = [{"t": 200, "subject": "welf", "verb": "insult", "target": "halgrim"}]
    base = run_session(CFG, "control", tmp_path / "base", seed=7, n_ticks=NT,
                       control=ControlState("welf", "manual"), interventions=iv)
    sc = dump_scenario(CFG, seed=7, probe_plan="control", n_ticks=NT,
                       control=ControlState("welf", "manual"), injected_events=iv)
    header = replay_scenario(sc, tmp_path / "rep")
    assert header["trace_sha256"] == base["trace_sha256"]


# 4 — replay refuses a corrupted embedded inn.yaml (loud, never silent).
def test_replay_rejects_corrupt_yaml(tmp_path):
    sc = dump_scenario(CFG, seed=7, probe_plan="impulse", n_ticks=NT)
    sc["inn_yaml"] += "\n# tampered\n"
    with pytest.raises(ValueError):
        replay_scenario(sc, tmp_path / "rep")


# 5 — burst_overlay: OFF (the default) is byte-identical to no override (golden-safe);
#     ON actually changes the run; both choices round-trip through a scenario.
def test_burst_overlay_toggle(tmp_path):
    base = run_session(CFG, "impulse", tmp_path / "b", seed=7, n_ticks=NT)
    off = run_session(CFG, "impulse", tmp_path / "off", seed=7, n_ticks=NT,
                      burst_overlay=False)
    on = run_session(CFG, "impulse", tmp_path / "on", seed=7, n_ticks=NT,
                     burst_overlay=True)
    assert off["trace_sha256"] == base["trace_sha256"]      # default == OFF
    assert on["trace_sha256"] != off["trace_sha256"]        # ON changes dynamics
    assert base["burst_overlay"] is False and on["burst_overlay"] is True
    # the ON run reproduces from its scenario
    sc = dump_scenario(CFG, seed=7, probe_plan="impulse", n_ticks=NT, burst_overlay=True)
    assert sc["burst_overlay"] is True
    rep = replay_scenario(sc, tmp_path / "rep")
    assert rep["trace_sha256"] == on["trace_sha256"]


# 6 — the cockpit exposes the dump (button + Python bridge) and the burst toggle.
def test_cockpit_wires_dump_and_burst():
    import observatory.build_bundle as B
    html = B.build_index().read_text(encoding="utf-8")
    assert "iv_dump" in html and "dumpScenario" in html and "scenario_json" in html
    assert "c_burst" in html and "burstVal" in html
    assert "dump_scenario" in html          # LiveSession.dump_scenario bridged in boot
