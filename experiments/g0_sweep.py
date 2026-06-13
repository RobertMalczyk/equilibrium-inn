"""G0 stability sweep (CLAUDE.md section 8): transducer intensity x recovery
on/off x catalog richness, over the three canonical probe plans.

Each cell is a full 3-day deterministic session. Outputs per cell:
experiments/out/g0/<cell>/<plan>/{trace.jsonl.gz, session.json, metrics.json}.

Usage: python -m experiments.g0_sweep [--quick]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from inn import metrics as M
from inn.config import load_inn_config
from inn.engine_surface import believable_day_layout
from inn.loop import make_persona_loader
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "out" / "g0"

# The canonical inn runs with idle recovery OFF (inn.yaml engine_overrides);
# the recovery=true sweep axis RESTORES the engine's default idle-recovery
# pull to measure its effect on the corridor.
_DEFAULT_RECOVERY = {"idle_recovery": {"stress": -0.010, "anger": -0.010}}


def make_loader(cfg, recovery: bool):
    """Believable timescale + inn engine_overrides; recovery axis toggles the
    engine's default idle-recovery pull back on."""
    return make_persona_loader(cfg.engine_overrides,
                               extra=_DEFAULT_RECOVERY if recovery else None)


def upper_clamp_dwell(records, states=("anger", "stress", "frustration")) -> dict:
    """Fraction of ticks at the UPPER clamp (>= 0.999) — the saturation signal.
    (metrics.clamp_dwell counts both clamps; boredom at 0 is healthy.)"""
    series = M.state_series(records, states)
    return {pid: {st: sum(1 for x in xs if x >= 0.999) / len(xs)
                  for st, xs in per.items()}
            for pid, per in series.items()}


def cell_metrics(records: list[dict], cfg, layout) -> dict:
    incs = M.incidents(records, tuple(cfg.g0["incident_def"]["actions"]))
    cs = M.cascade_stats(incs)
    cs.pop("cascades")
    ucd = upper_clamp_dwell(records)
    return {
        "incidents": cs,
        "incident_count": cs["n_incidents"],
        "routine_adherence": M.routine_adherence(records),
        "action_entropy": M.action_entropy(records),
        "envelopes": M.envelopes(records),
        "upper_clamp_dwell": ucd,
        "max_upper_clamp_dwell": max((v for per in ucd.values() for v in per.values()),
                                     default=0.0),
        "fft": M.fft_dominant(records, layout["dt"]),
        "delivery_delays": _delay_hist(records),
        "n_gaps": sum(len(r["gaps"]) for r in records),
        "n_dropped": sum(len(r["dropped"]) for r in records),
    }


def _delay_hist(records) -> dict:
    h: dict[int, int] = {}
    for r in records:
        for d in r["delivery_delays"].values():
            h[d] = h.get(d, 0) + 1
    return {str(k): v for k, v in sorted(h.items())}


def verdict(m: dict, corridor: tuple[int, int]) -> str:
    """Per-cell stability verdict for the impulse protocol.
    saturates: any persona pinned at an upper clamp for >20% of the run.
    limit_cycles: a dominant sub-day oscillation carries >50% of spectral power.
    settles: neither; corridor flag reported separately."""
    if m["max_upper_clamp_dwell"] > 0.20:
        return "saturates"
    # The inn has a designed daily rhythm (meals, sleep), so raw FFT power at
    # day-scale periods is not pathology. A limit cycle worth the name shows
    # up as sustained incident production far above the corridor.
    if m["incident_count"] > 3 * corridor[1]:
        return "limit_cycles"
    return "settles"


def run_sweep(quick: bool = False) -> list[dict]:
    cfg = load_inn_config(ROOT / "inn.yaml")
    layout = believable_day_layout()
    sweep = cfg.g0["sweep"]
    corridor = tuple(cfg.g0["corridor"]["incidents_per_impulse_run"])
    scales = sweep["transducer_scale"][:2] if quick else sweep["transducer_scale"]
    recoveries = sweep["recovery"]
    richness = sweep["catalog_richness"]
    plans = ["impulse", "step", "control"]
    results = []
    t0 = time.time()
    for scale in scales:
        for rec_on in recoveries:
            loader = make_loader(cfg, rec_on)
            for rname, rmult in richness.items():
                cell = f"s{scale}_r{'on' if rec_on else 'off'}_{rname}"
                for plan in plans:
                    out_dir = OUT / cell / plan
                    run_session(cfg, plan, out_dir, transducer_scale=scale,
                                richness_mults=rmult, persona_loader=loader)
                    records = M.load_records(out_dir / "trace.jsonl.gz")
                    m = cell_metrics(records, cfg, layout)
                    m["cell"] = cell
                    m["plan"] = plan
                    m["scale"] = scale
                    m["recovery"] = rec_on
                    m["richness"] = rname
                    if plan == "impulse":
                        m["verdict"] = verdict(m, corridor)
                        m["in_corridor"] = corridor[0] <= m["incident_count"] <= corridor[1]
                    (out_dir / "metrics.json").write_text(
                        json.dumps(m, indent=2), encoding="utf-8")
                    results.append(m)
                    print(f"[{time.time()-t0:7.1f}s] {cell}/{plan}: "
                          f"incidents={m['incident_count']} "
                          f"{m.get('verdict','')}", flush=True)
    (OUT / "sweep_results.json").write_text(json.dumps(results, indent=2),
                                            encoding="utf-8")
    return results


if __name__ == "__main__":
    run_sweep(quick="--quick" in sys.argv)
