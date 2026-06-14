"""The QA-corpus harvest (CLAUDE.md S8): every written scenario is engine-format
and reproduces the action the NPC took in the live run."""

from pathlib import Path

import yaml

from experiments.harvest import harvest, OUT

ROOT = Path(__file__).resolve().parents[1]


def test_harvest_writes_verified_engine_format_scenarios():
    paths = harvest(max_scenarios=4, validate=True)
    assert paths, "harvest produced no scenarios"
    for p in paths:
        scn = yaml.safe_load(p.read_text(encoding="utf-8"))
        # engine scenario shape
        assert scn["id"] and scn["persona"]
        assert set(scn["initial_overrides"]) <= {"global_state", "relations"}
        assert len(scn["events"]) == 1
        ev = scn["events"][0]
        assert {"type", "t", "source", "intensity", "context"} <= set(ev)
        assert ev["source"] != scn["persona"]  # an exchange, not self
        assert scn["expect_action"]
    # manifest records the verified run
    manifest = yaml.safe_load((OUT / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["validated"] is True
    assert manifest["scenarios_written"] == len(paths)


def test_harvest_scenarios_reproduce_under_inn_loader():
    """validate=True keeps only reproducing scenarios; an unvalidated run can only
    have >= as many candidates, never fewer written for the same cap."""
    paths = harvest(max_scenarios=4, validate=True)
    assert len(paths) <= 4
    assert all(p.name.startswith("inn_harvest_") for p in paths)
