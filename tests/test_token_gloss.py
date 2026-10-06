"""Hover/click gloss in the translation result: ``translate_to_conlang``
exposes per-rendered-word data (``TranslationResult.tokens``, a tuple of
``TokenGloss``) so a UI can show each word's English gloss, part of
speech, whether it was newly coined this call, and its real-word origin
on hover/click. Scope: the conlang-rendering direction only (see
``test_translate_to_english_never_populates_tokens`` for why); the
*gloss/POS/coined/real-word* data is static per entry, not the live
case/tense/mood/degree marking actually applied this occurrence (no
uniform mechanism for that exists in ``_render_plan`` today -- see
``docs/DEFERRED.md``)."""

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import _render_plan, translate_to_conlang, translate_to_english
from tests._shared_language import cached_language

_CLIENT = FakeLLMClient()
_SEED = 278  # SVO, nominative-accusative; core vocabulary has mountain/see/river


def _language(seed: int = _SEED):
    return cached_language(seed)


def _find_question_particle_language(limit: int = 300):
    for seed in range(1, limit):
        language = _language(seed)
        if language.grammar.question_particle:
            return language
    raise AssertionError("no seed found with a question particle")


def _real_word_language():
    traits = TraitProfile(source_languages=("Dutch",), source_language_strictness=1.0, source_word_strictness=1.0)
    return generate_language("RealWordTest", GenerationSpec(prompt="p", seed=3, traits=traits), FakeLLMClient())


def test_render_plan_entries_align_one_to_one_with_romanization_parts():
    language = _language()
    subject = PlannedSlot(kind="content", gloss="I", pos="pronoun")
    verb = PlannedSlot(kind="content", gloss="see", pos="verb")
    obj = PlannedSlot(kind="content", gloss="mountain", pos="noun")
    _, romanized, _, _, entries = _render_plan(
        SentencePlan(slots=(subject, verb, obj)), language, _CLIENT, []
    )
    assert len(entries) == len(romanized)
    glosses = {e.primary_gloss for e in entries if e is not None}
    assert {"I", "see", "mountain"} <= glosses


def test_render_plan_entries_cover_nested_clause_sites():
    # A subordinate clause slot (kind="clause") extends `entries` via a
    # dedicated recursive code path distinct from the plain main-word
    # append site -- make sure it's covered too, not just the common case.
    language = _language()
    nested = SentencePlan(slots=(
        PlannedSlot(kind="content", gloss="I", pos="pronoun"),
        PlannedSlot(kind="content", gloss="see", pos="verb"),
        PlannedSlot(kind="content", gloss="mountain", pos="noun"),
    ))
    clause_slot = PlannedSlot(kind="clause", role="complement", clause=nested)
    main_subject = PlannedSlot(kind="content", gloss="I", pos="pronoun")
    main_verb = PlannedSlot(kind="content", gloss="know", pos="verb", tense="past")
    _, romanized, _, _, entries = _render_plan(
        SentencePlan(slots=(main_subject, main_verb, clause_slot)), language, _CLIENT, []
    )
    assert len(entries) == len(romanized)
    glosses = {e.primary_gloss for e in entries if e is not None}
    assert {"I", "know", "see", "mountain"} <= glosses


def test_coined_flag_true_for_a_newly_coined_word_false_for_an_existing_one():
    language = _language()
    assert language.lexicon.by_gloss("king") is None  # outside the default vocabulary
    result = translate_to_conlang("I see the king", language, FakeLLMClient())
    by_gloss = {t.gloss: t for t in result.tokens if t.gloss}
    assert by_gloss["king"].coined is True
    assert by_gloss["see"].coined is False
    assert by_gloss["the"].coined is False


def test_real_word_field_set_for_a_real_word_sourced_token():
    language = _real_word_language()
    assert language.lexicon.by_gloss("king") is None  # excluded from the default vocabulary, coined on the fly
    result = translate_to_conlang("I see the king", language, FakeLLMClient())
    by_gloss = {t.gloss: t for t in result.tokens if t.gloss}
    assert by_gloss["king"].real_word == "Dutch"
    assert by_gloss["king"].notes.startswith("real")


def test_token_surface_count_matches_text_split_for_every_mood():
    language = _language()
    declarative = translate_to_conlang("I see the mountain", language, FakeLLMClient())
    question = translate_to_conlang("Do you see the mountain?", language, FakeLLMClient())
    imperative = translate_to_conlang("See the mountain!", language, FakeLLMClient())
    for result in (declarative, question, imperative):
        assert len(result.tokens) == len(result.text.split())
        assert [t.surface for t in result.tokens] == result.text.split()


def test_multi_sentence_translate_token_count_and_mark_placement():
    language = _language()
    result = translate_to_conlang("I see the mountain. Do you see the river?", language, FakeLLMClient())
    words = result.text.split()
    assert len(result.tokens) == len(words)
    assert [t.surface for t in result.tokens] == words
    # The first sentence's own mark ("." ) lands on its own last token, not
    # on the second sentence's first token.
    first_sentence_len = len(translate_to_conlang("I see the mountain", language, FakeLLMClient()).text.split())
    assert result.tokens[first_sentence_len - 1].surface.endswith(".")
    assert not result.tokens[first_sentence_len].surface.endswith(".")


def test_bare_particle_token_has_no_gloss_pos_or_real_word():
    language = _find_question_particle_language()
    result = translate_to_conlang("Do you see the mountain?", language, FakeLLMClient())
    particle_tokens = [t for t in result.tokens if t.gloss is None]
    assert particle_tokens  # the question particle itself rendered as a token
    assert all(t.pos is None and t.real_word is None and t.notes == "" and t.coined is False for t in particle_tokens)


def test_translate_to_english_never_populates_tokens():
    language = _language()
    conlang_result = translate_to_conlang("I see the mountain", language, FakeLLMClient())
    result = translate_to_english(conlang_result.text, language, FakeLLMClient())
    assert result.tokens == ()


def test_cli_prints_a_glosses_line_for_conlang_direction_only(tmp_path, monkeypatch):
    import conlang_generator.cli.main as cli_main
    from typer.testing import CliRunner

    from conlang_generator.storage.yaml_backend import YamlLanguageRepository

    monkeypatch.setattr(cli_main, "LANGUAGES_DIR", tmp_path / "conlangs")
    monkeypatch.setattr(cli_main, "CACHE_DIR", tmp_path / "cache")
    language = _language()
    YamlLanguageRepository(cli_main.LANGUAGES_DIR).save(language.model_copy(update={"name": "cli-token-gloss-test"}))

    to_conlang = CliRunner().invoke(
        cli_main.app, ["translate", "I see the king", "--lang", "cli-token-gloss-test", "--to", "conlang"]
    )
    assert to_conlang.exit_code == 0
    assert "Glosses: " in to_conlang.output
    assert "(king*)" in to_conlang.output  # coined this call

    to_english = CliRunner().invoke(
        cli_main.app, ["translate", "I see the king", "--lang", "cli-token-gloss-test", "--to", "english"]
    )
    assert to_english.exit_code == 0
    assert "Glosses: " not in to_english.output
