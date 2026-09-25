"""Comparison follow-ups: equatives ("as big as"), excessives ("too big"),
elatives ("very big"), degrees on adverbs, and a comparative standard marked by
any of ablative/locative/dative/genitive (once the language's cases are final).

Each degree is either a suffix on the adjective or a separate adverb word; the
draws come from one independent rng stream so earlier seeds do not shift."""

from __future__ import annotations

import random

DEGREE_LABELS = ("comparative", "superlative", "equative", "excessive", "elative")
DEGREE_WORDS = {
    "comparative": "more", "superlative": "most", "equative": "as", "excessive": "too", "elative": "very",
}
"""The English adverb each degree is written with when the language has no suffix for it."""
_STANDARD_CASES = (("ablative", 0.4), ("locative", 0.3), ("dative", 0.2), ("genitive", 0.1))
DEGREE_READING = {
    "comparative": "more {}", "superlative": "most {}", "equative": "as {} as", "excessive": "too {}",
    "elative": "very {}",
}
"""How a degree-marked adjective reads back in English."""


def roll_followups(rng: random.Random, grammar) -> dict[str, object]:
    """Every draw is always made, so the count never depends on the grammar."""
    equative_affix = rng.random() < 0.5
    excessive_affix = rng.random() < 0.5
    elative_affix = rng.random() < 0.4
    adverb_degree = rng.random() < 0.5
    switch_to_case = rng.random() < 0.25
    pick = rng.random()
    present = [(case, weight) for case, weight in _STANDARD_CASES if case in grammar.cases]
    strategy = grammar.comparative_strategy
    case = grammar.comparative_case
    if present:
        total = sum(weight for _, weight in present)
        cumulative = 0.0
        chosen = present[-1][0]
        for label, weight in present:
            cumulative += weight / total
            if pick < cumulative:
                chosen = label
                break
        if strategy == "case" or switch_to_case:
            strategy, case = "case", chosen
    return {
        "comparative_strategy": strategy,
        "comparative_case": case if strategy == "case" else "",
        "equative_marking": "affix" if equative_affix else "word",
        "excessive_marking": "affix" if excessive_affix else "word",
        "elative_marking": "affix" if elative_affix else "word",
        "adverb_degree": adverb_degree,
    }
