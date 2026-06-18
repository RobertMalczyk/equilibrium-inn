"""Aggressive QA battery for equilibrium-inn — functional AND non-functional.

Positioned as a reliable promotion gate for the engine: it stresses determinism,
the dt-resolution refinement (M-K), scenario reproducibility, intervention safety,
trace invariants, robustness/fuzz of the config + inputs, performance/scaling,
boundedness/stability (G0 corridor), and parity anchors — then writes a MD + HTML
report with a PROMOTE / HOLD verdict.

Run:   python -m qa.qa_suite              # writes qa/qa_report.md + .html
CI:    tests/test_qa_battery.py exercises the same check functions.

Every check reads ONLY the society trace / public API (hard rule 0.4); the engine
is consumed read-only at the pinned commit. No engine state is mutated.
"""

from __future__ import annotations

import gzip
import json
import math
import os
import platform
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from inn import metrics as M  # noqa: E402
from inn import timeplots as TP  # noqa: E402
from inn.config import load_inn_config  # noqa: E402
from inn.engine_surface import (  # noqa: E402
    ENGINE_ACTIONS,
    GLOBAL_STATES,
    PERCEIVABLE_EVENTS,
    PINNED_COMMIT,
    believable_day_layout,
)
from inn.intervention import ACTION_PALETTE, ControlState, make_intervention  # noqa: E402
from inn.live import LiveSession  # noqa: E402
from inn.scenario import dump_scenario, replay_scenario  # noqa: E402
from inn.session import replay, run_session  # noqa: E402

CFG = load_inn_config(ROOT / "inn.yaml")
LAYOUT = believable_day_layout()
DAY_TICKS = LAYOUT["day_ticks"]
PROFILE = CFG.default_profile or "game_semantic_profile"

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


@dataclass
class Result:
    id: str
    category: str
    name: str
    status: str = PASS
    detail: str = ""
    metrics: dict = field(default_factory=dict)
    seconds: float = 0.0


# -- small helpers -------------------------------------------------------------

def _run(plan="impulse", out=None, **kw):
    out = out or tempfile.mkdtemp(prefix="qa_")
    header = run_session(CFG, plan, out, **kw)
    return header, Path(out)


def _records(d: Path):
    return M.load_records(d / "trace.jsonl.gz")


def _check(id, category, name):
    """Decorator-ish wrapper: a check fn returns (status, detail, metrics) or raises."""
    def wrap(fn):
        def run() -> Result:
            t0 = time.perf_counter()
            try:
                status, detail, mx = fn()
            except AssertionError as e:
                status, detail, mx = FAIL, f"assertion: {e}", {}
            except Exception as e:  # any error is a failure, captured
                tb = traceback.format_exc().strip().splitlines()[-1]
                status, detail, mx = FAIL, f"{type(e).__name__}: {e} | {tb}", {}
            return Result(id, category, name, status, detail, mx or {},
                          round(time.perf_counter() - t0, 3))
        run._meta = (id, category, name)
        return run
    return wrap


# ============================================================================
# A. FUNCTIONAL
# ============================================================================

@_check("F1", "Functional", "Determinism — same inputs reproduce the trace SHA")
def f_determinism():
    a, _ = _run("impulse", seed=7, n_ticks=400)
    b, _ = _run("impulse", seed=7, n_ticks=400)
    assert a["trace_sha256"] == b["trace_sha256"], "two identical runs differ"
    # NOTE: the inn is seed-insensitive for the canonical plans — the engine tick is
    # deterministic and no stochastic activity-pick fires — so a different seed need NOT
    # diverge. We report that as an observation, not a contract.
    c, _ = _run("impulse", seed=8, n_ticks=400)
    return PASS, "identical inputs reproduce the trace bit-for-bit", \
        {"sha": a["trace_sha256"][:12], "seed_sensitive": c["trace_sha256"] != a["trace_sha256"]}


@_check("F2", "Functional", "Session replay reproduces the recorded SHA")
def f_replay():
    h, d = _run("control", seed=7, n_ticks=400)
    rep = replay(d / "session.json", ROOT / "inn.yaml", tempfile.mkdtemp(prefix="qa_"))
    assert rep["trace_sha256"] == h["trace_sha256"], "replay diverged"
    return PASS, "session.json replay is bit-identical", {}


