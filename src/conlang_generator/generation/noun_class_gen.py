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


# ---------------------------------------------------------------------------
# Class assignment for nouns with no natural gender or animacy, class marking on
# the noun itself, and which word categories agree in class, number and case.
# ---------------------------------------------------------------------------

AGREEMENT_CATEGORIES = ("article", "adjective", "demonstrative", "possessive", "numeral")
"""The word categories that can agree with their noun."""
LEGACY_CLASS_AGREEMENT = ("article", "adjective", "demonstrative", "possessive")
"""What agreed in class before targets were rolled (and on every older language)."""

_SEMANTIC_FIELDS: dict[str, frozenset[str]] = {
    "body": frozenset(
        "hand eye head hair face ear nose mouth tooth tongue neck arm leg foot finger nail skin blood bone heart "
        "belly back knee liver lip horn tail feather wing breast shoulder brain fat flesh".split()
    ),
    "nature": frozenset(
        "sun moon star sky cloud rain wind snow ice thunder lightning storm air earth sea river lake island forest "
        "mountain hill valley cave sand dust ash smoke fire water shadow light".split()
    ),
    "plant": frozenset("tree leaf root branch seed flower fruit grass vegetable".split()),
    "artifact": frozenset(
        "knife spear bow arrow axe stick boat ship wheel pot cup bowl basket net cloth shoe hat ring key book letter "
        "picture mirror lamp tool bag box bridge gate rope house door roof wall bed".split()
    ),
    "food": frozenset("bread meat milk rice honey oil wine sugar soup salt egg".split()),
    "abstract": frozenset(
        "song story word law war peace money gift game dream death life time power truth luck reason question news "
        "voice sound color shape size weight age name".split()
    ),
    "place": frozenset("road path field village town place".split()),
    "time": frozenset("night day year month morning evening".split()),
}
ASSIGNMENTS = (("hash", 0.30), ("semantic", 0.40), ("formal", 0.30))
_MARKING_RATES = (("suffix", 0.20), ("prefix", 0.15))
_NUMBER_TARGET_RATE = 0.30
_CASE_TARGET_RATE = 0.25
_NUMERAL_CLASS_RATE = 0.30


def semantic_field(gloss: str) -> str | None:
    """The broad semantic field of an English noun (``None`` if it has none)."""
    word = gloss.strip().lower()
    for field, glosses in _SEMANTIC_FIELDS.items():
        if word in glosses:
            return field
    return None


def roll_agreement_extras(rng: random.Random) -> dict[str, object]:
    """Rolls for the agreement follow-ups (every draw always made): how classes
    are assigned to unmarked nouns, whether/how the noun itself carries its
    class, and which categories agree in class (numerals sometimes), number and
    case."""
    assignment_roll = rng.random()
    assignment = ASSIGNMENTS[-1][0]
    cumulative = 0.0
    for label, weight in ASSIGNMENTS:
        cumulative += weight
        if assignment_roll < cumulative:
            assignment = label
            break
    marking_roll = rng.random()
    marking = "suffix" if marking_roll < _MARKING_RATES[0][1] else (
        "prefix" if marking_roll < _MARKING_RATES[0][1] + _MARKING_RATES[1][1] else "none"
    )
    numeral_class = rng.random() < _NUMERAL_CLASS_RATE
    number_targets = tuple(t for t in AGREEMENT_CATEGORIES if rng.random() < _NUMBER_TARGET_RATE)
    case_targets = tuple(t for t in AGREEMENT_CATEGORIES if rng.random() < _CASE_TARGET_RATE)
    return {
        "noun_class_assignment": assignment,
        "class_marking": marking,
        "class_agreement_targets": LEGACY_CLASS_AGREEMENT + (("numeral",) if numeral_class else ()),
        "number_agreement_targets": number_targets,
        "case_agreement_targets": case_targets,
    }


def _ending(ipa: str) -> str:
    """The final letter of ``ipa`` without stress, tone or length marks."""
    import unicodedata

    kept = [
        c
        for c in unicodedata.normalize("NFD", ipa)
        if not unicodedata.combining(c) and c not in "\u02c8\u02cc\u02d0.'"
    ]
    return kept[-1] if kept else ""


def assigned_class(
    classes: tuple[str, ...], seed: int, gloss: str, assignment: str = "hash", ipa: str | None = None
) -> str | None:
    """The class of a noun under this language's assignment: natural
    gender/animacy first (as ``noun_class``), then, for other nouns,
    ``hash`` (arbitrary, per noun), ``semantic`` (every noun of a broad
    semantic field shares a class) or ``formal`` (the class follows the
    noun's final sound, the way Romance and German nouns' endings predict
    gender -- falling back to ``hash`` when the noun's form is not known)."""
    natural = noun_class(classes, seed, gloss)
    if not classes or assignment == "hash":
        return natural
    word = gloss.strip().lower()
    if word in _MASCULINE or word in _FEMININE or "human" in classes or "animate" in classes:
        return natural  # natural gender/animacy systems decide these directly
    if assignment == "semantic":
        field = semantic_field(word)
        if field is None:
            return natural
        return classes[_stable_index(seed, f"field:{field}", len(classes))]
    if assignment == "formal" and ipa:
        ending = _ending(ipa)
        if ending:
            return classes[_stable_index(seed, f"ending:{ending}", len(classes))]
    return natural


def generate_class_prefixes(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    labels: tuple[str, ...],
    taken: frozenset[tuple[str, ...]] = frozenset(),
) -> tuple[InflectionAffix, ...]:
    """One open-syllable prefix (onset + vowel, so it joins any stem cleanly,
    like Bantu ``ki-``/``wa-``) per label, distinct from each other where the
    inventory allows."""
    from conlang_generator.generation import word_builder

    used = set(taken)
    affixes: list[InflectionAffix] = []
    for label in labels:
        prefix: tuple[str, ...] = ()
        for _ in range(30):
            onset, nucleus, _coda = word_builder._build_syllable_parts(rng, inventory, structure)
            prefix = tuple(onset[:1]) + (nucleus,)
            if prefix not in used:
                break
        used.add(prefix)
        affixes.append(InflectionAffix(label=label, prefix=prefix))
    return tuple(affixes)
