"""Tests for translation.translator's real-inflection application (Stage 4:
real articles, an overt copula with tense/agreement marking, and case
marking under both alignments) and its generate-and-compare decoding back
out again (Stage 5)."""

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation.translator import translate_to_conlang, translate_to_english

# seed=2 (default traits): has_articles=True, has_overt_copula=True,
# cases=("nominative", "accusative"), alignment=nominative_accusative,
# word_order=SVO, adjective_after_noun=True -- every core word this file's
# own tests need is already core vocabulary at this seed (translate_to_
# conlang never needs to coin anything, confirmed via `.coined == ()`
# below), so these tests stay fully deterministic with no LLM involved.
_NOM_ACC_SEED = 2

# seed=8 (default traits): alignment=ergative_absolutive,
# cases=("ergative", "absolutive"), word_order=SOV -- same "no coinage
# needed" property.
_ERGATIVE_SEED = 8

# seed=4 (default traits): has_articles=False, has_overt_copula=False,
# cases=() -- the "none of these features exist" baseline, confirming
# nothing spurious gets inserted when a language genuinely lacks them.
_NO_FEATURES_SEED = 4


def _language(seed: int):
    return generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())


def test_nom_acc_language_has_the_expected_grammar_shape():
    # Pins down this file's own fixture assumptions -- if a future change
    # shifts seed=2's own rolled grammar, this fails first and clearly,
    # rather than the more specific tests below failing for a confusing
    # reason.
    grammar = _language(_NOM_ACC_SEED).grammar
    assert grammar.has_articles is True
    assert grammar.has_overt_copula is True
    assert grammar.cases == ("nominative", "accusative")
    assert grammar.alignment.value == "nominative_accusative"


def test_article_is_inserted_before_a_non_pronoun_noun_when_has_articles():
    language = _language(_NOM_ACC_SEED)
    the_entry = language.lexicon.by_gloss("the")
    mountain_entry = language.lexicon.by_gloss("mountain")
    result = translate_to_conlang("the mountain is high", language, FakeLLMClient())
    assert result.coined == ()
    words = result.text.split()
    assert words[0] == the_entry.romanization
    assert words[1] == mountain_entry.romanization


def test_article_never_prefixes_a_pronoun_subject():
    language = _language(_NOM_ACC_SEED)
    the_entry = language.lexicon.by_gloss("the")
    i_entry = language.lexicon.by_gloss("I")
    result = translate_to_conlang("I see the mountain", language, FakeLLMClient())
    assert result.coined == ()
    words = result.text.split()
    assert words[0] == i_entry.romanization  # "I" itself, never preceded by "the"
    assert the_entry.romanization in words  # the object still gets its own article


def test_no_article_or_copula_inserted_when_the_language_lacks_them():
    language = _language(_NO_FEATURES_SEED)
    grammar = language.grammar
    assert grammar.has_articles is False
    assert grammar.has_overt_copula is False
    the_entry = language.lexicon.by_gloss("the")
    be_entry = language.lexicon.by_gloss("be")
    assert the_entry is None and be_entry is None  # never coined at all
    result = translate_to_conlang("the mountain is high", language, FakeLLMClient())
    assert result.coined == ()
    assert len(result.text.split()) == 2  # just subject + adjective, no article, no copula


def test_overt_copula_is_inserted_between_subject_and_adjective():
    language = _language(_NOM_ACC_SEED)
    mountain_entry = language.lexicon.by_gloss("mountain")
    high_entry = language.lexicon.by_gloss("high")
    result = translate_to_conlang("the mountain is high", language, FakeLLMClient())
    words = result.text.split()
    assert len(words) == 4  # the, mountain, copula, high
    assert words[1] == mountain_entry.romanization
    assert words[3] == high_entry.romanization
    copula_word = words[2]
    assert copula_word != language.lexicon.by_gloss("be").romanization  # tense/agreement-marked, not the bare form


def test_copula_tense_marking_differs_between_present_and_past_input():
    language = _language(_NOM_ACC_SEED)
    present = translate_to_conlang("the mountain is high", language, FakeLLMClient())
    past = translate_to_conlang("the mountain was high", language, FakeLLMClient())
    present_copula = present.text.split()[2]
    past_copula = past.text.split()[2]
    assert present_copula != past_copula


