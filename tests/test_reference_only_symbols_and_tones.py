"""Symbols real source languages need (retroflex ɭ/ɽ/ʈʂ, pharyngealized zˤ/lˤ,
β/ɸ/ɕ/ʑ/ɦ/ʋ/ɥ/ɴ, the diphthong ou) are modeled but never randomly drawn, and
tone marks in real/seed words make the generated language tonal."""

import random

from conlang_generator.core.phonology import TONE_DIACRITICS, LexicalToneSandhiRule, ToneLevel, ToneSandhiRule, ToneSystem
from conlang_generator.core.spec import GenerationSpec, SeedExample
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import ipa_tokenizer, phonology_gen, real_words, sound_change, tone_sandhi
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.sound_change import evolve_language
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
    # seed=1 (re-found from seed=3 after the "Missing symbols still" batch's
    # own new phoneme-pool content shifted downstream rng draws -- same
    # "seed-shift from new content" pattern this project's own history has
    # elsewhere).
    seeds = (SeedExample(gloss="water", form="voda", ipa="voda"),)
    plain = phonology_gen.generate_phonology(random.Random(1), GenerationSpec(prompt="p", seed=1))
    seeded = phonology_gen.generate_phonology(random.Random(1), GenerationSpec(prompt="p", seed=1, seed_examples=seeds))
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


def test_a_strict_zulu_sourced_language_takes_its_own_curated_tone_levels():
    # Regression guard for the "Other tone systems" batch: Zulu's own
    # `tone_levels` (real H/L register, pinned explicitly, see its own
    # profile comment) is now non-empty, so a strict-sourced run takes the
    # `_apply_reference_tone_profile`'s own "with_levels" branch instead
    # of falling back to the generic tone_level_count-biased pool pick --
    # a different code path, even though for Zulu's own real 2-level
    # system both happen to land on the same (HIGH, LOW) result.
    traits = TraitProfile(source_languages=("Zulu",), source_language_strictness=1.0)
    language = generate_language("T", GenerationSpec(prompt="p", seed=0, traits=traits), FakeLLMClient())
    assert language.tone_system.enabled
    assert set(language.tone_system.levels) == {ToneLevel.HIGH, ToneLevel.LOW}


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


def test_apply_sandhi_treats_a_single_multi_syllable_word_as_its_own_utterance():
    # Sandhi scope: apply_sandhi was previously only ever called across a
    # *sentence's* own separate words (translator.py) -- a single word's
    # own internal syllable sequence is exactly the same shape of input
    # (a list of tone-bearing IPA), so a real multi-syllable citation form
    # whose own two syllables happen to trigger third-tone sandhi gets the
    # same treatment reused as-is, with no new sandhi logic needed. This
    # is what `conlang pronounce` now does with a looked-up entry's own
    # `ipa` before synthesizing/reporting it (see cli/main.py).
    system = ToneSystem(enabled=True, levels=(ToneLevel.RISING, ToneLevel.DIPPING), sandhi=(_THIRD,))
    citation_word = _marked("nihao", ToneLevel.DIPPING, ToneLevel.DIPPING)
    spoken_word = tone_sandhi.apply_sandhi([citation_word], system)[0]
    assert spoken_word == _marked("nihao", ToneLevel.RISING, ToneLevel.DIPPING)
    assert spoken_word != citation_word


def test_evolved_languages_own_tone_system_and_sandhi_still_apply_correctly(monkeypatch):
    # Sandhi scope: when evolution *doesn't* also fire a tone-system
    # transition (detonalization/tonogenesis -- see
    # test_sound_change.py's own dedicated tests for that separate
    # mechanism), sound_change.py still just copies a language's own
    # ToneSystem (levels *and* sandhi rules) forward unchanged --
    # apply_sandhi is a pure function of whatever ToneSystem it's handed,
    # so an evolved language's own sandhi rules keep working correctly
    # with no extra plumbing needed, the same way translator.py's own
    # sentence-level sandhi already did for an evolved language before
    # this fix (only the single-word/CLI path needed a code change).
    # Detonalization is silenced here on purpose -- this test is about
    # sandhi surviving evolution, a different, orthogonal question from
    # whether the tone *system itself* changes this run.
    monkeypatch.setattr(sound_change, "_evolve_tone_system", lambda *a, **k: (a[1], None))
    traits = TraitProfile(source_languages=("Mandarin",), source_language_strictness=1.0)
    base = generate_language("Base", GenerationSpec(prompt="p", seed=3, traits=traits), FakeLLMClient())
    assert base.tone_system.sandhi  # sanity: Mandarin's own real rules are actually present pre-evolution
    evolved = evolve_language("Evolved", base, 500, TraitProfile(), seed=0)
    assert evolved.tone_system == base.tone_system
    citation_word = _marked("mama", ToneLevel.DIPPING, ToneLevel.DIPPING)
    assert tone_sandhi.apply_sandhi([citation_word], evolved.tone_system) == tone_sandhi.apply_sandhi(
        [citation_word], base.tone_system
    )


