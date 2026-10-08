"""Content-addressed cache wrapping any real ``TTSClient``, mirroring
``llm/cache.py::CachingLLMClient``'s own shape (a hobby-scale, by-hand-
inspectable cache needs no database). Unlike the LLM cache, the cached
content here is binary audio, not JSON -- stored as one ``.wav`` file
per cache entry rather than one flat index file.

A word's rendered audio depends on more than its own IPA text -- which
engine, and for eSpeak which voice/tones state, also determines the
output (see ``TTSClient.cache_identity``) -- so the cache key is
``(client.cache_identity(), ipa_text)``, not ``ipa_text`` alone. Never
wrap ``NoneTTSClient`` in this (it never writes a file; caching it is
pointless, not harmful, but callers should skip it anyway).
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from conlang_generator.speech.tts import TTSCapabilities, TTSClient


class CachingTTSClient:
    def __init__(self, wrapped: TTSClient, cache_dir: Path) -> None:
        self._wrapped = wrapped
        self._cache_dir = cache_dir

    def capabilities(self) -> TTSCapabilities:
        return self._wrapped.capabilities()

    def for_utterance(self, ipa_text: str) -> "TTSClient":
        return CachingTTSClient(self._wrapped.for_utterance(ipa_text), self._cache_dir)

    def cache_identity(self) -> str:
        return self._wrapped.cache_identity()

    def _cached_path(self, ipa_text: str) -> Path:
        key = hashlib.sha256(f"{self._wrapped.cache_identity()}|{ipa_text}".encode("utf-8")).hexdigest()
        return self._cache_dir / f"{key}.wav"

    def synthesize(self, ipa_text: str, output_path: Path) -> bool:
        cached_path = self._cached_path(ipa_text)
        if cached_path.is_file():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cached_path, output_path)
            return True
        if not self._wrapped.synthesize(ipa_text, output_path):
            return False
        cached_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output_path, cached_path)
        return True


__all__ = ["CachingTTSClient"]
