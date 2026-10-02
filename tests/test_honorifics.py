"""Politeness/honorific registers, second round (grammar pass 34, a
Discourse follow-up): a subject-referent honorific ("the professor sleeps")
marks deference toward the sentence's own subject, independent of the
addressee-only ``honorific_you``/``verb_politeness`` already in place --
reusing the very same "polite" verb affix rather than inventing a second
one. Scope: a closed title list only (no proper-name trigger, no
object/addressee-humbling marking), subject-position only."""

from conlang_generator.core.grammar import GrammarProfile
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import pronoun_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient, _fake_plan_dict
from tests._shared_language import cached_language
from conlang_generator.translation import sentence_planner

_CLIENT = FakeLLMClient()

_language = cached_language


def _find(predicate, limit: int = 300):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language.grammar):
            return language
    raise AssertionError("no seed found")


def _metadata(language):
    grammar = language.grammar
    return {
        "has_articles": "true" if grammar.has_articles else "false",
        "verb_politeness": "true" if grammar.verb_politeness else "false",
        "referent_honorifics": "true" if grammar.referent_honorifics else "false",
        "tenses": ",".join(grammar.tenses),
    }


def _verb_slot(prompt: str, language):
    plan = _fake_plan_dict(prompt, _metadata(language))
    return next(s for s in plan["slots"] if s.get("pos") == "verb")


# --- generation --------------------------------------------------------------


def test_referent_honorifics_rolls_both_true_and_false():
    grammars = [_language(s).grammar for s in range(1, 60)]
    assert any(g.referent_honorifics for g in grammars)
    assert any(not g.referent_honorifics for g in grammars)


def test_the_new_grammar_field_defaults_for_older_saved_languages():
    assert GrammarProfile.model_fields["referent_honorifics"].default is False


def test_verb_politeness_can_be_true_without_honorific_you():
    language = _find(lambda g: g.referent_honorifics and g.verb_politeness and not g.honorific_you)
    assert language.grammar.verb_polite_affixes


# --- fake-planner trigger -----------------------------------------------------


def test_a_title_subject_triggers_the_referent_honorific():
    language = _find(lambda g: g.referent_honorifics and g.verb_politeness)
    assert _verb_slot("The professor sleeps.", language).get("polite") is True


def test_an_ordinary_noun_subject_does_not_trigger_it():
    language = _find(lambda g: g.referent_honorifics and g.verb_politeness)
    assert _verb_slot("The dog sleeps.", language).get("polite") is not True


def test_plain_i_and_you_subjects_do_not_trigger_it():
    language = _find(lambda g: g.referent_honorifics and g.verb_politeness)
    assert _verb_slot("I sleep.", language).get("polite") is not True
    assert _verb_slot("You sleep.", language).get("polite") is not True


def test_the_title_trigger_needs_referent_honorifics_switched_on():
    # verb_politeness alone (addressee-only, no referent_honorifics) must
    # not let a title subject trigger the affix.
    language = _find(lambda g: g.verb_politeness and not g.referent_honorifics)
    assert _verb_slot("The professor sleeps.", language).get("polite") is not True


# --- regression guard: the pre-existing addressee path is unaffected ---------


def test_addressee_politeness_cue_is_unaffected():
    rich = _find(lambda g: g.honorific_you)
    plain = _find(lambda g: not g.honorific_you)
    assert pronoun_gen.english_pronoun_gloss(rich.grammar, "you", ["sir"]) == "you-polite"
    assert pronoun_gen.english_pronoun_gloss(plain.grammar, "you", ["sir"]) == "you"


def test_topic_is_still_a_valid_clause_role():
    # Sanity: pass 33's own clause role wasn't disturbed by this pass's edits.
    assert "topic" in sentence_planner.CLAUSE_ROLES
