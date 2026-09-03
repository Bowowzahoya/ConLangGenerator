from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.prompt_classifier import classify_prompt
from conlang_generator.llm.base import LLMRequest, LLMResponse
from conlang_generator.llm.fake_client import FakeLLMClient


class _GarbageLLMClient:
    """Stub that never returns parseable JSON, to exercise the fallback path."""

    def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text="I cannot help with that.", model="stub", input_tokens=1, output_tokens=1)


class _FixedJsonLLMClient:
    """Stub that always returns the given JSON text, for testing specific
    field extraction/parsing without depending on the fake strategy's
    hash-derived (and therefore free-text-blind) output."""

    def __init__(self, text: str) -> None:
        self._text = text

    def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text=self._text, model="stub", input_tokens=1, output_tokens=1)


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


def test_fake_profile_floats_are_within_bipolar_interval():
    client = FakeLLMClient()
    profile = classify_prompt("anything", False, client)
    for field in ("isolation", "altitude", "aesthetic_harshness", "tonal_friendliness"):
        assert -1.0 <= getattr(profile, field) <= 1.0


def test_fake_profiles_span_both_positive_and_negative():
    client = FakeLLMClient()
    values = [
        getattr(classify_prompt(f"prompt {i}", False, client), "aesthetic_harshness")
        for i in range(30)
    ]
    assert any(v > 0 for v in values)
    assert any(v < 0 for v in values)


def test_unparseable_response_degrades_to_neutral_profile():
    profile = classify_prompt("anything", False, _GarbageLLMClient())
    assert profile == TraitProfile()


def test_requested_orthography_style_parses_like_salient_context():
    client = _FixedJsonLLMClient('{"requested_orthography_style": "wade-giles-style"}')
    profile = classify_prompt("mark tone with a number, Wade-Giles style", False, client)
    assert profile.requested_orthography_style == "wade-giles-style"


def test_missing_requested_orthography_style_defaults_to_empty():
    client = _FixedJsonLLMClient("{}")
    profile = classify_prompt("anything", False, client)
    assert profile.requested_orthography_style == ""
