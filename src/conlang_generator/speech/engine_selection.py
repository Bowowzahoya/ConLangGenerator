"""Picks, for one word at a time, whichever available TTS engine covers
its sounds best -- never splicing different engines together within a
single word (matching pitch/timbre/volume at the seam would be its own
separate, harder problem, deliberately not taken on here). Ties between
equally-covering engines break on a small, explicitly subjective
naturalness rank, not coverage.

This is the ``"auto"`` engine value's own implementation -- handled
entirely by the caller (``webui/app.py``, ``cli/main.py``), never inside
``speech.tts.build_tts_client``, since a per-word choice needs a
*different* client per word, not one client for a whole call.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from conlang_generator.speech import phoneme_coverage, tts
from conlang_generator.speech.ipa_to_kirshenbaum import Fidelity
from conlang_generator.speech.phoneme_coverage import FIDELITY_RANK
from conlang_generator.speech.tts import TTSClient

NATURALNESS: dict[str, int] = {"sapi": 2, "espeak": 1}
"""Explicitly subjective, revisit when a new engine (Piper, ...) joins
the roster -- SAPI's real, recorded-voice-based OS synthesizer is rated
above eSpeak's formant synthesis for any sound both render correctly."""


@dataclass(frozen=True)
class EngineChoice:
    kind: str
    fidelity: Fidelity
    notes: tuple[str, ...]
    """Non-empty exactly when ``fidelity`` isn't ``"exact"`` -- why even
    the best available engine still falls short, for the caller to
    report rather than silently swallow."""


def choose_engine(ipa_word: str, candidates: Sequence[str]) -> EngineChoice | None:
    """The single best engine among ``candidates`` for this one word --
    highest ``word_fidelity``, ties broken by ``NATURALNESS``. ``None``
    when ``candidates`` is empty (nothing usable on this machine)."""
    if not candidates:
        return None
    best = max(
        candidates,
        key=lambda kind: (FIDELITY_RANK[phoneme_coverage.word_fidelity(ipa_word, kind)], NATURALNESS.get(kind, 0)),
    )
    fidelity = phoneme_coverage.word_fidelity(ipa_word, best)
    notes = () if fidelity == "exact" else phoneme_coverage.describe_gap(ipa_word, best)
    return EngineChoice(best, fidelity, notes)


def auto_client_for_word(ipa_sentence: str, candidate_kinds: Sequence[str]) -> Callable[[str], TTSClient]:
    """A ``word -> TTSClient`` function for voicing a whole sentence with
    automatic per-word engine choice. Resolves ``for_utterance`` once per
    *engine kind actually used in this sentence*, against only the words
    assigned to it -- not per bare word, and not over the raw whole
    sentence. This matters: eSpeak's own ``for_utterance`` decides "any
    tonal word anywhere in this sentence -> speak the *entire* sentence
    in the Mandarin voice" so a toneless word next to a tonal one doesn't
    switch voices mid-sentence; grouping by assigned engine first
    preserves that guarantee within eSpeak's own share of a mixed-engine
    sentence instead of silently breaking it."""
    words = ipa_sentence.split()
    choice_by_word = {word: choose_engine(word, candidate_kinds) for word in set(words)}
    words_by_kind: dict[str, list[str]] = {}
    for word in words:
        choice = choice_by_word[word]
        if choice is not None:
            words_by_kind.setdefault(choice.kind, []).append(word)
    resolved = {
        kind: tts.build_tts_client(kind).for_utterance(" ".join(assigned))
        for kind, assigned in words_by_kind.items()
    }
    none_client = tts.NoneTTSClient()

    def client_for_word(word: str) -> TTSClient:
        choice = choice_by_word.get(word)
        return resolved[choice.kind] if choice is not None else none_client

    return client_for_word


def auto_pronunciation_warnings(ipa_sentence: str, candidate_kinds: Sequence[str]) -> list[str]:
    """One warning per distinct word whose best available engine falls
    short of ``"exact"``, or has none at all -- the "report, not
    silently drop" deliverable for the ``"auto"`` path."""
    warnings: list[str] = []
    for word in dict.fromkeys(ipa_sentence.split()):  # dedup, preserve order
        choice = choose_engine(word, candidate_kinds)
        if choice is None:
            warnings.append(f"No TTS engine available to voice '{word}'.")
        elif choice.fidelity != "exact":
            warnings.append(
                f"'{word}' is only {choice.fidelity}ly covered by {tts.build_tts_client(choice.kind).capabilities().label}: "
                f"{'; '.join(choice.notes)}."
            )
    return warnings


__all__ = ["NATURALNESS", "EngineChoice", "choose_engine", "auto_client_for_word", "auto_pronunciation_warnings"]
