"""Numeral classifiers: which languages use them, the category of a noun, and
rendering/decoding."""

from conlang_generator.core.grammar import GrammarProfile, MorphologicalType
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import classifier_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import _render_plan, translate_to_conlang, translate_to_english

_CLIENT = FakeLLMClient()
_CACHE: dict[int, object] = {}


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


def _noun(gloss: str) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="noun")


def _classifier_language():
    """A classifier language of the plain kind: numeral-classifier-noun order, demonstratives take one too,
    and classifiers for animals and long things."""
    return _find(
        lambda g: g.uses_classifiers
        and not g.classifier_after_noun
        and g.classifier_with_demonstrative
        and g.classifier_assignment == "category"
        and g.repeater_rate == 0.0
        and {"animal", "long"} <= set(g.classifier_categories)
    )


_TWO = PlannedSlot(kind="content", gloss="two", pos="numeral")


def _render(language, *slots):
    updated, romanized, _, glosses = _render_plan(SentencePlan(slots=tuple(slots)), language, _CLIENT, [])
    return updated, romanized, glosses


# --- generation -----------------------------------------------------------


def test_classifier_use_is_rolled_and_more_common_when_isolating():
    grammars = [_language(s).grammar for s in range(1, 120)]
    isolating = [g.uses_classifiers for g in grammars if g.morphological_type is MorphologicalType.ISOLATING]
    other = [g.uses_classifiers for g in grammars if g.morphological_type is not MorphologicalType.ISOLATING]
    assert any(g.uses_classifiers for g in grammars) and not all(g.uses_classifiers for g in grammars)
    assert sum(isolating) / len(isolating) > sum(other) / len(other)


def test_a_classifier_language_keeps_the_noun_singular_after_a_numeral():
    for seed in range(1, 80):
        grammar = _language(seed).grammar
        if grammar.uses_classifiers:
            assert grammar.plural_after_numeral is False


def test_grammar_default_keeps_old_saved_languages_valid():
    assert GrammarProfile.model_fields["uses_classifiers"].default is False


def test_a_nouns_classifier_category_comes_from_its_meaning():
    assert [classifier_gen.classifier_category(w) for w in ("teacher", "dog", "river", "leaf", "stone", "idea")] == [
        "human", "animal", "long", "flat", "round", "general",
    ]
    assert classifier_gen.classifier_gloss("animal") == "classifier-animal"


# --- planning -------------------------------------------------------------


def test_the_prompt_says_the_renderer_adds_the_classifier():
    language = _classifier_language()
    assert "CLASSIFIER word that the renderer adds itself" in sentence_planner._build_system_prompt(language)
    other = _find(lambda g: not g.uses_classifiers)
    assert "no classifiers" in sentence_planner._build_system_prompt(other)


# --- rendering and decoding -----------------------------------------------


def test_a_classifier_follows_a_numeral_and_depends_on_the_noun():
    language = _classifier_language()
    updated, dog_tokens, dog_glosses = _render(language, _TWO, _noun("dog"))
    _, river_tokens, river_glosses = _render(language, _TWO, _noun("river"))
    assert len(dog_tokens) == 3 and len(river_tokens) == 3
    assert dog_glosses[1] == "classifier-animal" and river_glosses[1] == "classifier-long"
    assert dog_tokens[1] != river_tokens[1]
    assert updated.lexicon.by_gloss("classifier-animal") is not None


def test_a_language_without_classifiers_adds_none():
    language = _find(lambda g: not g.uses_classifiers)
    assert len(_render(language, _TWO, _noun("dog"))[1]) == 2


def test_a_demonstrative_also_takes_a_classifier_and_an_adjective_does_not_block_it():
    language = _classifier_language()
    demonstrative = PlannedSlot(kind="demonstrative", gloss="this")
    assert _render(language, demonstrative, _noun("dog"))[2][1] == "classifier-animal"
    adjective = PlannedSlot(kind="content", gloss="high", pos="adjective")
    _, tokens, glosses = _render(language, _TWO, adjective, _noun("dog"))
    assert glosses[1] == "classifier-animal" and len(tokens) == 4


def test_no_classifier_without_a_following_noun():
    language = _classifier_language()
    verb = PlannedSlot(kind="content", gloss="see", pos="verb")
    assert len(_render(language, _TWO, verb)[1]) == 2
    assert len(_render(language, _TWO)[1]) == 1


def test_a_classifier_is_coined_once_and_reused():
    language = _classifier_language()
    updated, first, _ = _render(language, _TWO, _noun("dog"))
    _, second, _ = _render(updated, _TWO, _noun("cat"))
    assert first[1] == second[1]  # both animals: the same classifier word


