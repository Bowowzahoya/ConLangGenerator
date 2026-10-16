"""Tests for speech.tts -- the provider-agnostic TTS seam. NoneTTSClient
(the default everywhere else in this project) is always tested; the
three real backends are each gated behind their own actual dependency
being present, so the suite stays green on a machine without
espeak-ng/off Windows/without the optional piper group + voice set up."""

import shutil
import sys
from pathlib import Path

import pytest

from conlang_generator.speech import tts

_ESPEAK_AVAILABLE = tts._find_espeak_ng() is not None
_IS_WINDOWS = sys.platform.startswith("win")
try:
    import piper  # noqa: F401

    _PIPER_AVAILABLE = tts._find_piper_voice() is not None
except ImportError:
    _PIPER_AVAILABLE = False


def test_build_tts_client_defaults_to_none():
    assert isinstance(tts.build_tts_client(), tts.NoneTTSClient)
    assert isinstance(tts.build_tts_client("none"), tts.NoneTTSClient)


def test_build_tts_client_rejects_an_unknown_kind():
    with pytest.raises(ValueError):
        tts.build_tts_client("not-a-real-backend")


def test_none_client_never_synthesizes(tmp_path: Path):
    client = tts.NoneTTSClient()
    output = tmp_path / "out.wav"
    assert client.synthesize("kat", output) is False
    assert not output.exists()


@pytest.mark.skipif(not _ESPEAK_AVAILABLE, reason="espeak-ng not installed on this machine")
def test_espeak_client_synthesizes_a_real_wav_file(tmp_path: Path):
    client = tts.build_tts_client("espeak")
    output = tmp_path / "out.wav"
    assert client.synthesize("kat", output) is True
    assert output.is_file()
    assert output.stat().st_size > 0


@pytest.mark.skipif(_ESPEAK_AVAILABLE, reason="this test only makes sense when espeak-ng is absent")
def test_espeak_client_reports_unavailable_when_not_installed(tmp_path: Path):
    client = tts.build_tts_client("espeak")
    output = tmp_path / "out.wav"
    assert client.synthesize("kat", output) is False
    assert not output.exists()


@pytest.mark.skipif(not _IS_WINDOWS, reason="SAPI is Windows-only")
def test_sapi_client_synthesizes_a_real_wav_file(tmp_path: Path):
    client = tts.build_tts_client("sapi")
    output = tmp_path / "out.wav"
    assert client.synthesize("kat", output) is True
    assert output.is_file()
    assert output.stat().st_size > 0


@pytest.mark.skipif(_IS_WINDOWS, reason="this test only makes sense off Windows")
def test_sapi_client_reports_unavailable_off_windows(tmp_path: Path):
    client = tts.build_tts_client("sapi")
    output = tmp_path / "out.wav"
    assert client.synthesize("kat", output) is False
    assert not output.exists()


def test_sapi_client_delegates_to_an_injected_worker_instead_of_a_one_shot_call(tmp_path: Path):
    class _FakeWorker:
        def __init__(self):
            self.calls = []

        def synthesize(self, escaped_ipa, output_path):
            self.calls.append((escaped_ipa, output_path))
            return True

    worker = _FakeWorker()
    client = tts.build_tts_client("sapi", sapi_worker=worker)
    assert isinstance(client, tts.SapiTTSClient)
    if _IS_WINDOWS:
        output = tmp_path / "out.wav"
        assert client.synthesize("kat", output) is True
        assert len(worker.calls) == 1
        assert worker.calls[0][1] == output


@pytest.mark.skipif(not _PIPER_AVAILABLE, reason="piper not installed or voice not downloaded on this machine")
def test_piper_client_synthesizes_a_real_wav_file(tmp_path: Path):
    client = tts.build_tts_client("piper")
    output = tmp_path / "out.wav"
    assert client.synthesize("ˈkat", output) is True
    assert output.is_file()
    assert output.stat().st_size > 44


@pytest.mark.skipif(_PIPER_AVAILABLE, reason="this test only makes sense when piper is unavailable")
def test_piper_client_reports_unavailable_when_not_set_up(tmp_path: Path):
    client = tts.build_tts_client("piper")
    output = tmp_path / "out.wav"
    assert client.synthesize("kat", output) is False
    assert not output.exists()


