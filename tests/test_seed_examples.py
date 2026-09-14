import random

from conlang_generator.core.spec import GenerationSpec, SeedExample
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import phonology_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.seed_examples import resolve_seed_examples
from conlang_generator.llm.fake_client import FakeLLMClient


def test_explicit_ipa_is_preserved_unchanged():
    examples = (SeedExample(gloss="water", form="aqua", ipa="akwa"),)
    resolved = resolve_seed_examples(examples, FakeLLMClient())
    assert resolved == examples  # nothing to resolve, no LLM call needed


def test_missing_ipa_gets_filled_in_deterministically():
    examples = (SeedExample(gloss="water", form="aqua"),)
    a = resolve_seed_examples(examples, FakeLLMClient())
    b = resolve_seed_examples(examples, FakeLLMClient())
    assert a[0].ipa is not None
    assert a == b  # deterministic for the same input


def test_seed_word_appears_verbatim_in_generated_language():
    client = FakeLLMClient()
    examples = (SeedExample(gloss="water", form="aqua", ipa="akwa"),)
    spec = GenerationSpec(prompt="p", seed=5, seed_examples=examples)
    language = generate_language("Test", spec, client)

    entry = language.lexicon.by_gloss("water")
    assert entry is not None
    assert entry.ipa == "akwa"


def test_seed_word_romanization_is_the_users_own_spelling_not_reconstructed():
    # The stored romanization must be `form` itself, not the scheme applied
    # to `ipa` -- a seed word's IPA is often already an approximation (this
    # project doesn't model diphthongs, tone/length nuances, etc.), so
    # reconstructing from it can never recover the real spelling even in
    # principle. Using a spelling with no plausible relationship to the IPA
    # makes any accidental reconstruction-based match implausible.
    client = FakeLLMClient()
    examples = (SeedExample(gloss="water", form="XyZzy", ipa="akwa"),)
    spec = GenerationSpec(prompt="p", seed=5, seed_examples=examples)
    language = generate_language("Test", spec, client)

    entry = language.lexicon.by_gloss("water")
    assert entry is not None
    assert entry.romanization == "XyZzy"


def test_seed_word_phonemes_are_present_in_generated_inventory():
    client = FakeLLMClient()
    # "ʁ" (voiced uvular fricative) has very low base prevalence -- forcing
    # it via a seed example should guarantee its presence regardless.
    examples = (SeedExample(gloss="water", form="test", ipa="aʁa"),)
    spec = GenerationSpec(prompt="p", seed=5, seed_examples=examples)
    language = generate_language("Test", spec, client)

    assert "ʁ" in language.phonology.consonant_symbols()
    assert "a" in language.phonology.vowel_symbols()


def test_seed_example_never_lets_an_unrelated_multichar_phoneme_swallow_two_adjacent_real_ones():
    # Direct, synthetic reproduction of the same tokenizer-ambiguity bug
    # `test_sound_change.py`'s own
    # `test_reconstruction_never_lets_an_unrelated_multichar_phoneme_
    # swallow_two_adjacent_real_ones` guards against, at this project's
    # other structurally-similar call site: `phonology_gen.ALL_CONSONANTS`
    # models a genuine Swahili-style prenasalized stop "nz" as a distinct,
    # unrelated global entry, with nothing to do with this test's own
    # seed example. A seed word whose IPA happens to contain the literal
    # substring "nz" -- here, two real, adjacent single-character
    # phonemes "n" and "z" -- used to get greedily mis-tokenized as the
    # *global* "nz" phoneme when `generate_phonology` scanned
    # `seed_examples` against the full, unrestricted global multi-
    # character pool, wrongly force-including "nz" itself (and neither
    # "n" nor "z" individually) in the generated inventory via
    # `_force_include`. With a matched reference profile that has no
    # "nz" of its own (real French has neither the phoneme nor any
    # multi-character consonant at all), the fix restricts multi-
    # character tokenizer candidates to that profile's own palette, so
    # this now tokenizes as two ordinary single-character phonemes.
    rng = random.Random(0)
    examples = (SeedExample(gloss="test", form="anza", ipa="anza"),)
    spec = GenerationSpec(
        prompt="p", seed=0, seed_examples=examples,
        traits=TraitProfile(source_languages=("French",)),
    )
    inventory, _, _, _ = phonology_gen.generate_phonology(rng, spec)
    assert "n" in inventory.consonant_symbols()
    assert "z" in inventory.consonant_symbols()
    assert "nz" not in inventory.consonant_symbols()


def test_seeded_gloss_is_not_also_generated():
    client = FakeLLMClient()
    examples = (SeedExample(gloss="water", form="aqua", ipa="akwa"),)
    spec = GenerationSpec(prompt="p", seed=5, seed_examples=examples)
    language = generate_language("Test", spec, client)

    water_entries = [e for e in language.lexicon.entries if "water" in e.glosses]
    assert len(water_entries) == 1
