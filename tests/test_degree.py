"""Comparatives and superlatives: marking, the standard of comparison, planning,
rendering and reading back."""

from conlang_generator.core.grammar import GrammarProfile
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient, _fake_degree_of, _fake_plan_dict
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import (
    _decode_adjective_full,
    _render_plan,
    translate_to_conlang,
    translate_to_english,
)

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


def _adjective(language, degree=None, agrees_with=None) -> str:
    slot = PlannedSlot(kind="content", gloss="high", pos="adjective", degree=degree, agrees_with=agrees_with)
    _, romanized, _, _ = _render_plan(SentencePlan(slots=(slot,)), language, _CLIENT, [])
    return romanized[0]


# --- generation -----------------------------------------------------------


def test_comparison_strategies_and_markings_are_all_rolled():
    grammars = [_language(s).grammar for s in range(1, 70)]
    assert {g.comparative_strategy for g in grammars} == {"particle", "case", "exceed"}
    assert {g.comparative_marking for g in grammars} == {"affix", "word"}
    assert {g.superlative_marking for g in grammars} == {"affix", "word"}
    for g in grammars:
        if g.comparative_strategy == "case":
            assert g.comparative_case in g.cases
        else:
            assert g.comparative_case == ""
        wanted = [
            label
            for label, marking in (
                ("comparative", g.comparative_marking), ("superlative", g.superlative_marking),
                ("equative", g.equative_marking), ("excessive", g.excessive_marking), ("elative", g.elative_marking),
            )
            if marking == "affix"
        ]
        assert [a.label for a in g.degree_affixes] == wanted


def test_grammar_defaults_keep_old_saved_languages_valid():
    fields = GrammarProfile.model_fields
    assert fields["comparative_strategy"].default == "particle"
    assert fields["comparative_marking"].default == "word"
    assert fields["superlative_marking"].default == "word"
    assert fields["degree_affixes"].default == ()


# --- planning -------------------------------------------------------------


def test_parse_reads_the_degree_and_ignores_an_unknown_one():
    plan = sentence_planner._parse(
        '[{"kind": "content", "gloss": "big", "pos": "adjective", "degree": "comparative"},'
        ' {"kind": "content", "gloss": "big", "pos": "adjective", "degree": "epic"}]'
    )
    assert plan is not None
    assert plan.slots[0].degree == "comparative" and plan.slots[1].degree is None


def test_the_prompt_describes_the_comparison_strategy():
    particle = _find(lambda g: g.comparative_strategy == "particle" and g.comparative_marking == "word")
    prompt = sentence_planner._build_system_prompt(particle)
    assert 'gloss "than"' in prompt and 'gloss "more"' in prompt
    case = _find(lambda g: g.comparative_strategy == "case" and g.superlative_marking == "affix")
    prompt = sentence_planner._build_system_prompt(case)
    assert f'takes the "{case.grammar.comparative_case}" case' in prompt
    assert '"degree":"superlative"' in prompt
    exceed = _find(lambda g: g.comparative_strategy == "exceed")
    assert 'gloss "exceed"' in sentence_planner._build_system_prompt(exceed)


_BASE = {"word_order": "SVO", "alignment": "nominative_accusative", "tenses": "past,non_past", "has_overt_copula": "true"}


def _shape(sentence: str, **overrides) -> list[tuple]:
    plan = _fake_plan_dict(sentence, {**_BASE, **overrides})
    return [(s.get("kind"), s.get("gloss"), s.get("case"), s.get("degree")) for s in plan["slots"]]


def test_the_english_degree_forms_are_recognized_without_mistaking_nouns():
    assert _fake_degree_of("bigger") == ("big", "comparative")
    assert _fake_degree_of("largest") == ("large", "superlative")
    assert _fake_degree_of("happier") == ("happy", "comparative")
    assert _fake_degree_of("better") == ("good", "comparative")
    assert _fake_degree_of("river") is None and _fake_degree_of("forest") is None and _fake_degree_of("teacher") is None


