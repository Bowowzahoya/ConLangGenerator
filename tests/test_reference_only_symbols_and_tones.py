"""Symbols real source languages need (retroflex ɭ/ɽ/ʈʂ, pharyngealized zˤ/lˤ,
β/ɸ/ɕ/ʑ/ɦ/ʋ/ɥ/ɴ, the diphthong ou) are modeled but never randomly drawn, and
tone marks in real/seed words make the generated language tonal."""

import random

from conlang_generator.core.phonology import TONE_DIACRITICS, ToneLevel, ToneSystem
from conlang_generator.core.spec import GenerationSpec, SeedExample
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import ipa_tokenizer, phonology_gen, real_words
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient

_NEW = ("β", "ɸ", "ɕ", "ʑ", "ɦ", "ʋ", "ɥ", "ɴ", "ɭ", "ɽ", "ɽʱ", "ʈʂ", "ʈʂʰ", "ɖʐ", "zˤ", "lˤ", "ou")
_SYMBOLS = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)


def _tone(vowel: str, level: ToneLevel) -> str:
    return vowel + TONE_DIACRITICS[level]


def test_the_new_symbols_are_modeled_and_tokenize_atomically():
    for symbol in _NEW:
        assert symbol in _SYMBOLS, symbol
        assert ipa_tokenizer.symbols_only(f"k{symbol}k", _SYMBOLS) == ("k", symbol, "k"), symbol


def test_reference_only_symbols_are_never_drawn_at_random():
    drawn = {c.ipa for c in phonology_gen._DRAWN_CONSONANTS} | {v.ipa for v in phonology_gen._DRAWN_VOWELS}
    assert not drawn & set(_NEW)
    for seed in range(40):
        inventory, *_ = phonology_gen.generate_phonology(random.Random(seed), GenerationSpec(prompt="p", seed=seed))
        assert not (set(inventory.consonant_symbols()) | set(inventory.vowel_symbols())) & set(_NEW)


def test_a_seed_word_forces_a_reference_only_consonant_into_the_inventory():
    spec = GenerationSpec(prompt="p", seed=4, seed_examples=(SeedExample(gloss="water", form="nīr", ipa="niɭ"),))
    inventory, *_ = phonology_gen.generate_phonology(random.Random(4), spec)
    assert "ɭ" in inventory.consonant_symbols()


def test_tone_marks_in_seed_words_make_the_language_tonal_with_those_tones():
    seeds = (
        SeedExample(gloss="water", form="shui", ipa="ʂwe" + TONE_DIACRITICS[ToneLevel.DIPPING]),
        SeedExample(gloss="fire", form="huo", ipa="xwo" + TONE_DIACRITICS[ToneLevel.DIPPING]),
        SeedExample(gloss="sun", form="ri", ipa="ʐi" + TONE_DIACRITICS[ToneLevel.FALLING]),
        SeedExample(gloss="moon", form="yue", ipa="jwe" + TONE_DIACRITICS[ToneLevel.FALLING]),
        SeedExample(gloss="stone", form="shi", ipa="ʂi" + TONE_DIACRITICS[ToneLevel.RISING]),
    )
    _, _, tone_system, _ = phonology_gen.generate_phonology(
        random.Random(9), GenerationSpec(prompt="p", seed=9, seed_examples=seeds)
    )
    assert tone_system.enabled
    assert {ToneLevel.DIPPING, ToneLevel.FALLING, ToneLevel.RISING} <= set(tone_system.levels)


def test_an_untoned_seed_leaves_the_tone_roll_alone():
    seeds = (SeedExample(gloss="water", form="voda", ipa="voda"),)
    plain = phonology_gen.generate_phonology(random.Random(3), GenerationSpec(prompt="p", seed=3))
    seeded = phonology_gen.generate_phonology(random.Random(3), GenerationSpec(prompt="p", seed=3, seed_examples=seeds))
    assert plain[2] == seeded[2]


def test_real_word_tones_are_fitted_to_the_languages_own_tone_system():
    high, rising, falling = ToneLevel.HIGH, ToneLevel.RISING, ToneLevel.FALLING
    assert real_words._fit_tones((rising, falling), ToneSystem()) == ()
    two = ToneSystem(enabled=True, levels=(ToneLevel.LOW, ToneLevel.HIGH))
    assert real_words._fit_tones((high, rising, falling), two) == (high, high, ToneLevel.LOW)
    assert real_words._tones_fit((high,), two) and not real_words._tones_fit((rising,), two)
    assert real_words._tones_fit((), ToneSystem())


def test_tones_are_reattached_to_a_deviated_word_vowel_by_vowel():
    marked = real_words._with_tones("mata", (ToneLevel.HIGH, ToneLevel.FALLING))
    assert ipa_tokenizer.tone_sequence(marked, _SYMBOLS) == (ToneLevel.HIGH, ToneLevel.FALLING)
    assert ipa_tokenizer.strip_tones(marked) == "mata"


def test_an_exact_tonal_real_word_keeps_its_tones_and_records_them(monkeypatch):
    word = "ma" + TONE_DIACRITICS[ToneLevel.FALLING]
    original = real_words.real_words

    def fake(name):
        return {"water": ("mà", word), "fire": ("hǒ", "xo" + TONE_DIACRITICS[ToneLevel.DIPPING])} if name == "Mandarin" else original(name)

    monkeypatch.setattr(real_words, "real_words", fake)
    traits = TraitProfile(source_languages=("Mandarin",), source_language_strictness=1.0, source_word_strictness=1.0)
    language = generate_language("T", GenerationSpec(prompt="p", seed=2, traits=traits), FakeLLMClient())
    assert language.tone_system.enabled
    water = language.lexicon.by_gloss("water")
    assert water.ipa == word and water.tones == (ToneLevel.FALLING,)
    assert language.lexicon.by_gloss("fire").tones == (ToneLevel.DIPPING,)
