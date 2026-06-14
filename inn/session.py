"""Session log: the determinism tuple and replay.

A session is fully determined by (engine commit, inn.yaml hash, calibration
hashes, seed, ordered injected-event log) — CLAUDE.md section 4.4. run_session
writes the header + the society trace and returns the trace SHA-256; replaying
the same header must reproduce the identical hash.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from inn.config import InnConfig, load_inn_config
from inn.engine_surface import ENGINE_ROOT, PINNED_COMMIT, believable_day_layout
from inn.loop import InnLoop
from inn.trace import TraceWriter

_CALIBRATION_FILES = [
    "calibration/defaults.yaml",
    "calibration/calibrated_layer1.yaml",
    "calibration/calibrated_layer2.yaml",
    "calibration/calibrated_recovery.yaml",
    "calibration/calibrated_timescale.yaml",
]


def calibration_hashes() -> dict[str, str]:
    out = {}
    for rel in _CALIBRATION_FILES:
        p = ENGINE_ROOT / rel
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def run_session(cfg: InnConfig, probe_plan: str, out_dir: str | Path,
                seed: int | None = None,
                transducer_scale: float | None = None,
                richness_mults: dict | None = None,
                persona_loader=None,
                n_ticks: int | None = None,
                profile: str | None = None) -> dict:
    """Run one session; write session.json + trace.jsonl.gz; return the header
    (including the resulting trace sha256)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seed = cfg.g0["seed"] if seed is None else seed
    layout = believable_day_layout()
    n_ticks = n_ticks or cfg.days * layout["day_ticks"]

    writer = TraceWriter(out_dir / "trace.jsonl.gz")
    loop = InnLoop(cfg, seed=seed, probe_plan=probe_plan, trace=writer,
                   transducer_scale=transducer_scale,
                   richness_mults=richness_mults,
                   persona_loader=persona_loader,
                   profile=profile)
    loop.run(n_ticks)
    sha = writer.close()

    header = {
        "engine_commit": PINNED_COMMIT,
        "inn_yaml_sha256": cfg.yaml_sha256,
        "calibration_hashes": calibration_hashes(),
        "seed": seed,
        "probe_plan": probe_plan,
        "n_ticks": n_ticks,
        "transducer_scale": transducer_scale,
        "richness_mults": richness_mults,
        "profile": profile,
        "layout": {k: layout[k] for k in ("dt", "day_ticks", "waking_ticks")},
        "injected_events": [],  # player verbs append here in the CLI milestone
        "trace_sha256": sha,
    }
    (out_dir / "session.json").write_text(
        json.dumps(header, indent=2), encoding="utf-8")
    return header


def replay(session_path: str | Path, inn_yaml: str | Path,
           out_dir: str | Path) -> dict:
    """Re-run a session from its header; caller compares trace_sha256."""
    header = json.loads(Path(session_path).read_text(encoding="utf-8"))
    cfg = load_inn_config(inn_yaml)
    if cfg.yaml_sha256 != header["inn_yaml_sha256"]:
        raise ValueError("inn.yaml has changed since the session was recorded")
    if header["engine_commit"] != PINNED_COMMIT:
        raise ValueError("engine commit differs from the session header")
    return run_session(cfg, header["probe_plan"], out_dir, seed=header["seed"],
                       transducer_scale=header["transducer_scale"],
                       richness_mults=header["richness_mults"],
                       n_ticks=header["n_ticks"],
                       profile=header.get("profile"))
