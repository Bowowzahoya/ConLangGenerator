"""Noun-phrase follow-ups, third round: more spatial cases, measure phrases,
adjectives across "and", classifiers beside adjectives and without a noun, partial
possessive words, irregular pasts, deictic and doubled articles, and the specific
article agreeing."""

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import np_followups_gen, voice_np_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import (
    _arrange_adjectives,
    _arrange_adpositions,
    _render_plan,
    translate_to_english,
)

_CLIENT = FakeLLMClient()
_CACHE: dict[int, object] = {}


def _language(seed: int):
    if seed not in _CACHE:
        _CACHE[seed] = generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())
    return _CACHE[seed]


def _find(predicate, check=None, limit: int = 300):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language.grammar) and (check is None or check(language)):
            return language
    raise AssertionError("no seed found")


def _with(language, **updates):
    return language.model_copy(update={"grammar": language.grammar.model_copy(update=updates)})


def _render(language, *slots):
    updated, romanized, _, glosses = _render_plan(SentencePlan(slots=tuple(slots)), language, _CLIENT, [])
    return updated, romanized, glosses


def _noun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="noun", **kw)


def _adjective(gloss: str) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="adjective")


def _preposition(gloss: str) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="preposition")


def _plain(language):
    return _with(
        language, periphrastic_labels=(), negation_strategy="particle", verb_negative_affixes=(), evidentials=(),
        evidential_affixes=(), number_agreement_targets=(), case_agreement_targets=(),
    )


def _plain_np_language():
    return _plain(_find(lambda g: not g.noun_classes and g.class_marking == "none" and not g.uses_classifiers))


# --- generation -----------------------------------------------------------------


def test_the_follow_up_choices_are_rolled():
    grammars = [_language(s).grammar for s in range(1, 120)]
    assert {c for g in grammars for c in g.cases} >= {"ablative", "allative", "comitative"}
    assert any(g.classifier_with_adjective for g in grammars) and any(g.drop_measure_of for g in grammars)
    assert any(g.possessive_word_persons for g in grammars) and any(g.suppletive_past for g in grammars)
    assert any(g.deictic_articles for g in grammars) and any(g.demonstrative_doubling for g in grammars)
    for g in grammars:
        assert {a.label for a in g.case_affixes} == set(g.cases)
        assert set(g.suppletive_past) <= set(voice_np_gen.IRREGULAR_PASTS)
        if g.suppletive_past:
            assert "past" in g.tenses
        if g.possessive_word_persons:
            assert g.possessive_pronouns == "words"
        if g.classifier_with_adjective:
            assert g.uses_classifiers


def test_the_new_grammar_fields_default_for_older_saved_languages():
    fields = type(_language(1).grammar).model_fields
    assert fields["classifier_with_adjective"].default is False and fields["drop_measure_of"].default is False
    assert fields["possessive_word_persons"].default == () and fields["suppletive_past"].default == ()
    assert fields["deictic_articles"].default is False and fields["demonstrative_doubling"].default is False


def test_a_derived_article_can_exist_in_a_tonal_language():
    for seed in range(1, 200):
        language = _language(seed)
        if language.grammar.article_source == "demonstrative" and language.tone_system.enabled:
            the = language.lexicon.by_gloss("the")
            assert the.romanization != language.lexicon.by_gloss("that").romanization
            assert len(the.tones) <= 1
            return
    raise AssertionError("no tonal language with a derived article")


# --- spatial cases -----------------------------------------------------------------------


def _spatial(case: str, strategy: str = "case_only", postpositional: bool = False):
    return _plain(
        _find(
            lambda g: case in g.cases and g.adposition_case_strategy == strategy
            and g.postpositional == postpositional and not g.uses_classifiers and not g.noun_classes
            and g.class_marking == "none"
        )
    )


def test_more_adpositions_map_to_their_cases():
    assert voice_np_gen.ADPOSITION_CASES["from"] == "ablative"
    assert voice_np_gen.ADPOSITION_CASES["under"] == "locative"
    assert voice_np_gen.ADPOSITION_CASES["into"] == "allative"


def test_an_ablative_replaces_from_and_reads_back():
    language = _spatial("ablative")
    updated, parts, _ = _render(language, _preposition("from"), _noun("house"))
    assert len(parts) == 1 and parts != _render(language, _noun("house"))[1]
    assert "from" in translate_to_english(parts[0], updated, _CLIENT).text.split()


def test_with_falls_back_to_a_comitative_when_there_is_no_instrumental():
    language = _spatial("comitative")
    forced = _with(language, cases=tuple(c for c in language.grammar.cases if c != "instrumental"))
    arranged = _arrange_adpositions(forced, (_preposition("with"), _noun("dog")))
    assert [s.gloss for s in arranged] == ["dog"] and arranged[0].case == "comitative"


