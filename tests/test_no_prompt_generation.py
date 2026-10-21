"""Generating a language with no prompt text at all, from traits/seed words/other explicit overrides
alone (`docs/DEFERRED.md` ch. 14, direct user request): `GenerationSpec.prompt` is optional (default
``""``), and a blank prompt skips `prompt_classifier.classify_prompt`'s own LLM call entirely (see
that function's own docstring) -- `tests/test_prompt_classifier.py` already covers that unit directly;
this file covers the two real entry points (CLI, webui) that used to block it."""

import pytest
from typer.testing import CliRunner

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.storage.yaml_backend import YamlLanguageRepository

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from conlang_generator.webui import app as webui_app  # noqa: E402


def test_generation_spec_prompt_defaults_to_blank():
    spec = GenerationSpec(seed=1)
    assert spec.prompt == ""


def test_cli_generate_succeeds_with_no_prompt_flag_at_all(tmp_path, monkeypatch):
    import conlang_generator.cli.main as cli_main

    monkeypatch.setattr(cli_main, "LANGUAGES_DIR", tmp_path / "conlangs")
    monkeypatch.setattr(cli_main, "CACHE_DIR", tmp_path / "cache")
    result = CliRunner().invoke(
        cli_main.app,
        ["generate", "--name", "no-prompt-cli", "--seed", "1", "--llm", "fake", "--vocabulary-size", "8"],
    )
    assert result.exit_code == 0, result.output
    repo = YamlLanguageRepository(tmp_path / "conlangs")
    language = repo.load("no-prompt-cli")
    assert language.spec.prompt == ""


def test_webui_generate_accepts_a_blank_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(webui_app, "CACHE_DIR", tmp_path / ".cache")
    monkeypatch.setattr(webui_app, "LANGUAGES_DIR", tmp_path / "conlangs")
    client = TestClient(webui_app.app)
    response = client.post(
        "/api/generate",
        json={"prompt": "", "name": "no-prompt-web", "seed": 1, "llm": "fake", "vocabulary_size": 8},
    )
    assert response.status_code == 200, response.text
    repo = YamlLanguageRepository(tmp_path / "conlangs")
    language = repo.load("no-prompt-web")
    assert language.spec.prompt == ""


def test_webui_generate_with_no_prompt_key_in_the_body_at_all(tmp_path, monkeypatch):
    # Confirms `prompt` is a genuinely optional JSON field, not just one FastAPI happens to accept
    # an empty string for.
    monkeypatch.setattr(webui_app, "CACHE_DIR", tmp_path / ".cache")
    monkeypatch.setattr(webui_app, "LANGUAGES_DIR", tmp_path / "conlangs")
    client = TestClient(webui_app.app)
    response = client.post(
        "/api/generate", json={"name": "no-prompt-key-web", "seed": 1, "llm": "fake", "vocabulary_size": 8},
    )
    assert response.status_code == 200, response.text


def test_an_explicit_trait_override_still_applies_with_no_prompt():
    # The whole point of allowing a blank prompt: explicit overrides and normal unconditioned rolls
    # still fully drive generation -- nothing downstream special-cases "no prompt" into "no language."
    from conlang_generator.core.traits import TraitProfile
    from conlang_generator.generation.generator import generate_language

    spec = GenerationSpec(seed=3, vocabulary_size=8, traits=TraitProfile(altitude=0.9))
    language = generate_language("T", spec, FakeLLMClient())
    assert language.spec.traits.altitude == 0.9
    assert len(language.lexicon.entries) > 0
