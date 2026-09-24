"""The pronoun system: which distinctions a language's pronouns make, and the
mapping from English pronouns onto its own.

Every language has the core pronouns I / you / he / we (in its lexicon) and
coins the rest on first use. Per language, rolled from an independent rng
stream:

- ``clusivity`` (15%): "we" splits into ``we-inclusive`` / ``we-exclusive``.
- ``third_person_gender`` (35%): ``she`` and ``it`` are their own words
  (otherwise English she/it/he all map to ``he``).
- ``honorific_you`` (15% plus up to 35% with the ``social_hierarchy`` trait):
  a separate polite ``you-polite`` beside plain ``you``.
- ``pro_drop`` (35%, and only when the four person agreement suffixes are
  distinct, since dropping a pronoun needs the verb to name the person): a
  subject pronoun is omitted when the verb's own agreement already names it.

Number: ``you-plural`` and ``they`` are always their own words. Verb
agreement stays person-only (I/you/he/we); plural and polite pronouns agree
like their singular person, and ``they`` like ``he``.

Illustrative, not a rigorous typological model (see docs/LIMITATIONS.md).
"""

from __future__ import annotations

import random

from conlang_generator.core.grammar import GrammarProfile

_CLUSIVITY_RATE = 0.15
_GENDER_RATE = 0.35
_HONORIFIC_BASE = 0.15
_HONORIFIC_HIERARCHY_WEIGHT = 0.35
_PRO_DROP_RATE = 0.35

PERSON_LABELS = ("I", "you", "he", "we")

PERSON_BY_GLOSS: dict[str, str] = {
    "i": "I", "me": "I",
    "you": "you", "you-plural": "you", "you-polite": "you",
    "he": "he", "she": "he", "it": "he", "they": "he", "him": "he", "them": "he",
    "we": "we", "we-inclusive": "we", "we-exclusive": "we", "us": "we",
}
"""Lower-cased pronoun gloss -> the verb-agreement person label it takes."""

ENGLISH_READING: dict[str, str] = {
    "you-plural": "you (plural)",
    "you-polite": "you (polite)",
    "we-inclusive": "we (inclusive)",
    "we-exclusive": "we (exclusive)",
}
"""How a language-specific pronoun gloss is written when read back as English."""

_POLITE_CUES = frozenset({"sir", "madam", "lord", "lady", "mister", "mr", "mrs", "majesty"})


def roll_pronoun_system(rng: random.Random, social_hierarchy: float) -> dict[str, bool]:
    """``clusivity``, ``third_person_gender``, ``honorific_you`` and the
    *wish* for ``pro_drop`` (the generator drops it when the person suffixes
    are not distinct)."""
    honorific_rate = _HONORIFIC_BASE + _HONORIFIC_HIERARCHY_WEIGHT * max(0.0, social_hierarchy)
    return {
        "clusivity": rng.random() < _CLUSIVITY_RATE,
        "third_person_gender": rng.random() < _GENDER_RATE,
        "honorific_you": rng.random() < honorific_rate,
        "pro_drop": rng.random() < _PRO_DROP_RATE,
    }


def pronoun_glosses(grammar: GrammarProfile) -> tuple[str, ...]:
    """Every pronoun gloss this language uses for a person, in a stable order."""
    glosses = ["I", "you", "you-plural"]
    if grammar.honorific_you:
        glosses.append("you-polite")
    glosses.append("he")
    if grammar.third_person_gender:
        glosses += ["she", "it"]
    glosses.append("they")
    glosses += ["we-inclusive", "we-exclusive"] if grammar.clusivity else ["we"]
    return tuple(glosses)


def english_pronoun_gloss(grammar: GrammarProfile, token: str, sentence_tokens: list[str] | tuple[str, ...] = ()) -> str:
    """The gloss this language uses for the English pronoun ``token`` (lower
    case): a coarse, context-free mapping used by the fake planner and as a
    reference for the real one. ``you`` becomes ``you-polite`` only when the
    language has one and the sentence carries a courtesy cue."""
    word = token.lower()
    if word in ("i", "me"):
        return "I"
    if word == "you":
        if grammar.honorific_you and any(t in _POLITE_CUES for t in sentence_tokens):
            return "you-polite"
        return "you"
    if word in ("he", "him"):
        return "he"
    if word == "she":
        return "she" if grammar.third_person_gender else "he"
    if word == "it":
        return "it" if grammar.third_person_gender else "he"
    if word in ("we", "us"):
        return "we-exclusive" if grammar.clusivity else "we"
    if word in ("they", "them"):
        return "they"
    return token


def person_label(gloss: str | None) -> str | None:
    """The agreement person label of a pronoun gloss (``None`` for anything
    that is not a personal pronoun)."""
    return PERSON_BY_GLOSS.get((gloss or "").strip().lower())
