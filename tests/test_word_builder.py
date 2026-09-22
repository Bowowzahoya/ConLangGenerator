"""Tests for word_builder.py's own reduplicated-word path
(build_reduplicated_word) -- specifically its second_tone_mark axis (real
Mandarin kinship reduplication, e.g. 妈妈 māma, carries its own real tone
only on the first syllable, with the second surfacing neutral)."""

import random

from conlang_generator.core.phonology import Consonant, Manner, Place, PhonemeInventory, Vowel, VowelBackness, VowelHeight
from conlang_generator.generation import word_builder

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