def test_a_governing_language_keeps_the_new_adposition():
    language = _spatial("allative", "governs")
    arranged = _arrange_adpositions(language, (_preposition("into"), _noun("house")))
    assert [s.gloss for s in arranged] == ["into", "house"] and arranged[1].case == "allative"


# --- measure phrases ----------------------------------------------------------------------


def _measure(postpositional: bool, drop: bool):
    language = _plain(_find(lambda g: g.postpositional == postpositional))
    return _with(language, drop_measure_of=drop, adposition_case_strategy="none")


def test_of_is_dropped_between_a_measure_noun_and_a_mass_noun():
    for postpositional in (False, True):
        language = _measure(postpositional, True)
        slots = (
            (_noun("cup"), _preposition("of"), _noun("water"))
            if not postpositional
            else (_noun("cup"), _noun("water"), _preposition("of"))
        )
        assert [s.gloss for s in _arrange_adpositions(language, slots)] == ["cup", "water"]


def test_of_stays_after_an_ordinary_noun_or_when_the_language_keeps_it():
    language = _measure(False, True)
    kept = _arrange_adpositions(language, (_noun("dog"), _preposition("of"), _noun("water")))
    assert [s.gloss for s in kept] == ["dog", "of", "water"]
    language = _measure(False, False)
    kept = _arrange_adpositions(language, (_noun("cup"), _preposition("of"), _noun("water")))
    assert [s.gloss for s in kept] == ["cup", "of", "water"]


# --- adjectives across "and" ----------------------------------------------------------------


def test_the_planners_and_between_adjectives_is_re_decided():
    order = ("colour", "size", "quality", "age", "other")
    conj = PlannedSlot(kind="conjunction")
    slots = (_adjective("big"), conj, _adjective("red"), _noun("dog"))
    unlinked = _with(
        _plain_np_language(), adjective_placement="global", adjective_after_noun=False, adjective_stack_order=order,
        adjective_stack_linker=False,
    )
    assert [s.gloss or s.kind for s in _arrange_adjectives(unlinked, slots)] == ["red", "big", "dog"]
    linked = _with(unlinked, adjective_stack_linker=True)
    assert [s.gloss or s.kind for s in _arrange_adjectives(linked, slots)] == ["red", "conjunction", "big", "dog"]


# --- classifiers -----------------------------------------------------------------------------


def _classifier_language():
    return _plain(_find(lambda g: g.uses_classifiers and not g.noun_classes and g.repeater_rate == 0.0))


def _classifier_glosses(glosses):
    return [g for g in glosses if g and g.startswith("classifier-")]


def test_a_classifier_can_stand_beside_an_attributive_adjective():
    language = _with(_classifier_language(), classifier_with_adjective=True, adjective_after_noun=False, classified_quantifiers=())
    glosses = _render(language, _adjective("big"), _noun("dog"))[2]
    assert glosses[0] == "big" and glosses[1].startswith("classifier-") and glosses[2] == "dog"
    after = _with(language, adjective_after_noun=True)
    glosses = _render(after, _noun("dog"), _adjective("big"))[2]
    assert glosses[0] == "dog" and glosses[1].startswith("classifier-") and glosses[2] == "big"


def test_only_one_classifier_serves_a_noun_with_a_numeral_and_an_adjective():
    language = _with(_classifier_language(), classifier_with_adjective=True, adjective_after_noun=False)
    two = PlannedSlot(kind="content", gloss="two", pos="numeral")
    glosses = _render(language, two, _adjective("big"), _noun("dog"))[2]
    assert len(_classifier_glosses(glosses)) == 1


def test_without_the_feature_an_adjective_brings_no_classifier():
    language = _with(_classifier_language(), classifier_with_adjective=False)
    assert not _classifier_glosses(_render(language, _adjective("big"), _noun("dog"))[2])


def test_a_numeral_standing_alone_takes_the_classifier_of_its_noun():
    language = _classifier_language()
    two = PlannedSlot(kind="content", gloss="two", pos="numeral", classifier_for="dog")
    glosses = _render(language, two)[2]
    assert glosses[0] == "two" and _classifier_glosses(glosses)
    bare = _render(language, PlannedSlot(kind="content", gloss="two", pos="numeral"))[2]
    assert not _classifier_glosses(bare)


def test_the_planner_accepts_classifier_for():
    plan = sentence_planner._parse(
        '{"mood": "declarative", "slots": [{"kind": "content", "gloss": "two", "pos": "numeral", "classifier_for": "Dog"}]}'
    )
    assert plan is not None and plan.slots[0].classifier_for == "dog"


# --- possessive words -----------------------------------------------------------------------------


