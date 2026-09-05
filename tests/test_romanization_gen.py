import random

import pytest

from conlang_generator.core.lexicon import PartOfSpeech
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


def test_no_source_language_matches_current_behavior():
    inventory = _dutch_flavored_inventory()
    for seed in (1, 2, 3):
        with_empty = generate_romanization(random.Random(seed), inventory, ())
        with_unmatched = generate_romanization(random.Random(seed), inventory, ("Klingon",))
        assert with_empty == with_unmatched


def _dutch_rule_fraction(source_languages: tuple[str, ...], strictness: float = 0.0) -> float:
    dutch_by_ipa = {rule.ipa: rule.latin for rule in _DUTCH.orthography}
    inventory = _dutch_flavored_inventory()
    hits = 0
    total = 0
    for seed in _SEEDS:
        scheme = generate_romanization(
            random.Random(seed), inventory, source_languages, allow_all_caps=False, strictness=strictness
        )
        by_ipa = {rule.ipa: rule.latin for rule in scheme.rules}
        for ipa, latin in dutch_by_ipa.items():
            total += 1
            hits += by_ipa[ipa] == latin
    return hits / total


def test_dutch_source_language_biases_romanization_toward_dutch_spelling():
    assert _dutch_rule_fraction(()) < _dutch_rule_fraction(("Dutch",))


def test_full_strictness_makes_dutch_rule_adoption_near_certain():
    soft = _dutch_rule_fraction(("Dutch",), strictness=0.0)
    strict = _dutch_rule_fraction(("Dutch",), strictness=1.0)
    assert strict > soft
    assert strict > 0.97


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


def test_new_phoneme_group_spellings():
    # Nasalized vowels.
    assert _DIGRAPH_TABLE["ã"] == "an"
    assert _DIACRITIC_TABLE["ã"] == "ã"
    assert _MONOLETTER_TABLE["ã"] == "a"
    # Breathy voice.
    assert _DIGRAPH_TABLE["bʱ"] == "bh"
    assert _DIACRITIC_TABLE["bʱ"] == "bʱ"
    assert _MONOLETTER_TABLE["bʱ"] == "b"
    # Nahuatl's /tɬ/.
    assert _DIGRAPH_TABLE["tɬ"] == "tl"
    assert _DIACRITIC_TABLE["tɬ"] == "tł"
    assert _MONOLETTER_TABLE["tɬ"] == "l"
    # Pre-aspiration -- h-prefix, distinct from post-aspiration's own
    # capital-H suffix (pH/tH/kH).
    assert _DIGRAPH_TABLE["ʰp"] == "hp"
    assert _DIGRAPH_TABLE["pʰ"] == "pH"
    assert _DIACRITIC_TABLE["ʰp"] == "ʰp"
    assert _MONOLETTER_TABLE["ʰp"] == "p"
    # Turkish's dotless-ı.
    assert _DIGRAPH_TABLE["ɯ"] == "i"
    assert _DIACRITIC_TABLE["ɯ"] == "ı"
    assert _MONOLETTER_TABLE["ɯ"] == "i"


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


def test_generate_doubling_rules_double_only_when_intervocalic_not_at_word_end():
    # Real Dutch/German doubling exists to disambiguate an *intervocalic*
    # consonant's syllable affiliation (bakken vs. baken) -- at word-end
    # there's no such ambiguity, so real orthography keeps it single
    # (Dutch "gek", "rekstok", never "gekk"/"rekkstok").
    category = _CATEGORIES_BY_NAME["germanic-doubling-style"]
    inventory = PhonemeInventory(
        consonants=(Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False),),
        vowels=(Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False),),
    )
    rules = (RomanizationRule(ipa="a", latin="a"), *_generate_doubling_rules(category, inventory))
    scheme = RomanizationScheme(rules=rules, vowel_symbols=("a",), vowel_length=(("a", "short"),))
    assert scheme.apply("ata") == "atta"  # short vowel, followed by another vowel -- intervocalic, doubled
    assert scheme.apply("at") == "at"  # short vowel, but word-final -- no ambiguity, stays single
    assert scheme.apply("t") == "t"  # no preceding vowel at all -- unconditioned fallback still applies


