from conlang_generator.core.spec import GenerationSpec, SeedExample
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


def test_seeded_gloss_is_not_also_generated():
    client = FakeLLMClient()
    examples = (SeedExample(gloss="water", form="aqua", ipa="akwa"),)
    spec = GenerationSpec(prompt="p", seed=5, seed_examples=examples)
    language = generate_language("Test", spec, client)

    water_entries = [e for e in language.lexicon.entries if "water" in e.glosses]
    assert len(water_entries) == 1
