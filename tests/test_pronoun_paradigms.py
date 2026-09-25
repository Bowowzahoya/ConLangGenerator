"""Suppletive pronoun case forms (I/me/my), reflexive possessives ("his own")
and classifiers in possessive constructions."""

from conlang_generator.core.grammar import GrammarProfile
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import classifier_gen, pronoun_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient, _fake_plan_dict
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import _decode_noun, _render_plan, translate_to_english

_CLIENT = FakeLLMClient()
_CACHE: dict[int, object] = {}


def _language(seed: int):
    if seed not in _CACHE:
        _CACHE[seed] = generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())
    return _CACHE[seed]


def _find(predicate, limit: int = 400):
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


def _noun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="noun", **kw)


def _own() -> PlannedSlot:
    return PlannedSlot(kind="possessive_pronoun", gloss="self")


# --- generation -----------------------------------------------------------


def test_suppletion_is_rolled_for_a_subset_of_persons():
    grammars = [_language(s).grammar for s in range(1, 100)]
    with_suppletion = [g for g in grammars if g.suppletive_pronoun_persons]
    assert with_suppletion and len(with_suppletion) < len(grammars)
    for g in with_suppletion:
        assert set(g.suppletive_pronoun_persons) <= set(pronoun_gen.PERSON_LABELS)
    assert len({g.suppletive_pronoun_persons for g in with_suppletion}) > 2


def test_reflexive_possessives_and_possessive_classifiers_are_rolled():
    grammars = [_language(s).grammar for s in range(1, 200)]
    assert {g.reflexive_possessive for g in grammars} == {"word", "affix", "none"}
    classifier_languages = [g for g in grammars if g.uses_classifiers]
    assert {g.possessive_classifiers for g in classifier_languages} == {True, False}
    assert not any(g.possessive_classifiers for g in grammars if not g.uses_classifiers)


def test_grammar_defaults_keep_old_saved_languages_valid():
    fields = GrammarProfile.model_fields
    assert fields["suppletive_pronoun_persons"].default == ()
    assert fields["reflexive_possessive"].default == "none"
    assert fields["possessive_classifiers"].default is False


def test_suppletive_forms_are_named_and_read_back_in_english():
    assert pronoun_gen.suppletive_gloss("I", "accusative") == "i-accusative"
    assert pronoun_gen.suppletive_split("i-accusative") == ("i", "accusative")
    assert pronoun_gen.suppletive_split("you-plural-genitive") == ("you-plural", "genitive")
    assert pronoun_gen.suppletive_split("dog-accusative") is None
    assert pronoun_gen.suppletive_split("possessive-i") is None
    assert pronoun_gen.suppletive_reading("i", "accusative") == "me"
    assert pronoun_gen.suppletive_reading("he", "genitive") == "his"
    assert pronoun_gen.suppletive_reading("we", "dative") == "us"
    assert pronoun_gen.suppletive_reading("you", "accusative") == "you"
    assert pronoun_gen.english_reading("possessive-self") == "one's own"


# --- planning -------------------------------------------------------------


def test_the_prompt_describes_the_new_choices():
    suppletive = _find(lambda g: "I" in g.suppletive_pronoun_persons and g.reflexive_possessive == "word")
    prompt = sentence_planner._build_system_prompt(suppletive)
    assert "have case forms that are words of their own" in prompt
    assert '"gloss":"self"' in prompt and "the renderer picks the right word" in prompt
    plain = _find(lambda g: not g.suppletive_pronoun_persons and g.reflexive_possessive == "none")
    text = sentence_planner._build_system_prompt(plain)
    assert "personal pronouns take the ordinary case marking" in text
    assert "ordinary possessive of the subject's own person" in text
    classifier = _find(lambda g: g.possessive_classifiers)
    assert "possessive classifier that the renderer adds itself" in sentence_planner._build_system_prompt(classifier)
    assert "no classifier after a possessor" in text


def _plan(sentence: str, **meta) -> list[dict]:
    base = {"word_order": "SVO", "alignment": "nominative_accusative", "tenses": "past,non_past"}
    return _fake_plan_dict(sentence, {**base, **meta})["slots"]


def test_the_fake_planner_uses_the_reflexive_possessive_where_the_language_has_one():
    word = _plan("He sees his own dog.", reflexive_possessive="word")
    assert {"kind": "possessive_pronoun", "gloss": "self"} in word
    none = _plan("He sees his own dog.", reflexive_possessive="none")
    assert all(s.get("gloss") != "self" for s in none)
    assert any(s.get("possessive") for s in none)
    assert all(s.get("gloss") != "own" for s in word + none)  # "own" is not a word of its own


# --- suppletive pronouns, rendered -------------------------------------------


def test_a_suppletive_person_gets_a_word_of_its_own_in_a_marked_case():
    language = _find(lambda g: "I" in g.suppletive_pronoun_persons and "accusative" in g.cases)
    updated, tokens, glosses = _render(language, _pronoun("I", case="accusative"))
    assert glosses == ["i-accusative"] and updated.lexicon.by_gloss("i-accusative") is not None
    assert tokens != _render(language, _pronoun("I"))[1]
    english = translate_to_english(tokens[0], updated, _CLIENT).text
    assert english.strip() == "me"


def test_a_regular_person_keeps_the_case_suffix():
    language = _find(lambda g: "I" not in g.suppletive_pronoun_persons and g.suppletive_pronoun_persons and "accusative" in g.cases)
    _, _, glosses = _render(language, _pronoun("I", case="accusative"))
    assert glosses == ["I"]  # the plain pronoun, suffixed


