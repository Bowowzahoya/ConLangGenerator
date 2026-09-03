import random

from conlang_generator.core.grammar import MorphologicalType
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


def _consonant_symbol_sets(contact_languages: tuple[str, ...]) -> list[frozenset[str]]:
    sets = []
    for seed in _SEEDS:
        spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile(contact_languages=contact_languages))
        inventory, _, _ = generate_phonology(random.Random(seed), spec)
        sets.append(frozenset(inventory.consonant_symbols()))
    return sets


def test_contact_language_biases_inventory_toward_its_palette():
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
        if (s := generate_romanization(random.Random(seed), inventory, ("French",)))
        and {rule.latin for rule in s.rules if rule.ipa == "ʒ"} == {"g", "ge", "j"}
    )
    # French nasal vowels aren't modeled (french.yaml's own docstring notes
    # this), so this uses the oral vowels the profile actually has -- "e"
    # and "o" specifically, since neither has its own style-dependent
    # rendering (plain ASCII, identity in both digraph and diacritic
    # style), keeping this deterministic regardless of which style the
    # rest of the scheme happened to roll.
    assert scheme.apply("maʒe") == "mage"  # front vowel following -- plain "g"
    assert scheme.apply("maʒo") == "mageo"  # back vowel following -- silent-e "ge"


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


def test_orthography_category_round_trips_from_yaml_for_japanese_and_hawaiian():
    japanese = next(p for p in REFERENCE_LANGUAGES if p.name == "Japanese")
    hawaiian = next(p for p in REFERENCE_LANGUAGES if p.name == "Hawaiian")
    assert japanese.orthography_category == "scholarly-macron-style"
    assert hawaiian.orthography_category == "scholarly-macron-style"


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


def test_arabic_contact_language_biases_toward_root_and_pattern_and_fusional():
    def _rates(contact_languages: tuple[str, ...]) -> tuple[float, float]:
        root_and_pattern_hits = 0
        fusional_hits = 0
        for seed in _SEEDS:
            spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile(contact_languages=contact_languages))
            grammar = generate_grammar(random.Random(seed), spec)
            root_and_pattern_hits += grammar.uses_root_and_pattern
            fusional_hits += grammar.morphological_type is MorphologicalType.FUSIONAL
        return root_and_pattern_hits / len(_SEEDS), fusional_hits / len(_SEEDS)

    unbiased_rap, unbiased_fusional = _rates(())
    biased_rap, biased_fusional = _rates(("Arabic",))
    assert biased_rap > unbiased_rap
    assert biased_fusional > unbiased_fusional