def test_generate_doubling_rules_never_doubles_h_or_a_glide():
    # Real German/Dutch doubling never touches "h" (it marks the
    # *preceding* vowel's length, never geminated itself) or a glide --
    # "hh"/"yy"/"ww" aren't real spellings in any style this project models.
    category = _CATEGORIES_BY_NAME["germanic-doubling-style"]
    inventory = PhonemeInventory(
        consonants=(
            Consonant(ipa="h", place=Place.GLOTTAL, manner=Manner.FRICATIVE, voiced=False),
            Consonant(ipa="j", place=Place.PALATAL, manner=Manner.APPROXIMANT, voiced=True),
            Consonant(ipa="w", place=Place.VELAR, manner=Manner.APPROXIMANT, voiced=True),
            Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False),
        ),
        vowels=(Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False),),
    )
    rules = _generate_doubling_rules(category, inventory)
    ipas_with_rules = {rule.ipa for rule in rules}
    assert ipas_with_rules == {"t"}  # h/j/w excluded entirely, t still gets its pair


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
    source_languages: tuple[str, ...],
    category_name: str,
    inventory: PhonemeInventory,
    requested_orthography_style: str = "",
    strictness: float = 0.0,
) -> float:
    hits = sum(
        generate_romanization(
            random.Random(seed), inventory, source_languages, requested_orthography_style, strictness=strictness
        ).category_name
        == category_name
        for seed in _SEEDS
    )
    return hits / len(_SEEDS)


def test_requested_orthography_style_biases_selection():
    inventory = _dutch_flavored_inventory()
    unbiased = _category_fraction((), "wade-giles-style", inventory)
    biased = _category_fraction((), "wade-giles-style", inventory, requested_orthography_style="wade-giles-style")
    assert biased > unbiased


def test_dutch_source_language_biases_toward_its_declared_category():
    inventory = _dutch_flavored_inventory()
    unbiased = _category_fraction((), "germanic-doubling-style", inventory)
    biased = _category_fraction(("Dutch",), "germanic-doubling-style", inventory)
    assert biased > unbiased


def test_mandarin_source_language_biases_toward_its_declared_category():
    mandarin = next(p for p in REFERENCE_LANGUAGES if p.name == "Mandarin")
    inventory = PhonemeInventory(
        consonants=tuple(_CONSONANT_BY_IPA[s] for s in mandarin.consonants),
        vowels=tuple(_VOWEL_BY_IPA[s] for s in mandarin.vowels),
    )
    unbiased = _category_fraction((), "wade-giles-style", inventory)
    biased = _category_fraction(("Mandarin",), "wade-giles-style", inventory)
    assert biased > unbiased


def test_full_strictness_makes_dutch_category_selection_near_certain():
    inventory = _dutch_flavored_inventory()
    soft = _category_fraction(("Dutch",), "germanic-doubling-style", inventory, strictness=0.0)
    strict = _category_fraction(("Dutch",), "germanic-doubling-style", inventory, strictness=1.0)
    assert strict > soft
    assert strict > 0.97


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


def test_germanic_doubling_style_uses_digraph_not_diacritic():
    # Real Dutch/German orthography marks its exotic sounds with digraphs
    # (sch, ch, ng, sj), not Slavic-style accented letters -- an uncurated
    # symbol under this anchor should read Germanic, not Slavic.
    germanic = _CATEGORIES_BY_NAME["germanic-doubling-style"]
    assert germanic.exotic_symbol_style == ExoticSymbolStyle.DIGRAPH
    assert germanic.exotic_style == _DIGRAPH_TABLE


def test_every_reference_profile_declares_an_orthography_category():
    # Without one, a source-language-biased language has no "family" for
    # the exotic-symbol fallback (below) to lean on at all.
    for profile in REFERENCE_LANGUAGES:
        assert profile.orthography_category, profile.name


