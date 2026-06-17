"""Lossless scenario dump + replay (CLAUDE.md M-J).

A *scenario* is the complete, self-contained set of INPUTS needed to reproduce a
run bit-for-bit later — for deep debugging. It deliberately contains NO simulation
results (no trace, no result SHA): only parameters and inputs.

Unlike session.json (which references inn.yaml by hash), a scenario EMBEDS the full
inn.yaml content, so it still reproduces even after the repo's inn.yaml has moved
on. Replay rebuilds the config from the embedded content and runs the exact same
loop; the caller can compare the resulting trace SHA to confirm reproduction.

  python -m inn.scenario replay <scenario.json> -o <out_dir>

Hard rules: pure over inputs; reproduction runs the normal loop; engine consumed
read-only at the pinned commit (replay refuses a different engine/calibration).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from inn.config import InnConfig, load_inn_config
from inn.engine_surface import PINNED_COMMIT
from inn.intervention import ControlState
from inn.session import calibration_hashes, run_session

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_VERSION = 1


def dump_scenario(cfg: InnConfig, *, seed: int, probe_plan: str, n_ticks: int,
                  profile: str | None = None, transducer_scale: float | None = None,
                  richness_mults: dict | None = None,
                  burst_overlay: bool | None = None,
                  resolution_factor: float = 1.0,
                  control: ControlState | None = None,
                  injected_events: list[dict] | None = None,
                  inn_yaml_path: str | Path | None = None) -> dict:
    """Build a portable, input-only scenario dict. Embeds the exact inn.yaml so the
    run reproduces independently of the current repo state. Raises if the on-disk
    inn.yaml does not match the loaded config (a mismatched dump would be a lie)."""
    inn_yaml_path = Path(inn_yaml_path) if inn_yaml_path else ROOT / "inn.yaml"
    raw = inn_yaml_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != cfg.yaml_sha256:
        raise ValueError("inn.yaml on disk does not match the loaded config — "
                         "cannot dump a faithful scenario")
    return {
        "scenario_version": SCENARIO_VERSION,
        "kind": "equilibrium-inn-scenario",
        "engine_commit": PINNED_COMMIT,
        "inn_yaml": raw.decode("utf-8"),
        "inn_yaml_sha256": sha,
        "calibration_hashes": calibration_hashes(),
        "seed": int(seed),
        "probe_plan": probe_plan,
        "n_ticks": int(n_ticks),
        "profile": profile,
        "transducer_scale": transducer_scale,
        "richness_mults": richness_mults,
        "burst_overlay": burst_overlay,
        "resolution_factor": resolution_factor,
        "control": ({"subject": control.subject, "mode": control.mode}
                    if control is not None and control.subject else None),
        "injected_events": list(injected_events or []),
        # NOTE: intentionally NO trace and NO trace_sha256 — inputs only.
    }


def replay_scenario(scenario: dict | str | Path, out_dir: str | Path,
                    check_calibration: bool = True) -> dict:
    """Reproduce a scenario by running the normal loop from its embedded inputs.
    Returns the run header (incl. the resulting trace_sha256, for verification)."""
    if isinstance(scenario, (str, Path)):
        scenario = json.loads(Path(scenario).read_text(encoding="utf-8"))
    if scenario.get("engine_commit") != PINNED_COMMIT:
        raise ValueError("scenario engine_commit differs from the seam pin — "
                         "check out the matching engine before replaying")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # materialize the embedded inn.yaml and load from it (portable: independent of
    # the repo's current inn.yaml)
    yml = out_dir / "inn.yaml"
    # write BYTES (not write_text) so platform newline translation can't alter the
    # content and break the sha256 round-trip
    yml.write_bytes(scenario["inn_yaml"].encode("utf-8"))
    cfg = load_inn_config(yml)
    if cfg.yaml_sha256 != scenario["inn_yaml_sha256"]:
        raise ValueError("embedded inn.yaml failed its own sha256 check (corrupt dump)")
    if check_calibration and calibration_hashes() != scenario.get("calibration_hashes"):
        raise ValueError("engine calibration differs from the scenario — replay would "
                         "not reproduce; pass check_calibration=False to override")

    c = scenario.get("control")
    control = ControlState(subject=c["subject"], mode=c.get("mode", "manual")) if c else None
    return run_session(
        cfg, scenario["probe_plan"], out_dir, seed=scenario["seed"],
        transducer_scale=scenario.get("transducer_scale"),
        richness_mults=scenario.get("richness_mults"),
        n_ticks=scenario["n_ticks"], profile=scenario.get("profile"),
        control=control, interventions=scenario.get("injected_events"),
        burst_overlay=scenario.get("burst_overlay"),
        resolution_factor=scenario.get("resolution_factor", 1.0))


def main(argv: list[str] | None = None) -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Replay a lossless equilibrium-inn scenario dump.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("replay", help="reproduce a scenario into an output dir")
    rp.add_argument("scenario", help="scenario .json file")
    rp.add_argument("-o", "--out", default="scenario_replay")
    rp.add_argument("--no-check-calibration", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "replay":
        header = replay_scenario(args.scenario, args.out,
                                 check_calibration=not args.no_check_calibration)
        print(f"replayed -> {args.out}")
        print(f"trace_sha256: {header['trace_sha256']}")


if __name__ == "__main__":
    main()
