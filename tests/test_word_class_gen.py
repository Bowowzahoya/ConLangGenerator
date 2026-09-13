"""Tests for generation.word_class_gen -- citation-form class-paradigm
generation and application (core.grammar.WordClass)."""

import random

from conlang_generator.core.grammar import MorphologicalType, PositionClass, PositionClassOption, WordClass
from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.phonology import Consonant, Manner, Place, PhonemeInventory, SyllableStructure, Vowel, VowelBackness, VowelHeight
from conlang_generator.core.romanization import STRESS_MARK
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import word_class_gen


def _inventory() -> PhonemeInventory:
    return PhonemeInventory(
        consonants=(
            Consonant(ipa="p", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, prevalence=0.9),
            Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, prevalence=0.9),
            Consonant(ipa="k", place=Place.VELAR, manner=Manner.STOP, voiced=False, prevalence=0.9),
            Consonant(ipa="r", place=Place.ALVEOLAR, manner=Manner.TRILL, voiced=True, prevalence=0.5),
        ),
        vowels=(
            Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=1.0),
            Vowel(ipa="e", height=VowelHeight.CLOSE_MID, backness=VowelBackness.FRONT, rounded=False, prevalence=0.8),
            Vowel(ipa="i", height=VowelHeight.CLOSE, backness=VowelBackness.FRONT, rounded=False, prevalence=0.8),
        ),
    )


def _structure() -> SyllableStructure:
    return SyllableStructure(max_onset=1, max_coda=1)


# --- assign_word_class ---


def test_assign_word_class_returns_none_when_pos_has_no_classes():
    rng = random.Random(0)
    classes = (WordClass(name="x", pos=PartOfSpeech.VERB, suffix=("a",)),)
    assert word_class_gen.assign_word_class(rng, classes, None, PartOfSpeech.NOUN) is None


def test_assign_word_class_always_none_at_full_deviation_rate():
    rng = random.Random(0)
    classes = (WordClass(name="x", pos=PartOfSpeech.NOUN, suffix=("a",)),)
    for _ in range(50):
        assert word_class_gen.assign_word_class(rng, classes, 1.0, PartOfSpeech.NOUN) is None


def test_assign_word_class_never_none_at_zero_deviation_rate_when_classes_exist():
    rng = random.Random(0)
    classes = (WordClass(name="x", pos=PartOfSpeech.NOUN, suffix=("a",)),)
    for _ in range(50):
        assert word_class_gen.assign_word_class(rng, classes, 0.0, PartOfSpeech.NOUN) is not None


def test_assign_word_class_respects_prevalence_weighting():
    rng = random.Random(0)
    classes = (
        WordClass(name="common", pos=PartOfSpeech.NOUN, suffix=("a",), prevalence=0.95),
        WordClass(name="rare", pos=PartOfSpeech.NOUN, suffix=("u",), prevalence=0.05),
    )
    hits = sum(
        1 for _ in range(300) if word_class_gen.assign_word_class(rng, classes, None, PartOfSpeech.NOUN).name == "common"
    )
    assert hits > 250  # overwhelmingly the high-prevalence class


# --- apply_word_class ---


def test_apply_word_class_is_a_no_op_for_none():
    rng = random.Random(0)
    result = word_class_gen.apply_word_class(rng, None, "kat", _inventory(), "", None, 0.0)
    assert result == "kat"


def test_apply_word_class_is_a_no_op_for_an_unmarked_class():
    # A class with no prefix/suffix at all is legal -- real German's own
    # masculine/neuter nouns (see german.yaml).
    rng = random.Random(0)
    unmarked = WordClass(name="unmarked", pos=PartOfSpeech.NOUN)
    result = word_class_gen.apply_word_class(rng, unmarked, "kat", _inventory(), "", None, 0.0)
    assert result == "kat"


