import random

import pytest

from conlang_generator.core.grammar import MorphologicalType
from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.phonology import PhonemeInventory
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.grammar_gen import generate_grammar
from conlang_generator.generation.phonology_gen import ALL_CONSONANTS, ALL_VOWELS, generate_phonology
from conlang_generator.generation.reference_languages import REFERENCE_LANGUAGES, match_profiles
from conlang_generator.generation.romanization_gen import generate_romanization

_SEEDS = range(150)
_CONSONANT_BY_IPA = {c.ipa: c for c in ALL_CONSONANTS}
_VOWEL_BY_IPA = {v.ipa: v for v in ALL_VOWELS}


def _inventory_for(profile) -> PhonemeInventory:
    return PhonemeInventory(
        consonants=tuple(_CONSONANT_BY_IPA[s] for s in profile.consonants),
        vowels=tuple(_VOWEL_BY_IPA[s] for s in profile.vowels),
    )


def test_match_profiles_is_case_insensitive_and_matches_aliases():
    matched = match_profiles(("japanese", "ZULU"))
    names = {p.name for p in matched}
    assert "Japanese" in names
    assert "Xhosa" in names  # "zulu" is an alias for the Xhosa/Nguni stand-in


def test_match_profiles_ignores_unknown_names():
    assert match_profiles(("Klingon", "not a real language")) == ()


def test_every_reference_symbol_is_in_our_own_phoneme_pool():
    # Reference profiles are meant to be subsets of what phonology_gen.py
    # already models -- otherwise reference bias could never surface them.
    from conlang_generator.generation.phonology_gen import ALL_CONSONANTS, ALL_VOWELS

    known = {c.ipa for c in ALL_CONSONANTS} | {v.ipa for v in ALL_VOWELS}
    for profile in REFERENCE_LANGUAGES:
        assert profile.symbols() <= known, profile.name


def _consonant_symbol_sets(source_languages: tuple[str, ...]) -> list[frozenset[str]]:
    sets = []
    for seed in _SEEDS:
        spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile(source_languages=source_languages))
        inventory, _, _, _ = generate_phonology(random.Random(seed), spec)
        sets.append(frozenset(inventory.consonant_symbols()))
    return sets


def test_source_language_biases_inventory_toward_its_palette():
    japanese_symbols = next(p for p in REFERENCE_LANGUAGES if p.name == "Japanese").symbols()

    unbiased = _consonant_symbol_sets(())
    biased = _consonant_symbol_sets(("Japanese",))

    def overlap_fraction(symbol_sets: list[frozenset[str]]) -> float:
        return sum(len(s & japanese_symbols) / max(len(s), 1) for s in symbol_sets) / len(symbol_sets)

    assert overlap_fraction(biased) > overlap_fraction(unbiased)


def test_every_profile_loads_from_its_own_yaml_file_with_a_unique_name():
    # Regression guard for the storage migration (hardcoded Python tuple ->
    # one YAML file per language): every profile in the directory parses,
    # and no two files accidentally define the same language twice.
    names = [p.name for p in REFERENCE_LANGUAGES]
    assert len(names) >= 10
    assert len(names) == len(set(names))


def test_french_profile_spells_the_manger_alternation_correctly():
    # The "manger"/"mangeons" g-softness regression case, end to end
    # through generate_romanization -- proves class-based (front/back
    # vowel) conditioning for a real, non-Dutch language.
    french = next(p for p in REFERENCE_LANGUAGES if p.name == "French")
    inventory = _inventory_for(french)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("French",), strictness=1.0))
        and {rule.latin for rule in s.rules if rule.ipa == "ʒ"} == {"g", "ge", "j"}
    )
    # French nasal vowels aren't modeled (french.yaml's own docstring notes
    # this), so this uses "y" and "ɔ" specifically -- both still deterministic,
    # single-spelling vowels in French's own curated data (unlike "e"/"o",
    # which now have their own real weighted spelling alternatives -- see
    # the per-language content curation). `strictness=1.0` makes every
    # curated rule win outright rather than a per-symbol probabilistic
    # roll, so this stays deterministic without depending on luck for a
    # symbol the test isn't actually about.
    assert scheme.apply("maʒy") == "magu"  # front vowel following -- plain "g"
    assert scheme.apply("maʒɔ") == "mageo"  # back vowel following -- silent-e "ge"


def test_french_profile_declares_its_own_real_open_e_spelling():
    # Real French spells /ɛ/ "è" (grave) among its real alternatives --
    # never the generic diacritic-style table's "ë", which in real French
    # marks a hiatus/diaeresis ("Noël"), not vowel quality.
    french = next(p for p in REFERENCE_LANGUAGES if p.name == "French")
    epsilon_spellings = {rule.latin for rule in french.orthography if rule.ipa == "ɛ"}
    assert "è" in epsilon_spellings
    assert "ë" not in epsilon_spellings


def test_english_profile_declares_its_own_w_plus_rounded_vowel_blacklist():
    # Real English labial dissimilation: "dw-"/"tw-"/"kw-"/"gw-" (and
    # plain "w-") never precede a rounded vowel.
    english = next(p for p in REFERENCE_LANGUAGES if p.name == "English")
    assert set(english.restricted_onset_nucleus_pairs) == {("w", "u"), ("w", "o"), ("w", "ʊ"), ("w", "ɔ")}
    assert english.attested_onset_nucleus_pairs == ()  # blacklist mode, not whitelist


def test_dutch_profile_declares_its_own_onset_restrictions():
    dutch = next(p for p in REFERENCE_LANGUAGES if p.name == "Dutch")
    assert dutch.restricted_onset_consonants == ("ŋ",)
    assert ("k", "n") in dutch.attested_onset_clusters  # "knie"
    assert ("b", "f") not in dutch.attested_onset_clusters  # never a real Dutch onset


def test_english_profile_declares_real_coda_clusters_not_generic_ones():
    english = next(p for p in REFERENCE_LANGUAGES if p.name == "English")
    assert ("s", "t") in english.attested_coda_clusters  # "fist"
    assert ("ʃ", "p") not in english.attested_coda_clusters  # never a real English coda


def test_english_profile_declares_its_own_ŋ_nucleus_restriction():
    # Real English /ŋ/ only closes a syllable after a lax/checked vowel
    # (sing, sung, hang) -- never a tense vowel or diphthong.
    english = next(p for p in REFERENCE_LANGUAGES if p.name == "English")
    assert set(english.restricted_nucleus_coda_pairs) == {
        ("i", "ŋ"), ("e", "ŋ"), ("u", "ŋ"), ("o", "ŋ"), ("ə", "ŋ"),
        ("ai", "ŋ"), ("au", "ŋ"), ("ɔi", "ŋ"), ("ei", "ŋ"),
    }
    assert english.attested_nucleus_coda_pairs == ()  # blacklist mode, not whitelist
    bad = [pair for pair in english.restricted_nucleus_coda_pairs if pair[0] not in english.vowels or pair[1] not in english.consonants]
    assert bad == []


