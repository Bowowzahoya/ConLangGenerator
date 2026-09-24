"""Numeral classifiers ("two [CL] dogs") -- Mandarin, Japanese, Thai style.

A language rolls whether it uses classifiers (more often when it is
isolating). A classifier language puts a classifier word between a numeral
(or demonstrative) and its noun; the classifier is chosen by the noun's
semantic category, derived from its English gloss (no rng, no stored field),
and each category's classifier is an ordinary lexicon word with the gloss
``classifier-<category>``, coined on first use. Nouns after a numeral stay
singular in such a language (``plural_after_numeral`` is switched off).

Illustrative, not a rigorous typological model (see docs/LIMITATIONS.md).
"""

from __future__ import annotations

import random

from conlang_generator.core.grammar import MorphologicalType
from conlang_generator.generation.noun_class_gen import _ANIMAL, _HUMAN

_ISOLATING_RATE = 0.45
_OTHER_RATE = 0.12

CATEGORIES = ("human", "animal", "long", "flat", "round", "general")
CLASSIFIER_GLOSS_PREFIX = "classifier-"

_LONG = frozenset(
    {
        "river", "road", "path", "rope", "snake", "arrow", "spear", "knife", "tree", "branch", "stick", "bridge",
        "bow", "axe", "tail", "arm", "leg", "finger", "neck", "hair", "worm", "thread",
    }
)
_FLAT = frozenset(
    {
        "leaf", "book", "letter", "picture", "cloth", "mirror", "door", "wall", "bed", "field", "roof", "gate",
        "feather", "wing", "skin", "hat", "shoe",
    }
)
_ROUND = frozenset(
    {
        "stone", "egg", "seed", "fruit", "eye", "moon", "sun", "star", "heart", "ring", "wheel", "pot", "cup",
        "bowl", "ball", "head", "island", "cloud", "mountain", "hill", "lake", "house", "box", "bag", "basket",
    }
)


def roll_uses_classifiers(rng: random.Random, morphological_type: MorphologicalType) -> bool:
    rate = _ISOLATING_RATE if morphological_type is MorphologicalType.ISOLATING else _OTHER_RATE
    return rng.random() < rate


def classifier_category(gloss: str) -> str:
    """The classifier category of the noun with English gloss ``gloss``."""
    word = gloss.strip().lower()
    if word in _HUMAN:
        return "human"
    if word in _ANIMAL:
        return "animal"
    if word in _LONG:
        return "long"
    if word in _FLAT:
        return "flat"
    if word in _ROUND:
        return "round"
    return "general"


def classifier_gloss(category: str) -> str:
    return f"{CLASSIFIER_GLOSS_PREFIX}{category}"
