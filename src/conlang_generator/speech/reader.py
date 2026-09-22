"""Placeholder for reading text aloud in the conlang.

v0 limitation: no audio synthesis. This only surfaces the stored IPA and
romanization for a known word so a human can read it aloud themselves.
Actual TTS (or a generated custom font, per the long-term plan) is future
work -- explicitly not pretended here.
"""

from __future__ import annotations

from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import LexicalEntry
from conlang_generator.core.phonology import TONE_CONTOURS, chao_letters


def lookup_pronunciation(language: Language, word_or_gloss: str) -> LexicalEntry | None:
    return language.lexicon.by_gloss(word_or_gloss) or language.lexicon.by_form(word_or_gloss)


def describe(entry: LexicalEntry) -> str:
    base = f"IPA: /{entry.ipa}/  Romanized: {entry.romanization}"
    if not entry.tones:
        return base
    # entry.ipa already carries each syllable's own tone as a combining
    # diacritic (TONE_DIACRITICS) -- this is a separate, phonetically
    # fuller register+contour view of the same stored tones (real Chao
    # tone-letter glyphs, plus their own pitch-level digits), not a
    # different fact, one pair per tone-bearing syllable in order.
    contour = " ".join(f"{chao_letters(tone)} ({TONE_CONTOURS[tone]})" for tone in entry.tones)
    return f"{base}  Tone contour: {contour}"
