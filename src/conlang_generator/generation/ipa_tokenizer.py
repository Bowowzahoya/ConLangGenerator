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

import unicodedata

from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK

_STANDALONE_MARKS = (STRESS_MARK, WORD_ACCENT_MARK)


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
    ordered = sorted(set(known_symbols), key=len, reverse=True)
    tokens: list[tuple[str, str]] = []
    i = 0
    while i < len(text):
        if text[i] in _STANDALONE_MARKS:
            tokens.append((text[i], ""))
            i += 1
            continue
        matched = next((s for s in ordered if text.startswith(s, i)), None)
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