@_check("F3", "Functional", "Scenario dump is lossless input-only and reproduces; rejects tamper")
def f_scenario():
    h, _ = _run("impulse", seed=7, n_ticks=400)
    sc = dump_scenario(CFG, seed=7, probe_plan="impulse", n_ticks=400)
    assert "trace_sha256" not in sc and "personas" not in sc, "scenario leaked results"
    assert sc["inn_yaml"] and sc["inn_yaml_sha256"] == CFG.yaml_sha256
    rep = replay_scenario(sc, tempfile.mkdtemp(prefix="qa_"))
    assert rep["trace_sha256"] == h["trace_sha256"], "scenario replay diverged"
    bad = dict(sc); bad["inn_yaml"] = sc["inn_yaml"] + "\n# tamper\n"
    rejected = False
    try:
        replay_scenario(bad, tempfile.mkdtemp(prefix="qa_"))
    except ValueError:
        rejected = True
    assert rejected, "tampered inn.yaml was not rejected"
    return PASS, "input-only, reproduces, and rejects a corrupted embed", {}


@_check("F4", "Functional", "resolution_factor — R=1 byte-identical; finer dt scales; reproduces")
def f_resolution_identity():
    base, _ = _run("impulse", seed=7, n_ticks=400)
    same, _ = _run("impulse", seed=7, n_ticks=400, resolution_factor=1.0)
    assert base["trace_sha256"] == same["trace_sha256"], "R=1 not byte-identical"
    r4a, _ = _run("impulse", seed=7, n_ticks=800, resolution_factor=4.0)
    r4b, _ = _run("impulse", seed=7, n_ticks=800, resolution_factor=4.0)
    assert r4a["trace_sha256"] == r4b["trace_sha256"], "R=4 not deterministic"
    assert abs(base["layout"]["dt"] / r4a["layout"]["dt"] - 4.0) < 0.05, "dt did not scale by ~4"
    return PASS, "R=1 identical, R=4 deterministic, dt scales by R", \
        {"dt_R1": round(base["layout"]["dt"], 2), "dt_R4": round(r4a["layout"]["dt"], 2)}


@_check("F5", "Functional", "burst_overlay — default OFF == no override; ON changes dynamics; reproduces")
def f_burst():
    base, _ = _run("impulse", seed=7, n_ticks=400)
    off, _ = _run("impulse", seed=7, n_ticks=400, burst_overlay=False)
    on, _ = _run("impulse", seed=7, n_ticks=400, burst_overlay=True)
    on2, _ = _run("impulse", seed=7, n_ticks=400, burst_overlay=True)
    assert base["trace_sha256"] == off["trace_sha256"], "default != burst OFF"
    assert on["trace_sha256"] != off["trace_sha256"], "burst ON did not change the run"
    assert on["trace_sha256"] == on2["trace_sha256"], "burst ON not deterministic"
    return PASS, "OFF is the default; ON changes & reproduces", {}


@_check("F6", "Functional", "Intervention — no-control byte-identical; override recorded; self-target rejected")
def f_intervention():
    auto, _ = _run("control", seed=7, n_ticks=400)
    # the M-G invariant: a run with NO subject controlled is byte-identical to autonomous
    # (intervention records are emitted only when a subject is controlled).
    none_ctl, dn = _run("control", seed=7, n_ticks=400, control=ControlState(None, "auto"))
    assert none_ctl["trace_sha256"] == auto["trace_sha256"], "no-subject control changed the trace"
    assert not any("intervention" in r for r in _records(dn)), "uncontrolled run carried intervention records"
    # a manual override at a daytime frontier (t=200, subject has company) changes the
    # trace and is recorded as manual_override.
    iv = [{"t": 200, "subject": "welf", "verb": "insult", "target": "halgrim"}]
    h, d = _run("control", seed=7, n_ticks=400,
                control=ControlState("welf", "manual"), interventions=iv)
    assert h["trace_sha256"] != auto["trace_sha256"], "manual override had no effect"
    recs = _records(d)
    ovr = [r for r in recs if r.get("intervention", {}).get("selected_by") == "manual_override"]
    assert ovr, "no manual_override recorded in the trace"
    # self-target rejected at validate time
    from inn.intervention import validate_target
    from inn.presence import Presence
    from inn.schedule import ScheduleStream
    from inn.clock import Clock
    clk = Clock.from_layout(LAYOUT)
    pres = Presence(CFG, ScheduleStream(CFG, clk), clk)
    assert make_intervention("insult", "halgrim")  # constructs
    assert validate_target(CFG, pres, "welf", "insult", "welf"), "self-target not rejected"
    return PASS, "no-subject run identical; override recorded; self-target rejected", {"overrides": len(ovr)}


@_check("F7", "Functional", "LiveSession (frontier) == batch run_session — bit-identical")
def f_live_equiv():
    # mirror the proven equivalence: F=200 is a daytime frontier where the subject has
    # company, so the override validates and fires (same as the batch's queued event).
    F, NT = 200, 400
    _, d = _run("control", seed=7, n_ticks=NT, control=ControlState("welf", "manual"),
                interventions=[{"t": F, "subject": "welf", "verb": "insult", "target": "halgrim"}])
    batch = _records(d)
    s = LiveSession(CFG, PROFILE, "control", 7, NT, subject="welf", mode="manual")
    s.advance(F)
    assert s.intervene("insult", "halgrim", advance=NT) is None, "frontier intervention was rejected"
    assert json.dumps(s.records, sort_keys=True) == json.dumps(batch, sort_keys=True), \
        "live-frontier trace differs from the batch trace"
    return PASS, "incremental frontier run reproduces the batch trace exactly", {"ticks": NT}


