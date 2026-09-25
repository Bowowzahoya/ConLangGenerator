"""Noun classes and agreement: class systems, derived noun classes, article/
adjective/verb agreement, object agreement, and decoding."""

from conlang_generator.core.grammar import GrammarProfile
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import inflection_gen, noun_class_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.translator import (
    _article_forms,
    _decode_adjective,
    _decode_verb_full,
    translate_to_conlang,
    translate_to_english,
)

_CLIENT = FakeLLMClient()
_CACHE: dict[int, object] = {}


def _language(seed: int):
    if seed not in _CACHE:
        _CACHE[seed] = generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())
    return _CACHE[seed]


def _find(predicate, limit: int = 200):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language.grammar):
            return language
    raise AssertionError("no seed found")


def _animacy_language(object_agreement: bool | None = None):
    return _find(
        lambda g: g.noun_classes == ("animate", "inanimate")
        and g.has_articles
        and (object_agreement is None or g.object_agreement is object_agreement)
    )


def _tokens(language, sentence: str) -> list[str]:
    return translate_to_conlang(sentence, language, _CLIENT).text.split()


def _verb_token(language, sentence: str) -> str:
    stem = language.lexicon.by_gloss("see").romanization[:2]
    return next(t for t in _tokens(language, sentence) if t.startswith(stem))


# --- generation -----------------------------------------------------------


def test_class_systems_and_object_agreement_are_rolled_from_the_defined_sets():
    seen_systems, seen_object = set(), set()
    for seed in range(1, 60):
        grammar = _language(seed).grammar
        assert grammar.noun_classes in noun_class_gen.NOUN_CLASS_SYSTEMS
        seen_systems.add(grammar.noun_classes)
        seen_object.add(grammar.object_agreement)
    assert seen_systems == set(noun_class_gen.NOUN_CLASS_SYSTEMS)
    assert seen_object == {True, False}


def test_a_class_language_gets_class_affixes_and_class_subject_agreement_labels():
    grammar = _find(lambda g: bool(g.noun_classes)).grammar
    assert [a.label for a in grammar.class_affixes] == list(grammar.noun_classes)
    labels = [a.label for a in grammar.agreement_affixes]
    assert labels[: len(inflection_gen.AGREEMENT_LABELS)] == list(inflection_gen.AGREEMENT_LABELS)
    assert labels[len(inflection_gen.AGREEMENT_LABELS):] == [f"class:{c}" for c in grammar.noun_classes]


def test_object_agreement_affixes_cover_persons_and_classes_only_when_enabled():
    with_object = _find(lambda g: g.object_agreement and bool(g.noun_classes)).grammar
    labels = [a.label for a in with_object.object_agreement_affixes]
    assert labels == ["I", "you", "he", "we"] + [f"class:{c}" for c in with_object.noun_classes]
    without = _find(lambda g: not g.object_agreement).grammar
    assert without.object_agreement_affixes == ()


def test_classless_language_gets_no_class_affixes():
    grammar = _find(lambda g: not g.noun_classes).grammar
    assert grammar.class_affixes == ()
    assert [a.label for a in grammar.agreement_affixes] == list(inflection_gen.AGREEMENT_LABELS)


def test_class_generation_is_reproducible():
    a, b = _language(9), _language(9)
    assert a.grammar.noun_classes == b.grammar.noun_classes
    assert a.grammar.class_affixes == b.grammar.class_affixes


def test_grammar_defaults_keep_old_saved_languages_valid():
    fields = GrammarProfile.model_fields
    assert fields["noun_classes"].default == ()
    assert fields["class_affixes"].default == ()
    assert fields["object_agreement"].default is False
    assert fields["object_agreement_affixes"].default == ()


# --- derived noun classes -------------------------------------------------


def test_natural_gender_and_animacy_go_to_the_obvious_class():
    gender = ("masculine", "feminine", "neuter")
    assert noun_class_gen.noun_class(gender, 1, "man") == "masculine"
    assert noun_class_gen.noun_class(gender, 1, "mother") == "feminine"
    animacy = ("animate", "inanimate")
    assert noun_class_gen.noun_class(animacy, 1, "dog") == "animate"
    assert noun_class_gen.noun_class(animacy, 1, "child") == "animate"
    assert noun_class_gen.noun_class(animacy, 1, "river") == "inanimate"
    four = ("human", "animal", "plant", "thing")
    assert [noun_class_gen.noun_class(four, 1, w) for w in ("teacher", "wolf", "tree", "river")] == [
        "human", "animal", "plant", "thing",
    ]


