"""Voice and noun-phrase follow-ups: middle/applicative/impersonal voices, passive
agent and agreement, trial and collective number, locative/instrumental case,
adposition placement and case government, suppletive plurals and comparatives,
and inalienable possession."""

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import voice_np_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import (
    _arrange_adpositions,
    _decode_noun,
    _decode_verb_full,
    _english_verb_phrase,
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


def _find(predicate, check=None, limit: int = 300):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language.grammar) and (check is None or check(language)):
            return language
    raise AssertionError("no seed found")


def _with(language, **updates):
    return language.model_copy(update={"grammar": language.grammar.model_copy(update=updates)})


def _render(language, *slots, mood: str = "declarative"):
    updated, romanized, _, glosses = _render_plan(SentencePlan(slots=tuple(slots), mood=mood), language, _CLIENT, [])
    return updated, romanized, glosses


def _noun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="noun", **kw)


def _verb(**kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss="see", pos="verb", agreement="I", **kw)


def _preposition(gloss: str) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="preposition")


def _plain(language):
    """Without the earlier follow-up features that would spell things another way."""
    return _with(
        language, periphrastic_labels=(), negation_strategy="particle", verb_negative_affixes=(), evidentials=(),
        evidential_affixes=(),
    )


# --- generation -----------------------------------------------------------------


def test_the_follow_up_choices_are_rolled():
    grammars = [_language(s).grammar for s in range(1, 120)]
    assert {v for g in grammars for v in g.voices} >= {"middle", "applicative", "impersonal"}
    assert {a.label for g in grammars for a in g.number_affixes} >= {"trial", "collective"}
    assert {c for g in grammars for c in g.cases} >= {"locative", "instrumental"}
    assert {g.adposition_case_strategy for g in grammars} == {"none", "governs", "case_only"}
    assert {g.passive_agreement for g in grammars} == {"patient", "none"}
    assert {g.passive_agent for g in grammars} == {"word", "case"}
    assert any(g.suppletive_plurals for g in grammars) and any(g.suppletive_degrees for g in grammars)
    assert any(g.inalienable_possession for g in grammars)
    for g in grammars:
        assert [a.label for a in g.voice_affixes] == list(g.voices)
        assert set(g.suppletive_plurals) <= set(voice_np_gen.IRREGULAR_PLURALS)
        assert set(g.suppletive_degrees) <= set(voice_np_gen.SUPPLETIVE_DEGREES)
        assert {a.label for a in g.case_affixes} == set(g.cases)


def test_extra_cases_only_join_a_language_that_already_marks_case():
    for seed in range(1, 120):
        g = _language(seed).grammar
        if not g.cases:
            assert not g.case_affixes and g.adposition_case_strategy in ("none", "governs", "case_only")


def test_the_new_grammar_fields_default_for_older_saved_languages():
    fields = type(_language(1).grammar).model_fields
    assert fields["passive_agreement"].default == "patient" and fields["passive_agent"].default == "word"
    assert fields["adposition_case_strategy"].default == "none" and fields["inalienable_possession"].default is False
    assert fields["suppletive_plurals"].default == () and fields["suppletive_degrees"].default == ()


def test_the_helpers_read_glosses():
    assert voice_np_gen.is_inalienable("hand") and voice_np_gen.is_inalienable("mother")
    assert not voice_np_gen.is_inalienable("dog")
    assert voice_np_gen.suppletive_split("child-plural") == ("child", "plural")
    assert voice_np_gen.suppletive_split("dog") is None
    assert voice_np_gen.suppletive_reading("child", "plural") == "children"
    assert voice_np_gen.suppletive_reading("good", "comparative") == "better"
    assert voice_np_gen.suppletive_reading("good", "superlative") == "best"


# --- voices ---------------------------------------------------------------------------


def _voice_language(voice: str):
    def check(language) -> bool:
        language = _plain(language)
        _, parts, _ = _render(language, _verb(voice=voice))
        decoded = _decode_verb_full(language, parts[0])
        return decoded is not None and decoded[4] == voice

    return _plain(_find(lambda g: voice in g.voices and not g.object_agreement and not g.pro_drop, check))


def test_the_new_voices_mark_the_verb_and_decode_back():
    for voice in ("middle", "applicative", "impersonal"):
        language = _voice_language(voice)
        active = _render(language, _verb())[1][0]
        marked = _render(language, _verb(voice=voice))[1][0]
        assert marked != active


def test_the_new_voices_read_back_in_english():
    language = _find(lambda g: True)
    see = language.lexicon.by_gloss("see")
    assert _english_verb_phrase(see, None, None, None, "middle") == "gets seen"
    assert _english_verb_phrase(see, "past", None, None, "middle") == "got seen"
    assert _english_verb_phrase(see, None, None, None, "applicative") == "see for"
    assert _english_verb_phrase(see, None, None, None, "impersonal") == "one sees"


