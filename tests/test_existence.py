"""Existential ("there is X") and predicative possession ("A has B")
constructions: strategies, planning and rendering."""

from conlang_generator.core.grammar import GrammarProfile
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient, _fake_plan_dict
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.translator import _decode_verb_full, translate_to_conlang, translate_to_english

_CLIENT = FakeLLMClient()
_CACHE: dict[int, object] = {}


class _SpyClient(FakeLLMClient):
    def __init__(self) -> None:
        self.requests: list = []

    def complete(self, request):
        self.requests.append(request)
        return super().complete(request)


def _language(seed: int):
    if seed not in _CACHE:
        _CACHE[seed] = generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())
    return _CACHE[seed]


def _find(predicate, limit: int = 250):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language.grammar):
            return language
    raise AssertionError("no seed found")


# --- generation -----------------------------------------------------------


def test_every_strategy_combination_occurs():
    combos = {(g.existential, g.possession_clause) for g in (_language(s).grammar for s in range(1, 60))}
    assert combos == {("copula", "have"), ("copula", "dative_be"), ("verb", "have"), ("verb", "dative_be")}


def test_grammar_defaults_keep_old_saved_languages_valid():
    fields = GrammarProfile.model_fields
    assert fields["existential"].default == "copula"
    assert fields["possession_clause"].default == "have"


# --- planning -------------------------------------------------------------


def test_the_prompt_describes_this_languages_strategies():
    verb_dative = _find(lambda g: g.existential == "verb" and g.possession_clause == "dative_be" and "dative" in g.cases)
    prompt = sentence_planner._build_system_prompt(verb_dative)
    assert 'gloss "exist"' in prompt
    assert 'no verb "have"' in prompt and 'the dative case ("case":"dative")' in prompt
    copula_have = _find(lambda g: g.existential == "copula" and g.possession_clause == "have" and g.has_overt_copula)
    prompt = sentence_planner._build_system_prompt(copula_have)
    assert "followed by the copula slot" in prompt
    assert 'verb is the content verb "have"' in prompt
    no_dative = _find(lambda g: g.possession_clause == "dative_be" and "dative" not in g.cases)
    assert '"possessive":true on the possessor slot' in sentence_planner._build_system_prompt(no_dative)
    no_copula = _find(lambda g: g.existential == "copula" and not g.has_overt_copula)
    assert "no overt copula" in sentence_planner._build_system_prompt(no_copula)


_BASE = {
    "word_order": "SVO", "alignment": "nominative_accusative", "tenses": "past,non_past",
    "has_overt_copula": "true", "cases": "nominative,accusative,genitive,dative",
}


def _shape(sentence: str, **overrides) -> list[tuple]:
    plan = _fake_plan_dict(sentence, {**_BASE, **overrides})
    return [(s.get("kind"), s.get("gloss"), s.get("case"), s.get("possessive")) for s in plan["slots"]]


def test_the_fake_planner_plans_an_existential_per_strategy():
    assert _shape("There is a dog.", existential="copula") == [("content", "dog", None, None), ("copula", None, None, None)]
    assert _shape("There are dogs.", existential="verb") == [("content", "dog", None, None), ("content", "exist", None, None)]
    assert _shape("There is a dog.", has_overt_copula="false") == [("content", "dog", None, None)]


def test_an_existential_question_keeps_its_mood_and_a_verb_initial_language_puts_the_verb_first():
    plan = _fake_plan_dict("Is there a river?", {**_BASE, "existential": "verb"})
    assert plan["mood"] == "question"
    assert [s.get("gloss") for s in plan["slots"]] == ["river", "exist"]
    assert _shape("There is a river.", existential="verb", word_order="VSO")[0][1] == "exist"


def test_negated_and_past_existentials():
    slots = _shape("There was no river.", existential="copula")
    assert ("negation", None, None, None) in slots
    plan = _fake_plan_dict("There was a river.", {**_BASE, "existential": "verb"})
    assert next(s for s in plan["slots"] if s.get("gloss") == "exist")["tense"] == "past"


def test_a_have_language_keeps_the_transitive_verb():
    assert _shape("I have a dog.", possession_clause="have") == [
        ("content", "i", None, None), ("content", "have", None, None), ("content", "dog", "accusative", None),
    ]
    plan = _fake_plan_dict("I had a dog.", {**_BASE, "possession_clause": "have"})
    assert next(s for s in plan["slots"] if s.get("gloss") == "have")["tense"] == "past"


