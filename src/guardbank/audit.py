"""Tamper-evident audit log: SHA-256 hash-chained JSONL (SPEC §2.8).

Each entry stores the hash of the previous entry, so editing, inserting or deleting a
line breaks the chain from that line on. Raw user text is never stored: only its
length and SHA-256, so the log does not become a second copy of customer PII.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from guardbank.types import GuardResult

GENESIS = "0" * 64


def _canonical(entry: dict) -> str:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _entry_hash(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def _last_hash(path: Path) -> str:
    if not path.exists():
        return GENESIS
    last = GENESIS
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                last = json.loads(line)["hash"]
    return last


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._prev = _last_hash(self.path)

    def append(self, request_id: str, result: GuardResult, *, input_text: str | None = None) -> dict:
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "request_id": request_id,
            "stage": result.stage,
            "verdict": result.action.value,
            "detected": result.detected,
            "score": round(result.score, 4),
            "category": result.category,
            "latency_ms": round(result.latency_ms, 3),
            "details": result.details,
        }
        if input_text is not None:
            entry["input_len"] = len(input_text)
            entry["input_sha256"] = hashlib.sha256(input_text.encode("utf-8")).hexdigest()
        with self._lock:
            entry["prev_hash"] = self._prev
            entry["hash"] = _entry_hash(entry)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(_canonical(entry) + "\n")
            self._prev = entry["hash"]
        return entry


def verify(path: str | Path) -> int | None:
    """Return the 1-based line number of the first broken entry, or None if intact."""
    prev = GENESIS
    with Path(path).open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("prev_hash") != prev or entry.get("hash") != _entry_hash(entry):
                return lineno
            prev = entry["hash"]
    return None
