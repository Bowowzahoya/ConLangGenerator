"""Noun-phrase follow-ups, second round: partial pronoun suppletion, adjective
placement/stacking order, and definiteness beyond two articles."""

import random

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import np_followups_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import (
    _article_forms,
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


def _adjective(gloss: str) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="adjective")


def _noun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="noun", **kw)


_VERB = PlannedSlot(kind="content", gloss="see", pos="verb", agreement="I")


def _simple(**updates):
    """A language with no class/number/case agreement, so an adjective renders bare."""
    language = _find(lambda g: not g.noun_classes and g.class_marking == "none" and not g.uses_classifiers)
    base = dict(
        number_agreement_targets=(), case_agreement_targets=(), adjective_placement="global",
        adjective_before_classes=(), adjective_stack_order=(), adjective_stack_linker=False, degree_affixes=(),
        periphrastic_labels=(), negation_strategy="particle", verb_negative_affixes=(),
    )
    return _with(language, **{**base, **updates})


def _glosses(language, *slots):
    return [g for g in _render(language, *slots)[2]]


# --- generation -----------------------------------------------------------------


def test_the_follow_up_choices_are_rolled():
    grammars = [_language(s).grammar for s in range(1, 120)]
    assert {g.adjective_placement for g in grammars} == {"global", "split"}
    assert any(g.adjective_stack_order for g in grammars) and any(g.adjective_stack_linker for g in grammars)
    assert any(g.suppletive_pronoun_case_limits for g in grammars)
    assert {g.article_source for g in grammars} == {"own", "demonstrative"}
    assert any(g.has_specific_article for g in grammars)
    for g in grammars:
        if g.adjective_placement == "split":
            assert g.adjective_before_classes and set(g.adjective_before_classes) < set(np_followups_gen.ADJECTIVE_CLASSES)
        if g.adjective_stack_order:
            assert sorted(g.adjective_stack_order) == sorted(np_followups_gen.ADJECTIVE_CLASSES)
        if g.has_specific_article:
            assert g.has_indefinite_article
        for person, cases in g.suppletive_pronoun_case_limits:
            assert person in g.suppletive_pronoun_persons and set(cases) < set(g.cases)


def test_the_new_grammar_fields_default_for_older_saved_languages():
    fields = type(_language(1).grammar).model_fields
    assert fields["adjective_placement"].default == "global" and fields["article_source"].default == "own"
    assert fields["suppletive_pronoun_case_limits"].default == () and fields["has_specific_article"].default is False


def test_adjectives_fall_into_order_classes():
    assert np_followups_gen.adjective_class("big") == "size"
    assert np_followups_gen.adjective_class("red") == "colour"
    assert np_followups_gen.adjective_class("old") == "age"
    assert np_followups_gen.adjective_class("good") == "quality"
    assert np_followups_gen.adjective_class("wooden") == "other"


# --- partial pronoun suppletion ------------------------------------------------------


def _suppletive_language():
    language = _find(lambda g: "accusative" in g.cases and "genitive" in g.cases and not g.uses_classifiers)
    return _with(
        language, suppletive_pronoun_persons=("I", "you"), suppletive_pronoun_case_limits=(("I", ("accusative",)),),
        possession="genitive",
    )


def test_a_limited_person_is_suppletive_only_in_its_listed_cases():
    language = _suppletive_language()
    i_slot = lambda case: PlannedSlot(kind="content", gloss="I", pos="pronoun", case=case)  # noqa: E731
    updated, accusative, _ = _render(language, i_slot("accusative"))
    assert "i-accusative" in [e.primary_gloss.lower() for e in updated.lexicon.entries]
    updated, genitive, glosses = _render(language, i_slot("genitive"))
    assert "i-genitive" not in [e.primary_gloss.lower() for e in updated.lexicon.entries]
    assert genitive[0] != language.lexicon.by_gloss("I").romanization  # the ordinary case suffix
    assert genitive != accusative


def test_a_person_without_a_limit_is_suppletive_in_every_case():
    language = _suppletive_language()
    updated, _, _ = _render(language, PlannedSlot(kind="content", gloss="you", pos="pronoun", case="genitive"))
    assert "you-genitive" in [e.primary_gloss.lower() for e in updated.lexicon.entries]


def test_a_regular_case_form_of_a_limited_person_reads_back():
    language = _suppletive_language()
    updated, parts, _ = _render(language, PlannedSlot(kind="content", gloss="I", pos="pronoun", case="genitive"))
    assert "<unknown" not in translate_to_english(parts[0], updated, _CLIENT).text


# --- adjective placement and stacking ----------------------------------------------------


def test_a_language_without_the_new_features_keeps_the_planner_order():
    language = _simple(adjective_after_noun=False)
    assert _glosses(language, _adjective("big"), _adjective("red"), _noun("dog")) == ["big", "red", "dog"]
    language = _simple(adjective_after_noun=True)
    assert _glosses(language, _noun("dog"), _adjective("big"), _adjective("red")) == ["dog", "big", "red"]


def test_stacked_adjectives_follow_the_class_order():
    order = ("colour", "size", "quality", "age", "other")
    before = _simple(adjective_after_noun=False, adjective_stack_order=order)
    assert _glosses(before, _adjective("big"), _adjective("red"), _noun("dog")) == ["red", "big", "dog"]
    assert _glosses(before, _adjective("red"), _adjective("big"), _noun("dog")) == ["red", "big", "dog"]


