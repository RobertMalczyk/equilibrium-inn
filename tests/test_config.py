from pathlib import Path

import pytest

from inn.config import load_inn_config

ROOT = Path(__file__).resolve().parents[1]


def test_loads_and_validates():
    cfg = load_inn_config(ROOT / "inn.yaml")
    assert cfg.days == 3
    assert len(cfg.cast) == 7
    assert cfg.cast_order["wojslaw"] == 0  # cast order = contention tiebreak
    assert cfg.transducer.rows["outburst"].as_event == "insult"
    assert cfg.transducer.rows["outburst"].floor == 0.30
    # S3 gap closed: the three negative social actions are now real rows.
    assert cfg.transducer.declared_gaps == ()
    assert cfg.transducer.rows["refuse"].as_event == "refusal"
    assert cfg.transducer.rows["cold_response"].as_event == "cold_reply"
    assert cfg.transducer.rows["complain"].as_event == "complaint"
    assert cfg.probes["impulse"][0].target == "halgrim"
    assert len(cfg.yaml_sha256) == 64


def test_rejects_unknown_keys(tmp_path):
    src = (ROOT / "inn.yaml").read_text(encoding="utf-8")
    bad = tmp_path / "inn.yaml"
    bad.write_text(src + "\nbogus_section: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="bogus_section"):
        load_inn_config(bad)


def test_rejects_non_perceivable_transduction(tmp_path):
    src = (ROOT / "inn.yaml").read_text(encoding="utf-8")
    bad = tmp_path / "inn.yaml"
    bad.write_text(src.replace("{as: insult, floor: 0.30", "{as: refused, floor: 0.30"),
                   encoding="utf-8")
    with pytest.raises(ValueError, match="not perceivable"):
        load_inn_config(bad)


# -- world.provoking_event_types (config-driven provocation set) -------------

def test_provoking_event_types_loaded():
    """The configured set is loaded verbatim and is exactly the documented five."""
    cfg = load_inn_config(ROOT / "inn.yaml")
    assert cfg.provoking_event_types == (
        "insult", "command", "cold_reply", "refusal", "complaint")


def test_provoking_event_types_defaults_when_world_block_absent(tmp_path):
    """Omitting the `world` block falls back to the historical safe default
    (insult + command only) — never silently empty, never silently expanded."""
    src = (ROOT / "inn.yaml").read_text(encoding="utf-8")
    i = src.index("\nworld:")
    j = src.index("\nworld_states:")
    bad = tmp_path / "inn.yaml"
    bad.write_text(src[:i] + src[j:], encoding="utf-8")
    cfg = load_inn_config(bad)
    assert cfg.provoking_event_types == ("insult", "command")


def test_provoking_event_types_rejects_non_perceivable(tmp_path):
    """An unknown / non-perceivable event name fails validation loudly rather
    than silently never provoking."""
    src = (ROOT / "inn.yaml").read_text(encoding="utf-8")
    bad = tmp_path / "inn.yaml"
    bad.write_text(
        src.replace("[insult, command, cold_reply, refusal, complaint]",
                    "[insult, command, bogus_event]"),
        encoding="utf-8")
    with pytest.raises(ValueError, match="non-perceivable type"):
        load_inn_config(bad)
