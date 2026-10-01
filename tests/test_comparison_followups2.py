"""Comparison follow-ups, second round: a negative degree ("less big [than
Y]", "least big"), a sufficiency degree ("big enough" -- the one degree
word that follows the adjective, not precedes it), an equative standard
case rolled independently of the comparative's own, and a wider fake-planner
adjective list."""

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import comparison_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
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


def _language(seed: int):
    if seed not in _CACHE:
        _CACHE[seed] = generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())
    return _CACHE[seed]


def _find(predicate, limit: int = 300):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language.grammar):
            return language
    raise AssertionError("no seed found")


def _with(language, **updates):
    return language.model_copy(update={"grammar": language.grammar.model_copy(update=updates)})


def _render(language, *slots):
    updated, romanized, _, glosses = _render_plan(SentencePlan(slots=tuple(slots)), language, _CLIENT, [])
    return updated, romanized, glosses


def _adjective(degree=None, gloss="big") -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="adjective", degree=degree)


def _plan(sentence: str, language):
    return sentence_planner.plan_sentence(sentence, language, _CLIENT)


def _simple(marking_field: str, marking: str):
    language = _find(lambda g: getattr(g, marking_field) == marking and not g.noun_classes and not g.uses_classifiers)
    return _with(
        language, number_agreement_targets=(), case_agreement_targets=(), adjective_placement="global",
        adjective_stack_order=(), adjective_stack_linker=False, suppletive_degrees=(),
    )


# --- generation -------------------------------------------------------------


def test_the_new_labels_are_covered_everywhere():
    assert set(comparison_gen.DEGREE_WORDS) == set(comparison_gen.DEGREE_LABELS) == set(comparison_gen.DEGREE_READING)
    assert {"comparative_negative", "superlative_negative", "sufficiency"} <= set(comparison_gen.DEGREE_LABELS)
    assert comparison_gen.DEGREE_READING["comparative_negative"].format("big") == "less big"
    assert comparison_gen.DEGREE_READING["superlative_negative"].format("big") == "least big"
    assert comparison_gen.DEGREE_READING["sufficiency"].format("big") == "big enough"


def test_the_new_grammar_fields_default_for_older_saved_languages():
    fields = type(_language(1).grammar).model_fields
    assert fields["sufficiency_marking"].default == "word"
    assert fields["equative_standard_case"].default == ""


def test_negative_degree_mirrors_its_positive_counterparts_own_marking():
    for seed in range(1, 60):
        g = _language(seed).grammar
        comp_has_affix = any(a.label == "comparative" for a in g.degree_affixes)
        neg_comp_has_affix = any(a.label == "comparative_negative" for a in g.degree_affixes)
        assert comp_has_affix == neg_comp_has_affix == (g.comparative_marking == "affix")
        sup_has_affix = any(a.label == "superlative" for a in g.degree_affixes)
        neg_sup_has_affix = any(a.label == "superlative_negative" for a in g.degree_affixes)
        assert sup_has_affix == neg_sup_has_affix == (g.superlative_marking == "affix")


def test_sufficiency_marking_and_equative_standard_case_are_rolled():
    grammars = [_language(s).grammar for s in range(1, 120)]
    assert {g.sufficiency_marking for g in grammars} == {"affix", "word"}
    assert any(g.equative_standard_case for g in grammars) and any(not g.equative_standard_case for g in grammars)


# --- negative degree, as a suffix and as a word ------------------------------


def test_a_negative_degree_suffix_marks_the_adjective_and_decodes_back():
    for label in ("comparative_negative", "superlative_negative"):
        worked = False
        for seed in range(1, 200):
            language = _language(seed)
            field = "comparative_marking" if label == "comparative_negative" else "superlative_marking"
            if getattr(language.grammar, field) != "affix" or language.grammar.noun_classes or language.grammar.uses_classifiers:
                continue
            language = _with(
                language, number_agreement_targets=(), case_agreement_targets=(), adjective_placement="global",
                adjective_stack_order=(), adjective_stack_linker=False, suppletive_degrees=(),
            )
            bare = language.lexicon.by_gloss("big").romanization
            updated, parts, _ = _render(language, _adjective(label))
            if parts[0] == bare:
                continue
            decoded = _decode_adjective_full(updated, parts[0])
            if decoded is None or decoded[2] != label:
                continue
            english = translate_to_english(parts[0], updated, _CLIENT).text
            if comparison_gen.DEGREE_READING[label].format("big") in english:
                worked = True
                break
        assert worked, label


