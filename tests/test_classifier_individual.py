"""Classifiers with quantifiers ("many", "several"...) and classifiers assigned
per individual noun: a lexical pool and repeaters (a noun as its own
classifier)."""

from conlang_generator.core.grammar import GrammarProfile
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import classifier_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient, _fake_plan_dict
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import _render_plan, translate_to_english

_CLIENT = FakeLLMClient()
_CACHE: dict[int, object] = {}


def _language(seed: int):
    if seed not in _CACHE:
        _CACHE[seed] = generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())
    return _CACHE[seed]


def _find(predicate, limit: int = 500):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language.grammar):
            return language
    raise AssertionError("no seed found")


def _render(language, *slots):
    updated, romanized, _, glosses = _render_plan(SentencePlan(slots=tuple(slots)), language, _CLIENT, [])
    return updated, romanized, glosses


def _noun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="noun", **kw)


def _quantifier(gloss: str) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="quantifier")


_TWO = PlannedSlot(kind="content", gloss="two", pos="numeral")


def _with(language, **grammar_updates):
    return language.model_copy(update={"grammar": language.grammar.model_copy(update=grammar_updates)})


def _plain_classifier_language():
    """A classifier language of the plain kind, before the noun, category-assigned, with no repeaters."""
    return _find(
        lambda g: g.uses_classifiers
        and not g.classifier_after_noun
        and g.classifier_assignment == "category"
        and g.repeater_rate == 0.0
        and {"animal", "long"} <= set(g.classifier_categories)
    )


# --- generation -----------------------------------------------------------


def test_the_new_choices_are_rolled_for_classifier_languages_only():
    grammars = [_language(s).grammar for s in range(1, 200)]
    classifier = [g for g in grammars if g.uses_classifiers]
    assert {g.classifier_assignment for g in classifier} == {"category", "lexical"}
    assert any(g.repeater_rate > 0 for g in classifier) and any(g.repeater_rate == 0 for g in classifier)
    assert any(g.classified_quantifiers for g in classifier)
    assert len({g.classified_quantifiers for g in classifier}) > 3
    for g in classifier:
        assert set(g.classified_quantifiers) <= set(classifier_gen.QUANTIFIERS)
        assert (g.classifier_pool_size > 0) == (g.classifier_assignment == "lexical")
        assert 0.0 <= g.repeater_rate <= 0.5
        if g.classifier_assignment == "lexical":
            assert 12 <= g.classifier_pool_size <= 40
    for g in grammars:
        if not g.uses_classifiers:
            assert g.classifier_assignment == "category" and g.repeater_rate == 0.0 and not g.classified_quantifiers


def test_grammar_defaults_keep_old_saved_languages_valid():
    fields = GrammarProfile.model_fields
    assert fields["classifier_assignment"].default == "category"
    assert fields["classifier_pool_size"].default == 0
    assert fields["repeater_rate"].default == 0.0
    assert fields["classified_quantifiers"].default == ()


def test_lexical_assignment_and_repeaters_are_stable_per_noun():
    assert classifier_gen.lexical_index(5, "dog", 20) == classifier_gen.lexical_index(5, " Dog ", 20)
    assert all(0 <= classifier_gen.lexical_index(5, w, 20) < 20 for w in ("dog", "river", "stone", "salt"))
    assert len({classifier_gen.lexical_index(5, w, 20) for w in ("dog", "river", "stone", "salt", "road", "leaf", "boat")}) > 2
    assert classifier_gen.lexical_gloss(3) == "classifier-lex03"
    assert classifier_gen.lexical_gloss(3, possessive=True) == "possessive-classifier-lex03"
    nouns = [f"noun{i}" for i in range(400)]
    share = sum(classifier_gen.is_repeater(1, n, 0.25) for n in nouns) / len(nouns)
    assert 0.15 < share < 0.35
    assert not any(classifier_gen.is_repeater(1, n, 0.0) for n in nouns)
    assert all(classifier_gen.is_repeater(1, n, 1.0) for n in nouns[:20])
    assert classifier_gen.is_repeater(1, "dog", 0.25) == classifier_gen.is_repeater(1, "DOG", 0.25)