def test_the_fake_planner_marks_a_comparative_per_strategy():
    assert _shape("The dog is bigger than the cat.") == [
        ("content", "dog", None, None), ("copula", None, None, None), ("content", "more", None, None),
        ("content", "big", None, None), ("content", "than", None, None), ("content", "cat", None, None),
    ]
    case = _shape("The dog is bigger than the cat.", comparative_marking="affix", comparative_strategy="case", comparative_case="dative")
    assert case[-2:] == [("content", "big", None, "comparative"), ("content", "cat", "dative", None)]
    exceed = _shape("The dog is more beautiful than the cat.", comparative_strategy="exceed")
    assert ("content", "exceed", None, None) in exceed and ("copula", None, None, None) not in exceed
    assert exceed[-1] == ("content", "cat", "accusative", None)


def test_a_postpositional_language_puts_than_after_the_standard():
    slots = _shape("The river is longer than the road.", postpositional="true")
    assert [s[1] for s in slots][-2:] == ["road", "than"]


def test_the_fake_planner_marks_a_superlative():
    assert _shape("The dog is the biggest.", superlative_marking="affix")[-1] == ("content", "big", None, "superlative")
    assert _shape("The dog is the most beautiful.")[-2:] == [("content", "most", None, None), ("content", "beautiful", None, None)]


def test_an_ordinary_adjective_sentence_is_not_a_comparison():
    assert all(degree is None for *_, degree in _shape("The teacher is old."))


# --- rendering and decoding -----------------------------------------------


def test_a_degree_suffix_changes_the_adjective_and_decodes_back():
    language = _find(lambda g: g.comparative_marking == "affix" and g.superlative_marking == "affix" and not g.noun_classes)
    bare = _adjective(language)
    comparative, superlative = _adjective(language, "comparative"), _adjective(language, "superlative")
    assert len({bare, comparative, superlative}) == 3
    high = language.lexicon.by_gloss("high")
    assert _decode_adjective_full(language, comparative) == (high, None, "comparative")
    assert _decode_adjective_full(language, superlative) == (high, None, "superlative")


def test_a_word_marked_degree_leaves_the_adjective_bare():
    language = _find(lambda g: g.comparative_marking == "word")
    assert _adjective(language, "comparative") == _adjective(language)


def test_degree_and_class_agreement_combine():
    language = _find(lambda g: g.comparative_marking == "affix" and g.noun_classes == ("animate", "inanimate"))
    high = language.lexicon.by_gloss("high")
    form = _adjective(language, "comparative", agrees_with="dog")
    assert form not in (_adjective(language), _adjective(language, agrees_with="dog"), _adjective(language, "comparative"))
    assert _decode_adjective_full(language, form) == (high, "animate", "comparative")


def test_a_whole_comparison_reads_back_with_its_words():
    word = _find(lambda g: g.comparative_strategy == "particle" and g.comparative_marking == "word" and g.has_overt_copula)
    result = translate_to_conlang("The dog is bigger than the cat.", word, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "more" in english and "big" in english and "than" in english and "cat" in english
    affix = _find(lambda g: g.comparative_strategy == "particle" and g.comparative_marking == "affix")
    result = translate_to_conlang("The dog is bigger than the cat.", affix, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "more big" in english and "than" in english and "<unknown" not in english


def test_an_exceed_language_uses_the_verb_exceed():
    language = _find(lambda g: g.comparative_strategy == "exceed")
    result = translate_to_conlang("The dog is bigger than the cat.", language, _CLIENT)
    assert any(e.primary_gloss == "exceed" for e in result.coined) or result.language.lexicon.by_gloss("exceed")
    assert "exceed" in translate_to_english(result.text, result.language, _CLIENT).text


def test_a_case_marked_standard_uses_no_word_than():
    language = _find(lambda g: g.comparative_strategy == "case")
    result = translate_to_conlang("The dog is bigger than the cat.", language, _CLIENT)
    assert all(e.primary_gloss != "than" for e in result.coined)


def test_the_fluency_prompt_explains_the_comparison_strategy():
    language = _find(lambda g: g.comparative_strategy == "exceed" and g.superlative_marking == "affix")
    spy = _SpyClient()
    translate_to_english("anything", language, spy)
    system = next(r.system for r in spy.requests if r.purpose == "translate.fluency")
    assert "Comparison:" in system and 'verb "exceed"' in system and "the superlative a suffix" in system