def test_coda_onset_boundary_pairs_default_empty_for_the_four_perfected_languages():
    # No solidly-verifiable, purely combinatorial (non-assimilation)
    # cross-syllable-boundary fact was curated for these four -- the
    # mechanism exists for future languages, but shouldn't fabricate data
    # here (same "abstain rather than fabricate" discipline as every
    # other curated field).
    for name in ("English", "German", "French", "Dutch"):
        profile = next(p for p in REFERENCE_LANGUAGES if p.name == name)
        assert profile.restricted_coda_onset_pairs == ()
        assert profile.attested_coda_onset_pairs == ()


def test_mandarin_profile_spells_the_pinyin_u_umlaut_alternation_correctly():
    # The ü/u pinyin regression case, end to end through
    # generate_romanization -- proves specific-segment (not class-based)
    # conditioning for an unrelated language family.
    mandarin = next(p for p in REFERENCE_LANGUAGES if p.name == "Mandarin")
    inventory = _inventory_for(mandarin)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("Mandarin",)))
        and {rule.latin for rule in s.rules if rule.ipa == "y"} == {"ü", "u"}
    )
    assert scheme.apply("ny") == "nü"  # no palatal-glide trigger preceding
    # "j" itself always romanizes as "y" (both generic styles agree, so
    # this stays deterministic regardless of which one this scheme rolled)
    # -- the /y/ vowel right after it is what loses its umlaut.
    assert scheme.apply("jy") == "yu"  # preceded by "j" -- umlaut dropped


def test_orthography_category_round_trips_from_yaml_for_dutch_and_mandarin():
    dutch = next(p for p in REFERENCE_LANGUAGES if p.name == "Dutch")
    mandarin = next(p for p in REFERENCE_LANGUAGES if p.name == "Mandarin")
    assert dutch.orthography_category == "germanic-doubling-style"
    assert mandarin.orthography_category == "wade-giles-style"


def test_only_the_real_final_devoicing_languages_declare_coda_devoicing():
    # Real final-obstruent devoicing -- Dutch, German, Russian, Turkish,
    # and Polish are all genuine, textbook cases (German "Rad"/"Tag";
    # Russian "друг" [druk]; Turkish kitab->kitap; Polish "chleb" [xlep]);
    # none of the other profiles categorically neutralize final obstruent
    # voicing.
    expected = {"Dutch", "German", "Russian", "Turkish", "Polish"}
    actual = {p.name for p in REFERENCE_LANGUAGES if p.coda_devoicing}
    assert actual == expected


def test_orthography_category_round_trips_from_yaml_for_japanese_and_hawaiian():
    japanese = next(p for p in REFERENCE_LANGUAGES if p.name == "Japanese")
    hawaiian = next(p for p in REFERENCE_LANGUAGES if p.name == "Hawaiian")
    assert japanese.orthography_category == "scholarly-macron-style"
    assert hawaiian.orthography_category == "scholarly-macron-style"


def test_orthography_category_round_trips_from_yaml_for_the_phase_b_languages():
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    assert by_name["German"].orthography_category == "germanic-doubling-style"
    assert by_name["Russian"].orthography_category == "diacritic-style"
    assert by_name["Portuguese"].orthography_category == "diacritic-style"
    assert by_name["Hindi"].orthography_category == "scholarly-macron-style"
    assert by_name["Turkish"].orthography_category == "diacritic-style"
    assert by_name["Korean"].orthography_category == "digraph-style"
    assert by_name["Icelandic"].orthography_category == "diacritic-style"
    assert by_name["Nahuatl"].orthography_category == "digraph-style"


def test_turkish_declares_vowel_harmony():
    turkish = next(p for p in REFERENCE_LANGUAGES if p.name == "Turkish")
    assert turkish.vowel_harmony is True


def test_orthography_category_round_trips_from_yaml_for_the_phase_c_languages():
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    assert by_name["English"].orthography_category == "silent-e-style"
    assert by_name["Italian"].orthography_category == "gemination-style"
    assert by_name["Bengali"].orthography_category == "scholarly-macron-style"
    assert by_name["Tamil"].orthography_category == "scholarly-macron-style"
    assert by_name["Indonesian"].orthography_category == "digraph-style"
    assert by_name["Persian"].orthography_category == "diacritic-style"
    assert by_name["Tibetan"].orthography_category == "diacritic-style"
    assert by_name["Mongolian"].orthography_category == "digraph-style"
    assert by_name["Arawakan"].orthography_category == "monoletter-style"
    assert by_name["Pama-Nyungan"].orthography_category == "monoletter-style"
    assert by_name["Quechua"].orthography_category == "diacritic-style"
    assert by_name["Hebrew"].orthography_category == "scholarly-macron-style"


def test_hebrew_declares_root_and_pattern():
    hebrew = next(p for p in REFERENCE_LANGUAGES if p.name == "Hebrew")
    assert hebrew.root_and_pattern is True


def test_tibetan_declares_tonal():
    tibetan = next(p for p in REFERENCE_LANGUAGES if p.name == "Tibetan")
    assert tibetan.tonal is True


def test_mongolian_declares_vowel_harmony():
    mongolian = next(p for p in REFERENCE_LANGUAGES if p.name == "Mongolian")
    assert mongolian.vowel_harmony is True


def test_pama_nyungan_matches_by_its_western_desert_alias():
    matched = match_profiles(("Western Desert",))
    assert {p.name for p in matched} == {"Pama-Nyungan"}


def test_arawakan_matches_by_its_garifuna_alias():
    matched = match_profiles(("Garifuna",))
    assert {p.name for p in matched} == {"Arawakan"}


def test_icelandic_matches_by_its_old_norse_and_viking_aliases():
    matched = match_profiles(("old norse", "VIKING"))
    names = {p.name for p in matched}
    assert names == {"Icelandic"}


def test_nahuatl_matches_by_its_aztec_alias():
    matched = match_profiles(("Aztec",))
    assert {p.name for p in matched} == {"Nahuatl"}


def test_finnish_orthography_category_and_geminate_symbol_round_trip_from_yaml():
    finnish = next(p for p in REFERENCE_LANGUAGES if p.name == "Finnish")
    assert finnish.orthography_category == "gemination-style"
    assert "kː" in finnish.consonants


