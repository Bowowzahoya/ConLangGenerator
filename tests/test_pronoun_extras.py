"""Reflexives and reciprocals, possessive pronoun paradigms, verb number and
politeness agreement, and object pro-drop."""

from conlang_generator.core.grammar import GrammarProfile
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import pronoun_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient, _fake_plan_dict
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import (
    _decode_noun,
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


def _render(language, *slots):
    updated, romanized, _, glosses = _render_plan(SentencePlan(slots=tuple(slots)), language, _CLIENT, [])
    return updated, romanized, glosses


def _pronoun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="pronoun", **kw)


def _verb(**kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss="see", pos="verb", agreement=kw.pop("agreement", "he"), **kw)


def _noun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="noun", **kw)


# --- generation -----------------------------------------------------------


def test_every_option_is_rolled():
    grammars = [_language(s).grammar for s in range(1, 100)]
    assert {g.reflexive_marking for g in grammars} == {"word", "affix", "none"}
    assert {g.reciprocal_marking for g in grammars} == {"word", "affix", "none"}
    assert {g.possessive_pronouns for g in grammars} == {"regular", "words", "affix"}
    for field in ("verb_number_agreement", "verb_politeness", "object_pro_drop"):
        assert {getattr(g, field) for g in grammars} == {True, False}, field


def test_affix_marked_reflexives_and_reciprocals_are_voices_with_suffixes():
    for seed in range(1, 100):
        grammar = _language(seed).grammar
        assert [a.label for a in grammar.voice_affixes] == list(grammar.voices)
        assert ("reflexive" in grammar.voices) == (grammar.reflexive_marking == "affix")
        assert ("reciprocal" in grammar.voices) == (grammar.reciprocal_marking == "affix")


def test_affixes_exist_exactly_where_the_strategy_needs_them():
    for seed in range(1, 100):
        g = _language(seed).grammar
        assert bool(g.possessor_person_affixes) == (g.possessive_pronouns == "affix" or g.reflexive_possessive == "affix")
        expected = (list(pronoun_gen.PERSON_LABELS) if g.possessive_pronouns == "affix" else []) + (
            ["self"] if g.reflexive_possessive == "affix" else []
        )
        assert [a.label for a in g.possessor_person_affixes] == expected
        assert bool(g.verb_number_affixes) == g.verb_number_agreement
        assert bool(g.verb_polite_affixes) == g.verb_politeness
        if g.verb_politeness:
            assert g.honorific_you
        if g.object_pro_drop:
            assert g.object_agreement
            suffixes = [a.suffix for a in g.object_agreement_affixes if a.label in pronoun_gen.PERSON_LABELS]
            assert len(set(suffixes)) == 4


def test_grammar_defaults_keep_old_saved_languages_valid():
    fields = GrammarProfile.model_fields
    assert fields["reflexive_marking"].default == "none" and fields["reciprocal_marking"].default == "none"
    assert fields["possessive_pronouns"].default == "regular"
    assert not any(fields[f].default for f in ("verb_number_agreement", "verb_politeness", "object_pro_drop"))


def test_english_readings_of_the_new_words():
    assert pronoun_gen.english_reading("self") == "oneself"
    assert pronoun_gen.english_reading("each-other") == "each other"
    assert pronoun_gen.english_reading("possessive-i") == "my"
    assert pronoun_gen.english_reading("possessive-we-inclusive") == "our (inclusive)"
    assert pronoun_gen.english_reading("you-plural") == "you (plural)"
    assert pronoun_gen.english_reading("dog") == "dog"


# --- planning -------------------------------------------------------------


def test_parse_reads_the_new_fields_and_slot_kind():
    plan = sentence_planner._parse(
        '[{"kind": "possessive_pronoun", "gloss": "I"},'
        ' {"kind": "content", "gloss": "see", "pos": "verb", "subject_number": "plural", "polite": true}]'
    )
    assert plan is not None
    assert plan.slots[0].kind == "possessive_pronoun"
    assert plan.slots[1].subject_number == "plural" and plan.slots[1].polite is True


