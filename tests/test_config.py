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
    assert "refuse" in cfg.transducer.declared_gaps
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
