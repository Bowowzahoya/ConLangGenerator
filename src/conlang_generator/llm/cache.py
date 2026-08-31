"""Content-addressed cache wrapping any ``LLMClient``.

Stored as one flat JSON file -- inspectable by hand, no database needed at
hobby scale. Cache the outermost layer around cost tracking (see
``build_default_client`` in ``llm/__init__``-adjacent wiring) so a cache hit
never reaches the cost tracker and is never billed twice.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from conlang_generator.llm.base import LLMRequest, LLMResponse


class CachingLLMClient:
    def __init__(self, wrapped, cache_path: Path) -> None:
        self._wrapped = wrapped
        self._cache_path = cache_path
        self._cache: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if self._cache_path.exists():
            return json.loads(self._cache_path.read_text(encoding="utf-8"))
        return {}

    def _save(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps(self._cache, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @staticmethod
    def _key(request: LLMRequest) -> str:
        payload = "|".join(
            [
                request.model,
                request.system,
                request.prompt,
                str(request.max_tokens),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def complete(self, request: LLMRequest) -> LLMResponse:
        key = self._key(request)
        if key in self._cache:
            return LLMResponse(**self._cache[key], cached=True)

        response = self._wrapped.complete(request)
        stored = asdict(response)
        stored.pop("cached", None)
        self._cache[key] = stored
        self._save()
        return response
