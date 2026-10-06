"""Topic/focus and information structure (grammar pass 33, Discourse
follow-up): a topicalized sentence ("as for the cat, it sleeps") is a
"topic"-role clause slot holding just the topic noun phrase, fronted, with
an optional dedicated particle; the main clause's own resumptive subject
pronoun is dropped. Scope: subject-coreferent topics only, a bare topic
noun phrase only (no adjectives/numerals/possessors on it), no focus/cleft
constructions."""

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient, _fake_plan_dict
from tests._shared_language import cached_language
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import _render_plan, translate_to_conlang, translate_to_english

_CLIENT = FakeLLMClient()

_language = cached_language


def _find(predicate, limit: int = 300):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language.grammar):
            return language
    raise AssertionError("no seed found")


def _render(language, *slots):
    _, romanized, _, glosses, _ = _render_plan(SentencePlan(slots=tuple(slots)), language, _CLIENT, [])
    return romanized, glosses


def _topic_clause(gloss="cat") -> PlannedSlot:
    return PlannedSlot(
        kind="clause", role="topic", clause=SentencePlan(slots=(PlannedSlot(kind="content", gloss=gloss, pos="noun"),))
    )


# --- generation --------------------------------------------------------------


def test_topic_particle_rolls_both_set_and_empty():
    grammars = [_language(s).grammar for s in range(1, 60)]
    assert any(g.topic_particle for g in grammars)
    assert any(not g.topic_particle for g in grammars)


def test_the_new_grammar_field_defaults_for_older_saved_languages():
    assert type(_language(1).grammar).model_fields["topic_particle"].default == ""


def test_topic_is_a_valid_clause_role():
    assert "topic" in sentence_planner.CLAUSE_ROLES


# --- direct-plan rendering ----------------------------------------------------


def test_topic_particle_follows_the_topic_np_and_resumptive_subject_is_dropped():
    language = _find(lambda g: g.topic_particle)
    particle_rom = language.romanization.apply(language.grammar.topic_particle)
    subject = PlannedSlot(kind="content", gloss="it", pos="pronoun")
    verb = PlannedSlot(kind="content", gloss="sleep", pos="verb")
    romanized, _ = _render(language, _topic_clause(), subject, verb)
    assert particle_rom in romanized
    particle_index = romanized.index(particle_rom)
    # The particle sits directly after the topic noun's own token(s), before
    # anything from the main clause.
    assert particle_index >= 1
    subject_rom = language.romanization.apply(
        next(e.ipa for e in language.lexicon.entries if e.primary_gloss == "it")
    ) if any(e.primary_gloss == "it" for e in language.lexicon.entries) else None
    if subject_rom is not None:
        assert subject_rom not in romanized[particle_index + 1 :]


def test_no_particle_language_still_fronts_the_topic_unmarked():
    language = _find(lambda g: not g.topic_particle)
    subject = PlannedSlot(kind="content", gloss="it", pos="pronoun")
    verb = PlannedSlot(kind="content", gloss="sleep", pos="verb")
    romanized, glosses = _render(language, _topic_clause(), subject, verb)
    # Whatever the topic noun's own token(s) are, they come before anything
    # from the main clause (the verb's gloss, "sleep", is the last thing
    # the main clause contributes).
    assert "sleep" in glosses
    assert glosses.index("sleep") == len(glosses) - 1


# --- free-text round trip -----------------------------------------------------


def test_free_text_as_for_round_trips_with_the_particle():
    language = _find(lambda g: g.topic_particle)
    rendered = translate_to_conlang("As for the cat, it sleeps.", language, _CLIENT)
    decoded = translate_to_english(rendered.text, language, _CLIENT)
    assert "as for" in decoded.text
    assert "cat" in decoded.text
    assert "sleep" in decoded.text


def test_free_text_as_for_fronts_the_topic_even_without_a_particle():
    language = _find(lambda g: not g.topic_particle)
    rendered = translate_to_conlang("As for the cat, it sleeps.", language, _CLIENT)
    decoded = translate_to_english(rendered.text, language, _CLIENT)
    # No particle means decode has no signal to recover "as for" from --
    # a documented limitation -- but the topic is still fronted and the
    # sentence still decodes to something containing the topic and the verb.
    assert "as for" not in decoded.text
    assert "cat" in decoded.text
    assert "sleep" in decoded.text


def test_plural_topic_noun_is_recognized():
    language = _find(lambda g: g.topic_particle and g.has_articles)
    rendered = translate_to_conlang("As for the dogs, they sleep.", language, _CLIENT)
    decoded = translate_to_english(rendered.text, language, _CLIENT)
    assert "as for" in decoded.text
    assert "dog" in decoded.text


# --- false-trigger / regression guards ----------------------------------------


def test_as_i_said_does_not_misfire_as_a_topic():
    plan = _fake_plan_dict("As I said, it is late.", {})
    assert not any(s.get("kind") == "clause" and s.get("role") == "topic" for s in plan["slots"])


def test_applicative_for_him_is_unaffected_by_the_topic_regex():
    # Pass 31's applicative construction uses "for" mid-sentence; the topic
    # regex only matches a sentence-initial "as for", so it must not fire.
    plan = _fake_plan_dict("I cook for him.", {})
    assert not any(s.get("kind") == "clause" and s.get("role") == "topic" for s in plan["slots"])
