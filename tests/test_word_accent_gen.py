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
        def __init__(self, realization, pattern, rate, length_rate=None, window=None):
            self.word_accent_realization = realization
            self.word_accent_pattern = pattern
            self.word_accent_deviation_rate = rate
            self.word_accent_length_rate = length_rate
            self.word_accent_window = window

    profiles = (_Fake("", "", None), _Fake("glottalization", "monosyllabic_heavy", 0.15), _Fake("pitch", "underived_monosyllable", 0.2))
    assert word_accent_gen.resolve_word_accent(profiles) == ("glottalization", "monosyllabic_heavy", 0.15, None, None)


def test_resolve_word_accent_no_curated_profile_abstains():
    class _Fake:
        word_accent_realization = ""
        word_accent_pattern = ""
        word_accent_deviation_rate = None
        word_accent_length_rate = None
        word_accent_window = None

    assert word_accent_gen.resolve_word_accent((_Fake(), _Fake())) == ("", "", None, None, None)


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


# --- Tone + length extension (real Serbo-Croatian "pitch_and_length") ---

_ACCENT_1_LONG = "̂"  # circumflex, U+0302
_ACCENT_1_SHORT = "̏"  # double grave, U+030F
_ACCENT_2_SHORT = TONE_DIACRITICS[ToneLevel.LOW]  # grave
_ACCENT_2_LONG = TONE_DIACRITICS[ToneLevel.HIGH]  # acute


def test_predict_default_word_accent_initial_falling_elsewhere_rising():
    # Real BCMS generalization: falling on a word-initial syllable or any
    # monosyllable, rising elsewhere.
    assert predict_default_word_accent(1, "a", (), "initial_falling_elsewhere_rising", 0) == WordAccentCategory.ACCENT_1
    assert predict_default_word_accent(3, "a", (), "initial_falling_elsewhere_rising", 0) == WordAccentCategory.ACCENT_1
    assert predict_default_word_accent(3, "a", (), "initial_falling_elsewhere_rising", 1) == WordAccentCategory.ACCENT_2
    assert predict_default_word_accent(3, "a", (), "initial_falling_elsewhere_rising", 2) == WordAccentCategory.ACCENT_2


def test_resolve_word_accent_returns_curated_length_rate():
    class _Fake:
        def __init__(self, realization, pattern, rate, length_rate, window=None):
            self.word_accent_realization = realization
            self.word_accent_pattern = pattern
            self.word_accent_deviation_rate = rate
            self.word_accent_length_rate = length_rate
            self.word_accent_window = window

    profiles = (_Fake("pitch_and_length", "initial_falling_elsewhere_rising", 0.1, 0.6),)
    assert word_accent_gen.resolve_word_accent(profiles) == ("pitch_and_length", "initial_falling_elsewhere_rising", 0.1, 0.6, None)


def test_resolve_word_accent_returns_curated_window():
    class _Fake:
        def __init__(self, realization, pattern, rate, length_rate, window):
            self.word_accent_realization = realization
            self.word_accent_pattern = pattern
            self.word_accent_deviation_rate = rate
            self.word_accent_length_rate = length_rate
            self.word_accent_window = window

    profiles = (_Fake("positional_pitch_accent", "lexical", None, None, 3),)
    assert word_accent_gen.resolve_word_accent(profiles) == ("positional_pitch_accent", "lexical", None, None, 3)


def test_assign_word_accent_with_length_at_zero_strictness_always_returns_none():
    rng = random.Random(0)
    for _ in range(50):
        assert (
            word_accent_gen.assign_word_accent_with_length(
                rng, 1, 0, "initial_falling_elsewhere_rising", 0.0, 0.5, 0.0
            )
            is None
        )


def test_assign_word_accent_with_length_at_full_strictness_matches_the_predicted_default_most_of_the_time():
    rng = random.Random(0)
    hits = sum(
        1
        for _ in range(500)
        if word_accent_gen.assign_word_accent_with_length(
            rng, 3, 0, "initial_falling_elsewhere_rising", 0.02, 0.5, 1.0
        )[0]
        == WordAccentCategory.ACCENT_1
    )
    assert hits > 450  # ~2% deviation rate -> overwhelmingly matches the initial-syllable falling default


