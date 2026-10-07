"""Model choice per task (DEFERRED.md), and its web-UI counterpart (the
model picker): a selectable model for prompt classification, for word
selection/coinage (generation time and later translation-time reuse), and
for translation (sentence planning + fluency) -- previously `DEFAULT_MODEL`
was hard-wired into every one of this project's `LLMRequest` call sites,
with no override anywhere."""

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import real_words_llm, seed_examples
from conlang_generator.generation.lexicon_gen import propose_word
from conlang_generator.generation.prompt_classifier import classify_prompt
from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.llm import pricing
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.expansion import coin_word
from conlang_generator.translation.translator import translate_to_conlang, translate_to_english
from tests.factories import make_minimal_language

_CHOSEN_MODEL = "claude-sonnet-5"


class _Spy(FakeLLMClient):
    def __init__(self):
        self.seen: list = []

    def complete(self, request):
        self.seen.append(request)
        return super().complete(request)


# --- pricing -----------------------------------------------------------------


def test_estimated_price_is_positive_for_a_real_model_and_zero_for_fake():
    for task in ("classifier", "word_selection", "translation"):
        assert pricing.estimated_price("claude-haiku-4-5-20251001", task) > 0
        assert pricing.estimated_price("fake-llm", task) == 0.0


# --- GenerationSpec defaults and backward compatibility -----------------------


def test_generation_spec_model_fields_default_to_default_model():
    spec = GenerationSpec(prompt="p", seed=1)
    assert spec.classifier_model == pricing.DEFAULT_MODEL
    assert spec.word_selection_model == pricing.DEFAULT_MODEL


def test_an_older_saved_language_with_no_model_fields_loads_with_the_default():
    # Same regression guard this project always adds for a new field on an
    # existing model: an older saved language's own YAML simply lacks these
    # keys, and pydantic falls back to the field's own declared default --
    # confirmed directly on the model, the same way test_topic.py's own
    # "defaults for older saved languages" test already does for a
    # differently-shaped new field.
    assert GenerationSpec.model_fields["classifier_model"].default == pricing.DEFAULT_MODEL
    assert GenerationSpec.model_fields["word_selection_model"].default == pricing.DEFAULT_MODEL


# --- the model string actually reaches the LLMRequest, for every task --------


def test_classify_prompt_sends_the_chosen_model():
    spy = _Spy()
    classify_prompt("a language", False, spy, model=_CHOSEN_MODEL)
    assert spy.seen[0].model == _CHOSEN_MODEL


def test_resolve_seed_examples_sends_the_chosen_model():
    from conlang_generator.core.spec import SeedExample

    spy = _Spy()
    seed_examples.resolve_seed_examples((SeedExample(gloss="dog", form="dog"),), spy, model=_CHOSEN_MODEL)
    assert spy.seen and all(r.model == _CHOSEN_MODEL for r in spy.seen)


def test_fetch_real_words_sends_the_chosen_model():
    spy = _Spy()
    real_words_llm.fetch_real_words([("Dutch", "king", PartOfSpeech.NOUN)], spy, model=_CHOSEN_MODEL)
    assert spy.seen and spy.seen[0].model == _CHOSEN_MODEL


def test_propose_word_sends_the_chosen_model_under_llm_word_selection():
    import random

    language = make_minimal_language()
    spy = _Spy()
    propose_word(
        random.Random(1), language.phonology, language.syllable_structure, language.tone_system,
        language.word_accent, language.romanization, "fish", PartOfSpeech.NOUN, spy, language.name,
        word_selection="llm", model=_CHOSEN_MODEL,
    )
    assert spy.seen and spy.seen[0].model == _CHOSEN_MODEL


def test_coin_word_reads_word_selection_model_off_the_language_spec():
    language = make_minimal_language()
    language = language.model_copy(update={
        "spec": language.spec.model_copy(update={"word_selection": "llm", "word_selection_model": _CHOSEN_MODEL})
    })
    spy = _Spy()
    coin_word(language, "fish", PartOfSpeech.NOUN, spy)
    assert spy.seen and any(r.model == _CHOSEN_MODEL for r in spy.seen)


