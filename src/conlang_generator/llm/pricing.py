"""Hardcoded $/token pricing, for cost estimates only (not billing-accurate).

Update these if Anthropic changes prices; there is no live lookup by design
(this is a hobby project and a network call here would be one more thing that
can fail during a cheap dry run).
"""

from __future__ import annotations

# (input $ / 1M tokens, output $ / 1M tokens)
PRICE_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-fable-5": (10.00, 50.00),
    "fake-llm": (0.0, 0.0),
}

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
"""Cheapest current model -- the sensible default for a cost-conscious hobby
project; override per call for harder creative tasks."""


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = PRICE_PER_MILLION_TOKENS.get(model, (0.0, 0.0))
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000
