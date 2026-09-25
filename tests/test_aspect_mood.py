"""Aspect and verbal mood as systems separate from tense: generation,
planning, rendering and decoding."""

from conlang_generator.core.grammar import GrammarProfile
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import inflection_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient, _fake_plan_dict
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.translator import (
    _decode_verb_full,
    translate_to_conlang,
    translate_to_english,
)

_FOUR_WAY = ("perfective", "progressive", "perfect", "habitual")
_THREE_MOODS = ("subjunctive", "conditional", "potential")


def _language(seed: int):
    """The generated language without the follow-up features (auxiliary tenses,
    suffix negation, prohibitive, evidentials): these tests exercise plain
    aspect and mood marking (the follow-ups are in ``test_aspect_followups.py``)."""
    language = generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())
    grammar = language.grammar
    plain = grammar.model_copy(
        update={
            "periphrastic_labels": (),
            "negation_strategy": "particle",
            "verb_negative_affixes": (),
            "evidentials": (),
            "evidential_affixes": (),
            "mood_affixes": tuple(a for a in grammar.mood_affixes if a.label != "prohibitive"),
        }
    )
    return language.model_copy(update={"grammar": plain})


def _find(predicate, limit: int = 300, check=None):
    """The first language whose grammar satisfies ``predicate`` (and, when
    given, for which ``check(language)`` holds -- short invented suffixes can
    concatenate into another reading, so tests of exact decoding pick a
    language where the readings are unambiguous)."""
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language.grammar) and (check is None or check(language)):
            return language
    raise AssertionError("no seed found")


def _decodes_as_planned(language, cases) -> bool:
    for sentence, aspect, mood in cases:
        decoded = _decode_verb_full(language, _verb_form(language, sentence))
        if decoded is None or decoded[2] != aspect or decoded[3] != mood:
            return False
    return True


def _verb_form(language, sentence: str) -> str:
    """The rendered token for the first verb of ``sentence``."""
    verb = language.lexicon.by_gloss("see")
    result = translate_to_conlang(sentence, language, FakeLLMClient())
    stem = verb.romanization[:2]
    return next(t for t in result.text.split() if t.startswith(stem))


# --- generation -----------------------------------------------------------


def test_every_language_has_one_of_the_defined_aspect_and_mood_systems():
    for seed in range(1, 30):
        grammar = _language(seed).grammar
        assert grammar.aspects in inflection_gen.ASPECT_SYSTEMS
        assert grammar.moods in inflection_gen.MOOD_SYSTEMS
        assert [a.label for a in grammar.aspect_affixes] == list(grammar.aspects)
        assert [a.label for a in grammar.mood_affixes] == ["imperative", *grammar.moods]


def test_all_three_aspect_systems_occur_across_seeds():
    systems = {_language(seed).grammar.aspects for seed in range(1, 40)}
    assert systems == set(inflection_gen.ASPECT_SYSTEMS)


def test_aspect_and_mood_suffixes_are_made_distinct_where_the_inventory_allows():
    """Labels get distinct suffixes (re-drawn on a clash); only a tiny
    inventory that runs out of distinct short suffixes may still repeat one."""
    four_way = [g for g in (_language(seed).grammar for seed in range(1, 60)) if g.aspects == _FOUR_WAY]
    assert len(four_way) >= 5
    clashing = [g for g in four_way if len({a.suffix for a in g.aspect_affixes}) < len(g.aspect_affixes)]
    assert len(clashing) <= len(four_way) // 5
    for grammar in four_way:
        aspect_suffixes = {a.suffix for a in grammar.aspect_affixes}
        tense_suffixes = {a.suffix for a in grammar.tense_affixes}
        assert len(aspect_suffixes - tense_suffixes) >= len(aspect_suffixes) - 1


def test_aspect_and_mood_generation_is_reproducible_and_leaves_the_lexicon_alone():
    a, b = _language(7), _language(7)
    assert a.grammar.aspect_affixes == b.grammar.aspect_affixes
    assert a.grammar.mood_affixes == b.grammar.mood_affixes


def test_grammar_defaults_keep_old_saved_languages_valid():
    fields = GrammarProfile.model_fields
    assert fields["aspects"].default == ()
    assert fields["aspect_affixes"].default == ()
    assert fields["moods"].default == ()


# --- planning -------------------------------------------------------------


def test_parse_reads_aspect_and_verb_mood():
    plan = sentence_planner._parse(
        '[{"kind": "content", "gloss": "see", "pos": "verb", "aspect": "progressive", "verb_mood": "conditional"}]'
    )
    assert plan is not None
    assert plan.slots[0].aspect == "progressive"
    assert plan.slots[0].verb_mood == "conditional"


