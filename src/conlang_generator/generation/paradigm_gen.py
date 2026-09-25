"""Real inflection paradigms: declension and conjugation classes, and irregular
lexemes, instead of one invented affix per feature for every word.

The language's existing affixes are its first class (class 0). A noun or verb
belongs to one class -- a noun's by its gender/class where the language has one,
otherwise by a stable hash of its gloss -- and a further class overrides some of
the labels' suffixes (the rest are shared, as real declensions share cells:
syncretism). An irregular lexeme overrides one or two cells of its own class.
Every override is drawn to be distinct, in its field, from that paradigm's other
suffixes (also as spelled), so a form still names its label.

One independent rng stream; it draws after everything else, so no earlier seed
choice shifts."""

from __future__ import annotations

import random

from conlang_generator.core.grammar import GrammarProfile, InflectionAffix, MorphologicalType, Paradigm
from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure
from conlang_generator.generation import inflection_gen, word_builder

NOUN_FIELDS = ("case_affixes", "number_affixes")
VERB_FIELDS = ("tense_affixes", "agreement_affixes")
_TYPE_RATE = {
    MorphologicalType.ISOLATING: 0.10,
    MorphologicalType.AGGLUTINATIVE: 0.30,
    MorphologicalType.FUSIONAL: 0.85,
    MorphologicalType.POLYSYNTHETIC: 0.40,
}
_CHANGE_RATE = 0.55
"""How likely a further class gives a label a suffix of its own (the rest are shared with class 0)."""
CLASS_WEIGHTS = (1.0, 0.6, 0.4, 0.3)
IRREGULAR_NOUNS = ("man", "woman", "child", "dog", "water", "fire", "hand", "eye", "foot", "mother", "father")
IRREGULAR_VERBS = ("be", "go", "see", "eat", "come", "give", "have", "say", "know", "take")


def _spelled(romanization, suffix: tuple[str, ...]):
    return romanization.apply("".join(suffix)).lower() if romanization is not None else suffix


def _override_labels(grammar: GrammarProfile, field: str) -> list[InflectionAffix]:
    """The base affixes of ``field`` that a paradigm may change."""
    affixes = [a for a in getattr(grammar, field) if a.suffix and not a.prefix]
    if field == "agreement_affixes":
        affixes = [a for a in affixes if a.label in inflection_gen.AGREEMENT_LABELS]  # class agreement stays shared
    return affixes