def test_less_big_than_and_least_big_round_trip_from_free_text():
    language = _find(lambda g: g.comparative_marking == "word" and g.comparative_strategy == "particle" and g.has_overt_copula)
    result = translate_to_conlang("The dog is less big than the cat.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "less" in english and "big" in english and "cat" in english
    result2 = translate_to_conlang("The dog is least big.", language, _CLIENT)
    english2 = translate_to_english(result2.text, result2.language, _CLIENT).text
    assert "least" in english2 and "big" in english2


# --- sufficiency: the one degree word that follows the adjective -----------


def test_a_sufficiency_suffix_marks_the_adjective_and_decodes_back():
    worked = False
    for seed in range(1, 200):
        language = _language(seed)
        if language.grammar.sufficiency_marking != "affix" or language.grammar.noun_classes or language.grammar.uses_classifiers:
            continue
        language = _with(
            language, number_agreement_targets=(), case_agreement_targets=(), adjective_placement="global",
            adjective_stack_order=(), adjective_stack_linker=False, suppletive_degrees=(),
        )
        bare = language.lexicon.by_gloss("big").romanization
        updated, parts, _ = _render(language, _adjective("sufficiency"))
        if parts[0] == bare:
            continue
        decoded = _decode_adjective_full(updated, parts[0])
        if decoded is None or decoded[2] != "sufficiency":
            continue
        english = translate_to_english(parts[0], updated, _CLIENT).text
        if "big enough" in english:
            worked = True
            break
    assert worked


def test_big_enough_round_trips_and_the_word_follows_the_adjective():
    language = _find(lambda g: g.sufficiency_marking == "word" and g.has_overt_copula)
    plan = _plan("The dog is big enough.", language)
    contents = [s for s in plan.slots if s.kind == "content"]
    big_index = next(i for i, s in enumerate(contents) if s.gloss == "big")
    enough_index = next(i for i, s in enumerate(contents) if s.gloss == "enough")
    assert enough_index == big_index + 1  # "enough" follows "big", not precedes it
    result = translate_to_conlang("The dog is big enough.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "big" in english and "enough" in english


def test_enough_after_an_adjective_does_not_get_swallowed_into_a_noun_phrase():
    # Regression guard: _fake_group_noun_phrases must not treat "enough" (or
    # "less"/"least") as the noun of an attributive-adjective phrase headed
    # by the preceding adjective -- the same trap "too"/"very"/"as"/"than"
    # were already excluded from.
    language = _find(lambda g: g.has_overt_copula)
    plan = _plan("The dog is big enough.", language)
    glosses = [s.gloss for s in plan.slots if s.kind == "content"]
    assert "dog" in glosses and "big" in glosses
    assert not any(g and g.startswith("zznp") for g in glosses)


# --- the equative's own, independently rolled standard case -----------------


def test_an_equative_can_use_a_different_standard_case_than_the_comparative():
    language = _find(
        lambda g: g.equative_standard_case and g.comparative_strategy == "particle" and g.equative_marking == "word"
    )
    plan = _plan("The dog is as big as the cat.", language)
    cat = next(s for s in plan.slots if s.gloss == "cat")
    assert cat.case == language.grammar.equative_standard_case
    # the comparative, meanwhile, still uses the particle "than"
    comparative_plan = _plan("The dog is bigger than the cat.", language)
    assert any(s.gloss == "than" for s in comparative_plan.slots)


def test_an_equative_without_its_own_case_falls_back_to_the_comparatives():
    language = _find(lambda g: g.comparative_strategy == "case" and g.comparative_case)
    language = _with(language, equative_standard_case="")
    plan = _plan("The dog is as big as the cat.", language)
    cat = next(s for s in plan.slots if s.gloss == "cat")
    assert cat.case == language.grammar.comparative_case


def test_an_equative_case_marked_standard_decodes_back_as_as_not_a_preposition():
    language = _find(
        lambda g: g.equative_standard_case and g.comparative_strategy != "case" and g.equative_marking == "word"
    )
    result = translate_to_conlang("The dog is as big as the cat.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "as big as cat" in english or ("as" in english.split() and "cat" in english)


# --- a wider adjective list ---------------------------------------------------


def test_a_newly_added_adjective_is_recognized_for_comparison():
    language = _find(lambda g: g.comparative_marking == "word" and g.comparative_strategy == "particle")
    plan = _plan("The dog is more friendly than the cat.", language)
    assert any(s.gloss == "friendly" and s.pos == "adjective" for s in plan.slots)
    plan2 = _plan("The cat is too greedy.", language)
    assert any(s.gloss == "greedy" and s.pos == "adjective" for s in plan2.slots)


def test_the_planner_prompt_describes_the_new_degrees():
    prompt = sentence_planner._build_system_prompt(_language(1))
    assert "Less big" in prompt and "Least big" in prompt and "Big enough" in prompt