def test_the_prompt_lists_this_languages_own_aspects_and_moods():
    language = _find(lambda g: g.aspects == _FOUR_WAY and g.moods == _THREE_MOODS)
    prompt = sentence_planner._build_system_prompt(language)
    assert "progressive, perfect" in prompt or "perfective, progressive" in prompt
    assert "subjunctive, conditional, potential" in prompt
    none_language = _find(lambda g: not g.aspects and not g.moods)
    none_prompt = sentence_planner._build_system_prompt(none_language)
    assert 'never set "aspect"' in none_prompt
    assert 'never set "verb_mood"' in none_prompt


_META = {"word_order": "SVO", "alignment": "nominative_accusative", "tenses": "past,non_past"}


def _verb_slot(sentence: str, aspects: str, moods: str) -> dict:
    plan = _fake_plan_dict(sentence, {**_META, "aspects": aspects, "verb_moods": moods})
    return next(s for s in plan["slots"] if s.get("pos") == "verb")


def test_the_fake_planner_reads_progressive_perfect_and_modals():
    slot = _verb_slot("I am seeing the river.", ",".join(_FOUR_WAY), ",".join(_THREE_MOODS))
    assert slot["aspect"] == "progressive" and slot["gloss"] == "see" and slot["tense"] == "non_past"
    slot = _verb_slot("I was seeing the river.", ",".join(_FOUR_WAY), "")
    assert slot["aspect"] == "progressive" and slot["tense"] == "past"
    slot = _verb_slot("I have seen the river.", ",".join(_FOUR_WAY), "")
    assert slot["aspect"] == "perfect" and slot["gloss"] == "see"
    slot = _verb_slot("I would see the river.", "", ",".join(_THREE_MOODS))
    assert slot["verb_mood"] == "conditional"


def test_the_fake_planner_falls_back_to_the_closest_available_label():
    assert _verb_slot("I am seeing the river.", "perfective,imperfective", "")["aspect"] == "imperfective"
    assert _verb_slot("I have seen the river.", "perfective,imperfective", "")["aspect"] == "perfective"
    assert _verb_slot("I would see the river.", "", "irrealis")["verb_mood"] == "irrealis"
    assert "aspect" not in _verb_slot("I am seeing the river.", "", "")


# --- rendering and decoding -----------------------------------------------


_ROUND_TRIP_CASES = (
    ("I am seeing the river.", "progressive", None),
    ("I have seen the river.", "perfect", None),
    ("I would see the river.", None, "conditional"),
)


def test_aspect_and_mood_change_the_verb_form_and_decode_back():
    language = _find(
        lambda g: g.aspects == _FOUR_WAY and g.moods == _THREE_MOODS,
        check=lambda lang: _decodes_as_planned(lang, _ROUND_TRIP_CASES),
    )
    plain = _verb_form(language, "I see the river.")
    progressive = _verb_form(language, "I am seeing the river.")
    perfect = _verb_form(language, "I have seen the river.")
    conditional = _verb_form(language, "I would see the river.")
    assert len({plain, progressive, perfect, conditional}) == 4
    see = language.lexicon.by_gloss("see")
    for form, aspect, mood in (
        (progressive, "progressive", None),
        (perfect, "perfect", None),
        (conditional, None, "conditional"),
    ):
        decoded = _decode_verb_full(language, form)
        assert decoded is not None and decoded[0] == see
        assert decoded[2] == aspect and decoded[3] == mood


def test_tense_and_aspect_are_independent():
    language = _find(lambda g: g.aspects == _FOUR_WAY and "past" in g.tenses)
    past_progressive = _decode_verb_full(language, _verb_form(language, "I was seeing the river."))
    present_progressive = _decode_verb_full(language, _verb_form(language, "I am seeing the river."))
    assert past_progressive[2] == present_progressive[2] == "progressive"
    assert past_progressive[1] == "past"
    assert present_progressive[1] != "past"


def test_a_language_without_aspect_ignores_the_planned_aspect():
    language = _find(lambda g: not g.aspects and not g.moods)
    assert _verb_form(language, "I am seeing the river.") == _verb_form(language, "I see the river.")


def test_english_gloss_reflects_aspect_and_mood():
    language = _find(
        lambda g: g.aspects == _FOUR_WAY and g.moods == _THREE_MOODS,
        check=lambda lang: _decodes_as_planned(lang, _ROUND_TRIP_CASES),
    )
    client = FakeLLMClient()
    conditional = translate_to_conlang("I would see the river.", language, client).text
    assert "would see" in translate_to_english(conditional, language, client).text
    perfect = translate_to_conlang("I have seen the river.", language, client).text
    assert "has seen" in translate_to_english(perfect, language, client).text


def test_a_plain_verb_still_decodes_with_no_aspect_or_mood():
    language = _find(lambda g: g.aspects == _FOUR_WAY)
    decoded = _decode_verb_full(language, _verb_form(language, "I see the river."))
    assert decoded is not None and decoded[2] is None and decoded[3] is None
