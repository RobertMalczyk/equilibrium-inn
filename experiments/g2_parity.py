"""G2 parity gate (CLAUDE.md §8): is a fixed session byte-identical between
CPython and the Pyodide cockpit? This script computes the CPython REFERENCE for
a fixed ~1000-tick session (full-trace SHA-256) and produces the static fallback
Observatory — the artifact the G2-failure path mandates (a CPython-built model
embedded in the same render layer, so the cockpit stays presentation-ready even
if parity fails).

How parity is closed: run the SAME fixed session in the cockpit (Pyodide) and
compare its trace SHA-256 to g2_reference.json's `trace_sha256`. Equal -> the
live cockpit is trustworthy. Unequal -> ship observatory/g2_fallback.html.

Usage: python -m experiments.g2_parity
"""

from __future__ import annotations

import json
from pathlib import Path

from inn.config import load_inn_config
from inn.observatory import export_html
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]
OBS = ROOT / "observatory"
N_TICKS = 1000
SEED = 7
PLAN = "control"
PROFILE = "game_semantic_profile"


def main() -> None:
    cfg = load_inn_config(ROOT / "inn.yaml")
    out = OBS / "_g2_ref"
    header = run_session(cfg, PLAN, out, seed=SEED, n_ticks=N_TICKS, profile=PROFILE)
    ref = {
        "n_ticks": N_TICKS, "seed": SEED, "probe_plan": PLAN, "profile": PROFILE,
        "engine_commit": header["engine_commit"],
        "inn_yaml_sha256": header["inn_yaml_sha256"],
        "trace_sha256": header["trace_sha256"],
    }
    (OBS / "g2_reference.json").write_text(json.dumps(ref, indent=2), encoding="utf-8")
    fallback = export_html(out, OBS / "g2_fallback.html")
    print("CPython reference (compare the cockpit's same-session trace SHA to this):")
    print(json.dumps(ref, indent=2))
    print(f"\nstatic fallback Observatory: {fallback}")
    print("parity status: REFERENCE READY — confirm equality in-browser to pass G2.")


if __name__ == "__main__":
    main()
