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
_POSSESSIVE_CLASSIFIER_RATE = 0.3
_LEXICAL_RATE = 0.3
_NO_REPEATER_RATE = 0.4

QUANTIFIERS = ("many", "few", "some", "several", "all", "every", "each", "both", "how-many")
"""English quantifiers that may take a classifier in a classifier language."""

CATEGORIES = (
    "human", "animal", "long", "flat", "round", "general",
    "plant", "container", "building", "vehicle", "tool", "food",
)
LEGACY_CATEGORIES = ("human", "animal", "long", "flat", "round", "general")
"""The six categories a language saved before the richer inventory has."""
CLASSIFIER_GLOSS_PREFIX = "classifier-"
POSSESSIVE_CLASSIFIER_GLOSS_PREFIX = "possessive-classifier-"

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
        "possessive_classifiers": rng.random() < _POSSESSIVE_CLASSIFIER_RATE,
        **_roll_individual_classifiers(rng),
    }


def _roll_individual_classifiers(rng: random.Random) -> dict[str, object]:
    """Drawn after the earlier classifier rolls (which are unchanged): whether
    a noun's classifier comes from its meaning or from a lexical pool (an
    arbitrary classifier per noun, 12-40 of them), how many nouns are their
    own classifier (a "repeater": two boat-boat), and which quantifiers take a
    classifier at all."""
    lexical = rng.random() < _LEXICAL_RATE
    pool_size = rng.randint(12, 40)
    repeater_roll = rng.random()
    repeater_rate = 0.0 if repeater_roll < _NO_REPEATER_RATE else round(0.1 + 0.4 * rng.random(), 2)
    classified = tuple(q for q in QUANTIFIERS if rng.random() < 0.5)
    return {
        "classifier_assignment": "lexical" if lexical else "category",
        "classifier_pool_size": pool_size if lexical else 0,
        "repeater_rate": repeater_rate,
        "classified_quantifiers": classified,
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


def possessive_classifier_gloss(category: str) -> str:
    """The lexicon gloss of the classifier that follows a possessor."""
    return f"{POSSESSIVE_CLASSIFIER_GLOSS_PREFIX}{category}"


def _stable_fraction(seed: int, gloss: str, salt: str) -> float:
    import hashlib

    digest = hashlib.sha256(f"{seed}:{salt}:{gloss.strip().lower()}".encode("utf-8")).hexdigest()
    return int(digest, 16) % 1_000_000 / 1_000_000


def lexical_index(seed: int, gloss: str, pool_size: int) -> int:
    """The index (0..pool_size-1) of the classifier a noun is assigned in a
    lexical-pool language: arbitrary but stable for ``(seed, gloss)``."""
    return int(_stable_fraction(seed, gloss, "lexical-classifier") * pool_size) % max(1, pool_size)


def is_repeater(seed: int, gloss: str, rate: float) -> bool:
    """Whether the noun ``gloss`` is its own classifier (a repeater)."""
    return rate > 0.0 and _stable_fraction(seed, gloss, "repeater-classifier") < rate


def lexical_gloss(index: int, possessive: bool = False) -> str:
    """The lexicon gloss of pool classifier ``index``."""
    name = f"lex{index:02d}"
    return possessive_classifier_gloss(name) if possessive else classifier_gloss(name)


REPEATER_GLOSS_PREFIX = "repeater:"