def _fresh_suffix(rng, inventory, structure, taken: set, romanization):
    for attempt in range(120):
        suffix = word_builder.build_class_suffix(rng, inventory, structure)
        for _ in range(attempt // 30):
            suffix = suffix + word_builder.build_class_suffix(rng, inventory, structure)
        if _spelled(romanization, suffix) not in taken:
            return suffix
    return None


def _group_taken(grammar: GrammarProfile, pos: str, romanization) -> set:
    """Every suffix, as spelled, that can sit on the same kind of word (the whole
    noun or verb group, so a number suffix never spells like a case suffix)."""
    fields = inflection_gen._NOUN_SUFFIX_FIELDS if pos == "noun" else inflection_gen._VERB_SUFFIX_FIELDS
    return {
        _spelled(romanization, a.suffix)
        for name in fields
        for a in getattr(grammar, name, ())
        if a.suffix and not a.prefix
    }


def _draw_class(
    rng, name: str, pos: str, grammar: GrammarProfile, fields, inventory, structure, romanization
) -> Paradigm:
    overrides: list[InflectionAffix] = []
    taken = _group_taken(grammar, pos, romanization)
    for field in fields:
        base = getattr(grammar, field)
        changeable = {a.label for a in _override_labels(grammar, field)}
        for affix in base:
            if affix.label not in changeable or rng.random() >= _CHANGE_RATE:
                continue
            suffix = _fresh_suffix(rng, inventory, structure, taken, romanization)
            if suffix is None:
                continue
            taken.add(_spelled(romanization, suffix))
            overrides.append(InflectionAffix(label=f"{field}/{affix.label}", suffix=suffix))
    return Paradigm(name=name, pos=pos, overrides=tuple(overrides))


def _draw_irregulars(
    rng, candidates, pos: str, fields, grammar, inventory, structure, romanization, classes=()
) -> list[Paradigm]:
    found: list[Paradigm] = []
    for gloss in candidates:
        if rng.random() >= 0.3:
            continue
        chosen: list[InflectionAffix] = []
        for field in fields:
            options = _override_labels(grammar, field)
            if not options or rng.random() >= 0.6:
                continue
            affix = options[int(rng.random() * len(options))]
            taken = (
                _group_taken(grammar, pos, romanization)
                | {_spelled(romanization, a.suffix) for a in chosen}
                | {_spelled(romanization, o.suffix) for cls in classes for o in cls.overrides}
            )
            suffix = _fresh_suffix(rng, inventory, structure, taken, romanization)
            if suffix is not None:
                chosen.append(InflectionAffix(label=f"{field}/{affix.label}", suffix=suffix))
        if chosen:
            found.append(Paradigm(name=gloss, pos=pos, overrides=tuple(chosen)))
    return found


def roll_paradigms(
    rng: random.Random,
    grammar: GrammarProfile,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    romanization=None,
) -> dict[str, tuple[Paradigm, ...]]:
    """The extra declension and conjugation classes and the irregular lexemes."""
    rate = _TYPE_RATE.get(grammar.morphological_type, 0.3)
    noun_gate = rng.random() < rate and bool(grammar.case_affixes or grammar.number_affixes)
    verb_gate = rng.random() < rate and bool(grammar.tense_affixes or grammar.agreement_affixes)
    extra_nouns = 1 + int(rng.random() * 3)
    extra_verbs = 1 + int(rng.random() * 2)
    irregular_gate = rng.random() < min(1.0, rate + 0.2)
    nouns = tuple(
        _draw_class(rng, f"declension-{k + 2}", "noun", grammar, NOUN_FIELDS, inventory, structure, romanization)
        for k in range(extra_nouns)
    ) if noun_gate else ()
    verbs = tuple(
        _draw_class(rng, f"conjugation-{k + 2}", "verb", grammar, VERB_FIELDS, inventory, structure, romanization)
        for k in range(extra_verbs)
    ) if verb_gate else ()
    irregulars: tuple[Paradigm, ...] = ()
    if irregular_gate:
        irregulars = tuple(
            _draw_irregulars(rng, IRREGULAR_NOUNS, "noun", NOUN_FIELDS, grammar, inventory, structure, romanization, nouns)
            + _draw_irregulars(rng, IRREGULAR_VERBS, "verb", VERB_FIELDS, grammar, inventory, structure, romanization, verbs)
        )
    # A class that changed nothing is not a class.
    return {
        "noun_paradigms": tuple(p for p in nouns if p.overrides),
        "verb_paradigms": tuple(p for p in verbs if p.overrides),
        "irregular_lexemes": irregulars,
    }


def class_index(seed: int, pos: str, gloss: str, count: int) -> int:
    """Which class (0 = the language's base affixes) a word with this gloss belongs to,
    among ``count`` classes, by a stable weighted hash."""
    import hashlib

    if count <= 1:
        return 0
    digest = hashlib.sha256(f"{seed}:paradigm:{pos}:{gloss}".encode()).digest()
    unit = int.from_bytes(digest[:8], "big") / 2**64
    weights = CLASS_WEIGHTS[:count] + (CLASS_WEIGHTS[-1],) * max(0, count - len(CLASS_WEIGHTS))
    total = sum(weights)
    cumulative = 0.0
    for index, weight in enumerate(weights):
        cumulative += weight / total
        if unit < cumulative:
            return index
    return count - 1
