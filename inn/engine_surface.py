"""Sole import seam between the inn and equilibrium-engine.

Contract (CLAUDE.md section 3): the inn consumes the engine only through its
public surface, at a pinned revision. Every other inn module imports engine
symbols from HERE, never from ``engine.*`` / ``eval.*`` directly — enforced by
tests/test_contract.py.

The engine's ``eval`` package is not installable (no __init__.py); the engine
runs from a source checkout with its root on sys.path. We therefore pin by
commit SHA, verified at import time.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1] / "equilibrium-engine"
PINNED_COMMIT = "311be038b5e8ee7e0ad931ea66f9f896c21be9a9"  # S2-S4 dt resolution_factor (refines dt; guarded no-op at 1.0) + decoupled refractory edge (off by default)


def _engine_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(ENGINE_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        # No git/subprocess (e.g. the Observatory running under Pyodide-in-WASM):
        # trust a `.engine_commit` sentinel written into the bundle by
        # observatory/build_bundle.py from the REAL git rev-parse at bundle time.
        # The engine checkout itself is never written (hard rule 0.1); only the
        # bundled copy carries this file.
        sentinel = ENGINE_ROOT / ".engine_commit"
        if sentinel.is_file():
            return sentinel.read_text(encoding="utf-8").strip()
        raise


def verify_pin() -> str:
    """Return the engine commit, raising if it differs from the pin."""
    commit = _engine_commit()
    if commit != PINNED_COMMIT:
        raise RuntimeError(
            f"engine at {ENGINE_ROOT} is {commit}, pinned {PINNED_COMMIT}; "
            "update the pin deliberately (CLAUDE.md section 3) or check out the tag"
        )
    return commit


if not ENGINE_ROOT.is_dir():
    raise RuntimeError(f"engine checkout not found at {ENGINE_ROOT}")
verify_pin()
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

# Public surface re-exports (noqa: imports require the path insertion above).
from engine.simulation import tick  # noqa: E402
from engine.schema import (  # noqa: E402
    ActionKind,
    ActionSelection,
    Mode,
    PersonaConfig,
    PersonaRuntime,
    RawEvent,
    StateDelta,
)
from engine.schema import (  # noqa: E402
    GLOBAL_STATES,
    RELATION_DIMS,
)
from engine.runtime import init_runtime  # noqa: E402
from engine.yaml_io import load_persona  # noqa: E402
from eval.calibrated import (  # noqa: E402
    believable_day_layout,
    burst_overrides,
    load_eval_persona_timescale,
    timescale_overrides,
)
# Narration vocabulary — sanctioned public surface (CLAUDE.md section 3): the
# deterministic, de-biased display tables the chronicle/CLI render with (never
# an LLM). DISPLAY/WHO = persona display names; REACTIVE_TIERS = action -> tiered
# observable phrases by selection score.
from eval.render_narration import (  # noqa: E402
    DISPLAY,
    REACTIVE_TIERS,
    WHO,
)

# The mapper's perceivable-event vocabulary (CLAUDE.md section 2). Events of
# any other type are invisible to personas; the transducer may only emit these.
PERCEIVABLE_EVENTS: tuple[str, ...] = (
    "food_given", "insult", "help", "command", "nightfall", "weather", "activity",
    # Social Event Mapper Pack (engine 0b7df59): three negative-but-not-insult
    # relational events, each its own channel. These let the S3 declared gap close.
    "cold_reply", "refusal", "complaint",
)

# The complete set of action ids the engine's action selector can place in
# ActionSelection.action at the pinned commit (3dcf4a3). Derived from
# engine/action_selector.py (literal returns: "neutral", "sleep",
# "seek_stimulus") and calibration/defaults.yaml drives + reactive potentials
# (the proactive/reactive `name` values and BUSY `active_action`s). The inn's
# transducer table MUST account for every one of these — as a transduced row,
# a declared gap, or a silent (no-social-surface) action — enforced at config
# load (config.load_inn_config). RE-VERIFY this set whenever the engine pin is
# bumped: a new selectable action that is not listed here will slip through the
# transducer untraced (this is the regression the coverage gate exists to stop).
ENGINE_ACTIONS: frozenset[str] = frozenset({
    # default / no-op / sleep
    "neutral", "sleep",
    # proactive drives (and the BUSY active_actions they sustain)
    "seek_stimulus", "rest", "self_activity", "external", "command_other",
    # reactive (command/affront/kindness gated)
    "outburst", "cold_response", "complain", "cooperate", "refuse",
    "positive_response",
})

__all__ = [
    "ENGINE_ROOT",
    "PERCEIVABLE_EVENTS",
    "ENGINE_ACTIONS",
    "GLOBAL_STATES",
    "RELATION_DIMS",
    "PINNED_COMMIT",
    "verify_pin",
    "tick",
    "ActionKind",
    "ActionSelection",
    "StateDelta",
    "Mode",
    "PersonaConfig",
    "PersonaRuntime",
    "RawEvent",
    "load_persona",
    "init_runtime",
    "believable_day_layout",
    "load_eval_persona_timescale",
    "timescale_overrides",
    "burst_overrides",
    "DISPLAY",
    "REACTIVE_TIERS",
    "WHO",
]