def test_georgian_biased_scheme_spells_ejectives_with_apostrophes():
    # The real Georgian National System convention -- and the first real
    # home anywhere in this project's reference set for ejective_drift's
    # own output (pʼ/tʼ/kʼ).
    georgian = next(p for p in REFERENCE_LANGUAGES if p.name == "Georgian")
    inventory = PhonemeInventory(
        consonants=tuple(_CONSONANT_BY_IPA[s] for s in georgian.consonants),
        vowels=tuple(_VOWEL_BY_IPA[s] for s in georgian.vowels),
    )
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("Georgian",)))
        and {rule.latin for rule in s.rules if rule.ipa == "pʼ"} == {"p'"}
    )
    by_ipa = {rule.ipa: rule.latin for rule in scheme.rules}
    assert by_ipa["pʼ"] == "p'"
    assert by_ipa["tʼ"] == "t'"
    assert by_ipa["kʼ"] == "k'"
    assert by_ipa["tʃ"] == "ch"
    assert by_ipa["dʒ"] == "j"


def test_uncurated_symbol_falls_back_to_the_source_languages_own_style_not_the_schemes():
    # The core of the new fallback tier: force the *whole scheme* onto an
    # unrelated named anchor (wade-giles-style, diacritic-backed -- "ʃ"
    # would spell "š") while Georgian (digraph-backed, "ʃ" -> "sh") is the
    # active contact language. Georgian doesn't curate "ʃ" specifically
    # (only tʃ/dʒ/pʼ/tʼ/kʼ), so it must fall through reference/structural
    # to this new tier -- and should land on Georgian's own digraph table,
    # not the forced scheme's diacritic one.
    inventory = PhonemeInventory(
        consonants=(_CONSONANT_BY_IPA["p"], _CONSONANT_BY_IPA["ʃ"]),
        vowels=(_VOWEL_BY_IPA["a"],),
    )
    scheme = generate_romanization(
        random.Random(1), inventory, ("Georgian",),
        forced_orthography=OrthographyForce(style="wade-giles-style"),
    )
    assert scheme.category_name == "wade-giles-style"  # the forced whole-scheme category really did win
    by_ipa = {rule.ipa: rule.latin for rule in scheme.rules}
    assert by_ipa["ʃ"] == "sh"  # Georgian's own digraph-style table, not wade-giles's diacritic "š"


# --- Grammatical spelling (capitalization / all-caps / mute suffix) ---

_GERMAN = next(p for p in REFERENCE_LANGUAGES if p.name == "German")
_FRENCH = next(p for p in REFERENCE_LANGUAGES if p.name == "French")
_ENGLISH = next(p for p in REFERENCE_LANGUAGES if p.name == "English")


def _german_inventory() -> PhonemeInventory:
    return PhonemeInventory(
        consonants=tuple(_CONSONANT_BY_IPA[s] for s in _GERMAN.consonants),
        vowels=tuple(_VOWEL_BY_IPA[s] for s in _GERMAN.vowels),
    )


def _french_inventory() -> PhonemeInventory:
    return PhonemeInventory(
        consonants=tuple(_CONSONANT_BY_IPA[s] for s in _FRENCH.consonants),
        vowels=tuple(_VOWEL_BY_IPA[s] for s in _FRENCH.vowels),
    )


def _english_inventory() -> PhonemeInventory:
    return PhonemeInventory(
        consonants=tuple(_CONSONANT_BY_IPA[s] for s in _ENGLISH.consonants),
        vowels=tuple(_VOWEL_BY_IPA[s] for s in _ENGLISH.vowels),
    )


def test_capitalization_fires_at_a_nonzero_rate_with_no_source_language():
    inventory = _dutch_flavored_inventory()
    hits = sum(bool(generate_romanization(random.Random(seed), inventory, ()).grammatical_spelling.capitalized_pos) for seed in _SEEDS)
    assert hits > 0


def test_mute_suffix_fires_at_a_nonzero_rate_with_no_source_language():
    inventory = _dutch_flavored_inventory()
    hits = sum(
        bool(generate_romanization(random.Random(seed), inventory, ()).grammatical_spelling.mute_suffix_by_pos)
        for seed in _SEEDS
    )
    assert hits > 0


