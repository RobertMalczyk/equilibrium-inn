"""Regression harness (CLAUDE.md §7, M-E): the canonical 3-day protocols frozen
like golden traces. A compact, deterministic metric fingerprint is computed for
each protocol (impulse / step / control) and compared against a committed golden;
metric diffs are the report. Re-run on every engine pin bump.

  python -m experiments.regression           # run + diff against the golden
  python -m experiments.regression --freeze   # re-baseline the golden (ritual)

The golden lives at tests/golden/regression_metrics.json and is asserted by
tests/test_regression.py.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from inn import metrics as M
from inn.config import load_inn_config
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "regression_metrics.json"
PROTOCOLS = ("impulse", "step", "control")


def compute_fingerprint(records: list[dict], cfg) -> dict:
    """A small deterministic metrics fingerprint of one run (CLAUDE.md §7
    families, condensed). Stable because the underlying trace is golden."""
    inc_actions = tuple(cfg.g0["incident_def"]["actions"])
    incs = M.incidents(records, inc_actions)
    cs = M.cascade_stats(incs)
    adh = M.routine_adherence(records)
    ent = M.action_entropy(records)

    def mean(d):
        return round(sum(d.values()) / len(d), 4) if d else 0.0

    return {
        "incidents": len(incs),
        "cascade_max_depth": cs["max_depth"],
        "cascade_max_breadth": cs["max_size"],
        "routine_adherence_mean": mean(adh),
        "action_entropy_mean": mean(ent),
        "offers": sum(len(r["offers"]) for r in records),
        "contention": sum(len(r["contention_losers"]) for r in records),
    }


def run_all() -> dict:
    cfg = load_inn_config(ROOT / "inn.yaml")
    out = {}
    for plan in PROTOCOLS:
        d = Path(tempfile.mkdtemp())
        run_session(cfg, plan, d)
        out[plan] = compute_fingerprint(M.load_records(d / "trace.jsonl.gz"), cfg)
    return out


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    fps = run_all()
    if "--freeze" in argv:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(fps, indent=2), encoding="utf-8")
        print(f"froze {GOLDEN}")
        print(json.dumps(fps, indent=2))
        return
    golden = json.loads(GOLDEN.read_text(encoding="utf-8")) if GOLDEN.is_file() else {}
    print("# Regression — engine fingerprints vs golden\n")
    for plan in PROTOCOLS:
        cur, ref = fps[plan], golden.get(plan, {})
        diffs = {k: (ref.get(k), v) for k, v in cur.items() if ref.get(k) != v}
        status = "OK" if not diffs else "CHANGED"
        print(f"## {plan}: {status}")
        for k, v in cur.items():
            mark = "" if ref.get(k) == v else f"   <- was {ref.get(k)}"
            print(f"  {k}: {v}{mark}")
        print()


if __name__ == "__main__":
    main()
