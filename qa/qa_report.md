# Equilibrium Inn — QA battery report

**Verdict: PROMOTE** — 28 passed · 0 warnings · 0 failed (of 28 deep checks).

This battery is an aggressive functional + non-functional gate for promoting the engine through the inn world-layer: determinism, dt-resolution refinement, scenario reproducibility, intervention safety, trace invariants, config/input fuzzing, performance & scaling, boundedness/stability, and parity anchors. It complements the 228-test pytest suite (run separately).

## Environment

| field | value |
|---|---|
| generated | 2026-06-18 19:33 UTC |
| engine_commit | 311be038b5e8ee7e0ad931ea66f9f896c21be9a9 |
| inn_yaml_sha256 | 43f45250088a06b9 |
| dt_s | 120.45 |
| day_ticks | 717 |
| cast | 7 |
| profile | game_semantic_profile |
| python | 3.12.10 |
| platform | Windows-11-10.0.26200-SP0 |

## Functional

| | id | check | detail | key metrics | t(s) |
|---|---|---|---|---|---|
| ✅ | F1 | Determinism — same inputs reproduce the trace SHA | identical inputs reproduce the trace bit-for-bit | sha=c82aa87c262a, seed_sensitive=False | 3.045 |
| ✅ | F2 | Session replay reproduces the recorded SHA | session.json replay is bit-identical |  | 2.579 |
| ✅ | F3 | Scenario dump is lossless input-only and reproduces; rejects tamper | input-only, reproduces, and rejects a corrupted embed |  | 2.554 |
| ✅ | F4 | resolution_factor — R=1 byte-identical; finer dt scales; reproduces | R=1 identical, R=4 deterministic, dt scales by R | dt_R1=120.45, dt_R4=30.11 | 6.341 |
| ✅ | F5 | burst_overlay — default OFF == no override; ON changes dynamics; reproduces | OFF is the default; ON changes & reproduces |  | 5.051 |
| ✅ | F6 | Intervention — no-control byte-identical; override recorded; self-target rejected | no-subject run identical; override recorded; self-target rejected | overrides=1 | 4.404 |
| ✅ | F7 | LiveSession (frontier) == batch run_session — bit-identical | incremental frontier run reproduces the batch trace exactly | ticks=400 | 2.775 |
| ✅ | F8 | Transducer coverage — every engine action accounted; events perceivable | all engine actions covered; emitted events perceivable | actions=13, rows=6 | 0.0 |
| ✅ | F9 | Observation model + timeplots model build cleanly and serialise | observe + timeplots models serialise with the expected keys | obs_keys=18, plot_points=400 | 1.512 |
| ✅ | F10 | Baseline cast — same trace schema; flatter cascades than the engine | baseline emits the same schema and stays flatter (no priming/grudges) | baseline_depth=1, engine_depth=3, baseline_sha=28cdabef7588 | 7.447 |

## Invariants

| | id | check | detail | key metrics | t(s) |
|---|---|---|---|---|---|
| ✅ | B1 | All global states finite & within [0,1] across many runs | finite & clamped, t-monotone, known actions/events (9 runs) | runs=9 | 15.084 |
| ✅ | B2 | Clock/day/night consistent with dt; presence rooms valid | day/night derive from dt; every presence room is declared | ticks=2151 | 7.006 |
| ✅ | B3 | resolution refinement preserves the real-time trajectory (convergent) | end-of-day-1 error vs R=1: R4=0.019, R8=0.019 (converging) | err_R4=0.0191, err_R8=0.0191 | 27.665 |
| ✅ | B4 | Model builders are pure (do not mutate the trace) + idempotent | trace read-only; identical output on re-build |  | 1.978 |

## Robustness

| | id | check | detail | key metrics | t(s) |
|---|---|---|---|---|---|
| ✅ | C1 | Config validation rejects malformed inn.yaml (battery of mutations) | all 7 malformed configs rejected | cases=7 | 0.654 |
| ✅ | C2 | Invalid interventions are rejected, not silently applied | unknown verb / self / absent / target-less all rejected | cases=5 | 0.001 |
| ✅ | C3 | Corrupt/empty trace handling is graceful (no crash on read) | empty trace reads as [] and metrics tolerate it |  | 0.012 |

## Performance

| | id | check | detail | key metrics | t(s) |
|---|---|---|---|---|---|
| ✅ | D1 | Throughput — persona-ticks/second on a full 3-day run | 2,607 persona-ticks/s (2151 ticks x 7 cast in 5.78s) | persona_ticks_per_s=2607, wall_s=5.78, n_ticks=2151 | 5.776 |
| ✅ | D2 | Resolution scaling — wall-time grows ~linearly with tick count | 8x ticks cost 7.0x wall-time (expect ~8x) | t_R1_1day_s=1.94, t_R8_1day_s=13.56, ratio=7.0 | 15.501 |
| ✅ | D3 | Trace footprint — compressed bytes per tick | 3,213 KB for 2151 ticks (1,529 bytes/tick, gzip) | trace_kb=3213, bytes_per_tick=1529 | 5.79 |
| ✅ | D4 | Memory — peak allocation for a full run | peak 1 MB for a full 3-day run | peak_mb=1 | 35.932 |
| ✅ | D6 | Display payload bounded at fine dt — strided observation model stays small | strided model 7.4 MB vs full 58 MB at R=8 (8x smaller) | strided_mb=7.4, full_mb=58, shrink_x=8 | 61.47 |
| ✅ | D5 | Determinism under stress — many seeds each reproduce | 20/20 seeds reproduced bit-identically | seeds=20 | 38.541 |

## Stability

| | id | check | detail | key metrics | t(s) |
|---|---|---|---|---|---|
| ✅ | E1 | Incident corridor — the canonical impulse run is bounded (no runaway) | 8 outbursts, cascade depth 3 (corridor ~4-10, depth 2-3) | incidents=8, cascade_depth=3 | 7.146 |
| ✅ | E2 | No saturation — UPPER-clamp dwell low; envelopes inside [0,1] | max upper-clamp dwell 0.0% (none); envelopes in [0,1] | max_upper_clamp_pct=0.0 | 7.203 |
| ✅ | E3 | Resolution boundedness — finer dt does not explode incidents | outbursts R1=8 vs R8=6 (bounded; fine dt is a new operating point) | R1=8, R8=6 | 56.091 |

## Parity

| | id | check | detail | key metrics | t(s) |
|---|---|---|---|---|---|
| ✅ | F-G2 | G2 reference — a fresh CPython control run matches the parity SHA | fresh CPython run reproduces the G2 reference SHA | sha=6a7404b6c30c | 2.176 |
| ✅ | F-GOLD | Golden — the canonical control session matches the frozen hash | canonical 3-day control session matches the frozen golden |  | 4.184 |

## Methodology

- Every check reads only the society trace / public API (hard rule 0.4); the engine is consumed read-only at the pinned commit.
- WARN = outside a soft target but not a defect (e.g. the incident corridor, a new fine-dt operating point, a perf ratio). FAIL = a broken contract.
- Determinism/parity use SHA-256 over the full trace; performance numbers are machine-dependent (see Environment).
