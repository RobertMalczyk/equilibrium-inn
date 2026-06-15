"""G2 parity (CLAUDE.md M-F). The pure status model is tested here; full closure
needs a real in-browser Pyodide run (the cockpit's Verify-parity button). We also
assert the CPython reference is deterministic — the fixed session reproduces its
own SHA — so the cockpit has a stable target to match."""

from pathlib import Path

from inn.config import load_inn_config
from inn.session import run_session
from experiments import g2_parity as G

ROOT = Path(__file__).resolve().parents[1]


def test_parity_status_model():
    assert G.parity_status("abc", "abc")["status"] == "passed"
    assert G.parity_status("abc", "xyz")["status"] == "failed"
    assert G.parity_status("abc", None)["status"] == "error"
    assert G.parity_status(None, "abc")["status"] == "error"
    # never bless on mismatch
    assert "blessed" not in G.parity_status("a", "b")["message"].lower() or \
        "remains" in G.parity_status("a", "b")["message"].lower()


def test_reference_session_is_deterministic(tmp_path):
    """The fixed G2 session (same params as the cockpit's run_parity) reproduces
    its trace SHA — the stable reference the in-browser check compares against."""
    cfg = load_inn_config(ROOT / "inn.yaml")
    a = run_session(cfg, G.PLAN, tmp_path / "a", seed=G.SEED,
                    n_ticks=G.N_TICKS, profile=G.PROFILE)
    b = run_session(cfg, G.PLAN, tmp_path / "b", seed=G.SEED,
                    n_ticks=G.N_TICKS, profile=G.PROFILE)
    assert a["trace_sha256"] == b["trace_sha256"]
    assert G.parity_status(a["trace_sha256"], b["trace_sha256"])["status"] == "passed"
