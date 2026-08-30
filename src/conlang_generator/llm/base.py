"""The provider-agnostic seam. Every LLM-backed feature talks to this
interface, never to a specific SDK -- ``generation``/``translation`` code
never imports ``anthropic`` directly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class LLMRequest:
    system: str
    prompt: str
    model: str
    max_tokens: int = 512
    temperature: float = 1.0
    purpose: str = "generic"
    """Cost-tracking tag, e.g. 'lexicon.propose_word' or 'translate.gloss'."""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str = "end_turn"
    cached: bool = False


class LLMClient(Protocol):
    def complete(self, request: LLMRequest) -> LLMResponse: ...
