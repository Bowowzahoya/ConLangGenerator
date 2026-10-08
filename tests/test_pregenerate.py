"""Tests for speech.pregenerate -- eagerly synthesizing a language's own
lexicon into the TTS audio cache (speech.tts_cache)."""

from pathlib import Path

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.speech import pregenerate, tts, tts_cache

_language = generate_language("pregen-fixture", GenerationSpec(prompt="p", seed=1, vocabulary_size=10), FakeLLMClient())


def test_pregenerate_audio_synthesizes_and_caches_every_entry(tmp_path: Path):
    summary = pregenerate.pregenerate_audio(_language, "espeak", tmp_path)
    assert summary.total == len(_language.lexicon.entries)
    assert summary.synthesized == summary.total
    assert summary.failed == 0
    cache_files = list((tmp_path / "tts_cache").glob("*.wav"))
    assert len(cache_files) == summary.total


def test_pregenerate_audio_builds_exactly_one_sapi_worker_not_one_per_word(tmp_path: Path, monkeypatch):
    # The whole point of the persistent-worker fix: one process shared
    # across the entire lexicon, never one per word.
    constructed = []
    closed = []

    class _FakeWorker:
        def __init__(self):
            constructed.append(self)

        def synthesize(self, escaped_ipa, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"\x00" * 100)
            return True

        def close(self):
            closed.append(self)

    monkeypatch.setattr(pregenerate, "SapiWorker", _FakeWorker)
    summary = pregenerate.pregenerate_audio(_language, "sapi", tmp_path)
    assert summary.synthesized == summary.total
    assert len(constructed) == 1
    assert closed == constructed  # the one worker built was also closed


def test_pregenerate_audio_builds_no_sapi_worker_for_a_pure_espeak_run(tmp_path: Path, monkeypatch):
    def _fail(*args, **kwargs):
        raise AssertionError("an espeak-only run must never construct a SapiWorker")

    monkeypatch.setattr(pregenerate, "SapiWorker", _fail)
    summary = pregenerate.pregenerate_audio(_language, "espeak", tmp_path)
    assert summary.synthesized == summary.total


def test_pregenerate_audio_reuses_the_cache_a_pronounce_call_would_hit(tmp_path: Path, monkeypatch):
    pregenerate.pregenerate_audio(_language, "espeak", tmp_path)
    entry = _language.lexicon.entries[0]
    client = tts_cache.CachingTTSClient(tts.build_tts_client("espeak"), tmp_path / "tts_cache")

    calls = {"count": 0}
    real_synthesize = tts.EspeakTTSClient.synthesize

    def counting_synthesize(self, ipa_text, output_path):
        calls["count"] += 1
        return real_synthesize(self, ipa_text, output_path)

    monkeypatch.setattr(tts.EspeakTTSClient, "synthesize", counting_synthesize)
    assert client.synthesize(entry.ipa, tmp_path / "out.wav") is True
    assert calls["count"] == 0  # served from the cache pregenerate_audio already populated


def test_pregenerate_audio_calls_on_progress_for_every_entry_in_order(tmp_path: Path):
    progress: list[tuple[int, int]] = []
    pregenerate.pregenerate_audio(_language, "espeak", tmp_path, on_progress=lambda done, total: progress.append((done, total)))
    total = len(_language.lexicon.entries)
    assert progress == [(i, total) for i in range(1, total + 1)]


def test_pregenerate_audio_on_an_empty_lexicon_is_a_no_op(tmp_path: Path):
    empty = _language.model_copy(update={"lexicon": _language.lexicon.model_copy(update={"entries": ()})})
    summary = pregenerate.pregenerate_audio(empty, "espeak", tmp_path)
    assert summary == pregenerate.PregenerateSummary(0, 0, 0)


def test_pregenerate_audio_auto_picks_an_engine_per_word_and_still_caches(tmp_path: Path):
    small = generate_language("pregen-auto-fixture", GenerationSpec(prompt="p", seed=2, vocabulary_size=3), FakeLLMClient())
    summary = pregenerate.pregenerate_audio(small, "auto", tmp_path)
    assert summary.total == len(small.lexicon.entries)
    assert summary.synthesized == summary.total
    cache_files = list((tmp_path / "tts_cache").glob("*.wav"))
    assert len(cache_files) == summary.total


def test_pregenerate_audio_reports_failure_when_no_backend_is_available(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(tts, "available_engine_kinds", lambda: ())
    summary = pregenerate.pregenerate_audio(_language, "auto", tmp_path)
    assert summary.total == len(_language.lexicon.entries)
    assert summary.synthesized == 0
    assert summary.failed == summary.total


# --- CLI -----------------------------------------------------------------------


def test_cli_generate_rejects_an_invalid_pregenerate_audio_value(tmp_path, monkeypatch):
    import conlang_generator.cli.main as cli_main
    from typer.testing import CliRunner

    monkeypatch.setattr(cli_main, "LANGUAGES_DIR", tmp_path / "conlangs")
    monkeypatch.setattr(cli_main, "CACHE_DIR", tmp_path / "cache")
    result = CliRunner().invoke(
        cli_main.app,
        ["generate", "--prompt", "p", "--name", "cli-pregen-bad", "--seed", "1", "--llm", "fake",
         "--pregenerate-audio", "piper"],
    )
    assert result.exit_code == 1
    assert "pregenerate-audio" in result.output


def test_cli_generate_pregenerates_audio_and_prints_a_summary(tmp_path, monkeypatch):
    import conlang_generator.cli.main as cli_main
    from typer.testing import CliRunner

    monkeypatch.setattr(cli_main, "LANGUAGES_DIR", tmp_path / "conlangs")
    monkeypatch.setattr(cli_main, "CACHE_DIR", tmp_path / "cache")
    result = CliRunner().invoke(
        cli_main.app,
        ["generate", "--prompt", "p", "--name", "cli-pregen-good", "--seed", "1", "--llm", "fake",
         "--vocabulary-size", "8", "--pregenerate-audio", "espeak"],
    )
    assert result.exit_code == 0
    assert "Pre-generating audio for" in result.output
    assert "Pre-generated audio for" in result.output

    from conlang_generator.storage.yaml_backend import YamlLanguageRepository

    language = YamlLanguageRepository(cli_main.LANGUAGES_DIR).load("cli-pregen-good")
    cache_files = list((tmp_path / "cache" / "tts_cache").glob("*.wav"))
    assert len(cache_files) == len(language.lexicon.entries)


def test_cli_generate_defaults_to_no_pregeneration(tmp_path, monkeypatch):
    import conlang_generator.cli.main as cli_main
    from typer.testing import CliRunner

    monkeypatch.setattr(cli_main, "LANGUAGES_DIR", tmp_path / "conlangs")
    monkeypatch.setattr(cli_main, "CACHE_DIR", tmp_path / "cache")
    result = CliRunner().invoke(
        cli_main.app,
        ["generate", "--prompt", "p", "--name", "cli-pregen-default", "--seed", "1", "--llm", "fake"],
    )
    assert result.exit_code == 0
    assert "Pre-generat" not in result.output
    assert not (tmp_path / "cache" / "tts_cache").exists()
