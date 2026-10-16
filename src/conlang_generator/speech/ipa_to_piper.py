"""Converts this project's own IPA notation into a list of phoneme
strings ready for Piper's own ``PiperVoice.phonemes_to_ids`` -- Piper
has no direct multi-character-symbol input of its own; its model's
phoneme vocabulary (``phoneme_id_map`` in a voice's own ``.onnx.json``)
is a flat set of *atomic* IPA letters and diacritics, built from
espeak-ng's own universal phoneme repertoire (every voice is trained
via espeak-ng's own IPA phonemization, regardless of language --
confirmed directly against a real downloaded voice).

Unlike ``ipa_to_kirshenbaum.py`` (which must map each of this project's
own, sometimes multi-character, stored symbols onto a *single* ASCII
mnemonic token, since Kirshenbaum's own bracket notation needs one
token per symbol), Piper synthesizes from a flat *sequence* of phoneme
IDs anyway -- so the natural, highest-fidelity approach is simpler:
NFD-decompose a stored symbol into its own individual base letter(s)
and combining diacritics, and look each one up directly in the voice's
own vocabulary, rather than remapping the whole symbol onto a new
notation. Verified empirically against this project's own full global
phoneme pool (``generation.phonology_gen.ALL_CONSONANTS``/
``ALL_VOWELS``, 255 symbols): with one notation fix (this project's own
ASCII ``"g"`` -> the real IPA script ``"ɡ"`` Piper's vocabulary actually
uses) and three diacritics dropped (ejective, breathy, voiceless-ring --
genuinely absent from Piper's vocabulary, the same "a real distinction
was lost" standard ``ipa_to_kirshenbaum.py``'s own ``"approximate"``
rating already uses), every single one of those 255 symbols resolves
fully -- there is no "poor"-fidelity fallback table needed at all for
this project's own pool today (the ``"poor"`` path below exists only to
degrade gracefully for a future symbol this pool doesn't have yet, not
because any symbol in the real pool needs it).

Tone marks and ``WORD_ACCENT_MARK`` have no Piper equivalent (Piper has
no tone/pitch-accent mechanism at all) and are dropped entirely by
``convert_word`` -- the same permanent, documented limitation
``ipa_to_kirshenbaum.py`` already carries for eSpeak outside its own
Mandarin-voice tone switch.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Literal

from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK
from conlang_generator.generation import ipa_tokenizer, phonology_gen

Fidelity = Literal["exact", "approximate", "poor"]
"""Same meaning as ``ipa_to_kirshenbaum.Fidelity``: ``"exact"`` -- every
atom of the symbol maps directly, nothing dropped; ``"approximate"`` --
at least one real distinction (ejective/breathy/voiceless) was dropped
to reach a mapping, but the base sound survives; ``"poor"`` -- nothing
usable survived at all (not reached by any symbol in this project's own
pool today, see this module's own docstring)."""

_ALL_SYMBOLS: tuple[str, ...] = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(
    v.ipa for v in phonology_gen.ALL_VOWELS
)

_PIPER_VOICE_SYMBOLS_RAW = (
    # The real, complete `phoneme_id_map` keys (minus the "_"/"^"/"$"/
    # space special tokens) from `en_US-lessac-medium.onnx.json` -- read
    # directly from the real downloaded voice file, not guessed. Every
    # espeak-trained Piper voice shares this same universal vocabulary
    # (it comes from espeak-ng's own phoneme repertoire, not anything
    # English-specific), so this list is expected to hold for any future
    # espeak-based voice this project might add, not just this one.
    "! \" # ' ( ) , - . 0 1 2 3 4 5 6 7 8 9 : ; ? a b c d e f h i j k l m n o p q r s t u v w x y z "
    "æ ç ð ø ħ ŋ œ ǀ ǁ ǂ ǃ ɐ ɑ ɒ ɓ ɔ ɕ ɖ ɗ ɘ ə ɚ ɛ ɜ ɞ ɟ ɠ ɡ ɢ ɣ ɤ ɥ ɦ ɧ ɨ ɪ ɫ ɬ ɭ ɮ ɯ ɰ ɱ ɲ ɳ ɴ ɵ ɶ "
    "ɸ ɹ ɺ ɻ ɽ ɾ ʀ ʁ ʂ ʃ ʄ ʈ ʉ ʊ ʋ ʌ ʍ ʎ ʏ ʐ ʑ ʒ ʔ ʕ ʘ ʙ ʛ ʜ ʝ ʟ ʡ ʢ ʰ ʲ ˈ ˌ ː ˑ ˞ ˤ ̃ ̧ ̩ ̪ ̯ ̺ ̻ "
    "β ε θ χ ᵻ ↑ ↓ ⱱ"
)
_PIPER_VOICE_SYMBOLS: frozenset[str] = frozenset(_PIPER_VOICE_SYMBOLS_RAW.split())

_NOTATION_FIX: dict[str, str] = {
    "g": "ɡ",  # this project's own ASCII "g" (see core/phonology.py's own convention) ->
    # the real IPA script g Piper's vocabulary actually uses -- a notation fix, not an approximation.
}

_DROPPED_DIACRITICS: frozenset[str] = frozenset(
    "ʼ"  # ejective (ʼ)
    "̥"  # voiceless ring below (̥)
    "ʱ"  # breathy voice (ʱ)
)
"""Confirmed genuinely absent from the real voice's own vocabulary
(empirically, not guessed) -- dropping each is a real, documented loss
of a distinction, the same "approximate" standard
``ipa_to_kirshenbaum.py`` already applies to the same three features."""


@dataclass(frozen=True)
class SymbolConversion:
    phonemes: tuple[str, ...]
    fidelity: Fidelity


def convert_symbol(ipa_symbol: str) -> SymbolConversion:
    """Converts one IPA symbol (already tokenized -- see ``convert_word``)
    into a sequence of Piper phoneme strings. NFD-decomposes the symbol
    into its own base letter(s) and combining diacritics, maps each atom
    through ``_NOTATION_FIX`` if needed, drops any of
    ``_DROPPED_DIACRITICS``, and keeps whatever atom remains if it's a
    real entry in the voice's own vocabulary -- an atom that's neither
    droppable nor present is also dropped (never crashes), so a future
    symbol this project's pool doesn't have yet still degrades
    gracefully rather than failing outright."""
    phonemes: list[str] = []
    lossy = False
    for atom in unicodedata.normalize("NFD", ipa_symbol):
        if atom in _DROPPED_DIACRITICS:
            lossy = True
            continue
        mapped = _NOTATION_FIX.get(atom, atom)
        if mapped in _PIPER_VOICE_SYMBOLS:
            phonemes.append(mapped)
        else:
            lossy = True
    if not phonemes:
        return SymbolConversion((), "poor")
    return SymbolConversion(tuple(phonemes), "approximate" if lossy else "exact")


def convert_word(ipa_text: str) -> list[str]:
    """Converts a whole word's own stored IPA (as ``LexicalEntry.ipa``
    stores it, including ``STRESS_MARK``/``WORD_ACCENT_MARK``/tone
    diacritics) into a flat list of Piper phoneme strings, ready for
    ``PiperVoice.phonemes_to_ids``. ``STRESS_MARK`` ("ˈ") is itself a
    real entry in Piper's own vocabulary and needs no repositioning
    (unlike Kirshenbaum's own notation, Piper's phoneme vocabulary is
    already real IPA, and this project already stores ``STRESS_MARK``
    directly before the syllable it marks, standard IPA convention).
    ``WORD_ACCENT_MARK`` and every tone diacritic have no Piper
    equivalent and are dropped entirely -- see this module's own
    docstring."""
    raw_tokens = ipa_tokenizer.tokenize(ipa_text, _ALL_SYMBOLS + (STRESS_MARK, WORD_ACCENT_MARK))
    out: list[str] = []
    for symbol, _deco in raw_tokens:
        if symbol == WORD_ACCENT_MARK:
            continue
        out.extend(convert_symbol(symbol).phonemes)
    return out


__all__ = ["SymbolConversion", "convert_symbol", "convert_word"]
