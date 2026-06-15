"""Assemble the public showcase site under observatory/_site (CLAUDE.md M-F).

One DRY builder used both locally and by .github/workflows/pages.yml, so the
published site equals what you preview locally:

  python observatory/build_site.py
  python -m http.server -d observatory/_site    # preview at localhost:8000

Produces _site/:
  index.html        the landing page (observatory/landing.html)
  observatory.html  a self-contained static export of a canonical run
  cockpit.html      the Pyodide live cockpit (with the Verify-parity button)
  inn_bundle.zip    the cockpit's in-browser inn + pinned-engine bundle
  g2_reference.json the CPython parity reference (fetched by Verify parity)
  assets/           the visual pack (for the landing emblem)

The Pyodide runtime is NOT bundled here (CDN by default; see fetch_pyodide.py for
an optional fully-offline build). No simulation dynamics are touched.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SITE = HERE / "_site"
if str(ROOT) not in sys.path:           # allow `python observatory/build_site.py`
    sys.path.insert(0, str(ROOT))       # so `experiments` / `observatory` resolve

from inn.config import load_inn_config  # noqa: E402
from inn.observatory import export_html  # noqa: E402
from inn.session import run_session  # noqa: E402


def build_site() -> Path:
    import observatory.build_bundle as B
    from experiments.g2_parity import build_reference

    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)

    # 1) canonical run -> static export (the deterministic fallback)
    cfg = load_inn_config(ROOT / "inn.yaml")
    run_dir = HERE / "_run_impulse"
    run_session(cfg, "impulse", run_dir)
    export_html(run_dir, SITE / "observatory.html", stride=2)

    # 2) Pyodide cockpit (shares the render layer) + its bundle
    B.build_bundle()                       # observatory/inn_bundle.zip
    cockpit = B.build_index()              # observatory/index.html
    shutil.copy2(cockpit, SITE / "cockpit.html")
    shutil.copy2(HERE / "inn_bundle.zip", SITE / "inn_bundle.zip")

    # 3) parity reference fetched by the cockpit's Verify-parity button
    build_reference()
    shutil.copy2(HERE / "g2_reference.json", SITE / "g2_reference.json")

    # 4) landing page (site root) + assets for its emblem
    shutil.copy2(HERE / "landing.html", SITE / "index.html")
    shutil.copytree(HERE / "assets", SITE / "assets",
                    ignore=shutil.ignore_patterns("README.md"))

    # 5) optional custom domain: if observatory/CNAME exists, publish it
    cname = HERE / "CNAME"
    if cname.is_file():
        shutil.copy2(cname, SITE / "CNAME")
    return SITE


def main() -> None:
    site = build_site()
    files = sorted(p.name for p in site.iterdir())
    print(f"built {site}")
    print("  " + ", ".join(files))
    print("preview:  python -m http.server -d observatory/_site  -> http://localhost:8000/")


if __name__ == "__main__":
    main()