def test_the_new_affricates_and_long_vowels_are_in_the_shared_pool():
    # Architecture extension for the Finnish/Hungarian/Polish batch: a
    # plain alveolar affricate pair, an alveolo-palatal affricate pair,
    # and three long front-rounded/long-æ vowels, all added to the
    # shared phonology_gen.py pool (not just these three profiles) --
    # see phonology_gen.py's own comments for the real languages that
    # motivated each.
    consonant_symbols = {c.ipa for c in ALL_CONSONANTS}
    vowel_symbols = {v.ipa for v in ALL_VOWELS}
    assert {"ts", "dz", "tɕ", "dʑ"} <= consonant_symbols
    assert {"æː", "øː", "yː"} <= vowel_symbols


def test_hungarian_and_polish_profiles_exist_with_their_own_real_phonemes():
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    hungarian = by_name["Hungarian"]
    assert "c" in hungarian.consonants and "ɟ" in hungarian.consonants  # real ty/gy palatal stops
    assert "ts" in hungarian.consonants and "dz" in hungarian.consonants
    polish = by_name["Polish"]
    assert "w" in polish.consonants  # real Polish "ł" -- a genuine /w/, not a dark l
    assert {"tɕ", "dʑ"} <= set(polish.consonants)  # real ć/dź, distinct from cz/dż
    assert polish.coda_devoicing is True


def test_finnish_hungarian_polish_declare_a_real_stress_pattern():
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    assert by_name["Finnish"].stress_pattern == "initial"
    assert by_name["Hungarian"].stress_pattern == "initial"
    assert by_name["Polish"].stress_pattern == "penultimate"
    for name in ("Finnish", "Hungarian", "Polish"):
        assert by_name[name].stress_deviation_rate is not None
        assert by_name[name].stress_driven_vowel_reduction is False
    # Real Hungarian stress is described as more rigidly exceptionless
    # than Finnish's own already-strong initial default.
    assert by_name["Hungarian"].stress_deviation_rate < by_name["Finnish"].stress_deviation_rate


def test_finnish_hungarian_polish_declare_a_real_average_syllable_count():
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    for name in ("Finnish", "Hungarian", "Polish"):
        assert by_name[name].core_vocabulary_average_syllables is not None


def test_hungarian_reverses_s_and_sz_spelling():
    # The famous real Hungarian convention: the letter "s" spells /ʃ/,
    # and plain /s/ is spelled "sz" -- the reverse of the naive
    # letter-to-sound mapping.
    hungarian = next(p for p in REFERENCE_LANGUAGES if p.name == "Hungarian")
    inventory = _inventory_for(hungarian)
    scheme = generate_romanization(
        random.Random(1), inventory, source_languages=("Hungarian",),
        requested_orthography_style=hungarian.orthography_category, strictness=1.0,
    )
    assert scheme.apply("s") == "sz"
    assert scheme.apply("ʃ") == "s"


def test_polish_spells_the_w_sound_as_l_with_stroke_and_the_v_sound_as_w():
    polish = next(p for p in REFERENCE_LANGUAGES if p.name == "Polish")
    inventory = _inventory_for(polish)
    scheme = generate_romanization(
        random.Random(1), inventory, source_languages=("Polish",),
        requested_orthography_style=polish.orthography_category, strictness=1.0,
    )
    assert scheme.apply("v") == "w"    # real Polish "w" letter is pronounced /v/
    assert scheme.apply("w") == "ł"    # the real *sound* /w/ is spelled "ł"


def test_dutch_diphthongs_and_their_spellings_round_trip_from_yaml():
    # /ɛi/ and /au/ are genuine weighted alternatives (ij/ei, ou/au) --
    # checked as membership, not a naive {ipa: latin} dict (which would
    # silently collapse to just one of the tied rules); /œy/ has no real
    # alternation, still a single deterministic rule.
    dutch = next(p for p in REFERENCE_LANGUAGES if p.name == "Dutch")
    assert {"ɛi", "œy", "au"} <= set(dutch.vowels)
    ei_spellings = {rule.latin for rule in dutch.orthography if rule.ipa == "ɛi"}
    au_spellings = {rule.latin for rule in dutch.orthography if rule.ipa == "au"}
    by_ipa = {rule.ipa: rule.latin for rule in dutch.orthography if rule.ipa == "œy"}
    assert ei_spellings == {"ij", "ei"}
    assert au_spellings == {"ou", "au"}
    assert by_ipa["œy"] == "ui"


def test_arabic_source_language_biases_toward_root_and_pattern_and_fusional():
    def _rates(source_languages: tuple[str, ...]) -> tuple[float, float]:
        root_and_pattern_hits = 0
        fusional_hits = 0
        for seed in _SEEDS:
            spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile(source_languages=source_languages))
            grammar = generate_grammar(random.Random(seed), spec)
            root_and_pattern_hits += grammar.uses_root_and_pattern
            fusional_hits += grammar.morphological_type is MorphologicalType.FUSIONAL
        return root_and_pattern_hits / len(_SEEDS), fusional_hits / len(_SEEDS)

    unbiased_rap, unbiased_fusional = _rates(())
    biased_rap, biased_fusional = _rates(("Arabic",))
    assert biased_rap > unbiased_rap
    assert biased_fusional > unbiased_fusional


def test_full_strictness_makes_root_and_pattern_exactly_zero_for_a_non_matching_source():
    # English never uses Semitic-style root-and-pattern morphology --
    # at strictness=1.0 the independent low base-rate chance of rolling
    # it anyway must be suppressed to exactly 0%.
    hits = 0
    for seed in _SEEDS:
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("English",), source_language_strictness=1.0)
        )
        grammar = generate_grammar(random.Random(seed), spec)
        hits += grammar.uses_root_and_pattern
    assert hits == 0


def test_full_strictness_still_boosts_root_and_pattern_for_arabic():
    # Fix A's suppression must be one-sided -- a matched source language
    # that genuinely *is* root-and-pattern should stay boosted, not get
    # suppressed by the same mechanism.
    hits = 0
    for seed in _SEEDS:
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("Arabic",), source_language_strictness=1.0)
        )
        grammar = generate_grammar(random.Random(seed), spec)
        hits += grammar.uses_root_and_pattern
    assert hits > len(_SEEDS) * 0.9


def test_german_declares_capitalized_nouns():
    german = next(p for p in REFERENCE_LANGUAGES if p.name == "German")
    assert german.capitalized_pos == (PartOfSpeech.NOUN,)


def test_french_declares_a_silent_r_verb_suffix():
    french = next(p for p in REFERENCE_LANGUAGES if p.name == "French")
    assert len(french.mute_suffix_by_pos) == 1
    rule = french.mute_suffix_by_pos[0]
    assert rule.pos is PartOfSpeech.VERB
    assert rule.suffix == "r"