# --- planning -------------------------------------------------------------


def test_parse_accepts_the_quantifier_pos():
    plan = sentence_planner._parse('[{"kind": "content", "gloss": "many", "pos": "quantifier"}]')
    assert plan is not None and plan.slots[0].pos == "quantifier"


def test_the_prompt_lists_the_quantifiers_that_take_a_classifier():
    language = _find(lambda g: g.uses_classifiers and "several" in g.classified_quantifiers)
    prompt = sentence_planner._build_system_prompt(language)
    assert 'pos "quantifier"' in prompt and "several" in prompt.split("also take a classifier")[1][:200]
    assert "no classifiers" in sentence_planner._build_system_prompt(_find(lambda g: not g.uses_classifiers))


_BASE = {"word_order": "SVO", "alignment": "nominative_accusative", "tenses": "past,non_past"}


def _slots(sentence: str) -> list[dict]:
    return _fake_plan_dict(sentence, _BASE)["slots"]


def test_the_fake_planner_plans_a_quantifier_and_its_noun_number():
    many = _slots("I see many dogs.")
    assert {"kind": "content", "gloss": "many", "pos": "quantifier"} in many
    assert next(s for s in many if s.get("gloss") == "dog")["number"] == "plural"
    every = _slots("I see every dog.")
    assert {"kind": "content", "gloss": "every", "pos": "quantifier"} in every
    assert "number" not in next(s for s in every if s.get("gloss") == "dog")


# --- quantifiers, rendered -------------------------------------------------


def test_a_classified_quantifier_takes_a_classifier_like_a_numeral():
    language = _plain_classifier_language()
    classified = _with(language, classified_quantifiers=("many",))
    _, tokens, glosses = _render(classified, _quantifier("many"), _noun("dog"))
    assert glosses[1] == "classifier-animal" and len(tokens) == 3


def test_a_quantifier_the_language_does_not_classify_takes_none():
    language = _with(_plain_classifier_language(), classified_quantifiers=("many",))
    assert len(_render(language, _quantifier("few"), _noun("dog"))[1]) == 2
    assert len(_render(language, _quantifier("every"), _noun("dog"))[1]) == 2


def test_how_many_matches_the_hyphenated_name():
    language = _with(_plain_classifier_language(), classified_quantifiers=("how-many",))
    assert len(_render(language, _quantifier("how many"), _noun("dog"))[1]) == 3


def test_a_classified_quantifier_keeps_the_noun_singular_and_follows_the_after_noun_order():
    base = _plain_classifier_language()
    classified = _with(base, classified_quantifiers=("many",))
    plural = _noun("dog", number="plural")
    assert _render(classified, _quantifier("many"), plural)[1][2] == _render(classified, _quantifier("many"), _noun("dog"))[1][2]
    after = _with(base, classified_quantifiers=("many",), classifier_after_noun=True)
    _, _, glosses = _render(after, _quantifier("many"), _noun("dog"))
    assert glosses[0] == "dog" and glosses[1] == "many" and glosses[2] == "classifier-animal"


def test_a_language_without_classifiers_leaves_quantifiers_alone():
    language = _find(lambda g: not g.uses_classifiers)
    assert len(_render(language, _quantifier("many"), _noun("dog"))[1]) == 2


def test_the_quantifier_classifier_is_dropped_on_the_way_back_to_english():
    language = _with(_plain_classifier_language(), classified_quantifiers=("many",))
    updated, tokens, _ = _render(language, _quantifier("many"), _noun("dog"))
    english = translate_to_english(" ".join(tokens), updated, _CLIENT).text
    assert "classifier" not in english and "many" in english and "dog" in english