def test_stacked_adjectives_mirror_after_the_noun():
    order = ("colour", "size", "quality", "age", "other")
    after = _simple(adjective_after_noun=True, adjective_stack_order=order)
    assert _glosses(after, _noun("dog"), _adjective("big"), _adjective("red")) == ["dog", "big", "red"]
    assert _glosses(after, _noun("dog"), _adjective("red"), _adjective("big")) == ["dog", "big", "red"]


def test_stacked_adjectives_can_be_joined_by_and():
    language = _simple(adjective_after_noun=False, adjective_stack_linker=True)
    assert _glosses(language, _adjective("big"), _adjective("red"), _noun("dog")) == ["big", "and", "red", "dog"]
    assert _glosses(language, _adjective("big"), _noun("dog")) == ["big", "dog"]


def test_a_split_language_puts_each_class_on_its_side():
    language = _simple(
        adjective_after_noun=False, adjective_placement="split", adjective_before_classes=("size", "age")
    )
    assert _glosses(language, _adjective("red"), _adjective("big"), _noun("dog"), _VERB) == ["big", "dog", "red", "see"]
    assert _glosses(language, _noun("dog"), _adjective("old"), _VERB) == ["old", "dog", "see"]


def test_a_split_language_leaves_a_predicate_adjective_alone():
    language = _simple(adjective_placement="split", adjective_before_classes=("size",))
    assert _glosses(language, _noun("dog"), _adjective("red")) == ["dog", "red"]


def test_an_adjective_keeps_its_own_agreement_when_it_moves():
    language = _find(lambda g: g.noun_classes and "adjective" in g.class_agreement_targets and not g.uses_classifiers)
    moved = _with(language, adjective_placement="split", adjective_before_classes=("size",), adjective_after_noun=False,
                  adjective_stack_order=(), adjective_stack_linker=False)
    plain = _with(language, adjective_placement="global", adjective_before_classes=(), adjective_after_noun=True,
                  adjective_stack_order=(), adjective_stack_linker=False)
    dog_after_moved = _render(moved, _adjective("red"), _noun("dog"), _VERB)[1]
    dog_after_plain = _render(plain, _noun("dog"), _adjective("red"), _VERB)[1]
    assert dog_after_moved == dog_after_plain  # red is after the dog in both, and agrees the same way


def test_stacked_adjectives_read_back():
    language = _simple(adjective_after_noun=False, adjective_stack_linker=True)
    result = translate_to_conlang("I see the big red dog.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "big" in english and "red" in english and "dog" in english


def test_the_fake_planner_plans_attributive_adjectives_on_the_languages_side():
    for after in (False, True):
        language = _find(lambda g: g.adjective_after_noun == after)
        plan = sentence_planner.plan_sentence("I see the big red dog.", language, _CLIENT)
        glosses = [s.gloss for s in plan.slots if s.kind == "content"]
        assert glosses.count("big") == 1 and glosses.count("red") == 1
        noun = glosses.index("dog")
        assert (glosses.index("big") > noun) == after


# --- definiteness ------------------------------------------------------------------------------


def _derived_article_language():
    return _find(lambda g: g.article_source == "demonstrative")


def test_a_demonstrative_derived_article_is_a_reduced_that():
    language = _derived_article_language()
    the = language.lexicon.by_gloss("the")
    that = language.lexicon.by_gloss("that")
    assert the.romanization != that.romanization
    assert len(the.ipa.replace("ˈ", "")) < len(that.ipa.replace("ˈ", "")) or the.ipa == that.ipa[:1]
    assert language.lexicon.by_form(the.romanization).primary_gloss == "the"


def test_the_derived_article_is_dropped_on_reading_back():
    language = _derived_article_language()
    result = translate_to_conlang("I see the river.", language, _CLIENT)
    assert language.lexicon.by_gloss("the").romanization.lower() in _article_forms(result.language)
    assert "<unknown" not in translate_to_english(result.text, result.language, _CLIENT).text


def test_derivation_needs_something_shorter():
    inventory = _language(1).phonology
    assert np_followups_gen.derive_article_ipa("", inventory) is None


def _specific_language():
    return _find(lambda g: g.has_specific_article and not g.uses_classifiers and not g.noun_classes)


def test_a_specific_article_is_its_own_word_and_reads_back():
    language = _specific_language()
    updated, parts, glosses = _render(language, PlannedSlot(kind="specific_article"), _noun("dog"))
    assert glosses[0] == "a-certain" and parts[0] != parts[1]
    assert "a certain" in translate_to_english(parts[0], updated, _CLIENT).text


def test_without_a_specific_article_it_falls_back_to_the_indefinite_or_nothing():
    fallback = _find(lambda g: g.has_indefinite_article and not g.has_specific_article and not g.noun_classes)
    assert _render(fallback, PlannedSlot(kind="specific_article"), _noun("dog"))[2][0] == "a"
    none = _find(lambda g: not g.has_indefinite_article)
    assert _render(none, PlannedSlot(kind="specific_article"), _noun("dog"))[2] == ["dog"]


def test_the_fake_planner_marks_a_specific_article_only_where_the_language_has_one():
    language = _specific_language()
    plan = sentence_planner.plan_sentence("I see a certain dog.", language, _CLIENT)
    assert any(slot.kind == "specific_article" for slot in plan.slots)
    other = _find(lambda g: g.has_indefinite_article and not g.has_specific_article)
    plan = sentence_planner.plan_sentence("I see a certain dog.", other, _CLIENT)
    assert all(slot.kind != "specific_article" for slot in plan.slots)


def test_the_planner_prompt_describes_the_new_pieces():
    language = _specific_language()
    prompt = sentence_planner._build_system_prompt(language)
    assert '"specific_article"' in prompt and "puts stacked adjectives in this language's order" in prompt
    assert random.Random(1)  # keeps the import used
