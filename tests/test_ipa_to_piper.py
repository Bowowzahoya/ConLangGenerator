"""Tests for speech.ipa_to_piper -- converting this project's own IPA
notation into a flat list of Piper phoneme strings."""

from conlang_generator.generation import phonology_gen
from conlang_generator.speech import ipa_to_piper


def test_convert_symbol_covers_every_symbol_in_the_global_phoneme_pool_without_crashing():
    all_symbols = [c.ipa for c in phonology_gen.ALL_CONSONANTS] + [v.ipa for v in phonology_gen.ALL_VOWELS]
    for symbol in all_symbols:
        result = ipa_to_piper.convert_symbol(symbol)
        assert result.fidelity in ("exact", "approximate", "poor")
        if result.fidelity != "poor":
            assert result.phonemes  # never empty unless genuinely unresolvable


def test_no_symbol_in_the_global_pool_falls_back_to_poor():
    # Empirically verified: with the "g" notation fix and the three
    # genuinely-absent diacritics dropped, every symbol in this
    # project's own pool resolves to at least one real Piper phoneme --
    # "poor" is a defensive fallback for a future symbol, not something
    # any symbol here should ever hit.
    all_symbols = [c.ipa for c in phonology_gen.ALL_CONSONANTS] + [v.ipa for v in phonology_gen.ALL_VOWELS]
    assert all(ipa_to_piper.convert_symbol(s).fidelity != "poor" for s in all_symbols)


def test_convert_symbol_plain_consonants_and_vowels_map_directly():
    assert ipa_to_piper.convert_symbol("p") == ipa_to_piper.SymbolConversion(("p",), "exact")
    assert ipa_to_piper.convert_symbol("a") == ipa_to_piper.SymbolConversion(("a",), "exact")
    assert ipa_to_piper.convert_symbol("ʃ") == ipa_to_piper.SymbolConversion(("ʃ",), "exact")


def test_convert_symbol_applies_the_ascii_g_notation_fix():
    # This project stores plain ASCII "g" by its own convention; Piper's
    # own vocabulary uses the real IPA script g -- a lossless notation
    # fix, not an approximation.
    assert ipa_to_piper.convert_symbol("g") == ipa_to_piper.SymbolConversion(("ɡ",), "exact")


def test_convert_symbol_decomposes_an_affricate_into_its_own_base_letters():
    assert ipa_to_piper.convert_symbol("tʃ") == ipa_to_piper.SymbolConversion(("t", "ʃ"), "exact")
    assert ipa_to_piper.convert_symbol("dʒ") == ipa_to_piper.SymbolConversion(("d", "ʒ"), "exact")


def test_convert_symbol_decomposes_a_long_vowel_and_a_diphthong():
    assert ipa_to_piper.convert_symbol("aː") == ipa_to_piper.SymbolConversion(("a", "ː"), "exact")
    assert ipa_to_piper.convert_symbol("ai") == ipa_to_piper.SymbolConversion(("a", "i"), "exact")


def test_convert_symbol_drops_the_ejective_marker_as_approximate():
    assert ipa_to_piper.convert_symbol("kʼ") == ipa_to_piper.SymbolConversion(("k",), "approximate")


def test_convert_symbol_drops_breathy_and_voiceless_ring_as_approximate():
    assert ipa_to_piper.convert_symbol("bʱ").fidelity == "approximate"
    assert "ʱ" not in ipa_to_piper.convert_symbol("bʱ").phonemes
    assert ipa_to_piper.convert_symbol("r̥").fidelity == "approximate"


def test_convert_symbol_click_letters_map_directly():
    # Piper's own vocabulary (derived from espeak-ng's universal phoneme
    # repertoire) already has real click letters -- no fallback needed.
    assert ipa_to_piper.convert_symbol("ǀ") == ipa_to_piper.SymbolConversion(("ǀ",), "exact")


def test_convert_word_strips_word_accent_mark_and_keeps_stress_in_place():
    from conlang_generator.core.romanization import STRESS_MARK

    assert ipa_to_piper.convert_word(f"{STRESS_MARK}kat") == ["ˈ", "k", "a", "t"]
    assert ipa_to_piper.convert_word("katˀmat") == ["k", "a", "t", "m", "a", "t"]  # WORD_ACCENT_MARK dropped


def test_convert_word_drops_tone_diacritics():
    from conlang_generator.core.phonology import ToneLevel, TONE_DIACRITICS

    tonal = "ma" + TONE_DIACRITICS[ToneLevel.HIGH]
    assert ipa_to_piper.convert_word(tonal) == ["m", "a"]