def test_the_four_perfected_languages_declare_a_real_average_syllable_count():
    # Hand-counted across this project's own CORE_MEANINGS glosses --
    # English shortest, German longest, Dutch/French in between.
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    assert by_name["English"].core_vocabulary_average_syllables == 1.14
    assert by_name["Dutch"].core_vocabulary_average_syllables == 1.27
    assert by_name["French"].core_vocabulary_average_syllables == 1.35
    assert by_name["German"].core_vocabulary_average_syllables == 1.43
    ordering = [by_name[n].core_vocabulary_average_syllables for n in ("English", "Dutch", "French", "German")]
    assert ordering == sorted(ordering)


def test_most_profiles_leave_average_syllables_uncurated():
    curated = {
        "English", "German", "French", "Dutch", "Italian", "Spanish",
        "Danish", "Swedish", "Norwegian", "Icelandic",
        "Finnish", "Hungarian", "Polish",
    }
    for profile in REFERENCE_LANGUAGES:
        if profile.name not in curated:
            assert profile.core_vocabulary_average_syllables is None


def test_north_germanic_batch_declares_a_real_average_syllable_count():
    # Hand-counted across this project's own CORE_MEANINGS glosses, same
    # illustrative caveat as every other curated language. Icelandic's
    # own conservative, ending-rich morphology keeps it a bit longer than
    # the more eroded mainland Scandinavian forms.
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    for name in ("Danish", "Swedish", "Norwegian", "Icelandic"):
        assert by_name[name].core_vocabulary_average_syllables is not None
    assert by_name["Icelandic"].core_vocabulary_average_syllables > by_name["Danish"].core_vocabulary_average_syllables
    assert by_name["Icelandic"].core_vocabulary_average_syllables > by_name["Swedish"].core_vocabulary_average_syllables
    assert by_name["Icelandic"].core_vocabulary_average_syllables > by_name["Norwegian"].core_vocabulary_average_syllables


def test_italian_and_spanish_declare_a_real_average_syllable_count():
    # Hand-counted across this project's own CORE_MEANINGS glosses, same
    # illustrative caveat as the earlier four -- Italian and Spanish both
    # retain more unstressed final vowels than any Germanic/French
    # profile, so both land well above German's own 1.43.
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    assert by_name["Spanish"].core_vocabulary_average_syllables == 1.90
    assert by_name["Italian"].core_vocabulary_average_syllables == 2.15
    assert by_name["German"].core_vocabulary_average_syllables < by_name["Spanish"].core_vocabulary_average_syllables
    assert by_name["Spanish"].core_vocabulary_average_syllables < by_name["Italian"].core_vocabulary_average_syllables


# Spanish has full onset/nucleus/coda tiers (an "unrestricted" coda
# profile, same as the four below); Italian is deliberately left out of
# this list -- its "sonorant" coda_profile means the true legal coda set
# is narrower than consonants-minus-restricted (see
# generation/phonology_gen.py's "sonorant" branch), so curating a
# same-shaped coda tier would silently mismatch _legal_symbols below.
# Italian's onset/nucleus tiers are checked separately.
_PERFECTED_LANGUAGES = (
    "English", "German", "French", "Dutch", "Spanish",
    "Danish", "Swedish", "Norwegian", "Icelandic",
    "Finnish", "Hungarian", "Polish",
)
_TIER_NAMES = {"very_common", "common", "uncommon", "rare"}


def _legal_symbols(profile, position: str) -> set[str]:
    if position == "onset":
        return set(profile.consonants) - set(profile.restricted_onset_consonants)
    if position == "coda":
        return set(profile.consonants) - set(profile.restricted_coda_consonants)
    return set(profile.vowels)  # nucleus -- every vowel is legal


def test_frequency_tiers_exactly_partition_each_legal_symbol_set():
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    for name in _PERFECTED_LANGUAGES:
        profile = by_name[name]
        for position, field in (
            ("onset", profile.onset_frequency_tiers),
            ("coda", profile.coda_frequency_tiers),
            ("nucleus", profile.nucleus_frequency_tiers),
        ):
            assert set(field.keys()) == _TIER_NAMES, f"{name} {position}"
            tiered: list[str] = [symbol for members in field.values() for symbol in members]
            assert len(tiered) == len(set(tiered)), f"{name} {position} has a symbol in more than one tier"
            assert set(tiered) == _legal_symbols(profile, position), f"{name} {position}"


def test_frequency_tiers_correctly_flip_by_position_for_dutch_x():
    # The clearest single example of why this needs to be per-position:
    # /x/ is a rare onset in Dutch but one of the most productive codas.
    dutch = next(p for p in REFERENCE_LANGUAGES if p.name == "Dutch")
    assert "x" in dutch.onset_frequency_tiers["rare"]
    assert "x" in dutch.coda_frequency_tiers["very_common"]


def test_english_ð_is_onset_rare_despite_high_token_frequency():
    # The type-vs-token-frequency distinction this whole feature is built
    # on: /ð/ is everywhere in running English text (the/this/that/...)
    # but is one of the smallest onset classes by word-type count.
    english = next(p for p in REFERENCE_LANGUAGES if p.name == "English")
    assert "ð" in english.onset_frequency_tiers["rare"]


def test_non_perfected_profiles_leave_frequency_tiers_uncurated():
    for profile in REFERENCE_LANGUAGES:
        if profile.name not in _PERFECTED_LANGUAGES and profile.name != "Italian":
            assert profile.onset_frequency_tiers == {}
            assert profile.nucleus_frequency_tiers == {}
            assert profile.coda_frequency_tiers == {}


def test_italian_onset_and_nucleus_frequency_tiers_partition_its_legal_symbols():
    # Italian curates onset/nucleus tiers like every other perfected
    # profile, but deliberately leaves coda_frequency_tiers uncurated --
    # see _PERFECTED_LANGUAGES' own comment above for why.
    italian = next(p for p in REFERENCE_LANGUAGES if p.name == "Italian")
    for position, field in (
        ("onset", italian.onset_frequency_tiers),
        ("nucleus", italian.nucleus_frequency_tiers),
    ):
        assert set(field.keys()) == _TIER_NAMES, position
        tiered = [symbol for members in field.values() for symbol in members]
        assert len(tiered) == len(set(tiered)), position
        assert set(tiered) == _legal_symbols(italian, position), position
    assert italian.coda_frequency_tiers == {}


# --- Probabilistic, richer French/English romanization ---


def test_french_ʃ_is_curated_as_ch_not_the_generic_diacritic_fallback():
    # Regression guard for the reported "glaplèš" bug: /ʃ/ had no curated
    # rule at all, so it fell through to the generic "diacritic-style"
    # category's fallback table ("š", Slavic-style) -- correct for
    # nobody in this project, and specifically wrong for French, which
    # always spells this sound "ch".
    french = next(p for p in REFERENCE_LANGUAGES if p.name == "French")
    sh_spellings = {rule.latin for rule in french.orthography if rule.ipa == "ʃ"}
    assert sh_spellings == {"ch"}