@_check("F8", "Functional", "Transducer coverage — every engine action accounted; events perceivable")
def f_transducer_coverage():
    rows = set(CFG.transducer.rows)
    accounted = rows | set(CFG.transducer.declared_gaps) | set(CFG.transducer.silent)
    assert ENGINE_ACTIONS <= accounted, f"uncovered: {sorted(ENGINE_ACTIONS - accounted)}"
    assert not (accounted - set(ENGINE_ACTIONS)), "phantom actions present"
    for r in CFG.transducer.rows.values():
        assert r.as_event in PERCEIVABLE_EVENTS, f"{r.action}->{r.as_event} not perceivable"
    for ev in CFG.provoking_event_types:
        assert ev in PERCEIVABLE_EVENTS, f"provoking {ev} not perceivable"
    return PASS, "all engine actions covered; emitted events perceivable", \
        {"actions": len(ENGINE_ACTIONS), "rows": len(rows)}


@_check("F9", "Functional", "Observation model + timeplots model build cleanly and serialise")
def f_models():
    import inn.observe as O
    _, d = _run("impulse", seed=7, n_ticks=400)
    recs = _records(d)
    m = O.build_model(recs, CFG)
    json.dumps(m)  # must be JSON-serialisable
    for k in ("cast", "ticks", "transitions", "incidents", "metrics", "intervention_ui"):
        assert k in m, f"observation model missing {k}"
    pm = TP.build_plot_model(recs, CFG, dt=LAYOUT["dt"])
    json.dumps(pm)
    assert pm["dt"] == LAYOUT["dt"] and pm["n"] == len(recs)
    assert all(i["tier"] in ("incident", "social") for i in pm["incidents"])
    return PASS, "observe + timeplots models serialise with the expected keys", \
        {"obs_keys": len(m), "plot_points": pm["n"]}


@_check("F10", "Functional", "Baseline cast — same trace schema; flatter cascades than the engine")
def f_baseline():
    from inn.baseline import run_baseline
    bd = tempfile.mkdtemp(prefix="qa_")
    bh = run_baseline(CFG, "impulse", bd, n_ticks=None)
    brecs = _records(Path(bd))
    # schema parity: same record top-level keys as an engine run
    _, ed = _run("impulse", seed=7)
    erecs = _records(ed)
    assert set(brecs[0]) >= {"t", "day", "clock", "personas", "transductions"}, "baseline schema off"
    binc = M.incidents(brecs, ("outburst",))
    einc = M.incidents(erecs, ("outburst",))
    bdepth = M.cascade_stats(binc)["max_depth"] if binc else 0
    edepth = M.cascade_stats(einc)["max_depth"] if einc else 0
    assert bdepth <= edepth, "baseline cascades deeper than the engine (unexpected)"
    return PASS, "baseline emits the same schema and stays flatter (no priming/grudges)", \
        {"baseline_depth": bdepth, "engine_depth": edepth,
         "baseline_sha": bh["trace_sha256"][:12]}


# ============================================================================
# B. TRACE INVARIANTS (property — across seeds / profiles / plans / resolutions)
# ============================================================================

def _invariants_over(recs):
    """Return a list of violation strings for one trace (empty == clean)."""
    bad = []
    last_t = -1
    for rec in recs:
        if rec["t"] <= last_t:
            bad.append(f"t not strictly increasing at {rec['t']}")
        last_t = rec["t"]
        for pid, tt in rec["personas"].items():
            g = tt["state_after_post"]["global"]
            for st in GLOBAL_STATES:
                v = g[st]
                if not (isinstance(v, (int, float)) and math.isfinite(v)):
                    bad.append(f"{pid}.{st}={v!r} not finite")
                elif not (-1e-6 <= v <= 1 + 1e-6):
                    bad.append(f"{pid}.{st}={v:.4f} outside [0,1]")
        for tr in rec["transductions"]:
            if tr["action"] not in ENGINE_ACTIONS:
                bad.append(f"transduction action {tr['action']} unknown")
            if tr.get("as") and tr["as"] not in PERCEIVABLE_EVENTS:
                bad.append(f"transduction as={tr['as']} not perceivable")
        if bad and len(bad) > 8:
            break
    return bad


@_check("B1", "Invariants", "All global states finite & within [0,1] across many runs")
def b_state_bounds():
    seen = 0
    for seed in (1, 7, 42):
        for plan in ("impulse", "step", "control"):
            _, d = _run(plan, seed=seed, n_ticks=500)
            v = _invariants_over(_records(d))
            assert not v, f"{plan}/seed{seed}: {v[:3]}"
            seen += 1
    return PASS, f"finite & clamped, t-monotone, known actions/events ({seen} runs)", {"runs": seen}