def test_apply_word_class_concatenates_prefix_and_suffix():
    rng = random.Random(0)
    cls = WordClass(name="x", pos=PartOfSpeech.NOUN, prefix=("k", "i"), suffix=("a",))
    result = word_class_gen.apply_word_class(rng, cls, "tap", _inventory(), "", None, 0.0)
    assert result.replace(STRESS_MARK, "") == "kitapa"


def test_apply_word_class_restresses_the_full_word_for_final_stress():
    # Regression guard for the real bug this function exists to avoid: a
    # vowel-bearing suffix must shift a "final" stress pattern's own mark
    # to the word's own new true-final syllable, not leave it on the
    # stem's former final syllable (real French's own "parler" would
    # otherwise end up stressed on "par-", not the true final "-ler").
    rng = random.Random(0)
    inventory = _inventory()
    stem = "tapa"  # ta.pa -- an (unmarked) 2-syllable stem
    cls = WordClass(name="-i", pos=PartOfSpeech.VERB, suffix=("i",))
    result = word_class_gen.apply_word_class(rng, cls, stem, inventory, "final", 0.0, 1.0)
    assert result.endswith("i")
    assert STRESS_MARK in result
    vowel_symbols = frozenset(inventory.vowel_symbols())
    mark_index = result.index(STRESS_MARK)
    vowels_after_mark = sum(1 for ch in result[mark_index + 1 :] if ch in vowel_symbols)
    assert vowels_after_mark == 1  # exactly the suffix's own vowel -- the true final syllable, not the stem's former one


def test_apply_word_class_prefix_also_gets_restressed_correctly():
    # Same regression guard, mirrored for a prefix and an "initial"
    # stress pattern (real Swahili-style m-/ki- noun-class prefixes).
    rng = random.Random(0)
    inventory = _inventory()
    stem = "tapa"
    cls = WordClass(name="ki-", pos=PartOfSpeech.NOUN, prefix=("k", "i"))
    result = word_class_gen.apply_word_class(rng, cls, stem, inventory, "initial", 0.0, 1.0)
    assert result.startswith(STRESS_MARK + "ki")


# --- generate_word_classes ---


def test_generate_word_classes_root_and_pattern_gets_no_invented_classes():
    inventory, structure = _inventory(), _structure()
    for seed in range(50):
        rng = random.Random(seed)
        spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile())
        classes, deviation_rate = word_class_gen.generate_word_classes(
            rng, spec, inventory, structure, True, MorphologicalType.FUSIONAL
        )
        assert classes == ()
        assert deviation_rate is None


def test_generate_word_classes_invents_classes_for_an_unmatched_language_sometimes():
    inventory, structure = _inventory(), _structure()
    hits = 0
    for seed in range(200):
        rng = random.Random(seed)
        spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile())
        classes, _ = word_class_gen.generate_word_classes(
            rng, spec, inventory, structure, False, MorphologicalType.FUSIONAL
        )
        if classes:
            hits += 1
    assert hits > 0


def test_generate_word_classes_adopts_frances_own_real_verb_classes_sometimes():
    inventory, structure = _inventory(), _structure()
    hits = 0
    for seed in range(60):
        rng = random.Random(seed)
        spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile(source_languages=("French",)))
        classes, deviation_rate = word_class_gen.generate_word_classes(
            rng, spec, inventory, structure, False, MorphologicalType.FUSIONAL
        )
        verb_classes = {c.name for c in classes if c.pos is PartOfSpeech.VERB}
        if verb_classes == {"-er verbs", "-ir verbs", "-re verbs"}:
            hits += 1
            assert deviation_rate is not None
    assert hits > 0


