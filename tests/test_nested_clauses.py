"""The nested sentence plan: subordinate clauses (complement, adverbial,
relative) as ``"clause"`` slots holding their own plan -- parsing, depth
cap, rendering (linking word placement, recursion) and decoding."""

import json

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient, _fake_plan_dict
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.translator import _decode_verb, translate_to_conlang, translate_to_english


def _language(seed: int = 278):
    return generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())


def _with_order(orders: set[str]):
    for seed in range(1, 200):
        language = _language(seed)
        if language.grammar.word_order.value in orders:
            return language
    raise AssertionError("no seed found")


def _content(gloss: str, pos: str = "noun") -> dict:
    return {"kind": "content", "gloss": gloss, "pos": pos}


def _clause(linker: str, slots: list[dict], role: str = "complement") -> dict:
    return {"kind": "clause", "gloss": linker, "role": role, "clause": {"slots": slots}}


# --- parsing --------------------------------------------------------------


def test_a_clause_slot_holds_its_own_nested_plan():
    plan = sentence_planner._parse(
        json.dumps({"mood": "declarative", "slots": [_content("I", "pronoun"), _clause("that", [_content("you", "pronoun")])]})
    )
    assert plan is not None
    clause_slot = plan.slots[1]
    assert clause_slot.kind == "clause"
    assert clause_slot.gloss == "that"
    assert clause_slot.role == "complement"
    assert [s.gloss for s in clause_slot.clause.slots] == ["you"]


def test_clauses_can_nest_and_flatten_slots_reads_them_in_order():
    inner = _clause("when", [_content("dog")], "adverbial")
    plan = sentence_planner._parse(
        json.dumps([_content("I", "pronoun"), _clause("that", [_content("you", "pronoun"), inner])])
    )
    assert plan is not None
    assert [s.gloss for s in sentence_planner.flatten_slots(plan)] == ["i", "you", "dog"]


def test_a_clause_nested_beyond_the_depth_cap_is_flattened_not_dropped():
    deepest = _content("deep")
    slots = [_clause("that", [_clause("that", [_clause("that", [_clause("that", [deepest])])])])]
    plan = sentence_planner._parse(json.dumps(slots))
    assert plan is not None

    def depth(p, d=1):
        nested = [s for s in p.slots if s.kind == "clause"]
        return max((depth(s.clause, d + 1) for s in nested), default=d)

    assert depth(plan) <= sentence_planner.MAX_CLAUSE_DEPTH
    assert "deep" in [s.gloss for s in sentence_planner.flatten_slots(plan)]


def test_an_empty_or_malformed_clause_slot_is_skipped():
    plan = sentence_planner._parse(
        json.dumps([_content("I", "pronoun"), {"kind": "clause", "gloss": "that"}, _clause("if", [])])
    )
    assert plan is not None
    assert [s.kind for s in plan.slots] == ["content"]


def test_an_unknown_role_becomes_none():
    plan = sentence_planner._parse(json.dumps([_clause("that", [_content("dog")], role="weird")]))
    assert plan is not None
    assert plan.slots[0].role is None


# --- the fake planner -----------------------------------------------------

_META = {"word_order": "SVO", "alignment": "nominative_accusative", "tenses": "past,non_past"}


def test_the_fake_planner_nests_a_clause_after_a_subordinating_word():
    plan = _fake_plan_dict("I see that you see the river.", _META)
    assert [s["kind"] for s in plan["slots"]][-1] == "clause"
    clause = plan["slots"][-1]
    assert clause["gloss"] == "that"
    assert any(s.get("gloss") == "river" for s in clause["clause"]["slots"])


def test_the_fake_planner_does_not_split_a_demonstrative_that():
    plan = _fake_plan_dict("I see that mountain.", _META)
    assert all(s["kind"] != "clause" for s in plan["slots"])


def test_the_fake_planner_nests_repeatedly():
    plan = _fake_plan_dict("I stay because you see the river when I sleep.", _META)
    outer = plan["slots"][-1]
    assert outer["gloss"] == "because"
    assert outer["clause"]["slots"][-1]["gloss"] == "when"


# --- rendering ------------------------------------------------------------


def test_the_linking_word_follows_the_clause_in_a_verb_final_language():
    language = _with_order({"SOV", "OSV"})
    client = FakeLLMClient()
    result = translate_to_conlang("I see that you see the river.", language, client)
    linker = result.language.lexicon.by_gloss("that")
    assert linker is not None
    assert result.text.split()[-1] == linker.romanization


def test_the_linking_word_precedes_the_clause_in_other_languages():
    language = _with_order({"SVO", "VSO"})
    client = FakeLLMClient()
    result = translate_to_conlang("I see that you see the river.", language, client)
    linker = result.language.lexicon.by_gloss("that")
    river = result.language.lexicon.by_gloss("river")
    tokens = result.text.split()
    assert linker.romanization in tokens
    assert tokens.index(linker.romanization) < max(i for i, t in enumerate(tokens) if t.startswith(river.romanization[:2]))


def test_the_subordinate_clause_words_are_all_rendered():
    language = _language()
    client = FakeLLMClient()
    flat = translate_to_conlang("I see the river.", language, client)
    nested = translate_to_conlang("I see the river because you see the mountain.", language, client)
    assert len(nested.text.split()) > len(flat.text.split()) + 2
    mountain = language.lexicon.by_gloss("mountain")
    assert any(t.startswith(mountain.romanization[:3]) for t in nested.text.split())


def test_a_subordinate_clause_is_never_an_imperative():
    language = _language()
    client = FakeLLMClient()
    result = translate_to_conlang("See the river if you see the mountain!", language, client)
    decoded = [_decode_verb(result.language, t) for t in result.text.split()]
    imperatives = [d for d in decoded if d is not None and d[1] == "imperative"]
    assert len(imperatives) == 1  # only the main clause's verb


# --- decoding -------------------------------------------------------------


def test_decoding_a_nested_translation_keeps_the_linking_word_and_both_clauses():
    language = _language()
    client = FakeLLMClient()
    result = translate_to_conlang("I see that you see the river.", language, client)
    english = translate_to_english(result.text, result.language, client).text
    assert "that" in english
    assert "river" in english
