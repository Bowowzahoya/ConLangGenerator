"""Noun number (plural) and clause types (imperative, yes/no and wh
questions), plus per-sentence planning -- generation, planning, rendering
and decoding back to English."""

from conlang_generator.core.grammar import GrammarProfile
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.translator import (
    _decode_noun,
    _decode_verb,
    translate_to_conlang,
    translate_to_english,
)

_SEED = 278  # SVO, nominative-accusative; core vocabulary has mountain/see/river


def _language(seed: int = _SEED):
    return generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())


def _first_language_with_order(orders: set[str]):
    for seed in range(1, 200):
        language = _language(seed)
        if language.grammar.word_order.value in orders:
            return language
    raise AssertionError("no seed found")


# --- generation -----------------------------------------------------------


def test_every_language_gets_plural_imperative_and_question_marking():
    for seed in (1, 2, 3):
        grammar = _language(seed).grammar
        assert [a.label for a in grammar.number_affixes][0] == "plural"  # a dual may follow
        assert grammar.mood_affixes[0].label == "imperative"
        assert grammar.number_affixes[0].suffix
        assert grammar.mood_affixes[0].suffix
        assert grammar.question_particle


def test_clause_grammar_is_reproducible_per_seed():
    assert _language(5).grammar.question_particle == _language(5).grammar.question_particle
    assert _language(5).grammar.number_affixes == _language(5).grammar.number_affixes


# --- planning -------------------------------------------------------------


def test_split_sentences_keeps_terminal_punctuation():
    assert sentence_planner.split_sentences("Hi there. Is it high? Go!") == ["Hi there.", "Is it high?", "Go!"]
    assert sentence_planner.split_sentences("no punctuation") == ["no punctuation"]
    assert sentence_planner.split_sentences("   ") == []


def test_parse_reads_mood_and_number_from_the_object_form():
    plan = sentence_planner._parse(
        '{"mood": "imperative", "slots": [{"kind": "content", "gloss": "dog", "pos": "noun", "number": "plural"}]}'
    )
    assert plan is not None
    assert plan.mood == "imperative"
    assert plan.slots[0].number == "plural"


def test_parse_still_accepts_a_bare_array_and_defaults_the_mood():
    plan = sentence_planner._parse('[{"kind": "content", "gloss": "dog", "pos": "noun"}]')
    assert plan is not None
    assert plan.mood == "declarative"
    assert plan.slots[0].number is None


def test_parse_ignores_an_unknown_mood_or_number():
    plan = sentence_planner._parse(
        '{"mood": "shouting", "slots": [{"kind": "content", "gloss": "dog", "pos": "noun", "number": "septal"}]}'
    )
    assert plan is not None
    assert plan.mood == "declarative"
    assert plan.slots[0].number is None


# --- plural ---------------------------------------------------------------


def test_a_plural_noun_is_marked_and_decodes_back_as_plural():
    language = _language()
    client = FakeLLMClient()
    singular = translate_to_conlang("I see the mountain", language, client)
    plural = translate_to_conlang("I see the mountains", language, client)
    assert singular.text != plural.text
    mountain = language.lexicon.by_gloss("mountain")
    plural_tokens = [t for t in plural.text.split() if t.startswith(mountain.romanization[:3])]
    decoded = [_decode_noun(language, t) for t in plural.text.split()]
    assert any(d is not None and d[0] == mountain and d[1].endswith("plural") for d in decoded), plural_tokens


def test_plural_noun_reads_back_in_english_as_plural():
    language = _language()
    client = FakeLLMClient()
    conlang = translate_to_conlang("I see the mountains", language, client).text
    english = translate_to_english(conlang, language, client).text
    assert "mountains" in english


def test_a_language_saved_without_number_affixes_just_leaves_the_noun_bare():
    language = _language()
    old_grammar = language.grammar.model_copy(update={"number_affixes": ()})
    old = language.model_copy(update={"grammar": old_grammar})
    client = FakeLLMClient()
    singular = translate_to_conlang("I see the mountain", old, client)
    plural = translate_to_conlang("I see the mountains", old, client)
    assert singular.text == plural.text


# --- imperative -----------------------------------------------------------


def test_an_imperative_verb_takes_the_imperative_marker_and_decodes_as_a_command():
    language = _language()
    client = FakeLLMClient()
    result = translate_to_conlang("See the mountain!", language, client)
    verb = language.lexicon.by_gloss("see")
    imperatives = [_decode_verb(language, t) for t in result.text.split()]
    assert any(d is not None and d[0] == verb and d[1] == "imperative" for d in imperatives)
    assert result.text != translate_to_conlang("I see the mountain.", language, client).text
    assert translate_to_english(result.text, language, client).text.endswith("!")


# --- questions ------------------------------------------------------------


def test_a_yes_no_question_gets_the_particle_at_the_end_in_an_svo_language():
    language = _language()
    assert language.grammar.word_order.value == "SVO"
    client = FakeLLMClient()
    romanized_particle = language.romanization.apply(language.grammar.question_particle)
    question = translate_to_conlang("Do you see the mountain?", language, client)
    assert question.text.split()[-1] == romanized_particle
    statement = translate_to_conlang("You see the mountain.", language, client)
    assert romanized_particle not in statement.text.split()
    assert translate_to_english(question.text, language, client).text.endswith("?")


def test_a_verb_initial_language_puts_the_particle_first():
    language = _first_language_with_order({"VSO", "VOS"})
    romanized_particle = language.romanization.apply(language.grammar.question_particle)
    question = translate_to_conlang("Do you see the mountain?", language, FakeLLMClient())
    assert question.text.split()[0] == romanized_particle


def test_a_wh_question_has_no_particle():
    language = _language()
    romanized_particle = language.romanization.apply(language.grammar.question_particle)
    result = translate_to_conlang("What do you see?", language, FakeLLMClient())
    assert romanized_particle not in result.text.split()


# --- several sentences ----------------------------------------------------


def test_each_sentence_is_planned_and_rendered_separately():
    language = _language()
    client = FakeLLMClient()
    two = translate_to_conlang("I see the mountain. You see the river.", language, client)
    one_a = translate_to_conlang("I see the mountain.", language, client)
    one_b = translate_to_conlang("You see the river.", language, client)
    assert two.text == f"{one_a.text} {one_b.text}"


def test_a_sentence_initial_capital_in_a_later_sentence_is_not_a_name():
    language = _language()
    client = FakeLLMClient()
    result = translate_to_conlang("I see the mountain. Just see the river.", language, client)
    assert not any(names_entry.notes == "proper name" for names_entry in result.coined)


def test_grammar_profile_defaults_keep_old_saved_languages_valid():
    fields = GrammarProfile.model_fields
    assert fields["number_affixes"].default == ()
    assert fields["mood_affixes"].default == ()
    assert fields["question_particle"].default == ""
