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


def tokenize(text: str, known_symbols: tuple[str, ...]) -> list[tuple[str, str]]:
    """Returns ``(symbol, trailing_combining_marks)`` pairs. Characters that
    don't start a known symbol and aren't a combining mark following one
    are silently skipped -- unrecognized input, not an error."""
    ordered = sorted(set(known_symbols), key=len, reverse=True)
    tokens: list[tuple[str, str]] = []
    i = 0
    while i < len(text):
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
    appear" queries."""
    return tuple(symbol for symbol, _ in tokenize(text, known_symbols))
