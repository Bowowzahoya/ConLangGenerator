"""Aspect/mood follow-ups: auxiliary (periphrastic) tenses/aspects/moods,
evidentiality, negation strategies and the prohibitive, distinct suffixes, and
the affixes evolving with sound change."""

from conlang_generator.core.grammar import InflectionAffix
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import inflection_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.sound_change import evolve_language
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


def _verb(**kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss="see", pos="verb", agreement="I", **kw)


_NEGATION = PlannedSlot(kind="negation")


def _decoded(language, token):
    return _decode_verb_full(language, token)


# --- generation -----------------------------------------------------------------


def test_the_follow_up_choices_are_rolled():
    grammars = [_language(s).grammar for s in range(1, 100)]
    assert {g.evidentials for g in grammars} == set(inflection_gen.EVIDENTIAL_SYSTEMS)
    assert {g.negation_strategy for g in grammars} == {"particle", "affix", "both"}
    assert {g.auxiliary_position for g in grammars if g.periphrastic_labels} == {"before", "after"}
    assert any(a.label == "prohibitive" for g in grammars for a in g.mood_affixes)
    for g in grammars:
        assert [a.label for a in g.evidential_affixes] == list(g.evidentials)
        assert bool(g.verb_negative_affixes) == (g.negation_strategy != "particle")
        available = {*g.tenses, *g.aspects, *g.moods}
        assert set(g.periphrastic_labels) <= available


def test_the_new_grammar_fields_default_for_older_saved_languages():
    grammar = _language(1).grammar.__class__.model_fields
    assert grammar["evidentials"].default == () and grammar["negation_strategy"].default == "particle"
    assert grammar["periphrastic_labels"].default == () and grammar["auxiliary_position"].default == "before"


def test_suffixes_of_one_paradigm_no_longer_collide():
    collisions = 0
    for seed in range(1, 100):
        grammar = _language(seed).grammar
        for fields in (
            inflection_gen._VERB_SUFFIX_FIELDS, inflection_gen._NOUN_SUFFIX_FIELDS, inflection_gen._MODIFIER_SUFFIX_FIELDS,
        ):
            suffixes = [
                a.suffix for name in fields for a in getattr(grammar, name) if a.suffix and not a.prefix
            ]
            collisions += len(suffixes) - len(set(suffixes))
    assert collisions == 0


def test_resolve_collisions_keeps_the_first_and_redraws_the_later_one():
    language = _language(4)
    grammar = language.grammar
    first = grammar.agreement_affixes[0]
    clash = InflectionAffix(label="past", suffix=first.suffix)
    forced = grammar.model_copy(update={"tense_affixes": (clash,)})
    import random

    fixed = inflection_gen.resolve_collisions(
        random.Random(1), language.phonology, language.syllable_structure, forced
    )
    assert fixed.tense_affixes[0].suffix == first.suffix  # tense comes first in the verb paradigm
    assert fixed.agreement_affixes[0].suffix != first.suffix


# --- auxiliary tenses, aspects and moods ---------------------------------------------


def _roundtrips(language, sentence: str, expected: str) -> bool:
    result = translate_to_conlang(sentence, language, _CLIENT)
    return expected in translate_to_english(result.text, result.language, _CLIENT).text


def _auxiliary_language(position: str):
    language = _find(lambda g: "past" in g.tenses and not g.pro_drop and not g.object_agreement)
    return _with(language, periphrastic_labels=("past",), auxiliary_position=position, negation_strategy="particle",
                 verb_negative_affixes=())


def test_a_periphrastic_tense_is_an_auxiliary_word_beside_the_verb():
    for position in ("before", "after"):
        language = _auxiliary_language(position)
        plain = _with(language, periphrastic_labels=())
        _, aux_parts, aux_glosses = _render(language, _verb(tense="past"))
        _, suffix_parts, _ = _render(plain, _verb(tense="past"))
        assert len(aux_parts) == len(suffix_parts) + 1
        assert "aux-past" in aux_glosses
        assert aux_glosses.index("aux-past") == (0 if position == "before" else len(aux_glosses) - 1)
        assert aux_parts[1 if position == "before" else 0] != suffix_parts[0]  # the verb has no past suffix