_NOT_FALLING_RISING = LexicalToneSandhiRule(gloss="not", before=ToneLevel.FALLING, becomes=ToneLevel.RISING)
_ONE_RULES = (
    LexicalToneSandhiRule(gloss="one", before=ToneLevel.FALLING, becomes=ToneLevel.RISING),
    LexicalToneSandhiRule(gloss="one", before=ToneLevel.HIGH, becomes=ToneLevel.FALLING),
    LexicalToneSandhiRule(gloss="one", before=ToneLevel.RISING, becomes=ToneLevel.FALLING),
    LexicalToneSandhiRule(gloss="one", before=ToneLevel.DIPPING, becomes=ToneLevel.FALLING),
)


def test_lexical_sandhi_changes_only_the_tracked_gloss_before_its_own_trigger_tone():
    # real 不是 bùshì -> búshì: "not" (citation falling) + a falling-tone
    # word becomes rising -- but only because it's specifically "not",
    # not because any falling-toned syllable does this before another.
    system = ToneSystem(enabled=True, levels=(ToneLevel.RISING, ToneLevel.FALLING), lexical_sandhi=(_NOT_FALLING_RISING,))
    bu = _marked("bu", ToneLevel.FALLING)
    shi = _marked("shi", ToneLevel.FALLING)
    spoken = tone_sandhi.apply_sandhi([bu, shi], system, glosses=["not", "verb"])
    assert spoken == [_marked("bu", ToneLevel.RISING), shi]
    # the same two falling-toned syllables, untracked (no glosses passed
    # at all), are left alone -- this is not a general tone-context rule.
    assert tone_sandhi.apply_sandhi([bu, shi], system) == [bu, shi]
    # a different falling-toned word immediately before the same falling
    # verb does NOT change -- the rule is bound to the gloss "not", not
    # to "any falling syllable."
    other = _marked("ta", ToneLevel.FALLING)
    assert tone_sandhi.apply_sandhi([other, shi], system, glosses=["he", "verb"]) == [other, shi]


def test_lexical_sandhi_keeps_the_citation_tone_when_word_final_or_unmatched():
    system = ToneSystem(enabled=True, levels=(ToneLevel.RISING, ToneLevel.FALLING), lexical_sandhi=(_NOT_FALLING_RISING,))
    bu = _marked("bu", ToneLevel.FALLING)
    # utterance-final "not" (real bù said alone, or at the end of a
    # clause) -- no following syllable to trigger the rule, so the
    # citation tone stands, the same real fact every other word's own
    # citation form already has.
    assert tone_sandhi.apply_sandhi([bu], system, glosses=["not"]) == [bu]
    # followed by a non-falling tone -- no rule matches this (gloss,
    # tone) pair, so it's also left alone.
    rising_next = _marked("hao", ToneLevel.RISING)
    assert tone_sandhi.apply_sandhi([bu, rising_next], system, glosses=["not", "adjective"]) == [bu, rising_next]


def test_real_yi_one_needs_all_three_of_its_own_non_falling_contexts():
    # real 一 "one" (citation high): falling -> rising (一样 yīyàng ->
    # yíyàng), and high/rising/dipping all alike -> falling (一天/一年/
    # 一起). Exercises all four curated rules at once.
    system = ToneSystem(
        enabled=True, levels=(ToneLevel.HIGH, ToneLevel.RISING, ToneLevel.DIPPING, ToneLevel.FALLING),
        lexical_sandhi=_ONE_RULES,
    )
    yi = _marked("yi", ToneLevel.HIGH)
    for next_tone, expected in (
        (ToneLevel.FALLING, ToneLevel.RISING),
        (ToneLevel.HIGH, ToneLevel.FALLING),
        (ToneLevel.RISING, ToneLevel.FALLING),
        (ToneLevel.DIPPING, ToneLevel.FALLING),
    ):
        following = _marked("ta", next_tone)  # a real vowel-bearing placeholder -- "x" has none to mark
        spoken = tone_sandhi.apply_sandhi([yi, following], system, glosses=["one", "noun"])
        assert spoken[0] == _marked("yi", expected), next_tone