def test_generate_word_classes_invents_a_harmony_conditioned_class_when_structure_has_vowel_harmony():
    # A language with no source-language influence at all, but this run's
    # own independently-rolled `structure.vowel_harmony=True` -- the
    # invented path should sometimes collapse a POS's own class marking
    # into a single real harmony-conditioned suffix pair instead of N
    # flat classes, the same mechanism a matched Turkish/Finnish/
    # Mongolian-style profile already exercises via reference adoption.
    inventory = _inventory()
    structure = SyllableStructure(max_onset=1, max_coda=1, vowel_harmony=True)
    hits = 0
    for seed in range(400):
        rng = random.Random(seed)
        spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile())
        classes, _ = word_class_gen.generate_word_classes(
            rng, spec, inventory, structure, False, MorphologicalType.FUSIONAL
        )
        harmony_classes = [c for c in classes if c.condition == "vowel_harmony"]
        if harmony_classes:
            hits += 1
            for wc in harmony_classes:
                assert wc.suffix
                assert wc.suffix_alt
                assert wc.prefix == ()
    assert hits > 0


def test_generate_word_classes_never_invents_harmony_classes_without_vowel_harmony():
    inventory = _inventory()
    structure = SyllableStructure(max_onset=1, max_coda=1, vowel_harmony=False)
    for seed in range(200):
        rng = random.Random(seed)
        spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile())
        classes, _ = word_class_gen.generate_word_classes(
            rng, spec, inventory, structure, False, MorphologicalType.FUSIONAL
        )
        assert not any(c.condition == "vowel_harmony" for c in classes)


def test_generate_word_classes_invents_position_classes_for_a_polysynthetic_verb():
    # No source-language influence, but this run's own independently-
    # rolled `morphological_type=POLYSYNTHETIC` -- VERB's own invented
    # class marking should sometimes take the shape of real Navajo-style
    # position-class prefixation instead of a flat prefix/suffix class.
    inventory, structure = _inventory(), _structure()
    hits = 0
    for seed in range(400):
        rng = random.Random(seed)
        spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile())
        classes, _ = word_class_gen.generate_word_classes(
            rng, spec, inventory, structure, False, MorphologicalType.POLYSYNTHETIC
        )
        position_classes_wcs = [c for c in classes if c.pos is PartOfSpeech.VERB and c.position_classes]
        if position_classes_wcs:
            hits += 1
            for wc in position_classes_wcs:
                assert wc.prefix == () and wc.suffix == ()
                for slot in wc.position_classes:
                    assert len(slot.options) >= 2
                    assert any(option.symbols == () for option in slot.options)
    assert hits > 0


def test_generate_word_classes_never_invents_position_classes_without_polysynthetic():
    inventory, structure = _inventory(), _structure()
    for seed in range(200):
        rng = random.Random(seed)
        spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile())
        classes, _ = word_class_gen.generate_word_classes(
            rng, spec, inventory, structure, False, MorphologicalType.FUSIONAL
        )
        assert not any(c.position_classes for c in classes)


def test_source_language_weights_reduce_frances_own_class_adoption_when_lightly_weighted():
    # A lightly-weighted French alongside a heavily-weighted English
    # (which curates no VERB classes of its own) should adopt French's
    # real "-er"/"-ir"/"-re" pool far less often than a heavily-weighted
    # French does -- each matched profile's own adoption roll is now
    # independently scaled by its own weight, not one shared roll at flat
    # strictness regardless of how the named influence is actually split.
    inventory, structure = _inventory(), _structure()

    def _hit_rate(weights: tuple[float, float]) -> float:
        hits = 0
        n = 150
        for seed in range(n):
            rng = random.Random(seed)
            spec = GenerationSpec(
                prompt="p",
                seed=seed,
                traits=TraitProfile(
                    source_languages=("French", "English"),
                    source_language_weights=weights,
                    source_language_strictness=1.0,
                ),
            )
            classes, _ = word_class_gen.generate_word_classes(
            rng, spec, inventory, structure, False, MorphologicalType.FUSIONAL
        )
            verb_classes = {c.name for c in classes if c.pos is PartOfSpeech.VERB}
            if verb_classes == {"-er verbs", "-ir verbs", "-re verbs"}:
                hits += 1
        return hits / n

    french_heavy = _hit_rate((0.9, 0.1))
    french_light = _hit_rate((0.1, 0.9))
    assert french_light < french_heavy


# --- apply_word_class: condition="vowel_harmony"/"final_voicing" ---


