"""Agreement follow-ups, second round: a plain subject-plus-intransitive-verb
sentence ("I sleep.", "The dogs sleep.") now gets a verb slot with correct
person/number agreement instead of falling through to the bare-noun
fallback (which produced no verb at all), and a classifier "repeater" noun
in a class-marked language now carries the same class marker as its head
noun and decodes back to a single reading instead of two."""

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import lexicon_gen, noun_class_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient, _fake_plan_dict
from tests._shared_language import cached_language
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import (
    _render_plan,
    translate_to_conlang,
    translate_to_english,
)

_CLIENT = FakeLLMClient()
_BASE = {"word_order": "SVO", "alignment": "nominative_accusative", "tenses": "past,non_past"}


_language = cached_language


def _find(predicate, limit: int = 400):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language.grammar):
            return language
    raise AssertionError("no seed found")


def _with(language, **updates):
    return language.model_copy(update={"grammar": language.grammar.model_copy(update=updates)})


def _render(language, *slots):
    updated, romanized, _, glosses = _render_plan(SentencePlan(slots=tuple(slots)), language, _CLIENT, [])
    return updated, romanized, glosses


def _noun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="noun", **kw)


def _plan(sentence: str, **meta) -> list[dict]:
    return _fake_plan_dict(sentence, {**_BASE, **meta})["slots"]


# --- the fake planner's intransitive-verb branch ---------------------------


def test_a_plain_intransitive_sentence_gets_a_verb_slot_not_two_nouns():
    plan = _plan("I sleep.")
    assert [s["pos"] for s in plan] == ["pronoun", "verb"]
    assert plan[0]["gloss"] == "i" and plan[1]["gloss"] == "sleep"


def test_verb_number_agreement_on_a_plural_subject():
    assert "subject_number" not in _plan("I sleep.", verb_number_agreement="true")[-1]
    assert _plan("We sleep.", verb_number_agreement="true")[-1]["subject_number"] == "plural"
    assert _plan("The dogs sleep.", verb_number_agreement="true")[-1]["subject_number"] == "plural"
    assert _plan("Dogs sleep.", verb_number_agreement="true")[-1]["subject_number"] == "plural"
    assert "subject_number" not in _plan("The dog sleeps.", verb_number_agreement="true")[-1]
    assert "subject_number" not in _plan("I sleep.")[-1]  # off when the language has no such agreement


def test_subject_and_verb_roles_do_not_swap_with_a_verb_first_word_order():
    # The regression this guards: the input tokens are always in English
    # surface order (subject then verb), regardless of the target language's
    # own word order -- only the OUTPUT slot order should follow it.
    for order in ("SVO", "VSO", "VOS", "SOV", "OVS"):
        plan = _plan("The dogs sleep.", word_order=order, verb_number_agreement="true")
        verb = next(s for s in plan if s["pos"] == "verb")
        assert verb["gloss"] == "sleep"
        assert verb["subject_number"] == "plural"
        noun = next(s for s in plan if s["pos"] == "noun")
        assert noun["gloss"] == "dog"


def test_an_ergative_language_leaves_the_intransitive_subject_unmarked():
    plan = _plan("The dogs sleep.", alignment="ergative_absolutive")
    noun = next(s for s in plan if s["pos"] == "noun")
    assert "case" not in noun


def test_a_language_without_the_agreement_leaves_the_verb_unmarked():
    off = _plan("We sleep.")
    assert "subject_number" not in off[-1]


def test_the_new_branch_renders_and_decodes_through_the_whole_pipeline():
    language = _find(lambda g: g.verb_number_agreement)
    result = translate_to_conlang("The dogs sleep.", language, _CLIENT)
    singular = translate_to_conlang("The dog sleeps.", language, _CLIENT)
    assert result.text != singular.text
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "dog" in english and "sleep" in english


def test_middle_voice_detection_still_wins_over_the_new_branch():
    language = _find(lambda g: "middle" in g.voices)
    plan = sentence_planner.plan_sentence("The door opens.", language, _CLIENT)
    verb = next((s for s in plan.slots if s.pos == "verb"), None)
    assert verb is not None and verb.voice == "middle"


# --- broader semantic-field coverage for class assignment -----------------


def test_semantic_fields_now_cover_animals_people_and_materials():
    assert noun_class_gen.semantic_field("dog") == noun_class_gen.semantic_field("wolf") == "animal"
    assert noun_class_gen.semantic_field("gold") == noun_class_gen.semantic_field("stone") == "material"
    assert noun_class_gen.semantic_field("teacher") == noun_class_gen.semantic_field("farmer") == "person"


def test_semantic_fields_cover_almost_every_noun_gloss_without_overlap():
    noun_glosses = {g for g, pos in lexicon_gen.ALL_MEANINGS if pos is PartOfSpeech.NOUN}
    seen: dict[str, str] = {}
    for field, words in noun_class_gen._SEMANTIC_FIELDS.items():
        for word in words:
            assert word not in seen, f"{word} is in both {seen.get(word)} and {field}"
            seen[word] = field
    covered = noun_glosses & set(seen)
    assert len(covered) / len(noun_glosses) > 0.95


# --- classifier repeater de-duplication in a class-marked language ---------


def _class_marked_classifier_language():
    return _find(lambda g: g.uses_classifiers and g.class_marking != "none")


def test_a_repeater_carries_the_same_class_marker_as_the_head_noun():
    language = _with(_class_marked_classifier_language(), repeater_rate=1.0)
    two = PlannedSlot(kind="content", gloss="two", pos="numeral")
    _, tokens, glosses = _render(language, two, _noun("dog"))
    assert glosses[1] == "dog" and glosses[2] == "dog"
    assert tokens[1] == tokens[2]  # identical surface form: same word, same class marker


def test_a_class_marked_repeater_decodes_back_once():
    language = _with(_class_marked_classifier_language(), repeater_rate=1.0)
    two = PlannedSlot(kind="content", gloss="two", pos="numeral")
    updated, tokens, _ = _render(language, two, _noun("dog"))
    english = translate_to_english(" ".join(tokens), updated, _CLIENT).text.split()
    assert english.count("dog") == 1 and "two" in english