def test_the_prompt_describes_each_strategy():
    word = _find(lambda g: g.reflexive_marking == "word" and g.possessive_pronouns == "words")
    prompt = sentence_planner._build_system_prompt(word)
    assert 'gloss "self"' in prompt and '"kind":"possessive_pronoun"' in prompt
    affix = _find(lambda g: g.reflexive_marking == "affix" and g.reciprocal_marking == "affix")
    prompt = sentence_planner._build_system_prompt(affix)
    assert '"voice":"reflexive"' in prompt and '"voice":"reciprocal"' in prompt
    plain = _find(lambda g: g.possessive_pronouns == "regular" and not g.verb_number_agreement and not g.verb_politeness)
    prompt = sentence_planner._build_system_prompt(plain)
    assert 'as for any possessor' in prompt and "verbs here carry no number or politeness" in prompt
    rich = _find(lambda g: g.verb_number_agreement and g.verb_politeness)
    prompt = sentence_planner._build_system_prompt(rich)
    assert '"subject_number":"plural"' in prompt and '"polite":true' in prompt


_BASE = {"word_order": "SVO", "alignment": "nominative_accusative", "tenses": "past,non_past"}


def _plan(sentence: str, **meta) -> list[dict]:
    return _fake_plan_dict(sentence, {**_BASE, **meta})["slots"]


def test_the_fake_planner_plans_a_reflexive_per_strategy():
    word = _plan("He sees himself.", reflexive_marking="word")
    assert word[-1]["gloss"] == "self" and word[-1]["case"] == "accusative"
    affix = _plan("He sees himself.", reflexive_marking="affix")
    verb = next(s for s in affix if s.get("pos") == "verb")
    assert verb["voice"] == "reflexive" and len(affix) == 2
    none = _plan("He sees himself.", reflexive_marking="none")
    assert [s["gloss"] for s in none if s.get("pos") == "pronoun"] == ["he", "he"]


def test_the_fake_planner_plans_a_reciprocal_per_strategy():
    word = _plan("They see each other.", reciprocal_marking="word")
    assert word[-1]["gloss"] == "each-other"
    affix = _plan("They see one another.", reciprocal_marking="affix")
    assert next(s for s in affix if s.get("pos") == "verb")["voice"] == "reciprocal"
    none = _plan("They see each other.")
    assert [s["gloss"] for s in none if s.get("pos") == "pronoun"] == ["they", "they"]


def test_the_fake_planner_uses_possessive_pronoun_slots_where_the_language_has_them():
    words = _plan("I see my dog.", possessive_pronouns="words")
    assert {"kind": "possessive_pronoun", "gloss": "I"} in words
    regular = _plan("I see my dog.", possessive_pronouns="regular")
    assert {"kind": "content", "gloss": "I", "pos": "pronoun", "possessive": True} in regular


def test_the_fake_planner_sets_verb_number_and_politeness():
    plan = _plan("They see the river.", verb_number_agreement="true")
    assert next(s for s in plan if s.get("pos") == "verb")["subject_number"] == "plural"
    plan = _plan("The dogs see the river.", verb_number_agreement="true")
    assert next(s for s in plan if s.get("pos") == "verb")["subject_number"] == "plural"
    plan = _plan("He sees the river.", verb_number_agreement="true")
    assert "subject_number" not in next(s for s in plan if s.get("pos") == "verb")
    assert "subject_number" not in next(s for s in _plan("They see the river.") if s.get("pos") == "verb")


# --- reflexives and reciprocals, rendered ----------------------------------


def test_a_reflexive_word_is_an_object_pronoun_read_back_as_oneself():
    language = _find(lambda g: g.reflexive_marking == "word")
    updated, tokens, glosses = _render(language, _pronoun("he"), _verb(), _pronoun("self", case="accusative"))
    assert glosses[-1] == "self" and updated.lexicon.by_gloss("self") is not None
    assert "oneself" in translate_to_english(" ".join(tokens), updated, _CLIENT).text


