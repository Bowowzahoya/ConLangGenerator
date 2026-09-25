"""The pronoun system: clusivity, third-person gender, honorific "you", pro-drop
and the mapping from English pronouns."""

from conlang_generator.core.grammar import GrammarProfile
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import inflection_gen, pronoun_gen
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


def _pronoun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="pronoun", **kw)


def _verb(agreement: str = "I") -> PlannedSlot:
    return PlannedSlot(kind="content", gloss="see", pos="verb", agreement=agreement)


def _render(language, *slots):
    updated, romanized, _, glosses = _render_plan(SentencePlan(slots=tuple(slots)), language, _CLIENT, [])
    return updated, romanized, glosses


# --- generation -----------------------------------------------------------


def test_each_pronoun_distinction_is_rolled():
    grammars = [_language(s).grammar for s in range(1, 80)]
    for field in ("clusivity", "third_person_gender", "honorific_you", "pro_drop"):
        values = {getattr(g, field) for g in grammars}
        assert values == {True, False}, field


def test_pro_drop_needs_distinct_person_suffixes():
    for seed in range(1, 80):
        grammar = _language(seed).grammar
        if grammar.pro_drop:
            suffixes = [(a.prefix, a.infix, a.suffix) for a in grammar.agreement_affixes if a.label in pronoun_gen.PERSON_LABELS]
            assert len(set(suffixes)) == len(pronoun_gen.PERSON_LABELS)


def test_a_high_social_hierarchy_makes_an_honorific_more_likely():
    import random

    def rate(hierarchy: float) -> float:
        rolls = [pronoun_gen.roll_pronoun_system(random.Random(i), hierarchy)["honorific_you"] for i in range(400)]
        return sum(rolls) / len(rolls)

    assert rate(1.0) > rate(0.0) + 0.15
    assert abs(rate(-1.0) - rate(0.0)) < 0.001  # a low hierarchy is not a reason to have no honorific either


def test_grammar_defaults_keep_old_saved_languages_valid():
    fields = GrammarProfile.model_fields
    assert all(fields[f].default is False for f in ("clusivity", "third_person_gender", "honorific_you", "pro_drop"))


# --- the inventory and the mapping ----------------------------------------


def test_the_pronoun_glosses_follow_the_languages_distinctions():
    plain = _find(lambda g: not g.clusivity and not g.third_person_gender and not g.honorific_you)
    assert pronoun_gen.pronoun_glosses(plain.grammar) == ("I", "you", "you-plural", "he", "they", "we")
    rich = _find(lambda g: g.clusivity and g.third_person_gender and g.honorific_you)
    assert pronoun_gen.pronoun_glosses(rich.grammar) == (
        "I", "you", "you-plural", "you-polite", "he", "she", "it", "they", "we-inclusive", "we-exclusive",
    )


def test_english_pronouns_map_onto_this_languages_own():
    rich = _find(lambda g: g.clusivity and g.third_person_gender and g.honorific_you).grammar
    plain = _find(lambda g: not g.clusivity and not g.third_person_gender and not g.honorific_you).grammar
    assert pronoun_gen.english_pronoun_gloss(rich, "she") == "she" and pronoun_gen.english_pronoun_gloss(plain, "she") == "he"
    assert pronoun_gen.english_pronoun_gloss(rich, "it") == "it" and pronoun_gen.english_pronoun_gloss(plain, "it") == "he"
    assert pronoun_gen.english_pronoun_gloss(rich, "we") == "we-exclusive"
    assert pronoun_gen.english_pronoun_gloss(plain, "we") == "we"
    assert pronoun_gen.english_pronoun_gloss(rich, "you", ["sir"]) == "you-polite"
    assert pronoun_gen.english_pronoun_gloss(rich, "you", ["hello"]) == "you"
    assert pronoun_gen.english_pronoun_gloss(plain, "you", ["sir"]) == "you"
    assert pronoun_gen.english_pronoun_gloss(plain, "them") == "they"


def test_every_pronoun_gloss_has_a_person_for_agreement():
    for gloss in pronoun_gen.pronoun_glosses(_find(lambda g: g.clusivity and g.third_person_gender and g.honorific_you).grammar):
        assert pronoun_gen.person_label(gloss) in pronoun_gen.PERSON_LABELS
    assert pronoun_gen.person_label("dog") is None


# --- planning -------------------------------------------------------------


def test_the_prompt_lists_the_pronouns_and_the_mapping():
    rich = _find(lambda g: g.clusivity and g.third_person_gender and g.honorific_you)
    prompt = sentence_planner._build_system_prompt(rich)
    assert "we-inclusive, we-exclusive" in prompt and '"you-polite"' in prompt and '"she" -> "she"' in prompt
    dropping = _find(lambda g: g.pro_drop)
    assert "drops subject pronouns (yes)" in sentence_planner._build_system_prompt(dropping)
    keeping = _find(lambda g: not g.pro_drop)
    assert "drops subject pronouns (no)" in sentence_planner._build_system_prompt(keeping)
    plain = _find(lambda g: not g.clusivity and not g.third_person_gender and not g.honorific_you)
    text = sentence_planner._build_system_prompt(plain)
    assert 'no separate "she"' in text and '"we/us" -> "we"' in text


