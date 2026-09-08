import random

from conlang_generator.core.phonology import (
    Consonant,
    Manner,
    Place,
    PhonemeInventory,
    SyllableStructure,
    TONE_DIACRITICS,
    ToneLevel,
    Vowel,
    VowelBackness,
    VowelHeight,
    WordAccentCategory,
)
from conlang_generator.core.romanization import (
    STRESS_MARK,
    WORD_ACCENT_MARK,
    RomanizationRule,
    RomanizationScheme,
    predict_default_word_accent,
)
from conlang_generator.generation import word_accent_gen, word_builder


def test_predict_default_word_accent_monosyllabic_heavy_long_nucleus_is_accent_1():
    # Real Danish stød default: a monosyllable with a long/diphthong
    # nucleus (2+ characters) gets accent 1.
    assert predict_default_word_accent(1, "aː", (), "monosyllabic_heavy") == WordAccentCategory.ACCENT_1
    assert predict_default_word_accent(1, "ai", (), "monosyllabic_heavy") == WordAccentCategory.ACCENT_1


def test_predict_default_word_accent_monosyllabic_heavy_sonorant_coda_is_accent_1():
    assert predict_default_word_accent(1, "u", ("n",), "monosyllabic_heavy") == WordAccentCategory.ACCENT_1
    assert predict_default_word_accent(1, "u", ("r",), "monosyllabic_heavy") == WordAccentCategory.ACCENT_1


def test_predict_default_word_accent_monosyllabic_heavy_light_syllable_is_accent_2():
    assert predict_default_word_accent(1, "u", (), "monosyllabic_heavy") == WordAccentCategory.ACCENT_2
    assert predict_default_word_accent(1, "u", ("h",), "monosyllabic_heavy") == WordAccentCategory.ACCENT_2


def test_predict_default_word_accent_monosyllabic_heavy_never_fires_for_a_polysyllable():
    # Even a "heavy"-shaped accented syllable only counts under this
    # pattern when the *whole word* is monosyllabic.
    assert predict_default_word_accent(2, "aː", ("n",), "monosyllabic_heavy") == WordAccentCategory.ACCENT_2


def test_predict_default_word_accent_underived_monosyllable():
    assert predict_default_word_accent(1, "a", (), "underived_monosyllable") == WordAccentCategory.ACCENT_1
    assert predict_default_word_accent(2, "a", (), "underived_monosyllable") == WordAccentCategory.ACCENT_2
    assert predict_default_word_accent(3, "a", ("n",), "underived_monosyllable") == WordAccentCategory.ACCENT_2


def test_predict_default_word_accent_unrecognized_pattern_falls_back_to_accent_2():
    assert predict_default_word_accent(1, "aː", ("n",), "") == WordAccentCategory.ACCENT_2
    assert predict_default_word_accent(1, "aː", ("n",), "made-up-value") == WordAccentCategory.ACCENT_2


def test_resolve_word_accent_first_matched_profile_wins():
    class _Fake:
        def __init__(self, realization, pattern, rate):
            self.word_accent_realization = realization
            self.word_accent_pattern = pattern
            self.word_accent_deviation_rate = rate

    profiles = (_Fake("", "", None), _Fake("glottalization", "monosyllabic_heavy", 0.15), _Fake("pitch", "underived_monosyllable", 0.2))
    assert word_accent_gen.resolve_word_accent(profiles) == ("glottalization", "monosyllabic_heavy", 0.15)


def test_resolve_word_accent_no_curated_profile_abstains():
    class _Fake:
        word_accent_realization = ""
        word_accent_pattern = ""
        word_accent_deviation_rate = None

    assert word_accent_gen.resolve_word_accent((_Fake(), _Fake())) == ("", "", None)


def test_assign_word_accent_at_zero_strictness_always_returns_none():
    rng = random.Random(0)
    for _ in range(50):
        assert word_accent_gen.assign_word_accent(rng, 1, "aː", ("n",), "monosyllabic_heavy", 0.0, 0.0) is None


def test_assign_word_accent_with_no_pattern_always_returns_none_regardless_of_strictness():
    rng = random.Random(0)
    for _ in range(50):
        assert word_accent_gen.assign_word_accent(rng, 1, "aː", ("n",), "", 0.0, 1.0) is None


def test_assign_word_accent_at_full_strictness_matches_the_predicted_default_most_of_the_time():
    rng = random.Random(0)
    hits = sum(
        1
        for _ in range(500)
        if word_accent_gen.assign_word_accent(rng, 1, "aː", (), "monosyllabic_heavy", 0.02, 1.0)
        == WordAccentCategory.ACCENT_1
    )
    assert hits > 450  # ~2% deviation rate -> overwhelmingly matches the heavy-syllable default


def test_mark_word_accent_none_category_is_always_unmarked():
    assert word_accent_gen.mark_word_accent(None, "glottalization") == ""
    assert word_accent_gen.mark_word_accent(None, "pitch") == ""


def test_mark_word_accent_glottalization_only_marks_accent_1():
    assert word_accent_gen.mark_word_accent(WordAccentCategory.ACCENT_1, "glottalization") == WORD_ACCENT_MARK
    assert word_accent_gen.mark_word_accent(WordAccentCategory.ACCENT_2, "glottalization") == ""


