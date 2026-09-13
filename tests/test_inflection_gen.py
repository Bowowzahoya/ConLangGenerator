"""Tests for generation.inflection_gen -- case/tense/agreement affix
generation (core.grammar.InflectionAffix)."""

import random

from conlang_generator.core.phonology import Consonant, Manner, Place, PhonemeInventory, SyllableStructure, Vowel, VowelBackness, VowelHeight
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import inflection_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient


def _inventory() -> PhonemeInventory:
    return PhonemeInventory(
        consonants=(
            Consonant(ipa="p", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, prevalence=0.9),
            Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, prevalence=0.9),
            Consonant(ipa="k", place=Place.VELAR, manner=Manner.STOP, voiced=False, prevalence=0.9),
        ),
        vowels=(
            Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=1.0),
            Vowel(ipa="i", height=VowelHeight.CLOSE, backness=VowelBackness.FRONT, rounded=False, prevalence=0.8),
        ),
    )


def _structure() -> SyllableStructure:
    return SyllableStructure(max_onset=1, max_coda=1)


def test_generate_case_affixes_returns_one_per_label_in_order():
    rng = random.Random(0)
    cases = ("nominative", "accusative", "genitive")
    affixes = inflection_gen.generate_case_affixes(rng, _inventory(), _structure(), cases)
    assert [a.label for a in affixes] == list(cases)
    for affix in affixes:
        assert affix.suffix  # build_class_suffix always returns at least a nucleus
        assert affix.prefix == ()


def test_generate_case_affixes_empty_for_no_cases():
    rng = random.Random(0)
    assert inflection_gen.generate_case_affixes(rng, _inventory(), _structure(), ()) == ()


def test_generate_tense_affixes_returns_one_per_label_in_order():
    rng = random.Random(0)
    tenses = ("past", "non_past")
    affixes = inflection_gen.generate_tense_affixes(rng, _inventory(), _structure(), tenses)
    assert [a.label for a in affixes] == list(tenses)
    for affix in affixes:
        assert affix.suffix


def test_generate_agreement_affixes_covers_every_agreement_label():
    rng = random.Random(0)
    affixes = inflection_gen.generate_agreement_affixes(rng, _inventory(), _structure())
    assert [a.label for a in affixes] == list(inflection_gen.AGREEMENT_LABELS)
    for affix in affixes:
        assert affix.suffix


def test_generate_language_populates_case_tense_agreement_affixes():
    # End-to-end: generator.py actually wires these into a real
    # GrammarProfile, not just inflection_gen.py's own direct-call tests.
    language = generate_language("Test", GenerationSpec(prompt="p", seed=7), FakeLLMClient())
    grammar = language.grammar
    assert [a.label for a in grammar.case_affixes] == list(grammar.cases)
    assert [a.label for a in grammar.tense_affixes] == list(grammar.tenses)
    assert [a.label for a in grammar.agreement_affixes] == list(inflection_gen.AGREEMENT_LABELS)


def test_generate_language_is_still_deterministic_with_affixes_wired_in():
    spec = GenerationSpec(prompt="test language", seed=7)
    lang1 = generate_language("Test", spec, FakeLLMClient())
    lang2 = generate_language("Test", spec, FakeLLMClient())
    assert lang1 == lang2
