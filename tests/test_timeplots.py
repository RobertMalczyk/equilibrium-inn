"""M-J — Time Plots study page.

The page is pure observability over the society trace (hard rule 0.4): a model
builder + a shared Canvas render layer that serves BOTH the static plots.html and
a live panel in the Pyodide cockpit. These lock in the model shape the render layer
binds to, that the static export embeds all three protocols, that the cockpit page
still builds with the panel wired, and — critically — that none of this perturbs the
golden trace or the import contract (observability only; verified in test_determinism
too, asserted directly here for the M-J surface).
"""

import shutil
import subprocess
from pathlib import Path

from inn import metrics as M
from inn import timeplots as TP
from inn.config import load_inn_config
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")
NT = 320


def _records(tmp_path, plan="impulse"):
    run_session(CFG, plan, tmp_path, seed=7, n_ticks=NT)
    return M.load_records(tmp_path / "trace.jsonl.gz")


# 1 — model shape: every series is present and exactly as long as the run.
def test_model_series_shape(tmp_path):
    recs = _records(tmp_path)
    m = TP.build_plot_model(recs, CFG)
    assert m["n"] == len(recs)
    assert [c.id for c in CFG.cast] == m["cast"]
    states = TP.PERSONA_STATES_OPEN + TP.PERSONA_STATES_COLLAPSED
    for pid in m["cast"]:
        for st in states:
            assert len(m["series"][pid][st]) == m["n"]
    # parallel axis arrays are aligned with the series
    assert len(m["ticks"]) == len(m["day"]) == len(m["mins"]) == m["n"]
    # the high-signal facets are the open set; room_tension is a world series
    assert m["states_open"][0] == "anger"
    assert "room_tension" in m["world"] and m["world"]["room_tension"]


# 2 — incident markers are tiered: outburst = the spine, S3 events = near-misses.
def test_incident_markers_tiered(tmp_path):
    recs = _records(tmp_path)
    m = TP.build_plot_model(recs, CFG)
    tiers = {i["tier"] for i in m["incidents"]}
    assert tiers <= {"incident", "social"}
    for inc in m["incidents"]:
        assert (inc["tier"] == "incident") == (inc["action"] == "outburst")
        assert 0 <= inc["i"] < m["n"] and m["ticks"][inc["i"]] == inc["t"]


# 3 — relations: only directed pairs that actually moved are plotted; the rest are
#     summarized flat. Every moved channel exceeds the epsilon.
def test_relations_moved_filter(tmp_path):
    recs = _records(tmp_path)
    m = TP.build_plot_model(recs, CFG)
    rel = m["relations"]
    for e in rel["moved"]:
        assert max(e["series"]) - min(e["series"]) > TP.RELATION_EPSILON
        assert len(e["series"]) == rel["n_samples"]
    for e in rel["flat"]:
        assert "series" not in e and "value" in e


# 4 — color resolution: explicit inn.yaml colors win; a cast member without one
#     gets a deterministic generated fallback (never missing).
def test_color_resolution():
    colors = TP._resolve_colors(CFG)
    assert set(colors) == {c.id for c in CFG.cast}
    for c in CFG.cast:
        if c.color:
            assert colors[c.id] == c.color
        else:
            assert colors[c.id].startswith("hsl(")     # generated fallback
    # fallback alone covers a colorless cast deterministically
    ramp = TP._hue_ramp(["a", "b", "c"])
    assert ramp == TP._hue_ramp(["a", "b", "c"]) and len(set(ramp.values())) == 3


# 5 — developer CLI export smoke: a single self-contained file embedding the
#     render layer (single or multi-trace; multi adds a protocol selector). Not a
#     published site page (M-J ships time plots as a cockpit tab), but kept for
#     offline study of an arbitrary trace.
def test_dev_export_embeds_render_layer(tmp_path):
    dirs = {}
    for plan in ("impulse", "step", "control"):
        d = tmp_path / plan
        run_session(CFG, plan, d, seed=7, n_ticks=NT)
        dirs[plan] = d
    out = TP.export_html(dirs, tmp_path / "plots.html")
    html = out.read_text(encoding="utf-8")
    assert "<canvas" in html and "window.TimePlots" in html
    assert "data-tp-ov" in html and 'id="tp_proto"' in html
    for plan in ("impulse", "step", "control"):
        assert f'"{plan}"' in html


# 6 — the cockpit page builds the Time Plots as a TAB (subpage) of the SAME live
#     session, fed the live trace by renderPlotsLive (observability only).
def test_cockpit_index_wires_time_plots_tab():
    import observatory.build_bundle as B
    html = B.build_index().read_text(encoding="utf-8")
    assert 'id="tpc"' in html                      # the live plot view container
    assert "view_plots" in html and "view_obs" in html   # the two subpages
    assert "tab_plots" in html and "tpShowView" in html   # the tab switch
    assert "renderPlotsLive" in html               # driven each frontier change + on tab show
    assert "window.TPMODEL" in html                # live model the view binds to
    assert "import inn.timeplots as TP" in html     # the Python live builder is bundled


# 7 — observability only: building the plot model does NOT touch the trace, and the
#     module obeys the import contract (no engine internals).
def test_plot_model_is_pure_over_trace(tmp_path):
    recs = _records(tmp_path)
    import copy
    snapshot = copy.deepcopy(recs)
    TP.build_plot_model(recs, CFG)
    assert recs == snapshot                         # the trace is read, never mutated
    src = (ROOT / "inn" / "timeplots.py").read_text(encoding="utf-8")
    import re
    assert not re.search(r"^\s*(from|import)\s+(engine|eval)[.\s]", src, re.M)


# 7b — the render layer carries the incident-designation hover path (overview +
#      facets) bound to the provenance the model embeds.
def test_render_has_incident_hover():
    src = TP.PLOT_SCRIPT
    assert "incidentNear" in src and "showIncidentTip" in src
    assert "OUTBURST (incident)" in src and "provoked by" in src


# 7c — the hover-highlight selector (incident / values / both) is present and wired.
def test_render_has_hover_selector():
    assert "data-tp-hover" in TP.plot_body()
    src = TP.PLOT_SCRIPT
    assert "hoverMode" in src
    for mode in ("'values'", "'incident'", "'both'"):
        assert mode in src


# 8 — the shared render JS is syntactically valid (skipped if node is absent).
def test_render_js_syntax(tmp_path):
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node not available")
    js = tmp_path / "tp.js"
    js.write_text(TP.PLOT_SCRIPT, encoding="utf-8")
    r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
