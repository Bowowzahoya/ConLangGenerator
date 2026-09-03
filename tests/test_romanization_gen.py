import random

import pytest

from conlang_generator.core.phonology import Consonant, Manner, Place, PhonemeInventory, Vowel, VowelBackness, VowelHeight
from conlang_generator.core.romanization import (
    ExoticSymbolStyle,
    OrthographyForce,
    RomanizationRule,
    RomanizationScheme,
    SyllableBoundaryMarker,
    ToneMarkingStrategy,
    VowelLengthStrategy,
)
from conlang_generator.generation.phonology_gen import ALL_CONSONANTS, ALL_VOWELS
from conlang_generator.generation.reference_languages import REFERENCE_LANGUAGES
from conlang_generator.generation.romanization_gen import (
    _CATEGORIES_BY_NAME,
    _DIACRITIC_TABLE,
    _DIGRAPH_TABLE,
    _MONOLETTER_TABLE,
    _apply_orthography_drift,
    _category_from_scheme,
    _generate_doubling_rules,
    _generate_gemination_rules,
    _generate_length_rules,
    _roll_independent_axes,
    evolve_romanization,
    generate_romanization,
)

_SEEDS = range(150)
_DUTCH = next(p for p in REFERENCE_LANGUAGES if p.name == "Dutch")
_CONSONANT_BY_IPA = {c.ipa: c for c in ALL_CONSONANTS}
_VOWEL_BY_IPA = {v.ipa: v for v in ALL_VOWELS}


def _dutch_flavored_inventory() -> PhonemeInventory:
    return PhonemeInventory(
        consonants=tuple(_CONSONANT_BY_IPA[s] for s in _DUTCH.consonants),
        vowels=tuple(_VOWEL_BY_IPA[s] for s in _DUTCH.vowels),
    )


def test_every_reference_orthography_symbol_is_in_that_profiles_own_pool():
    # generate_romanization/evolve_romanization only ever look a symbol up
    # in the reference table when it's already in the inventory being
    # romanized, but a stray typo mapping a symbol the profile doesn't even
    # model would be silently unreachable -- catch that here.
    for profile in REFERENCE_LANGUAGES:
        pool = profile.symbols()
        for rule in profile.orthography:
            assert rule.ipa in pool, (profile.name, rule.ipa)


def test_every_dutch_vowel_has_an_orthography_rule():
    # Regression guard for the missing "ɔ" gap: Dutch is the one profile
    # whose whole vowel system this project models real conventions for
    # (the open/closed length alternation) -- every vowel it declares
    # should have at least one explicit rule, not fall through to the
    # generic style (which can silently give the wrong letter, e.g. "ö"
    # instead of "o" for /ɔ/).
    covered = {rule.ipa for rule in _DUTCH.orthography}
    assert set(_DUTCH.vowels) <= covered


def test_no_contact_language_matches_current_behavior():
    inventory = _dutch_flavored_inventory()
    for seed in (1, 2, 3):
        with_empty = generate_romanization(random.Random(seed), inventory, ())
        with_unmatched = generate_romanization(random.Random(seed), inventory, ("Klingon",))
        assert with_empty == with_unmatched


def _dutch_rule_fraction(contact_languages: tuple[str, ...]) -> float:
    dutch_by_ipa = {rule.ipa: rule.latin for rule in _DUTCH.orthography}
    inventory = _dutch_flavored_inventory()
    hits = 0
    total = 0
    for seed in _SEEDS:
        scheme = generate_romanization(random.Random(seed), inventory, contact_languages)
        by_ipa = {rule.ipa: rule.latin for rule in scheme.rules}
        for ipa, latin in dutch_by_ipa.items():
            total += 1
            hits += by_ipa[ipa] == latin
    return hits / total


def test_dutch_contact_language_biases_romanization_toward_dutch_spelling():
    assert _dutch_rule_fraction(()) < _dutch_rule_fraction(("Dutch",))


