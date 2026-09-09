"""End-to-end coverage using FakeLLMClient: generation determinism,
translation round-tripping, on-the-fly word coinage and persistence, and the
cache/cost-tracking contract (a cache hit must not be billed twice)."""

from pathlib import Path

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.sound_change import evolve_language
from conlang_generator.llm.base import LLMRequest
from conlang_generator.llm.cost_tracker import CostTracker
from conlang_generator.llm.factory import build_llm_client
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.llm.pricing import DEFAULT_MODEL
from conlang_generator.storage.yaml_backend import YamlLanguageRepository
from conlang_generator.translation.translator import translate_to_conlang, translate_to_english


def test_generation_is_deterministic_for_identical_inputs():
    spec = GenerationSpec(prompt="test language", seed=7)
    lang1 = generate_language("Test", spec, FakeLLMClient())
    lang2 = generate_language("Test", spec, FakeLLMClient())
    assert lang1 == lang2


def test_translate_round_trip_for_core_vocabulary():
    # Seed 0 -- known to round-trip "mountain"/"high" cleanly with no
    # candidate collisions (seed 7's own word choices shifted once
    # lexicon_gen's syllable-count tables were recalibrated for more
    # realistic average word length -- see lexicon_gen.py).
    spec = GenerationSpec(prompt="test language", seed=0)
    client = FakeLLMClient()
    language = generate_language("Test", spec, client)

    to_conlang = translate_to_conlang("the mountain is high", language, client)
    assert to_conlang.pattern == "predicate-adjective"
    assert to_conlang.coined == ()  # both words are core vocabulary

    back = translate_to_english(to_conlang.text, to_conlang.language, client)
    assert "mountain" in back.text.lower()
    assert "high" in back.text.lower()


def test_translate_coins_new_word_and_can_be_persisted(tmp_path: Path):
    spec = GenerationSpec(prompt="test language", seed=7)
    client = FakeLLMClient()
    language = generate_language("Test", spec, client)
    assert language.lexicon.by_gloss("boat") is None  # not core vocabulary

    result = translate_to_conlang("the boat is red", language, client)
    assert len(result.coined) == 2
    assert result.language.lexicon.by_gloss("boat") is not None
    assert result.language.lexicon.by_gloss("red") is not None
    assert language.lexicon.by_gloss("boat") is None  # original untouched

    repo = YamlLanguageRepository(tmp_path)
    repo.save(result.language)
    reloaded = repo.load(language.name)
    assert reloaded.lexicon.by_gloss("boat") is not None
    assert reloaded.lexicon.by_gloss("red") is not None


def test_cache_hit_is_not_billed_again(tmp_path: Path):
    client = build_llm_client(kind="fake", cache_dir=tmp_path)
    request = LLMRequest(
        system="system prompt",
        prompt="same prompt every time",
        model=DEFAULT_MODEL,
        purpose="test",
    )

    first = client.complete(request)
    second = client.complete(request)

    assert first.text == second.text
    assert first.cached is False
    assert second.cached is True

    summary = CostTracker(tmp_path / "cost_ledger.jsonl").summarize()
    assert summary["num_calls"] == 1


def test_german_biased_language_capitalizes_its_noun_entries():
    # seed 2 rolls capitalized_pos=(NOUN,) for a German-contact language
    # (see romanization_gen.py's grammatical-spelling roll) -- an
    # empirically-found seed, same "search for a working seed" convention
    # this project already uses elsewhere (test_sound_change.py). (Re-found
    # against seed=0 after the ts/dz/alveolo-palatal-affricate/long-vowel
    # pool extension added new rng draws to consonant/vowel selection,
    # shifting downstream results -- same "seed-shift from new content"
    # pattern documented throughout this project's history.)
    spec = GenerationSpec(prompt="test", seed=2, traits=TraitProfile(source_languages=("German",)))
    language = generate_language("Test", spec, FakeLLMClient())
    assert PartOfSpeech.NOUN in language.romanization.grammatical_spelling.capitalized_pos
    nouns = [e for e in language.lexicon.entries if e.pos is PartOfSpeech.NOUN]
    assert nouns
    assert all(entry.romanization[:1].isupper() for entry in nouns)


def test_french_biased_language_gives_its_verb_entries_a_silent_r():
    # seed 3 rolls French's own mute_suffix_by_pos (VERB, "r") -- see the
    # note on the German test above for the seed-search convention. (Was
    # seed 11 before the Russian/Serbo-Croatian palatalization and
    # syllabic-/r/ pool additions shifted downstream rng draws enough to
    # change which seed rolls this -- same "seed-shift from new content"
    # pattern documented elsewhere in this project's history.)
    spec = GenerationSpec(prompt="test", seed=3, traits=TraitProfile(source_languages=("French",)))
    language = generate_language("Test", spec, FakeLLMClient())
    rule = next(
        (r for r in language.romanization.grammatical_spelling.mute_suffix_by_pos if r.pos is PartOfSpeech.VERB), None
    )
    assert rule is not None and rule.suffix == "r"
    verbs = [e for e in language.lexicon.entries if e.pos is PartOfSpeech.VERB]
    assert verbs
    for entry in verbs:
        assert entry.romanization.endswith("r")
        assert not entry.ipa.endswith("r")  # the "r" has no corresponding sound at all


def test_grammatical_spelling_convention_survives_evolution_with_no_new_source_language():
    # seed=2 -- see test_german_biased_language_capitalizes_its_noun_entries's
    # own comment for why this moved from seed=0.
    spec = GenerationSpec(prompt="test", seed=2, traits=TraitProfile(source_languages=("German",)))
    base = generate_language("Base", spec, FakeLLMClient())
    assert PartOfSpeech.NOUN in base.romanization.grammatical_spelling.capitalized_pos

    evolved = evolve_language("Evolved", base, years=200, traits=TraitProfile(), seed=1)
    assert evolved.romanization.grammatical_spelling == base.romanization.grammatical_spelling
    nouns = [e for e in evolved.lexicon.entries if e.pos is PartOfSpeech.NOUN]
    assert nouns
    assert all(entry.romanization[:1].isupper() for entry in nouns)
