"""Assembles the LLM client stack: cache(cost_tracker(real_client)).

The cache sits outermost so a cache hit is never recorded as spend.
"""

from __future__ import annotations

from pathlib import Path

import dotenv

from conlang_generator.llm.anthropic_client import AnthropicClient
from conlang_generator.llm.base import LLMClient
from conlang_generator.llm.cache import CachingLLMClient
from conlang_generator.llm.cost_tracker import CostTracker, CostTrackingLLMClient
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.llm.pricing import DEFAULT_MODEL

DEFAULT_CACHE_DIR = Path(".cache")


def build_llm_client(
    kind: str = "fake",
    cache_dir: Path = DEFAULT_CACHE_DIR,
    api_key: str | None = None,
) -> LLMClient:
    if kind == "fake":
        real: LLMClient = FakeLLMClient()
    elif kind == "anthropic":
        if api_key is None:
            # Populates os.environ from a local .env file (repo root or any
            # parent directory), without overriding a real env var that's
            # already set -- anthropic.Anthropic(api_key=None) itself then
            # reads ANTHROPIC_API_KEY from os.environ, same as always. A
            # no-op when no .env exists (the common case for anyone with
            # the key set the ordinary way).
            dotenv.load_dotenv()
        real = AnthropicClient(api_key=api_key)
    else:
        raise ValueError(f"unknown LLM client kind: {kind!r}")

    tracker = CostTracker(cache_dir / "cost_ledger.jsonl")
    tracked = CostTrackingLLMClient(real, tracker)
    return CachingLLMClient(tracked, cache_dir / "llm_cache.json")


__all__ = ["build_llm_client", "DEFAULT_MODEL", "DEFAULT_CACHE_DIR"]
