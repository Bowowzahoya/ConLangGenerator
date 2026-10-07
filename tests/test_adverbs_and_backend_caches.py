"""Regression tests: degree adverbs must survive translation (they used to be
dropped by the real planner and misread as verbs by the fake one), each real
LLM backend must get its own response cache (a shared, content-keyed file
served a fake answer to a later real request), and the fake backend must
never be cached at all (a fix to the fake planner's own logic must take
effect immediately, not be masked by a stale cached response for text
already seen once -- the real cause of a reported bug: `_fake_single_clause_
plan`'s generic fallback leaked an internal placeholder as a word's gloss,
and the fix was invisible on an already-used saved language purely because
its own translate request had been cached before the fix landed)."""

from conlang_generator.llm.base import LLMRequest
from conlang_generator.llm.cache import CachingLLMClient
from conlang_generator.llm.factory import build_llm_client
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.translator import translate_to_conlang, translate_to_english
from tests._shared_language import cached_language

# seed=83 (re-found from seed=2 after the "Missing symbols still" batch's
# own new phoneme-pool content shifted downstream rng draws -- needs
# has_overt_copula=True for the copula slot these tests check).
_SEED = 83


def _language():
    language = cached_language(_SEED, name="T")
    # "very" as a word (an elative suffix language would mark the adjective instead)
    grammar = language.grammar.model_copy(
        update={
            "elative_marking": "word",
            "degree_affixes": tuple(a for a in language.grammar.degree_affixes if a.label != "elative"),
        }
    )
    return language.model_copy(update={"grammar": grammar})


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


def test_the_fake_backend_is_never_cached(tmp_path):
    client = build_llm_client(kind="fake", cache_dir=tmp_path)
    assert not isinstance(client, CachingLLMClient)
    response = client.complete(LLMRequest(system="s", prompt="p", model="m"))
    assert response.cached is False
    assert not (tmp_path / "llm_cache_fake.json").exists()
    # A second, identical call doesn't short-circuit through a cache either
    # (still runs the real strategy dispatch, still reports uncached).
    again = client.complete(LLMRequest(system="s", prompt="p", model="m"))
    assert again.cached is False and again.text == response.text


def test_caching_llm_client_itself_still_caches_by_request_content(tmp_path):
    # The caching mechanism itself (used for the real "anthropic" backend)
    # is unchanged -- only `build_llm_client`'s own choice of whether to
    # wrap a given backend kind in it changed.
    (tmp_path / "llm_cache.json").write_text("{}", encoding="utf-8")  # legacy shared file is ignored
    client = CachingLLMClient(FakeLLMClient(), tmp_path / "llm_cache_anthropic.json")
    first = client.complete(LLMRequest(system="s", prompt="p", model="m"))
    assert first.cached is False
    second = client.complete(LLMRequest(system="s", prompt="p", model="m"))
    assert second.cached is True and second.text == first.text
    assert (tmp_path / "llm_cache_anthropic.json").exists()