def _harmony_inventory() -> PhonemeInventory:
    # Turkish-shaped: a genuine front/back vowel pair (i/u), plus "a"
    # deliberately kept CENTRAL (this project's own global pool
    # convention -- see WordClass.condition's own docstring) so a
    # central-only stem is exercised too.
    return PhonemeInventory(
        consonants=(
            Consonant(ipa="m", place=Place.BILABIAL, manner=Manner.NASAL, voiced=True, prevalence=0.9),
            Consonant(ipa="k", place=Place.VELAR, manner=Manner.STOP, voiced=False, prevalence=0.9),
            Consonant(ipa="d", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=True, prevalence=0.9),
            Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, prevalence=0.9),
        ),
        vowels=(
            Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=1.0),
            Vowel(ipa="i", height=VowelHeight.CLOSE, backness=VowelBackness.FRONT, rounded=False, prevalence=0.8),
            Vowel(ipa="u", height=VowelHeight.CLOSE, backness=VowelBackness.BACK, rounded=True, prevalence=0.8),
        ),
    )


def test_apply_word_class_vowel_harmony_picks_front_suffix_for_a_front_stem():
    rng = random.Random(0)
    cls = WordClass(name="infinitive", pos=PartOfSpeech.VERB, condition="vowel_harmony", suffix=("m", "e"), suffix_alt=("m", "a"))
    result = word_class_gen.apply_word_class(rng, cls, "gil", _harmony_inventory(), "", None, 0.0)
    assert result.replace(STRESS_MARK, "").endswith("me")


def test_apply_word_class_vowel_harmony_picks_back_suffix_for_a_back_stem():
    rng = random.Random(0)
    cls = WordClass(name="infinitive", pos=PartOfSpeech.VERB, condition="vowel_harmony", suffix=("m", "e"), suffix_alt=("m", "a"))
    result = word_class_gen.apply_word_class(rng, cls, "kud", _harmony_inventory(), "", None, 0.0)
    assert result.replace(STRESS_MARK, "").endswith("ma")


def test_apply_word_class_vowel_harmony_uses_the_stems_last_vowel_not_its_first():
    # Real harmony conditions on the vowel nearest the suffix boundary --
    # a front-then-back stem must still agree with its own trailing back
    # vowel, not its leading front one.
    rng = random.Random(0)
    cls = WordClass(name="infinitive", pos=PartOfSpeech.VERB, condition="vowel_harmony", suffix=("m", "e"), suffix_alt=("m", "a"))
    result = word_class_gen.apply_word_class(rng, cls, "kitud", _harmony_inventory(), "", None, 0.0)
    assert result.replace(STRESS_MARK, "").endswith("ma")


def test_apply_word_class_vowel_harmony_falls_back_to_back_for_a_central_only_stem():
    # This project's own global vowel pool classifies "a" as CENTRAL, not
    # BACK (see WordClass.condition's own docstring) -- a stem with no
    # non-central vowel at all (e.g. an all-"a" stem) has no harmony
    # signal to read, and falls back to the back-harmony form.
    rng = random.Random(0)
    cls = WordClass(name="infinitive", pos=PartOfSpeech.VERB, condition="vowel_harmony", suffix=("m", "e"), suffix_alt=("m", "a"))
    result = word_class_gen.apply_word_class(rng, cls, "kad", _harmony_inventory(), "", None, 0.0)
    assert result.replace(STRESS_MARK, "").endswith("ma")


def test_apply_word_class_final_voicing_picks_voiceless_suffix_after_a_voiceless_stem():
    rng = random.Random(0)
    cls = WordClass(name="infinitive", pos=PartOfSpeech.VERB, condition="final_voicing", suffix=("t", "a", "n"), suffix_alt=("d", "a", "n"))
    result = word_class_gen.apply_word_class(rng, cls, "raft", _harmony_inventory(), "", None, 0.0)
    assert result.replace(STRESS_MARK, "").endswith("tan")


