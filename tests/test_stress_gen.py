import random

import pytest

from conlang_generator.core.romanization import STRESS_MARK
from conlang_generator.generation import stress_gen


def test_predict_default_stress_final():
    assert stress_gen.predict_default_stress(3, "final") == 2


def test_predict_default_stress_initial():
    assert stress_gen.predict_default_stress(3, "initial") == 0


def test_predict_default_stress_penultimate():
    assert stress_gen.predict_default_stress(3, "penultimate") == 1


def test_predict_default_stress_unrecognized_pattern_falls_back_to_penultimate():
    assert stress_gen.predict_default_stress(4, "") == 2
    assert stress_gen.predict_default_stress(4, "made-up-value") == 2


def test_predict_default_stress_monosyllable_is_always_zero():
    for pattern in ("final", "initial", "penultimate", "penultimate_or_final_by_coda", ""):
        assert stress_gen.predict_default_stress(1, pattern) == 0


def test_predict_default_stress_spanish_style_coda_conditioning():
    # Real Spanish: penultimate if the word ends in a vowel or n/s, final
    # otherwise -- pizza/pero (vowel), corazón (n) vs. hotel/papel (l).
    pattern = "penultimate_or_final_by_coda"
    assert stress_gen.predict_default_stress(3, pattern, final_coda=()) == 1  # vowel-final
    assert stress_gen.predict_default_stress(3, pattern, final_coda=("n",)) == 1
    assert stress_gen.predict_default_stress(3, pattern, final_coda=("s",)) == 1
    assert stress_gen.predict_default_stress(3, pattern, final_coda=("l",)) == 2
    assert stress_gen.predict_default_stress(3, pattern, final_coda=("d",)) == 2


def test_predict_default_stress_mongolian_style_first_long_vowel():
    # Real Mongolian: stress falls on the first syllable with a long
    # vowel/diphthong, else the initial syllable.
    pattern = "first_long_vowel_else_initial"
    assert stress_gen.predict_default_stress(4, pattern, first_long_syllable=2) == 2
    assert stress_gen.predict_default_stress(4, pattern, first_long_syllable=None) == 0
    assert stress_gen.predict_default_stress(4, pattern) == 0  # default-safe when omitted


def test_first_long_vowel_index_finds_the_first_long_nucleus():
    assert stress_gen.first_long_vowel_index(("a", "e", "aː", "u")) == 2
    assert stress_gen.first_long_vowel_index(("a", "e", "u")) is None
    assert stress_gen.first_long_vowel_index(()) is None
    assert stress_gen.first_long_vowel_index(("aː", "eː")) == 0  # first, not just any


def test_resolve_stress_pattern_first_matched_profile_wins():
    class _Fake:
        def __init__(self, pattern, rate):
            self.stress_pattern = pattern
            self.stress_deviation_rate = rate

    profiles = (_Fake("", None), _Fake("final", 0.1), _Fake("initial", 0.9))
    assert stress_gen.resolve_stress_pattern(profiles) == ("final", 0.1)


def test_resolve_stress_pattern_no_curated_profile_abstains():
    class _Fake:
        stress_pattern = ""
        stress_deviation_rate = None

    assert stress_gen.resolve_stress_pattern((_Fake(), _Fake())) == ("", None)


def test_assign_stress_at_full_strictness_matches_the_curated_pattern_most_of_the_time():
    rng = random.Random(0)
    hits = sum(
        1
        for _ in range(500)
        if stress_gen.assign_stress(rng, 3, (), "final", 0.02, 1.0) == 2
    )
    assert hits > 450  # ~2% deviation rate -> overwhelmingly matches the default


def test_assign_stress_at_zero_strictness_uses_the_generic_baseline_regardless_of_pattern():
    rng = random.Random(0)
    # A curated pattern of "initial" (default index 0) with strictness=0
    # should behave like the *generic* penultimate-leaning baseline, not
    # like "initial" -- i.e. it should land on the generic default (1)
    # far more often than on index 0.
    counts = {0: 0, 1: 0, 2: 0}
    for _ in range(500):
        counts[stress_gen.assign_stress(rng, 3, (), "initial", 0.02, 0.0)] += 1
    assert counts[1] > counts[0]


def test_assign_stress_threads_first_long_syllable_through_to_the_mongolian_pattern():
    rng = random.Random(0)
    hits = sum(
        1
        for _ in range(500)
        if stress_gen.assign_stress(
            rng, 3, (), "first_long_vowel_else_initial", 0.02, 1.0, first_long_syllable=1
        )
        == 1
    )
    assert hits > 450  # ~2% deviation rate -> overwhelmingly matches the long-vowel syllable


def test_assign_stress_never_deviates_for_a_monosyllable():
    rng = random.Random(0)
    for _ in range(50):
        assert stress_gen.assign_stress(rng, 1, (), "lexical", 0.9, 1.0) == 0


def test_syllable_onset_starts_single_intervocalic_consonant_goes_to_the_next_onset():
    # "katab"-shaped: C-V-C-V-C -- the medial "t" starts syllable 2
    # (ka-tab), not syllable 1's coda (kat-ab), under maximal onset.
    symbols = ("k", "a", "t", "a", "b")
    assert stress_gen.syllable_onset_starts(symbols, frozenset("a")) == (0, 2)


def test_syllable_onset_starts_two_medial_consonants_split_coda_then_onset():
    symbols = ("k", "a", "n", "t", "a")
    assert stress_gen.syllable_onset_starts(symbols, frozenset("a")) == (0, 3)


def test_mark_stress_places_the_mark_at_the_default_syllable_for_a_deterministic_pattern():
    rng = random.Random(0)
    symbols = ("k", "a", "t", "a", "b")
    result = stress_gen.mark_stress(rng, symbols, frozenset("a"), "final", 0.0, 1.0)
    assert result == "ka" + STRESS_MARK + "tab"


def test_mark_stress_places_the_mark_on_the_first_long_vowel_syllable_mongolian_style():
    rng = random.Random(0)
    symbols = ("k", "a", "t", "aː", "n")
    result = stress_gen.mark_stress(rng, symbols, frozenset({"a", "aː"}), "first_long_vowel_else_initial", 0.0, 1.0)
    assert result == "ka" + STRESS_MARK + "taːn"


def test_mark_stress_omits_the_mark_for_a_monosyllable():
    rng = random.Random(0)
    symbols = ("k", "a", "b")
    result = stress_gen.mark_stress(rng, symbols, frozenset("a"), "final", 0.0, 1.0)
    assert result == "kab"
    assert STRESS_MARK not in result
