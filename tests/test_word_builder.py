"""Tests for word_builder.py's own reduplicated-word path
(build_reduplicated_word) -- specifically its second_tone_mark axis (real
Mandarin kinship reduplication, e.g. 妈妈 māma, carries its own real tone
only on the first syllable, with the second surfacing neutral) -- and
``safe_affix_junction``, the curated-affix cluster-legality guard found
investigating a real reported Tweak bug (see its own docstring)."""

import random

from conlang_generator.core.phonology import (
    Consonant, Manner, Place, PhonemeInventory, SyllableStructure, Vowel, VowelBackness, VowelHeight,
)
from conlang_generator.generation import word_builder


def _french_like_inventory() -> PhonemeInventory:
    consonants = (
        Consonant(ipa="ʃ", place=Place.POSTALVEOLAR, manner=Manner.FRICATIVE, voiced=False, prevalence=1.0),
        Consonant(ipa="f", place=Place.LABIODENTAL, manner=Manner.FRICATIVE, voiced=False, prevalence=1.0),
        Consonant(ipa="ʁ", place=Place.UVULAR, manner=Manner.FRICATIVE, voiced=True, prevalence=1.0),
    )
    vowels = (Vowel(ipa="ə", height=VowelHeight.MID, backness=VowelBackness.CENTRAL, rounded=False, prevalence=1.0),)
    return PhonemeInventory(consonants=consonants, vowels=vowels)


def test_safe_affix_junction_inserts_a_vowel_for_an_illegal_curated_suffix():
    # The exact real reproduction: a French-sourced language's own
    # freshly-coined "begin" stem "ʃəf" plus French's own real, curated
    # "-re" verb suffix ("ʁ", bare consonant -- french.yaml's own
    # suffix: ["ʁ"]) produced the illegal coda "fʁ" under a structure
    # that only allows a single-consonant coda.
    structure = SyllableStructure(max_onset=2, max_coda=1)
    inventory = _french_like_inventory()
    left, right = word_builder.safe_affix_junction(
        ("ʃ", "ə", "f"), ("ʁ",), inventory, structure, at_right_is_suffix=True
    )
    assert left == ("ʃ", "ə", "f")
    assert right == ("ə", "ʁ")  # epenthetic vowel inserted before the bare suffix


def test_safe_affix_junction_leaves_a_legal_single_consonant_coda_alone():
    structure = SyllableStructure(max_onset=2, max_coda=1)
    inventory = _french_like_inventory()
    left, right = word_builder.safe_affix_junction(
        ("ʃ", "ə"), ("ʁ",), inventory, structure, at_right_is_suffix=True
    )
    assert (left, right) == (("ʃ", "ə"), ("ʁ",))


def test_safe_affix_junction_leaves_a_vowel_initial_suffix_alone():
    structure = SyllableStructure(max_onset=2, max_coda=1)
    inventory = _french_like_inventory()
    left, right = word_builder.safe_affix_junction(
        ("ʃ", "ə", "f"), ("ə", "ʁ"), inventory, structure, at_right_is_suffix=True
    )
    assert (left, right) == (("ʃ", "ə", "f"), ("ə", "ʁ"))


def test_safe_affix_junction_abstains_with_no_structure():
    # root_pattern.py's own optional case -- no structure to check
    # against means no guess, same "abstain" convention everywhere else.
    inventory = _french_like_inventory()
    left, right = word_builder.safe_affix_junction(("ʃ", "ə", "f"), ("ʁ",), inventory, None, at_right_is_suffix=True)
    assert (left, right) == (("ʃ", "ə", "f"), ("ʁ",))


def test_safe_affix_junction_handles_the_prefix_side_symmetrically():
    # Swahili's own real bare "m-"/"n-" noun-class prefixes, directly
    # before a consonant-initial stem.
    structure = SyllableStructure(max_onset=1)
    inventory = _french_like_inventory()
    left, right = word_builder.safe_affix_junction(
        ("m",), ("f", "ə"), inventory, structure, at_right_is_suffix=False
    )
    assert left == ("m", "ə")  # epenthetic vowel inserted after the bare prefix
    assert right == ("f", "ə")

_HIGH_MARK = "́"  # combining acute -- ToneLevel.HIGH's own mark
_NEUTRAL_MARK = "̇"  # combining dot above -- ToneLevel.NEUTRAL's own mark


def _inventory() -> PhonemeInventory:
    consonants = (Consonant(ipa="m", place=Place.BILABIAL, manner=Manner.NASAL, voiced=True, prevalence=1.0),)
    vowels = (Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=1.0),)
    return PhonemeInventory(consonants=consonants, vowels=vowels)


def test_second_tone_mark_defaults_to_the_first_syllables_own_tone():
    # None (the common, non-Mandarin-neutral-tone case) means "same as
    # tone_mark" -- the original, pre-fix behavior for every other
    # tonal language's own kinship words.
    word = word_builder.build_reduplicated_word(
        random.Random(1), _inventory(), (Manner.NASAL,), tone_mark=_HIGH_MARK,
    )
    assert word.count(_HIGH_MARK) == 2
    assert _NEUTRAL_MARK not in word


def test_second_tone_mark_overrides_only_the_second_syllable():
    # Real Mandarin 妈妈 māma-shaped: first syllable real (high), second
    # neutral -- the base consonant+vowel stays identical (still a real
    # reduplicated word), only the tone differs.
    word = word_builder.build_reduplicated_word(
        random.Random(1), _inventory(), (Manner.NASAL,), tone_mark=_HIGH_MARK, second_tone_mark=_NEUTRAL_MARK,
    )
    assert word.count(_HIGH_MARK) == 1
    assert word.count(_NEUTRAL_MARK) == 1
    # Both syllables are still "ma" -- only the trailing tone mark differs
    # between them (a leading stress mark may appear on either half, so
    # this strips it out too rather than trying to split the string in
    # half positionally).
    stripped = word.replace(_HIGH_MARK, "").replace(_NEUTRAL_MARK, "").replace("ˈ", "")
    assert stripped == "mama"
