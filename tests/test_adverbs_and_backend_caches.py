"""Regression tests: degree adverbs must survive translation (they used to be
dropped by the real planner and misread as verbs by the fake one), and each
LLM backend must get its own response cache (a shared, content-keyed file
served a fake answer to a later real request)."""

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.base import LLMRequest
from conlang_generator.llm.factory import build_llm_client
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.translator import translate_to_conlang, translate_to_english

_SEED = 2


def _language():
    return generate_language("T", GenerationSpec(prompt="p", seed=_SEED), FakeLLMClient())


def test_fake_planner_keeps_a_degree_adverb_as_its_own_slot_before_the_adjective():
    plan = sentence_planner.plan_sentence("I am very tired", _language(), FakeLLMClient())
    assert [(s.kind, s.gloss) for s in plan.slots] == [
        ("content", "i"), ("copula", ""), ("content", "very"), ("content", "tired"),
    ]
    assert plan.slots[2].pos == "adverb"


def test_intensifiers_change_the_translation_and_round_trip():
    client = FakeLLMClient()
    language = _language()
    plain = translate_to_conlang("I am tired", language, client)
    very = translate_to_conlang("I am very tired", language, client)
    extremely = translate_to_conlang("I am extremely tired", very.language, client)
    assert len({plain.text, very.text, extremely.text}) == 3
    assert [e.primary_gloss for e in extremely.coined] == ["extremely"]  # coined, not dropped
    back = translate_to_english(extremely.text, extremely.language, client)
    assert "extremely" in back.text.lower() and "tired" in back.text.lower()
    again = translate_to_conlang("I am extremely tired", extremely.language, client)
    assert again.coined == () and again.text == extremely.text  # reused


def test_each_backend_gets_its_own_cache_file(tmp_path):
    (tmp_path / "llm_cache.json").write_text("{}", encoding="utf-8")  # legacy shared file is ignored
    client = build_llm_client(kind="fake", cache_dir=tmp_path)
    client.complete(LLMRequest(system="s", prompt="p", model="m"))
    assert (tmp_path / "llm_cache_fake.json").exists()
    assert not (tmp_path / "llm_cache_anthropic.json").exists()
