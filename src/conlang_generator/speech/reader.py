"""Placeholder for reading text aloud in the conlang.

v0 limitation: no audio synthesis. This only surfaces the stored IPA and
romanization for a known word so a human can read it aloud themselves.
Actual TTS (or a generated custom font, per the long-term plan) is future
work -- explicitly not pretended here.
"""

from __future__ import annotations

from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import LexicalEntry


def lookup_pronunciation(language: Language, word_or_gloss: str) -> LexicalEntry | None:
    return language.lexicon.by_gloss(word_or_gloss) or language.lexicon.by_form(word_or_gloss)


def describe(entry: LexicalEntry) -> str:
    return f"IPA: /{entry.ipa}/  Romanized: {entry.romanization}"
