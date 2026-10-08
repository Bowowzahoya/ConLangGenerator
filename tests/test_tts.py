"""Tests for speech.tts -- the provider-agnostic TTS seam. NoneTTSClient
(the default everywhere else in this project) is always tested; the two
real backends are gated behind the actual dependency being present, so
the suite stays green on a machine without espeak-ng or off Windows."""

import shutil
import sys
from pathlib import Path

import pytest

from conlang_generator.speech import tts

_ESPEAK_AVAILABLE = tts._find_espeak_ng() is not None
_IS_WINDOWS = sys.platform.startswith("win")


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


def test_sapi_worker_kwarg_is_ignored_by_every_other_kind():
    # build_tts_client's new keyword-only parameter must be a no-op for
    # anything but "sapi" -- passing it to "espeak"/"none" must not raise.
    class _FakeWorker:
        def synthesize(self, escaped_ipa, output_path):
            raise AssertionError("espeak/none must never touch a sapi_worker")

    assert isinstance(tts.build_tts_client("none", sapi_worker=_FakeWorker()), tts.NoneTTSClient)
    assert isinstance(tts.build_tts_client("espeak", sapi_worker=_FakeWorker()), tts.EspeakTTSClient)


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


def test_available_backends_none_is_always_true():
    assert tts.available_backends()["none"] is True


def test_available_backends_reflects_actual_espeak_and_platform_state():
    backends = tts.available_backends()
    assert backends["espeak"] == _ESPEAK_AVAILABLE
    assert backends["sapi"] == _IS_WINDOWS
