"""Deterministic, phonotactically-valid word construction from a seeded RNG.

This is the one place that actually assembles IPA strings; it's reused for
whole lexicon entries (multiple syllables) and short grammatical affixes
(one syllable), so both are guaranteed to obey the language's own
``SyllableStructure``.

Phoneme selection is weighted by each candidate's ``prevalence`` (see
``core/phonology.py``) rather than uniform -- the same phonemes that are
more likely to be *in* a language's inventory are also more likely to show
up often *within* words once they are (the schwa-in-English effect).
"""

from __future__ import annotations

import random

from conlang_generator.core.phonology import (
    Consonant,
    Manner,
    PhonemeInventory,
    SyllableStructure,
    Vowel,
    VowelBackness,
    VowelHeight,
)

_SMALL_HEIGHTS = (VowelHeight.CLOSE, VowelHeight.NEAR_CLOSE)
_BIG_HEIGHTS = (VowelHeight.OPEN, VowelHeight.NEAR_OPEN)
_OPEN_HEIGHTS = (VowelHeight.OPEN, VowelHeight.NEAR_OPEN)


def _weighted_choice(rng: random.Random, options: tuple):
    weights = [max(o.prevalence, 0.001) for o in options]
    return rng.choices(options, weights=weights)[0]


def _cluster_weight(cluster: tuple[str, str], by_symbol: dict[str, float]) -> float:
    return max(by_symbol.get(cluster[0], 0.001) * by_symbol.get(cluster[1], 0.001), 0.001)


def _build_onset(
    rng: random.Random, inventory: PhonemeInventory, structure: SyllableStructure, by_symbol: dict[str, float]
) -> tuple[str, ...]:
    if structure.max_onset == 0:
        return ()
    if structure.max_onset >= 2 and structure.allowed_onset_clusters and rng.random() < 0.3:
        weights = [_cluster_weight(c, by_symbol) for c in structure.allowed_onset_clusters]
        return rng.choices(structure.allowed_onset_clusters, weights=weights)[0]
    return (_weighted_choice(rng, inventory.consonants).ipa,)


def _build_coda(
    rng: random.Random, inventory: PhonemeInventory, structure: SyllableStructure, by_symbol: dict[str, float]
) -> tuple[str, ...]:
    if structure.max_coda == 0 or rng.random() < 0.4:
        return ()
    if structure.max_coda >= 2 and structure.allowed_coda_clusters and rng.random() < 0.2:
        weights = [_cluster_weight(c, by_symbol) for c in structure.allowed_coda_clusters]
        return rng.choices(structure.allowed_coda_clusters, weights=weights)[0]
    candidates = structure.allowed_coda_consonants or inventory.consonant_symbols()
    weights = [by_symbol.get(c, 0.001) for c in candidates]
    return (rng.choices(candidates, weights=weights)[0],)


def _choose_nucleus(
    rng: random.Random,
    inventory: PhonemeInventory,
    harmony_class: VowelBackness | None = None,
    size_bias: str | None = None,
) -> Vowel:
    """``size_bias`` ("small"/"big") is sound symbolism, not phonotactics --
    high front vowels statistically evoke smallness cross-linguistically,
    low back vowels largeness (Sapir 1929 and later replications). Applied
    as a soft preference, same as ``harmony_class``, and after it, so the
    two compose rather than one silently overriding the other."""
    vowels: tuple[Vowel, ...] = inventory.vowels
    if harmony_class is not None:
        matching = tuple(v for v in vowels if v.backness in (harmony_class, VowelBackness.CENTRAL))
        if matching and rng.random() < 0.9:  # small leak, like real harmony exceptions/loans
            vowels = matching
    if size_bias is not None:
        heights = _SMALL_HEIGHTS if size_bias == "small" else _BIG_HEIGHTS
        matching = tuple(v for v in vowels if v.height in heights)
        if matching and rng.random() < 0.8:
            vowels = matching
    return _weighted_choice(rng, vowels)


def build_syllable(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    tone_mark: str = "",
    harmony_class: VowelBackness | None = None,
    size_bias: str | None = None,
) -> str:
    by_symbol = {c.ipa: c.prevalence for c in inventory.consonants}
    onset = _build_onset(rng, inventory, structure, by_symbol)
    nucleus = _choose_nucleus(rng, inventory, harmony_class, size_bias).ipa
    coda = _build_coda(rng, inventory, structure, by_symbol)
    assert structure.is_valid_syllable(onset, coda), (onset, coda)
    return "".join(onset) + nucleus + tone_mark + "".join(coda)


def build_word(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    num_syllables: int,
    tone_marks: tuple[str, ...] = (),
    size_bias: str | None = None,
) -> str:
    marks = tone_marks or ("",) * num_syllables
    harmony_class: VowelBackness | None = None
    if structure.vowel_harmony:
        harmony_class = rng.choice([VowelBackness.FRONT, VowelBackness.BACK])
    return "".join(
        build_syllable(rng, inventory, structure, tone_mark=marks[i], harmony_class=harmony_class, size_bias=size_bias)
        for i in range(num_syllables)
    )


def build_reduplicated_word(
    rng: random.Random,
    inventory: PhonemeInventory,
    manner_classes: tuple[Manner, ...],
    tone_mark: str = "",
) -> str | None:
    """A same-syllable-twice word (``mama``/``papa``-shaped): one onset
    consonant restricted to ``manner_classes``, one vowel preferring open
    height, repeated. Models the cross-linguistic convergence of basic
    kinship terms on the simplest sounds a human infant can produce
    (Jakobson 1960) -- not a phonotactic rule, so it deliberately bypasses
    ``SyllableStructure`` (no coda, no cluster, always legal).

    Returns ``None`` if the inventory has no consonant in any of
    ``manner_classes`` (the caller should fall back to normal generation).
    """
    candidates: tuple[Consonant, ...] = tuple(
        c for c in inventory.consonants if c.manner in manner_classes and not c.ejective
    )
    if not candidates:
        return None
    consonant = _weighted_choice(rng, candidates)
    open_vowels = tuple(v for v in inventory.vowels if v.height in _OPEN_HEIGHTS)
    vowel = _weighted_choice(rng, open_vowels or inventory.vowels)
    syllable = consonant.ipa + vowel.ipa + tone_mark
    return syllable + syllable