def test_an_affix_reflexive_marks_the_verb_and_reads_back():
    language = _find(lambda g: g.reflexive_marking == "affix")
    form = _render(language, _verb(voice="reflexive"))[1][0]
    assert form != _render(language, _verb())[1][0]
    decoded = _decode_verb_full(language, form)
    assert decoded is not None and decoded[4] == "reflexive"
    assert "oneself" in translate_to_english(form, language, _CLIENT).text


def test_an_affix_reciprocal_marks_the_verb_and_reads_back():
    language = _find(lambda g: g.reciprocal_marking == "affix")
    form = _render(language, _verb(voice="reciprocal"))[1][0]
    decoded = _decode_verb_full(language, form)
    assert decoded is not None and decoded[4] == "reciprocal"
    assert "each other" in translate_to_english(form, language, _CLIENT).text


def test_a_reflexive_object_agrees_like_the_subject_where_the_verb_agrees_with_objects():
    language = _find(lambda g: g.reflexive_marking == "word" and g.object_agreement)
    with_self = _render(language, _verb(agreement="I", object_gloss="self"))[1][0]
    with_me = _render(language, _verb(agreement="I", object_gloss="me"))[1][0]
    assert with_self == with_me  # "self" takes the subject's own person label


# --- possessive pronouns, rendered -----------------------------------------


def test_possessive_words_are_coined_per_person_and_read_back():
    language = _find(lambda g: g.possessive_pronouns == "words" and not g.noun_classes)
    slot_i = PlannedSlot(kind="possessive_pronoun", gloss="I")
    slot_you = PlannedSlot(kind="possessive_pronoun", gloss="you")
    updated, mine, _ = _render(language, slot_i, _noun("dog"))
    _, yours, _ = _render(updated, slot_you, _noun("dog"))
    assert len(mine) == 2 and mine[0] != yours[0] and mine[1] == yours[1]
    assert updated.lexicon.by_gloss("possessive-i") is not None
    english = translate_to_english(" ".join(mine), updated, _CLIENT).text
    assert "my" in english.split()


def test_a_possessive_word_agrees_with_the_class_of_its_noun():
    language = _find(lambda g: g.possessive_pronouns == "words" and g.noun_classes == ("animate", "inanimate"))
    slot = PlannedSlot(kind="possessive_pronoun", gloss="I")
    of_dog = _render(language, slot, _noun("dog"))[1][0]
    of_river = _render(language, slot, _noun("river"))[1][0]
    assert of_dog != of_river


def test_a_person_suffix_marks_the_possessed_noun_and_decodes_back():
    language = _find(lambda g: g.possessive_pronouns == "affix" and g.possessor_person_affixes)
    forms = {}
    for person, gloss in (("I", "I"), ("you", "you"), ("he", "he"), ("we", "we")):
        tokens = _render(language, PlannedSlot(kind="possessive_pronoun", gloss=gloss), _noun("dog"))[1]
        assert len(tokens) == 1  # no separate possessive word
        forms[person] = tokens[0]
    bare = _render(language, _noun("dog"))[1][0]
    assert len(set(forms.values()) | {bare}) == 5
    dog = language.lexicon.by_gloss("dog")
    decoded = _decode_noun(language, forms["you"])
    assert decoded is not None and decoded[0] == dog and "poss:you" in decoded[1]


def test_a_regular_language_treats_a_possessive_pronoun_slot_as_a_pronoun_possessor():
    language = _find(lambda g: g.possessive_pronouns == "regular")
    via_slot = _render(language, PlannedSlot(kind="possessive_pronoun", gloss="I"), _noun("dog"))[1]
    via_flag = _render(language, _pronoun("I", possessive=True), _noun("dog"))[1]
    assert via_slot == via_flag


