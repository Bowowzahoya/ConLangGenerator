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
    "a-certain": "a certain",
    "this-article": "this",
    "that-article": "that",
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


# ---------------------------------------------------------------------------
# Reflexives, reciprocals, possessive pronouns, verb number/politeness, object
# pro-drop -- rolled together from a further independent stream.
# ---------------------------------------------------------------------------

REFLEXIVE_GLOSS = "self"
RECIPROCAL_GLOSS = "each-other"
POSSESSIVE_GLOSS_PREFIX = "possessive-"

POSSESSIVE_READING: dict[str, str] = {
    "self": "one's own", "i": "my", "you": "your", "he": "his", "she": "her", "it": "its", "they": "their", "we": "our",
    "you-plural": "your (plural)", "you-polite": "your (polite)",
    "we-inclusive": "our (inclusive)", "we-exclusive": "our (exclusive)",
}
"""The English possessive a ``possessive-<gloss>`` word is read back as."""

OBJECT_READING: dict[str, str] = {"I": "me", "you": "you", "he": "him", "we": "us"}
"""How a dropped object's person is written when read back as English."""

_REFLEXIVE_WORD_RATE = 0.45
_REFLEXIVE_AFFIX_RATE = 0.35
_RECIPROCAL_WORD_RATE = 0.40
_RECIPROCAL_AFFIX_RATE = 0.30
_POSSESSIVE_REGULAR_RATE = 0.40
_POSSESSIVE_WORDS_RATE = 0.30
_VERB_NUMBER_RATE = 0.25
_VERB_POLITENESS_RATE = 0.60
_OBJECT_PRO_DROP_RATE = 0.40
_SUPPLETION_RATE = 0.35
_SUPPLETIVE_PERSON_RATE = 0.60
_REFLEXIVE_POSSESSIVE_WORD_RATE = 0.30
_REFLEXIVE_POSSESSIVE_AFFIX_RATE = 0.25

CASE_NAMES = frozenset({"nominative", "accusative", "ergative", "absolutive", "genitive", "dative", "locative"})
_OBJECT_FORMS = {"i": "me", "he": "him", "she": "her", "we": "us", "they": "them"}


def possessive_gloss(pronoun_gloss_: str) -> str:
    """The lexicon gloss of the possessive word for a personal pronoun."""
    return f"{POSSESSIVE_GLOSS_PREFIX}{pronoun_gloss_.strip().lower()}"


def _marking(roll: float, word_rate: float, affix_rate: float) -> str:
    return "word" if roll < word_rate else "affix" if roll < word_rate + affix_rate else "none"


def roll_pronoun_extras(rng: random.Random) -> dict[str, object]:
    """The raw rolls (every one always drawn, so the stream is stable);
    ``generator.py`` finishes them (affixes, the honorific and object-agreement
    conditions)."""
    possessive_roll = rng.random()
    return {
        "reflexive_marking": _marking(rng.random(), _REFLEXIVE_WORD_RATE, _REFLEXIVE_AFFIX_RATE),
        "reciprocal_marking": _marking(rng.random(), _RECIPROCAL_WORD_RATE, _RECIPROCAL_AFFIX_RATE),
        "possessive_pronouns": (
            "regular"
            if possessive_roll < _POSSESSIVE_REGULAR_RATE
            else "words"
            if possessive_roll < _POSSESSIVE_REGULAR_RATE + _POSSESSIVE_WORDS_RATE
            else "affix"
        ),
        "verb_number_agreement": rng.random() < _VERB_NUMBER_RATE,
        "verb_politeness_wish": rng.random() < _VERB_POLITENESS_RATE,
        "object_pro_drop_wish": rng.random() < _OBJECT_PRO_DROP_RATE,
        **_roll_later_extras(rng),
    }


def _roll_later_extras(rng: random.Random) -> dict[str, object]:
    """Draws made after the rest of ``roll_pronoun_extras`` so that adding them
    changed none of the earlier values: which persons have suppletive case
    forms (I/me) and how a reflexive possessive ("his own") is marked."""
    suppletion = rng.random() < _SUPPLETION_RATE
    picks = [label for label in PERSON_LABELS if rng.random() < _SUPPLETIVE_PERSON_RATE]
    if suppletion and not picks:
        picks = [PERSON_LABELS[int(rng.random() * len(PERSON_LABELS))]]
    reflexive_possessive_roll = rng.random()
    return {
        "suppletive_pronoun_persons": tuple(picks) if suppletion else (),
        "reflexive_possessive": (
            "word"
            if reflexive_possessive_roll < _REFLEXIVE_POSSESSIVE_WORD_RATE
            else "affix"
            if reflexive_possessive_roll < _REFLEXIVE_POSSESSIVE_WORD_RATE + _REFLEXIVE_POSSESSIVE_AFFIX_RATE
            else "none"
        ),
    }


def english_reading(gloss: str) -> str:
    """How a pronoun-like lexicon gloss is written when read back as English:
    language-specific pronouns, ``self``/``each-other`` and possessive words."""
    if gloss.startswith(POSSESSIVE_GLOSS_PREFIX):
        rest = gloss[len(POSSESSIVE_GLOSS_PREFIX):]
        return POSSESSIVE_READING.get(rest, gloss)
    if gloss == REFLEXIVE_GLOSS:
        return "oneself"
    if gloss == RECIPROCAL_GLOSS:
        return "each other"
    return ENGLISH_READING.get(gloss, gloss)


def suppletive_gloss(pronoun_gloss_: str, case: str) -> str:
    """The lexicon gloss of a personal pronoun's own word for ``case`` (I -> me)."""
    return f"{pronoun_gloss_.strip().lower()}-{case}"


def suppletive_split(gloss: str) -> tuple[str, str] | None:
    """``(pronoun gloss, case)`` if ``gloss`` names a suppletive case form of a
    personal pronoun (``"i-accusative"``), else ``None``."""
    base, sep, case = gloss.strip().lower().rpartition("-")
    if sep and case in CASE_NAMES and person_label(base) is not None:
        return base, case
    return None


def suppletive_reading(pronoun_gloss_: str, case: str) -> str:
    """How a suppletive pronoun form reads in English: the object form
    (me/him/us/them) for an accusative or dative, the possessive for a
    genitive, the plain pronoun otherwise."""
    if case in ("accusative", "dative") and pronoun_gloss_ in _OBJECT_FORMS:
        return _OBJECT_FORMS[pronoun_gloss_]
    if case == "genitive" and pronoun_gloss_ in POSSESSIVE_READING:
        return POSSESSIVE_READING[pronoun_gloss_]
    return english_reading(pronoun_gloss_)
