"""M-F site build + offline-runtime helper. The Pages site is assembled by one
DRY builder; the Pyodide runtime is fetched on demand (not committed)."""

from pathlib import Path

from observatory import fetch_pyodide as F

ROOT = Path(__file__).resolve().parents[1]


def test_fetch_pyodide_logic(tmp_path):
    assert not F.core_present(tmp_path)             # empty dir
    for f in F.CORE:
        (tmp_path / f).write_text("x")
    assert F.core_present(tmp_path)                 # all core files now present
    assert F.VERSION == "0.26.2" and F.URL.endswith(".tar.bz2")


def test_build_site_smoke():
    from observatory.build_site import build_site
    site = build_site()
    names = {p.name for p in site.iterdir()}
    assert {"index.html", "observatory.html", "cockpit.html", "inn_bundle.zip",
            "g2_reference.json", "assets"} <= names
    landing = (site / "index.html").read_text(encoding="utf-8")
    assert "Equilibrium Inn Observatory" in landing
    for href in ("observatory.html", "cockpit.html",
                 "github.com/RobertMalczyk/equilibrium-inn"):
        assert href in landing, href
    cockpit = (site / "cockpit.html").read_text(encoding="utf-8")
    assert "Verify parity" in cockpit and "g2_reference.json" in cockpit
    assert "window.MODEL=" in (site / "observatory.html").read_text(encoding="utf-8")
