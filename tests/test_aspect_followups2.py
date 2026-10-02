"""Aspect/mood follow-ups, second round: a periphrastic auxiliary word can now
agree with the subject like a real auxiliary "have"/"has" instead of being an
invariant particle; the ordinary negative suffix can now mark a non-finite
verb form (infinitive, nominalized...) -- previously negation only ever
reached a finite verb, so a negated non-finite clause (or one with no finite
verb at all, such as a bare infinitival complement) fell back to the bare
"not" particle even in a suffix-negating language; a negated existential
("there is no X") or a dative-possession clause ("A has no B") can now use a
dedicated negative-existential word instead of the ordinary negation particle;
and a second, narrower collision-resolution pass catches a suffix
concatenation (e.g. tense+agreement) that spells the same as some other,
single affix -- suffixes were previously only checked one at a time."""

import random

from conlang_generator.core.grammar import GrammarProfile, InflectionAffix
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import inflection_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from tests._shared_language import cached_language
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import (
    _decode_verb_full,
    _render_plan,
    translate_to_conlang,
    translate_to_english,
)

_CLIENT = FakeLLMClient()
_NEGATION = PlannedSlot(kind="negation")


_language = cached_language


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


def _verb(gloss: str = "go", **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="verb", agreement=kw.pop("agreement", "he"), **kw)


# --- generation -------------------------------------------------------------


def test_auxiliary_agreement_is_rolled():
    grammars = [_language(s).grammar for s in range(1, 150)]
    assert {g.auxiliary_agreement for g in grammars} == {True, False}


def test_the_new_field_defaults_for_older_saved_languages():
    assert GrammarProfile.model_fields["auxiliary_agreement"].default is False


# --- auxiliary agreement ------------------------------------------------------------


def _auxiliary_agreement_language():
    language = _find(lambda g: "past" in g.tenses and not g.pro_drop and not g.object_agreement)
    return _with(
        language, periphrastic_labels=("past",), auxiliary_position="before", auxiliary_agreement=True,
        negation_strategy="particle", verb_negative_affixes=(),
    )


def test_the_auxiliary_agrees_with_the_subject():
    language = _auxiliary_agreement_language()
    _, he_parts, he_glosses = _render(language, _verb(tense="past", agreement="he"))
    _, i_parts, i_glosses = _render(language, _verb(tense="past", agreement="I"))
    aux_index_he = he_glosses.index("aux-past")
    aux_index_i = i_glosses.index("aux-past")
    assert he_parts[aux_index_he] != i_parts[aux_index_i]


def test_without_the_trait_the_auxiliary_stays_invariant():
    language = _with(_auxiliary_agreement_language(), auxiliary_agreement=False)
    _, he_parts, he_glosses = _render(language, _verb(tense="past", agreement="he"))
    _, i_parts, i_glosses = _render(language, _verb(tense="past", agreement="I"))
    assert he_parts[he_glosses.index("aux-past")] == i_parts[i_glosses.index("aux-past")]


def test_the_auxiliary_also_agrees_in_number_where_the_language_has_it():
    base = _find(
        lambda g: "past" in g.tenses and g.verb_number_agreement and not g.pro_drop and not g.object_agreement
    )
    language = _with(
        base, periphrastic_labels=("past",), auxiliary_position="before", auxiliary_agreement=True,
        negation_strategy="particle", verb_negative_affixes=(),
    )
    _, singular, s_glosses = _render(language, _verb(tense="past", agreement="he"))
    _, plural, p_glosses = _render(language, _verb(tense="past", agreement="he", subject_number="plural"))
    assert singular[s_glosses.index("aux-past")] != plural[p_glosses.index("aux-past")]


def test_the_agreeing_auxiliary_still_reads_back():
    language = _auxiliary_agreement_language()
    updated, parts, _ = _render(language, _verb(tense="past", agreement="he"))
    english = translate_to_english(" ".join(parts), updated, _CLIENT).text
    assert "went" in english or "go" in english


def test_the_copula_auxiliary_agrees_too():
    language = _find(lambda g: "past" in g.tenses and g.has_overt_copula and not g.pro_drop)
    language = _with(
        language, periphrastic_labels=("past",), auxiliary_position="before", auxiliary_agreement=True,
        negation_strategy="particle", verb_negative_affixes=(),
    )
    copula_he = PlannedSlot(kind="copula", tense="past", agreement="he")
    copula_i = PlannedSlot(kind="copula", tense="past", agreement="I")
    _, he_parts, he_glosses = _render(language, copula_he)
    _, i_parts, i_glosses = _render(language, copula_i)
    assert he_parts[he_glosses.index("aux-past")] != i_parts[i_glosses.index("aux-past")]