def test_an_impersonal_verb_takes_no_subject_agreement():
    language = _voice_language("impersonal")
    assert _render(language, _verb(voice="impersonal"))[1] == _render(
        language, PlannedSlot(kind="content", gloss="see", pos="verb", agreement="you", voice="impersonal")
    )[1]


def test_a_passive_agrees_only_where_the_language_says_so():
    def clean(language) -> bool:
        return language.grammar.passive_agreement == "none" and "passive" in language.grammar.voices

    none = _plain(_find(lambda g: g.passive_agreement == "none" and "passive" in g.voices and not g.object_agreement))
    i_form = _render(none, _verb(voice="passive"))[1]
    you_form = _render(none, PlannedSlot(kind="content", gloss="see", pos="verb", agreement="you", voice="passive"))[1]
    assert i_form == you_form
    patient = _plain(_find(lambda g: g.passive_agreement == "patient" and "passive" in g.voices and not g.object_agreement))
    a = _render(patient, _verb(voice="passive"))[1]
    b = _render(patient, PlannedSlot(kind="content", gloss="see", pos="verb", agreement="you", voice="passive"))[1]
    assert a != b


# --- trial and collective ------------------------------------------------------------


def _number_language(label: str):
    def check(language) -> bool:
        _, parts, _ = _render(language, _noun("dog", number=label))
        decoded = _decode_noun(language, parts[0])
        return decoded is not None and decoded[1].endswith(label)

    return _find(lambda g: label in [a.label for a in g.number_affixes] and not g.uses_classifiers, check)


def test_trial_and_collective_are_their_own_marked_forms():
    for label in ("trial", "collective"):
        language = _number_language(label)
        plural = _render(language, _noun("dog", number="plural"))[1][0]
        marked = _render(language, _noun("dog", number=label))[1][0]
        assert marked != plural != _render(language, _noun("dog"))[1][0]


def test_trial_and_collective_read_back_in_english():
    for label, expected in (("trial", "three"), ("collective", "group of")):
        language = _number_language(label)
        token = _render(language, _noun("dog", number=label))[1][0]
        assert expected in translate_to_english(token, language, _CLIENT).text


def test_the_fake_planner_marks_a_trial_and_a_collective():
    trial = _find(lambda g: "trial" in [a.label for a in g.number_affixes])
    plan = sentence_planner.plan_sentence("I see three dogs.", trial, _CLIENT)
    assert any(slot.number == "trial" for slot in plan.slots)
    collective = _find(lambda g: "collective" in [a.label for a in g.number_affixes])
    plan = sentence_planner.plan_sentence("I see all dogs.", collective, _CLIENT)
    assert any(slot.number == "collective" for slot in plan.slots)


# --- adpositions and case -------------------------------------------------------------


def _case_language(strategy: str, case: str, postpositional: bool):
    return _plain(
        _find(
            lambda g: g.adposition_case_strategy == strategy and case in g.cases
            and g.postpositional == postpositional and not g.uses_classifiers and not g.noun_classes
            and g.class_marking == "none"
        )
    )


def _in_the_house(language, before: bool):
    house = _noun("house")
    adposition = _preposition("in")
    return [adposition, house] if before else [house, adposition]


def test_a_locative_case_replaces_its_adposition():
    for postpositional in (False, True):
        language = _case_language("case_only", "locative", postpositional)
        bare_house = _render(language, _noun("house"))[1][0]
        parts = _render(language, *_in_the_house(language, not postpositional))[1]
        assert len(parts) == 1 and parts[0] != bare_house
        assert parts == _render(language, _noun("house", case="locative"))[1]


def test_a_governing_adposition_stays_and_its_noun_takes_the_case():
    language = _case_language("governs", "locative", False)
    parts = _render(language, *_in_the_house(language, True))[1]
    assert len(parts) == 2
    in_word = language.lexicon.by_gloss("in")
    assert parts[0] == in_word.romanization or parts[1] == in_word.romanization
    assert _render(language, _noun("house", case="locative"))[1][0] in parts


def test_without_a_strategy_the_adposition_and_noun_are_left_alone():
    language = _plain(_find(lambda g: g.adposition_case_strategy == "none" and not g.uses_classifiers))
    parts = _render(language, *_in_the_house(language, not language.grammar.postpositional))[1]
    assert len(parts) == 2 and _render(language, _noun("house"))[1][0] in parts


def test_an_adposition_is_moved_to_the_languages_own_side():
    for postpositional in (False, True):
        language = _plain(
            _find(lambda g: g.adposition_case_strategy == "none" and g.postpositional == postpositional)
        )
        wrong = _arrange_adpositions(language, tuple(_in_the_house(language, before=postpositional)))
        assert [s.gloss for s in wrong] == (["house", "in"] if postpositional else ["in", "house"])


