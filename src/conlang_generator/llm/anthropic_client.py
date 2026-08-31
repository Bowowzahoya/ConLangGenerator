"""Thin wrapper over the Anthropic SDK. Only imported when the caller
explicitly asks for a real model; everything else in the package depends on
``llm.base.LLMClient`` instead of this module."""

from __future__ import annotations

import anthropic

from conlang_generator.llm.base import LLMRequest, LLMResponse


class AnthropicClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, request: LLMRequest) -> LLMResponse:
        # Sampling params (temperature/top_p/top_k) were removed from the
        # Messages API request shape entirely -- not just model-gated, see
        # anthropic.resources.messages.messages.Messages.create's signature.
        response = self._client.messages.create(
            model=request.model,
            max_tokens=request.max_tokens,
            system=request.system,
            messages=[{"role": "user", "content": request.prompt}],
        )
        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        return LLMResponse(
            text=text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason or "end_turn",
        )
