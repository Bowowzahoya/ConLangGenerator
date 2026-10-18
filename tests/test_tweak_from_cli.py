"""Tests for ``generate --tweak-from``/``--words`` -- the CLI entry point
for "Tweaking an existing language" item 5 (``docs/DEFERRED.md``), thin
plumbing over the already-tested ``generator.regenerate_phonology``/
``regenerate_phonology_adapt_words`` (mirrors how ``--evolve-from`` is
itself only plumbing over ``sound_change.evolve_language``, not separately
unit-tested beyond its own CLI-level validation)."""

import conlang_generator.cli.main as cli_main
from typer.testing import CliRunner


def _runner(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_main, "LANGUAGES_DIR", tmp_path / "conlangs")
    monkeypatch.setattr(cli_main, "CACHE_DIR", tmp_path / "cache")
    return CliRunner()


def _make_base(runner, name="tweak-base"):
    result = runner.invoke(
        cli_main.app,
        ["generate", "--prompt", "p", "--name", name, "--seed", "5", "--llm", "fake", "--vocabulary-size", "10"],
    )
    assert result.exit_code == 0
    return result


def test_tweak_from_requires_words(tmp_path, monkeypatch):
    runner = _runner(tmp_path, monkeypatch)
    _make_base(runner)
    result = runner.invoke(
        cli_main.app,
        ["generate", "--tweak-from", "tweak-base", "--name", "x", "--prompt", "ignored", "--llm", "fake"],
    )
    assert result.exit_code == 1
    assert "--words" in result.output


def test_tweak_from_rejects_an_invalid_words_value(tmp_path, monkeypatch):
    runner = _runner(tmp_path, monkeypatch)
    _make_base(runner)
    result = runner.invoke(
        cli_main.app,
        ["generate", "--tweak-from", "tweak-base", "--name", "x", "--words", "bogus", "--prompt", "ignored", "--llm", "fake"],
    )
    assert result.exit_code == 1
    assert "--words" in result.output


def test_tweak_from_rejects_a_grammar_affecting_trait(tmp_path, monkeypatch):
    runner = _runner(tmp_path, monkeypatch)
    _make_base(runner)
    result = runner.invoke(
        cli_main.app,
        [
            "generate", "--tweak-from", "tweak-base", "--name", "x", "--words", "regenerate",
            "--trait", "social_hierarchy=0.5", "--prompt", "ignored", "--llm", "fake",
        ],
    )
    assert result.exit_code == 1
    assert "social_hierarchy" in result.output


def test_tweak_from_rejects_a_nonexistent_base_language(tmp_path, monkeypatch):
    runner = _runner(tmp_path, monkeypatch)
    result = runner.invoke(
        cli_main.app,
        ["generate", "--tweak-from", "does-not-exist", "--name", "x", "--words", "regenerate", "--prompt", "p", "--llm", "fake"],
    )
    assert result.exit_code == 1
    assert "does-not-exist" in result.output


def test_tweak_from_regenerate_words_saves_a_new_language_with_a_fresh_lexicon(tmp_path, monkeypatch):
    runner = _runner(tmp_path, monkeypatch)
    _make_base(runner)
    result = runner.invoke(
        cli_main.app,
        [
            "generate", "--tweak-from", "tweak-base", "--name", "tweak-regen", "--words", "regenerate",
            "--trait", "aesthetic_harshness=0.9", "--prompt", "ignored", "--llm", "fake",
        ],
    )
    assert result.exit_code == 0
    assert "Tweaked 'tweak-base' -> 'tweak-regen'" in result.output
    assert "words: regenerate" in result.output

    from conlang_generator.storage.yaml_backend import YamlLanguageRepository

    repo = YamlLanguageRepository(tmp_path / "conlangs")
    base = repo.load("tweak-base")
    tweaked = repo.load("tweak-regen")
    assert tweaked.grammar.word_order == base.grammar.word_order
    assert [e.ipa for e in tweaked.lexicon.entries] != [e.ipa for e in base.lexicon.entries]


def test_tweak_from_adapt_words_keeps_the_same_glosses(tmp_path, monkeypatch):
    runner = _runner(tmp_path, monkeypatch)
    _make_base(runner)
    result = runner.invoke(
        cli_main.app,
        [
            "generate", "--tweak-from", "tweak-base", "--name", "tweak-adapt", "--words", "adapt",
            "--trait", "aesthetic_harshness=0.9", "--prompt", "ignored", "--llm", "fake",
        ],
    )
    assert result.exit_code == 0
    assert "words: adapt" in result.output

    from conlang_generator.storage.yaml_backend import YamlLanguageRepository

    repo = YamlLanguageRepository(tmp_path / "conlangs")
    base = repo.load("tweak-base")
    tweaked = repo.load("tweak-adapt")
    assert [e.glosses for e in tweaked.lexicon.entries] == [e.glosses for e in base.lexicon.entries]
