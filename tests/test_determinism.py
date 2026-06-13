"""Determinism contract (CLAUDE.md section 4.4) + import contract (section 3)."""

import re
from pathlib import Path

from inn.config import load_inn_config
from inn.session import replay, run_session

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")
GOLDEN = ROOT / "tests" / "golden" / "canonical_session.sha256"


def test_same_session_same_hash(tmp_path):
    h1 = run_session(CFG, "impulse", tmp_path / "a", n_ticks=300)
    h2 = run_session(CFG, "impulse", tmp_path / "b", n_ticks=300)
    assert h1["trace_sha256"] == h2["trace_sha256"]


def test_replay_reproduces(tmp_path):
    h1 = run_session(CFG, "impulse", tmp_path / "a", n_ticks=300)
    h2 = replay(tmp_path / "a" / "session.json", ROOT / "inn.yaml", tmp_path / "b")
    assert h2["trace_sha256"] == h1["trace_sha256"]


def test_golden_canonical_session(tmp_path):
    """Full canonical 3-day control session against the frozen golden hash.
    Regenerate deliberately with: python -m experiments.regen_golden"""
    h = run_session(CFG, "control", tmp_path / "g")
    assert GOLDEN.is_file(), "golden hash missing — run experiments/regen_golden.py"
    assert h["trace_sha256"] == GOLDEN.read_text().strip()


def test_import_contract():
    """Only engine_surface.py may import engine internals (CLAUDE.md section 3)."""
    pat = re.compile(r"^\s*(from|import)\s+(engine|eval)[.\s]", re.M)
    offenders = []
    for py in (ROOT / "inn").glob("*.py"):
        if py.name == "engine_surface.py":
            continue
        if pat.search(py.read_text(encoding="utf-8")):
            offenders.append(py.name)
    assert offenders == []
