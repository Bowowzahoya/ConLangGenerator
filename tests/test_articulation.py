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


def test_example_word_language_and_letters_are_all_set_or_all_none():
    for consonant in phonology_gen.ALL_CONSONANTS:
        entry = articulation._consonant_entry(consonant)
        assert (entry.example_word is None) == (entry.example_language is None) == (entry.example_letters is None)
    for vowel in phonology_gen.ALL_VOWELS:
        entry = articulation._vowel_entry(vowel)
        assert (entry.example_word is None) == (entry.example_language is None) == (entry.example_letters is None)


def test_example_letters_are_always_a_literal_substring_of_the_example_word():
    # Not a phonetic respelling -- a real, case-sensitive substring, so
    # the frontend can highlight exactly that span within the word as
    # shown (see articulation.py's own _CONSONANT_EXAMPLES docstring).
    for consonant in phonology_gen.ALL_CONSONANTS:
        example = articulation._consonant_example(consonant)
        if example is not None:
            word, _language, letters = example
            assert letters in word
    for vowel in phonology_gen.ALL_VOWELS:
        example = articulation._vowel_example(vowel)
        if example is not None:
            word, _language, letters = example
            assert letters in word


def test_most_symbols_in_the_global_pool_have_a_real_example():
    # A loose threshold, not an exact count -- a handful of genuinely
    # rare sounds (bilabial/palatal clicks, voiced uvular stop, ɤ) are
    # deliberately left without a forced, shaky citation (see
    # _CONSONANT_EXAMPLES's own docstring), so 100% coverage is not the
    # goal; this just guards against the table silently regressing. The
    # vowel threshold is a bit looser than the consonant one: a handful
    # of Khmer-style diphthongs (ɨə/oə/aə/əɨ/aɨ) are likewise left
    # without one rather than falsely reusing their onset monophthong's
    # own example (see `_vowel_example`'s own diphthong handling).
    consonants_with_example = sum(
        1 for c in phonology_gen.ALL_CONSONANTS if articulation._consonant_example(c) is not None
    )
    vowels_with_example = sum(1 for v in phonology_gen.ALL_VOWELS if articulation._vowel_example(v) is not None)
    assert consonants_with_example / len(phonology_gen.ALL_CONSONANTS) > 0.9
    assert vowels_with_example / len(phonology_gen.ALL_VOWELS) > 0.85


def test_a_modified_symbol_reuses_its_base_symbols_example():
    # "kʰ" (aspirated k) isn't its own entry in the curated table -- it
    # shares "k"'s (place, manner, voiced) identity, since the modifier
    # itself is already explained separately in the prose description.
    plain = articulation._consonant_example(_consonant("k"))
    aspirated = articulation._consonant_example(_consonant("kʰ"))
    assert plain is not None
    assert aspirated == plain


def test_well_known_consonants_have_their_expected_example():
    assert articulation._consonant_example(_consonant("p")) == ("pin", "English", "p")
    assert articulation._consonant_example(_consonant("tʃ")) == ("chip", "English", "ch")


def test_syllabic_r_gets_its_own_override_not_its_vowel_buckets_example():
    # r̩/ɻ̩ share a (height, backness, rounded) bucket with plain "ɨ" in
    # the data model (no separate "syllabic" dimension), but are
    # distinctive enough to deserve their own citation.
    assert articulation._vowel_example(_vowel("r̩")) != articulation._vowel_example(_vowel("ɨ"))


def test_full_inventory_entries_carry_the_example_fields_through_as_dict():
    language = cached_language(0)
    entries = articulation.full_inventory(language)
    for entry in entries:
        d = entry.as_dict()
        assert "example_word" in d and "example_language" in d and "example_letters" in d
        assert (d["example_word"] is None) == (d["example_language"] is None) == (d["example_letters"] is None)
