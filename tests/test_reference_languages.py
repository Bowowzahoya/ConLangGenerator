import random

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.phonology_gen import generate_phonology
from conlang_generator.generation.reference_languages import REFERENCE_LANGUAGES, match_profiles

_SEEDS = range(150)


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
    from conlang_generator.generation.phonology_gen import _ALL_CONSONANTS, _ALL_VOWELS

    known = {c.ipa for c in _ALL_CONSONANTS} | {v.ipa for v in _ALL_VOWELS}
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
