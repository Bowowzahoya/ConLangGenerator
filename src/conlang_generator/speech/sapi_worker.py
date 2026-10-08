"""A persistent SAPI synthesis worker: one long-lived PowerShell process,
fed requests over its own stdin/stdout, instead of a fresh process per
word. Fixes ``SapiTTSClient``'s original one-shot ``subprocess.run``,
measured at ~3.7s/word -- almost entirely PowerShell process-startup +
.NET assembly load, not the actual speech synthesis (see
``docs/DEFERRED.md``).

Uses the exact same ``Add-Type -AssemblyName System.Speech`` /
``SpeechSynthesizer`` / ``SpeakSsml()`` call the original one-shot script
already proved works (direct IPA passthrough via SSML's ``<phoneme
alphabet="ipa">``) -- only run once per *process* instead of once per
*word*, never swapped for a different SAPI binding: raw COM automation
(``pywin32``'s ``SAPI.SpVoice``) is a different object model with
unverified SSML-phoneme behavior, and ``pythonnet`` would keep the same
API but adds a heavy, never-used-here native-interop dependency this
project already chose PowerShell specifically to avoid once before.
"""

from __future__ import annotations

import json
import queue
import subprocess
import tempfile
import threading
from pathlib import Path

_WORKER_SCRIPT = r"""
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
while ($line = [Console]::In.ReadLine()) {
    try {
        $req = $line | ConvertFrom-Json
        $synth.SetOutputToWaveFile($req.path)
        $ssml = '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US"><phoneme alphabet="ipa" ph="' + $req.ipa + '">word</phoneme></speak>'
        $synth.SpeakSsml($ssml)
        $synth.SetOutputToNull()
        [Console]::Out.WriteLine("OK")
    } catch {
        [Console]::Out.WriteLine("ERROR: " + $_.Exception.Message)
    }
    [Console]::Out.Flush()
}
"""
"""Same setup/SpeakSsml call as ``tts._SAPI_SCRIPT_TEMPLATE`` -- loaded
and instantiated once, then a read-one-line/reply-one-line loop instead
of a single one-shot invocation. ``[Console]::InputEncoding``/
``OutputEncoding`` are forced to UTF-8 explicitly: PowerShell 5.1's own
console encoding under a *redirected* pipe (as opposed to a real
interactive console) does not reliably default to UTF-8, and an exotic
IPA symbol could otherwise get mangled silently."""

_REQUEST_TIMEOUT_SECONDS = 15.0


class SapiWorker:
    """One persistent ``powershell.exe`` process, reused across many
    ``synthesize`` calls instead of spawning a fresh one each time.
    Thread-safe (an internal lock serializes access) -- share one
    instance across concurrent callers freely. Fully lazy: no process
    exists until the first ``synthesize`` call, so constructing one
    that never ends up being used costs nothing."""

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._script_path: Path | None = None
        self._output_queue: queue.Queue[str] | None = None
        self._lock = threading.Lock()

    def _start(self) -> bool:
        script_file = tempfile.NamedTemporaryFile(mode="w", suffix=".ps1", delete=False, encoding="utf-8")
        script_file.write(_WORKER_SCRIPT)
        script_file.close()  # Windows: a second process can't reliably open this while our own handle is still open
        self._script_path = Path(script_file.name)
        try:
            self._process = subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(self._script_path)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", bufsize=1,
            )
        except OSError:
            self._process = None
            return False
        self._output_queue = queue.Queue()
        threading.Thread(target=self._read_output, args=(self._process, self._output_queue), daemon=True).start()
        return True

    @staticmethod
    def _read_output(process: subprocess.Popen, output_queue: "queue.Queue[str]") -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            output_queue.put(line.rstrip("\n"))

    def _kill(self) -> None:
        if self._process is not None:
            try:
                self._process.kill()
                self._process.wait(timeout=5)
            except Exception:
                pass
            self._process = None
        if self._script_path is not None:
            self._script_path.unlink(missing_ok=True)
            self._script_path = None
        self._output_queue = None

    def _restart(self) -> bool:
        self._kill()
        return self._start()

    def _send(self, escaped_ipa: str, output_path: Path) -> bool:
        if self._process is None or self._process.poll() is not None:
            if not self._start():
                return False
        assert self._process is not None and self._process.stdin is not None and self._output_queue is not None
        request = json.dumps({"path": str(output_path), "ipa": escaped_ipa})
        try:
            self._process.stdin.write(request + "\n")
            self._process.stdin.flush()
        except (OSError, ValueError):
            return False
        try:
            result = self._output_queue.get(timeout=_REQUEST_TIMEOUT_SECONDS)
        except queue.Empty:
            return False
        if result != "OK":
            return False
        # The script reporting "OK" only means SpeakSsml raised nothing --
        # matching the one-shot path's own sanity check, a bare WAV header
        # (44 bytes) with no real audio still counts as a failure.
        return output_path.is_file() and output_path.stat().st_size > 44

    def synthesize(self, escaped_ipa: str, output_path: Path) -> bool:
        """``escaped_ipa`` must already be XML-escaped and NFD-normalized
        -- ``SapiTTSClient.synthesize`` already does this before calling
        in, this module has no IPA preprocessing of its own. Never
        raises -- ``False`` for a failed or unavailable worker, after
        one retry against a freshly restarted process (covers a
        crashed/hung worker; a genuinely bad request just fails the
        same way twice, harmlessly)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if self._send(escaped_ipa, output_path):
                return True
            if not self._restart():
                return False
            return self._send(escaped_ipa, output_path)

    def close(self) -> None:
        with self._lock:
            if self._process is not None and self._process.stdin is not None:
                try:
                    self._process.stdin.close()
                except Exception:
                    pass
            self._kill()

    def __enter__(self) -> "SapiWorker":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


__all__ = ["SapiWorker"]