def test_lexical_sandhi_reads_the_next_words_own_already_general_sandhied_tone():
    # The lexical pass reads its neighbor's tone *after* the general
    # tone-context pass has already run, not its untouched citation tone
    # -- constructed so the difference is observable: the middle word's
    # own citation tone (dipping) would NOT trigger "not"'s own rule
    # (which only fires before falling), but third-tone sandhi first
    # turns it rising... which *still* doesn't match, so "not" stays
    # unchanged either way here -- this test instead directly confirms
    # the general pass runs first by checking its own output tone is
    # what the lexical pass actually saw, via a rule keyed on the
    # post-sandhi value.
    third_tone = ToneSandhiRule(before=ToneLevel.DIPPING, after=ToneLevel.DIPPING, becomes=ToneLevel.RISING)
    not_before_rising = LexicalToneSandhiRule(gloss="not", before=ToneLevel.RISING, becomes=ToneLevel.FALLING)
    system = ToneSystem(
        enabled=True, levels=(ToneLevel.RISING, ToneLevel.DIPPING, ToneLevel.FALLING),
        sandhi=(third_tone,), lexical_sandhi=(not_before_rising,),
    )
    bu = _marked("bu", ToneLevel.DIPPING)
    first_of_pair = _marked("ma", ToneLevel.DIPPING)
    second_of_pair = _marked("ma", ToneLevel.DIPPING)
    # first_of_pair+second_of_pair both start dipping; third-tone sandhi
    # turns first_of_pair into rising -- "not" (also dipping, citation)
    # sits right before that now-rising syllable, so the lexical rule
    # (before=rising -> falling) fires on "not" too, which is only
    # observable if the lexical pass reads the POST-sandhi tone.
    spoken = tone_sandhi.apply_sandhi(
        [bu, first_of_pair, second_of_pair], system, glosses=["not", None, None]
    )
    assert spoken[0] == _marked("bu", ToneLevel.FALLING)
    assert spoken[1] == _marked("ma", ToneLevel.RISING)  # confirms the general pass really did fire first


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
    # A strict single-source run keeps every one of Mandarin's own curated
    # lexical rules too -- certain, the same "kept" mechanic the general
    # sandhi rule above already exercises at full weighted strictness.
    assert set(tone_system.lexical_sandhi) == {_NOT_FALLING_RISING} | set(_ONE_RULES)
    assert {"ʈʂ", "ʈʂʰ", "ɕ"} <= set(inventory.consonant_symbols())


def test_mandarin_kinship_reduplication_puts_neutral_tone_on_the_second_syllable():
    # Neutral tone as grammar: real Mandarin kinship reduplication (妈妈
    # māma, 爸爸 bàba) carries its own real tone only on the first
    # syllable, with the second surfacing neutral -- seed=1 rolls the
    # mama/papa-style reduplicated pattern for "mother" (the common,
    # ~80%-of-the-time path -- see lexicon_gen._KINSHIP_PATTERN_PROBABILITY)
    # at this strict Mandarin-sourced run.
    traits = TraitProfile(source_languages=("Mandarin",), source_language_strictness=1.0)
    language = generate_language("T", GenerationSpec(prompt="p", seed=1, traits=traits), FakeLLMClient())
    mother = language.lexicon.by_gloss("mother")
    assert len(mother.tones) == 2
    assert mother.tones[0] is not ToneLevel.NEUTRAL  # the real, drawn citation tone
    assert mother.tones[1] is ToneLevel.NEUTRAL
    # The stored IPA itself reflects this too, not just the separate
    # `tones` field -- the second syllable's own tone mark is literally
    # the neutral one, not a second copy of the first syllable's mark.
    assert mother.ipa.count(TONE_DIACRITICS[ToneLevel.NEUTRAL]) == 1


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