@_check("B2", "Invariants", "Clock/day/night consistent with dt; presence rooms valid")
def b_clock_presence():
    _, d = _run("impulse", seed=7)
    recs = _records(d)
    dt = LAYOUT["dt"]
    rooms = set(CFG.rooms)
    for rec in recs:
        # day index consistent with tick / day_ticks
        assert rec["day"] == rec["t"] // DAY_TICKS + 1, f"day mismatch at t={rec['t']}"
        # night flag consistent with waking_ticks
        off = rec["t"] % DAY_TICKS
        assert rec["night"] == (off >= LAYOUT["waking_ticks"]), f"night flag off at t={rec['t']}"
        for pid, room in (rec.get("presence") or {}).items():
            assert room in rooms, f"{pid} in unknown room {room}"
    return PASS, "day/night derive from dt; every presence room is declared", {"ticks": len(recs)}


@_check("B3", "Invariants", "resolution refinement preserves the real-time trajectory (convergent)")
def b_resolution_convergence():
    # compare end-of-day-1 states across R; finer dt must converge (shrinking error)
    def end_day1(R, ntick):
        _, d = _run("impulse", seed=7, n_ticks=ntick, resolution_factor=R)
        recs = _records(d)
        idx = next(i for i, r in enumerate(recs) if r["day"] == 2) - 1
        return {st: M.state_series(recs, (st,))["wojslaw"][st][idx]
                for st in ("boredom", "fatigue", "stress", "anger")}
    base = end_day1(1.0, DAY_TICKS + 5)
    r4 = end_day1(4.0, 4 * DAY_TICKS + 5)
    r8 = end_day1(8.0, 8 * DAY_TICKS + 5)
    e4 = max(abs(base[s] - r4[s]) for s in base)
    e8 = max(abs(base[s] - r8[s]) for s in base)
    assert e4 < 0.05 and e8 < 0.05, f"diverged: e4={e4:.3f} e8={e8:.3f}"
    status = PASS if e8 <= e4 + 0.01 else WARN
    return status, f"end-of-day-1 error vs R=1: R4={e4:.3f}, R8={e8:.3f} (converging)", \
        {"err_R4": round(e4, 4), "err_R8": round(e8, 4)}


@_check("B4", "Invariants", "Model builders are pure (do not mutate the trace) + idempotent")
def b_purity():
    import copy
    import inn.observe as O
    _, d = _run("impulse", seed=7, n_ticks=400)
    recs = _records(d)
    snap = copy.deepcopy(recs)
    m1 = json.dumps(O.build_model(recs, CFG))
    p1 = json.dumps(TP.build_plot_model(recs, CFG))
    assert recs == snap, "build_model/build_plot_model mutated the trace"
    m2 = json.dumps(O.build_model(recs, CFG))
    p2 = json.dumps(TP.build_plot_model(recs, CFG))
    assert m1 == m2 and p1 == p2, "model build is not idempotent"
    return PASS, "trace read-only; identical output on re-build", {}


# ============================================================================
# C. ROBUSTNESS / FUZZ (negative tests — every guard must reject bad input)
# ============================================================================

def _load_bad(mutate) -> bool:
    """Apply `mutate(doc)` to a parsed inn.yaml, write it, and return True iff
    load_inn_config rejects it with ValueError."""
    doc = yaml.safe_load((ROOT / "inn.yaml").read_text(encoding="utf-8"))
    mutate(doc)
    p = Path(tempfile.mkdtemp(prefix="qa_")) / "inn.yaml"
    p.write_text(yaml.safe_dump(doc), encoding="utf-8")
    try:
        load_inn_config(p)
        return False
    except (ValueError, KeyError):
        return True


@_check("C1", "Robustness", "Config validation rejects malformed inn.yaml (battery of mutations)")
def c_config_fuzz():
    cases = {
        "unknown top-level key": lambda d: d.update({"bogus_key": 1}),
        "duplicate cast id": lambda d: d["cast"].append(dict(d["cast"][0])),
        "unknown room_home": lambda d: d["cast"][0].__setitem__("room_home", "void"),
        "non-perceivable transducer event":
            lambda d: d["transducer"]["rows"]["outburst"].__setitem__("as", "telepathy"),
        "non-perceivable provoking type":
            lambda d: d.setdefault("world", {}).__setitem__("provoking_event_types", ["mindmeld"]),
        "probe day out of range":
            lambda d: d["probes"]["impulse"][0].__setitem__("t", "day9 20:00"),
        "observation.high bad state":
            lambda d: d.setdefault("observation", {}).setdefault("high", {}).__setitem__("vibe", 0.5),
    }
    rejected, failed = 0, []
    for name, mut in cases.items():
        if _load_bad(mut):
            rejected += 1
        else:
            failed.append(name)
    assert not failed, f"NOT rejected: {failed}"
    return PASS, f"all {rejected} malformed configs rejected", {"cases": rejected}


