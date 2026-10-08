"""Tests for speech.ipa_to_kirshenbaum -- converting this project's own
IPA notation into espeak-ng's Kirshenbaum ASCII-IPA phoneme mnemonics."""

from conlang_generator.core.romanization import STRESS_MARK
from conlang_generator.generation import phonology_gen
from conlang_generator.speech import ipa_to_kirshenbaum


def test_convert_symbol_covers_every_symbol_in_the_global_phoneme_pool_without_crashing():
    all_symbols = [c.ipa for c in phonology_gen.ALL_CONSONANTS] + [v.ipa for v in phonology_gen.ALL_VOWELS]
    for symbol in all_symbols:
        result = ipa_to_kirshenbaum.convert_symbol(symbol)
        assert result.mnemonic  # never empty
        assert result.mnemonic.isascii()  # always valid espeak-ng bracket-notation input
        assert result.fidelity in ("exact", "approximate", "poor")


def test_convert_symbol_plain_consonants_and_vowels_map_directly():
    assert ipa_to_kirshenbaum.convert_symbol("p") == ipa_to_kirshenbaum.SymbolConversion("p", "exact")
    assert ipa_to_kirshenbaum.convert_symbol("a") == ipa_to_kirshenbaum.SymbolConversion("a", "exact")
    assert ipa_to_kirshenbaum.convert_symbol("ʃ") == ipa_to_kirshenbaum.SymbolConversion("S", "exact")


def test_convert_symbol_strips_ejective_and_aspiration_modifiers():
    # Stripping a real distinctive feature (ejective/aspiration) to reach a
    # mapping is a genuine loss of information, not just a different spelling.
    assert ipa_to_kirshenbaum.convert_symbol("kʼ") == ipa_to_kirshenbaum.SymbolConversion("k", "approximate")
    assert ipa_to_kirshenbaum.convert_symbol("tʰ") == ipa_to_kirshenbaum.SymbolConversion("t", "approximate")


def test_convert_symbol_long_vowel_appends_kirshenbaum_length_marker():
    # Length is *appended* (Kirshenbaum's own ":" marker), not dropped -- no
    # information is lost, so this stays "exact".
    assert ipa_to_kirshenbaum.convert_symbol("aː") == ipa_to_kirshenbaum.SymbolConversion("a:", "exact")


def test_convert_symbol_nasalized_vowel_is_a_precomposed_codepoint_and_still_converts():
    # "ã" is stored as one real Unicode codepoint (U+00E3), not "a" plus a
    # separate combining tilde -- unlike every other modifier in this
    # pool. Regression guard for that NFD-normalization requirement.
    # Nasalization is appended, same as length -- stays "exact".
    assert ipa_to_kirshenbaum.convert_symbol("ã") == ipa_to_kirshenbaum.SymbolConversion("a~", "exact")


def test_convert_symbol_breathy_and_click_cluster_g_symbols_resolve_to_ascii():
    # The pool writes every g as ASCII "g" -- including the breathy and click-cluster symbols that
    # used to carry the strict-IPA script g (U+0261); see tests/test_pool_uses_ascii_g.
    assert ipa_to_kirshenbaum.convert_symbol("gʱ") == ipa_to_kirshenbaum.SymbolConversion("g", "approximate")
    assert ipa_to_kirshenbaum.convert_symbol("gb") == ipa_to_kirshenbaum.SymbolConversion("gb", "exact")


def test_convert_symbol_diphthong_splits_into_two_known_vowels():
    assert ipa_to_kirshenbaum.convert_symbol("ai") == ipa_to_kirshenbaum.SymbolConversion("ai", "exact")
    assert ipa_to_kirshenbaum.convert_symbol("au") == ipa_to_kirshenbaum.SymbolConversion("au", "exact")
    assert ipa_to_kirshenbaum.convert_symbol("ɔi") == ipa_to_kirshenbaum.SymbolConversion("Oi", "exact")


def test_convert_symbol_click_cluster_falls_back_to_its_own_click_letter():
    result = ipa_to_kirshenbaum.convert_symbol("ŋǀʼ")
    assert result.mnemonic.isascii() and result.mnemonic  # never crashes, never non-ASCII
    assert result.fidelity == "poor"


def test_convert_symbol_direct_hits_that_are_themselves_documented_approximations():
    # A direct _BASE_BY_IPA entry isn't automatically "exact" -- a few are
    # themselves already-documented approximations (no clean Kirshenbaum
    # letter exists, or a nasal onset is lost). Without this distinction,
    # the fidelity rating would silently defeat its own purpose.
    for symbol in ("ɟ", "ʜ", "ʢ", "ɰ", "ɱ", "ʁ", "ʋ", "ɥ", "mb", "nd", "ŋg", "nz"):
        assert ipa_to_kirshenbaum.convert_symbol(symbol).fidelity == "approximate"
    # The rhotic-vowel letter pair is an intentional convergence, not a loss.
    assert ipa_to_kirshenbaum.convert_symbol("ɚ").fidelity == "exact"
    assert ipa_to_kirshenbaum.convert_symbol("ɻ̩").fidelity == "exact"


def test_convert_word_places_stress_before_the_stressed_syllables_onset():
    # "the mountain word" pəˈla -- stress falls on the second syllable.
    result = ipa_to_kirshenbaum.convert_word(f"pə{STRESS_MARK}la")
    assert result == "p@'la"


def test_convert_word_drops_tone_diacritics_without_crashing():
    result = ipa_to_kirshenbaum.convert_word("má")  # "a" + combining acute (high tone)
    assert result == "ma"


def test_convert_word_with_no_stress_or_tone_is_a_plain_concatenation():
    assert ipa_to_kirshenbaum.convert_word("kat") == "kat"