def test_all_caps_fires_at_a_nonzero_rate_when_allowed():
    inventory = _dutch_flavored_inventory()
    hits = sum(
        bool(generate_romanization(random.Random(seed), inventory, (), allow_all_caps=True).grammatical_spelling.all_caps_pos)
        for seed in _SEEDS
    )
    assert hits > 0


def test_all_caps_never_fires_when_not_allowed():
    inventory = _dutch_flavored_inventory()
    for seed in _SEEDS:
        scheme = generate_romanization(random.Random(seed), inventory, ())  # allow_all_caps defaults False
        assert scheme.grammatical_spelling.all_caps_pos == ()


def test_german_source_language_biases_toward_capitalizing_nouns():
    inventory = _german_inventory()
    unbiased = sum(
        PartOfSpeech.NOUN in generate_romanization(random.Random(seed), inventory, ()).grammatical_spelling.capitalized_pos
        for seed in _SEEDS
    )
    biased = sum(
        PartOfSpeech.NOUN in generate_romanization(random.Random(seed), inventory, ("German",)).grammatical_spelling.capitalized_pos
        for seed in _SEEDS
    )
    assert biased > unbiased


def test_full_strictness_makes_german_noun_capitalization_near_certain():
    inventory = _german_inventory()
    strict = sum(
        PartOfSpeech.NOUN
        in generate_romanization(
            random.Random(seed), inventory, ("German",), strictness=1.0
        ).grammatical_spelling.capitalized_pos
        for seed in _SEEDS
    )
    assert strict > len(_SEEDS) * 0.97


def test_full_strictness_suppresses_capitalization_for_a_non_capitalizing_language():
    # English doesn't declare capitalized_pos -- at strictness=1.0 it
    # should never invent capitalization real English doesn't have,
    # unlike the base rate's usual "some seeds fire" behavior.
    inventory = _english_inventory()
    hits = sum(
        bool(generate_romanization(random.Random(seed), inventory, ("English",), strictness=1.0).grammatical_spelling.capitalized_pos)
        for seed in _SEEDS
    )
    assert hits == 0


def test_full_strictness_suppresses_mute_suffix_for_a_non_mute_suffix_language():
    # German doesn't declare mute_suffix_by_pos -- at strictness=1.0 it
    # should never invent a silent-letter convention real German lacks.
    inventory = _german_inventory()
    hits = sum(
        bool(generate_romanization(random.Random(seed), inventory, ("German",), strictness=1.0).grammatical_spelling.mute_suffix_by_pos)
        for seed in _SEEDS
    )
    assert hits == 0


def test_full_strictness_suppresses_all_caps_even_when_explicitly_allowed():
    # No real language does this -- strictness should suppress it to
    # exactly 0% even when the caller opts into allow_all_caps.
    inventory = _german_inventory()
    hits = sum(
        bool(
            generate_romanization(
                random.Random(seed), inventory, ("German",), allow_all_caps=True, strictness=1.0
            ).grammatical_spelling.all_caps_pos
        )
        for seed in _SEEDS
    )
    assert hits == 0


def test_french_source_language_biases_toward_a_silent_r_verb_suffix():
    inventory = _french_inventory()

    def _has_verb_r(scheme):
        return any(rule.pos is PartOfSpeech.VERB and rule.suffix == "r" for rule in scheme.grammatical_spelling.mute_suffix_by_pos)

    unbiased = sum(_has_verb_r(generate_romanization(random.Random(seed), inventory, ())) for seed in _SEEDS)
    biased = sum(_has_verb_r(generate_romanization(random.Random(seed), inventory, ("French",))) for seed in _SEEDS)
    assert biased > unbiased


def test_evolve_romanization_carries_grammatical_spelling_forward_unchanged():
    inventory = _german_inventory()
    base = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("German",))).grammatical_spelling.capitalized_pos
    )
    evolved = evolve_romanization(base, inventory, random.Random(99), ())
    assert evolved.grammatical_spelling == base.grammatical_spelling
