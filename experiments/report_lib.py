"""Shared helpers for the M-D validation reports (CLAUDE.md §7, M-D §4).

Reports read the society trace and answer the validation questions
(boredom->seeking, activity->fatigue, rest/sleep->recovery, scarcity,
persona contrast). Trace-only reports load a cached trace (running one canonical
session if absent); scarcity/contrast run their own seeded sessions. No dynamics
are tuned — a mismatch is a FINDING (registers/m_d.yaml), not a fix here.

experiments/ is exempt from the inn import contract (only inn/*.py is bound).
"""

from __future__ import annotations

from pathlib import Path

from inn import metrics as M
from inn.config import load_inn_config
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "out" / "g0" / "reports"
CFG = load_inn_config(ROOT / "inn.yaml")
CAST = [c.id for c in CFG.cast]

# Richness presets reuse the frozen G0 sweep axis (inn.yaml g0.sweep).
RICHNESS = CFG.g0["sweep"]["catalog_richness"]


def canonical_trace(plan: str = "impulse") -> list[dict]:
    """Load a cached canonical trace, running one session if it is missing.
    Deterministic (seed + profile from cfg)."""
    out = OUT / f"_trace_{plan}"
    trace = out / "trace.jsonl.gz"
    if not trace.is_file():
        run_session(CFG, plan, out)
    return M.load_records(trace)


def run_trace(plan: str, richness: dict | None, tag: str) -> list[dict]:
    out = OUT / f"_run_{tag}"
    run_session(CFG, plan, out, richness_mults=richness)
    return M.load_records(out / "trace.jsonl.gz")


def write_md(name: str, lines: list[str]) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p