def test_other_nouns_get_a_stable_class_within_the_system():
    gender = ("masculine", "feminine")
    first = noun_class_gen.noun_class(gender, 5, "river")
    assert first in gender
    assert first == noun_class_gen.noun_class(gender, 5, "River ")
    assert noun_class_gen.noun_class((), 5, "river") is None
    classes = {noun_class_gen.noun_class(gender, 5, w) for w in ("river", "stone", "cloud", "salt", "road", "wall")}
    assert classes == set(gender)  # the hash spreads nouns over both classes


# --- planning -------------------------------------------------------------


def test_parse_reads_the_agreement_fields():
    plan = sentence_planner._parse(
        '[{"kind": "content", "gloss": "high", "pos": "adjective", "agrees_with": " Dog "},'
        ' {"kind": "content", "gloss": "see", "pos": "verb", "subject_gloss": "Dog", "object_gloss": "river"}]'
    )
    assert plan is not None
    assert plan.slots[0].agrees_with == "dog"
    assert plan.slots[1].subject_gloss == "dog" and plan.slots[1].object_gloss == "river"


def test_the_prompt_lists_this_languages_classes_and_object_agreement():
    language = _find(lambda g: g.noun_classes == ("masculine", "feminine") and g.object_agreement)
    prompt = sentence_planner._build_system_prompt(language)
    assert "masculine, feminine" in prompt
    assert "also agrees with its direct object: yes" in prompt
    plain = sentence_planner._build_system_prompt(_find(lambda g: not g.noun_classes and not g.object_agreement))
    assert 'never set "agrees_with"' in plain
    assert 'never set "object_gloss"' in plain


# --- rendering and decoding -----------------------------------------------


def test_the_article_agrees_with_the_class_of_the_next_noun():
    language = _animacy_language()
    forms = _article_forms(language)
    articles = [t for t in _tokens(language, "the dog sees the river") if t.lower() in forms]
    assert len(articles) == 2
    assert articles[0] != articles[1]  # an animate noun and an inanimate one
    assert len(forms) == 3  # bare "the" plus one form per class


def test_articles_are_dropped_on_the_way_back_to_english():
    language = _animacy_language()
    text = translate_to_conlang("the dog sees the river", language, _CLIENT).text
    english = translate_to_english(text, language, _CLIENT).text
    assert "dog" in english and "river" in english
    assert "<unknown" not in english


def test_an_adjective_agrees_with_its_subjects_class_and_decodes_back():
    language = _animacy_language()
    high = language.lexicon.by_gloss("high")
    stem = high.romanization[:2]

    def adjective(sentence: str) -> str:
        return next(t for t in _tokens(language, sentence) if t.startswith(stem))

    of_dog, of_river = adjective("the dog is high"), adjective("the river is high")
    assert of_dog != of_river
    assert _decode_adjective(language, of_dog) == (high, "animate")
    assert _decode_adjective(language, of_river) == (high, "inanimate")


def test_the_verb_agrees_with_a_noun_subjects_class():
    language = _animacy_language()
    assert _verb_token(language, "the dog sees you") != _verb_token(language, "the river sees you")
    see = language.lexicon.by_gloss("see")
    decoded = _decode_verb_full(language, _verb_token(language, "the dog sees you"))
    assert decoded is not None and decoded[0] == see


def test_a_pronoun_subject_keeps_person_agreement():
    language = _animacy_language()
    assert _verb_token(language, "I see you") != _verb_token(language, "the dog sees you")


def test_object_agreement_marks_the_verb_by_its_objects_class_or_person():
    language = _animacy_language(object_agreement=True)
    with_dog = _verb_token(language, "I see the dog")
    with_river = _verb_token(language, "I see the river")
    with_you = _verb_token(language, "I see you")
    assert len({with_dog, with_river, with_you}) == 3
    see = language.lexicon.by_gloss("see")
    for form in (with_dog, with_river, with_you):
        decoded = _decode_verb_full(language, form)
        assert decoded is not None and decoded[0] == see


def test_without_object_agreement_the_object_does_not_change_the_verb():
    language = _animacy_language(object_agreement=False)
    assert _verb_token(language, "I see the dog") == _verb_token(language, "I see the river")


def test_a_language_without_classes_leaves_the_article_bare():
    language = _find(
        lambda g: not g.noun_classes and g.has_articles
        and "article" not in g.number_agreement_targets and "article" not in g.case_agreement_targets
    )
    bare = language.lexicon.by_gloss("the").romanization
    assert _tokens(language, "the dog sees the river")[0] == bare
    assert _article_forms(language) == {bare.lower()}