def test_a_dative_be_language_puts_the_possessor_first_in_the_dative():
    slots = _shape("I have a dog.", possession_clause="dative_be")
    assert slots[0] == ("content", "i", "dative", None)
    assert ("content", "dog", None, None) in slots and ("copula", None, None, None) in slots
    assert all(gloss != "have" for _, gloss, _, _ in slots)


def test_without_a_dative_the_possessor_is_possessor_marked():
    slots = _shape("The man has two dogs.", possession_clause="dative_be", cases="nominative,accusative", existential="verb")
    assert slots[0] == ("content", "man", None, True)
    assert slots[-1][1] == "exist"


# --- rendering ------------------------------------------------------------


def test_an_existential_verb_language_renders_and_decodes_the_verb_exist():
    language = _find(lambda g: g.existential == "verb" and g.word_order.value in ("SVO", "SOV"))
    result = translate_to_conlang("There was a dog.", language, _CLIENT)
    exist = result.language.lexicon.by_gloss("exist")
    assert exist is not None and any(e.primary_gloss == "exist" for e in result.coined)
    decoded = [_decode_verb_full(result.language, t) for t in result.text.split()]
    assert any(d is not None and d[0] == exist for d in decoded)
    assert "exist" in translate_to_english(result.text, result.language, _CLIENT).text


def test_a_copula_existential_uses_the_copula_and_no_new_verb():
    language = _find(lambda g: g.existential == "copula" and g.has_overt_copula)
    result = translate_to_conlang("There is a dog.", language, _CLIENT)
    assert all(e.primary_gloss != "exist" for e in result.coined)
    be = language.lexicon.by_gloss("be")
    assert be is not None
    assert any(_decode_verb_full(result.language, t) is not None for t in result.text.split())


def test_a_dative_be_language_never_uses_the_verb_have():
    language = _find(lambda g: g.possession_clause == "dative_be" and "dative" in g.cases)
    result = translate_to_conlang("I have a dog.", language, _CLIENT)
    decoded = [_decode_verb_full(result.language, t) for t in result.text.split()]
    assert all(d is None or d[0].primary_gloss != "have" for d in decoded)
    have_language = _find(lambda g: g.possession_clause == "have")
    have_result = translate_to_conlang("I have a dog.", have_language, _CLIENT)
    have_decoded = [_decode_verb_full(have_result.language, t) for t in have_result.text.split()]
    assert any(d is not None and d[0].primary_gloss == "have" for d in have_decoded)


def test_the_dative_possessor_is_a_different_form_from_the_bare_pronoun():
    language = _find(lambda g: g.possession_clause == "dative_be" and "dative" in g.cases)
    from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
    from conlang_generator.translation.translator import _render_plan

    slot = PlannedSlot(kind="content", gloss="I", pos="pronoun", case="dative")
    _, dative, _, _ = _render_plan(SentencePlan(slots=(slot,)), language, _CLIENT, [])
    _, bare, _, _ = _render_plan(
        SentencePlan(slots=(PlannedSlot(kind="content", gloss="I", pos="pronoun"),)), language, _CLIENT, []
    )
    assert dative != bare


def test_an_existential_question_gets_the_question_particle():
    language = _find(lambda g: g.word_order.value in ("SVO", "SOV"))
    particle = language.romanization.apply(language.grammar.question_particle)
    result = translate_to_conlang("Is there a dog?", language, _CLIENT)
    assert result.text.split()[-1] == particle


# --- reading back ---------------------------------------------------------


def test_the_fluency_prompt_explains_this_languages_constructions():
    language = _find(lambda g: g.existential == "verb" and g.possession_clause == "dative_be")
    spy = _SpyClient()
    translate_to_english("anything", language, spy)
    system = next(r.system for r in spy.requests if r.purpose == "translate.fluency")
    assert 'X plus the verb "exist"' in system
    assert 'no verb "have"' in system
    other = _find(lambda g: g.existential == "copula" and g.possession_clause == "have")
    spy = _SpyClient()
    translate_to_english("anything", other, spy)
    system = next(r.system for r in spy.requests if r.purpose == "translate.fluency")
    assert 'the ordinary transitive verb "have"' in system
