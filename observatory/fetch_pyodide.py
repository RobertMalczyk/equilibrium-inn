"""Fetch the Pyodide runtime locally for a fully-offline cockpit (CLAUDE.md M-F).

The Pyodide distribution is large (tens of MB) and is NOT committed to git. Run
this to download v0.26.2 into observatory/pyodide/; observatory/build_bundle.py
then detects the local runtime and uses it instead of the CDN. Idempotent and
safe to rerun. For release packaging, host the runtime via Git LFS or a GitHub
Release asset — never a raw git commit.

  python observatory/fetch_pyodide.py            # download if missing
  python observatory/fetch_pyodide.py --force    # re-download
  python observatory/fetch_pyodide.py --check    # report presence only
"""

from __future__ import annotations

import argparse
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

VERSION = "0.26.2"
URL = (f"https://github.com/pyodide/pyodide/releases/download/{VERSION}/"
       f"pyodide-{VERSION}.tar.bz2")
DEST = Path(__file__).resolve().parent / "pyodide"
# Core files the cockpit needs present after extraction.
CORE = ("pyodide.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")


def core_present(dest: Path = DEST) -> bool:
    return dest.is_dir() and all((dest / f).is_file() for f in CORE)


def fetch(force: bool = False) -> Path:
    if core_present() and not force:
        print(f"Pyodide already present at {DEST} (use --force to re-download).")
        return DEST
    DEST.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Pyodide {VERSION} (~tens of MB)…\n  {URL}")
    try:
        with tempfile.NamedTemporaryFile(suffix=".tar.bz2", delete=False) as tmp:
            urllib.request.urlretrieve(URL, tmp.name)
            archive = tmp.name
    except Exception as e:  # network/download failure -> clear, non-silent error
        raise SystemExit(f"download failed: {e}\nCheck connectivity or fetch the "
                         f"release asset manually into {DEST}.")
    print("Extracting…")
    with tarfile.open(archive, "r:bz2") as tf:
        members = tf.getmembers()
        # The tarball roots everything under a top-level 'pyodide/' dir.
        for m in members:
            parts = Path(m.name).parts
            if len(parts) >= 2 and parts[0] == "pyodide":
                m.name = str(Path(*parts[1:]))
                if m.name:
                    tf.extract(m, DEST)
    if not core_present():
        raise SystemExit(f"extraction incomplete: missing one of {CORE} in {DEST}")
    print(f"\nPyodide {VERSION} ready at {DEST}")
    print("Now rebuild the cockpit — it will use the local runtime (no CDN):")
    print("  python observatory/build_bundle.py")
    return DEST


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Fetch the Pyodide runtime locally.")
    ap.add_argument("--force", action="store_true", help="re-download even if present")
    ap.add_argument("--check", action="store_true", help="report presence and exit")
    args = ap.parse_args(argv)
    if args.check:
        print(f"pyodide present: {core_present()} ({DEST})")
        return
    fetch(force=args.force)


if __name__ == "__main__":
    main(sys.argv[1:])
