from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.prompt_classifier import classify_prompt
from conlang_generator.llm.base import LLMRequest, LLMResponse
from conlang_generator.llm.fake_client import FakeLLMClient


class _GarbageLLMClient:
    """Stub that never returns parseable JSON, to exercise the fallback path."""

    def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text="I cannot help with that.", model="stub", input_tokens=1, output_tokens=1)


def test_different_prompts_yield_different_profiles():
    client = FakeLLMClient()
    a = classify_prompt("a language spoken in the mountains", False, client)
    b = classify_prompt("a language spoken on a tropical island", False, client)
    assert a != b


def test_same_prompt_is_deterministic():
    client = FakeLLMClient()
    a = classify_prompt("a language spoken in the mountains", False, client)
    b = classify_prompt("a language spoken in the mountains", False, client)
    assert a == b


def test_fake_profile_floats_are_within_unit_interval():
    client = FakeLLMClient()
    profile = classify_prompt("anything", False, client)
    for field in ("isolation", "altitude", "aesthetic_harshness", "tonal_friendliness"):
        assert 0.0 <= getattr(profile, field) <= 1.0


def test_unparseable_response_degrades_to_neutral_profile():
    profile = classify_prompt("anything", False, _GarbageLLMClient())
    assert profile == TraitProfile()