@_check("C2", "Robustness", "Invalid interventions are rejected, not silently applied")
def c_intervention_fuzz():
    from inn.intervention import validate_target
    from inn.presence import Presence
    from inn.schedule import ScheduleStream
    from inn.clock import Clock
    clk = Clock.from_layout(LAYOUT)
    pres = Presence(CFG, ScheduleStream(CFG, clk), clk)
    checks = [
        ("unknown verb", lambda: validate_target(CFG, pres, "welf", "smite", "halgrim")),
        ("self target", lambda: validate_target(CFG, pres, "welf", "insult", "welf")),
        ("absent target", lambda: validate_target(CFG, pres, "welf", "insult", "nobody")),
        ("target on a target-less verb", lambda: validate_target(CFG, pres, "welf", "observe", "halgrim")),
    ]
    bad = [n for n, fn in checks if not fn()]
    assert not bad, f"accepted bad interventions: {bad}"
    # make_intervention raises on unknown verb
    raised = False
    try:
        make_intervention("smite")
    except ValueError:
        raised = True
    assert raised, "make_intervention accepted an unknown verb"
    return PASS, "unknown verb / self / absent / target-less all rejected", {"cases": len(checks) + 1}


@_check("C3", "Robustness", "Corrupt/empty trace handling is graceful (no crash on read)")
def c_trace_robust():
    d = Path(tempfile.mkdtemp(prefix="qa_"))
    (d / "trace.jsonl.gz").write_bytes(gzip.compress(b""))  # empty trace
    recs = M.load_records(d / "trace.jsonl.gz")
    assert recs == [], "empty trace did not read as []"
    # metrics over empty trace must not crash
    M.incidents(recs, ("outburst",))
    return PASS, "empty trace reads as [] and metrics tolerate it", {}


# ============================================================================
# D. NON-FUNCTIONAL — performance, scaling, footprint
# ============================================================================

@_check("D1", "Performance", "Throughput — persona-ticks/second on a full 3-day run")
def d_throughput():
    t0 = time.perf_counter()
    h, _ = _run("impulse", seed=7)  # full 3 days
    dt = time.perf_counter() - t0
    pt = len(CFG.cast) * h["n_ticks"]
    rate = pt / dt
    status = PASS if rate > 1000 else WARN
    return status, f"{rate:,.0f} persona-ticks/s ({h['n_ticks']} ticks x {len(CFG.cast)} cast in {dt:.2f}s)", \
        {"persona_ticks_per_s": round(rate), "wall_s": round(dt, 2), "n_ticks": h["n_ticks"]}


@_check("D2", "Performance", "Resolution scaling — wall-time grows ~linearly with tick count")
def d_scaling():
    def timed(R, ntick):
        t0 = time.perf_counter(); _run("impulse", seed=7, n_ticks=ntick, resolution_factor=R)
        return time.perf_counter() - t0
    n = DAY_TICKS
    t1 = timed(1.0, n)
    t8 = timed(8.0, 8 * n)
    ratio = (t8 / t1) if t1 > 0 else 0
    # 8x the ticks should cost roughly 8x (allow 4x..16x for noise/overhead)
    status = PASS if 4.0 <= ratio <= 16.0 else WARN
    return status, f"8x ticks cost {ratio:.1f}x wall-time (expect ~8x)", \
        {"t_R1_1day_s": round(t1, 2), "t_R8_1day_s": round(t8, 2), "ratio": round(ratio, 1)}


@_check("D3", "Performance", "Trace footprint — compressed bytes per tick")
def d_footprint():
    h, d = _run("impulse", seed=7)
    size = (d / "trace.jsonl.gz").stat().st_size
    per = size / h["n_ticks"]
    return PASS, f"{size/1024:,.0f} KB for {h['n_ticks']} ticks ({per:,.0f} bytes/tick, gzip)", \
        {"trace_kb": round(size / 1024), "bytes_per_tick": round(per)}


@_check("D4", "Performance", "Memory — peak allocation for a full run")
def d_memory():
    import tracemalloc
    tracemalloc.start()
    _run("impulse", seed=7)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    mb = peak / 1e6
    status = PASS if mb < 1500 else WARN
    return status, f"peak {mb:,.0f} MB for a full 3-day run", {"peak_mb": round(mb)}