def test_only_some_persons_have_their_own_possessive_word():
    language = _plain(_find(lambda g: g.possessive_pronouns == "words" and not g.uses_classifiers))
    language = _with(language, possessive_word_persons=("I",), possession="particle")
    mine = _render(language, PlannedSlot(kind="possessive_pronoun", gloss="I"), _noun("dog"))[2]
    yours = _render(language, PlannedSlot(kind="possessive_pronoun", gloss="you"), _noun("dog"))[2]
    assert mine[0].startswith("poss") and yours[0] == "you"


# --- irregular pasts -----------------------------------------------------------------------------------


def _past_language():
    def usable(language) -> bool:
        language = _plain(language)
        return "past" in language.grammar.tenses and not language.grammar.object_agreement

    return _plain(_find(lambda g: "past" in g.tenses and not g.object_agreement, usable))


def test_an_irregular_past_is_a_word_of_its_own_and_reads_back():
    language = _with(_past_language(), suppletive_past=("go",))
    go = PlannedSlot(kind="content", gloss="go", pos="verb", agreement="I", tense="past")
    updated, parts, glosses = _render(language, go)
    assert glosses == ["go-past"]
    assert "went" in translate_to_english(parts[0], updated, _CLIENT).text
    present = PlannedSlot(kind="content", gloss="go", pos="verb", agreement="I", tense="present" if "present" in language.grammar.tenses else "non_past")
    assert _render(language, present)[2] == ["go"]


def test_a_regular_verb_keeps_its_tense_suffix_in_such_a_language():
    language = _with(_past_language(), suppletive_past=("go",))
    walk = PlannedSlot(kind="content", gloss="walk", pos="verb", agreement="I", tense="past")
    assert _render(language, walk)[2] == ["walk"]
    plain = _with(language, suppletive_past=())
    go = PlannedSlot(kind="content", gloss="go", pos="verb", agreement="I", tense="past")
    assert _render(plain, go)[2] == ["go"]


# --- deictic and doubled articles ----------------------------------------------------------------------


def _demonstrative_language():
    return _plain(_find(lambda g: g.has_articles and not g.noun_classes and not g.uses_classifiers and not g.number_agreement_targets))


def test_a_deictic_article_is_a_reduced_demonstrative_next_to_a_noun():
    language = _with(_demonstrative_language(), deictic_articles=True, demonstrative_after_noun=False)
    updated, parts, glosses = _render(language, PlannedSlot(kind="demonstrative", gloss="this"), _noun("dog"))
    full = language.lexicon.by_gloss("this")
    assert glosses[0] in ("this-article", "this")
    if glosses[0] == "this-article":
        assert parts[0] != full.romanization and len(parts[0]) <= len(full.romanization)
        assert "this" in translate_to_english(parts[0], updated, _CLIENT).text.split()


def test_a_standalone_demonstrative_keeps_its_full_form():
    language = _with(_demonstrative_language(), deictic_articles=True)
    assert _render(language, PlannedSlot(kind="demonstrative", gloss="this"))[2] == ["this"]


def test_demonstrative_doubling_adds_the_definite_article():
    language = _with(_demonstrative_language(), demonstrative_doubling=True, demonstrative_after_noun=False)
    glosses = _render(language, PlannedSlot(kind="demonstrative", gloss="this"), _noun("dog"))[2]
    assert glosses[0] == "the" and glosses[1] == "this"
    again = _render(language, PlannedSlot(kind="article"), PlannedSlot(kind="demonstrative", gloss="this"), _noun("dog"))[2]
    assert again.count("the") == 1
    single = _with(language, demonstrative_doubling=False)
    assert _render(single, PlannedSlot(kind="demonstrative", gloss="this"), _noun("dog"))[2] == ["this", "dog"]


def test_doubling_after_the_noun_puts_the_article_before_the_noun():
    language = _with(_demonstrative_language(), demonstrative_doubling=True, demonstrative_after_noun=True)
    glosses = _render(language, _noun("dog"), PlannedSlot(kind="demonstrative", gloss="this"))[2]
    assert glosses == ["the", "dog", "this"]


# --- the specific article agreeing ----------------------------------------------------------------------------


def test_the_specific_article_agrees_with_its_noun():
    language = _find(
        lambda g: g.noun_classes and "article" in g.class_agreement_targets and g.has_indefinite_article
        and not g.uses_classifiers and g.class_marking == "none"
    )
    language = _plain(_with(language, has_specific_article=True, class_agreement_targets=("article",)))
    specific = PlannedSlot(kind="specific_article")
    with_agreement = _render(language, specific, _noun("dog"))[1][0]
    without = _render(_with(language, class_agreement_targets=()), specific, _noun("dog"))[1][0]
    assert with_agreement != without


def test_the_planner_prompt_mentions_measure_phrases_and_standalone_numerals():
    prompt = sentence_planner._build_system_prompt(_language(1))
    assert '"classifier_for"' in prompt and "a cup of water" in prompt
    assert np_followups_gen.SPECIFIC_ARTICLE_GLOSS == "a-certain"