def _fake_pronouns(sentence: str, **meta) -> list[str]:
    base = {"word_order": "SVO", "alignment": "nominative_accusative", "tenses": "past,non_past"}
    plan = _fake_plan_dict(sentence, {**base, **meta})
    return [s["gloss"] for s in plan["slots"] if s.get("pos") == "pronoun"]


def test_the_fake_planner_uses_this_languages_pronoun_glosses():
    rich = {"clusivity": "true", "third_person_gender": "true", "honorific_you": "true"}
    assert _fake_pronouns("She sees them.", **rich) == ["she", "they"]
    assert _fake_pronouns("She sees them.") == ["he", "they"]
    assert _fake_pronouns("We see you.", **rich) == ["we-exclusive", "you"]
    assert _fake_pronouns("It sees me.", third_person_gender="true") == ["it", "i"]


def test_a_third_person_or_plural_subject_agrees_like_he():
    plan = _fake_plan_dict("They see the river.", {"word_order": "SVO", "alignment": "nominative_accusative", "tenses": "past"})
    assert next(s for s in plan["slots"] if s.get("pos") == "verb")["agreement"] == "he"


# --- rendering ------------------------------------------------------------


def test_they_and_she_agree_like_he():
    language = _find(
        lambda g: not g.pro_drop
        and not g.third_person_gender
        and len({a.suffix for a in g.agreement_affixes if a.label in pronoun_gen.PERSON_LABELS}) == 4
    )
    stem = language.lexicon.by_gloss("see").romanization[:2]

    def verb(sentence: str) -> str:
        return next(t for t in translate_to_conlang(sentence, language, _CLIENT).text.split() if t.startswith(stem))

    assert verb("They see the river.") == verb("He sees the river.") == verb("She sees the river.")
    assert verb("They see the river.") != verb("We see the river.")


def test_a_subject_pronoun_is_omitted_in_a_pro_drop_language():
    language = _find(lambda g: g.pro_drop and g.alignment.value == "nominative_accusative")
    _, tokens, glosses = _render(language, _pronoun("I"), _verb("I"), _pronoun("you", case="accusative"))
    assert len(tokens) == 2 and "I" not in glosses  # the subject "I" is gone, the object stays


def test_a_pronoun_is_kept_where_the_language_does_not_drop_it():
    language = _find(lambda g: not g.pro_drop)
    _, tokens, _ = _render(language, _pronoun("I"), _verb("I"))
    assert len(tokens) == 2


def test_only_the_pronoun_matching_the_verbs_person_is_dropped():
    language = _find(lambda g: g.pro_drop)
    _, tokens, _ = _render(language, _pronoun("you"), _verb("I"))
    assert len(tokens) == 2  # the verb names "I", the pronoun is "you": nothing to drop


def test_a_dropped_subject_is_read_back_from_the_verbs_agreement():
    language = _find(lambda g: g.pro_drop and g.alignment.value == "nominative_accusative")
    keeping = language.model_copy(update={"grammar": language.grammar.model_copy(update={"pro_drop": False})})
    dropped = translate_to_conlang("I see the river.", language, _CLIENT)
    kept = translate_to_conlang("I see the river.", keeping, _CLIENT)
    assert len(dropped.text.split()) == len(kept.text.split()) - 1
    english = translate_to_english(dropped.text, dropped.language, _CLIENT).text
    assert "I" in english.split() and "river" in english


def test_the_verb_form_carries_the_person_that_replaces_the_pronoun():
    language = _find(lambda g: g.pro_drop)
    forms = {}
    for person in pronoun_gen.PERSON_LABELS:
        _, tokens, _ = _render(language, _verb(person))
        forms[person] = tokens[0]
        decoded = _decode_verb_full(language, tokens[0])
        assert decoded is not None and decoded[5] == person
    assert len(set(forms.values())) == 4


def test_new_pronouns_are_coined_and_read_back_in_english():
    language = _find(lambda g: g.honorific_you and g.clusivity)
    updated, tokens, glosses = _render(language, _pronoun("you-plural"), _pronoun("we-inclusive"))
    assert glosses == ["you-plural", "we-inclusive"]
    english = translate_to_english(" ".join(tokens), updated, _CLIENT).text
    assert "you (plural)" in english and "we (inclusive)" in english


def test_the_inflection_labels_are_unchanged_for_the_core_persons():
    assert inflection_gen.AGREEMENT_LABELS[:4] == pronoun_gen.PERSON_LABELS