def test_a_whole_sentence_with_an_agreeing_auxiliary_round_trips():
    language = _auxiliary_agreement_language()
    result = translate_to_conlang("He saw the river.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "river" in english and ("saw" in english or "see" in english)


# --- negative non-finite verb forms ------------------------------------------------


def _negatable_infinitive_language():
    return _find(
        lambda g: "infinitive" in g.verb_forms and g.negation_strategy == "affix" and g.verb_negative_affixes
    )


def test_a_negated_infinitive_carries_the_suffix_not_a_bare_particle():
    language = _negatable_infinitive_language()
    plain = _render(language, _verb(verb_form="infinitive"))[1]
    negated = _render(language, _verb(verb_form="infinitive"), _NEGATION)[1]
    assert len(negated) == len(plain)  # no separate "not" word -- absorbed as a suffix
    assert negated[0] != plain[0]


def test_the_negated_infinitive_decodes_with_the_negative_flag():
    language = _negatable_infinitive_language()
    negated = _render(language, _verb(verb_form="infinitive"), _NEGATION)[1][0]
    decoded = _decode_verb_full(language, negated)
    assert decoded is not None
    assert decoded[1] == "infinitive" and decoded[11] is True
    plain = _render(language, _verb(verb_form="infinitive"))[1][0]
    assert _decode_verb_full(language, plain)[11] is False


def test_a_negated_infinitive_reads_back_as_english_not():
    language = _negatable_infinitive_language()
    updated, parts, _ = _render(language, _verb(verb_form="infinitive"), _NEGATION)
    english = translate_to_english(" ".join(parts), updated, _CLIENT).text
    assert "not" in english


def test_a_negated_nominalized_clause_also_takes_the_suffix():
    language = _find(
        lambda g: "nominalized" in g.verb_forms and g.negation_strategy == "affix" and g.verb_negative_affixes
    )
    plain = _render(language, _verb(verb_form="nominalized"))[1][0]
    negated = _render(language, _verb(verb_form="nominalized"), _NEGATION)[1][0]
    assert negated != plain
    decoded = _decode_verb_full(language, negated)
    assert decoded is not None and decoded[1] == "nominalized" and decoded[11] is True


def test_a_negation_particle_language_leaves_the_infinitive_alone():
    language = _find(
        lambda g: "infinitive" in g.verb_forms and g.negation_strategy == "particle"
    )
    plain = _render(language, _verb(verb_form="infinitive"))[1]
    negated = _render(language, _verb(verb_form="infinitive"), _NEGATION)[1]
    assert negated[0] == plain[0]  # the verb form itself is untouched
    assert len(negated) == len(plain) + 1  # "not" still renders as its own word


# --- negative existentials ---------------------------------------------------


def test_negative_existential_is_rolled():
    grammars = [_language(s).grammar for s in range(1, 150)]
    assert {g.negative_existential for g in grammars} == {True, False}


def test_the_new_field_defaults_false_for_older_saved_languages():
    assert GrammarProfile.model_fields["negative_existential"].default is False


def _negative_existential_language():
    return _find(lambda g: g.negative_existential)


def test_a_negated_existential_is_one_dedicated_word():
    language = _negative_existential_language()
    plan = sentence_planner.plan_sentence("There is no dog.", language, _CLIENT)
    assert [s.gloss for s in plan.slots if s.kind == "content" and s.gloss == "not-exist"] == ["not-exist"]
    assert not any(s.kind == "negation" for s in plan.slots)
    result = translate_to_conlang("There is no dog.", language, _CLIENT)
    positive = translate_to_conlang("There is a dog.", language, _CLIENT)
    assert result.text != positive.text
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "does not exist" in english and "dog" in english


def test_a_positive_existential_is_unaffected():
    language = _negative_existential_language()
    plan = sentence_planner.plan_sentence("There is a dog.", language, _CLIENT)
    assert not any(s.gloss == "not-exist" for s in plan.slots if s.kind == "content")


def test_a_dative_possession_clause_also_uses_the_negative_existential():
    language = _find(lambda g: g.negative_existential and g.possession_clause == "dative_be")
    plan = sentence_planner.plan_sentence("I have no dog.", language, _CLIENT)
    glosses = [s.gloss for s in plan.slots]
    assert "dog" in glosses and "not-exist" in glosses  # "dog" is not lost to the "no" token
    result = translate_to_conlang("I have no dog.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "does not exist" in english and "dog" in english and "i" in english.lower().split()


def test_a_language_without_the_trait_still_uses_the_ordinary_negation():
    language = _find(lambda g: not g.negative_existential)
    plan = sentence_planner.plan_sentence("There is no dog.", language, _CLIENT)
    assert not any(s.gloss == "not-exist" for s in plan.slots if s.kind == "content")
    assert any(s.kind == "negation" for s in plan.slots)


def test_the_prompt_mentions_the_dedicated_word_only_when_the_language_has_it():
    with_it = _negative_existential_language()
    without_it = _find(lambda g: not g.negative_existential)
    assert '"not-exist"' in sentence_planner._build_system_prompt(with_it)
    assert '"not-exist"' not in sentence_planner._build_system_prompt(without_it)


# --- a suffix concatenation colliding with a single affix -------------------


def test_resolve_collisions_also_fixes_a_two_affix_concatenation():
    language = _language(4)
    grammar = language.grammar
    tense = InflectionAffix(label="past", suffix=("a",))
    agreement = InflectionAffix(label="I", suffix=("b",))
    colliding = InflectionAffix(label="conditional", suffix=("a", "b"))  # spells like tense+agreement concatenated
    forced = grammar.model_copy(
        update={"tense_affixes": (tense,), "agreement_affixes": (agreement,), "mood_affixes": (colliding,)}
    )
    fixed = inflection_gen.resolve_collisions(
        random.Random(1), language.phonology, language.syllable_structure, forced
    )
    assert fixed.tense_affixes[0].suffix == ("a",)  # the pair keeps its own exponents
    assert fixed.agreement_affixes[0].suffix == ("b",)
    assert fixed.mood_affixes[0].suffix != ("a", "b")  # the single affix that collided was redrawn


def test_resolve_collisions_leaves_a_genuinely_distinct_grammar_alone():
    language = _language(4)
    fixed = inflection_gen.resolve_collisions(
        random.Random(1), language.phonology, language.syllable_structure, language.grammar, language.romanization
    )
    assert fixed == language.grammar
