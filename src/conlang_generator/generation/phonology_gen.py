"""Seeded phoneme-inventory generation, nudged by a small set of real,
illustrative typological tendencies:

- an (almost) universal implicational rule: a voiced stop is only added once
  its voiceless counterpart is present -- guaranteed here by construction
  rather than modeled probabilistically.
- ``spec.high_altitude`` boosts the odds of ejective consonants, per
  Everett (2013)'s cross-linguistic correlation between ejectives and
  high-altitude regions.
- ``spec.isolated`` gives a small boost to rarer places of articulation
  (uvulars), loosely reflecting that isolated speech communities can retain
  more idiosyncratic inventories.

This is an illustrative starting set, not a typological database -- easy to
extend as more tendencies are wanted.
"""

from __future__ import annotations

import random

from conlang_generator.core.phonology import (
    Consonant,
    Manner,
    Place,
    PhonemeInventory,
    SyllableStructure,
    ToneLevel,
    ToneSystem,
    Vowel,
    VowelBackness,
    VowelHeight,
)
from conlang_generator.core.spec import GenerationSpec

_BASE_VOICELESS_STOPS = [
    Consonant(ipa="p", place=Place.BILABIAL, manner=Manner.STOP, voiced=False),
    Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False),
    Consonant(ipa="k", place=Place.VELAR, manner=Manner.STOP, voiced=False),
]
_VOICED_STOP_COUNTERPARTS = {
    "p": Consonant(ipa="b", place=Place.BILABIAL, manner=Manner.STOP, voiced=True),
    "t": Consonant(ipa="d", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=True),
    "k": Consonant(ipa="g", place=Place.VELAR, manner=Manner.STOP, voiced=True),
}
_EJECTIVES = [
    Consonant(ipa="pʼ", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, ejective=True),
    Consonant(ipa="tʼ", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, ejective=True),
    Consonant(ipa="kʼ", place=Place.VELAR, manner=Manner.STOP, voiced=False, ejective=True),
]
_UVULARS = [
    Consonant(ipa="q", place=Place.UVULAR, manner=Manner.STOP, voiced=False),
    Consonant(ipa="χ", place=Place.UVULAR, manner=Manner.FRICATIVE, voiced=False),
]
_GLOTTAL_STOP = Consonant(ipa="ʔ", place=Place.GLOTTAL, manner=Manner.STOP, voiced=False)
_NASALS = [
    Consonant(ipa="m", place=Place.BILABIAL, manner=Manner.NASAL, voiced=True),
    Consonant(ipa="n", place=Place.ALVEOLAR, manner=Manner.NASAL, voiced=True),
]
_OPTIONAL_NASAL = Consonant(ipa="ŋ", place=Place.VELAR, manner=Manner.NASAL, voiced=True)
_FRICATIVE_POOL = [
    Consonant(ipa="s", place=Place.ALVEOLAR, manner=Manner.FRICATIVE, voiced=False),
    Consonant(ipa="f", place=Place.LABIODENTAL, manner=Manner.FRICATIVE, voiced=False),
    Consonant(ipa="ʃ", place=Place.POSTALVEOLAR, manner=Manner.FRICATIVE, voiced=False),
    Consonant(ipa="x", place=Place.VELAR, manner=Manner.FRICATIVE, voiced=False),
    Consonant(ipa="h", place=Place.GLOTTAL, manner=Manner.FRICATIVE, voiced=False),
    Consonant(ipa="z", place=Place.ALVEOLAR, manner=Manner.FRICATIVE, voiced=True),
    Consonant(ipa="v", place=Place.LABIODENTAL, manner=Manner.FRICATIVE, voiced=True),
]
_APPROXIMANT_POOL = [
    Consonant(ipa="l", place=Place.ALVEOLAR, manner=Manner.LATERAL_APPROXIMANT, voiced=True),
    Consonant(ipa="ɾ", place=Place.ALVEOLAR, manner=Manner.TAP, voiced=True),
    Consonant(ipa="j", place=Place.PALATAL, manner=Manner.APPROXIMANT, voiced=True),
    Consonant(ipa="w", place=Place.BILABIAL, manner=Manner.APPROXIMANT, voiced=True),
]
_AFFRICATE_POOL = [
    Consonant(ipa="tʃ", place=Place.POSTALVEOLAR, manner=Manner.AFFRICATE, voiced=False),
    Consonant(ipa="dʒ", place=Place.POSTALVEOLAR, manner=Manner.AFFRICATE, voiced=True),
]