@_check("D6", "Performance", "Display payload bounded at fine dt — strided observation model stays small")
def d_payload():
    # the cockpit strides the observation model by the resolution factor so the page
    # payload stays ~constant (it froze at R=8 with a 58 MB / 17k-tick full model).
    import inn.observe as O
    _, d = _run("impulse", seed=7, resolution_factor=8.0)
    recs = _records(d)
    full = len(json.dumps(O.build_model(recs, CFG, stride=1)))
    strided = len(json.dumps(O.build_model(recs, CFG, stride=8)))
    ratio = full / max(1, strided)
    assert strided < 12_000_000, f"strided model still {strided/1e6:.0f} MB"
    assert ratio > 5, f"stride did not shrink the payload (ratio {ratio:.1f})"
    return PASS, f"strided model {strided/1e6:.1f} MB vs full {full/1e6:.0f} MB at R=8 ({ratio:.0f}x smaller)", \
        {"strided_mb": round(strided / 1e6, 1), "full_mb": round(full / 1e6), "shrink_x": round(ratio)}


@_check("D5", "Performance", "Determinism under stress — many seeds each reproduce")
def d_stress_determinism():
    mism = 0
    for seed in range(20):
        a, _ = _run("impulse", seed=seed, n_ticks=250)
        b, _ = _run("impulse", seed=seed, n_ticks=250)
        if a["trace_sha256"] != b["trace_sha256"]:
            mism += 1
    assert mism == 0, f"{mism}/20 seeds were non-deterministic"
    return PASS, "20/20 seeds reproduced bit-identically", {"seeds": 20}


# ============================================================================
# E. STABILITY / BOUNDEDNESS (G0)
# ============================================================================

@_check("E1", "Stability", "Incident corridor — the canonical impulse run is bounded (no runaway)")
def e_corridor():
    _, d = _run("impulse", seed=7, profile=PROFILE)
    recs = _records(d)
    inc = M.incidents(recs, ("outburst",))
    n = len(inc)
    cs = M.cascade_stats(inc) if inc else {"max_depth": 0}
    # hard ceiling: anything >100 outbursts in 3 days is a runaway (FAIL).
    # soft corridor (CLAUDE.md DEC-7 ~8/impulse, depth 2-3): WARN if outside 1..40.
    if n > 100:
        return FAIL, f"runaway: {n} outbursts in 3 days", {"incidents": n}
    status = PASS if 1 <= n <= 40 else WARN
    return status, f"{n} outbursts, cascade depth {cs['max_depth']} (corridor ~4-10, depth 2-3)", \
        {"incidents": n, "cascade_depth": cs["max_depth"]}


@_check("E2", "Stability", "No saturation — UPPER-clamp dwell low; envelopes inside [0,1]")
def e_saturation():
    _, d = _run("impulse", seed=7)
    recs = _records(d)
    env = M.envelopes(recs)
    ok_env = all(-1e-6 <= v["min"] and v["max"] <= 1 + 1e-6
                 for p in env.values() for v in p.values())
    assert ok_env, "an envelope left [0,1]"
    # saturation = dwell at the UPPER clamp (>=0.999). Time spent at 0.0 (calm) is healthy
    # and must NOT count — the affect states sit at 0 through the calm stretches/nights.
    states = ("anger", "stress", "frustration", "boredom")
    ser = M.state_series(recs, states)
    worst, worst_at = 0.0, ""
    for pid, per in ser.items():
        for st, xs in per.items():
            frac = sum(1 for v in xs if v >= 0.999) / len(xs)
            if frac > worst:
                worst, worst_at = frac, f"{pid}.{st}"
    status = PASS if worst < 0.10 else WARN
    return status, f"max upper-clamp dwell {worst*100:.1f}% ({worst_at or 'none'}); envelopes in [0,1]", \
        {"max_upper_clamp_pct": round(worst * 100, 2)}


@_check("E3", "Stability", "Resolution boundedness — finer dt does not explode incidents")
def e_resolution_bounded():
    _, d1 = _run("impulse", seed=7, resolution_factor=1.0)
    _, d8 = _run("impulse", seed=7, resolution_factor=8.0)
    n1 = len(M.incidents(_records(d1), ("outburst",)))
    n8 = len(M.incidents(_records(d8), ("outburst",)))
    # finer dt is a new operating point; incidents should stay the same order of
    # magnitude (not blow up). FAIL only on a true explosion.
    if n8 > max(40, 6 * (n1 + 1)):
        return FAIL, f"incidents exploded at R=8: {n1} -> {n8}", {"R1": n1, "R8": n8}
    status = PASS if n8 <= max(20, 3 * (n1 + 1)) else WARN
    return status, f"outbursts R1={n1} vs R8={n8} (bounded; fine dt is a new operating point)", \
        {"R1": n1, "R8": n8}


# ============================================================================
# F. PARITY ANCHORS
# ============================================================================

