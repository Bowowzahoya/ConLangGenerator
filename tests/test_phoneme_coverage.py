"""Tests for speech.phoneme_coverage -- per-engine, per-phoneme fidelity
for eSpeak-ng and Windows SAPI, the per-word selection mechanism's own
coverage model."""

from conlang_generator.generation import phonology_gen
from conlang_generator.speech import phoneme_coverage


def test_symbol_fidelity_covers_every_symbol_in_the_global_phoneme_pool_without_crashing():
    all_symbols = [c.ipa for c in phonology_gen.ALL_CONSONANTS] + [v.ipa for v in phonology_gen.ALL_VOWELS]
    for symbol in all_symbols:
        for engine in ("espeak", "sapi"):
            assert phoneme_coverage.symbol_fidelity(symbol, engine) in ("exact", "approximate", "poor")


def test_symbol_fidelity_rejects_an_unknown_engine():
    import pytest

    with pytest.raises(ValueError):
        phoneme_coverage.symbol_fidelity("p", "piper")


def test_plain_symbols_are_exact_under_both_engines():
    assert phoneme_coverage.symbol_fidelity("p", "espeak") == "exact"
    assert phoneme_coverage.symbol_fidelity("p", "sapi") == "exact"
    assert phoneme_coverage.symbol_fidelity("a", "espeak") == "exact"
    assert phoneme_coverage.symbol_fidelity("a", "sapi") == "exact"


def test_ejective_is_approximate_under_espeak_and_poor_under_sapi():
    assert phoneme_coverage.symbol_fidelity("kʼ", "espeak") == "approximate"
    assert phoneme_coverage.symbol_fidelity("kʼ", "sapi") == "poor"


def test_breathy_is_approximate_under_espeak_and_poor_under_sapi():
    assert phoneme_coverage.symbol_fidelity("bʱ", "espeak") == "approximate"
    assert phoneme_coverage.symbol_fidelity("bʱ", "sapi") == "poor"


def test_pharyngealized_is_approximate_under_espeak_and_poor_under_sapi():
    assert phoneme_coverage.symbol_fidelity("tˤ", "espeak") == "approximate"
    assert phoneme_coverage.symbol_fidelity("tˤ", "sapi") == "poor"


def test_pharyngeal_place_is_poor_under_sapi():
    # ħ/ʕ are primary-place pharyngeals, not secondary pharyngealization --
    # a distinct case from tˤ above, both landing on "poor" for SAPI.
    assert phoneme_coverage.symbol_fidelity("ħ", "sapi") == "poor"
    assert phoneme_coverage.symbol_fidelity("ʕ", "sapi") == "poor"


def test_a_bare_click_is_exact_under_espeak_but_poor_under_sapi():
    # Kirshenbaum has real, dedicated click letters -- a bare click is a
    # clean 1:1 mapping for eSpeak, unlike a click *cluster* (see below).
    # SAPI has no click phoneme at all in a standard English voice.
    assert phoneme_coverage.symbol_fidelity("ǀ", "espeak") == "exact"
    assert phoneme_coverage.symbol_fidelity("ǀ", "sapi") == "poor"


def test_a_click_cluster_with_extra_features_is_poor_under_espeak_too():
    assert phoneme_coverage.symbol_fidelity("ŋǀʼ", "espeak") == "poor"
    assert phoneme_coverage.symbol_fidelity("ŋǀʼ", "sapi") == "poor"


def test_an_ordinary_non_english_sound_is_approximate_under_sapi():
    # ɸ (voiceless bilabial fricative) isn't a click/ejective/breathy/
    # pharyngeal(ized) sound, and isn't in SAPI_EXACT_SYMBOLS -- an
    # ordinary foreign sound, not an impossible one.
    assert phoneme_coverage.symbol_fidelity("ɸ", "sapi") == "approximate"


def test_word_fidelity_is_the_worst_symbol_in_the_word():
    assert phoneme_coverage.word_fidelity("pata", "espeak") == "exact"
    assert phoneme_coverage.word_fidelity("pakʼa", "espeak") == "approximate"
    assert phoneme_coverage.word_fidelity("paŋǀʼa", "espeak") == "poor"


def test_word_fidelity_an_untoned_word_has_no_default_entries_to_worsen():
    assert phoneme_coverage.word_fidelity("", "espeak") == "exact"
    assert phoneme_coverage.word_fidelity("", "sapi") == "exact"


def test_word_fidelity_forces_poor_under_sapi_when_a_tone_is_present():
    tonal = "pa" + "́"  # high tone (combining acute)
    assert phoneme_coverage.word_fidelity(tonal, "sapi") == "poor"
    # eSpeak voices every tone via its Mandarin voice -- not degraded by
    # a tone mark the way SAPI is.
    assert phoneme_coverage.word_fidelity(tonal, "espeak") == "exact"


def test_describe_gap_is_empty_for_an_exact_word():
    assert phoneme_coverage.describe_gap("pata", "espeak") == ()


def test_describe_gap_names_the_actual_reason():
    assert "ejective" in " ".join(phoneme_coverage.describe_gap("pakʼa", "sapi"))
    assert "click" in " ".join(phoneme_coverage.describe_gap("paǀa", "sapi"))
    assert "breathy" in " ".join(phoneme_coverage.describe_gap("bʱa", "sapi"))
    assert "pharyngealized" in " ".join(phoneme_coverage.describe_gap("tˤa", "sapi"))
    assert "pharyngeal" in " ".join(phoneme_coverage.describe_gap("ħa", "sapi"))


def test_describe_gap_names_tones_under_sapi():
    tonal = "pa" + "́"
    assert "tones" in " ".join(phoneme_coverage.describe_gap(tonal, "sapi"))


def test_describe_gap_does_not_repeat_the_same_reason_twice():
    reasons = phoneme_coverage.describe_gap("kʼakʼa", "sapi")
    assert reasons.count("ejective sounds are only approximated") == 1
