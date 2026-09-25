"""Noun-phrase follow-ups, second round: partial suppletion in a pronoun's
case paradigm (I/me but I-genitive regular), adjective placement and stacking
order, and definiteness beyond two articles (a specific article, and a definite
article derived from the demonstrative).

One independent rng stream, so no earlier seed choice shifts."""

from __future__ import annotations

import random

from conlang_generator.core.phonology import PhonemeInventory
from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK
from conlang_generator.generation import ipa_tokenizer
from conlang_generator.generation.inflection_gen import _ALL_SINGLE_CHAR_SYMBOLS

ADJECTIVE_CLASSES = ("quality", "size", "age", "colour", "other")
_CLASS_WORDS: dict[str, frozenset[str]] = {
    "quality": frozenset("good bad nice beautiful ugly clean dirty happy sad".split()),
    "size": frozenset("big small large little long short tall high low wide narrow deep fat thin".split()),
    "age": frozenset("old new young ancient".split()),
    "colour": frozenset("red blue green yellow white black brown grey".split()),
}
_SUPPLETIVE_CASE_POOL = ("accusative", "dative", "genitive", "locative", "instrumental")
SPECIFIC_ARTICLE_GLOSS = "a-certain"


def adjective_class(gloss: str) -> str:
    """Which order class an English adjective belongs to (``other`` if unknown)."""
    word = gloss.strip().lower()
    for name, words in _CLASS_WORDS.items():
        if word in words:
            return name
    return "other"


def roll_followups(rng: random.Random, grammar) -> dict[str, object]:
    """Every draw is always made, so the count never depends on the grammar."""
    limit_gates = [rng.random() < 0.5 for _ in range(4)]
    limit_picks = [[rng.random() < 0.5 for _ in _SUPPLETIVE_CASE_POOL] for _ in range(4)]
    split = rng.random() < 0.4
    before_hits = [rng.random() < 0.5 for _ in ADJECTIVE_CLASSES]
    ordered = rng.random() < 0.6
    order = list(ADJECTIVE_CLASSES)
    rng.shuffle(order)
    linker = rng.random() < 0.2
    from_demonstrative = rng.random() < 0.3
    specific = rng.random() < 0.35

    person_labels = ("I", "you", "he", "we")
    available = [c for c in _SUPPLETIVE_CASE_POOL if c in grammar.cases]
    limits: list[tuple[str, tuple[str, ...]]] = []
    for person, gate, picks in zip(person_labels, limit_gates, limit_picks):
        if person not in grammar.suppletive_pronoun_persons or not gate:
            continue
        chosen = tuple(c for c, hit in zip(_SUPPLETIVE_CASE_POOL, picks) if hit and c in available)
        if chosen and len(chosen) < len(available):
            limits.append((person, chosen))
    before = tuple(c for c, hit in zip(ADJECTIVE_CLASSES, before_hits) if hit)
    if split and (not before or len(before) == len(ADJECTIVE_CLASSES)):
        before = ("quality", "size")  # a split language needs both sides
    return {
        "suppletive_pronoun_case_limits": tuple(limits),
        "adjective_placement": "split" if split else "global",
        "adjective_before_classes": before if split else (),
        "adjective_stack_order": tuple(order) if ordered else (),
        "adjective_stack_linker": linker,
        "article_source": "demonstrative" if from_demonstrative and grammar.has_articles else "own",
        "has_specific_article": specific and grammar.has_indefinite_article,
    }


def derive_article_ipa(demonstrative_ipa: str, inventory: PhonemeInventory) -> str | None:
    """The definite article as a reduced demonstrative: its onset and first
    vowel (Latin ille -> Romance le), or the vowel alone when that is already all
    there is. ``None`` when nothing shorter remains."""
    known = tuple(_ALL_SINGLE_CHAR_SYMBOLS | {s for s in inventory.all_symbols() if len(s) > 1})
    stripped = demonstrative_ipa.replace(STRESS_MARK, "").replace(WORD_ACCENT_MARK, "")
    tokens = ipa_tokenizer.tokenize(stripped, known)
    vowels = set(inventory.vowel_symbols())
    for position, (symbol, _deco) in enumerate(tokens):
        if symbol in vowels:
            reduced = "".join(sym + deco for sym, deco in tokens[: position + 1])
            if reduced != stripped:
                return reduced
            alone = tokens[position][0] + tokens[position][1]  # already open: keep just the vowel
            return alone if alone != stripped else None
    return None