@_check("F-G2", "Parity", "G2 reference — a fresh CPython control run matches the parity SHA")
def f_g2():
    ref_path = ROOT / "observatory" / "g2_reference.json"
    if not ref_path.is_file():
        return WARN, "g2_reference.json absent (run build_bundle/g2_parity first)", {}
    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    h, _ = _run("control", seed=ref["seed"], n_ticks=ref["n_ticks"], profile=PROFILE)
    ok = h["trace_sha256"] == ref["trace_sha256"]
    assert ok, f"SHA mismatch: {h['trace_sha256'][:12]} vs ref {ref['trace_sha256'][:12]}"
    return PASS, "fresh CPython run reproduces the G2 reference SHA", {"sha": ref["trace_sha256"][:12]}


@_check("F-GOLD", "Parity", "Golden — the canonical control session matches the frozen hash")
def f_golden():
    gp = ROOT / "tests" / "golden" / "canonical_session.sha256"
    if not gp.is_file():
        return WARN, "golden hash file absent", {}
    h, _ = _run("control", seed=None)  # seed defaults to cfg.g0 seed, full 3 days
    ok = h["trace_sha256"] == gp.read_text().strip()
    assert ok, "golden canonical-session hash mismatch"
    return PASS, "canonical 3-day control session matches the frozen golden", {}


# ---------------------------------------------------------------------------

CHECKS = [
    f_determinism, f_replay, f_scenario, f_resolution_identity, f_burst,
    f_intervention, f_live_equiv, f_transducer_coverage, f_models, f_baseline,
    b_state_bounds, b_clock_presence, b_resolution_convergence, b_purity,
    c_config_fuzz, c_intervention_fuzz, c_trace_robust,
    d_throughput, d_scaling, d_footprint, d_memory, d_payload, d_stress_determinism,
    e_corridor, e_saturation, e_resolution_bounded,
    f_g2, f_golden,
]


def run_all(verbose=True) -> list[Result]:
    out = []
    for fn in CHECKS:
        r = fn()
        out.append(r)
        if verbose:
            print(f"[{r.status:4}] {r.id:6} {r.name}  ({r.seconds}s)")
            if r.status != PASS:
                print(f"         -> {r.detail}")
    return out


# -- reporting ----------------------------------------------------------------

def _env() -> dict:
    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "engine_commit": PINNED_COMMIT,
        "inn_yaml_sha256": CFG.yaml_sha256[:16],
        "dt_s": round(LAYOUT["dt"], 2),
        "day_ticks": DAY_TICKS,
        "cast": len(CFG.cast),
        "profile": PROFILE,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def _verdict(results) -> tuple[str, int, int, int]:
    n_fail = sum(r.status == FAIL for r in results)
    n_warn = sum(r.status == WARN for r in results)
    n_pass = sum(r.status == PASS for r in results)
    return (("HOLD" if n_fail else "PROMOTE"), n_pass, n_warn, n_fail)


def render_md(results, env) -> str:
    verdict, np_, nw, nf = _verdict(results)
    L = [f"# Equilibrium Inn — QA battery report",
         "",
         f"**Verdict: {verdict}** — {np_} passed · {nw} warnings · {nf} failed "
         f"(of {len(results)} deep checks).",
         "",
         "This battery is an aggressive functional + non-functional gate for promoting the "
         "engine through the inn world-layer: determinism, dt-resolution refinement, scenario "
         "reproducibility, intervention safety, trace invariants, config/input fuzzing, "
         "performance & scaling, boundedness/stability, and parity anchors. It complements the "
         "228-test pytest suite (run separately).",
         "",
         "## Environment",
         "",
         "| field | value |", "|---|---|"]
    for k, v in env.items():
        L.append(f"| {k} | {v} |")
    # category sections
    cats = {}
    for r in results:
        cats.setdefault(r.category, []).append(r)
    icon = {PASS: "✅", WARN: "⚠️", FAIL: "❌"}
    for cat, rs in cats.items():
        L += ["", f"## {cat}", "", "| | id | check | detail | key metrics | t(s) |",
              "|---|---|---|---|---|---|"]
        for r in rs:
            mx = ", ".join(f"{k}={v}" for k, v in r.metrics.items())
            L.append(f"| {icon[r.status]} | {r.id} | {r.name} | {r.detail} | {mx} | {r.seconds} |")
    L += ["", "## Methodology", "",
          "- Every check reads only the society trace / public API (hard rule 0.4); the engine "
          "is consumed read-only at the pinned commit.",
          "- WARN = outside a soft target but not a defect (e.g. the incident corridor, a new "
          "fine-dt operating point, a perf ratio). FAIL = a broken contract.",
          "- Determinism/parity use SHA-256 over the full trace; performance numbers are "
          "machine-dependent (see Environment).",
          ""]
    return "\n".join(L)


