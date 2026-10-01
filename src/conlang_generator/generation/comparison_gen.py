"""Comparison follow-ups: equatives ("as big as"), excessives ("too big"),
elatives ("very big"), degrees on adverbs, and a comparative standard marked by
any of ablative/locative/dative/genitive (once the language's cases are final).

Each degree is either a suffix on the adjective or a separate adverb word; the
draws come from one independent rng stream so earlier seeds do not shift."""

from __future__ import annotations

import random

DEGREE_LABELS = (
    "comparative", "superlative", "equative", "excessive", "elative",
    "comparative_negative", "superlative_negative", "sufficiency",
)
DEGREE_WORDS = {
    "comparative": "more", "superlative": "most", "equative": "as", "excessive": "too", "elative": "very",
    "comparative_negative": "less", "superlative_negative": "least", "sufficiency": "enough",
}
"""The English adverb each degree is written with when the language has no suffix for it."""
_STANDARD_CASES = (("ablative", 0.4), ("locative", 0.3), ("dative", 0.2), ("genitive", 0.1))
DEGREE_READING = {
    "comparative": "more {}", "superlative": "most {}", "equative": "as {} as", "excessive": "too {}",
    "elative": "very {}", "comparative_negative": "less {}", "superlative_negative": "least {}",
    "sufficiency": "{} enough",
}
"""How a degree-marked adjective reads back in English -- "sufficiency" is the
one degree whose English word follows the adjective ("big enough"), not
precedes it."""


def roll_followups(rng: random.Random, grammar) -> dict[str, object]:
    """Every draw is always made, so the count never depends on the grammar.
    ``comparative_negative``/``superlative_negative`` ("less big"/"least big")
    deliberately reuse ``comparative_marking``/``superlative_marking`` rather
    than rolling their own strategy -- a language's comparative suffix marks
    "degree exists", not "more" specifically, so the same choice of
    affix-vs-word carries over to its negative counterpart the way English
    itself does (an "-er" suffix, but always the separate word "less", never
    a suffix, for the negative direction)."""
    equative_affix = rng.random() < 0.5
    excessive_affix = rng.random() < 0.5
    elative_affix = rng.random() < 0.4
    adverb_degree = rng.random() < 0.5
    switch_to_case = rng.random() < 0.25
    pick = rng.random()
    present = [(case, weight) for case, weight in _STANDARD_CASES if case in grammar.cases]
    strategy = grammar.comparative_strategy
    case = grammar.comparative_case
    total = sum(weight for _, weight in present) if present else 0.0
    if present:
        cumulative = 0.0
        chosen = present[-1][0]
        for label, weight in present:
            cumulative += weight / total
            if pick < cumulative:
                chosen = label
                break
        if strategy == "case" or switch_to_case:
            strategy, case = "case", chosen
    # New draws, added after every draw above so no existing seed shifts.
    sufficiency_affix = rng.random() < 0.4
    equative_pick = rng.random()
    equative_switch = rng.random() < 0.25
    equative_case = ""
    if present:
        equative_chosen = present[-1][0]
        cumulative = 0.0
        for label, weight in present:
            cumulative += weight / total
            if equative_pick < cumulative:
                equative_chosen = label
                break
        if equative_switch:
            equative_case = equative_chosen
    return {
        "comparative_strategy": strategy,
        "comparative_case": case if strategy == "case" else "",
        "equative_marking": "affix" if equative_affix else "word",
        "excessive_marking": "affix" if excessive_affix else "word",
        "elative_marking": "affix" if elative_affix else "word",
        "sufficiency_marking": "affix" if sufficiency_affix else "word",
        "adverb_degree": adverb_degree,
        "equative_standard_case": equative_case,
    }
