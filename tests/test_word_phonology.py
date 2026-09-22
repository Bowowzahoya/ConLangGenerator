"""Tests for word_phonology.py -- the named, holistic word-internal
phonological rules a per-symbol romanization rule can't express (Hindi
schwa deletion, Bengali's own narrower word-final counterpart, Korean's
own cross-syllable consonant assimilation), plus integration checks that
word_builder.build_word actually wires each rule in at the right point."""

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


def test_hindi_bengali_korean_profiles_declare_their_own_rule():
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    assert by_name["Hindi"].word_level_phonology == "hindi_schwa_deletion"
    assert by_name["Bengali"].word_level_phonology == "bengali_final_vowel_deletion"
    assert by_name["Korean"].word_level_phonology == "korean_assimilation"
    # No other curated profile has opted into any rule -- the whole point
    # of dispatching by name is that it stays a no-op everywhere else.
    for name, profile in by_name.items():
        if name not in ("Hindi", "Bengali", "Korean"):
            assert profile.word_level_phonology == ""


# A permissive structure for the Korean assimilation tests below -- every
# rewrite target this module's own rules ever produce (m/n/ŋ/l codas,
# pʼ/tʼ/kʼ/tʃʼ/l onsets) is left unrestricted, so a test can isolate the
# rule's own trigger logic without also fighting legality checks (those
# get their own dedicated test further down).
_KOREAN_STRUCTURE = SyllableStructure(max_onset=1, max_coda=1)


def test_nasalization_of_a_stop_coda_before_a_nasal_onset():
    # real 국물 gungmul "soup": /k/+/m/ -> [ŋ]+[m].
    syllables = [(("k",), "u", ("k",)), (("m",), "u", ("l",))]
    result = word_phonology.apply(syllables, "korean_assimilation", _KOREAN_STRUCTURE)
    assert result == [(("k",), "u", ("ŋ",)), (("m",), "u", ("l",))]
    # real 낱말 nanmal "word": /t/+/n/ -> [n]+[n].
    syllables = [(("n",), "a", ("t",)), (("m",), "a", ("l",))]
    result = word_phonology.apply(syllables, "korean_assimilation", _KOREAN_STRUCTURE)
    assert result == [(("n",), "a", ("n",)), (("m",), "a", ("l",))]


def test_lateralization_converges_on_double_l_from_either_direction():
    # real 신라 Silla: /n/+/l/ -> [l]+[l].
    syllables = [(("s",), "i", ("n",)), (("l",), "a", ())]
    result = word_phonology.apply(syllables, "korean_assimilation", _KOREAN_STRUCTURE)
    assert result == [(("s",), "i", ("l",)), (("l",), "a", ())]
    # real 칼날 kalnal "knife blade": /l/+/n/ -> [l]+[l].
    syllables = [(("k",), "a", ("l",)), (("n",), "a", ("l",))]
    result = word_phonology.apply(syllables, "korean_assimilation", _KOREAN_STRUCTURE)
    assert result == [(("k",), "a", ("l",)), (("l",), "a", ("l",))]


def test_tensification_of_a_plain_obstruent_onset_after_an_obstruent_coda():
    # real 학교 hakgyo "school": /k/+/k/ -> [k]+[kʼ].
    syllables = [(("h",), "a", ("k",)), (("k",), "jo", ())]
    result = word_phonology.apply(syllables, "korean_assimilation", _KOREAN_STRUCTURE)
    assert result == [(("h",), "a", ("k",)), (("kʼ",), "jo", ())]
    # real 잡지 japji "magazine": /p/+/tʃ/ -> [p]+[tʃʼ].
    syllables = [(("tʃ",), "a", ("p",)), (("tʃ",), "i", ())]
    result = word_phonology.apply(syllables, "korean_assimilation", _KOREAN_STRUCTURE)
    assert result == [(("tʃ",), "a", ("p",)), (("tʃʼ",), "i", ())]


def test_korean_assimilation_is_a_no_op_when_no_rule_is_triggered():
    # an obstruent coda before a glide onset triggers none of the three
    # rules (not nasal, not {n,l}, not a plain obstruent).
    syllables = [(("k",), "a", ("k",)), (("w",), "a", ())]
    assert word_phonology.apply(syllables, "korean_assimilation", _KOREAN_STRUCTURE) == syllables
    # an open syllable (no coda at all) has nothing to assimilate.
    syllables = [(("k",), "a", ()), (("m",), "a", ())]
    assert word_phonology.apply(syllables, "korean_assimilation", _KOREAN_STRUCTURE) == syllables


def test_korean_assimilation_skips_a_rewrite_the_language_wouldnt_actually_allow():
    # Same nasalization-triggering shape as the passing test above, but
    # under a structure that excludes "ŋ" from coda position entirely --
    # the rewrite is skipped, not forced through, and the pair is left
    # exactly as it started.
    no_velar_nasal_coda = SyllableStructure(max_onset=1, max_coda=1, excluded_coda_consonants=("ŋ",))
    syllables = [(("k",), "u", ("k",)), (("m",), "u", ("l",))]
    result = word_phonology.apply(syllables, "korean_assimilation", no_velar_nasal_coda)
    assert result == syllables


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


def _k_m_inventory() -> PhonemeInventory:
    """A tiny 2-consonant/1-vowel inventory -- "ŋ" is deliberately absent,
    so it can only ever appear in build_word's own output via nasalization
    actually firing (never from ordinary phoneme selection), the same
    "rewrite target not in the drawing pool at all" trick the schwa-only
    inventory above uses for a clean before/after signal."""
    consonants = (
        Consonant(ipa="k", place=Place.VELAR, manner=Manner.STOP, voiced=False, prevalence=1.0),
        Consonant(ipa="m", place=Place.BILABIAL, manner=Manner.NASAL, voiced=True, prevalence=1.0),
    )
    vowels = (Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=1.0),)
    return PhonemeInventory(consonants=consonants, vowels=vowels)


def test_build_word_applies_korean_assimilation():
    inventory = _k_m_inventory()
    structure = SyllableStructure(max_onset=1, max_coda=1)
    # "ŋ" is never drawn by ordinary phoneme selection (see the inventory
    # above) -- with the rule off, it can never appear, whatever the rng
    # draws for onset/coda presence.
    for seed in range(20):
        baseline = word_builder.build_word(
            random.Random(seed), inventory, structure, num_syllables=2,
            word_level_phonology="korean_assimilation", word_level_phonology_strictness=0.0,
        )
        assert "ŋ" not in baseline
    # With the rule on, a "k" coda immediately before an "m" onset -- bound
    # to happen for at least one of enough seeds, given only two
    # consonants to draw from -- nasalizes to "ŋ", proving the rule is
    # actually wired into build_word.
    has_nasalization = any(
        "ŋ"
        in word_builder.build_word(
            random.Random(seed), inventory, structure, num_syllables=2,
            word_level_phonology="korean_assimilation", word_level_phonology_strictness=1.0,
        )
        for seed in range(20)
    )
    assert has_nasalization