def test_apply_word_class_final_voicing_picks_voiced_suffix_after_a_voiced_stem():
    rng = random.Random(0)
    cls = WordClass(name="infinitive", pos=PartOfSpeech.VERB, condition="final_voicing", suffix=("t", "a", "n"), suffix_alt=("d", "a", "n"))
    result = word_class_gen.apply_word_class(rng, cls, "xord", _harmony_inventory(), "", None, 0.0)
    assert result.replace(STRESS_MARK, "").endswith("dan")


def test_apply_word_class_final_voicing_falls_back_to_the_default_suffix_for_a_vowel_final_stem():
    rng = random.Random(0)
    cls = WordClass(name="infinitive", pos=PartOfSpeech.VERB, condition="final_voicing", suffix=("t", "a", "n"), suffix_alt=("d", "a", "n"))
    result = word_class_gen.apply_word_class(rng, cls, "da", _harmony_inventory(), "", None, 0.0)
    assert result.replace(STRESS_MARK, "").endswith("tan")


# --- apply_word_class: position_classes (real Navajo-style polysynthetic prefixes) ---


def test_apply_word_class_position_classes_single_slot_single_option():
    rng = random.Random(0)
    slot = PositionClass(name="classifier", options=(PositionClassOption(name="ł", symbols=("l",), prevalence=1.0),))
    cls = WordClass(name="verb (classifier)", pos=PartOfSpeech.VERB, position_classes=(slot,))
    result = word_class_gen.apply_word_class(rng, cls, "tal", _inventory(), "", None, 0.0)
    assert result.replace(STRESS_MARK, "") == "ltal"


def test_apply_word_class_position_classes_are_concatenated_in_slot_order():
    rng = random.Random(0)
    first = PositionClass(name="outer", options=(PositionClassOption(name="p", symbols=("p",), prevalence=1.0),))
    second = PositionClass(name="inner", options=(PositionClassOption(name="k", symbols=("k",), prevalence=1.0),))
    cls = WordClass(name="verb", pos=PartOfSpeech.VERB, position_classes=(first, second))
    result = word_class_gen.apply_word_class(rng, cls, "tal", _inventory(), "", None, 0.0)
    assert result.replace(STRESS_MARK, "") == "pktal"  # "outer" slot precedes "inner", both precede the stem


def test_apply_word_class_position_classes_zero_symbol_option_is_a_real_choice():
    # A real null/zero morpheme option (WordClass.position_classes's own
    # docstring: Navajo's own zero classifier) -- picking it must leave
    # the stem untouched by this slot, not be treated as "no class."
    rng = random.Random(0)
    slot = PositionClass(name="classifier", options=(PositionClassOption(name="zero", symbols=(), prevalence=1.0),))
    cls = WordClass(name="verb (classifier)", pos=PartOfSpeech.VERB, position_classes=(slot,))
    result = word_class_gen.apply_word_class(rng, cls, "tal", _inventory(), "", None, 0.0)
    assert result.replace(STRESS_MARK, "") == "tal"


def test_apply_word_class_position_classes_respect_option_prevalence():
    rng = random.Random(0)
    slot = PositionClass(
        name="classifier",
        options=(
            PositionClassOption(name="zero", symbols=(), prevalence=0.7),
            PositionClassOption(name="ł", symbols=("l",), prevalence=0.3),
        ),
    )
    cls = WordClass(name="verb (classifier)", pos=PartOfSpeech.VERB, position_classes=(slot,))
    hits = sum(
        1
        for _ in range(400)
        if word_class_gen.apply_word_class(rng, cls, "tal", _inventory(), "", None, 0.0).replace(STRESS_MARK, "") == "tal"
    )
    assert 240 < hits < 340  # roughly 70% zero-classifier, generous band for a 400-draw sample