_VOWEL_GRID: dict[str, Vowel] = {
    "i": Vowel(ipa="i", height=VowelHeight.CLOSE, backness=VowelBackness.FRONT, rounded=False),
    "e": Vowel(ipa="e", height=VowelHeight.CLOSE_MID, backness=VowelBackness.FRONT, rounded=False),
    "ɛ": Vowel(ipa="ɛ", height=VowelHeight.OPEN_MID, backness=VowelBackness.FRONT, rounded=False),
    "a": Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False),
    "ə": Vowel(ipa="ə", height=VowelHeight.MID, backness=VowelBackness.CENTRAL, rounded=False),
    "ɨ": Vowel(ipa="ɨ", height=VowelHeight.CLOSE, backness=VowelBackness.CENTRAL, rounded=False),
    "ɔ": Vowel(ipa="ɔ", height=VowelHeight.OPEN_MID, backness=VowelBackness.BACK, rounded=True),
    "o": Vowel(ipa="o", height=VowelHeight.CLOSE_MID, backness=VowelBackness.BACK, rounded=True),
    "u": Vowel(ipa="u", height=VowelHeight.CLOSE, backness=VowelBackness.BACK, rounded=True),
}
_VOWEL_ANCHORS = ["i", "a", "u"]  # near-universal
_VOWEL_EXTRAS = ["e", "ɔ", "o", "ɛ", "ə", "ɨ"]

_ONSET_CLUSTER_CANDIDATES = [
    ("s", "t"), ("s", "p"), ("s", "k"),
    ("p", "ɾ"), ("t", "ɾ"), ("k", "ɾ"),
    ("p", "l"), ("k", "l"),
]

_TONE_LEVEL_SETS = [
    (ToneLevel.LOW, ToneLevel.HIGH),
    (ToneLevel.LOW, ToneLevel.MID, ToneLevel.HIGH),
    (ToneLevel.LOW, ToneLevel.MID, ToneLevel.HIGH, ToneLevel.FALLING),
]


def generate_phonology(
    rng: random.Random, spec: GenerationSpec
) -> tuple[PhonemeInventory, SyllableStructure, ToneSystem]:
    consonants: list[Consonant] = list(_BASE_VOICELESS_STOPS)

    for stop in _BASE_VOICELESS_STOPS:
        if rng.random() < 0.7:
            consonants.append(_VOICED_STOP_COUNTERPARTS[stop.ipa])

    if rng.random() < 0.85:
        consonants.append(_GLOTTAL_STOP)

    ejective_probability = 0.6 if spec.high_altitude else 0.08
    if rng.random() < ejective_probability:
        consonants.extend(_EJECTIVES)

    uvular_probability = 0.5 if spec.isolated else 0.12
    if rng.random() < uvular_probability:
        consonants.extend(_UVULARS)

    consonants.extend(_NASALS)
    if rng.random() < 0.6:
        consonants.append(_OPTIONAL_NASAL)

    consonants.extend(rng.sample(_FRICATIVE_POOL, k=rng.randint(2, len(_FRICATIVE_POOL))))
    consonants.extend(rng.sample(_APPROXIMANT_POOL, k=rng.randint(2, len(_APPROXIMANT_POOL))))
    if rng.random() < 0.5:
        consonants.extend(rng.sample(_AFFRICATE_POOL, k=1))

    vowel_count = rng.choices([5, 6, 7, 8], weights=[5, 3, 2, 1])[0]
    vowel_symbols = list(_VOWEL_ANCHORS)
    remaining_extras = [v for v in _VOWEL_EXTRAS if v not in vowel_symbols]
    vowel_symbols.extend(rng.sample(remaining_extras, k=min(vowel_count - len(vowel_symbols), len(remaining_extras))))
    vowels = [_VOWEL_GRID[symbol] for symbol in vowel_symbols]

    inventory = PhonemeInventory(consonants=tuple(consonants), vowels=tuple(vowels))

    present = set(inventory.consonant_symbols())
    allowed_clusters = tuple(pair for pair in _ONSET_CLUSTER_CANDIDATES if pair[0] in present and pair[1] in present)
    max_onset = 2 if allowed_clusters and rng.random() < 0.5 else 1
    max_coda = 0 if rng.random() < 0.25 else 1
    syllable_structure = SyllableStructure(
        max_onset=max_onset,
        max_coda=max_coda,
        allowed_onset_clusters=allowed_clusters if max_onset >= 2 else (),
        allowed_coda_consonants=None,
    )

    if spec.tonal:
        levels = rng.choice(_TONE_LEVEL_SETS)
        tone_system = ToneSystem(enabled=True, levels=levels)
    else:
        tone_system = ToneSystem(enabled=False)

    return inventory, syllable_structure, tone_system
