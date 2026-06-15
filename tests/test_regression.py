"""Regression harness (CLAUDE.md M-E): the canonical protocols frozen like golden
traces. The engine's compact metric fingerprint per protocol must match the
committed golden — a guard that an engine pin bump (or any change) surfaces its
metric diffs deliberately, via `python -m experiments.regression --freeze`."""

import json
from pathlib import Path

import pytest

from experiments.regression import GOLDEN, PROTOCOLS, run_all

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def fingerprints():
    return run_all()


def test_golden_exists():
    assert GOLDEN.is_file(), "freeze it: python -m experiments.regression --freeze"


def test_fingerprints_match_golden(fingerprints):
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert set(golden) == set(PROTOCOLS)
    for plan in PROTOCOLS:
        assert fingerprints[plan] == golden[plan], (
            f"{plan} regression: {fingerprints[plan]} != golden {golden[plan]} "
            "(re-baseline deliberately with --freeze if this change is intended)")
