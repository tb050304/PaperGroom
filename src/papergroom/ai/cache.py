"""Disk cache for LLM responses.

Tuning the rules means re-running the pipeline over the same documents
repeatedly; that should not re-bill for identical requests. Entries are keyed
on the model and the exact request, so editing the prompt or the paragraph
text misses the cache and calls the API as usual.

The cache is best-effort: an unwritable directory degrades to no caching
rather than failing a run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ResponseCache:
    """A directory of ``<sha256>.json`` files holding one response each."""

    def __init__(self, directory: Path | str):
        self._dir = Path(directory)

    @staticmethod
    def _key(request: dict[str, Any]) -> str:
        payload = json.dumps(request, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, request: dict[str, Any]) -> str | None:
        path = self._dir / f"{self._key(request)}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))["content"]
        except (OSError, ValueError, KeyError):
            return None

    def put(self, request: dict[str, Any], content: str) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path = self._dir / f"{self._key(request)}.json"
            path.write_text(
                json.dumps({"content": content}, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass  # caching is an optimisation; never fail a run over it
