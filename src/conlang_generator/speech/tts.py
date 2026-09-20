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
import unicodedata
import xml.sax.saxutils
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from conlang_generator.core.phonology import TONE_DIACRITICS, ToneLevel
from conlang_generator.generation import ipa_tokenizer, phonology_gen
from conlang_generator.speech import ipa_to_kirshenbaum

_ESPEAK_FALLBACK_PATHS = (
    r"C:\Program Files\eSpeak NG\espeak-ng.exe",
    r"C:\Program Files (x86)\eSpeak NG\espeak-ng.exe",
)
"""Common Windows install locations, consulted when ``espeak-ng`` isn't
on ``PATH`` -- its own installer doesn't always add it, and updating
``PATH`` for an already-running shell needs a fresh session anyway."""


@dataclass(frozen=True)
class TTSCapabilities:
    """What a pronunciation engine can and cannot voice -- shown next to the
    engine's name in the UI, and checked against a translation's IPA by
    ``pronunciation_warnings`` so an unpronounceable tone is reported
    instead of silently dropped."""

    label: str
    tones: frozenset[ToneLevel]
    """The tones it can actually voice (empty: none, tone marks are dropped)."""
    notes: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "tones": [level.value for level in ToneLevel if level in self.tones],
            "notes": list(self.notes),
        }


_TONE_CHARACTERS = frozenset(TONE_DIACRITICS.values())
_SYMBOLS = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)


def tones_in(ipa_text: str) -> tuple[ToneLevel, ...]:
    """The tones carried by ``ipa_text`` (in order, with repeats)."""
    return ipa_tokenizer.tone_sequence(ipa_text, _SYMBOLS)


def strip_tone_marks(ipa_text: str) -> str:
    return "".join(ch for ch in ipa_text if ch not in _TONE_CHARACTERS)


def pronunciation_warnings(capabilities: TTSCapabilities, ipa_text: str) -> list[str]:
    """Human-readable alerts for the tones in ``ipa_text`` this engine cannot
    voice (empty when there are none, or the text has no tones)."""
    used = set(tones_in(ipa_text))
    missing = [level for level in ToneLevel if level in used and level not in capabilities.tones]
    if not missing:
        return []
    names = ", ".join(level.value for level in missing)
    if not capabilities.tones:
        return [
            f"{capabilities.label} cannot voice tones: the {names} tone marks in this text will be spoken without them."
        ]
    return [f"{capabilities.label} cannot voice the {names} tone(s) in this text: those syllables will be spoken without them."]


class TTSClient(Protocol):
    def synthesize(self, ipa_text: str, output_path: Path) -> bool:
        """Renders ``ipa_text`` to a ``.wav`` file at ``output_path``.
        Returns whether synthesis actually happened -- ``False`` for an
        unavailable backend or a failed external call, never an
        exception (a missing/broken TTS backend is a normal, expected
        state this project's own CLI reports cleanly, not a bug)."""
        ...

    def capabilities(self) -> TTSCapabilities:
        """What this engine can and cannot pronounce."""
        ...

    def for_utterance(self, ipa_text: str) -> "TTSClient":
        """The client to voice a whole sentence with -- ``self`` unless the
        engine needs a different voice for the sentence as a whole (eSpeak
        switches every word to its Mandarin voice when any word is tonal, so
        the sentence keeps one voice)."""
        ...


class NoneTTSClient:
    """The default -- no audio synthesis, matching this project's
    original "just print the IPA as text" behavior exactly."""

    def synthesize(self, ipa_text: str, output_path: Path) -> bool:
        return False

    def capabilities(self) -> TTSCapabilities:
        return TTSCapabilities("No audio", frozenset(), ("Shows the IPA and romanization as text only.",))

    def for_utterance(self, ipa_text: str) -> "TTSClient":
        return self


def _find_espeak_ng() -> str | None:
    found = shutil.which("espeak-ng")
    if found:
        return found
    for candidate in _ESPEAK_FALLBACK_PATHS:
        if Path(candidate).is_file():
            return candidate
    return None


