"""Symbols real source languages need (retroflex ɭ/ɽ/ʈʂ, pharyngealized zˤ/lˤ,
β/ɸ/ɕ/ʑ/ɦ/ʋ/ɥ/ɴ, the diphthong ou) are modeled but never randomly drawn, and
tone marks in real/seed words make the generated language tonal."""

import random

from conlang_generator.core.phonology import TONE_DIACRITICS, ToneLevel, ToneSandhiRule, ToneSystem
from conlang_generator.core.spec import GenerationSpec, SeedExample
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import ipa_tokenizer, phonology_gen, real_words, tone_sandhi
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


def test_the_curated_mandarin_lexicon_makes_a_tonal_language_with_its_four_tones():
    traits = TraitProfile(source_languages=("Mandarin",), source_language_strictness=1.0, source_word_strictness=1.0)
    language = generate_language("T", GenerationSpec(prompt="p", seed=5, traits=traits), FakeLLMClient())
    assert language.tone_system.enabled
    assert set(language.tone_system.levels) == {
        ToneLevel.HIGH, ToneLevel.RISING, ToneLevel.DIPPING, ToneLevel.FALLING, ToneLevel.NEUTRAL,
    }
    water = language.lexicon.by_gloss("water")
    assert water.romanization == "shuǐ" and water.tones == (ToneLevel.DIPPING,)


_THIRD = ToneSandhiRule(before=ToneLevel.DIPPING, after=ToneLevel.DIPPING, becomes=ToneLevel.RISING)


def _marked(text: str, *tones: ToneLevel) -> str:
    """``text`` with each tone attached to the next vowel in turn."""
    out, remaining = [], list(tones)
    for ch in text:
        out.append(ch)
        if ch in "aeiou" and remaining:
            out.append(TONE_DIACRITICS[remaining.pop(0)])
    return "".join(out)


def test_third_tone_sandhi_changes_the_first_of_two_dipping_syllables():
    system = ToneSystem(enabled=True, levels=(ToneLevel.RISING, ToneLevel.DIPPING), sandhi=(_THIRD,))
    spoken = tone_sandhi.apply_sandhi([_marked("ni", ToneLevel.DIPPING), _marked("hao", ToneLevel.DIPPING)], system)
    assert spoken == [_marked("ni", ToneLevel.RISING), _marked("hao", ToneLevel.DIPPING)]


def test_sandhi_reads_citation_tones_and_leaves_other_tones_and_citation_forms_alone():
    system = ToneSystem(enabled=True, levels=(ToneLevel.RISING, ToneLevel.DIPPING, ToneLevel.HIGH), sandhi=(_THIRD,))
    three = [_marked("ma", ToneLevel.DIPPING)] * 3
    assert tone_sandhi.apply_sandhi(three, system) == [_marked("ma", ToneLevel.RISING)] * 2 + [three[2]]
    mixed = [_marked("ma", ToneLevel.HIGH), _marked("ma", ToneLevel.DIPPING)]
    assert tone_sandhi.apply_sandhi(mixed, system) == mixed
    assert tone_sandhi.apply_sandhi(three, ToneSystem(enabled=True, levels=system.levels)) == three  # no rules
    assert three == [_marked("ma", ToneLevel.DIPPING)] * 3  # input untouched


def test_a_strict_mandarin_run_takes_its_real_tones_neutral_tone_sandhi_and_retroflex_sounds():
    traits = TraitProfile(source_languages=("Mandarin",), source_language_strictness=1.0)
    inventory, _, tone_system, _ = phonology_gen.generate_phonology(
        random.Random(3), GenerationSpec(prompt="p", seed=3, traits=traits)
    )
    assert tone_system.levels == (
        ToneLevel.RISING, ToneLevel.DIPPING, ToneLevel.HIGH, ToneLevel.FALLING, ToneLevel.NEUTRAL,
    ) or set(tone_system.levels) == {
        ToneLevel.HIGH, ToneLevel.RISING, ToneLevel.DIPPING, ToneLevel.FALLING, ToneLevel.NEUTRAL,
    }
    assert _THIRD in tone_system.sandhi
    assert {"ʈʂ", "ʈʂʰ", "ɕ"} <= set(inventory.consonant_symbols())


def test_a_source_language_run_without_the_needed_tones_gets_no_sandhi():
    traits = TraitProfile(source_languages=("Mandarin",), source_language_strictness=0.2)
    _, _, tone_system, _ = phonology_gen.generate_phonology(
        random.Random(1), GenerationSpec(prompt="p", seed=1, traits=traits, force_tonal=True)
    )
    assert all({r.before, r.after, r.becomes} <= set(tone_system.levels) for r in tone_system.sandhi)


def test_the_neutral_tone_never_opens_a_generated_word():
    traits = TraitProfile(source_languages=("Mandarin",), source_language_strictness=1.0)
    language = generate_language("T", GenerationSpec(prompt="p", seed=6, traits=traits), FakeLLMClient())
    assert ToneLevel.NEUTRAL in language.tone_system.levels
    firsts = [e.tones[0] for e in language.lexicon.entries if e.tones]
    assert firsts and ToneLevel.NEUTRAL not in firsts


def test_the_tonal_language_lexicons_carry_their_own_tones():
    from conlang_generator.generation.reference_languages.real_lexicon import real_words

    expected = {
        "Cantonese": {ToneLevel.HIGH, ToneLevel.RISING, ToneLevel.MID, ToneLevel.FALLING, ToneLevel.DIPPING, ToneLevel.LOW},
        "Vietnamese": {ToneLevel.MID, ToneLevel.LOW, ToneLevel.HIGH, ToneLevel.DIPPING, ToneLevel.RISING, ToneLevel.FALLING},
        "Thai": {ToneLevel.MID, ToneLevel.LOW, ToneLevel.FALLING, ToneLevel.HIGH, ToneLevel.RISING},
        "Yoruba": {ToneLevel.LOW, ToneLevel.MID, ToneLevel.HIGH},
    }
    for name, levels in expected.items():
        used = {t for _, ipa in real_words(name).values() for t in ipa_tokenizer.tone_sequence(ipa, _SYMBOLS)}
        assert used == levels, (name, used ^ levels)


def test_a_strict_vietnamese_run_is_tonal_with_its_six_tones():
    traits = TraitProfile(source_languages=("Vietnamese",), source_language_strictness=1.0, source_word_strictness=1.0)
    language = generate_language("T", GenerationSpec(prompt="p", seed=4, traits=traits), FakeLLMClient())
    assert language.tone_system.enabled
    assert len(set(language.tone_system.levels)) == 6