# --- verb number and politeness ---------------------------------------------


def test_verb_number_agreement_marks_a_plural_subject():
    language = _find(lambda g: g.verb_number_agreement)
    plain = _render(language, _verb())[1][0]
    plural = _render(language, _verb(subject_number="plural"))[1][0]
    assert plain != plural
    decoded = _decode_verb_full(language, plural)
    assert decoded is not None and decoded[7] == "plural"
    assert "subject: plural" in _annotation(language, plural)


def test_a_language_without_verb_number_ignores_it():
    language = _find(lambda g: not g.verb_number_agreement)
    assert _render(language, _verb(subject_number="plural"))[1] == _render(language, _verb())[1]


def test_verb_politeness_marks_a_polite_subject():
    language = _find(lambda g: g.verb_politeness)
    plain = _render(language, _verb(agreement="you"))[1][0]
    polite = _render(language, _verb(agreement="you", polite=True))[1][0]
    assert plain != polite
    decoded = _decode_verb_full(language, polite)
    assert decoded is not None and decoded[8] is True
    assert "polite" in _annotation(language, polite)


def test_number_and_politeness_combine():
    language = _find(lambda g: g.verb_politeness and g.verb_number_agreement)
    form = _render(language, _verb(agreement="you", polite=True, subject_number="plural"))[1][0]
    decoded = _decode_verb_full(language, form)
    assert decoded is not None and decoded[7] == "plural" and decoded[8] is True


def _annotation(language, token: str) -> str:
    """The annotated draft the fluency model would see for a lone verb token."""
    from conlang_generator.llm.base import LLMRequest  # noqa: F401 -- documents the request type

    class _Spy(FakeLLMClient):
        seen: list = []

        def complete(self, request):
            self.seen.append(request)
            return super().complete(request)

    spy = _Spy()
    spy.seen = []
    translate_to_english(token, language, spy)
    return next(r.prompt for r in spy.seen if r.purpose == "translate.fluency")


# --- object pro-drop ---------------------------------------------------------


def test_an_object_pronoun_is_omitted_in_an_object_pro_drop_language():
    language = _find(lambda g: g.object_pro_drop and g.alignment.value == "nominative_accusative")
    kept = language.model_copy(update={"grammar": language.grammar.model_copy(update={"object_pro_drop": False})})
    slots = (_pronoun("he"), _verb(agreement="he", object_gloss="you"), _pronoun("you", case="accusative"))
    assert len(_render(language, *slots)[1]) == len(_render(kept, *slots)[1]) - 1


def test_only_the_pronoun_named_by_object_agreement_is_dropped():
    language = _find(lambda g: g.object_pro_drop and g.alignment.value == "nominative_accusative")
    slots = (_pronoun("he"), _verb(agreement="he", object_gloss="you"), _pronoun("we", case="accusative"))
    assert len(_render(language, *slots)[1]) == 3


def test_a_dropped_object_is_read_back_from_the_verbs_object_agreement():
    language = _find(lambda g: g.object_pro_drop and g.alignment.value == "nominative_accusative")
    tokens = _render(language, _verb(agreement="he", object_gloss="you"))[1]
    decoded = _decode_verb_full(language, tokens[0])
    assert decoded is not None and decoded[6] == "you"
    assert "you" in translate_to_english(tokens[0], language, _CLIENT).text.split()


def test_an_object_pronoun_stays_where_the_language_does_not_drop_it():
    language = _find(lambda g: g.object_agreement and not g.object_pro_drop)
    slots = (_pronoun("he"), _verb(agreement="he", object_gloss="you"), _pronoun("you", case="accusative"))
    assert len(_render(language, *slots)[1]) == 3


def test_a_whole_sentence_still_round_trips_its_nouns():
    language = _find(lambda g: g.possessive_pronouns == "words" or g.reflexive_marking == "word")
    result = translate_to_conlang("I see my dog.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "dog" in english and "<unknown" not in english
