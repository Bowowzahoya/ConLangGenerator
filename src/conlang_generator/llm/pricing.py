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

TYPICAL_TOKENS: dict[str, tuple[int, int]] = {
    "classifier": (3300, 320),
    "word_selection": (1500, 60),
    "translation": (1500, 200),
}
"""(input, output) token counts typical of one call for each model-choice
task -- a ballpark for ``estimated_price``, not a measurement: most local
testing runs the free ``fake-llm`` backend, so the real cost ledger has
thin-to-zero coverage for any paid model today, and a hardcoded estimate
labeled as such is more honest than a ledger rollup that would silently
read as "0 samples." Taken from docs/DEFERRED.md's own ledger-sourced
figures (classify ~3.3k in / 0.3k out, translate plan ~1.5k in / 0.05-0.3k
out); ``"word_selection"`` is a flat guess -- its real cost scales with
candidate-list/vocabulary size, not captured by one fixed number (see
docs/LIMITATIONS.md)."""


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = PRICE_PER_MILLION_TOKENS.get(model, (0.0, 0.0))
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def estimated_price(model: str, task: str) -> float:
    """A rough per-call price for ``task`` ("classifier"/"word_selection"/
    "translation") on ``model``, from ``TYPICAL_TOKENS`` -- see its own
    docstring for why this is an estimate, not a measurement."""
    input_tokens, output_tokens = TYPICAL_TOKENS[task]
    return estimate_cost(model, input_tokens, output_tokens)