def test_piper_reported_unavailable_when_voice_files_exist_but_the_package_is_not_installed(tmp_path, monkeypatch):
    # Regression guard for a real bug hit in practice: `uv sync` without
    # `--group piper` silently drops the `piper` package while leaving
    # already-downloaded voice files in place. available_backends() used
    # to report "piper": True purely from file presence, so "auto"
    # confidently routed words to Piper and every one of them then
    # failed silently at synthesize() time (ImportError swallowed),
    # surfacing only as a confusing "TTS backend unavailable or
    # synthesis failed" error with no indication of the real cause.
    voice_dir = tmp_path / "piper_voices"
    voice_dir.mkdir()
    (voice_dir / f"{tts._PIPER_VOICE_NAME}.onnx").write_bytes(b"not a real model")
    (voice_dir / f"{tts._PIPER_VOICE_NAME}.onnx.json").write_text("{}")
    monkeypatch.setattr(tts, "_PIPER_VOICE_DIR", voice_dir)
    assert tts._find_piper_voice() is not None  # files alone look present

    monkeypatch.setitem(sys.modules, "piper", None)  # forces `import piper` to raise ImportError
    assert tts._piper_usable() is False
    assert tts.available_backends()["piper"] is False


@pytest.mark.skipif(not _PIPER_AVAILABLE, reason="piper not installed or voice not downloaded on this machine")
def test_piper_client_reuses_an_injected_client_instance_instead_of_a_fresh_one():
    shared = tts.build_tts_client("piper")
    assert tts.build_tts_client("piper", piper_client=shared) is shared


def test_piper_client_capabilities_report_no_tones():
    # Needs no real piper install -- capabilities() never touches the
    # lazily-loaded voice.
    caps = tts.build_tts_client("piper").capabilities()
    assert caps.tones == frozenset()
    assert caps.notes


def test_piper_client_cache_identity_is_a_fixed_engine_specific_string():
    assert tts.PiperTTSClient().cache_identity() == "piper:en_US-lessac-medium"


def test_sapi_worker_kwarg_is_ignored_by_every_other_kind():
    # build_tts_client's new keyword-only parameter must be a no-op for
    # anything but "sapi" -- passing it to "espeak"/"none" must not raise.
    class _FakeWorker:
        def synthesize(self, escaped_ipa, output_path):
            raise AssertionError("espeak/none must never touch a sapi_worker")

    assert isinstance(tts.build_tts_client("none", sapi_worker=_FakeWorker()), tts.NoneTTSClient)
    assert isinstance(tts.build_tts_client("espeak", sapi_worker=_FakeWorker()), tts.EspeakTTSClient)


def test_piper_client_kwarg_is_ignored_by_every_other_kind():
    other_client = tts.PiperTTSClient()
    assert tts.build_tts_client("none", piper_client=other_client) is not other_client
    assert isinstance(tts.build_tts_client("espeak", piper_client=other_client), tts.EspeakTTSClient)


def test_find_espeak_ng_prefers_path_over_fallback_locations(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: r"C:\some\other\espeak-ng.exe")
    assert tts._find_espeak_ng() == r"C:\some\other\espeak-ng.exe"


def test_find_espeak_ng_returns_none_when_nothing_is_found(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(Path, "is_file", lambda self: False)
    assert tts._find_espeak_ng() is None


def test_cache_identity_reflects_every_constructor_argument_that_changes_output():
    # Two EspeakTTSClient instances differing only in voice/tones must have
    # different identities -- speech.tts_cache.CachingTTSClient relies on
    # this to never conflate two clients that would actually synthesize
    # different audio for the same text.
    assert tts.EspeakTTSClient().cache_identity() != tts.EspeakTTSClient(voice="cmn", tones=True).cache_identity()
    assert tts.EspeakTTSClient().cache_identity() == tts.EspeakTTSClient().cache_identity()
    assert tts.SapiTTSClient().cache_identity() == "sapi"
    assert tts.NoneTTSClient().cache_identity() == "none"
    assert tts.PiperTTSClient().cache_identity() == "piper:en_US-lessac-medium"


def test_available_backends_none_is_always_true():
    assert tts.available_backends()["none"] is True


def test_available_backends_reflects_actual_espeak_and_platform_state():
    backends = tts.available_backends()
    assert backends["espeak"] == _ESPEAK_AVAILABLE
    assert backends["sapi"] == _IS_WINDOWS
    assert backends["piper"] == _PIPER_AVAILABLE
