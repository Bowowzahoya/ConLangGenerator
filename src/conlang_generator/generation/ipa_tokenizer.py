"""Greedy longest-match tokenization of an IPA string against a known
symbol set -- same approach as ``RomanizationScheme.apply``. Decoration-
aware: trailing Unicode combining marks (tone diacritics) stay attached to
the base symbol they modify instead of being dropped, so a word can be
pulled apart into segments and reassembled later without losing
information (needed by ``generation/sound_change.py``, which rewrites
individual segments while preserving tone).

Shared between ``phonology_gen.py`` (which only needs "which phonemes
appear," via ``symbols_only``) and ``sound_change.py`` (which needs the
full decoration-aware structure).
"""

from __future__ import annotations

import functools
import unicodedata

from conlang_generator.core.phonology import TONE_DIACRITICS, ToneLevel
from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK

_STANDALONE_MARKS = (STRESS_MARK, WORD_ACCENT_MARK)
_ARTICULATION_MODIFIERS = "ʱʰʼ"


def _strands_a_modifier(text: str, end: int) -> bool:
    """Whether a match ending at ``end`` leaves a breathy ``ʱ``, aspirated ``ʰ`` or
    ejective ``ʼ`` mark stranded at the front of the rest -- a sign the greedy match
    ate the wrong sounds: in ``ŋgʱ`` the prenasalized ``ŋg`` would leave ``ʱ``
    orphaned, whereas ``ŋ`` + ``gʱ`` reads it whole. (Length ``ː`` is deliberately
    not covered: ``tsː`` keeps reading as ``ts`` + a stray ``ː``, which is why
    ``sonority`` refuses the pair ``t`` + ``sː``.)"""
    return end < len(text) and text[end] in _ARTICULATION_MODIFIERS


@functools.lru_cache(maxsize=64)
def _ordered_by_first_char(known: frozenset[str]) -> dict[str, tuple[str, ...]]:
    """``known`` grouped by first character, longest first."""
    grouped: dict[str, list[str]] = {}
    for symbol in sorted(known, key=len, reverse=True):
        if symbol:
            grouped.setdefault(symbol[0], []).append(symbol)
    return {first: tuple(symbols) for first, symbols in grouped.items()}


def tokenize(text: str, known_symbols: tuple[str, ...]) -> list[tuple[str, str]]:
    """Returns ``(symbol, trailing_combining_marks)`` pairs. ``STRESS_MARK``
    and ``WORD_ACCENT_MARK`` (the ``"glottalization"``-realization word-
    accent mark -- real Danish stød) each become their own token
    (``(mark, "")``, never a decoration on another token) -- unlike
    ``core.romanization``'s own ``_tokenize`` (a single, non-mutating
    pass, which pulls ``STRESS_MARK`` out as a side-channel index
    instead), keeping them as genuine list entries here lets them move
    naturally with their neighbors through ``sound_change.py``'s own
    token-list mutations (only ``_simplify_clusters`` deletes a token
    today, but future rules could too) with no separate index to keep in
    sync. The ``"pitch"``-realization word-accent marks need no such
    handling -- they're ordinary Unicode combining characters (reused
    from ``core.phonology.TONE_DIACRITICS``), already covered by the
    trailing-combining-mark slurp below the same way tone diacritics
    always have been. Every other unrecognized, non-combining character
    is silently skipped -- unrecognized input, not an error."""
    ordered = _ordered_by_first_char(frozenset(known_symbols))
    tokens: list[tuple[str, str]] = []
    i = 0
    while i < len(text):
        if text[i] in _STANDALONE_MARKS:
            tokens.append((text[i], ""))
            i += 1
            continue
        candidates = [s for s in ordered.get(text[i], ()) if text.startswith(s, i)]
        matched = next((s for s in candidates if not _strands_a_modifier(text, i + len(s))), None)
        if matched is None and candidates:
            matched = candidates[0]  # every reading strands one: keep plain longest-match
        if matched is None:
            if tokens and unicodedata.combining(text[i]):
                symbol, deco = tokens[-1]
                tokens[-1] = (symbol, deco + text[i])
            i += 1
            continue
        i += len(matched)
        deco = ""
        while i < len(text) and unicodedata.combining(text[i]):
            deco += text[i]
            i += 1
        tokens.append((matched, deco))
    return tokens


def symbols_only(text: str, known_symbols: tuple[str, ...]) -> tuple[str, ...]:
    """Just the base symbols, decorations discarded -- for "which phonemes
    appear" queries. ``STRESS_MARK``/``WORD_ACCENT_MARK`` are deliberately
    excluded here (unlike ``tokenize``'s own full output) -- neither is a
    phoneme, and every caller of this function is asking "which sounds
    does this word use," a question stress/word accent have no part in."""
    return tuple(symbol for symbol, _ in tokenize(text, known_symbols) if symbol not in _STANDALONE_MARKS)


_LEVEL_BY_MARK = {mark: level for level, mark in TONE_DIACRITICS.items()}


def tone_sequence(text: str, known_symbols: tuple[str, ...]) -> tuple[ToneLevel, ...]:
    """The tone (a ``TONE_DIACRITICS`` combining mark) carried by each
    tone-bearing segment of ``text``, in order -- empty for an untoned word.
    Only the tone marks count; any other combining decoration is ignored."""
    tones = []
    for _, deco in tokenize(text, known_symbols):
        level = next((_LEVEL_BY_MARK[c] for c in deco if c in _LEVEL_BY_MARK), None)
        if level is not None:
            tones.append(level)
    return tuple(tones)


def strip_tones(text: str) -> str:
    """``text`` without its tone marks (other combining marks stay)."""
    return "".join(c for c in text if c not in _LEVEL_BY_MARK)