def test_object_gets_accusative_case_marking_under_nominative_accusative_alignment():
    language = _language(_NOM_ACC_SEED)
    mountain_entry = language.lexicon.by_gloss("mountain")
    result = translate_to_conlang("I see the mountain", language, FakeLLMClient())
    assert result.coined == ()
    words = result.text.split()
    # word_order is SVO at this seed -- subject, verb, then the
    # article-prefixed, case-marked object.
    object_word = words[-1]
    assert object_word != mountain_entry.romanization  # accusative-marked, not the bare citation form


def test_subject_is_unmarked_under_nominative_accusative_alignment():
    language = _language(_NOM_ACC_SEED)
    i_entry = language.lexicon.by_gloss("I")
    result = translate_to_conlang("I see the mountain", language, FakeLLMClient())
    words = result.text.split()
    assert words[0] == i_entry.romanization  # bare -- nominative stays zero-marked


def test_ergative_language_has_the_expected_grammar_shape():
    grammar = _language(_ERGATIVE_SEED).grammar
    assert grammar.alignment.value == "ergative_absolutive"
    assert grammar.cases == ("ergative", "absolutive")


def test_subject_gets_ergative_case_marking_under_ergative_absolutive_alignment():
    language = _language(_ERGATIVE_SEED)
    i_entry = language.lexicon.by_gloss("I")
    result = translate_to_conlang("I see the mountain", language, FakeLLMClient())
    assert result.coined == ()
    words = result.text.split()
    assert words[0] != i_entry.romanization  # ergative-marked, not the bare pronoun


def test_translation_is_deterministic_for_the_same_input():
    language = _language(_NOM_ACC_SEED)
    first = translate_to_conlang("I see the mountain", language, FakeLLMClient())
    second = translate_to_conlang("I see the mountain", language, FakeLLMClient())
    assert first.text == second.text
    assert first.ipa == second.ipa


# --- Stage 5: decoding real inflection back out (translate_to_english) ---


def test_predicate_adjective_with_copula_round_trips_present_tense():
    language = _language(_NOM_ACC_SEED)
    to_conlang = translate_to_conlang("the mountain is high", language, FakeLLMClient())
    back = translate_to_english(to_conlang.text, to_conlang.language, FakeLLMClient())
    assert back.pattern == "predicate-adjective"
    assert "mountain" in back.text.lower()
    assert "high" in back.text.lower()
    assert "is" in back.text.lower()


def test_predicate_adjective_with_copula_round_trips_past_tense():
    language = _language(_NOM_ACC_SEED)
    to_conlang = translate_to_conlang("the mountain was high", language, FakeLLMClient())
    back = translate_to_english(to_conlang.text, to_conlang.language, FakeLLMClient())
    assert back.pattern == "predicate-adjective"
    assert "was" in back.text.lower()


def test_svo_with_accusative_object_round_trips_and_disambiguates_from_copula_pattern():
    # The 3-token copula-vs-SVO ambiguity this module's own docstring
    # describes: has_overt_copula is true for this fixture language too,
    # so this confirms the copula hypothesis correctly fails (the middle
    # token isn't "be") and falls through to the real transitive reading.
    language = _language(_NOM_ACC_SEED)
    to_conlang = translate_to_conlang("I see the mountain", language, FakeLLMClient())
    back = translate_to_english(to_conlang.text, to_conlang.language, FakeLLMClient())
    assert back.pattern == "subject-verb-object"
    assert back.text.lower().split() == ["i", "see", "mountain"]


def test_svo_round_trips_past_tense_with_irregular_verb():
    language = _language(_NOM_ACC_SEED)
    to_conlang = translate_to_conlang("I saw the mountain", language, FakeLLMClient())
    back = translate_to_english(to_conlang.text, to_conlang.language, FakeLLMClient())
    assert back.pattern == "subject-verb-object"
    assert back.text.lower().split() == ["i", "saw", "mountain"]


def test_ergative_language_svo_round_trips_with_ergative_marked_subject():
    language = _language(_ERGATIVE_SEED)
    to_conlang = translate_to_conlang("I see the mountain", language, FakeLLMClient())
    back = translate_to_english(to_conlang.text, to_conlang.language, FakeLLMClient())
    assert back.pattern == "subject-verb-object"
    assert back.text.lower().split() == ["i", "see", "mountain"]


def test_no_features_language_predicate_adjective_still_round_trips():
    language = _language(_NO_FEATURES_SEED)
    to_conlang = translate_to_conlang("the mountain is high", language, FakeLLMClient())
    back = translate_to_english(to_conlang.text, to_conlang.language, FakeLLMClient())
    assert back.pattern == "predicate-adjective"
    assert "mountain" in back.text.lower()
    assert "high" in back.text.lower()
