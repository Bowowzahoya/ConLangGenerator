"""Tone sandhi at the utterance level: a language's ``ToneSystem.sandhi``
rules rewrite the tone marks of adjacent syllables when words are spoken in
sequence, while every lexicon entry keeps its citation tones.

Rules read each syllable's pair from the citation tones (so Mandarin's
third-tone rule turns dipping-dipping-dipping into rising-rising-dipping)
over the whole utterance's tone-bearing syllables and see across word
boundaries, which is where most sandhi is audible. Each rule's own
``target`` (see ``core.phonology.ToneSandhiRule``'s own docstring) says
which of its two syllables actually changes -- ``"before"`` (the common,
Mandarin-shaped case) rewrites the *earlier* one, ``"after"`` (real Bantu
Meeussen's Rule) the *later* one. When a syllable could be rewritten both
ways in the same pass -- once as some rule's own ``"after"`` target from
its *left* neighbor's own check, and again as a *different* rule's own
``"before"`` target from its own check one position later -- the second
(rightward, later-iterating) write wins; both checks always read the
same original citation tones, never each other's output, so this is the
only order-dependence that can arise, and it's a deliberate, simple
tie-break rather than a cascading multi-pass resolution.

``ToneSystem.lexical_sandhi`` (real Mandarin 不 "not" / 一 "one", each
changing tone before a specific following tone, but *only* for that one
word, not any syllable that happens to share its tone -- see
``LexicalToneSandhiRule``'s own docstring for why this needs gloss
identity, not just tone context) is applied as a second pass, after the
general ``sandhi`` pass above: it reads each word's own *already*
general-sandhi'd neighbor tone (the real, as-spoken tone a listener
actually hears next), which only ``apply_sandhi`` itself -- not a caller
-- is in a position to compute, so this couldn't be layered on
separately outside this function."""

from __future__ import annotations

from conlang_generator.core.phonology import TONE_DIACRITICS, ToneSystem
from conlang_generator.generation import ipa_tokenizer, phonology_gen

_SYMBOLS = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)


def apply_sandhi(ipa_words: list[str], tone_system: ToneSystem, glosses: list[str | None] | None = None) -> list[str]:
    """``ipa_words`` with the language's sandhi rules applied across them
    (unchanged when the language has no tone system or no rules).
    ``glosses`` (one entry per ``ipa_words``, ``None`` for a word with no
    gloss to track, or omitted entirely) is only ever consulted for
    ``ToneSystem.lexical_sandhi`` -- the general ``sandhi`` pass has
    never needed word identity and still doesn't. A word with more than
    one tone-bearing syllable is tracked on its own *last* one (the
    syllable immediately preceding whatever comes next, real or another
    word) -- irrelevant for Mandarin's own monosyllabic 不/一, but keeps
    the mechanism correct for a hypothetically polysyllabic tracked
    gloss too."""
    if not tone_system.enabled or not (tone_system.sandhi or tone_system.lexical_sandhi):
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
                if rule.target == "before":
                    tones[index] = rule.becomes
                else:
                    tones[index + 1] = rule.becomes
                break

    if tone_system.lexical_sandhi and glosses is not None:
        lexical_by_gloss: dict[str, dict] = {}
        for rule in tone_system.lexical_sandhi:
            lexical_by_gloss.setdefault(rule.gloss, {})[rule.before] = rule.becomes
        # A tracked word's own *last* tone-bearing slot is the one that's
        # actually "before" whatever comes next -- found by only keeping
        # each word index's own final match while scanning in order.
        last_slot_by_word: dict[int, int] = {}
        for slot_index, (w, _, _) in enumerate(slots):
            last_slot_by_word[w] = slot_index
        for w, gloss in enumerate(glosses):
            if gloss is None or gloss not in lexical_by_gloss:
                continue
            slot_index = last_slot_by_word.get(w)
            if slot_index is None or slot_index + 1 >= len(tones):
                continue  # utterance-final/isolated -- real citation tone stands, same as 不/一 said alone
            next_tone = tones[slot_index + 1]
            becomes = lexical_by_gloss[gloss].get(next_tone)
            if becomes is not None:
                tones[slot_index] = becomes

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