def test_the_nominative_and_absolutive_are_never_suppletive():
    language = _find(lambda g: "I" in g.suppletive_pronoun_persons and "nominative" in g.cases)
    assert _render(language, _pronoun("I", case="nominative"))[2] == ["I"]
    assert _render(language, _pronoun("I"))[2] == ["I"]


def test_a_genitive_possessor_pronoun_uses_the_suppletive_genitive():
    language = _find(lambda g: "I" in g.suppletive_pronoun_persons and g.possession == "genitive" and "I" not in dict(g.suppletive_pronoun_case_limits))
    updated, tokens, glosses = _render(language, _pronoun("I", possessive=True), _noun("dog"))
    assert glosses[0] == "i-genitive" and len(tokens) == 2
    assert "my" in translate_to_english(tokens[0], updated, _CLIENT).text.split()


def test_a_language_without_suppletion_is_unchanged():
    language = _find(lambda g: not g.suppletive_pronoun_persons and "accusative" in g.cases)
    _, _, glosses = _render(language, _pronoun("I", case="accusative"))
    assert glosses == ["I"]


# --- reflexive possessives, rendered -------------------------------------------


def test_a_reflexive_possessive_word_is_its_own_lexicon_word():
    language = _find(lambda g: g.reflexive_possessive == "word" and not g.noun_classes and not g.possessive_classifiers)
    updated, tokens, glosses = _render(language, _own(), _noun("dog"))
    assert glosses[0] == "possessive-self" and len(tokens) == 2
    assert "one's own" in translate_to_english(" ".join(tokens), updated, _CLIENT).text


def test_a_reflexive_possessive_suffix_marks_the_noun_and_decodes_back():
    language = _find(lambda g: g.reflexive_possessive == "affix")
    tokens = _render(language, _own(), _noun("dog"))[1]
    assert len(tokens) == 1 and tokens[0] != _render(language, _noun("dog"))[1][0]
    decoded = _decode_noun(language, tokens[0])
    assert decoded is not None and "poss:self" in decoded[1]
    assert "his/her/its own" in _annotation(language, tokens[0])


def test_the_reflexive_possessive_suffix_differs_from_the_person_suffixes():
    language = _find(lambda g: g.reflexive_possessive == "affix" and g.possessive_pronouns == "affix")
    own = _render(language, _own(), _noun("dog"))[1][0]
    persons = {_render(language, PlannedSlot(kind="possessive_pronoun", gloss=g), _noun("dog"))[1][0] for g in ("I", "you", "he", "we")}
    assert own not in persons and len(persons) == 4


def test_a_language_without_a_reflexive_possessive_reads_own_as_the_ordinary_possessive():
    language = _find(lambda g: g.reflexive_possessive == "none" and g.possessive_pronouns == "regular")
    assert _render(language, _own(), _noun("dog"))[1] == _render(language, _pronoun("he", possessive=True), _noun("dog"))[1]


def _annotation(language, token: str) -> str:
    class _Spy(FakeLLMClient):
        def __init__(self) -> None:
            self.seen: list = []

        def complete(self, request):
            self.seen.append(request)
            return super().complete(request)

    spy = _Spy()
    translate_to_english(token, language, spy)
    return next(r.prompt for r in spy.seen if r.purpose == "translate.fluency")


# --- possessive classifiers -----------------------------------------------------


def test_a_classifier_follows_a_possessor_word_and_depends_on_the_possessed_noun():
    language = _find(
        lambda g: g.possessive_classifiers and {"animal", "long"} <= set(g.classifier_categories)
        and g.possession in ("genitive", "particle", "none") and g.classifier_assignment == "category"
    )
    possessor = _pronoun("I", possessive=True)
    updated, dog_tokens, dog_glosses = _render(language, possessor, _noun("dog"))
    _, river_tokens, river_glosses = _render(language, possessor, _noun("river"))
    dog_index = dog_glosses.index("possessive-classifier-animal")
    assert dog_index > 0 and dog_glosses[-1] == "dog"
    assert "possessive-classifier-long" in river_glosses
    assert dog_tokens[dog_index] != river_tokens[river_glosses.index("possessive-classifier-long")]
    english = translate_to_english(" ".join(dog_tokens), updated, _CLIENT).text
    assert "classifier" not in english and "dog" in english


def test_a_language_without_possessive_classifiers_adds_none():
    language = _find(lambda g: g.uses_classifiers and not g.possessive_classifiers)
    _, _, glosses = _render(language, _pronoun("I", possessive=True), _noun("dog"))
    assert not any(g.startswith("possessive-classifier-") for g in glosses)


def test_a_possessive_word_takes_a_classifier_too():
    language = _find(
        lambda g: g.possessive_classifiers and g.possessive_pronouns == "words" and not g.noun_classes
    )  # (any assignment: the classifier word is a possessive classifier either way)
    _, tokens, glosses = _render(language, PlannedSlot(kind="possessive_pronoun", gloss="I"), _noun("dog"))
    assert glosses[0] == "possessive-i" and glosses[1].startswith("possessive-classifier-") and len(tokens) == 3


def test_a_person_suffix_possessive_has_no_word_to_attach_a_classifier_to():
    language = _find(lambda g: g.possessive_classifiers and g.possessive_pronouns == "affix")
    _, tokens, glosses = _render(language, PlannedSlot(kind="possessive_pronoun", gloss="I"), _noun("dog"))
    assert len(tokens) == 1 and not any(g and g.startswith("possessive-classifier-") for g in glosses)


def test_the_possessive_classifier_words_are_not_numeral_classifier_words():
    assert classifier_gen.possessive_classifier_gloss("food") == "possessive-classifier-food"
    assert classifier_gen.possessive_classifier_gloss("food") != classifier_gen.classifier_gloss("food")
