"""Tests for speech.ipa_to_kirshenbaum -- converting this project's own
IPA notation into espeak-ng's Kirshenbaum ASCII-IPA phoneme mnemonics."""

from conlang_generator.core.romanization import STRESS_MARK
from conlang_generator.generation import phonology_gen
from conlang_generator.speech import ipa_to_kirshenbaum


def test_convert_symbol_covers_every_symbol_in_the_global_phoneme_pool_without_crashing():
    all_symbols = [c.ipa for c in phonology_gen.ALL_CONSONANTS] + [v.ipa for v in phonology_gen.ALL_VOWELS]
    for symbol in all_symbols:
        result = ipa_to_kirshenbaum.convert_symbol(symbol)
        assert result  # never empty
        assert result.isascii()  # always valid espeak-ng bracket-notation input


def test_convert_symbol_plain_consonants_and_vowels_map_directly():
    assert ipa_to_kirshenbaum.convert_symbol("p") == "p"
    assert ipa_to_kirshenbaum.convert_symbol("a") == "a"
    assert ipa_to_kirshenbaum.convert_symbol("ʃ") == "S"


def test_convert_symbol_strips_ejective_and_aspiration_modifiers():
    assert ipa_to_kirshenbaum.convert_symbol("kʼ") == "k"
    assert ipa_to_kirshenbaum.convert_symbol("tʰ") == "t"


def test_convert_symbol_long_vowel_appends_kirshenbaum_length_marker():
    assert ipa_to_kirshenbaum.convert_symbol("aː") == "a:"


def test_convert_symbol_nasalized_vowel_is_a_precomposed_codepoint_and_still_converts():
    # "ã" is stored as one real Unicode codepoint (U+00E3), not "a" plus a
    # separate combining tilde -- unlike every other modifier in this
    # pool. Regression guard for that NFD-normalization requirement.
    assert ipa_to_kirshenbaum.convert_symbol("ã") == "a~"


def test_convert_symbol_breathy_and_click_cluster_g_symbols_resolve_to_ascii():
    # The pool writes every g as ASCII "g" -- including the breathy and click-cluster symbols that
    # used to carry the strict-IPA script g (U+0261); see tests/test_pool_uses_ascii_g.
    assert ipa_to_kirshenbaum.convert_symbol("gʱ") == "g"
    assert ipa_to_kirshenbaum.convert_symbol("gb") == "gb"


def test_convert_symbol_diphthong_splits_into_two_known_vowels():
    assert ipa_to_kirshenbaum.convert_symbol("ai") == "ai"
    assert ipa_to_kirshenbaum.convert_symbol("au") == "au"
    assert ipa_to_kirshenbaum.convert_symbol("ɔi") == "Oi"


def test_convert_symbol_click_cluster_falls_back_to_its_own_click_letter():
    result = ipa_to_kirshenbaum.convert_symbol("ŋǀʼ")
    assert result.isascii() and result  # never crashes, never non-ASCII


def test_convert_word_places_stress_before_the_stressed_syllables_onset():
    # "the mountain word" pəˈla -- stress falls on the second syllable.
    result = ipa_to_kirshenbaum.convert_word(f"pə{STRESS_MARK}la")
    assert result == "p@'la"


def test_convert_word_drops_tone_diacritics_without_crashing():
    result = ipa_to_kirshenbaum.convert_word("má")  # "a" + combining acute (high tone)
    assert result == "ma"


def test_convert_word_with_no_stress_or_tone_is_a_plain_concatenation():
    assert ipa_to_kirshenbaum.convert_word("kat") == "kat"
