"""Engine vs baseline, side-by-side (CLAUDE.md §7, M-E): run the SAME canonical
protocols on the engine cast and the deliberately-fair baseline cast (schedule
automaton + trigger->bark), and report the metric families that distinguish a
living world from a schedule-with-barks. The litmus aimed at the industry standard.

  python -m experiments.baseline_compare      # writes experiments/out/g0/baseline/

Reads only traces (both casts emit the same society-trace schema), via inn.metrics
and the shared fingerprint in experiments.regression.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from inn import metrics as M
from inn import observe as O
from inn.baseline import run_baseline
from inn.config import load_inn_config
from inn.session import run_session
from experiments.regression import compute_fingerprint

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "out" / "g0" / "baseline"
PROTOCOLS = ("impulse", "step", "control")


def _budget_means(records, cast):
    agg = {}
    for p in cast:
        for k, v in O.time_budget(records, p).items():
            agg[k] = agg.get(k, 0.0) + v / len(cast)
    return {k: round(v, 3) for k, v in agg.items()}


def render() -> list[str]:
    cfg = load_inn_config(ROOT / "inn.yaml")
    cast = [c.id for c in cfg.cast]
    lines = ["# Engine vs baseline cast", "",
             "Same schedule, same world layer, same probes — only the NPC brain "
             "differs (engine vs schedule-automaton + trigger->bark).", ""]
    for plan in PROTOCOLS:
        de, db = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        run_session(cfg, plan, de)
        run_baseline(cfg, plan, db)
        re_, rb = M.load_records(de / "trace.jsonl.gz"), M.load_records(db / "trace.jsonl.gz")
        fe, fb = compute_fingerprint(re_, cfg), compute_fingerprint(rb, cfg)
        lines += [f"## {plan}", "",
                  "| metric | engine | baseline |", "|---|---|---|"]
        for k in fe:
            lines.append(f"| {k} | {fe[k]} | {fb[k]} |")
        be, bb = _budget_means(re_, cast), _budget_means(rb, cast)
        keys = sorted(set(be) | set(bb))
        lines += ["", "| time budget | engine | baseline |", "|---|---|---|"]
        for k in keys:
            lines.append(f"| {k} | {be.get(k, 0)} | {bb.get(k, 0)} |")
        lines.append("")
    lines += ["_Reading: a living world should show variety under repetition "
              "(higher action entropy), priming-driven incident clustering, and "
              "recovery — where the baseline is flat/triggered. A flat baseline is "
              "the control, not a defect._"]
    return lines


def main() -> None:
    lines = render()
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "comparison.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
