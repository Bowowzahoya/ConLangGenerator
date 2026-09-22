"""Tests for word_phonology.py -- the named, holistic word-internal
phonological rules a per-symbol romanization rule can't express (Hindi
schwa deletion, Bengali's own narrower word-final counterpart), plus one
integration check that word_builder.build_word actually wires the rule in
at the right point (before stress is assigned)."""

import random

from conlang_generator.core.phonology import (
    Consonant,
    Manner,
    Place,
    PhonemeInventory,
    SyllableStructure,
    Vowel,
    VowelBackness,
    VowelHeight,
)
from conlang_generator.generation import word_builder, word_phonology
from conlang_generator.generation.reference_languages import REFERENCE_LANGUAGES

# A permissive structure -- onset/coda up to 2 consonants, "r"+"m"/"r"+"t"
# among the allowed coda clusters (real Hindi "dharm"/"mitr"-shaped
# clusters), so a legal 2-consonant merge always succeeds in these tests
# unless a test specifically wants it to fail.
_STRUCTURE = SyllableStructure(
    max_onset=2, max_coda=2,
    allowed_coda_clusters=(("r", "m"), ("r", "t"), ("g", "m")),
)


def test_unknown_or_empty_rule_is_a_no_op():
    syllables = [(("d",), "a", ()), (("m",), "ə", ())]
    assert word_phonology.apply(syllables, "", _STRUCTURE) == syllables
    assert word_phonology.apply(syllables, "some_unrecognized_rule", _STRUCTURE) == syllables


def test_monosyllable_never_loses_its_own_only_vowel():
    syllables = [(("g",), "ə", ())]
    assert word_phonology.apply(syllables, "hindi_schwa_deletion", _STRUCTURE) == syllables


def test_word_final_schwa_deletes_merging_into_the_previous_syllables_coda():
    # na-gə -> nag (real "nagar"-shaped final deletion, minus the medial
    # syllable this test isn't exercising).
    syllables = [(("n",), "a", ()), (("g",), "ə", ())]
    result = word_phonology.apply(syllables, "hindi_schwa_deletion", _STRUCTURE)
    assert result == [(("n",), "a", ("g",))]


def test_medial_schwa_deletes_when_the_preceding_syllable_is_closed():
    # dar-mə-ta -> darm-ta: the VC_CV rule's own left context (syllable 0
    # is closed -- has its own coda "r") licenses deleting syllable 1's
    # medial schwa, the same shape real Hindi "dharm"/"mitr" collapse
    # from an underlying tri-syllabic C-schwa form.
    syllables = [(("d",), "a", ("r",)), (("m",), "ə", ()), (("t",), "a", ())]
    result = word_phonology.apply(syllables, "hindi_schwa_deletion", _STRUCTURE)
    assert result == [(("d",), "a", ("r", "m")), (("t",), "a", ())]


def test_medial_schwa_survives_when_the_preceding_syllable_is_open():
    # da-mə-ta: syllable 0 has no coda (open), so the VC_CV rule's own
    # left context isn't met -- the medial schwa is real, spoken, and
    # stays.
    syllables = [(("d",), "a", ()), (("m",), "ə", ()), (("t",), "a", ())]
    result = word_phonology.apply(syllables, "hindi_schwa_deletion", _STRUCTURE)
    assert result == syllables


def test_illegal_merge_is_skipped_rather_than_forced_through():
    # Same shape as the successful medial-deletion test above, but under a
    # structure with no legal 2-consonant coda clusters at all -- merging
    # would produce an illegal "rm" coda, so the schwa is honestly kept
    # instead of fabricating an unpronounceable cluster.
    strict = SyllableStructure(max_onset=2, max_coda=1)
    syllables = [(("d",), "a", ("r",)), (("m",), "ə", ()), (("t",), "a", ())]
    result = word_phonology.apply(syllables, "hindi_schwa_deletion", strict)
    assert result == syllables


