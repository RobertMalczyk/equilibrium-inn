"""Deliberately regenerate the golden canonical-session hash.

Run only after a conscious decision that the trace must change
(inn.yaml edit, engine pin bump). CI asserts against the written hash.
"""

import tempfile
from pathlib import Path

from inn.config import load_inn_config
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    cfg = load_inn_config(ROOT / "inn.yaml")
    with tempfile.TemporaryDirectory() as td:
        header = run_session(cfg, "control", td)
    out = ROOT / "tests" / "golden" / "canonical_session.sha256"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header["trace_sha256"] + "\n", encoding="utf-8")
    print("golden:", header["trace_sha256"])
