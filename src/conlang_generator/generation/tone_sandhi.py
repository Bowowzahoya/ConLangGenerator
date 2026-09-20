"""Tone sandhi at the utterance level: a language's ``ToneSystem.sandhi``
rules rewrite the tone marks of adjacent syllables when words are spoken in
sequence, while every lexicon entry keeps its citation tones.

Rules read each syllable's pair from the citation tones (so Mandarin's
third-tone rule turns dipping-dipping-dipping into rising-rising-dipping)
over the whole utterance's tone-bearing syllables and see across word boundaries, which is where most
sandhi is audible. Lexically specific sandhi (Mandarin 不/一 changing before
a falling tone) is not expressible as a tone-context rule and stays
unmodeled.
"""

from __future__ import annotations

from conlang_generator.core.phonology import TONE_DIACRITICS, ToneSystem
from conlang_generator.generation import ipa_tokenizer, phonology_gen

_SYMBOLS = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)


def apply_sandhi(ipa_words: list[str], tone_system: ToneSystem) -> list[str]:
    """``ipa_words`` with the language's sandhi rules applied across them
    (unchanged when the language has no tone system or no rules)."""
    if not tone_system.enabled or not tone_system.sandhi:
        return list(ipa_words)
    tokenized = [ipa_tokenizer.tokenize(word, _SYMBOLS) for word in ipa_words]
    # (word index, token index, tone) for each tone-bearing syllable, in order
    slots = []
    for w, tokens in enumerate(tokenized):
        for i, (_, deco) in enumerate(tokens):
            tone = _tone_of(deco)
            if tone is not None:
                slots.append((w, i, tone))
    citation = [tone for _, _, tone in slots]
    tones = list(citation)
    for index in range(len(citation) - 1):
        for rule in tone_system.sandhi:
            if citation[index] == rule.before and citation[index + 1] == rule.after:
                tones[index] = rule.becomes
                break
    for (w, i, old), new in zip(slots, tones):
        if new != old:
            symbol, deco = tokenized[w][i]
            deco = deco.replace(TONE_DIACRITICS[old], TONE_DIACRITICS[new])
            tokenized[w][i] = (symbol, deco)
    return [_join(tokens) for tokens in tokenized]


def _tone_of(deco: str):
    return next((level for level, mark in TONE_DIACRITICS.items() if mark in deco), None)


def _join(tokens: list[tuple[str, str]]) -> str:
    return "".join(symbol + deco for symbol, deco in tokens)
