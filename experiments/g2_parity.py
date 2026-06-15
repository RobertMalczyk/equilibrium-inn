"""G2 parity gate (CLAUDE.md §8): is a fixed session byte-identical between
CPython and the Pyodide cockpit? This computes the CPython REFERENCE for a fixed
~1000-tick session (full-trace SHA-256), writes g2_reference.json (consumed by the
cockpit's one-click "Verify parity" button), and produces the static fallback
Observatory — the artifact the G2-failure path mandates.

How parity is closed: in the cockpit, click "Verify parity" — it runs the SAME
fixed session in Pyodide and compares its trace SHA-256 to g2_reference.json.
Equal -> the live cockpit is blessed. Unequal -> the static export stays the
deterministic fallback. Final closure REQUIRES a real browser run (Pyodide), so
this CPython-side module only prepares the reference + fallback and the pure
status logic (tested below).

  python -m experiments.g2_parity
"""

from __future__ import annotations

import json
from pathlib import Path

from inn.config import load_inn_config
from inn.observatory import export_html
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]
OBS = ROOT / "observatory"
REFERENCE = OBS / "g2_reference.json"
N_TICKS = 1000
SEED = 7
PLAN = "control"
PROFILE = "game_semantic_profile"


def parity_status(expected: str | None, actual: str | None) -> dict:
    """Pure status model for the parity check (shared shape for UI + tests).
    Never blesses Pyodide unless the SHAs match exactly."""
    if not expected or not actual:
        return {"status": "error", "expected": expected, "actual": actual,
                "message": "⚠️ error running parity check"}
    if expected == actual:
        return {"status": "passed", "expected": expected, "actual": actual,
                "message": "✅ CPython and Pyodide outputs match — live mode blessed"}
    return {"status": "failed", "expected": expected, "actual": actual,
            "message": "❌ mismatch; the static export remains the blessed path"}


def build_reference(out_dir: Path | None = None) -> dict:
    """Run the fixed CPython session and write g2_reference.json. Deterministic."""
    cfg = load_inn_config(ROOT / "inn.yaml")
    out_dir = out_dir or (OBS / "_g2_ref")
    header = run_session(cfg, PLAN, out_dir, seed=SEED, n_ticks=N_TICKS, profile=PROFILE)
    ref = {
        "n_ticks": N_TICKS, "seed": SEED, "probe_plan": PLAN, "profile": PROFILE,
        "engine_commit": header["engine_commit"],
        "inn_yaml_sha256": header["inn_yaml_sha256"],
        "trace_sha256": header["trace_sha256"],
    }
    REFERENCE.parent.mkdir(parents=True, exist_ok=True)
    REFERENCE.write_text(json.dumps(ref, indent=2), encoding="utf-8")
    return ref


def ensure_reference() -> dict:
    """Return the reference dict, building it (and g2_reference.json) if absent."""
    if REFERENCE.is_file():
        return json.loads(REFERENCE.read_text(encoding="utf-8"))
    return build_reference()


def main() -> None:
    out = OBS / "_g2_ref"
    ref = build_reference(out)
    fallback = export_html(out, OBS / "g2_fallback.html")
    print("CPython reference (the cockpit compares its same-session SHA to this):")
    print(json.dumps(ref, indent=2))
    print(f"\nstatic fallback Observatory: {fallback}")
    print("parity status: REFERENCE READY — click 'Verify parity' in the cockpit "
          "(a real browser run) to close G2.")


if __name__ == "__main__":
    main()