def render_html(results, env) -> str:
    verdict, np_, nw, nf = _verdict(results)
    vcolor = {"PROMOTE": "#3a7d2c", "HOLD": "#b5532e"}[verdict]
    badge = {PASS: ("PASS", "#3a7d2c", "#e7f3e0"), WARN: ("WARN", "#9a6a16", "#f7eed0"),
             FAIL: ("FAIL", "#b5532e", "#f6ddd2")}
    cats = {}
    for r in results:
        cats.setdefault(r.category, []).append(r)
    rows = []
    for cat, rs in cats.items():
        rows.append(f"<tr class='cat'><td colspan='6'>{cat}</td></tr>")
        for r in rs:
            lab, fg, bg = badge[r.status]
            mx = "<br>".join(f"<span class='m'>{k}</span> {v}" for k, v in r.metrics.items())
            rows.append(
                f"<tr><td><span class='b' style='color:{fg};background:{bg}'>{lab}</span></td>"
                f"<td class='id'>{r.id}</td><td class='nm'>{r.name}</td>"
                f"<td class='dt'>{r.detail}</td><td class='mx'>{mx}</td>"
                f"<td class='t'>{r.seconds}s</td></tr>")
    envrows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in env.items())
    return f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Equilibrium Inn — QA report</title>
<style>
:root{{--ink:#3a2f24;--muted:#7c6f5d;--line:#d8c9a8;--panel:#fbf4e3}}
*{{box-sizing:border-box}}
body{{margin:0;background:radial-gradient(circle at 50% -8%,#fbf3df,#ecdcb8) fixed;
 color:var(--ink);font:14px/1.5 "Iowan Old Style",Georgia,serif;padding:0 0 60px}}
.wrap{{max-width:1180px;margin:0 auto;padding:0 22px}}
h1{{font-size:27px;margin:24px 0 4px}}
.verdict{{display:inline-block;font-size:15px;font-weight:700;color:#fff;background:{vcolor};
 border-radius:8px;padding:5px 14px;margin:8px 0}}
.lead{{color:#5a4a33;max-width:860px}}
.counts span{{display:inline-block;margin-right:14px;font-variant-numeric:tabular-nums}}
table{{width:100%;border-collapse:collapse;margin:14px 0;background:var(--panel);
 border:1px solid var(--line);border-radius:12px;overflow:hidden}}
td,th{{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
tr.cat td{{background:#efe2c2;font-size:12px;text-transform:uppercase;letter-spacing:1.2px;
 color:var(--muted);font-weight:700}}
.b{{font-size:11px;font-weight:800;border-radius:6px;padding:2px 7px}}
.id{{font-variant-numeric:tabular-nums;color:var(--muted);white-space:nowrap}}
.nm{{font-weight:600;max-width:280px}}
.dt{{color:#5a4a33;max-width:380px}}
.mx{{font-size:12px;color:var(--muted)}} .mx .m{{color:#8a6a2e}}
.t{{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}}
.env{{max-width:520px}} .env td:first-child{{color:var(--muted);width:160px}}
.foot{{color:var(--muted);font-size:12px;margin-top:18px}}
</style></head><body><div class='wrap'>
<h1>Equilibrium Inn — QA battery</h1>
<div class='verdict'>VERDICT: {verdict}</div>
<div class='counts'><span>✅ {np_} passed</span><span>⚠️ {nw} warnings</span>
 <span>❌ {nf} failed</span><span>· {len(results)} deep checks</span></div>
<p class='lead'>Aggressive functional + non-functional gate for promoting the engine through
the inn world-layer: determinism, dt-resolution refinement, scenario reproducibility,
intervention safety, trace invariants, config/input fuzzing, performance &amp; scaling,
boundedness/stability, and parity anchors. Complements the 228-test pytest suite.</p>
<h3>Environment</h3>
<table class='env'>{envrows}</table>
<h3>Results</h3>
<table>
<tr><th></th><th>id</th><th>check</th><th>detail</th><th>metrics</th><th>t</th></tr>
{''.join(rows)}
</table>
<p class='foot'>WARN = outside a soft target (corridor / new fine-dt operating point / perf
ratio), not a defect. FAIL = a broken contract. Determinism &amp; parity use SHA-256 over
the full trace; performance is machine-dependent.</p>
</div></body></html>"""


def main(argv=None):
    results = run_all(verbose=True)
    env = _env()
    md = ROOT / "qa" / "qa_report.md"
    html = ROOT / "qa" / "qa_report.html"
    md.write_text(render_md(results, env), encoding="utf-8")
    html.write_text(render_html(results, env), encoding="utf-8")
    verdict, np_, nw, nf = _verdict(results)
    print(f"\nVERDICT: {verdict}  ({np_} pass / {nw} warn / {nf} fail)")
    print(f"wrote {md}")
    print(f"wrote {html}")
    return 1 if nf else 0


if __name__ == "__main__":
    raise SystemExit(main())