def test_mark_word_accent_with_length_none_is_always_unmarked():
    assert word_accent_gen.mark_word_accent_with_length(None) == ""


def test_mark_word_accent_with_length_covers_all_four_real_slavistic_marks():
    assert word_accent_gen.mark_word_accent_with_length((WordAccentCategory.ACCENT_1, True)) == _ACCENT_1_LONG
    assert word_accent_gen.mark_word_accent_with_length((WordAccentCategory.ACCENT_1, False)) == _ACCENT_1_SHORT
    assert word_accent_gen.mark_word_accent_with_length((WordAccentCategory.ACCENT_2, True)) == _ACCENT_2_LONG
    assert word_accent_gen.mark_word_accent_with_length((WordAccentCategory.ACCENT_2, False)) == _ACCENT_2_SHORT


def test_mark_stress_and_word_accent_pitch_and_length_marks_a_monosyllable():
    # Same monosyllable regression this whole feature hinges on (see the
    # binary "glottalization" test above), for the tone+length path.
    rng = random.Random(0)
    symbols = ("h", "u", "n")
    result = word_accent_gen.mark_stress_and_word_accent(
        rng, symbols, frozenset("u"), "final", 0.0, 1.0,
        word_accent_realization="pitch_and_length", word_accent_pattern="initial_falling_elsewhere_rising",
        word_accent_deviation_rate=0.0, word_accent_length_rate=1.0,
    )
    assert STRESS_MARK not in result
    assert result == "h" + "u" + _ACCENT_1_LONG + "n"


def test_apply_never_leaks_the_new_tone_length_marks_into_latin_output():
    scheme = RomanizationScheme(rules=_RULES, vowel_symbols=("u",), word_accent_realization="pitch_and_length")
    assert scheme.apply("hu" + _ACCENT_1_LONG + "n") == "hun"
    assert scheme.apply("hu" + _ACCENT_1_SHORT + "n") == "hun"
    assert scheme.apply("hu" + _ACCENT_2_LONG + "n") == "hun"
    assert scheme.apply("hu" + _ACCENT_2_SHORT + "n") == "hun"


# --- Positional pitch accent (real Japanese) ---

_HIGH = TONE_DIACRITICS[ToneLevel.HIGH]
_LOW = TONE_DIACRITICS[ToneLevel.LOW]


def test_assign_positional_pitch_accent_at_zero_strictness_always_returns_none():
    rng = random.Random(0)
    for _ in range(50):
        assert word_accent_gen.assign_positional_pitch_accent(rng, 3, 0.0) is None


def test_assign_positional_pitch_accent_at_full_strictness_covers_every_real_pattern():
    # An n-syllable word has n+1 real patterns (kernel on syllable 0..n-1,
    # or unaccented) -- over enough draws, every one of them should turn
    # up, confirming this isn't silently collapsing to a narrower set.
    rng = random.Random(0)
    seen = {word_accent_gen.assign_positional_pitch_accent(rng, 3, 1.0) for _ in range(500)}
    assert seen == {None, 0, 1, 2}


def test_mark_positional_pitch_accent_unaccented_is_low_then_high_with_no_drop():
    assert word_accent_gen.mark_positional_pitch_accent(None, 3) == (_LOW, _HIGH, _HIGH)


def test_mark_positional_pitch_accent_kernel_on_first_syllable_is_high_then_low():
    # Real "hashi" (chopsticks): HL.
    assert word_accent_gen.mark_positional_pitch_accent(0, 2) == (_HIGH, _LOW)


def test_mark_positional_pitch_accent_kernel_mid_word_rises_then_drops():
    assert word_accent_gen.mark_positional_pitch_accent(1, 4) == (_LOW, _HIGH, _LOW, _LOW)
    assert word_accent_gen.mark_positional_pitch_accent(2, 4) == (_LOW, _HIGH, _HIGH, _LOW)


def test_mark_positional_pitch_accent_monosyllable():
    assert word_accent_gen.mark_positional_pitch_accent(0, 1) == (_HIGH,)
    assert word_accent_gen.mark_positional_pitch_accent(None, 1) == (_LOW,)