def test_evolve_romanization_keeps_old_rules_for_surviving_symbols():
    # exotic_symbol_style set explicitly (DIACRITIC) so evolution's
    # reconstruction (`_category_from_scheme`) has something real to read
    # -- this scheme's own axis fields are the source of truth now, not a
    # guess from which symbol has which letter.
    base_scheme = RomanizationScheme(
        rules=(RomanizationRule(ipa="ʃ", latin="š"), RomanizationRule(ipa="a", latin="a")),
        exotic_symbol_style=ExoticSymbolStyle.DIACRITIC,
    )
    # A new inventory that still has both old symbols plus a genuinely new
    # one ("ə") the old scheme has no rule for.
    new_inventory = PhonemeInventory(
        consonants=(Consonant(ipa="ʃ", place=Place.POSTALVEOLAR, manner=Manner.FRICATIVE, voiced=False),),
        vowels=(
            Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False),
            Vowel(ipa="ə", height=VowelHeight.MID, backness=VowelBackness.CENTRAL, rounded=False),
        ),
    )
    evolved = evolve_romanization(base_scheme, new_inventory, random.Random(1))
    by_ipa = {rule.ipa: rule.latin for rule in evolved.rules}

    assert by_ipa["ʃ"] == "š"  # inherited verbatim, not re-rolled
    assert by_ipa["a"] == "a"  # inherited verbatim, not re-rolled
    assert by_ipa["ə"] == "ě"  # freshly generated, in the inherited diacritic style
    assert evolved.exotic_symbol_style == ExoticSymbolStyle.DIACRITIC


def test_evolve_romanization_uses_the_scheme_s_default_exotic_symbol_style_when_unset():
    # exotic_symbol_style left unset -- RomanizationScheme's own default
    # (DIGRAPH) is what evolution reconstructs and uses for a genuinely
    # new symbol, since there's no more diagnostic-symbol guessing.
    base_scheme = RomanizationScheme(rules=(RomanizationRule(ipa="a", latin="a"),))
    new_inventory = PhonemeInventory(
        consonants=(),
        vowels=(
            Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False),
            Vowel(ipa="ə", height=VowelHeight.MID, backness=VowelBackness.CENTRAL, rounded=False),
        ),
    )
    evolved = evolve_romanization(base_scheme, new_inventory, random.Random(1))
    by_ipa = {rule.ipa: rule.latin for rule in evolved.rules}
    assert by_ipa["ə"] == "e"  # digraph style, the scheme's own default


def test_evolve_romanization_reform_rate_one_always_regenerates():
    # A deliberately non-style-derivable old rule, so "regenerated fresh"
    # is guaranteed to differ regardless of which style gets inferred/used
    # (unlike a real style value, which regeneration could coincidentally
    # reproduce).
    base_scheme = RomanizationScheme(rules=(RomanizationRule(ipa="ʃ", latin="zzq"),))
    new_inventory = PhonemeInventory(
        consonants=(Consonant(ipa="ʃ", place=Place.POSTALVEOLAR, manner=Manner.FRICATIVE, voiced=False),),
        vowels=(),
    )
    evolved = evolve_romanization(base_scheme, new_inventory, random.Random(1), reform_rate=1.0)
    by_ipa = {rule.ipa: rule.latin for rule in evolved.rules}
    assert by_ipa["ʃ"] != "zzq"  # old rule dropped, regenerated fresh instead of inherited


def test_every_pool_symbol_has_a_deliberate_mapping_in_every_style_table():
    # Regression guard: no phoneme should fall through to a raw, non-Latin
    # IPA glyph in any of the three exotic-symbol style tables.
    for symbol in [c.ipa for c in ALL_CONSONANTS] + [v.ipa for v in ALL_VOWELS]:
        if symbol.isascii():
            continue
        assert symbol in _DIGRAPH_TABLE, symbol
        assert _DIGRAPH_TABLE[symbol].isascii(), symbol
        assert symbol in _DIACRITIC_TABLE, symbol
        assert symbol in _MONOLETTER_TABLE, symbol
        assert _MONOLETTER_TABLE[symbol].isascii(), symbol


def test_diphthong_spellings():
    # "ai"/"au"/"ei" need no table entry at all (already plain ASCII, so
    # the identity fallback already spells them correctly) -- the ones
    # with a non-ASCII component do.
    assert "ai" not in _DIGRAPH_TABLE and "ai" not in _DIACRITIC_TABLE and "ai" not in _MONOLETTER_TABLE
    assert _DIGRAPH_TABLE["ɛi"] == "ei"
    assert _DIACRITIC_TABLE["ɛi"] == "ëi"
    assert _MONOLETTER_TABLE["ɛi"] == "ei"
    assert _DIGRAPH_TABLE["œy"] == _DIACRITIC_TABLE["œy"] == _MONOLETTER_TABLE["œy"] == "ui"


def test_orthography_drift_drops_diacritics_and_ejective_marks():
    assert _apply_orthography_drift("ǯëṅk̓", random.Random(1), rate=1.0) == "ʒenk"
    assert _apply_orthography_drift("k'ap'", random.Random(1), rate=1.0) == "kap"
    # rate=0 is a strict no-op, matching every other rule in this module.
    assert _apply_orthography_drift("ǯëṅk̓", random.Random(1), rate=0.0) == "ǯëṅk̓"


