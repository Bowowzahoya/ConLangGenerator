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


def test_find_espeak_ng_prefers_path_over_fallback_locations(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: r"C:\some\other\espeak-ng.exe")
    assert tts._find_espeak_ng() == r"C:\some\other\espeak-ng.exe"


def test_find_espeak_ng_returns_none_when_nothing_is_found(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(Path, "is_file", lambda self: False)
    assert tts._find_espeak_ng() is None
