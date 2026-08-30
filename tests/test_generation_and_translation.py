"""End-to-end coverage using FakeLLMClient: generation determinism,
translation round-tripping, on-the-fly word coinage and persistence, and the
cache/cost-tracking contract (a cache hit must not be billed twice)."""

from pathlib import Path

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.generator import generate_language
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
    spec = GenerationSpec(prompt="test language", seed=7)
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
