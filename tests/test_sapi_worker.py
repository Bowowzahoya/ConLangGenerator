"""Tests for speech.sapi_worker.SapiWorker -- the persistent-process fix
for SapiTTSClient's original one-shot ~3.7s/word PowerShell-process-
startup cost.

Protocol/lifecycle tests (framing, timeout, restart) use a trivial
Python stand-in subprocess instead of real PowerShell, so they're fast
and don't need Windows/SAPI installed. A small number of real-SAPI
tests are gated behind `sys.platform.startswith("win")`, matching
tests/test_tts.py's own existing convention."""

import subprocess
import sys
from pathlib import Path

import pytest

from conlang_generator.speech import sapi_worker as sapi_worker_module
from conlang_generator.speech.sapi_worker import SapiWorker

_IS_WINDOWS = sys.platform.startswith("win")

_ECHO_OK_SCRIPT = (
    "import sys\n"
    "for line in sys.stdin:\n"
    "    sys.stdout.write('OK\\n')\n"
    "    sys.stdout.flush()\n"
)
"""Mimics the real worker script's own line protocol (one line in, one
'OK' line out) without touching PowerShell/SAPI at all -- for testing
the request/response framing and lifecycle, not the actual synthesis."""

_EXIT_IMMEDIATELY_SCRIPT = "import sys\nsys.exit(1)\n"
"""Simulates a worker that's already dead the moment it's started."""

_NEVER_RESPONDS_SCRIPT = (
    "import sys, time\n"
    "for line in sys.stdin:\n"
    "    time.sleep(60)\n"
)
"""Reads a request but never replies -- exercises the timeout path."""


_real_popen = subprocess.Popen
"""Captured before any monkeypatching -- `fake_popen` below must call
*this*, not `subprocess.Popen` by name, since patching that name would
otherwise make a fake_popen that calls itself recursively."""


def _fake_popen_launching(script: str):
    """A drop-in replacement for `subprocess.Popen` that ignores the
    real `powershell.exe ...` argument list `SapiWorker._start` builds
    and launches this Python stand-in script instead, using the exact
    same pipe/encoding kwargs so the rest of `SapiWorker`'s own code
    (which only interacts with it as a generic `Popen` object) is
    none the wiser."""

    def fake_popen(_args, **kwargs):
        return _real_popen([sys.executable, "-c", script], **kwargs)

    return fake_popen


def _write_fake_wav(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"\x00" * 100)  # bigger than the 44-byte "empty" threshold


@pytest.fixture()
def _fast_timeout(monkeypatch):
    # Every fake-protocol test below should resolve in well under a
    # second, not the real 15s production timeout. Deliberately NOT
    # autouse: the real-SAPI tests further down must keep the real
    # timeout -- an autouse version of this fixture once made every
    # real-SAPI test flaky under the full suite's own heavy load
    # (genuine startup contention legitimately took a bit over 1s,
    # which this fixture's whole point is to rule out as "too slow").
    monkeypatch.setattr(sapi_worker_module, "_REQUEST_TIMEOUT_SECONDS", 1.0)


def test_synthesize_succeeds_when_the_script_replies_ok_and_a_real_file_exists(tmp_path: Path, monkeypatch, _fast_timeout):
    monkeypatch.setattr(sapi_worker_module.subprocess, "Popen", _fake_popen_launching(_ECHO_OK_SCRIPT))
    worker = SapiWorker()
    output_path = tmp_path / "out.wav"
    _write_fake_wav(output_path)  # the fake script never actually writes the file -- simulate that it did
    assert worker.synthesize("kat", output_path) is True
    worker.close()


def test_synthesize_fails_when_ok_is_reported_but_no_real_file_was_written(tmp_path: Path, monkeypatch, _fast_timeout):
    # The fake script says "OK" unconditionally but writes nothing --
    # the file-size sanity check (mirroring the one-shot path's own)
    # must catch this, not just trust the string reply.
    monkeypatch.setattr(sapi_worker_module.subprocess, "Popen", _fake_popen_launching(_ECHO_OK_SCRIPT))
    worker = SapiWorker()
    output_path = tmp_path / "out.wav"
    assert worker.synthesize("kat", output_path) is False
    worker.close()


def test_synthesize_reuses_the_same_process_across_calls(tmp_path: Path, monkeypatch, _fast_timeout):
    monkeypatch.setattr(sapi_worker_module.subprocess, "Popen", _fake_popen_launching(_ECHO_OK_SCRIPT))
    worker = SapiWorker()
    p1 = tmp_path / "w1.wav"
    p2 = tmp_path / "w2.wav"
    _write_fake_wav(p1)
    worker.synthesize("kat", p1)
    first_pid = worker._process.pid
    _write_fake_wav(p2)
    worker.synthesize("mat", p2)
    assert worker._process.pid == first_pid  # no new process spawned for the second call
    worker.close()