_ESPEAK_TONE_VOICE = "cmn"
_ESPEAK_TONE_NUMBERS: dict[ToneLevel, str] = {
    # eSpeak's Mandarin voice reads a run of pitch-contour digits after a
    # vowel as that syllable's tone (5 = highest, 1 = lowest): "55" high
    # level, "35" rising, "214" dipping, "51" falling; "33"/"21" give a mid
    # and a low tone, and "11" its short, weak neutral tone. Verified by
    # synthesizing each and comparing lengths/pitch against the pinyin voice.
    ToneLevel.HIGH: "55",
    ToneLevel.RISING: "35",
    ToneLevel.DIPPING: "214",
    ToneLevel.FALLING: "51",
    ToneLevel.MID: "33",
    ToneLevel.LOW: "21",
    ToneLevel.NEUTRAL: "11",
}


class EspeakTTSClient:
    """Shells out to espeak-ng's own ``[[...]]`` Kirshenbaum bracket
    syntax (see ``speech.ipa_to_kirshenbaum``'s own docstring for why
    that conversion is needed at all -- espeak-ng has no direct IPA
    input). Tonal IPA is voiced with eSpeak's Mandarin voice, the only one
    with a tone mechanism: every tone becomes a contour-digit suffix on its
    vowel, and the language's other sounds are approximated by that voice's
    own inventory."""

    def __init__(self, voice: str = "en-us", tones: bool = False) -> None:
        self.voice = voice
        self.tones = tones

    def capabilities(self) -> TTSCapabilities:
        return TTSCapabilities(
            "eSpeak NG",
            frozenset(_ESPEAK_TONE_NUMBERS),
            (
                "Tones are voiced through eSpeak's Mandarin voice (contour digits 55/35/214/51, mid 33, "
                "low 21, neutral 11); a tonal sentence is spoken entirely in that voice.",
                "Sounds outside Mandarin's inventory, clicks and ejectives are approximated.",
                "Word-accent marks (stod, pitch accent) are not voiced.",
            ),
        )

    def for_utterance(self, ipa_text: str) -> "TTSClient":
        if self.tones or not tones_in(ipa_text):
            return self
        return EspeakTTSClient(voice=_ESPEAK_TONE_VOICE, tones=True)

    def synthesize(self, ipa_text: str, output_path: Path) -> bool:
        exe = _find_espeak_ng()
        if exe is None:
            return False
        tonal = self.tones or bool(tones_in(ipa_text))
        voice = _ESPEAK_TONE_VOICE if tonal else self.voice
        kirshenbaum = ipa_to_kirshenbaum.convert_word(ipa_text, _ESPEAK_TONE_NUMBERS if tonal else None)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [exe, "-v", voice, "-w", str(output_path), f"[[{kirshenbaum}]]"],
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

    def capabilities(self) -> TTSCapabilities:
        return TTSCapabilities(
            "Windows SAPI",
            frozenset(),
            (
                "Takes IPA directly through the installed voice (English by default).",
                "Cannot voice tones: SAPI rejects IPA tone marks (its Mandarin voices only accept grave/acute, "
                "as stress), so they are removed before speaking -- the words are still spoken, toneless.",
                "Sounds the voice lacks are approximated by it.",
            ),
        )

    def for_utterance(self, ipa_text: str) -> "TTSClient":
        return self

    def synthesize(self, ipa_text: str, output_path: Path) -> bool:
        if not sys.platform.startswith("win"):
            return False
        ipa_text = strip_tone_marks(ipa_text)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # SAPI silently writes an empty file for a precomposed character like
        # the nasalized vowel "ã" (U+00E3); the decomposed form (a + combining
        # tilde) is accepted.
        ipa_text = unicodedata.normalize("NFD", ipa_text)
        escaped_ipa = xml.sax.saxutils.escape(ipa_text, {'"': "&quot;"})
        script = _SAPI_SCRIPT_TEMPLATE.format(
            output_path=str(output_path).replace('"', '`"'), ipa=escaped_ipa
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
        )
        # A bare WAV header is 44 bytes -- anything that small is silence/empty.
        return result.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 44


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


def backend_capabilities() -> dict[str, dict]:
    """``{backend: capabilities}`` for every backend, for the UI's info line."""
    return {kind: build_tts_client(kind).capabilities().as_dict() for kind in ("none", "espeak", "sapi")}


__all__ = [
    "TTSClient", "TTSCapabilities", "NoneTTSClient", "EspeakTTSClient", "SapiTTSClient",
    "build_tts_client", "available_backends", "backend_capabilities", "pronunciation_warnings", "tones_in",
]
