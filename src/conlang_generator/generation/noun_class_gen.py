"""Noun classes (grammatical gender / animacy) and the agreement they drive.

A language rolls one class system (none, masculine/feminine, masculine/
feminine/neuter, animate/inanimate, or human/animal/plant/thing). Each noun's
class is *derived*, not stored: natural-gender and animacy glosses go to their
obvious class, every other noun to a class chosen by a stable hash of
``(seed, gloss)`` -- so no lexicon draw shifts and a noun coined later during
translation gets its class the same way. The class shows up only through
agreement: articles and adjectives take the class suffix of their noun, and a
verb can take the class of its subject (and, in languages with object
agreement, of its object).

Illustrative, not a rigorous typological model (see docs/LIMITATIONS.md).
"""

from __future__ import annotations

import hashlib
import random

from conlang_generator.core.grammar import InflectionAffix
from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure
from conlang_generator.generation import inflection_gen

NOUN_CLASS_SYSTEMS: tuple[tuple[str, ...], ...] = (
    (),
    ("masculine", "feminine"),
    ("masculine", "feminine", "neuter"),
    ("animate", "inanimate"),
    ("human", "animal", "plant", "thing"),
)
_SYSTEM_WEIGHTS = (0.35, 0.20, 0.15, 0.15, 0.15)
_OBJECT_AGREEMENT_RATE = 0.3

_MASCULINE = frozenset({"man", "boy", "father", "brother", "king", "he"})
_FEMININE = frozenset({"woman", "girl", "mother", "sister", "queen", "she"})
_HUMAN = frozenset(
    {
        "person", "child", "man", "woman", "boy", "girl", "mother", "father", "brother", "sister", "friend",
        "enemy", "king", "chief", "teacher", "hunter", "farmer", "family", "god", "spirit",
    }
)
_ANIMAL = frozenset(
    {
        "animal", "bird", "fish", "dog", "cat", "horse", "cow", "pig", "sheep", "goat", "snake", "mouse",
        "rabbit", "wolf", "bear", "deer", "insect", "worm", "ant", "spider", "frog", "turtle", "monkey",
        "elephant", "lion",
    }
)
_PLANT = frozenset({"tree", "leaf", "root", "branch", "seed", "flower", "fruit", "grass", "forest", "vegetable"})

CLASS_AGREEMENT_PREFIX = "class:"
"""Label prefix for a class-based agreement affix, e.g. ``"class:feminine"``
(person agreement labels -- ``I``/``you``/``he``/``we``/``default`` -- have no
prefix)."""


def class_agreement_label(noun_class: str) -> str:
    return f"{CLASS_AGREEMENT_PREFIX}{noun_class}"


def roll_noun_classes(rng: random.Random) -> tuple[str, ...]:
    return rng.choices(NOUN_CLASS_SYSTEMS, weights=_SYSTEM_WEIGHTS)[0]


def roll_object_agreement(rng: random.Random) -> bool:
    return rng.random() < _OBJECT_AGREEMENT_RATE


def _stable_index(seed: int, gloss: str, modulo: int) -> int:
    digest = hashlib.sha256(f"{seed}:noun-class:{gloss}".encode("utf-8")).hexdigest()
    return int(digest, 16) % modulo


def noun_class(classes: tuple[str, ...], seed: int, gloss: str) -> str | None:
    """The class of the noun with English gloss ``gloss`` in a language with
    class system ``classes`` (``None`` when it has none)."""
    if not classes:
        return None
    word = gloss.strip().lower()
    if "human" in classes:
        return "human" if word in _HUMAN else "animal" if word in _ANIMAL else "plant" if word in _PLANT else "thing"
    if "animate" in classes:
        return "animate" if word in _HUMAN or word in _ANIMAL else "inanimate"
    if word in _MASCULINE:
        return "masculine"
    if word in _FEMININE:
        return "feminine"
    return classes[_stable_index(seed, word, len(classes))]


def generate_noun_class_grammar(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    classes: tuple[str, ...],
    object_agreement: bool,
    taken: frozenset[tuple[str, ...]],
) -> tuple[tuple[InflectionAffix, ...], tuple[InflectionAffix, ...], tuple[InflectionAffix, ...]]:
    """``(class_affixes, class_subject_agreement_affixes, object_agreement_
    affixes)``.

    - ``class_affixes``: one per class, for articles and adjectives.
    - ``class_subject_agreement_affixes``: one per class, labelled
      ``"class:<name>"``, appended to ``GrammarProfile.agreement_affixes``.
    - ``object_agreement_affixes``: empty unless ``object_agreement``;
      otherwise one per person label (``I``/``you``/``he``/``we``) and per
      class (``"class:<name>"``).

    Suffixes are drawn distinct from ``taken`` and from each other where the
    inventory allows.
    """
    if not classes and not object_agreement:
        return (), (), ()
    labels = tuple(classes)
    agreement_labels = tuple(class_agreement_label(c) for c in classes)
    class_affixes = inflection_gen.distinct_suffixes(rng, inventory, structure, labels, taken)
    taken = taken | {a.suffix for a in class_affixes}
    subject_affixes = inflection_gen.distinct_suffixes(rng, inventory, structure, agreement_labels, taken)
    taken = taken | {a.suffix for a in subject_affixes}
    object_affixes: tuple[InflectionAffix, ...] = ()
    if object_agreement:
        object_labels = ("I", "you", "he", "we") + agreement_labels
        object_affixes = inflection_gen.distinct_suffixes(rng, inventory, structure, object_labels, taken)
    return class_affixes, subject_affixes, object_affixes
