"""Eagerly pre-synthesizes every lexicon entry's own spoken pronunciation
into the TTS audio cache (``speech.tts_cache``), so the *first* real
pronunciation request for any word is as fast as a repeat one -- an
explicit opt-in (see ``docs/DEFERRED.md``), never automatic: synthesizing
a several-hundred-word lexicon takes real wall-clock time, and -- once a
paid engine exists -- could cost real money.

Real per-word synthesis time varies hugely by engine (measured directly):
eSpeak-ng is fast (~60ms/word), but Windows SAPI pays a fresh PowerShell
+ .NET process-startup cost on *every one-shot call* (~3.7s/word) -- so
``"sapi"``, or ``"auto"`` (which can tie-break onto SAPI for any word
both engines voice exactly -- see ``speech.engine_selection.
NATURALNESS``), used to take on the order of tens of minutes for a
several-hundred-word vocabulary. Fixed here: a shared ``speech.sapi_
worker.SapiWorker`` (one persistent process, reused across every word
that needs it) is built once per call -- never per word -- whenever
``kind`` can possibly touch SAPI, so only the very first SAPI word in a
run pays that startup cost."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from conlang_generator.core.language import Language
from conlang_generator.generation.tone_sandhi import apply_sandhi
from conlang_generator.speech import engine_selection, tts, tts_cache
from conlang_generator.speech.sapi_worker import SapiWorker


@dataclass(frozen=True)
class PregenerateSummary:
    total: int
    synthesized: int
    failed: int


def pregenerate_audio(
    language: Language,
    kind: str,
    cache_dir: Path,
    on_progress: Callable[[int, int], None] | None = None,
) -> PregenerateSummary:
    """Synthesizes (and caches) every lexicon entry's own spoken
    pronunciation -- the same tone-sandhi-adjusted form ``cli.main.
    pronounce`` already derives for a single word, applied here across
    the whole lexicon. ``kind`` is ``"espeak"``/``"sapi"``/``"auto"`` --
    never call this with ``"none"`` (nothing to pre-generate).
    ``on_progress(done, total)``, when given, is called after every word
    (whether its own synthesis succeeded or not) -- the only way a
    caller can show real progress, since this function has no notion of
    a CLI or an HTTP response."""
    entries = language.lexicon.entries
    total = len(entries)
    if total == 0:
        return PregenerateSummary(0, 0, 0)
    audio_dir = cache_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    tts_cache_dir = cache_dir / "tts_cache"
    # Built once per call, never per word -- SapiWorker() itself is cheap
    # (no process spawned until the first real synthesize call), so an
    # "auto" run that never actually picks SAPI for any word never pays
    # the PowerShell startup cost at all.
    worker = SapiWorker() if kind in ("sapi", "auto") else None
    try:
        fixed_client = (
            tts_cache.CachingTTSClient(tts.build_tts_client(kind, sapi_worker=worker), tts_cache_dir)
            if kind != "auto" else None
        )
        engine_kinds = tts.available_engine_kinds()
        synthesized = 0
        failed = 0
        for i, entry in enumerate(entries, start=1):
            spoken_ipa = apply_sandhi([entry.ipa], language.tone_system, [entry.primary_gloss])[0]
            if fixed_client is not None:
                client = fixed_client
            else:
                choice = engine_selection.choose_engine(spoken_ipa, engine_kinds)
                client = (
                    tts_cache.CachingTTSClient(tts.build_tts_client(choice.kind, sapi_worker=worker), tts_cache_dir)
                    if choice is not None else tts.NoneTTSClient()
                )
            temp_path = audio_dir / f"pregenerate-{uuid.uuid4().hex}.wav"
            try:
                ok = client.synthesize(spoken_ipa, temp_path)
            finally:
                temp_path.unlink(missing_ok=True)
            if ok:
                synthesized += 1
            else:
                failed += 1
            if on_progress is not None:
                on_progress(i, total)
        return PregenerateSummary(total, synthesized, failed)
    finally:
        if worker is not None:
            worker.close()


__all__ = ["PregenerateSummary", "pregenerate_audio"]