def test_the_noun_stays_singular_after_a_numeral_in_a_classifier_language():
    language = _classifier_language()
    two_dogs = PlannedSlot(kind="content", gloss="dog", pos="noun", number="plural")
    assert _render(language, _TWO, two_dogs)[1][2] == _render(language, _TWO, _noun("dog"))[1][2]


def test_the_classifier_is_dropped_on_the_way_back_to_english():
    language = _classifier_language()
    result = translate_to_conlang("I see two dogs.", language, _CLIENT)
    assert any(e.primary_gloss == "classifier-animal" for e in result.coined)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "classifier" not in english and "dog" in english and "<unknown" not in english


# --- variety: categories, order, demonstratives ---------------------------


def test_the_categories_cover_twelve_kinds_of_noun():
    assert len(classifier_gen.CATEGORIES) == 12
    picks = {
        "cup": "container", "house": "building", "boat": "vehicle", "key": "tool", "bread": "food", "flower": "plant",
    }
    assert {w: classifier_gen.classifier_category(w) for w in picks} == picks


def test_a_noun_without_its_own_classifier_takes_the_general_one():
    assert classifier_gen.classifier_category("cup", ("human", "general")) == "general"
    assert classifier_gen.classifier_category("teacher", ("human", "general")) == "human"
    assert classifier_gen.classifier_category("cup", None) == "container"


def test_each_classifier_language_has_a_subset_of_categories_with_general():
    languages = [g for g in (_language(s).grammar for s in range(1, 200)) if g.uses_classifiers]
    assert languages
    for grammar in languages:
        assert "general" in grammar.classifier_categories
        assert set(grammar.classifier_categories) <= set(classifier_gen.CATEGORIES)
        assert 4 <= len(grammar.classifier_categories) <= len(classifier_gen.CATEGORIES)
    assert len({g.classifier_categories for g in languages}) > 3
    assert {g.classifier_after_noun for g in languages} == {True, False}
    assert {g.classifier_with_demonstrative for g in languages} == {True, False}


def test_a_language_without_classifiers_has_no_categories():
    assert _find(lambda g: not g.uses_classifiers).grammar.classifier_categories == ()


def test_an_old_classifier_language_without_categories_uses_the_original_six():
    language = _find(
        lambda g: g.uses_classifiers and not g.classifier_after_noun and g.classifier_assignment == "category"
        and g.repeater_rate == 0.0
    )
    old = language.model_copy(update={"grammar": language.grammar.model_copy(update={"classifier_categories": ()})})
    assert _render(old, _TWO, _noun("cup"))[2][1] == "classifier-round" or _render(old, _TWO, _noun("cup"))[2][1] == "classifier-general"
    assert _render(old, _TWO, _noun("dog"))[2][1] == "classifier-animal"


def test_a_missing_category_falls_back_to_general_when_rendering():
    language = _find(
        lambda g: g.uses_classifiers and not g.classifier_after_noun and "container" not in g.classifier_categories
        and g.classifier_assignment == "category" and g.repeater_rate == 0.0
    )
    assert _render(language, _TWO, _noun("cup"))[2][1] == "classifier-general"
    with_cup = _find(
        lambda g: g.uses_classifiers and not g.classifier_after_noun and "container" in g.classifier_categories
        and g.classifier_assignment == "category" and g.repeater_rate == 0.0
    )
    assert _render(with_cup, _TWO, _noun("cup"))[2][1] == "classifier-container"


def test_a_noun_numeral_classifier_language_puts_the_numeral_and_classifier_after_the_noun():
    language = _find(
        lambda g: g.uses_classifiers and g.classifier_after_noun and "animal" in g.classifier_categories
        and g.classifier_assignment == "category" and g.repeater_rate == 0.0
    )
    _, tokens, glosses = _render(language, _TWO, _noun("dog"))
    assert glosses[0] == "dog" and glosses[2] == "classifier-animal" and len(tokens) == 3
    adjective = PlannedSlot(kind="content", gloss="high", pos="adjective")
    _, _, glosses = _render(language, _TWO, adjective, _noun("dog"))
    assert glosses[0] == "high" and glosses[1] == "dog" and glosses[3] == "classifier-animal"  # numeral, classifier follow the noun


def test_a_demonstrative_without_a_classifier_where_the_language_lacks_the_habit():
    language = _find(lambda g: g.uses_classifiers and not g.classifier_with_demonstrative)
    demonstrative = PlannedSlot(kind="demonstrative", gloss="this")
    assert len(_render(language, demonstrative, _noun("dog"))[1]) == 2
    assert len(_render(language, _TWO, _noun("dog"))[1]) == 3
