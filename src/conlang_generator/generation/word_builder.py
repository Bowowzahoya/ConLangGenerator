"""Deterministic, phonotactically-valid word construction from a seeded RNG.

This is the one place that actually assembles IPA strings; it's reused for
whole lexicon entries (multiple syllables) and short grammatical affixes
(one syllable), so both are guaranteed to obey the language's own
``SyllableStructure``.
"""

from __future__ import annotations

import random

from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure


def _build_onset(
    rng: random.Random, inventory: PhonemeInventory, structure: SyllableStructure
) -> tuple[str, ...]:
    if structure.max_onset == 0:
        return ()
    if structure.max_onset >= 2 and structure.allowed_onset_clusters and rng.random() < 0.3:
        return rng.choice(structure.allowed_onset_clusters)
    return (rng.choice(inventory.consonant_symbols()),)


def _build_coda(
    rng: random.Random, inventory: PhonemeInventory, structure: SyllableStructure
) -> tuple[str, ...]:
    if structure.max_coda == 0 or rng.random() < 0.4:
        return ()
    candidates = structure.allowed_coda_consonants or inventory.consonant_symbols()
    return (rng.choice(candidates),)


def build_syllable(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    tone_mark: str = "",
) -> str:
    onset = _build_onset(rng, inventory, structure)
    nucleus = rng.choice(inventory.vowel_symbols())
    coda = _build_coda(rng, inventory, structure)
    assert structure.is_valid_syllable(onset, coda), (onset, coda)
    return "".join(onset) + nucleus + tone_mark + "".join(coda)


def build_word(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    num_syllables: int,
    tone_marks: tuple[str, ...] = (),
) -> str:
    marks = tone_marks or ("",) * num_syllables
    return "".join(
        build_syllable(rng, inventory, structure, tone_mark=marks[i])
        for i in range(num_syllables)
    )