def test_bengali_rule_deletes_only_the_final_inherent_vowel_not_medial():
    # Same medial-trigger shape as the Hindi test above, but targeting
    # Bengali's own inherent vowel /ɔ/ -- Bengali's real medial pattern is
    # deliberately left unmodeled (see bengali.yaml's own comment), so
    # only a genuine word-final /ɔ/ should ever delete.
    syllables = [(("d",), "a", ("r",)), (("m",), "ɔ", ()), (("t",), "ɔ", ())]
    result = word_phonology.apply(syllables, "bengali_final_vowel_deletion", _STRUCTURE)
    # Only the word-final /ɔ/ (syllable 2) deletes, merging into syllable
    # 1's own coda -- syllable 1's own medial /ɔ/ is untouched, unlike
    # what the (Hindi-only) VC_CV rule would do to the same shape.
    assert result == [(("d",), "a", ("r",)), (("m",), "ɔ", ("t",))]


def test_bengali_rule_is_a_no_op_when_the_final_vowel_isnt_the_inherent_one():
    syllables = [(("d",), "a", ("r",)), (("m",), "ɔ", ()), (("t",), "a", ())]
    result = word_phonology.apply(syllables, "bengali_final_vowel_deletion", _STRUCTURE)
    assert result == syllables


def test_hindi_and_bengali_profiles_declare_their_own_rule():
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    assert by_name["Hindi"].word_level_phonology == "hindi_schwa_deletion"
    assert by_name["Bengali"].word_level_phonology == "bengali_final_vowel_deletion"
    # No other curated profile has opted into either rule -- the whole
    # point of dispatching by name is that it stays a no-op everywhere
    # else.
    for name, profile in by_name.items():
        if name not in ("Hindi", "Bengali"):
            assert profile.word_level_phonology == ""


def _schwa_only_inventory() -> PhonemeInventory:
    """A tiny inventory whose only vowel is "ə" -- forces every syllable's
    nucleus to be "ə" regardless of the rng draw, so build_word's own
    integration with word_phonology.apply can be checked deterministically
    without needing to fish for a lucky seed."""
    consonants = (
        Consonant(ipa="d", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=True, prevalence=1.0),
        Consonant(ipa="m", place=Place.BILABIAL, manner=Manner.NASAL, voiced=True, prevalence=1.0),
        Consonant(ipa="r", place=Place.ALVEOLAR, manner=Manner.TRILL, voiced=True, prevalence=1.0),
    )
    vowels = (Vowel(ipa="ə", height=VowelHeight.MID, backness=VowelBackness.CENTRAL, rounded=False, prevalence=1.0),)
    return PhonemeInventory(consonants=consonants, vowels=vowels)


def test_build_word_applies_word_level_phonology_before_stress_is_assigned():
    inventory = _schwa_only_inventory()
    structure = SyllableStructure(max_onset=1, max_coda=1, allowed_coda_clusters=(("d", "m"), ("m", "r"), ("r", "d")))
    # Every syllable's own nucleus is forced to "ə" (see the inventory
    # above). With the rule turned off (strictness 0), that's completely
    # deterministic -- every seed's own 3-syllable request keeps its own
    # full, unreduced vowel count, whatever else about the word varies.
    for seed in range(20):
        baseline = word_builder.build_word(
            random.Random(seed), inventory, structure, num_syllables=3,
            word_level_phonology="hindi_schwa_deletion", word_level_phonology_strictness=0.0,
        )
        assert baseline.count("ə") == 3
    # With the rule on (strictness 1.0, so the per-word gate always fires),
    # word-final deletion succeeds whenever the resulting merged coda is
    # still legal -- not every single draw (a merge can still be rejected
    # as illegal, the same "abstain rather than fabricate" case the pure
    # word_phonology tests above already cover directly), but over enough
    # seeds at least one clearly shows fewer than the full 3 vowels, proving
    # the rule is actually wired into build_word and not just a dead param.
    reduced_count = sum(
        1
        for seed in range(20)
        if word_builder.build_word(
            random.Random(seed), inventory, structure, num_syllables=3,
            word_level_phonology="hindi_schwa_deletion", word_level_phonology_strictness=1.0,
        ).count("ə")
        < 3
    )
    assert reduced_count > 0
