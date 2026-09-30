"""Voice follow-ups, second round: an impersonal verb plans (and renders)
with no subject at all, not just no subject agreement; an applicative verb's
promoted beneficiary now triggers the verb's own object agreement, a real
valency-changing effect, not just a bare suffix; and the fake planner's
closed middle/antipassive verb lists are a bit wider."""

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import (
    _decode_verb_full,
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


def _render(language, *slots, mood: str = "declarative"):
    updated, romanized, _, glosses = _render_plan(SentencePlan(slots=tuple(slots), mood=mood), language, _CLIENT, [])
    return updated, romanized, glosses


def _verb(gloss: str = "see", **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="verb", agreement=kw.pop("agreement", "I"), **kw)


def _pronoun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="pronoun", **kw)


# --- impersonal: no subject at all, not just no subject agreement ----------


def _impersonal_language():
    return _find(lambda g: "impersonal" in g.voices)


def test_impersonal_drops_an_adjacent_planned_subject():
    language = _impersonal_language()
    verb = _verb("dance", voice="impersonal", agreement="default")
    with_subject = _render(language, _pronoun("he"), verb)[1]
    without_subject = _render(language, verb)[1]
    assert with_subject == without_subject  # the "he" slot never reaches the output
    verb_after = _verb("dance", voice="impersonal", agreement="default")
    also_dropped = _render(language, verb_after, _pronoun("he"))[1]
    assert also_dropped == without_subject  # drops it on either side of the verb


def test_a_non_impersonal_verb_keeps_its_subject():
    language = _impersonal_language()
    with_subject = _render(language, _pronoun("he"), _verb("dance"))[1]
    without_subject = _render(language, _verb("dance"))[1]
    assert with_subject != without_subject
    assert len(with_subject) == len(without_subject) + 1


def test_the_fake_planner_plans_an_impersonal_with_no_subject_slot():
    language = _impersonal_language()
    plan = sentence_planner.plan_sentence("Someone dances.", language, _CLIENT)
    assert len(plan.slots) == 1
    slot = plan.slots[0]
    assert slot.kind == "content" and slot.pos == "verb" and slot.voice == "impersonal"


def test_an_impersonal_sentence_round_trips():
    language = _impersonal_language()
    result = translate_to_conlang("Someone dances.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "dance" in english


# --- applicative: promotion triggers real object agreement -----------------


def _applicative_language(object_agreement: bool):
    return _find(lambda g: "applicative" in g.voices and g.object_agreement == object_agreement)


def test_applicative_promotion_sets_object_agreement_from_free_text():
    language = _applicative_language(True)
    plan = sentence_planner.plan_sentence("I cook for him.", language, _CLIENT)
    verb = next(s for s in plan.slots if s.pos == "verb")
    assert verb.voice == "applicative" and verb.object_gloss == "he"


def test_no_object_agreement_language_sets_no_object_gloss_for_applicative():
    language = _applicative_language(False)
    plan = sentence_planner.plan_sentence("I cook for him.", language, _CLIENT)
    verb = next(s for s in plan.slots if s.pos == "verb")
    assert verb.voice == "applicative" and verb.object_gloss is None


def test_an_applicative_verb_with_object_agreement_round_trips():
    language = _applicative_language(True)
    result = translate_to_conlang("I cook for him.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "cook" in english and ("him" in english or "he" in english)


def test_decoding_finds_a_voice_and_object_agreement_combination_together():
    language = _find(lambda g: "applicative" in g.voices and g.object_agreement)
    token = _render(language, _verb(voice="applicative", object_gloss="he"))[1][0]
    decoded = _decode_verb_full(language, token)
    assert decoded is not None
    assert decoded[4] == "applicative" and decoded[6] == "he"


def test_reflexive_and_reciprocal_still_never_carry_object_agreement():
    # These voices already cover the missing object themselves (subject ==
    # object) -- guards against the new voice+object decode stage causing a
    # false-positive match against an entry that never set object_gloss.
    language = _find(lambda g: "reflexive" in g.voices and g.object_agreement)
    token = _render(language, _verb(voice="reflexive"))[1][0]
    decoded = _decode_verb_full(language, token)
    assert decoded is not None and decoded[4] == "reflexive" and decoded[6] is None


# --- the fake planner's wider middle/antipassive verb lists -----------------


def test_a_newly_added_middle_verb_still_marks_the_voice():
    language = _find(lambda g: "middle" in g.voices)
    plan = sentence_planner.plan_sentence("The water boiled.", language, _CLIENT)
    verb = next((s for s in plan.slots if s.pos == "verb"), None)
    assert verb is not None and verb.voice == "middle"


def test_a_newly_added_antipassive_verb_still_marks_the_voice():
    language = _find(lambda g: "antipassive" in g.voices)
    plan = sentence_planner.plan_sentence("The woman baked.", language, _CLIENT)
    verb = next((s for s in plan.slots if s.pos == "verb"), None)
    assert verb is not None and verb.voice == "antipassive"