def test_an_adposition_takes_its_whole_noun_phrase_with_it():
    language = _plain(_find(lambda g: g.adposition_case_strategy == "none" and g.postpositional and not g.adjective_after_noun))
    adjective = PlannedSlot(kind="content", gloss="big", pos="adjective")
    arranged = _arrange_adpositions(language, (_preposition("in"), adjective, _noun("house")))
    assert [s.gloss for s in arranged] == ["big", "house", "in"]


def test_the_passive_agent_can_be_an_instrumental_case():
    language = _plain(
        _find(
            lambda g: g.passive_agent == "case" and "instrumental" in g.cases and "passive" in g.voices
            and not g.uses_classifiers and not g.noun_classes and g.class_marking == "none"
        )
    )
    by = _preposition("by")
    dog = _noun("dog")
    agent = [dog, by] if language.grammar.postpositional else [by, dog]
    parts = _render(language, *agent)[1]
    assert len(parts) == 1 and parts == _render(language, _noun("dog", case="instrumental"))[1]


def test_case_marked_nouns_read_back_with_their_adposition():
    language = _case_language("case_only", "locative", False)
    updated, parts, _ = _render(language, _noun("house", case="locative"))
    assert "in" in translate_to_english(parts[0], updated, _CLIENT).text.split()


# --- suppletive plurals and degrees -----------------------------------------------------


def _suppletive_plural_language():
    def check(language) -> bool:
        updated, parts, _ = _render(_plain(language), _noun("child", number="plural"))
        return _decode_noun(updated, parts[0]) is not None

    return _plain(_find(lambda g: "child" in g.suppletive_plurals and not g.uses_classifiers, check))


def test_an_irregular_plural_is_a_separate_word_that_reads_back():
    language = _suppletive_plural_language()
    updated, parts, glosses = _render(language, _noun("child", number="plural"))
    assert "child-plural" in [e.primary_gloss for e in updated.lexicon.entries]
    assert parts[0] != _render(language, _noun("child"))[1][0]
    assert "children" in translate_to_english(parts[0], updated, _CLIENT).text


def test_a_regular_noun_still_takes_the_plural_suffix():
    language = _suppletive_plural_language()
    dog_plural = _render(language, _noun("dog", number="plural"))[1][0]
    assert dog_plural != _render(language, _noun("dog"))[1][0]
    assert "child-plural" not in _render(language, _noun("dog", number="plural"))[2]


def test_a_suppletive_comparative_is_a_separate_word():
    language = _plain(_find(lambda g: "good" in g.suppletive_degrees and g.degree_affixes and not g.noun_classes))
    adjective = PlannedSlot(kind="content", gloss="good", pos="adjective", degree="comparative")
    updated, parts, _ = _render(language, adjective)
    assert "good-comparative" in [e.primary_gloss for e in updated.lexicon.entries]
    assert "better" in translate_to_english(parts[0], updated, _CLIENT).text
    regular = PlannedSlot(kind="content", gloss="big", pos="adjective", degree="comparative")
    _, big_parts, _ = _render(language, regular)
    assert big_parts[0] != language.lexicon.by_gloss("big").romanization


# --- inalienable possession -------------------------------------------------------------


def test_an_inalienable_noun_takes_no_possessive_marking():
    language = _plain(
        _find(lambda g: g.inalienable_possession and g.possession == "particle" and g.possessive_pronouns == "regular")
    )
    owner = PlannedSlot(kind="content", gloss="he", pos="pronoun", possessive=True)
    dog = _render(language, owner, _noun("dog"))[1]
    hand = _render(language, owner, _noun("hand"))[1]
    assert len(dog) == len(hand) + 1  # the possessive particle is missing


def test_an_alienable_language_marks_every_possessed_noun():
    language = _plain(_find(lambda g: not g.inalienable_possession and g.possession == "particle"))
    owner = PlannedSlot(kind="content", gloss="he", pos="pronoun", possessive=True)
    assert len(_render(language, owner, _noun("dog"))[1]) == len(_render(language, owner, _noun("hand"))[1])


# --- planner ---------------------------------------------------------------------------


def test_the_fake_planner_marks_the_new_voices():
    for voice, sentence in (("antipassive", "The man eats."), ("middle", "The door opens."), ("applicative", "I cook for him.")):
        language = _find(lambda g: voice in g.voices)
        plan = sentence_planner.plan_sentence(sentence, language, _CLIENT)
        assert any(slot.voice == voice for slot in plan.slots), voice


def test_the_planner_prompt_describes_the_new_constructions():
    language = _find(lambda g: "middle" in g.voices)
    prompt = sentence_planner._build_system_prompt(language)
    assert '"middle"' in prompt and '"applicative"' in prompt and '"impersonal"' in prompt
    assert '"trial"' in prompt and "turns them into case endings" in prompt
