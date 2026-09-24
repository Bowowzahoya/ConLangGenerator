"""Voice (passive, antipassive, causative): generation, planning, rendering and
decoding."""

from conlang_generator.core.grammar import GrammarProfile
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import inflection_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient, _fake_plan_dict
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


def _find(predicate, limit: int = 250):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language.grammar):
            return language
    raise AssertionError("no seed found")


def _base(grammar) -> tuple:
    """The voices of the roll itself, without the reflexive/reciprocal suffix voices added later."""
    return tuple(v for v in grammar.voices if v not in ("reflexive", "reciprocal"))


def _verb_form(language, voice: str | None, tense: str | None = None, aspect: str | None = None) -> str:
    slot = PlannedSlot(kind="content", gloss="see", pos="verb", agreement="default", voice=voice, tense=tense, aspect=aspect)
    _, romanized, _, _ = _render_plan(SentencePlan(slots=(slot,)), language, _CLIENT, [])
    return romanized[0]


# --- generation -----------------------------------------------------------


def test_voice_systems_follow_the_alignment():
    seen_nom, seen_erg = set(), set()
    for seed in range(1, 80):
        grammar = _language(seed).grammar
        (seen_erg if grammar.alignment.value == "ergative_absolutive" else seen_nom).add(_base(grammar))
        assert [a.label for a in grammar.voice_affixes] == list(grammar.voices)
    assert seen_nom <= set(inflection_gen.VOICE_SYSTEMS_NOM_ACC)
    assert seen_erg <= set(inflection_gen.VOICE_SYSTEMS_ERGATIVE)
    assert len(seen_nom) >= 2 and len(seen_erg) >= 2
    assert all("antipassive" not in v for v in seen_nom)


def test_voice_suffixes_are_distinct_from_each_other():
    both = [g for g in (_language(s).grammar for s in range(1, 60)) if len(g.voices) >= 2]
    assert both
    clashing = [g for g in both if len({a.suffix for a in g.voice_affixes}) < len(g.voice_affixes)]
    assert len(clashing) <= len(both) // 5


def test_voice_generation_is_reproducible():
    assert _language(6).grammar.voice_affixes == _language(6).grammar.voice_affixes


def test_grammar_defaults_keep_old_saved_languages_valid():
    fields = GrammarProfile.model_fields
    assert fields["voices"].default == ()
    assert fields["voice_affixes"].default == ()


# --- planning -------------------------------------------------------------


def test_parse_reads_the_voice():
    plan = sentence_planner._parse('[{"kind": "content", "gloss": "see", "pos": "verb", "voice": "passive"}]')
    assert plan is not None and plan.slots[0].voice == "passive"


def test_the_prompt_lists_this_languages_voices():
    language = _find(lambda g: _base(g) == ("passive", "causative"))
    prompt = sentence_planner._build_system_prompt(language)
    assert "passive, causative" in prompt
    none_language = _find(lambda g: not g.voices)
    assert 'never set "voice"' in sentence_planner._build_system_prompt(none_language)


_META = {"word_order": "SVO", "alignment": "nominative_accusative", "tenses": "past,non_past", "voices": "passive,causative"}


def _summary(sentence: str, **overrides) -> list[tuple]:
    return [
        (s.get("gloss"), s.get("voice"), s.get("case"))
        for s in _fake_plan_dict(sentence, {**_META, **overrides})["slots"]
    ]


def test_the_fake_planner_plans_a_passive_with_its_agent_phrase():
    slots = _summary("The river was seen by the dog.")
    assert slots == [("river", None, None), ("see", "passive", None), ("by", None, None), ("dog", None, None)]
    tense = next(s for s in _fake_plan_dict("The river was seen by the dog.", _META)["slots"] if s.get("voice"))
    assert tense["tense"] == "past"


def test_a_postpositional_language_puts_the_agent_before_its_marker():
    slots = _summary("The river is seen by the dog.", postpositional="true")
    assert [s[0] for s in slots][-2:] == ["dog", "by"]


def test_a_verb_final_language_puts_the_agent_phrase_before_the_verb():
    slots = _summary("The river is seen by the dog.", word_order="SOV", postpositional="true")
    assert [s[0] for s in slots] == ["river", "dog", "by", "see"]


def test_without_the_passive_the_fake_planner_rewords_as_an_active():
    assert _summary("The river is seen by the dog.", voices="") == [
        ("dog", None, None), ("see", None, None), ("river", None, "accusative"),
    ]
    assert _summary("The river is seen.", voices="")[0] == ("they", None, None)


def test_an_adjective_with_ed_is_not_taken_for_a_passive():
    assert all(voice is None for _, voice, _ in _summary("The man is tired."))


def test_the_fake_planner_plans_a_causative():
    slots = _summary("I made the dog see the river.")
    assert slots[0][0] == "i"
    assert ("see", "causative", None) in slots
    assert ("dog", None, "accusative") in slots
    assert _summary("I made the dog see the river.", voices="passive")[1][1] is None  # no causative here


# --- rendering and decoding -----------------------------------------------


def test_each_voice_changes_the_verb_form_and_decodes_back():
    language = _find(lambda g: _base(g) == ("passive", "causative"))
    forms = {voice: _verb_form(language, voice) for voice in (None, "passive", "causative")}
    assert len(set(forms.values())) == 3
    see = language.lexicon.by_gloss("see")
    for voice in ("passive", "causative"):
        decoded = _decode_verb_full(language, forms[voice])
        assert decoded is not None and decoded[0] == see and decoded[4] == voice
    assert _decode_verb_full(language, forms[None])[4] is None


def test_an_antipassive_in_an_ergative_language_decodes_back():
    language = _find(lambda g: "antipassive" in g.voices)
    form = _verb_form(language, "antipassive")
    assert form != _verb_form(language, None)
    decoded = _decode_verb_full(language, form)
    assert decoded is not None and decoded[4] == "antipassive"


def test_tense_and_voice_are_independent():
    language = _find(lambda g: "passive" in g.voices and "past" in g.tenses)
    past_passive = _decode_verb_full(language, _verb_form(language, "passive", tense="past"))
    assert past_passive[1] == "past" and past_passive[4] == "passive"


def test_voice_combines_with_aspect():
    language = _find(lambda g: "passive" in g.voices and bool(g.aspects))
    aspect = language.grammar.aspects[0]
    decoded = _decode_verb_full(language, _verb_form(language, "passive", aspect=aspect))
    assert decoded is not None and decoded[2] == aspect and decoded[4] == "passive"


def test_a_voice_the_language_lacks_is_ignored():
    language = _find(lambda g: "causative" not in g.voices)
    assert _verb_form(language, "causative") == _verb_form(language, None)


def test_a_whole_passive_sentence_differs_from_its_active_and_reads_back_as_passive():
    language = _find(lambda g: "passive" in g.voices)
    active = translate_to_conlang("The dog sees the river.", language, _CLIENT)
    passive = translate_to_conlang("The river is seen by the dog.", language, _CLIENT)
    assert active.text != passive.text
    english = translate_to_english(passive.text, passive.language, _CLIENT).text
    assert "is seen" in english or "was seen" in english
    assert "river" in english and "dog" in english


def test_english_reads_a_causative_as_make():
    language = _find(lambda g: "causative" in g.voices)
    result = translate_to_conlang("I made the dog see the river.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "made see" in english