# --- lexical pools ---------------------------------------------------------


def test_a_lexical_language_assigns_each_noun_a_pool_classifier():
    base = _plain_classifier_language()
    language = _with(base, classifier_assignment="lexical", classifier_pool_size=20)
    _, tokens, glosses = _render(language, _TWO, _noun("dog"))
    assert glosses[1] == classifier_gen.lexical_gloss(classifier_gen.lexical_index(language.spec.seed, "dog", 20))
    assert glosses[1].startswith("classifier-lex")
    seen = {
        _render(language, _TWO, _noun(w))[2][1]
        for w in ("dog", "river", "stone", "salt", "road", "leaf", "boat", "house", "king", "tree")
    }
    assert len(seen) > 3  # not one shared classifier: arbitrary, per noun
    _, again, again_glosses = _render(language, _TWO, _noun("dog"))
    assert again_glosses == glosses and again == tokens


def test_a_lexical_possessive_classifier_uses_the_pool_too():
    base = _find(
        lambda g: g.possessive_classifiers and g.uses_classifiers and not g.classifier_after_noun
        and g.possessive_pronouns == "regular" and not g.noun_classes and g.repeater_rate == 0.0
        and g.possession in ("genitive", "particle", "none")
    )
    language = _with(base, classifier_assignment="lexical", classifier_pool_size=20)
    possessor = PlannedSlot(kind="content", gloss="I", pos="pronoun", possessive=True)
    _, _, glosses = _render(language, possessor, _noun("dog"))
    assert any(g and g.startswith("possessive-classifier-lex") for g in glosses)


# --- repeaters ---------------------------------------------------------------


def test_a_repeater_noun_is_its_own_classifier():
    language = _with(_plain_classifier_language(), repeater_rate=1.0)
    _, tokens, glosses = _render(language, _TWO, _noun("dog"))
    assert glosses == ["two", "dog", "dog"] and tokens[1] == tokens[2]


def test_a_repeater_follows_the_after_noun_order():
    language = _with(_plain_classifier_language(), repeater_rate=1.0, classifier_after_noun=True)
    _, _, glosses = _render(language, _TWO, _noun("dog"))
    assert glosses == ["dog", "two", "dog"]


def test_only_the_repeater_nouns_repeat():
    base = _plain_classifier_language()
    language = _with(base, repeater_rate=0.5)
    nouns = ["dog", "river", "stone", "salt", "road", "leaf", "boat", "house", "king", "tree", "bird", "fish"]
    repeated = [n for n in nouns if _render(language, _TWO, _noun(n))[2][1] == n]
    assert 0 < len(repeated) < len(nouns)
    assert set(repeated) == {n for n in nouns if classifier_gen.is_repeater(language.spec.seed, n, 0.5)}


def test_a_repeated_noun_is_read_back_once():
    language = _with(_plain_classifier_language(), repeater_rate=1.0)
    updated, tokens, _ = _render(language, _TWO, _noun("dog"))
    english = translate_to_english(" ".join(tokens), updated, _CLIENT).text.split()
    assert english.count("dog") == 1 and "two" in english
    after = _with(language, classifier_after_noun=True)
    updated, tokens, _ = _render(after, _TWO, _noun("dog"))
    english = translate_to_english(" ".join(tokens), updated, _CLIENT).text.split()
    assert english.count("dog") == 1


def test_a_possessive_classifier_is_never_a_repeater():
    base = _find(
        lambda g: g.possessive_classifiers and g.uses_classifiers and not g.classifier_after_noun
        and g.possessive_pronouns == "regular" and g.classifier_assignment == "category"
        and g.possession in ("genitive", "particle", "none")
    )
    language = _with(base, repeater_rate=1.0)
    possessor = PlannedSlot(kind="content", gloss="I", pos="pronoun", possessive=True)
    _, _, glosses = _render(language, possessor, _noun("dog"))
    assert glosses.count("dog") == 1