def test_plan_sentence_sends_the_chosen_model():
    language = make_minimal_language()
    spy = _Spy()
    sentence_planner.plan_sentence("I see the mountain", language, spy, model=_CHOSEN_MODEL)
    assert spy.seen and spy.seen[0].model == _CHOSEN_MODEL


def test_translate_to_conlang_forwards_the_chosen_model_to_the_planner():
    language = make_minimal_language()
    spy = _Spy()
    translate_to_conlang("I see the mountain", language, spy, model=_CHOSEN_MODEL)
    plan_requests = [r for r in spy.seen if r.purpose == "translate.plan_sentence"]
    assert plan_requests and all(r.model == _CHOSEN_MODEL for r in plan_requests)


def test_translate_to_english_sends_the_chosen_model_for_fluency():
    language = make_minimal_language()
    spy = _Spy()
    translate_to_english("pa ti", language, spy, model=_CHOSEN_MODEL)
    fluency_requests = [r for r in spy.seen if r.purpose == "translate.fluency"]
    assert fluency_requests and fluency_requests[0].model == _CHOSEN_MODEL


def test_default_model_is_used_when_no_model_is_given():
    # Regression guard: every new parameter is additive -- an existing
    # caller that never passes `model` keeps using DEFAULT_MODEL exactly
    # as before this feature.
    language = make_minimal_language()
    spy = _Spy()
    translate_to_conlang("I see the mountain", language, spy)
    plan_requests = [r for r in spy.seen if r.purpose == "translate.plan_sentence"]
    assert plan_requests and all(r.model == pricing.DEFAULT_MODEL for r in plan_requests)


# --- CLI ----------------------------------------------------------------------


def test_cli_generate_prints_and_persists_the_chosen_models(tmp_path, monkeypatch):
    import conlang_generator.cli.main as cli_main
    from typer.testing import CliRunner

    monkeypatch.setattr(cli_main, "LANGUAGES_DIR", tmp_path / "conlangs")
    monkeypatch.setattr(cli_main, "CACHE_DIR", tmp_path / "cache")
    result = CliRunner().invoke(
        cli_main.app,
        [
            "generate", "--prompt", "p", "--name", "cli-model-test", "--seed", "1", "--llm", "fake",
            "--model", "claude-sonnet-5", "--word-model", "claude-opus-5",
        ],
    )
    assert result.exit_code == 0
    assert "Models: classifier=claude-sonnet-5, word selection=claude-opus-5" in result.output

    from conlang_generator.storage.yaml_backend import YamlLanguageRepository

    language = YamlLanguageRepository(cli_main.LANGUAGES_DIR).load("cli-model-test")
    assert language.spec.classifier_model == "claude-sonnet-5"
    assert language.spec.word_selection_model == "claude-opus-5"


def test_cli_translate_accepts_a_translate_model_flag(tmp_path, monkeypatch):
    import conlang_generator.cli.main as cli_main
    from typer.testing import CliRunner

    monkeypatch.setattr(cli_main, "LANGUAGES_DIR", tmp_path / "conlangs")
    monkeypatch.setattr(cli_main, "CACHE_DIR", tmp_path / "cache")
    language = make_minimal_language()
    from conlang_generator.storage.yaml_backend import YamlLanguageRepository

    YamlLanguageRepository(cli_main.LANGUAGES_DIR).save(language.model_copy(update={"name": "cli-translate-model"}))
    result = CliRunner().invoke(
        cli_main.app,
        [
            "translate", "I see the mountain", "--lang", "cli-translate-model", "--to", "conlang",
            "--llm", "fake", "--translate-model", "claude-sonnet-5",
        ],
    )
    assert result.exit_code == 0
