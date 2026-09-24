"""Numeral classifiers ("two [CL] dogs") -- Mandarin, Japanese, Thai style.

A language rolls whether it uses classifiers (more often when it is
isolating) and, if so, how:

- ``classifier_categories``: which of the twelve noun categories have a
  classifier of their own (a subset; ``general`` is always there and takes any
  noun whose category the language lacks);
- ``classifier_after_noun``: the order noun-numeral-classifier (Thai,
  Vietnamese) instead of numeral-classifier-noun (Mandarin, Japanese);
- ``classifier_with_demonstrative``: whether a demonstrative takes a
  classifier too.

The category of a noun is derived from its English gloss (no rng, no stored
field), and each category's classifier is an ordinary lexicon word with the
gloss ``classifier-<category>``, coined on first use. Nouns after a numeral
stay singular in such a language (``plural_after_numeral`` is switched off).

Illustrative, not a rigorous typological model (see docs/LIMITATIONS.md).
"""

from __future__ import annotations

import random

from conlang_generator.core.grammar import MorphologicalType
from conlang_generator.generation.noun_class_gen import _ANIMAL, _HUMAN

_ISOLATING_RATE = 0.45
_OTHER_RATE = 0.12
_AFTER_NOUN_RATE = 0.25
_WITH_DEMONSTRATIVE_RATE = 0.8

CATEGORIES = (
    "human", "animal", "long", "flat", "round", "general",
    "plant", "container", "building", "vehicle", "tool", "food",
)
LEGACY_CATEGORIES = ("human", "animal", "long", "flat", "round", "general")
"""The six categories a language saved before the richer inventory has."""
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
        "stone", "egg", "seed", "fruit", "eye", "moon", "sun", "star", "heart", "ring", "wheel", "ball", "head",
        "island", "cloud", "mountain", "hill", "lake",
    }
)
_PLANT = frozenset({"flower", "grass", "vegetable", "forest", "root"})
_CONTAINER = frozenset({"pot", "cup", "bowl", "basket", "box", "bag", "bottle"})
_BUILDING = frozenset({"house", "village", "town", "cave", "tower", "city"})
_VEHICLE = frozenset({"boat", "ship", "cart", "wagon"})
_TOOL = frozenset({"tool", "key", "lamp", "net", "hammer", "needle"})
_FOOD = frozenset({"bread", "meat", "rice", "honey", "sugar", "soup", "milk", "oil", "wine", "salt", "water"})


def roll_classifier_system(rng: random.Random, morphological_type: MorphologicalType) -> dict[str, object]:
    """The classifier fields of ``GrammarProfile``. The first draw is the
    same "does it use classifiers" roll as ever, so a language that does not
    use them (and every earlier seed) is unchanged; the rest is drawn only
    for a classifier language."""
    rate = _ISOLATING_RATE if morphological_type is MorphologicalType.ISOLATING else _OTHER_RATE
    if not rng.random() < rate:
        return {"uses_classifiers": False}
    others = [c for c in CATEGORIES if c != "general"]
    chosen = set(rng.sample(others, rng.randint(3, len(others))))
    return {
        "uses_classifiers": True,
        "classifier_categories": tuple(c for c in CATEGORIES if c in chosen or c == "general"),
        "classifier_after_noun": rng.random() < _AFTER_NOUN_RATE,
        "classifier_with_demonstrative": rng.random() < _WITH_DEMONSTRATIVE_RATE,
    }


def raw_category(gloss: str) -> str:
    word = gloss.strip().lower()
    for category, glosses in (
        ("human", _HUMAN), ("animal", _ANIMAL), ("long", _LONG), ("flat", _FLAT), ("round", _ROUND),
        ("plant", _PLANT), ("container", _CONTAINER), ("building", _BUILDING), ("vehicle", _VEHICLE),
        ("tool", _TOOL), ("food", _FOOD),
    ):
        if word in glosses:
            return category
    return "general"


def classifier_category(gloss: str, available: tuple[str, ...] | None = None) -> str:
    """The classifier category of the noun with English gloss ``gloss``: its
    own category if the language has a classifier for it (``available``
    ``None`` meaning every category), else ``general``."""
    category = raw_category(gloss)
    if available is not None and available and category not in available:
        return "general"
    return category


def classifier_gloss(category: str) -> str:
    return f"{CLASSIFIER_GLOSS_PREFIX}{category}"