def test_french_and_english_declare_real_weighted_spelling_alternatives():
    french = next(p for p in REFERENCE_LANGUAGES if p.name == "French")
    english = next(p for p in REFERENCE_LANGUAGES if p.name == "English")
    o_rules = [rule for rule in french.orthography if rule.ipa == "o" and not rule.following]
    assert {rule.latin for rule in o_rules} == {"o", "au", "eau"}
    assert sum(rule.weight for rule in o_rules) == pytest.approx(1.0)
    schwa_rules = [rule for rule in english.orthography if rule.ipa == "ə"]
    assert {rule.latin for rule in schwa_rules} == {"a", "e", "o", "u", "i"}
    assert sum(rule.weight for rule in schwa_rules) == pytest.approx(1.0)


def test_only_french_overrides_syllable_boundary_marker():
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    assert by_name["French"].syllable_boundary_marker == "diaeresis"
    for name, profile in by_name.items():
        if name != "French":
            assert profile.syllable_boundary_marker == ""


def test_french_restricts_w_to_its_three_real_attested_vowels():
    # Real French /w/ only ever precedes a (moi, roi), i (oui), or ɛ
    # (ouest) -- blacklist the rest so a strict French language can't
    # generate implausible sequences like /w/+/o/ ("wagon" is actually
    # /v/, not /w/, in real French).
    french = next(p for p in REFERENCE_LANGUAGES if p.name == "French")
    blacklisted_vowels = {pair[1] for pair in french.restricted_onset_nucleus_pairs if pair[0] == "w"}
    assert blacklisted_vowels == set(french.vowels) - {"a", "i", "ɛ"}


def test_french_declares_the_real_wa_joint_spelling():
    # Real French "moi"/"roi" -- /w/+/a/ spelled as one joint "oi" unit,
    # not /w/'s own spelling plus a separately-appended "a".
    french = next(p for p in REFERENCE_LANGUAGES if p.name == "French")
    assert len(french.onset_nucleus_spellings) == 1
    entry = french.onset_nucleus_spellings[0]
    assert (entry.first, entry.second, entry.latin) == ("w", "a", "oi")


def test_no_profile_curates_nucleus_coda_spellings_yet():
    for profile in REFERENCE_LANGUAGES:
        assert profile.nucleus_coda_spellings == ()


# --- Italian / Spanish parity with the other perfected languages ---


def test_spanish_no_longer_aliases_italian():
    # Regression guard: spanish.yaml used to carry a leftover
    # `aliases: [italian, ...]` from before Italian had its own profile.
    # Harmless in practice (match_profiles checks files in alphabetical
    # order and italian.yaml always sorted first), but wrong data --
    # a real "Italian" query must resolve to Italian's own profile.
    matched = match_profiles(("Italian",))
    assert {p.name for p in matched} == {"Italian"}
    spanish = next(p for p in REFERENCE_LANGUAGES if p.name == "Spanish")
    assert "italian" not in spanish.aliases


def test_italian_profile_declares_its_own_onset_restrictions():
    italian = next(p for p in REFERENCE_LANGUAGES if p.name == "Italian")
    assert set(italian.restricted_onset_consonants) == {"kː", "tː", "pː", "sː", "nː", "lː", "z"}
    assert ("k", "w") in italian.attested_onset_clusters  # "quattro"
    assert ("t", "l") not in italian.attested_onset_clusters  # never a real Italian onset


def test_italian_profile_declares_its_own_coda_restrictions():
    # coda_profile is already "sonorant", but that alone still admits
    # every sonority>=3 consonant -- j/w/ɲ/lʲ all qualify by that measure
    # but none genuinely closes a real Italian syllable.
    italian = next(p for p in REFERENCE_LANGUAGES if p.name == "Italian")
    assert set(italian.restricted_coda_consonants) == {"j", "w", "ɲ", "lʲ"}
    assert italian.attested_coda_clusters == ()  # dead data under coda_profile "sonorant" -- see phonology_gen.py


def test_spanish_profile_declares_its_own_onset_clusters():
    spanish = next(p for p in REFERENCE_LANGUAGES if p.name == "Spanish")
    assert ("g", "ɾ") in spanish.attested_onset_clusters  # "grande" -- always the tap, never the trill
    assert ("g", "r") not in spanish.attested_onset_clusters  # the trill never follows another onset consonant
    assert ("s", "k") not in spanish.attested_onset_clusters  # never a real Spanish onset


def test_spanish_profile_declares_real_coda_clusters():
    spanish = next(p for p in REFERENCE_LANGUAGES if p.name == "Spanish")
    assert ("s", "t") in spanish.attested_coda_clusters  # "estar"-internal, "texto"
    assert ("p", "l") not in spanish.attested_coda_clusters  # never a real Spanish coda cluster


def test_italian_profile_fixes_its_hard_k_and_g_spellings():
    # /k/ and /g/ used to default to bare identity ("k"->"k", "g"->"g"),
    # but real Italian keeps these sounds hard via the c/ch and g/gh
    # alternation (casa/chiesa, gatto/ghiaccio) -- bare "k"/no digraph
    # never actually appears.
    italian = next(p for p in REFERENCE_LANGUAGES if p.name == "Italian")
    k_spellings = {(rule.latin, tuple(rule.following)) for rule in italian.orthography if rule.ipa == "k"}
    g_spellings = {(rule.latin, tuple(rule.following)) for rule in italian.orthography if rule.ipa == "g"}
    assert ("ch", ("front_vowel",)) in k_spellings
    assert ("c", ()) in k_spellings
    assert ("gh", ("front_vowel",)) in g_spellings
    assert ("g", ()) in g_spellings


def test_italian_profile_spells_soft_c_g_sc_correctly_before_front_and_back_vowels():
    # Regression guard: the original ʃ/tʃ/dʒ rules had no `following`
    # condition and no elsewhere alternative -- "cena" (front vowel,
    # correct /tʃ/) and "cono" (back vowel, real /k/) would have spelled
    # identically. End to end through generate_romanization proves the
    # fix composes correctly with the rest of the scheme.
    italian = next(p for p in REFERENCE_LANGUAGES if p.name == "Italian")
    inventory = _inventory_for(italian)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("Italian",), strictness=1.0))
    )
    assert scheme.apply("tʃe") == "ce"    # "cena" -- front vowel
    assert scheme.apply("tʃo") == "cio"   # "ciao"-style -- elsewhere
    assert scheme.apply("dʒe") == "ge"    # "gente" -- front vowel
    assert scheme.apply("dʒo") == "gio"   # "giorno" -- elsewhere
    assert scheme.apply("ʃe") == "sce"    # "scena" -- front vowel
    assert scheme.apply("ʃo") == "scio"   # "sciopero"-style -- elsewhere
    assert scheme.apply("ke") == "che"    # "chiesa" -- front vowel
    assert scheme.apply("ko") == "co"     # "casa"-style -- elsewhere
    assert scheme.apply("ge") == "ghe"    # "ghiaccio" -- front vowel
    assert scheme.apply("go") == "go"     # "gatto"-style -- elsewhere


