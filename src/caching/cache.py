"""Content-addressed cache for model responses.

Every live API response is written to disk keyed by a hash of the *full*
request (model, prompt, system instruction, decoding parameters, repetition
index). Re-running the experiment therefore costs zero API calls, which is what
makes a 250-call budget compatible with an iterative analysis workflow.

The cache is committed to the repository on purpose: it is the raw
experimental record, and it lets a reader reproduce every number in the report
without a key and without spending quota. The API key is never part of the
cache key and is never written to disk.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


class ResponseCache:
    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0
        self.writes = 0
        self.stale_failures = 0
        self.rejected_writes = 0

    @staticmethod
    def make_key(request: dict[str, Any]) -> str:
        """Stable hash over the request. Key material must never be included."""
        forbidden = {"api_key", "key", "authorization", "token"}
        clean = {k: v for k, v in request.items() if k.lower() not in forbidden}
        blob = json.dumps(clean, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        # shard by first two chars to keep directory listings small
        d = self.cache_dir / key[:2]
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        p = self._path(key)
        if not p.exists():
            self.misses += 1
            return None
        try:
            with p.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (json.JSONDecodeError, OSError):
            # A corrupt entry must not silently poison the experiment.
            self.misses += 1
            return None
        # A failed call is not experimental data. Older revisions cached
        # failures and replayed them here as ordinary hits, so a rerun after a
        # bad run (expired key, transient 5xx, a retired model) would silently
        # serve those failures as if they were model output, with no live call
        # and no budget spent to reveal the problem. Entries are now written
        # only on success, and any non-ok entry left over from an older run is
        # treated as a miss so the call is re-issued for real.
        if not payload.get("ok", False):
            self.stale_failures += 1
            self.misses += 1
            return None
        self.hits += 1
        return payload

    def put(self, key: str, value: dict[str, Any]) -> None:
        # Only successful responses are experimental data, so only they are
        # persisted. Writing failures would make a rerun reproduce the failure
        # from disk instead of retrying it. Callers may pass a failure through
        # unconditionally; it is dropped here rather than at each call site.
        if not value.get("ok", False):
            self.rejected_writes += 1
            return
        p = self._path(key)
        # atomic write so an interrupted run cannot leave a half-written entry
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(value, fh, indent=2, sort_keys=True)
            os.replace(tmp, p)
            self.writes += 1
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def stats(self) -> dict[str, int]:
        return {"cache_hits": self.hits, "cache_misses": self.misses,
                "cache_writes": self.writes,
                "stale_failure_entries": self.stale_failures,
                "rejected_failure_writes": self.rejected_writes}
