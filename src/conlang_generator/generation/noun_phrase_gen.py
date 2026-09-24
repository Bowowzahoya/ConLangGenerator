"""Noun-phrase grammar: dual number, demonstrative and numeral behaviour, an
indefinite article, and possession marking.

Rolled once per language from its own independent rng stream (so no other
draw shifts). What is rolled:

- ``dual`` number (15%): a ``"dual"`` suffix beside the plural one.
- ``plural_after_numeral`` (50%): whether a noun after a numeral above "one"
  still takes the plural (English) or stays singular (Turkish, Hungarian).
- ``demonstrative_after_noun`` (35%): demonstratives follow their noun.
- ``has_indefinite_article`` (50% with a definite article, else 15%).
- ``possession``: ``"genitive"`` (the language has a genitive case),
  otherwise a free ``"particle"`` after the possessor (45%), an ``"affix"``
  on the possessed noun (45%) or plain ``"none"`` (juxtaposition, 10%).

Illustrative, not a rigorous typological model (see docs/LIMITATIONS.md).
"""

from __future__ import annotations

import random

from conlang_generator.core.grammar import GrammarProfile, InflectionAffix
from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure
from conlang_generator.generation import inflection_gen, word_builder

_DUAL_RATE = 0.15
_PLURAL_AFTER_NUMERAL_RATE = 0.5
_DEMONSTRATIVE_AFTER_NOUN_RATE = 0.35
_INDEFINITE_RATE_WITH_ARTICLES = 0.5
_INDEFINITE_RATE_WITHOUT_ARTICLES = 0.15
_PARTICLE_CUTOFF = 0.45
_AFFIX_CUTOFF = 0.90


def generate_noun_phrase_grammar(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    grammar: GrammarProfile,
) -> dict[str, object]:
    """The ``GrammarProfile`` field updates for this language's noun phrase."""
    dual = rng.random() < _DUAL_RATE
    plural_after_numeral = rng.random() < _PLURAL_AFTER_NUMERAL_RATE
    demonstrative_after_noun = rng.random() < _DEMONSTRATIVE_AFTER_NOUN_RATE
    indefinite_rate = _INDEFINITE_RATE_WITH_ARTICLES if grammar.has_articles else _INDEFINITE_RATE_WITHOUT_ARTICLES
    has_indefinite_article = rng.random() < indefinite_rate
    possession_roll = rng.random()
    if "genitive" in grammar.cases:
        possession = "genitive"
    elif possession_roll < _PARTICLE_CUTOFF:
        possession = "particle"
    elif possession_roll < _AFFIX_CUTOFF:
        possession = "affix"
    else:
        possession = "none"

    taken = frozenset(
        affix.suffix for affix in (*grammar.case_affixes, *grammar.number_affixes, *grammar.class_affixes)
    )
    number_affixes = grammar.number_affixes
    if dual:
        number_affixes = number_affixes + inflection_gen.distinct_suffixes(rng, inventory, structure, ("dual",), taken)
        taken = taken | {affix.suffix for affix in number_affixes}
    possession_affixes: tuple[InflectionAffix, ...] = ()
    if possession == "affix":
        possession_affixes = inflection_gen.distinct_suffixes(rng, inventory, structure, ("possessed",), taken)
    particle = word_builder.build_syllable(rng, inventory, structure) if possession == "particle" else ""
    return {
        "number_affixes": number_affixes,
        "plural_after_numeral": plural_after_numeral,
        "demonstrative_after_noun": demonstrative_after_noun,
        "has_indefinite_article": has_indefinite_article,
        "possession": possession,
        "possessive_particle": particle,
        "possession_affixes": possession_affixes,
    }