def test_generated_scheme_always_logs_axis_metadata():
    # category_name is no longer guaranteed to be one of _CATEGORIES_BY_NAME
    # -- an unforced roll composes its own axes independently and may not
    # match any named anchor -- but it's always set, and tone_markers is
    # populated exactly when tone_strategy actually needs it.
    inventory = _dutch_flavored_inventory()
    for seed in range(20):
        scheme = generate_romanization(random.Random(seed), inventory)
        assert scheme.category_name
        if scheme.tone_strategy in (ToneMarkingStrategy.POSTPOSED_DIGIT, ToneMarkingStrategy.POSTPOSED_LETTER):
            assert scheme.tone_markers
        else:
            assert scheme.tone_markers == ()


def test_generate_length_rules_doubling_produces_the_syllable_conditioned_pair():
    category = _CATEGORIES_BY_NAME["germanic-doubling-style"]
    inventory = PhonemeInventory(
        consonants=(),
        vowels=(
            Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False),
            Vowel(ipa="aː", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, long=True),
        ),
    )
    rules = _generate_length_rules(category, inventory)
    by_syllable = {rule.syllable: rule.latin for rule in rules}
    assert by_syllable[("syllable_closed",)] == "aa"
    assert by_syllable[("syllable_open",)] == "a"


def test_generate_length_rules_macron_is_unconditioned():
    category = _CATEGORIES_BY_NAME["scholarly-macron-style"]
    inventory = PhonemeInventory(
        consonants=(),
        vowels=(
            Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False),
            Vowel(ipa="aː", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, long=True),
        ),
    )
    rules = _generate_length_rules(category, inventory)
    assert len(rules) == 1
    assert rules[0].syllable == ()
    assert rules[0].latin == "ā"


def test_generate_length_rules_skips_a_long_vowel_with_no_short_counterpart():
    category = _CATEGORIES_BY_NAME["germanic-doubling-style"]
    inventory = PhonemeInventory(
        consonants=(),
        vowels=(Vowel(ipa="aː", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, long=True),),
    )
    assert _generate_length_rules(category, inventory) == []


def test_generate_doubling_rules_double_the_consonant_after_a_short_vowel_and_fall_back_otherwise():
    category = _CATEGORIES_BY_NAME["germanic-doubling-style"]
    inventory = PhonemeInventory(
        consonants=(Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False),),
        vowels=(Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False),),
    )
    rules = (RomanizationRule(ipa="a", latin="a"), *_generate_doubling_rules(category, inventory))
    scheme = RomanizationScheme(rules=rules, vowel_symbols=("a",), vowel_length=(("a", "short"),))
    assert scheme.apply("at") == "att"  # short vowel -- doubled
    assert scheme.apply("t") == "t"  # no preceding vowel at all -- unconditioned fallback still applies


def test_category_from_scheme_reconstructs_every_axis_exactly():
    inventory = _dutch_flavored_inventory()
    base = generate_romanization(random.Random(3), inventory, ("Dutch",))
    reconstructed = _category_from_scheme(base)
    assert reconstructed.name == base.category_name
    assert reconstructed.tone_strategy == base.tone_strategy
    assert reconstructed.tone_markers == base.tone_markers
    assert reconstructed.vowel_length_strategy == base.vowel_length_strategy
    assert reconstructed.short_vowel_consonant_doubling == base.short_vowel_consonant_doubling
    assert reconstructed.exotic_symbol_style == base.exotic_symbol_style
    assert reconstructed.syllable_boundary_marker == base.syllable_boundary_marker


def test_category_round_trips_through_evolution_with_no_reform():
    inventory = _dutch_flavored_inventory()
    base = generate_romanization(random.Random(7), inventory, ("Dutch",))
    evolved = evolve_romanization(base, inventory, random.Random(9), reform_rate=0.0)
    assert evolved.category_name == base.category_name
    assert evolved.vowel_length_strategy == base.vowel_length_strategy
    assert evolved.short_vowel_consonant_doubling == base.short_vowel_consonant_doubling
    assert evolved.exotic_symbol_style == base.exotic_symbol_style
    assert evolved.syllable_boundary_marker == base.syllable_boundary_marker


def test_generate_length_rules_silent_e_is_unconditioned_and_uses_the_plain_letter():
    category = _CATEGORIES_BY_NAME["silent-e-style"]
    inventory = PhonemeInventory(
        consonants=(),
        vowels=(
            Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False),
            Vowel(ipa="aː", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, long=True),
        ),
    )
    rules = _generate_length_rules(category, inventory)
    assert len(rules) == 1
    assert rules[0].ipa == "aː"
    assert rules[0].latin == "a"
    assert rules[0].syllable == ()


