"""Reduplication as grammar: copying part of the stem to mark a cell.

A language may mark some cells -- the plural (``dog`` -> ``dogdog``), a habitual or progressive
aspect, an intensive degree -- by reduplicating the stem: ``full`` (the whole stem), ``initial_cv``
(the first consonant + vowel, as in Tagalog ``ta-tawa``), ``initial_syllable`` (the first
syllable with its coda) or ``final_syllable``. The copy is made from the stem before the
cell's ordinary affix is attached, so the two combine. Isolating languages reduplicate most.

One independent rng stream, drawn after the patterns."""

from __future__ import annotations

import random

from conlang_generator.core.grammar import GrammarProfile, MorphologicalType, Reduplication
from conlang_generator.generation import ipa_tokenizer

KINDS = (("full", 0.40), ("initial_cv", 0.25), ("initial_syllable", 0.20), ("final_syllable", 0.15))
CANDIDATE_CELLS = (
    "number_affixes/plural", "aspect_affixes/progressive", "aspect_affixes/habitual", "aspect_affixes/imperfective",
    "degree_affixes/elative", "degree_affixes/superlative",
)
_RATE = {
    MorphologicalType.ISOLATING: 0.22, MorphologicalType.AGGLUTINATIVE: 0.10,
    MorphologicalType.FUSIONAL: 0.05, MorphologicalType.POLYSYNTHETIC: 0.12,
}
CELL_POS = {
    "case_affixes": "noun", "number_affixes": "noun", "possession_affixes": "noun", "tense_affixes": "verb",
    "aspect_affixes": "verb", "mood_affixes": "verb", "voice_affixes": "verb", "degree_affixes": "adjective",
}
"""The part of speech that takes a cell of each inflectional field."""


def _pick_kind(roll: float) -> str:
    cumulative = 0.0
    for kind, weight in KINDS:
        cumulative += weight
        if roll < cumulative:
            return kind
    return KINDS[0][0]


def roll_reduplication(rng: random.Random, grammar: GrammarProfile) -> tuple[Reduplication, ...]:
    """The cells this language marks by reduplication and how (every draw always made). A cell that a
    root-and-pattern language already marks by a pattern is left to the pattern."""
    rate = _RATE.get(grammar.morphological_type, 0.2)
    rolls = [(rng.random(), rng.random()) for _ in CANDIDATE_CELLS]
    patterned = {p.cell for p in grammar.pattern_cells}
    found: list[Reduplication] = []
    for cell, (presence, kind_roll) in zip(CANDIDATE_CELLS, rolls):
        field, _, label = cell.partition("/")
        if cell in patterned or presence >= rate:
            continue
        if not any(a.label == label for a in getattr(grammar, field, ())):
            continue
        found.append(Reduplication(cell=cell, kind=_pick_kind(kind_roll)))
    return tuple(found)


def reduplicate(ipa: str, kind: str, known_symbols, vowel_symbols: frozenset[str]) -> str:
    """``ipa`` with the part ``kind`` names copied (unchanged when it has no vowel to anchor on)."""
    tokens = ipa_tokenizer.tokenize(ipa, known_symbols)
    body = [(i, t) for i, t in enumerate(tokens) if t[0] not in ("ˈ", "ˌ")]
    symbols = [t for _, t in body]
    vowel_at = [i for i, (symbol, _) in enumerate(symbols) if symbol in vowel_symbols]
    if not vowel_at:
        return ipa
    plain = "".join(symbol + deco for symbol, deco in symbols)
    if kind == "full":
        return plain + plain
    first = vowel_at[0]
    if kind == "initial_cv":
        copy = symbols[: first + 1]
        return "".join(s + d for s, d in copy) + plain
    if kind == "initial_syllable":
        end = first + 1
        if (
            end < len(symbols) and symbols[end][0] not in vowel_symbols
            and (end + 1 >= len(symbols) or symbols[end + 1][0] not in vowel_symbols)
        ):
            end += 1  # a consonant closing the syllable (before another consonant, or word-final): take the coda too
        copy = symbols[:end]
        return "".join(s + d for s, d in copy) + plain
    last = vowel_at[-1]
    start = last - 1 if last > 0 and symbols[last - 1][0] not in vowel_symbols else last
    copy = symbols[start:]
    return plain + "".join(s + d for s, d in copy)