def test_spanish_profile_fixes_its_k_g_j_w_spellings():
    # /k/, /g/ had the identical hard-sound bug as Italian; /j/ defaulted
    # to identity "j", colliding with /h/'s own already-correct "j"
    # mapping; /w/ defaulted to identity "w" instead of real Spanish "u".
    spanish = next(p for p in REFERENCE_LANGUAGES if p.name == "Spanish")
    inventory = _inventory_for(spanish)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("Spanish",), strictness=1.0))
    )
    assert scheme.apply("ke") == "que"   # "queso" -- front vowel
    assert scheme.apply("ko") == "co"    # "casa"-style -- elsewhere
    assert scheme.apply("ge") == "gue"   # "guerra" -- front vowel
    assert scheme.apply("go") == "go"    # "gato"-style -- elsewhere
    assert scheme.apply("jo") == "yo"    # "yo" -- no longer collides with h
    assert scheme.apply("ho") == "jo"    # "jamón"-style -- unaffected by the j fix
    assert scheme.apply("wa") == "ua"    # "cuando"-style


def test_spanish_c_plus_r_clusters_use_the_tap_not_the_trill():
    # Regression guard: attested_onset_clusters originally used the
    # trill "r" as the second member of every C+r cluster, which put the
    # trill phoneme directly after a stop -- real Spanish "pr"/"tr"/
    # "dr"/"cr"/"gr"/"fr" are always the tap [ɾ] (primo, tren, drama,
    # crear, grande, fruta); the trill only ever follows a vowel. Because
    # {ipa: r, latin: rr} fires unconditionally, the bug doubled every
    # such cluster into an unnatural "drr"/"crr" ("clabdrrasat").
    spanish = next(p for p in REFERENCE_LANGUAGES if p.name == "Spanish")
    assert all(pair[1] != "r" for pair in spanish.attested_onset_clusters)
    inventory = _inventory_for(spanish)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("Spanish",), strictness=1.0))
    )
    assert scheme.apply("dɾa") == "dra"   # "drama" -- single r, not doubled
    assert scheme.apply("kɾe") == "cre"   # "crear"-style


def test_spanish_restricts_the_trill_from_coda_position():
    # The same root bug as the cluster one above, at the other end of the
    # syllable: the trill /r/ categorically never closes a real Spanish
    # syllable (only the tap does) -- without this restriction, the
    # unconditional {ipa: r, latin: rr} rule would double a coda trill
    # into an unnatural "-rr-" no real Spanish word has.
    spanish = next(p for p in REFERENCE_LANGUAGES if p.name == "Spanish")
    assert spanish.restricted_coda_consonants == ("r",)
    assert "r" not in spanish.coda_frequency_tiers.get("uncommon", ())


def test_spanish_only_doubles_the_trill_intervocalically():
    # Real Spanish word-initial /r/ is single "r" (rosa, rey) -- "rr"
    # marks the trill only where it needs to be distinguished from the
    # tap, i.e. intervocalically (perro vs. pero). The original rule was
    # unconditioned, so a word-initial trill also doubled ("rrablatsel").
    spanish = next(p for p in REFERENCE_LANGUAGES if p.name == "Spanish")
    inventory = _inventory_for(spanish)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("Spanish",), strictness=1.0))
    )
    assert scheme.apply("ra") == "ra"     # "rosa"-style -- word-initial, single r
    assert scheme.apply("ara") == "arra"  # "perro"-style -- intervocalic, doubled
    assert scheme.apply("ɾa") == "ra"     # the tap is always single, unaffected by this fix


def test_spanish_declares_the_real_seseo_s_alternation():
    # Real seseo: most of the Spanish-speaking world merges "z" and
    # "c" (before e/i) with plain "s" -- a genuine weighted alternative,
    # conditioned so "c" only competes before a front vowel and "z"
    # only elsewhere.
    spanish = next(p for p in REFERENCE_LANGUAGES if p.name == "Spanish")
    front_rules = [rule for rule in spanish.orthography if rule.ipa == "s" and rule.following == ("front_vowel",)]
    elsewhere_rules = [rule for rule in spanish.orthography if rule.ipa == "s" and not rule.following]
    assert {rule.latin for rule in front_rules} == {"s", "c"}
    assert sum(rule.weight for rule in front_rules) == pytest.approx(1.0)
    assert {rule.latin for rule in elsewhere_rules} == {"s", "z"}
    assert sum(rule.weight for rule in elsewhere_rules) == pytest.approx(1.0)


# --- The real /kw/-/gw/-/kv/ family (qu/gu/qu=kv), across all six profiles ---


def test_italian_kw_and_gw_clusters_spell_qu_and_gu_not_cw_and_gw():
    # Regression guard: Italian's /w/ was never curated at all, defaulting
    # to bare identity "w" -- "quando" rendered as "cwando", "guerra" as
    # "gwerra", and even a bare glide like "uovo" as "wovo". Real Italian
    # spells /w/ "u" almost everywhere (it barely uses the letter "w" at
    # all), which composes correctly with /k/'s new q-before-w override
    # and /g/'s own already-unconditioned elsewhere rule.
    italian = next(p for p in REFERENCE_LANGUAGES if p.name == "Italian")
    inventory = _inventory_for(italian)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("Italian",), strictness=1.0))
    )
    assert scheme.apply("kwa") == "qua"   # "quando"-style
    assert scheme.apply("gwe") == "gue"   # "guerra"-style
    assert scheme.apply("wo") == "uo"     # "uovo"-style -- bare /w/, no k/g involved


def test_spanish_gue_gui_diaeresis_distinguishes_a_real_w_from_silent_u():
    # The actual güe/güi fix: pingüino/vergüenza (a real /w/ before a
    # front vowel) must render differently from guitarra/guerra (plain
    # /g/+front-vowel, no /w/ phoneme at all in that word's IPA) -- before
    # this fix both collapsed to the same "gui"/"gue" spelling.
    spanish = next(p for p in REFERENCE_LANGUAGES if p.name == "Spanish")
    inventory = _inventory_for(spanish)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("Spanish",), strictness=1.0))
    )
    assert scheme.apply("gwi") == "güi"   # "pingüino"-style -- real w, front vowel
    assert scheme.apply("gwe") == "güe"   # "vergüenza"-style
    assert scheme.apply("gwa") == "gua"   # "agua"-style -- real w, but back vowel: no diaeresis needed
    assert scheme.apply("gi") == "gui"    # "guitarra"-style -- no w at all, unaffected
    assert scheme.apply("kwa") == "cua"   # "cuando"-style -- w not preceded by g, unaffected