def test_generate_gemination_rules_doubles_when_marked_and_empty_otherwise():
    inventory = PhonemeInventory(
        consonants=(
            Consonant(ipa="k", place=Place.VELAR, manner=Manner.STOP, voiced=False),
            Consonant(ipa="kː", place=Place.VELAR, manner=Manner.STOP, voiced=False, long=True),
        ),
        vowels=(),
    )
    marked = _CATEGORIES_BY_NAME["gemination-style"]
    rules = _generate_gemination_rules(marked, inventory)
    assert len(rules) == 1
    assert rules[0].ipa == "kː"
    assert rules[0].latin == "kk"
    assert rules[0].syllable == () and rules[0].preceding == ()  # unconditioned

    unmarked = _CATEGORIES_BY_NAME["digraph-style"]
    assert _generate_gemination_rules(unmarked, inventory) == []


def test_gemination_fallback_renders_the_plain_letter_when_unmarked():
    inventory = PhonemeInventory(
        consonants=(
            Consonant(ipa="k", place=Place.VELAR, manner=Manner.STOP, voiced=False),
            Consonant(ipa="kː", place=Place.VELAR, manner=Manner.STOP, voiced=False, long=True),
        ),
        vowels=(Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False),),
    )
    unmarked = generate_romanization(random.Random(1), inventory, forced_orthography=OrthographyForce(style="digraph-style"))
    marked = generate_romanization(random.Random(1), inventory, forced_orthography=OrthographyForce(style="gemination-style"))
    assert unmarked.apply("akːa") == "aka"  # length lost, not a raw "ː" leaking through
    assert marked.apply("akːa") == "akka"


def test_generate_gemination_rules_skips_a_long_consonant_with_no_short_counterpart():
    marked = _CATEGORIES_BY_NAME["gemination-style"]
    inventory = PhonemeInventory(
        consonants=(Consonant(ipa="kː", place=Place.VELAR, manner=Manner.STOP, voiced=False, long=True),),
        vowels=(),
    )
    assert _generate_gemination_rules(marked, inventory) == []


def test_new_named_anchors_have_the_expected_axis_values():
    pinyin = _CATEGORIES_BY_NAME["pinyin-style"]
    assert pinyin.tone_strategy == ToneMarkingStrategy.VOWEL_DIACRITIC
    assert pinyin.syllable_boundary_marker == SyllableBoundaryMarker.APOSTROPHE

    silent_e = _CATEGORIES_BY_NAME["silent-e-style"]
    assert silent_e.vowel_length_strategy == VowelLengthStrategy.SILENT_E
    assert silent_e.syllable_boundary_marker == SyllableBoundaryMarker.NONE

    gemination = _CATEGORIES_BY_NAME["gemination-style"]
    assert gemination.consonant_gemination_marked is True


def test_roll_independent_axes_can_reach_silent_e_and_apostrophe():
    found_silent_e = False
    found_apostrophe = False
    found_gemination = False
    for seed in range(500):
        category = _roll_independent_axes(random.Random(seed))
        found_silent_e |= category.vowel_length_strategy == VowelLengthStrategy.SILENT_E
        found_apostrophe |= category.syllable_boundary_marker == SyllableBoundaryMarker.APOSTROPHE
        found_gemination |= category.consonant_gemination_marked is True
    assert found_silent_e
    assert found_apostrophe
    assert found_gemination


def test_forced_syllable_boundary_marker_composes_with_a_forced_style():
    # pinyin-style already has APOSTROPHE -- force germanic-doubling-style
    # (which has NONE) plus an explicit apostrophe override, proving the
    # two axes compose across two different anchors.
    inventory = _dutch_flavored_inventory()
    scheme = generate_romanization(
        random.Random(1), inventory,
        forced_orthography=OrthographyForce(style="germanic-doubling-style", syllable_boundary_marker=SyllableBoundaryMarker.APOSTROPHE),
    )
    assert scheme.vowel_length_strategy == VowelLengthStrategy.DOUBLING
    assert scheme.syllable_boundary_marker == SyllableBoundaryMarker.APOSTROPHE


