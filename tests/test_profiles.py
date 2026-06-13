"""Two-profile split (CLAUDE.md DEC-1): one inn.yaml, two instrument characters.

g0_stability_profile = the frozen hearth-stable base (empty overlay).
game_semantic_profile = Option B: partial frustration-only idle recovery + hearth
disabled (scarcity restored). Selection is explicit until the M-B audit ratifies
making semantic the loaded default.
"""

from pathlib import Path

import pytest

from inn.config import load_inn_config
from inn.economy import Economy
from inn.clock import Clock
from inn.engine_surface import believable_day_layout

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")


def test_profiles_loaded_and_default():
    assert set(CFG.profiles) == {"g0_stability_profile", "game_semantic_profile"}
    assert CFG.default_profile == "game_semantic_profile"


def test_stability_profile_is_an_empty_overlay():
    """The frozen profile must reproduce the bare base exactly (so its golden is
    unchanged): no override delta, no disabled activity."""
    assert CFG.resolved_engine_overrides("g0_stability_profile") == CFG.engine_overrides
    assert CFG.disabled_activities("g0_stability_profile") == frozenset()


def test_semantic_profile_overlay():
    base = CFG.engine_overrides["idle_recovery"]
    assert base == {"stress": 0.0, "anger": 0.0}             # base unchanged
    eo = CFG.resolved_engine_overrides("game_semantic_profile")["idle_recovery"]
    # frustration-only recovery added; stress/anger still pinned (DEC-2)
    assert eo == {"stress": 0.0, "anger": 0.0, "frustration": -0.010}
    assert CFG.engine_overrides["idle_recovery"] == base    # base not mutated


def test_semantic_profile_disables_hearth():
    assert CFG.disabled_activities("game_semantic_profile") == {"hearth_idle"}
    clock = Clock.from_layout(believable_day_layout())
    eco_stable = Economy(CFG, clock, disabled_activities=frozenset())
    eco_semantic = Economy(CFG, clock,
                           disabled_activities=CFG.disabled_activities("game_semantic_profile"))
    assert "hearth_idle" in eco_stable.sources
    assert "hearth_idle" not in eco_semantic.sources
    # every other activity survives
    assert set(eco_semantic.sources) == set(eco_stable.sources) - {"hearth_idle"}


def test_none_profile_is_bare_base():
    assert CFG.resolved_engine_overrides(None) == CFG.engine_overrides
    assert CFG.disabled_activities(None) == frozenset()


def test_unknown_profile_raises():
    with pytest.raises(ValueError, match="unknown profile"):
        CFG.resolved_engine_overrides("nope")


def test_rejects_unknown_disable_id(tmp_path):
    src = (ROOT / "inn.yaml").read_text(encoding="utf-8")
    bad = tmp_path / "inn.yaml"
    bad.write_text(src.replace("disable_activities: [hearth_idle]",
                               "disable_activities: [not_an_activity]"),
                   encoding="utf-8")
    with pytest.raises(ValueError, match="unknown id"):
        load_inn_config(bad)


def test_rejects_unknown_idle_recovery_state(tmp_path):
    src = (ROOT / "inn.yaml").read_text(encoding="utf-8")
    bad = tmp_path / "inn.yaml"
    bad.write_text(src.replace("idle_recovery: {frustration: -0.010}",
                               "idle_recovery: {bogus_state: -0.010}"),
                   encoding="utf-8")
    with pytest.raises(ValueError, match="not a global state"):
        load_inn_config(bad)


def test_rejects_default_naming_missing_profile(tmp_path):
    src = (ROOT / "inn.yaml").read_text(encoding="utf-8")
    bad = tmp_path / "inn.yaml"
    bad.write_text(src.replace("default: game_semantic_profile",
                               "default: ghost_profile"),
                   encoding="utf-8")
    with pytest.raises(ValueError, match="not a defined profile"):
        load_inn_config(bad)