def test_spanish_declares_kw_and_gw_as_attested_onset_clusters():
    # Without these, real Spanish's very productive "cu-" family (cuando,
    # cuatro, cuidado) and the güe/güi family above would barely ever get
    # generated at all, even with the spelling rules ready for them.
    spanish = next(p for p in REFERENCE_LANGUAGES if p.name == "Spanish")
    assert ("k", "w") in spanish.attested_onset_clusters
    assert ("g", "w") in spanish.attested_onset_clusters


def test_english_kw_and_gw_clusters_spell_qu_and_gu():
    # Real English /kw/ is always "qu" (queen, quick, aqueduct), never
    # "w" -- /k/'s existing front-vowel/elsewhere rules never anticipated
    # /w/ as the following segment, and /w/ had no rule of its own at
    # all. /g/+/w/ (penguin, language, distinguish) gets the same fix.
    english = next(p for p in REFERENCE_LANGUAGES if p.name == "English")
    assert ("k", "w") in english.attested_onset_clusters
    assert ("g", "w") in english.attested_onset_clusters
    inventory = _inventory_for(english)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("English",), strictness=1.0))
    )
    assert scheme.apply("kwa") == "qua"   # "quack"-style
    assert scheme.apply("gwa") == "gua"   # "iguana"-style -- w preceded by g, not k


def test_german_kv_cluster_spells_qu():
    # Real German "qu" is always /kv/ (Quelle, Qualität, bequem) -- /k/'s
    # existing weighted k/ck alternatives never anticipated /v/ as the
    # following segment, and /v/'s existing w/v alternation never
    # anticipated a preceding /k/.
    german = next(p for p in REFERENCE_LANGUAGES if p.name == "German")
    assert ("k", "v") in german.attested_onset_clusters
    inventory = _inventory_for(german)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("German",), strictness=1.0))
    )
    assert scheme.apply("kve") == "que"   # "Quelle"-style
    assert scheme.apply("kva") == "qua"   # "Qualität"-style


def test_french_k_spells_qu_before_a_front_vowel_and_c_elsewhere():
    # Real French "qui"/"que" (qui, que, quel, quinze) is deterministic --
    # no rule predicted this before, so /k/ fell through to the generic
    # category's own uncurated default. Elsewhere, plain "c" is the
    # dominant native spelling (comme, cou); "k" is loanword-only
    # (kilo, kayak), deliberately not modeled as a competing alternative,
    # same call already made for German's own excluded loanword "c".
    french = next(p for p in REFERENCE_LANGUAGES if p.name == "French")
    inventory = _inventory_for(french)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("French",), strictness=1.0))
    )
    assert scheme.apply("ki") == "qui"
    assert scheme.apply("ka") == "ca"


def test_dutch_kw_cluster_needs_no_fix():
    # The one profile in this family that turns out to already be
    # correct: native Dutch /kʋ/ is genuinely spelled "kw" (kwart, kwaad,
    # kwaliteit) via /k/ and /w/'s own independent identity defaults --
    # "aquaduct"/"aquarium" retain "qu" only as an unassimilated Latin/
    # French loanword spelling, not a native convention to model as a
    # competing alternative (same call as French/German's excluded
    # loanword letters above).
    dutch = next(p for p in REFERENCE_LANGUAGES if p.name == "Dutch")
    assert not any(rule.ipa == "w" for rule in dutch.orthography)
    assert not any(rule.ipa == "k" for rule in dutch.orthography)
    inventory = _inventory_for(dutch)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("Dutch",), strictness=1.0))
    )
    assert scheme.apply("kwa") == "kwa"


# --- English's digraph-implies-position fixes (/u/, /i/, /o/, /ai/, /ɔi/, /ei/) ---


def test_english_u_digraphs_never_fire_before_a_real_coda():
    # Regression guard for the reported "sewv" bug: "ew"/"ue" are real
    # only word-finally (new/few, blue/true) -- they must never appear
    # when a real consonant follows.
    english = next(p for p in REFERENCE_LANGUAGES if p.name == "English")
    inventory = _inventory_for(english)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("English",), strictness=1.0))
    )
    assert scheme.apply("suv") not in {"sewv", "suev"}
    assert "ew" not in scheme.apply("suv") and "ue" not in scheme.apply("suv")
    # word-final: oo/o must still compete alongside ew/ue, not be excluded
    assert scheme.apply("su") in {"sew", "sue", "soo", "so"}


def test_english_i_bare_e_only_fires_word_finally():
    # Same shape as /u/'s bug: bare "e" (be/he/we/she) is real only
    # word-finally -- must never fire mid-word (e.g. a hypothetical
    # "smiv"->"smev").
    english = next(p for p in REFERENCE_LANGUAGES if p.name == "English")
    inventory = _inventory_for(english)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("English",), strictness=1.0))
    )
    assert scheme.apply("smiv") != "smev"
    assert scheme.apply("smi") in {"smee", "smea", "smie", "sme"}


def test_english_o_oa_and_oe_are_mutually_exclusive_by_position():
    # "oa" (boat/road) is real only before a following consonant; "oe"
    # (toe/doe) is real only word-finally -- the mirror image.
    english = next(p for p in REFERENCE_LANGUAGES if p.name == "English")
    inventory = _inventory_for(english)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("English",), strictness=1.0))
    )
    assert "oe" not in scheme.apply("gov")   # never word-medial
    assert scheme.apply("go") != "goa"        # never word-final


def test_english_ai_igh_is_restricted_to_before_t_or_word_final():
    # "igh" (night/light/right) is real only before /t/, or -- a much
    # smaller set -- word-finally (high/sigh); it must never fire before
    # any other consonant (no real "aim"->"ighm").
    english = next(p for p in REFERENCE_LANGUAGES if p.name == "English")
    inventory = _inventory_for(english)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("English",), strictness=1.0))
    )
    assert scheme.apply("bait") == "bight"     # before /t/ -- deterministic
    assert "igh" not in scheme.apply("baim")   # before another consonant -- never "igh"
    assert scheme.apply("bai") in {"by", "bigh"}  # word-final -- y or igh compete


def test_english_ɔi_and_ei_split_by_following_position():
    # Real English "oy"/"ay" before a vowel or at a word's end (boy/toy,
    # day/way), "oi"/"ai" before a consonant (point/voice, rain/wait) --
    # a structural split, not a genuine lexical alternation, so no
    # weight is involved.
    english = next(p for p in REFERENCE_LANGUAGES if p.name == "English")
    inventory = _inventory_for(english)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("English",), strictness=1.0))
    )
    oi = "ɔi"
    assert scheme.apply("b" + oi + "n") == "boin"
    assert scheme.apply("b" + oi) == "boy"
    assert scheme.apply("dein") == "dain"
    assert scheme.apply("dei") == "day"