def test_apply_word_class_position_classes_compose_with_prefix_and_suffix():
    rng = random.Random(0)
    slot = PositionClass(name="classifier", options=(PositionClassOption(name="ł", symbols=("l",), prevalence=1.0),))
    cls = WordClass(
        name="x", pos=PartOfSpeech.VERB, position_classes=(slot,), prefix=("k", "i"), suffix=("a",),
    )
    result = word_class_gen.apply_word_class(rng, cls, "tap", _inventory(), "", None, 0.0)
    assert result.replace(STRESS_MARK, "") == "lkitapa"  # position prefix, then ordinary prefix, then stem, then suffix


def test_apply_word_class_position_classes_alone_are_not_treated_as_a_no_op():
    # Guard regression: a class with only position_classes set (no plain
    # prefix/suffix) must still apply -- Navajo's own real curated class
    # is shaped exactly this way.
    rng = random.Random(0)
    slot = PositionClass(name="classifier", options=(PositionClassOption(name="ł", symbols=("l",), prevalence=1.0),))
    cls = WordClass(name="verb (classifier)", pos=PartOfSpeech.VERB, position_classes=(slot,))
    result = word_class_gen.apply_word_class(rng, cls, "tal", _inventory(), "", None, 0.0)
    assert result != "tal"


def test_apply_word_class_position_classes_restress_correctly_for_a_syllable_slot():
    # A slot contributing a full onset+nucleus syllable (not just a bare
    # consonant, unlike Navajo's own curated classifier) must still be
    # correctly folded into initial-stress restressing.
    rng = random.Random(0)
    inventory = _inventory()
    slot = PositionClass(name="prefix", options=(PositionClassOption(name="ki", symbols=("k", "i"), prevalence=1.0),))
    cls = WordClass(name="x", pos=PartOfSpeech.NOUN, position_classes=(slot,))
    result = word_class_gen.apply_word_class(rng, cls, "tapa", inventory, "initial", 0.0, 1.0)
    assert result.startswith(STRESS_MARK + "ki")


def test_generate_word_classes_full_strictness_suppresses_invented_classes_for_an_uncurated_pos():
    # French only curates VERB word_classes -- at full strictness, NOUN
    # (a POS French's own profile has no opinion on, curated or not)
    # should almost never get an invented class, the same "matched but
    # doesn't have it -> suppress" treatment grammar_gen.py already gives
    # uses_root_and_pattern.
    inventory, structure = _inventory(), _structure()
    hits = 0
    n = 200
    for seed in range(n):
        rng = random.Random(seed)
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("French",), source_language_strictness=1.0)
        )
        classes, _ = word_class_gen.generate_word_classes(
            rng, spec, inventory, structure, False, MorphologicalType.FUSIONAL
        )
        if any(c.pos is PartOfSpeech.NOUN for c in classes):
            hits += 1
    assert hits / n < 0.05  # near-zero, not just "reduced"


def test_generate_word_classes_zero_strictness_still_invents_classes_for_an_uncurated_pos():
    # A no-op at strictness=0.0 -- today's behavior (an unmatched-for-
    # this-POS language still gets the ordinary invented-class base rate)
    # stays unchanged when strictness isn't actually dialed up.
    inventory, structure = _inventory(), _structure()
    hits = 0
    n = 200
    for seed in range(n):
        rng = random.Random(seed)
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("French",), source_language_strictness=0.0)
        )
        classes, _ = word_class_gen.generate_word_classes(
            rng, spec, inventory, structure, False, MorphologicalType.FUSIONAL
        )
        if any(c.pos is PartOfSpeech.NOUN for c in classes):
            hits += 1
    assert hits > 0


def test_generate_word_classes_full_strictness_makes_frances_own_classes_near_certain():
    inventory, structure = _inventory(), _structure()
    hits = 0
    n = 40
    for seed in range(n):
        rng = random.Random(seed)
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("French",), source_language_strictness=1.0)
        )
        classes, _ = word_class_gen.generate_word_classes(
            rng, spec, inventory, structure, False, MorphologicalType.FUSIONAL
        )
        verb_classes = {c.name for c in classes if c.pos is PartOfSpeech.VERB}
        if verb_classes == {"-er verbs", "-ir verbs", "-re verbs"}:
            hits += 1
    assert hits / n > 0.9
