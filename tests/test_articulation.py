"""Tests for speech.articulation -- the pronunciation guide's plain-
language description content."""

from conlang_generator.generation import phonology_gen
from conlang_generator.speech import articulation
from tests._shared_language import cached_language


def test_describe_consonant_never_crashes_and_is_never_empty():
    for consonant in phonology_gen.ALL_CONSONANTS:
        description = articulation.describe_consonant(consonant)
        assert description and description.endswith(".")


def test_describe_vowel_never_crashes_and_is_never_empty():
    for vowel in phonology_gen.ALL_VOWELS:
        description = articulation.describe_vowel(vowel)
        assert description and description.endswith(".")


def _consonant(ipa: str):
    return next(c for c in phonology_gen.ALL_CONSONANTS if c.ipa == ipa)


def _vowel(ipa: str):
    return next(v for v in phonology_gen.ALL_VOWELS if v.ipa == ipa)


def test_voicing_is_named_explicitly():
    assert "voiceless" in articulation.describe_consonant(_consonant("p"))
    assert "voiced" in articulation.describe_consonant(_consonant("b"))


def test_ejective_modifier_is_named_only_when_set():
    assert "ejective" in articulation.describe_consonant(_consonant("kʼ"))
    assert "ejective" not in articulation.describe_consonant(_consonant("k"))


def test_aspirated_modifier_is_named_only_when_set():
    assert "aspirated" in articulation.describe_consonant(_consonant("kʰ"))
    assert "aspirated" not in articulation.describe_consonant(_consonant("k"))


def test_breathy_modifier_is_named_only_when_set():
    assert "breathy" in articulation.describe_consonant(_consonant("bʱ"))
    assert "breathy" not in articulation.describe_consonant(_consonant("b"))


def test_pharyngealized_modifier_is_named_only_when_set():
    assert "pharyngealized" in articulation.describe_consonant(_consonant("tˤ"))
    assert "pharyngealized" not in articulation.describe_consonant(_consonant("t"))


def test_click_overrides_the_manner_clause():
    description = articulation.describe_consonant(_consonant("ǀ"))
    assert "click" in description


def test_nasalized_modifier_is_named_only_when_set():
    assert "nose" in articulation.describe_vowel(_vowel("ã"))
    assert "nose" not in articulation.describe_vowel(_vowel("a"))


def test_full_inventory_covers_exactly_the_languages_own_symbols():
    language = cached_language(0)
    entries = articulation.full_inventory(language)
    assert {e.ipa for e in entries} == set(language.phonology.all_symbols())
    assert len(entries) == len(set(e.ipa for e in entries))  # no duplicates


def test_word_inventory_is_a_subset_in_first_appearance_order():
    language = cached_language(0)
    word = language.lexicon.entries[0].ipa
    entries = articulation.word_inventory(language, word)
    all_ipa = {e.ipa for e in articulation.full_inventory(language)}
    assert all(e.ipa in all_ipa for e in entries)
    assert len(entries) == len(set(e.ipa for e in entries))  # deduplicated


def test_word_inventory_deduplicates_a_repeated_symbol():
    language = cached_language(0)
    repeated_word = next(
        (e.ipa for e in language.lexicon.entries if len(set(e.ipa)) < len(e.ipa)),
        None,
    )
    if repeated_word is None:
        return  # no repeated-character word in this sample -- nothing to check
    entries = articulation.word_inventory(language, repeated_word)
    ipas = [e.ipa for e in entries]
    assert len(ipas) == len(set(ipas))