# --- Word stress: profile curation and Spanish/Italian's real accent marks ---


def test_the_six_perfected_languages_declare_a_real_stress_pattern():
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    assert by_name["French"].stress_pattern == "final"
    assert by_name["Spanish"].stress_pattern == "penultimate_or_final_by_coda"
    assert by_name["Italian"].stress_pattern == "lexical"
    assert by_name["German"].stress_pattern == "initial"
    assert by_name["Dutch"].stress_pattern == "initial"
    assert by_name["English"].stress_pattern == "lexical"
    for name in ("French", "Spanish", "Italian", "German", "Dutch", "English"):
        assert by_name[name].stress_deviation_rate is not None


def test_most_profiles_leave_stress_pattern_uncurated():
    curated = {
        "French", "Spanish", "Italian", "German", "Dutch", "English",
        "Danish", "Swedish", "Norwegian", "Icelandic",
        "Finnish", "Hungarian", "Polish",
    }
    for profile in REFERENCE_LANGUAGES:
        if profile.name not in curated:
            assert profile.stress_pattern == ""
            assert profile.stress_deviation_rate is None
            assert profile.stress_accent_marking == ""


def test_only_spanish_and_italian_declare_a_real_stress_accent_marking():
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    assert by_name["Spanish"].stress_accent_marking == "irregular_only"
    assert by_name["Italian"].stress_accent_marking == "final_only"
    for name in ("French", "German", "Dutch", "English", "Danish", "Swedish", "Norwegian", "Icelandic"):
        assert by_name[name].stress_accent_marking == ""


def test_north_germanic_batch_declares_a_real_initial_stress_pattern():
    # All four are real, robust initial-stress languages -- the shared
    # Germanic default. Icelandic's own stress is famously more rigidly
    # initial than even German/Dutch, so it gets a notably lower
    # deviation rate than the mainland three.
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    for name in ("Danish", "Swedish", "Norwegian", "Icelandic"):
        assert by_name[name].stress_pattern == "initial"
        assert by_name[name].stress_deviation_rate is not None
    assert by_name["Icelandic"].stress_deviation_rate < by_name["Danish"].stress_deviation_rate
    assert by_name["Icelandic"].stress_deviation_rate < by_name["Swedish"].stress_deviation_rate
    assert by_name["Icelandic"].stress_deviation_rate < by_name["Norwegian"].stress_deviation_rate


def test_mainland_scandinavian_reduces_unstressed_vowels_but_icelandic_does_not():
    # Real, deliberate typological split: Danish/Swedish/Norwegian
    # genuinely reduce unstressed syllables toward schwa (Danish
    # especially); Icelandic's own inflectional endings keep distinct
    # full vowel qualities instead.
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    assert by_name["Danish"].stress_driven_vowel_reduction is True
    assert by_name["Swedish"].stress_driven_vowel_reduction is True
    assert by_name["Norwegian"].stress_driven_vowel_reduction is True
    assert by_name["Icelandic"].stress_driven_vowel_reduction is False


def test_danish_declares_glottalization_word_accent_and_swedish_norwegian_declare_pitch():
    # Real, well-established fact: stød and Swedish/Norwegian pitch accent
    # are two different surface realizations of the same Common
    # Scandinavian binary word-accent contrast -- see
    # core.phonology.WordAccentCategory's own docstring.
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    assert by_name["Danish"].word_accent_realization == "glottalization"
    assert by_name["Danish"].word_accent_pattern == "monosyllabic_heavy"
    for name in ("Swedish", "Norwegian"):
        assert by_name[name].word_accent_realization == "pitch"
        assert by_name[name].word_accent_pattern == "underived_monosyllable"
    for name in ("Danish", "Swedish", "Norwegian"):
        assert by_name[name].word_accent_deviation_rate is not None


def test_icelandic_and_the_six_perfected_languages_leave_word_accent_uncurated():
    # Real Icelandic has no stød/pitch accent; the six perfected profiles
    # are unrelated languages that don't have this feature either.
    curated = {"Danish", "Swedish", "Norwegian"}
    for profile in REFERENCE_LANGUAGES:
        if profile.name not in curated:
            assert profile.word_accent_realization == ""
            assert profile.word_accent_pattern == ""
            assert profile.word_accent_deviation_rate is None
            assert profile.word_accent_marking == ""


def test_spanish_marks_stress_only_when_it_deviates_from_the_predictable_default():
    # Real Spanish: casa/comen (vowel/n-final, penultimate -- the
    # default) stay unmarked; corazón-shaped irregular final stress on a
    # vowel-final word gets the accent. papel-shaped (l-final, final
    # stress) is itself the *regular* case for a non-n/s-final word and
    # stays unmarked; stressing that same shape on the penultimate
    # instead is what's irregular there, and gets accented.
    spanish = next(p for p in REFERENCE_LANGUAGES if p.name == "Spanish")
    inventory = _inventory_for(spanish)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("Spanish",), strictness=1.0))
        and s.stress_accent_marking == "irregular_only"
    )
    # The middle "s" is Spanish's own real, independent seseo s/z/c
    # alternation (see the earlier weighted-spelling tests) -- unrelated
    # to stress, so both letters are accepted here; only the presence or
    # absence, and position, of the accent mark is under test.
    S = "ˈ"
    assert scheme.apply("k" + S + "asa") in {"casa", "caza"}          # penultimate, vowel-final -- regular
    assert scheme.apply("kas" + S + "a") in {"casá", "cazá"}          # final, vowel-final -- irregular, accented
    assert scheme.apply("pap" + S + "el") == "papel"                  # final, l-final -- regular
    assert scheme.apply(S + "papel") == "pápel"                       # penultimate, l-final -- irregular, accented


def test_italian_marks_stress_only_on_the_final_syllable():
    # Real Italian: a grave accent appears whenever the last syllable is
    # stressed (città/perché-style), regardless of any other measure of
    # "regularity" -- non-final stress (the majority pattern) never gets
    # marked at all, even though it's also genuinely lexical/unpredictable.
    italian = next(p for p in REFERENCE_LANGUAGES if p.name == "Italian")
    inventory = _inventory_for(italian)
    scheme = next(
        s
        for seed in _SEEDS
        if (s := generate_romanization(random.Random(seed), inventory, ("Italian",), strictness=1.0))
        and s.stress_accent_marking == "final_only"
    )
    S = "ˈ"
    assert scheme.apply("kit" + S + "a") == "chitá"  # final syllable stressed -- accented
    assert scheme.apply(S + "kita") == "chita"        # non-final stressed -- unmarked