def test_roll_independent_axes_can_combine_axes_no_named_preset_has():
    # germanic-doubling-style pairs DOUBLING with the default inline tone
    # diacritic; wade-giles-style pairs POSTPOSED_DIGIT with no vowel-
    # length marking. No named anchor combines the two -- prove the
    # independent roll still reaches that combination.
    found = False
    for seed in range(500):
        category = _roll_independent_axes(random.Random(seed))
        if category.vowel_length_strategy == VowelLengthStrategy.DOUBLING and category.tone_strategy == ToneMarkingStrategy.POSTPOSED_DIGIT:
            found = True
            break
    assert found


def test_forced_style_reproduces_exact_axis_values_across_seeds():
    inventory = _dutch_flavored_inventory()
    anchor = _CATEGORIES_BY_NAME["wade-giles-style"]
    for seed in range(10):
        scheme = generate_romanization(
            random.Random(seed), inventory, forced_orthography=OrthographyForce(style="wade-giles-style")
        )
        assert scheme.category_name == anchor.name
        assert scheme.tone_strategy == anchor.tone_strategy
        assert scheme.tone_markers == anchor.tone_markers
        assert scheme.vowel_length_strategy == anchor.vowel_length_strategy
        assert scheme.short_vowel_consonant_doubling == anchor.short_vowel_consonant_doubling
        assert scheme.exotic_symbol_style == anchor.exotic_symbol_style


def test_forced_style_composes_with_a_forced_axis_override():
    # The motivating example: Dutch/German-style doubling forced together
    # with Wade-Giles-style postposed-digit tone marking -- a combination
    # no single named anchor has on its own.
    inventory = _dutch_flavored_inventory()
    scheme = generate_romanization(
        random.Random(1), inventory,
        forced_orthography=OrthographyForce(style="germanic-doubling-style", tone_strategy=ToneMarkingStrategy.POSTPOSED_DIGIT),
    )
    assert scheme.vowel_length_strategy == VowelLengthStrategy.DOUBLING
    assert scheme.short_vowel_consonant_doubling is True
    assert scheme.tone_strategy == ToneMarkingStrategy.POSTPOSED_DIGIT
    assert scheme.tone_markers == _CATEGORIES_BY_NAME["wade-giles-style"].tone_markers


def test_unknown_forced_style_raises_value_error_naming_valid_options():
    inventory = _dutch_flavored_inventory()
    with pytest.raises(ValueError, match="not-a-real-style"):
        generate_romanization(random.Random(1), inventory, forced_orthography=OrthographyForce(style="not-a-real-style"))


def _category_fraction(
    contact_languages: tuple[str, ...],
    category_name: str,
    inventory: PhonemeInventory,
    requested_orthography_style: str = "",
) -> float:
    hits = sum(
        generate_romanization(random.Random(seed), inventory, contact_languages, requested_orthography_style).category_name
        == category_name
        for seed in _SEEDS
    )
    return hits / len(_SEEDS)


def test_requested_orthography_style_biases_selection():
    inventory = _dutch_flavored_inventory()
    unbiased = _category_fraction((), "wade-giles-style", inventory)
    biased = _category_fraction((), "wade-giles-style", inventory, requested_orthography_style="wade-giles-style")
    assert biased > unbiased


def test_dutch_contact_language_biases_toward_its_declared_category():
    inventory = _dutch_flavored_inventory()
    unbiased = _category_fraction((), "germanic-doubling-style", inventory)
    biased = _category_fraction(("Dutch",), "germanic-doubling-style", inventory)
    assert biased > unbiased


def test_mandarin_contact_language_biases_toward_its_declared_category():
    mandarin = next(p for p in REFERENCE_LANGUAGES if p.name == "Mandarin")
    inventory = PhonemeInventory(
        consonants=tuple(_CONSONANT_BY_IPA[s] for s in mandarin.consonants),
        vowels=tuple(_VOWEL_BY_IPA[s] for s in mandarin.vowels),
    )
    unbiased = _category_fraction((), "wade-giles-style", inventory)
    biased = _category_fraction(("Mandarin",), "wade-giles-style", inventory)
    assert biased > unbiased


def test_dutch_biased_scheme_spells_the_vuur_alternation_correctly():
    # The "vuur" (closed syllable, doubled uu) vs "vuren" (open syllable,
    # single u) regression case, end to end through generate_romanization.
    inventory = _dutch_flavored_inventory()
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("Dutch",)))
        and {rule.latin for rule in s.rules if rule.ipa == "y"} == {"uu", "u"}
        and any(rule.ipa == "ə" and rule.latin == "e" for rule in s.rules)
    )
    assert scheme.apply("vyr") == "vuur"  # closed syllable
    assert scheme.apply("vyrən") == "vuren"  # open syllable ("r" is the next onset)