def test_mark_word_accent_pitch_marks_both_categories_distinctly():
    accent_1_mark = word_accent_gen.mark_word_accent(WordAccentCategory.ACCENT_1, "pitch")
    accent_2_mark = word_accent_gen.mark_word_accent(WordAccentCategory.ACCENT_2, "pitch")
    assert accent_1_mark == TONE_DIACRITICS[ToneLevel.HIGH]
    assert accent_2_mark == TONE_DIACRITICS[ToneLevel.LOW]
    assert accent_1_mark != accent_2_mark


def test_mark_stress_and_word_accent_marks_a_monosyllable_despite_no_stress_mark():
    # The real, easy-to-get-wrong regression this whole feature hinges on:
    # STRESS_MARK is omitted for a monosyllable (nothing to contrast), but
    # real Danish stød is canonically a *monosyllable* phenomenon -- so
    # word accent must still land even when stress doesn't.
    rng = random.Random(0)
    symbols = ("h", "u", "n")
    result = word_accent_gen.mark_stress_and_word_accent(
        rng, symbols, frozenset("u"), "final", 0.0, 1.0,
        word_accent_realization="glottalization", word_accent_pattern="monosyllabic_heavy", word_accent_deviation_rate=0.0,
    )
    assert STRESS_MARK not in result
    assert result == "hun" + WORD_ACCENT_MARK


def test_mark_stress_and_word_accent_places_pitch_mark_on_the_stressed_syllables_nucleus():
    rng = random.Random(0)
    symbols = ("k", "a", "t", "a", "b")
    result = word_accent_gen.mark_stress_and_word_accent(
        rng, symbols, frozenset("a"), "final", 0.0, 1.0,
        word_accent_realization="pitch", word_accent_pattern="underived_monosyllable", word_accent_deviation_rate=0.0,
    )
    # "final" stress -> last syllable ("tab"); word_accent_pattern
    # predicts ACCENT_2 for this 2-syllable word -> the low (grave) mark.
    assert result == "ka" + STRESS_MARK + "ta" + TONE_DIACRITICS[ToneLevel.LOW] + "b"


def test_mark_stress_and_word_accent_is_a_no_op_when_word_accent_pattern_is_empty():
    rng = random.Random(0)
    symbols = ("k", "a", "t", "a", "b")
    result = word_accent_gen.mark_stress_and_word_accent(rng, symbols, frozenset("a"), "final", 0.0, 1.0)
    assert result == "ka" + STRESS_MARK + "tab"


_H = Consonant(ipa="h", place=Place.GLOTTAL, manner=Manner.FRICATIVE, voiced=False, prevalence=0.5)
_N = Consonant(ipa="n", place=Place.ALVEOLAR, manner=Manner.NASAL, voiced=True, prevalence=0.9)
_U = Vowel(ipa="u", height=VowelHeight.CLOSE, backness=VowelBackness.BACK, rounded=True, prevalence=0.9)


def test_build_word_marks_stod_on_a_monosyllable_with_a_sonorant_coda():
    # The real Danish example this whole feature is grounded in: "hund"
    # /hunˀ/. A monosyllable, so word_builder.build_word never emits
    # STRESS_MARK for it -- word accent still has to land.
    inventory = PhonemeInventory(consonants=(_H, _N), vowels=(_U,))
    structure = SyllableStructure(max_onset=1, max_coda=1, allowed_coda_consonants=("n",), excluded_onset_consonants=("n",))
    rng = random.Random(0)
    word = word_builder.build_word(
        rng, inventory, structure, 1,
        word_accent_realization="glottalization", word_accent_pattern="monosyllabic_heavy",
        word_accent_deviation_rate=0.0, word_accent_strictness=1.0,
    )
    assert word == "hun" + WORD_ACCENT_MARK


_RULES = (
    RomanizationRule(ipa="h", latin="h"),
    RomanizationRule(ipa="u", latin="u"),
    RomanizationRule(ipa="n", latin="n"),
)


def test_apply_never_leaks_the_glottalization_mark_into_latin_output():
    scheme = RomanizationScheme(rules=_RULES, vowel_symbols=("u",), word_accent_realization="glottalization")
    assert scheme.apply("hun" + WORD_ACCENT_MARK) == "hun"


def test_apply_never_leaks_either_pitch_diacritic_into_latin_output():
    scheme = RomanizationScheme(rules=_RULES, vowel_symbols=("u",), word_accent_realization="pitch")
    assert scheme.apply("hu" + TONE_DIACRITICS[ToneLevel.HIGH] + "n") == "hun"
    assert scheme.apply("hu" + TONE_DIACRITICS[ToneLevel.LOW] + "n") == "hun"


def test_apply_still_renders_real_tone_when_this_scheme_is_not_word_accented():
    # Negative control: the pitch-realization stripping in `apply()` must
    # not blanket-suppress these two characters for an ordinary tonal
    # scheme (word_accent_realization="" is the default -- unset here).
    scheme = RomanizationScheme(rules=_RULES, vowel_symbols=("u",))
    assert scheme.apply("hu" + TONE_DIACRITICS[ToneLevel.HIGH] + "n") == "hún"


def test_build_word_never_marks_word_accent_when_pattern_is_unset():
    inventory = PhonemeInventory(consonants=(_H, _N), vowels=(_U,))
    structure = SyllableStructure(max_onset=1, max_coda=1, allowed_coda_consonants=("n",), excluded_onset_consonants=("n",))
    rng = random.Random(0)
    for _ in range(20):
        word = word_builder.build_word(rng, inventory, structure, 1)
        assert WORD_ACCENT_MARK not in word
