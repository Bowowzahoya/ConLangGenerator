"""CLI tests for `conlang generate --own-script` and the new `conlang
script` command."""

from typer.testing import CliRunner


def test_cli_generate_rejects_an_invalid_own_script_value(tmp_path, monkeypatch):
    import conlang_generator.cli.main as cli_main

    monkeypatch.setattr(cli_main, "LANGUAGES_DIR", tmp_path / "conlangs")
    monkeypatch.setattr(cli_main, "CACHE_DIR", tmp_path / "cache")
    result = CliRunner().invoke(
        cli_main.app,
        ["generate", "--prompt", "p", "--name", "cli-script-bad", "--seed", "1", "--llm", "fake",
         "--own-script", "maybe"],
    )
    assert result.exit_code == 1
    assert "own-script" in result.output


def test_cli_generate_own_script_auto_defaults_to_no_script(tmp_path, monkeypatch):
    import conlang_generator.cli.main as cli_main
    from conlang_generator.storage.yaml_backend import YamlLanguageRepository

    monkeypatch.setattr(cli_main, "LANGUAGES_DIR", tmp_path / "conlangs")
    monkeypatch.setattr(cli_main, "CACHE_DIR", tmp_path / "cache")
    result = CliRunner().invoke(
        cli_main.app,
        ["generate", "--prompt", "p", "--name", "cli-script-auto", "--seed", "1", "--llm", "fake",
         "--vocabulary-size", "8"],
    )
    assert result.exit_code == 0
    language = YamlLanguageRepository(cli_main.LANGUAGES_DIR).load("cli-script-auto")
    assert language.script is None


def test_cli_generate_own_script_yes_attaches_a_script(tmp_path, monkeypatch):
    import conlang_generator.cli.main as cli_main
    from conlang_generator.storage.yaml_backend import YamlLanguageRepository

    monkeypatch.setattr(cli_main, "LANGUAGES_DIR", tmp_path / "conlangs")
    monkeypatch.setattr(cli_main, "CACHE_DIR", tmp_path / "cache")
    result = CliRunner().invoke(
        cli_main.app,
        ["generate", "--prompt", "p", "--name", "cli-script-yes", "--seed", "1", "--llm", "fake",
         "--vocabulary-size", "8", "--own-script", "yes"],
    )
    assert result.exit_code == 0
    language = YamlLanguageRepository(cli_main.LANGUAGES_DIR).load("cli-script-yes")
    assert language.script is not None
    assert len(language.script.glyphs) > 0


def test_cli_script_on_a_language_with_none_errors_clearly(tmp_path, monkeypatch):
    import conlang_generator.cli.main as cli_main

    monkeypatch.setattr(cli_main, "LANGUAGES_DIR", tmp_path / "conlangs")
    monkeypatch.setattr(cli_main, "CACHE_DIR", tmp_path / "cache")
    CliRunner().invoke(
        cli_main.app,
        ["generate", "--prompt", "p", "--name", "cli-script-none", "--seed", "1", "--llm", "fake",
         "--vocabulary-size", "8"],
    )
    result = CliRunner().invoke(cli_main.app, ["script", "--lang", "cli-script-none"])
    assert result.exit_code == 1
    assert "no invented script" in result.output


def test_cli_script_sounds_lists_every_glyph(tmp_path, monkeypatch):
    import conlang_generator.cli.main as cli_main
    from conlang_generator.storage.yaml_backend import YamlLanguageRepository

    monkeypatch.setattr(cli_main, "LANGUAGES_DIR", tmp_path / "conlangs")
    monkeypatch.setattr(cli_main, "CACHE_DIR", tmp_path / "cache")
    CliRunner().invoke(
        cli_main.app,
        ["generate", "--prompt", "p", "--name", "cli-script-sounds", "--seed", "1", "--llm", "fake",
         "--vocabulary-size", "8", "--own-script", "yes"],
    )
    language = YamlLanguageRepository(cli_main.LANGUAGES_DIR).load("cli-script-sounds")

    result = CliRunner().invoke(cli_main.app, ["script", "--lang", "cli-script-sounds", "--sounds"])
    assert result.exit_code == 0
    for glyph in language.script.glyphs:
        assert f"/{glyph.ipa}/" in result.output


def test_cli_script_export_writes_a_real_font_file(tmp_path, monkeypatch):
    import conlang_generator.cli.main as cli_main

    monkeypatch.setattr(cli_main, "LANGUAGES_DIR", tmp_path / "conlangs")
    monkeypatch.setattr(cli_main, "CACHE_DIR", tmp_path / "cache")
    CliRunner().invoke(
        cli_main.app,
        ["generate", "--prompt", "p", "--name", "cli-script-export", "--seed", "1", "--llm", "fake",
         "--vocabulary-size", "8", "--own-script", "yes"],
    )
    font_path = tmp_path / "exported.ttf"
    result = CliRunner().invoke(
        cli_main.app, ["script", "--lang", "cli-script-export", "--export", str(font_path)]
    )
    assert result.exit_code == 0
    assert font_path.is_file() and font_path.stat().st_size > 0
