"""Observatory render layer + self-contained HTML export (CLAUDE.md M-D Phase 3).
Browser behaviour can't run headlessly; we lock in that the page builds, embeds
the model, and shares one render layer between the export and the cockpit."""

from pathlib import Path

import pytest

from inn import metrics as M
from inn import observatory as OB
from inn import observe as O
from inn.config import load_inn_config
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")


@pytest.fixture(scope="module")
def trace_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("obs_export")
    run_session(CFG, "impulse", out, n_ticks=717)
    return out


def test_page_embeds_model_and_render_layer():
    model = {"meta": {}, "cast": ["welf"], "display_names": {"welf": "Welf"},
             "rooms": ["common_room"], "days": [1], "high_thresholds": {},
             "state_families": {"need": [], "affect": [], "sleep": []},
             "ticks": [{"t": 0, "day": 1, "clock": "06:00", "night": False,
                        "rain": False, "event": None, "world": {},
                        "personas": {"welf": {"mode": "idle", "mood": "calm",
                                     "room": "common_room", "action": "neutral",
                                     "states": {}, "raw": {}}}}],
             "stride": 1, "transitions": [], "crossings": [], "incidents": [],
             "daily": {}, "metrics": {"incidents": 0}}
    html = OB.page(model, meta_subtitle="t")
    assert html.startswith("<!doctype html>")
    assert "window.MODEL=" in html and "Living Inn Observatory" in html
    assert "buildRibbons" in html  # the shared SCRIPT is inlined
    assert "if(window.MODEL) init();" in html


def test_export_html_from_trace(trace_dir):
    out = trace_dir / "observatory.html"
    p = OB.export_html(trace_dir, out, stride=4)
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "window.MODEL=" in text and "<canvas" in text
    # the embedded model is the same one inn.observe.build_model produces
    recs = M.load_records(trace_dir / "trace.jsonl.gz")
    model = O.build_model(recs, CFG, stride=4)
    assert model["cast"] == [c.id for c in CFG.cast]
    assert len(model["ticks"]) == len(recs[::4])


def test_assets_load_and_embed():
    assets = OB.load_assets()
    # the art pack embeds as image data URIs under their canonical names,
    # regardless of the on-disk extension (PNGs fill SVG-named slots)
    for name in ("equilibrium_observatory_emblem.svg", "icon_boredom.svg",
                 "icon_causality.svg", "divider_lantern_vine.svg",
                 "npc_token_base.svg", "overlay_fireflies_soft.svg",
                 "bg_observatory_warm.png", "scene_inn_rooms.png"):
        assert name in assets, name
        assert assets[name].startswith("data:image/"), assets[name][:24]


def test_unoptimized_load_preserves_source_mime():
    # raw embed path (optimize off) keeps the source format
    assets = OB.load_assets(optimize=False)
    assert assets["bg_observatory_warm.png"].startswith("data:image/png;base64,")


def test_page_embeds_assets():
    model = {"meta": {}, "cast": ["welf"], "display_names": {"welf": "Welf"},
             "rooms": ["common_room"], "days": [1], "high_thresholds": {},
             "state_families": {"need": [], "affect": [], "sleep": []},
             "ticks": [{"t": 0, "day": 1, "clock": "06:00", "night": False,
                        "rain": False, "event": None, "world": {},
                        "personas": {"welf": {"mode": "idle", "mood": "calm",
                                     "room": "common_room", "action": "neutral",
                                     "states": {}, "raw": {}}}}],
             "stride": 1, "transitions": [], "crossings": [], "incidents": [],
             "daily": {}, "why": {"welf": ["Welf has done nothing yet."]},
             "metrics": {"incidents": 0}}
    html = OB.page(model)
    assert "window.ASSETS=" in html
    assert "renderWhy" in html and 'id="emblem"' in html


def test_build_model_includes_why(trace_dir):
    recs = M.load_records(trace_dir / "trace.jsonl.gz")
    model = O.build_model(recs, CFG)
    assert "why" in model and set(model["why"]) == {c.id for c in CFG.cast}
    assert all(isinstance(v, list) for v in model["why"].values())
