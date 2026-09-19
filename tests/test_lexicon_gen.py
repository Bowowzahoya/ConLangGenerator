"""Tests for lexicon_gen's word-selection step: the algorithmic (no-LLM)
default, the single-word LLM path, and the batched LLM path used by the
initial core-vocabulary pass. A call-counting stub (not ``FakeLLMClient``,
whose calls are free and invisible) proves how many LLM requests actually
happen."""

import random

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import lexicon_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.base import LLMResponse
from conlang_generator.llm.fake_client import FakeLLMClient


class _CountingClient:
    """Wraps FakeLLMClient, recording each request's purpose."""

    def __init__(self, response_text: str | None = None) -> None:
        self._fake = FakeLLMClient()
        self._response_text = response_text
        self.purposes: list[str] = []

    def complete(self, request):
        self.purposes.append(request.purpose)
        if self._response_text is not None:
            return LLMResponse(text=self._response_text, model="stub", input_tokens=1, output_tokens=1)
        return self._fake.complete(request)


def _word_selection_calls(client: _CountingClient) -> int:
    return sum(1 for p in client.purposes if p.startswith("lexicon."))


def test_resolve_candidate_algorithmic_never_calls_the_llm():
    client = _CountingClient()
    candidates = ["ka", "to", "mi", "su", "ne"]
    chosen = lexicon_gen.resolve_candidate(
        random.Random(1), candidates, "water", PartOfSpeech.NOUN, client, "T", "", "algorithmic"
    )
    assert chosen in candidates
    assert client.purposes == []


def test_resolve_candidate_llm_makes_exactly_one_call():
    client = _CountingClient()
    candidates = ["ka", "to", "mi", "su", "ne"]
    chosen = lexicon_gen.resolve_candidate(
        random.Random(1), candidates, "water", PartOfSpeech.NOUN, client, "T", "", "llm"
    )
    assert chosen in candidates
    assert client.purposes == ["lexicon.propose_word"]


def test_resolve_candidate_single_candidate_needs_no_choice_either_way():
    client = _CountingClient()
    for mode in ("algorithmic", "llm"):
        assert lexicon_gen.resolve_candidate(random.Random(1), ["ka"], "x", PartOfSpeech.NOUN, client, "T", "", mode) == "ka"
    assert client.purposes == []


def _pending(gloss: str, candidates: list[str]) -> lexicon_gen.PendingWord:
    return lexicon_gen.PendingWord(gloss, PartOfSpeech.NOUN, candidates, finish=lambda c: c)  # type: ignore[arg-type]


def test_batch_chooser_parses_a_well_formed_response_in_one_call():
    client = _CountingClient(response_text="1:2\n2:3\n3:1")
    pending = [_pending("a", ["a1", "a2"]), _pending("b", ["b1", "b2", "b3"]), _pending("c", ["c1", "c2"])]
    chosen = lexicon_gen.choose_best_candidates_batch(pending, client, "T")
    assert chosen == ["a2", "b3", "c1"]
    assert client.purposes == ["lexicon.propose_words_batch"]


def test_batch_chooser_degrades_malformed_or_out_of_range_answers_to_the_first_candidate():
    client = _CountingClient(response_text="sorry, I can't do that\n2:99")
    pending = [_pending("a", ["a1", "a2"]), _pending("b", ["b1", "b2", "b3"])]
    assert lexicon_gen.choose_best_candidates_batch(pending, client, "T") == ["a1", "b1"]


def test_batch_chooser_with_nothing_pending_makes_no_call():
    client = _CountingClient()
    assert lexicon_gen.choose_best_candidates_batch([], client, "T") == []
    assert client.purposes == []


def test_generate_language_algorithmic_makes_no_word_selection_calls():
    client = _CountingClient()
    generate_language("T", GenerationSpec(prompt="p", seed=2, word_selection="algorithmic"), client)
    assert _word_selection_calls(client) == 0


def test_generate_language_llm_batches_the_whole_vocabulary_into_a_few_calls():
    client = _CountingClient()
    language = generate_language("T", GenerationSpec(prompt="p", seed=2, word_selection="llm"), client)
    assert len(language.lexicon.entries) > 380  # the full default vocabulary, not a stub
    # One request per BATCH_CHUNK_SIZE words -- collision retries never call
    # the LLM -- so 400 words cost 4 requests, not ~400.
    assert _word_selection_calls(client) == 4
    assert client.purposes.count("lexicon.propose_words_batch") == 4


def test_a_smaller_vocabulary_size_costs_fewer_batched_calls_and_words():
    client = _CountingClient()
    language = generate_language(
        "T", GenerationSpec(prompt="p", seed=2, word_selection="llm", vocabulary_size=60), client
    )
    assert 55 <= len(language.lexicon.entries) <= 70
    assert _word_selection_calls(client) == 1


def test_word_selection_is_deterministic_per_seed_in_both_modes():
    for mode in ("algorithmic", "llm"):
        spec = GenerationSpec(prompt="p", seed=4, word_selection=mode)
        first = generate_language("T", spec, FakeLLMClient())
        second = generate_language("T", spec, FakeLLMClient())
        assert [e.ipa for e in first.lexicon.entries] == [e.ipa for e in second.lexicon.entries]
