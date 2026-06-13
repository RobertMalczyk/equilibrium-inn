"""Society trace: complete per-tick record, gzipped JSONL.

One JSON object per tick. Completeness standard inherited from the engine —
full TickTrace fidelity per persona, plus presence, world states, the
transduction log with provenance, gap records, drops, offers, contention.
Float rounding matches the engine's serialization precision so trace hashes
are stable.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


class TraceWriter:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = gzip.open(self.path, "wt", encoding="utf-8", newline="\n")
        self._sha = hashlib.sha256()

    def emit(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False, sort_keys=False,
                          separators=(",", ":")) + "\n"
        self._sha.update(line.encode("utf-8"))
        self._fh.write(line)

    def close(self) -> str:
        """Close and return the SHA-256 over the uncompressed JSONL bytes."""
        self._fh.close()
        return self._sha.hexdigest()


def read_trace(path: str | Path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def trace_sha256(path: str | Path) -> str:
    sha = hashlib.sha256()
    with gzip.open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()
