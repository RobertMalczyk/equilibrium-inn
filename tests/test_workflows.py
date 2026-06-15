"""CI/Pages workflow contracts (CLAUDE.md M-F). The engine pin must have ONE
source of truth (inn/engine_surface.py); the workflows derive it rather than
hardcoding a SHA. Pages deploys only on push to main; PRs are validated by CI."""

from pathlib import Path

from inn.engine_surface import PINNED_COMMIT

ROOT = Path(__file__).resolve().parents[1]
PAGES = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_no_hardcoded_engine_sha_in_workflows():
    # the pin lives only in inn/engine_surface.py; workflows must not duplicate it
    assert PINNED_COMMIT not in PAGES, "pages.yml hardcodes the engine SHA"
    assert PINNED_COMMIT not in CI, "ci.yml hardcodes the engine SHA"


def test_workflows_derive_the_pin():
    assert "engine_surface.py" in PAGES and "PINNED_COMMIT" in PAGES
    assert "engine_surface.py" in CI and "PINNED_COMMIT" in CI


def test_pages_deploys_only_on_push_not_pr():
    assert "pull_request" not in PAGES, "Pages must not deploy on PRs"
    assert "deploy-pages" in PAGES
    # the actual build/test gate runs on PRs in ci.yml
    assert "pull_request" in CI and "pytest" in CI
