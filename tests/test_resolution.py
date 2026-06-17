"""M-K — tick-resolution refinement (resolution_factor) + playback wiring.

resolution_factor refines dt: finer dt => more ticks for the same 3 game-days, the
real-time trajectory preserved (engine S2-S4). R=1.0 (default) is a guarded no-op =>
byte-identical to the canonical run (the golden, in test_determinism, is the binding
proof). The speed selector is playback-only (no trace effect).
"""

from pathlib import Path

from inn import metrics as M
from inn.config import load_inn_config
from inn.live import LiveSession
from inn.scenario import dump_scenario, replay_scenario
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")


# 1 — R=1.0 is byte-identical to the default (no resolution_factor passed).
def test_resolution_1_is_byte_identical(tmp_path):
    a = run_session(CFG, "impulse", tmp_path / "a", seed=7, n_ticks=300)
    b = run_session(CFG, "impulse", tmp_path / "b", seed=7, n_ticks=300,
                    resolution_factor=1.0)
    assert a["trace_sha256"] == b["trace_sha256"]
    assert a["resolution_factor"] == 1.0


# 2 — finer dt: more ticks for the same 3 days, dt shrinks ~ by R, recorded in header.
def test_finer_dt_scales_layout(tmp_path):
    base = run_session(CFG, "impulse", tmp_path / "r1", seed=7)         # full 3 days, R=1
    fine = run_session(CFG, "impulse", tmp_path / "r8", seed=7, resolution_factor=8.0)
    assert fine["resolution_factor"] == 8.0
    # dt ~ 8x smaller, day_ticks/n_ticks ~ 8x larger
    assert abs(base["layout"]["dt"] / fine["layout"]["dt"] - 8.0) < 0.05
    assert fine["layout"]["day_ticks"] > 7 * base["layout"]["day_ticks"]
    assert fine["n_ticks"] > 7 * base["n_ticks"]


# 3 — the real-time trajectory is preserved (convergent), not the per-tick trace:
#     a state at the SAME game-time (end of day 1) is close between R=1 and R=8.
def test_trajectory_preserved_over_game_time(tmp_path):
    d1 = tmp_path / "r1"; run_session(CFG, "impulse", d1, seed=7)
    d8 = tmp_path / "r8"; run_session(CFG, "impulse", d8, seed=7, resolution_factor=8.0)
    r1 = M.load_records(d1 / "trace.jsonl.gz")
    r8 = M.load_records(d8 / "trace.jsonl.gz")
    dt1 = r1[1]["t"]  # not used; clarity
    day1_t1 = next(i for i, rec in enumerate(r1) if rec["day"] == 2) - 1
    day1_t8 = next(i for i, rec in enumerate(r8) if rec["day"] == 2) - 1
    for st in ("boredom", "fatigue", "stress"):
        s1 = M.state_series(r1, (st,))["wojslaw"][st][day1_t1]
        s8 = M.state_series(r8, (st,))["wojslaw"][st][day1_t8]
        assert abs(s1 - s8) < 0.05, f"{st}: R1={s1} R8={s8} diverged"


# 4 — resolution_factor round-trips through the scenario dump + reproduces.
def test_resolution_in_scenario(tmp_path):
    run = run_session(CFG, "impulse", tmp_path / "run", seed=7, n_ticks=600,
                      resolution_factor=8.0)
    sc = dump_scenario(CFG, seed=7, probe_plan="impulse", n_ticks=600, resolution_factor=8.0)
    assert sc["resolution_factor"] == 8.0
    rep = replay_scenario(sc, tmp_path / "rep")
    assert rep["trace_sha256"] == run["trace_sha256"]


# 5 — LiveSession derives its total ticks from the refined clock (more ticks at R>1).
def test_livesession_total_scales_with_resolution():
    s1 = LiveSession(CFG, "game_semantic_profile", "control", 7)
    s8 = LiveSession(CFG, "game_semantic_profile", "control", 7, resolution_factor=8.0)
    assert s8.total > 7 * s1.total
    assert abs(s1.loop.clock.dt / s8.loop.clock.dt - 8.0) < 0.05


# 6 — the cockpit wires the resolution + speed selectors and a real-time playback loop.
def test_cockpit_wires_resolution_and_speed():
    import observatory.build_bundle as B
    from inn import observatory as OB
    html = B.build_index().read_text(encoding="utf-8")
    assert "c_res" in html and "resVal" in html         # resolution selector
    assert "c_speed" in html and "speedVal" in html      # speed selector
    assert "resolution_factor" in html                   # threaded into live_start
    assert "PLAY_DT" in html and "PLAY_SPEED" in html     # real-time playback inputs
    assert "_playFrame" in OB.SCRIPT                      # speed-aware playback loop
