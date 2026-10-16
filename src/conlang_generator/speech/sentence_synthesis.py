"""Stitches several words' own separately-synthesized ``.wav`` files into
one combined in-memory sentence recording -- every real ``TTSClient.
synthesize`` is documented as a *word's* own IPA -> one ``.wav`` file,
which neither backend's own single-``[[...]]``/single-``<phoneme>`` call
is built to span, so a multi-word sentence needs this extra assembly
step. Shared by ``cli/main.py``'s ``translate --tts`` and ``webui/
app.py``'s ``/api/pronounce`` -- the two call sites that both need a
full sentence's audio, not just one word's.
"""

from __future__ import annotations

import io
import uuid
import wave
from collections.abc import Callable
from pathlib import Path

from conlang_generator.speech.tts import TTSClient

INTER_WORD_SILENCE_SECONDS = 0.05
"""Was 0.15 -- reported as noticeably too long for a translated sentence
to sound natural at all; real sentence-level prosody stays out of scope
(see docs/DEFERRED.md), this just shortens the gap between words."""


def synthesize_sentence(
    client_for_word: Callable[[str], TTSClient], ipa_sentence: str, audio_dir: Path,
) -> bytes | None:
    """Synthesizes each word of ``ipa_sentence`` separately (via
    ``client_for_word``, a plain ``lambda w: client`` for a fixed-engine
    caller, or ``engine_selection.auto_client_for_word``'s own per-word
    choice for ``"auto"``), into its own temp file under ``audio_dir``,
    then concatenates the raw PCM frames (with a short silence between
    words for intelligibility) into one combined in-memory ``.wav`` --
    ``None`` if every word's own synthesis fails, matching every
    ``TTSClient``'s own "unavailable/failed is a normal, non-exceptional
    state" contract. ``audio_dir`` is the caller's own temp-file
    location; each real client's own ``synthesize`` already creates it
    via ``output_path.parent.mkdir(parents=True, exist_ok=True)``."""
    words = ipa_sentence.split()
    if not words:
        return None
    temp_paths = [audio_dir / f"sentence-{uuid.uuid4().hex}.wav" for _ in words]
    try:
        params = None
        silence = b""
        frames: list[bytes] = []
        for word_ipa, path in zip(words, temp_paths):
            # A word the backend can't render (or renders as an unreadable
            # file) is skipped rather than failing the whole sentence.
            try:
                if not client_for_word(word_ipa).synthesize(word_ipa, path):
                    continue
                with wave.open(str(path), "rb") as wf:
                    if params is None:
                        params = wf.getparams()
                        silence = b"\x00" * int(INTER_WORD_SILENCE_SECONDS * params.framerate) * params.sampwidth * params.nchannels
                    elif (wf.getframerate(), wf.getnchannels(), wf.getsampwidth()) != (
                        params.framerate, params.nchannels, params.sampwidth,
                    ):
                        continue
                    frames.append(wf.readframes(wf.getnframes()))
            except (wave.Error, EOFError):
                continue
        if not frames:
            return None
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as out:
            out.setparams(params)
            for i, frame in enumerate(frames):
                if i > 0:
                    out.writeframesraw(silence)
                out.writeframesraw(frame)
        return buffer.getvalue()
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)


__all__ = ["INTER_WORD_SILENCE_SECONDS", "synthesize_sentence"]
