"""Where inflectional affixes sit: suffix (the default), prefix, circumfix
(prefix + suffix) or infix (inside the stem).

A language rolls first whether it is uniformly suffixing (65%) or mixed; a mixed
language then gives each inflectional field (noun case, number, possession; verb
tense, agreement, aspect, mood, voice, object agreement, verb number) its own position,
by morphological type (agglutinative and polysynthetic languages prefix most).

The conversion keeps the paradigm's shape: a new exponent is drawn for every
*distinct* suffix of a field -- two labels that shared a suffix (a syncretism)
share the new exponent too, and two that differed still differ. A prefix is an
open syllable (onset + vowel, like Bantu ``ki-``), a circumfix keeps the old suffix
and adds such a prefix, an infix is a nucleus + coda (Tagalog ``-um-``) put after
the stem's first consonant or before its last vowel.

Runs last, after the paradigms, from its own rng stream, so no earlier seed choice
shifts. Paradigm overrides and irregular lexemes are converted with their field."""

from __future__ import annotations

import random

from conlang_generator.core.grammar import GrammarProfile, InflectionAffix, MorphologicalType, Paradigm
from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure
from conlang_generator.generation import word_builder

NOUN_FIELDS = ("case_affixes", "number_affixes", "possession_affixes")
VERB_FIELDS = (
    "tense_affixes", "agreement_affixes", "aspect_affixes", "mood_affixes", "voice_affixes",
    "object_agreement_affixes", "verb_number_affixes",
)
POSITIONS = ("suffix", "prefix", "circumfix", "infix")
INFIX_PLACES = ("after_first_consonant", "before_last_vowel")
_MIXED_RATE = 0.35
_POSITION_WEIGHTS = {
    MorphologicalType.ISOLATING: (0.80, 0.10, 0.05, 0.05),
    MorphologicalType.AGGLUTINATIVE: (0.50, 0.32, 0.10, 0.08),
    MorphologicalType.FUSIONAL: (0.60, 0.15, 0.15, 0.10),
    MorphologicalType.POLYSYNTHETIC: (0.30, 0.40, 0.15, 0.15),
}


def _pick(roll: float, weights) -> str:
    cumulative = 0.0
    for position, weight in zip(POSITIONS, weights):
        cumulative += weight
        if roll < cumulative:
            return position
    return POSITIONS[0]


def _fresh_prefix(rng, inventory, structure, taken: set) -> tuple[str, ...]:
    prefix: tuple[str, ...] = ()
    for _ in range(60):
        onset, nucleus, _coda = word_builder._build_syllable_parts(rng, inventory, structure)
        prefix = tuple(onset[:1]) + (nucleus,)
        if prefix not in taken:
            break
    taken.add(prefix)
    return prefix


def _fresh_infix(rng, inventory, structure, taken: set) -> tuple[str, ...]:
    infix: tuple[str, ...] = ()
    for _ in range(60):
        infix = word_builder.build_class_suffix(rng, inventory, structure)
        if infix not in taken:
            break
    taken.add(infix)
    return infix


def roll_and_apply(
    rng: random.Random, grammar: GrammarProfile, inventory: PhonemeInventory, structure: SyllableStructure
) -> GrammarProfile:
    """``grammar`` with each field moved to its rolled position (a no-op for a
    uniformly suffixing language)."""
    mixed = rng.random() < _MIXED_RATE
    weights = _POSITION_WEIGHTS.get(grammar.morphological_type, _POSITION_WEIGHTS[MorphologicalType.AGGLUTINATIVE])
    rolls = {field: (rng.random(), rng.random()) for field in (*NOUN_FIELDS, *VERB_FIELDS)}
    if not mixed:
        return grammar
    chosen: dict[str, tuple[str, str]] = {}
    for field, (position_roll, place_roll) in rolls.items():
        position = _pick(position_roll, weights)
        if position != "suffix" and (getattr(grammar, field) or True):
            chosen[field] = (position, INFIX_PLACES[int(place_roll * len(INFIX_PLACES))])
    if not chosen:
        return grammar

    paradigms = {
        name: getattr(grammar, name)
        for name in ("noun_paradigms", "verb_paradigms", "adjective_paradigms", "irregular_lexemes")
    }
    prefix_taken = {"noun": set(), "verb": set()}
    infix_taken = {"noun": set(), "verb": set()}
    updates: dict[str, object] = {}
    mappings: dict[str, dict[tuple[str, ...], tuple[str, ...]]] = {}
    for field, (position, place) in chosen.items():
        group = "noun" if field in NOUN_FIELDS else "verb"
        suffixes: list[tuple[str, ...]] = []
        for affix in getattr(grammar, field):
            if affix.suffix and affix.suffix not in suffixes:
                suffixes.append(affix.suffix)
        for group_paradigms in paradigms.values():
            for paradigm in group_paradigms:
                for override in paradigm.overrides:
                    if override.label.startswith(field + "/") and override.suffix and override.suffix not in suffixes:
                        suffixes.append(override.suffix)
        mapping: dict[tuple[str, ...], tuple[str, ...]] = {}
        for suffix in suffixes:
            if position == "infix":
                mapping[suffix] = _fresh_infix(rng, inventory, structure, infix_taken[group])
            else:
                mapping[suffix] = _fresh_prefix(rng, inventory, structure, prefix_taken[group])
        mappings[field] = mapping

    def convert(affix: InflectionAffix, field: str) -> InflectionAffix:
        position, place = chosen[field]
        exponent = mappings[field].get(affix.suffix)
        if exponent is None:
            return affix
        if position == "prefix":
            return affix.model_copy(update={"prefix": exponent, "suffix": ()})
        if position == "circumfix":
            return affix.model_copy(update={"prefix": exponent})
        return affix.model_copy(update={"suffix": (), "infix": exponent, "infix_at": place})

    for field in chosen:
        updates[field] = tuple(convert(a, field) for a in getattr(grammar, field))
    for name, group_paradigms in paradigms.items():
        converted = []
        for paradigm in group_paradigms:
            overrides = []
            for override in paradigm.overrides:
                field = override.label.partition("/")[0]
                overrides.append(convert(override, field) if field in chosen else override)
            converted.append(paradigm.model_copy(update={"overrides": tuple(overrides)}))
        updates[name] = tuple(converted)
    updates["affix_positions"] = tuple((field, position) for field, (position, _place) in chosen.items())
    return grammar.model_copy(update=updates)