def test_the_auxiliary_is_one_word_reused_and_carries_the_label_back():
    language = _auxiliary_language("before")
    updated, _, _ = _render(language, _verb(tense="past"), _verb(tense="past"))
    assert sum(1 for e in updated.lexicon.entries if e.primary_gloss == "aux-past") == 1
    result = translate_to_conlang("I saw the river.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "saw" in english and "aux" not in english


def test_the_auxiliary_reads_back_after_the_verb_too():
    language = _auxiliary_language("after")
    result = translate_to_conlang("I saw the river.", language, _CLIENT)
    assert "saw" in translate_to_english(result.text, result.language, _CLIENT).text


def test_a_periphrastic_aspect_and_mood_use_their_own_auxiliaries():
    language = _find(lambda g: "progressive" in g.aspects and "conditional" in g.moods and not g.object_agreement)
    language = _with(
        language, periphrastic_labels=("progressive", "conditional"), negation_strategy="particle",
        verb_negative_affixes=(),
    )
    _, _, glosses = _render(language, _verb(aspect="progressive", verb_mood="conditional"))
    assert "aux-progressive" in glosses and "aux-conditional" in glosses
    _, _, none = _render(_with(language, periphrastic_labels=()), _verb(aspect="progressive", verb_mood="conditional"))
    assert not any(g and g.startswith("aux-") for g in none)


def test_a_command_never_takes_an_auxiliary():
    language = _auxiliary_language("before")
    _, _, glosses = _render(language, _verb(tense="past"), mood="imperative")
    assert "aux-past" not in glosses


# --- negation ----------------------------------------------------------------------------


def _negation_language(strategy: str):
    def clean(language) -> bool:
        return _decodes(_with(language, periphrastic_labels=()), strategy)

    return _with(
        _find(lambda g: g.negation_strategy == strategy and not g.object_agreement, clean),
        periphrastic_labels=(),
    )


def _decodes(language, strategy: str) -> bool:
    _, parts, _ = _render(language, _verb(tense=language.grammar.tenses[0] if language.grammar.tenses else None), _NEGATION)
    decoded = [_decoded(language, p) for p in parts]
    return any(d is not None and d[11] for d in decoded)


def test_a_suffix_negation_folds_the_negation_into_the_verb():
    language = _negation_language("affix")
    not_word = language.lexicon.by_gloss("not").romanization
    _, parts, _ = _render(language, _verb(), _NEGATION)
    _, positive, _ = _render(language, _verb())
    assert len(parts) == 1 and not_word not in parts
    assert parts[0] != positive[0]


def test_a_both_negation_keeps_the_word_and_marks_the_verb():
    language = _negation_language("both")
    not_word = language.lexicon.by_gloss("not").romanization
    _, parts, _ = _render(language, _verb(), _NEGATION)
    assert not_word in parts and len(parts) == 2
    result = translate_to_conlang("I do not see the river.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert english.count("not") == 1  # negative concord reads as one "not"


def test_a_particle_negation_is_unchanged():
    language = _find(lambda g: g.negation_strategy == "particle" and not g.object_agreement)
    not_word = language.lexicon.by_gloss("not").romanization
    _, parts, _ = _render(language, _verb(), _NEGATION)
    _, positive, _ = _render(language, _verb())
    assert not_word in parts and parts[0] == positive[0] or parts[1] == positive[0]


def test_the_negated_verb_decodes_as_negative_and_reads_back_as_not():
    language = _negation_language("affix")
    result = translate_to_conlang("I do not see the river.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "not" in english


def _prohibitive_language():
    def ok(language) -> bool:
        _, parts, _ = _render(_with(language, periphrastic_labels=()), _verb(), _NEGATION, mood="imperative")
        decoded = _decoded(language, parts[0])
        return decoded is not None and decoded[1] == "prohibitive"

    return _find(lambda g: any(a.label == "prohibitive" for a in g.mood_affixes) and not g.object_agreement, ok)


def test_a_negated_command_takes_the_prohibitive_instead_of_a_negation_word():
    language = _prohibitive_language()
    not_word = language.lexicon.by_gloss("not").romanization
    _, prohibited, _ = _render(language, _verb(), _NEGATION, mood="imperative")
    _, command, _ = _render(language, _verb(), mood="imperative")
    assert not_word not in prohibited and len(prohibited) == 1 and prohibited[0] != command[0]
    result = translate_to_conlang("Do not see the river!", language, _CLIENT)
    assert "do not see" in translate_to_english(result.text, result.language, _CLIENT).text


def test_a_language_without_a_prohibitive_keeps_the_particle_in_a_command():
    language = _find(lambda g: not any(a.label == "prohibitive" for a in g.mood_affixes) and g.negation_strategy != "affix")
    not_word = language.lexicon.by_gloss("not").romanization
    _, parts, _ = _render(language, _verb(), _NEGATION, mood="imperative")
    assert not_word in parts


# --- evidentiality --------------------------------------------------------------------------


def _evidential_language():
    def ok(language) -> bool:
        language = _with(language, periphrastic_labels=())
        for label in language.grammar.evidentials:
            _, parts, _ = _render(language, _verb(evidential=label))
            decoded = _decoded(language, parts[0])
            if decoded is None or decoded[10] != label:
                return False
        return True

    return _with(
        _find(lambda g: g.evidentials == ("witnessed", "inferred", "reported") and not g.object_agreement, ok),
        periphrastic_labels=(),
    )


def test_an_evidential_marks_the_verb_and_decodes_back():
    language = _evidential_language()
    plain = _render(language, _verb())[1][0]
    forms = {label: _render(language, _verb(evidential=label))[1][0] for label in language.grammar.evidentials}
    assert len({plain, *forms.values()}) == 4
    for label, form in forms.items():
        assert _decoded(language, form)[10] == label


def test_an_evidential_reads_back_in_english():
    language = _evidential_language()
    result = translate_to_conlang("I reportedly see the river.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "reportedly" in english


def test_a_language_without_evidentials_ignores_the_field():
    language = _find(lambda g: not g.evidentials and not g.object_agreement)
    assert _render(language, _verb(evidential="reported"))[1] == _render(language, _verb())[1]


def test_the_planner_marks_an_evidential_only_when_the_language_has_one():
    with_it = _find(lambda g: "reported" in g.evidentials)
    without = _find(lambda g: not g.evidentials)
    plan = sentence_planner.plan_sentence("I reportedly see the river.", with_it, _CLIENT)
    assert any(slot.evidential == "reported" for slot in plan.slots)
    plan = sentence_planner.plan_sentence("I reportedly see the river.", without, _CLIENT)
    assert all(slot.evidential is None for slot in plan.slots)


def test_the_planner_prompt_lists_the_evidentials():
    language = _find(lambda g: "reported" in g.evidentials)
    prompt = sentence_planner._build_system_prompt(language)
    assert "evidentials this language actually has: " in prompt and "reported" in prompt


# --- evolution of the affixes ----------------------------------------------------------------


def test_sound_change_reaches_the_inflectional_affixes():
    changed = 0
    for seed in range(1, 8):
        base = _language(seed)
        evolved = evolve_language("Evolved", base, 800, TraitProfile(), seed=seed)
        assert evolved == evolve_language("Evolved", base, 800, TraitProfile(), seed=seed)
        for name in ("tense_affixes", "aspect_affixes", "mood_affixes", "case_affixes", "evidential_affixes"):
            before = getattr(base.grammar, name)
            after = getattr(evolved.grammar, name)
            assert [a.label for a in after] == [a.label for a in before]
            assert all(a.suffix or a.prefix or a.infix for a in after)
            changed += sum(1 for a, b in zip(before, after) if a != b)
    assert changed > 0


def test_evolved_affixes_stay_distinct_and_the_language_still_translates():
    base = _language(6)
    evolved = evolve_language("Evolved", base, 800, TraitProfile(), seed=3)
    suffixes = [a.suffix for name in inflection_gen._VERB_SUFFIX_FIELDS for a in getattr(evolved.grammar, name) if a.suffix]
    assert len(set(suffixes)) >= len(suffixes) - 2
    result = translate_to_conlang("I see the river.", evolved, _CLIENT)
    assert "<unknown" not in translate_to_english(result.text, result.language, _CLIENT).text


def test_no_evolution_leaves_the_affixes_alone():
    base = _language(6)
    assert evolve_language("Same", base, 0, TraitProfile(), seed=1).grammar.aspect_affixes == base.grammar.aspect_affixes
