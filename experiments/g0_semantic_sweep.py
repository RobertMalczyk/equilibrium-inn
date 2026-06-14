"""G0 sweep for the SEMANTIC profile (CLAUDE.md DEC-1 / M-B step 2c).

Recharacterizes the incident corridor for `game_semantic_profile` (Option B:
partial frustration-only idle recovery + hearth disabled, scarcity restored) now
that the S3 social gap is closed. Recovery is fixed BY the profile, so the
stability sweep's recovery on/off axis collapses; we vary transducer intensity x
catalog richness over the three canonical probe plans. Scarcity is meaningful
again here, so the richness axis is the headline (thin should now exceed rich).

Outputs: experiments/out/g0_semantic/<cell>/<plan>/{trace,session,metrics}.

Usage: python -m experiments.g0_semantic_sweep [--quick]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from inn import metrics as M
from inn.config import load_inn_config
from inn.engine_surface import believable_day_layout
from inn.session import run_session
from experiments.g0_sweep import cell_metrics, verdict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "out" / "g0_semantic"
PROFILE = "game_semantic_profile"


def run_sweep(quick: bool = False) -> list[dict]:
    cfg = load_inn_config(ROOT / "inn.yaml")
    layout = believable_day_layout()
    sweep = cfg.g0["sweep"]
    corridor = tuple(cfg.g0["corridor"]["incidents_per_impulse_run"])
    scales = sweep["transducer_scale"][:2] if quick else sweep["transducer_scale"]
    richness = sweep["catalog_richness"]
    plans = ["impulse", "step", "control"]
    results = []
    t0 = time.time()
    for scale in scales:
        for rname, rmult in richness.items():
            cell = f"sem_s{scale}_{rname}"
            for plan in plans:
                out_dir = OUT / cell / plan
                run_session(cfg, plan, out_dir, transducer_scale=scale,
                            richness_mults=rmult, profile=PROFILE)
                records = M.load_records(out_dir / "trace.jsonl.gz")
                m = cell_metrics(records, cfg, layout)
                m.update(cell=cell, plan=plan, scale=scale, richness=rname,
                         profile=PROFILE)
                if plan == "impulse":
                    m["verdict"] = verdict(m, corridor)
                    m["in_corridor"] = corridor[0] <= m["incident_count"] <= corridor[1]
                (out_dir / "metrics.json").write_text(
                    json.dumps(m, indent=2), encoding="utf-8")
                results.append(m)
                print(f"[{time.time()-t0:7.1f}s] {cell}/{plan}: "
                      f"incidents={m['incident_count']} {m.get('verdict','')}",
                      flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sweep_results.json").write_text(json.dumps(results, indent=2),
                                            encoding="utf-8")
    return results


if __name__ == "__main__":
    run_sweep(quick="--quick" in sys.argv)
