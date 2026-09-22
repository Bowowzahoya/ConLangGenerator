"""Tests for translation.sentence_planner -- the LLM-drafted structure
step translate_to_conlang now renders. FakeLLMClient's own "sentence_plan"
strategy is exercised for its documented reproduction of the two-pattern
heuristic translate_to_conlang used to hard-code; a stub LLMClient covers
the lenient-parsing/fallback behavior a real, occasionally-malformed LLM
response needs."""

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.base import LLMResponse
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import sentence_planner

# Same fixtures as test_translator.py -- seed=2 (nominative-accusative,
# SVO, has_articles/has_overt_copula both true) and seed=283 (ergative-
# absolutive, SOV) -- redefined locally rather than imported, matching
# this project's own "each test module owns its fixtures" convention.
# seed was 180 until the Russian palatalization-gap phoneme-pool addition
# (gʲ) shifted its downstream RNG draws -- same "seed-shift from new
# content, not a functional regression" pattern documented elsewhere in
# this project's own history (see architecture/OVERVIEW.md).
_NOM_ACC_SEED = 2
_ERGATIVE_SEED = 283


def _language(seed: int):
    return generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())


class _StubLLMClient:
    """A minimal LLMClient stub for testing plan_sentence's own parsing/
    fallback behavior against a fixed, hand-written response -- unlike
    FakeLLMClient, this doesn't try to reproduce any structural
    heuristic, it just returns whatever text it was built with."""

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, request) -> LLMResponse:
        return LLMResponse(text=self.text, model="stub", input_tokens=1, output_tokens=1)


def test_plan_sentence_reproduces_predicate_adjective_pattern_under_fake_strategy():
    language = _language(_NOM_ACC_SEED)
    plan = sentence_planner.plan_sentence("the mountain is high", language, FakeLLMClient())
    kinds = [s.kind for s in plan.slots]
    assert kinds == ["article", "content", "copula", "content"]
    content_glosses = [s.gloss for s in plan.slots if s.kind == "content"]
    assert content_glosses == ["mountain", "high"]
    copula_slot = next(s for s in plan.slots if s.kind == "copula")
    assert copula_slot.agreement == "default"
    assert copula_slot.tense is not None


def test_plan_sentence_reproduces_svo_pattern_with_case_marking_under_fake_strategy():
    language = _language(_NOM_ACC_SEED)
    plan = sentence_planner.plan_sentence("I see the mountain", language, FakeLLMClient())
    kinds = [s.kind for s in plan.slots]
    assert kinds == ["content", "content", "article", "content"]
    subject_slot, verb_slot, _, object_slot = plan.slots
    assert subject_slot.gloss == "i" and subject_slot.pos == "pronoun"
    assert verb_slot.gloss == "see" and verb_slot.pos == "verb" and verb_slot.agreement == "I"
    assert object_slot.gloss == "mountain" and object_slot.case == "accusative"


def test_plan_sentence_marks_ergative_subject_not_accusative_object_under_ergative_alignment():
    language = _language(_ERGATIVE_SEED)
    plan = sentence_planner.plan_sentence("I see the mountain", language, FakeLLMClient())
    subject_slot = next(s for s in plan.slots if s.kind == "content" and s.pos == "pronoun")
    object_slot = next(s for s in plan.slots if s.kind == "content" and s.gloss == "mountain")
    assert subject_slot.case == "ergative"
    assert object_slot.case is None


def test_plan_sentence_negation_slot_appears_for_negated_predicate_adjective():
    language = _language(_NOM_ACC_SEED)
    plan = sentence_planner.plan_sentence("the mountain is not high", language, FakeLLMClient())
    kinds = [s.kind for s in plan.slots]
    assert "negation" in kinds
    assert kinds.index("negation") > kinds.index("copula")  # next to the copula it negates


def test_plan_sentence_falls_back_to_one_content_slot_per_word_for_other_shapes():
    language = _language(_NOM_ACC_SEED)
    plan = sentence_planner.plan_sentence("I see the mountain and the river", language, FakeLLMClient())
    # Neither the 2-word copula pattern nor the 3-word SVO pattern applies
    # once "and" pulls in a second noun phrase -- every content word
    # (including "and" itself) becomes its own bare content slot.
    glosses = [s.gloss for s in plan.slots]
    assert glosses == ["i", "see", "mountain", "and", "river"]
    assert all(s.kind == "content" for s in plan.slots)


def test_plan_sentence_falls_back_to_word_for_word_when_llm_response_is_unparseable():
    # The word-for-word fallback only strips articles (matching
    # translate_to_conlang's own naive fallback of old), not copulas --
    # "is" stays a bare content word here, unlike the structured
    # predicate-adjective plan the fake/real planner would normally draft.
    language = _language(_NOM_ACC_SEED)
    plan = sentence_planner.plan_sentence(
        "the mountain is high", language, _StubLLMClient("I'm sorry, I can't help with that.")
    )
    assert [s.kind for s in plan.slots] == ["content", "content", "content"]
    assert [s.gloss for s in plan.slots] == ["mountain", "is", "high"]


def test_plan_sentence_falls_back_to_word_for_word_when_llm_response_is_empty_json():
    language = _language(_NOM_ACC_SEED)
    plan = sentence_planner.plan_sentence("the mountain is high", language, _StubLLMClient("[]"))
    assert [s.gloss for s in plan.slots] == ["mountain", "is", "high"]


def test_plan_sentence_tolerates_a_slot_with_unknown_kind_by_dropping_it_only():
    language = _language(_NOM_ACC_SEED)
    response = (
        '[{"kind": "content", "gloss": "mountain", "pos": "noun"}, '
        '{"kind": "question"}, '
        '{"kind": "content", "gloss": "high", "pos": "adjective"}]'
    )
    plan = sentence_planner.plan_sentence("the mountain is high", language, _StubLLMClient(response))
    assert [s.gloss for s in plan.slots] == ["mountain", "high"]


def test_plan_sentence_defaults_an_invalid_pos_to_noun():
    language = _language(_NOM_ACC_SEED)
    response = '[{"kind": "content", "gloss": "mountain", "pos": "not-a-real-pos"}]'
    plan = sentence_planner.plan_sentence("mountain", language, _StubLLMClient(response))
    assert plan.slots[0].pos == "noun"


def test_plan_sentence_extracts_json_even_with_surrounding_prose():
    language = _language(_NOM_ACC_SEED)
    response = 'Sure, here is the plan:\n[{"kind": "article"}, {"kind": "content", "gloss": "mountain", "pos": "noun"}]\nHope that helps!'
    plan = sentence_planner.plan_sentence("the mountain", language, _StubLLMClient(response))
    assert [s.kind for s in plan.slots] == ["article", "content"]