def test_synthesize_restarts_after_the_process_is_already_dead(tmp_path: Path, monkeypatch, _fast_timeout):
    monkeypatch.setattr(sapi_worker_module.subprocess, "Popen", _fake_popen_launching(_EXIT_IMMEDIATELY_SCRIPT))
    worker = SapiWorker()
    # Force-start the (immediately-dying) process, then let it actually die.
    worker._start()
    worker._process.wait()
    # Now swap in a working script for the restart this call should trigger.
    monkeypatch.setattr(sapi_worker_module.subprocess, "Popen", _fake_popen_launching(_ECHO_OK_SCRIPT))
    output_path = tmp_path / "out.wav"
    _write_fake_wav(output_path)
    assert worker.synthesize("kat", output_path) is True
    worker.close()


def test_synthesize_returns_false_on_a_timeout_without_hanging(tmp_path: Path, monkeypatch, _fast_timeout):
    # Both the initial attempt and its one restart-retry hit the same
    # never-responding script -- confirms synthesize() gives up cleanly
    # (bounded by 2x the patched 1s timeout) rather than hanging forever.
    monkeypatch.setattr(sapi_worker_module.subprocess, "Popen", _fake_popen_launching(_NEVER_RESPONDS_SCRIPT))
    worker = SapiWorker()
    assert worker.synthesize("kat", tmp_path / "out.wav") is False
    worker.close()


def test_close_terminates_the_process_and_removes_the_temp_script(tmp_path: Path, monkeypatch, _fast_timeout):
    monkeypatch.setattr(sapi_worker_module.subprocess, "Popen", _fake_popen_launching(_ECHO_OK_SCRIPT))
    worker = SapiWorker()
    output_path = tmp_path / "out.wav"
    _write_fake_wav(output_path)
    worker.synthesize("kat", output_path)
    script_path = worker._script_path
    assert script_path is not None and script_path.is_file()
    worker.close()
    assert worker._process is None
    assert not script_path.is_file()


def test_context_manager_closes_on_exit(monkeypatch, _fast_timeout):
    monkeypatch.setattr(sapi_worker_module.subprocess, "Popen", _fake_popen_launching(_ECHO_OK_SCRIPT))
    with SapiWorker() as worker:
        worker._start()
    assert worker._process is None


def test_a_fresh_worker_spawns_no_process_until_the_first_synthesize_call(_fast_timeout):
    worker = SapiWorker()
    assert worker._process is None  # constructing it is free -- fully lazy
    worker.close()  # must be a no-op, not an error, on a never-started worker


# --- real SAPI (Windows only) --------------------------------------------------


@pytest.mark.skipif(not _IS_WINDOWS, reason="SAPI is Windows-only")
def test_real_worker_synthesizes_two_real_words_through_one_process(tmp_path: Path):
    worker = SapiWorker()
    p1, p2 = tmp_path / "w1.wav", tmp_path / "w2.wav"
    assert worker.synthesize("kat", p1) is True
    assert worker.synthesize("mat", p2) is True
    assert p1.stat().st_size > 44 and p2.stat().st_size > 44
    worker.close()


@pytest.mark.skipif(not _IS_WINDOWS, reason="SAPI is Windows-only")
def test_real_worker_produces_byte_identical_output_to_the_one_shot_client(tmp_path: Path):
    # The whole point of reusing System.Speech's own proven SpeakSsml
    # call instead of switching SAPI bindings -- confirms zero behavior
    # change on the one feature (direct IPA passthrough) that matters.
    import unicodedata
    import xml.sax.saxutils

    from conlang_generator.speech.tts import SapiTTSClient

    exotic = "k" + "ʼ" + "a" + "̃"  # kʼã -- ejective + nasalized vowel
    one_shot_path = tmp_path / "one_shot.wav"
    assert SapiTTSClient().synthesize(exotic, one_shot_path) is True

    worker = SapiWorker()
    worker_path = tmp_path / "worker.wav"
    prepped = unicodedata.normalize("NFD", exotic)
    escaped = xml.sax.saxutils.escape(prepped, {'"': "&quot;"})
    assert worker.synthesize(escaped, worker_path) is True
    worker.close()

    assert one_shot_path.read_bytes() == worker_path.read_bytes()


@pytest.mark.skipif(not _IS_WINDOWS, reason="SAPI is Windows-only")
@pytest.mark.slow
def test_real_worker_is_dramatically_faster_after_the_first_word(tmp_path: Path):
    # A loose timing tripwire, not a precise benchmark (same philosophy
    # AGENTS.md documents for this suite's other timing tripwires) --
    # guards against the persistent-process fix regressing back toward
    # one-shot-per-word behavior, not an exact number.
    import time

    worker = SapiWorker()
    t0 = time.time()
    worker.synthesize("kat", tmp_path / "w1.wav")
    first = time.time() - t0

    t0 = time.time()
    worker.synthesize("mat", tmp_path / "w2.wav")
    second = time.time() - t0
    worker.close()

    assert second < first / 5  # dramatically faster, not just "a bit"
    assert second < 1.0  # well under the original ~3.7s/word
