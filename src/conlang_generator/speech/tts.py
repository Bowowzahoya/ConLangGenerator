"""The provider-agnostic TTS seam -- mirrors ``llm/base.py``/``llm/
factory.py``'s own shape exactly (``TTSClient`` `Protocol`, a ``build_tts_
client()`` factory keyed by a string ``kind``), so ``cli/main.py`` never
imports a specific synthesis backend directly.

Two real backends, since the two sound genuinely different and there's no
clear universal winner:

- ``"espeak"``: espeak-ng, a real cross-platform synthesizer, once
  installed -- has no direct IPA input, so ``speech.ipa_to_kirshenbaum``
  converts to its own Kirshenbaum ASCII-IPA notation first (an
  approximation for this project's more exotic symbols -- see that
  module's own docstring).
- ``"sapi"``: Windows' own built-in ``System.Speech`` (SAPI), invoked via
  a short PowerShell script rather than a Python binding -- no install at
  all, and it accepts literal IPA directly through SSML's ``<phoneme
  alphabet="ipa">``, so no approximation step is needed. Windows-only.

``"none"`` (the default, matching ``build_llm_client(kind="fake")``'s own
"cheap and dependency-free by default" precedent) reproduces today's
"just print the IPA/romanization as text" behavior -- no audio, no
external process, always available.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import xml.sax.saxutils
from pathlib import Path
from typing import Protocol

from conlang_generator.speech import ipa_to_kirshenbaum

_ESPEAK_FALLBACK_PATHS = (
    r"C:\Program Files\eSpeak NG\espeak-ng.exe",
    r"C:\Program Files (x86)\eSpeak NG\espeak-ng.exe",
)
"""Common Windows install locations, consulted when ``espeak-ng`` isn't
on ``PATH`` -- its own installer doesn't always add it, and updating
``PATH`` for an already-running shell needs a fresh session anyway."""


class TTSClient(Protocol):
    def synthesize(self, ipa_text: str, output_path: Path) -> bool:
        """Renders ``ipa_text`` to a ``.wav`` file at ``output_path``.
        Returns whether synthesis actually happened -- ``False`` for an
        unavailable backend or a failed external call, never an
        exception (a missing/broken TTS backend is a normal, expected
        state this project's own CLI reports cleanly, not a bug)."""
        ...


class NoneTTSClient:
    """The default -- no audio synthesis, matching this project's
    original "just print the IPA as text" behavior exactly."""

    def synthesize(self, ipa_text: str, output_path: Path) -> bool:
        return False


def _find_espeak_ng() -> str | None:
    found = shutil.which("espeak-ng")
    if found:
        return found
    for candidate in _ESPEAK_FALLBACK_PATHS:
        if Path(candidate).is_file():
            return candidate
    return None


class EspeakTTSClient:
    """Shells out to espeak-ng's own ``[[...]]`` Kirshenbaum bracket
    syntax (see ``speech.ipa_to_kirshenbaum``'s own docstring for why
    that conversion is needed at all -- espeak-ng has no direct IPA
    input)."""

    def __init__(self, voice: str = "en-us") -> None:
        self.voice = voice

    def synthesize(self, ipa_text: str, output_path: Path) -> bool:
        exe = _find_espeak_ng()
        if exe is None:
            return False
        kirshenbaum = ipa_to_kirshenbaum.convert_word(ipa_text)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [exe, "-v", self.voice, "-w", str(output_path), f"[[{kirshenbaum}]]"],
            capture_output=True,
        )
        return result.returncode == 0 and output_path.is_file()


_SAPI_SCRIPT_TEMPLATE = """
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SetOutputToWaveFile("{output_path}")
$ssml = '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US"><phoneme alphabet="ipa" ph="{ipa}">word</phoneme></speak>'
$synth.SpeakSsml($ssml)
$synth.SetOutputToNull()
"""
"""A literal PowerShell script, not a Python COM/``pywin32`` binding --
avoids a new dependency for what's otherwise one small, one-shot call;
``System.Speech`` is already part of every Windows .NET install, so
``powershell.exe`` (also always present) is the only thing this needs."""


class SapiTTSClient:
    """Windows' own built-in SAPI, via ``System.Speech``'s real direct-
    IPA SSML support (``<phoneme alphabet="ipa" ph="...">``) -- no
    Kirshenbaum conversion, no separate install. Only available on
    Windows; ``synthesize`` returns ``False`` cleanly everywhere else,
    the same "unavailable is a normal state" contract every ``TTSClient``
    has."""

    def synthesize(self, ipa_text: str, output_path: Path) -> bool:
        if not sys.platform.startswith("win"):
            return False
        output_path.parent.mkdir(parents=True, exist_ok=True)
        escaped_ipa = xml.sax.saxutils.escape(ipa_text, {'"': "&quot;"})
        script = _SAPI_SCRIPT_TEMPLATE.format(
            output_path=str(output_path).replace('"', '`"'), ipa=escaped_ipa
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
        )
        return result.returncode == 0 and output_path.is_file()


def build_tts_client(kind: str = "none") -> TTSClient:
    if kind == "none":
        return NoneTTSClient()
    if kind == "espeak":
        return EspeakTTSClient()
    if kind == "sapi":
        return SapiTTSClient()
    raise ValueError(f"unknown TTS client kind: {kind!r}")


def available_backends() -> dict[str, bool]:
    """Which backends are actually usable right now on this machine --
    for a caller (``webui/app.py``'s own ``/api/options``) that wants to
    only offer a real choice, not silently fail after the fact.
    ``"none"`` is always ``True`` (it just does nothing)."""
    return {
        "none": True,
        "espeak": _find_espeak_ng() is not None,
        "sapi": sys.platform.startswith("win"),
    }


__all__ = [
    "TTSClient", "NoneTTSClient", "EspeakTTSClient", "SapiTTSClient",
    "build_tts_client", "available_backends",
]