def test_assign_positional_pitch_accent_window_none_matches_original_behavior():
    # window=None (the default) must be byte-identical to omitting the
    # parameter entirely -- Japanese's own generation must never change.
    seen_default = {word_accent_gen.assign_positional_pitch_accent(random.Random(s), 5, 1.0) for s in range(200)}
    seen_explicit_none = {
        word_accent_gen.assign_positional_pitch_accent(random.Random(s), 5, 1.0, None) for s in range(200)
    }
    assert seen_default == seen_explicit_none == {None, 0, 1, 2, 3, 4}


def test_assign_positional_pitch_accent_window_restricts_kernel_candidates():
    # Real Ancient Greek's own trimoric law: a 5-syllable word with
    # window=3 can only ever land the kernel on syllable 2, 3, or 4 (the
    # last 3), never 0 or 1.
    rng = random.Random(0)
    seen = {word_accent_gen.assign_positional_pitch_accent(rng, 5, 1.0, 3) for _ in range(500)}
    assert seen == {None, 2, 3, 4}


def test_assign_positional_pitch_accent_window_wider_than_word_covers_every_syllable():
    # A word shorter than the window still allows every syllable, not a
    # truncated/empty candidate range.
    rng = random.Random(0)
    seen = {word_accent_gen.assign_positional_pitch_accent(rng, 2, 1.0, 3) for _ in range(200)}
    assert seen == {None, 0, 1}


def test_mark_positional_pitch_accent_long_nucleus_false_matches_original_behavior():
    assert word_accent_gen.mark_positional_pitch_accent(1, 4, False) == word_accent_gen.mark_positional_pitch_accent(1, 4)
    assert word_accent_gen.mark_positional_pitch_accent(0, 2, False) == word_accent_gen.mark_positional_pitch_accent(0, 2)


def test_mark_positional_pitch_accent_long_nucleus_at_kernel_gets_circumflex():
    _FALLING = TONE_DIACRITICS[ToneLevel.FALLING]
    # Real Attic acute-vs-circumflex rule: the kernel syllable specifically
    # gets the falling (circumflex) mark instead of plain High when its
    # own nucleus is long -- every other syllable's own mark is unaffected.
    assert word_accent_gen.mark_positional_pitch_accent(1, 4, True) == (_LOW, _FALLING, _LOW, _LOW)
    assert word_accent_gen.mark_positional_pitch_accent(2, 4, True) == (_LOW, _HIGH, _FALLING, _LOW)
    assert word_accent_gen.mark_positional_pitch_accent(0, 2, True) == (_FALLING, _LOW)


def test_mark_stress_and_word_accent_positional_pitch_accent_marks_every_syllable():
    # A real stress mark still lands independently (this function always
    # resolves stress for a multi-syllable word, same as every other
    # realization) -- the point here is that pitch-accent marking doesn't
    # key off where it landed the way every other realization's
    # accented-syllable selection does: every nucleus gets its own H/L
    # mark, not just the stressed one.
    rng = random.Random(1)
    symbols = ("k", "a", "t", "a", "b", "a")
    result = word_accent_gen.mark_stress_and_word_accent(
        rng, symbols, frozenset("a"), "final", 0.0, 1.0,
        word_accent_realization="positional_pitch_accent", word_accent_pattern="lexical",
    )
    assert result.count(_HIGH) + result.count(_LOW) == 3


def test_build_word_positional_pitch_accent_marks_every_syllable_not_just_the_stressed_one():
    inventory = PhonemeInventory(consonants=(_H, _N), vowels=(_U,))
    structure = SyllableStructure(max_onset=1, max_coda=1, allowed_coda_consonants=("n",), excluded_onset_consonants=("n",))
    rng = random.Random(2)
    word = word_builder.build_word(
        rng, inventory, structure, 3,
        word_accent_realization="positional_pitch_accent", word_accent_pattern="lexical",
        word_accent_strictness=1.0,
    )
    assert word.count(_HIGH) + word.count(_LOW) == 3


def test_apply_never_leaks_positional_pitch_accent_marks_into_latin_output():
    scheme = RomanizationScheme(rules=_RULES, vowel_symbols=("u",), word_accent_realization="positional_pitch_accent")
    assert scheme.apply("hu" + _HIGH + "n") == "hun"
    assert scheme.apply("hu" + _LOW + "n") == "hun"
