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
        inventory, _, _ = generate_phonology(random.Random(seed), spec)
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
    # Real final-obstruent devoicing -- Dutch, German, Russian, and
    # Turkish are all genuine, textbook cases (German "Rad"/"Tag";
    # Russian "друг" [druk]; Turkish kitab->kitap); none of the other
    # profiles categorically neutralize final obstruent voicing.
    expected = {"Dutch", "German", "Russian", "Turkish"}
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


def test_dutch_diphthongs_and_their_spellings_round_trip_from_yaml():
    dutch = next(p for p in REFERENCE_LANGUAGES if p.name == "Dutch")
    assert {"ɛi", "œy", "au"} <= set(dutch.vowels)
    by_ipa = {rule.ipa: rule.latin for rule in dutch.orthography}
    assert by_ipa["ɛi"] == "ij"
    assert by_ipa["œy"] == "ui"
    assert by_ipa["au"] == "ou"


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
    perfected = {"English", "German", "French", "Dutch"}
    for profile in REFERENCE_LANGUAGES:
        if profile.name not in perfected:
            assert profile.core_vocabulary_average_syllables is None


_PERFECTED_LANGUAGES = ("English", "German", "French", "Dutch")
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
        if profile.name not in _PERFECTED_LANGUAGES:
            assert profile.onset_frequency_tiers == {}
            assert profile.nucleus_frequency_tiers == {}
            assert profile.coda_frequency_tiers == {}


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
