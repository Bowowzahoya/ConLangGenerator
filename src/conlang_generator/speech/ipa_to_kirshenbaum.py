"""Converts this project's own IPA notation into espeak-ng's Kirshenbaum
ASCII-IPA phoneme mnemonics, for feeding into its ``[[...]]`` bracket
phonetic-input syntax -- espeak-ng has no *direct* IPA input (its own
``--ipa`` flag is output-only), so real synthesis from a word's stored IPA
needs this translation step first.

Kirshenbaum is a real, documented ASCII transliteration of IPA (not
espeak-ng's own arbitrary notation), so a systematic table is buildable --
but this project's own global phoneme pool
(``generation.phonology_gen.ALL_CONSONANTS``/``ALL_VOWELS``) models close
to 200 symbols, including several typologically exotic ones (click
clusters, pharyngealized/breathy/pre-aspirated consonants, apical-vs-
laminal distinctions) Kirshenbaum has no clean 1:1 equivalent for.
Illustrative, not exhaustive, the same honesty standard every other
curated table in this project already holds itself to: ``_BASE_BY_IPA``
covers every *plain* (unmodified) symbol directly; ``convert_symbol``
falls back to stripping a modifier (ejective/aspirated/palatalized/
pharyngealized/breathy/long/nasalized/apical/laminal/syllabic) one at a
time and re-checking the base table, approximating toward the nearest
representable phoneme rather than failing outright. Genuinely unmappable
symbols (most of the click-cluster combinations) fall back to their own
nearest manner-of-articulation letter.

Tone and word-accent marks have no real espeak-ng equivalent at all (it
has no lexical-tone input mechanism) and are dropped entirely -- a known,
permanent limitation, not something this module pretends to solve.
"""

from __future__ import annotations

import unicodedata

from conlang_generator.core.phonology import TONE_DIACRITICS, ToneLevel
from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK
from conlang_generator.generation import ipa_tokenizer, phonology_gen

_ALL_SYMBOLS: tuple[str, ...] = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(
    v.ipa for v in phonology_gen.ALL_VOWELS
)

_BASE_BY_IPA: dict[str, str] = {
    # --- Plain stops ---
    "p": "p", "b": "b", "t": "t", "d": "d", "k": "k", "g": "g", "ʔ": "?",
    "ʈ": "t.", "ɖ": "d.",  # retroflex -- Kirshenbaum's own dotted-diacritic convention
    "c": "c", "ɟ": "gj",  # palatal stops -- no clean single letter, approximated
    "q": "q", "ɢ": "g<",  # uvular stops
    "ɓ": "b`", "ɗ": "d`", "ʄ": "gj`", "ɠ": "g`",  # implosives -- Kirshenbaum's own trailing backtick
    # --- Affricates ---
    "tʃ": "tS", "dʒ": "dZ", "ts": "ts", "dz": "dz", "tɕ": "tS'", "dʑ": "dZ'",
    "tɬ": "tL", "tsʼ": "ts`", "tʃʼ": "tS`", "tɬʼ": "tL`",
    # --- Fricatives ---
    "s": "s", "z": "z", "ʃ": "S", "ʒ": "Z", "x": "x", "ɣ": "Q",
    "ʂ": "s.", "ʐ": "z.", "ɬ": "L", "ħ": "H", "ʕ": "?<",
    "f": "f", "v": "v", "h": "h", "θ": "T", "ð": "D", "ç": "C", "ʝ": "C<",
    "χ": "X", "ʁ": "g<",
    "β": "B", "ɸ": "P", "ɕ": "S'", "ʑ": "Z'", "ɦ": "h<",
    "ɭ": "l.", "ɽ": "*.", "ʈʂ": "ts.", "ɖʐ": "dz.", "ɴ": "N<", "ʋ": "v", "ɥ": "w",
    # --- Nasals ---
    "m": "m", "n": "n", "ŋ": "N", "ɳ": "n.", "ɲ": "nj",
    # --- Liquids/approximants ---
    "l": "l", "ɾ": "*", "r": "r", "j": "j", "w": "w", "ɻ": "r.", "ʎ": "lj",
    "rʲ": "r'",
    # --- Clicks (Kirshenbaum's own real click letters) ---
    "ǀ": "l!", "ǃ": "!", "ǂ": "c!", "ǁ": "lZ!",
    # --- Prenasalized/labial-velar clusters -- no real single-phoneme
    # equivalent; approximated as the plain oral stop (the nasal onset is
    # lost, an honest, documented simplification) ---
    "mb": "b", "nd": "d", "ŋg": "g", "nz": "z", "gb": "gb",
    # --- Plain vowels ---
    "i": "i", "a": "a", "u": "u", "e": "e", "o": "o", "ɛ": "E", "ɔ": "O",
    "ə": "@", "ɨ": "1", "ɪ": "I", "ʊ": "U", "æ": "&", "ɐ": "6", "ɑ": "A",
    "y": "y", "ø": "Y", "œ": "&2", "ɯ": "M", "ɤ": "7",
    "r̩": "3",  # syllabic r -- Kirshenbaum's own rhotic-vowel letter
}
"""Every *plain*, unmodified symbol this project's own phoneme pool has --
see this module's own docstring for the fallback strategy covering
everything else (modified consonants, long/nasalized/diphthong vowels,
click clusters)."""

_MODIFIER_STRIP: tuple[tuple[str, str], ...] = (
    ("ʼ", ""),   # ejective
    ("ʰ", ""),   # aspirated (also appears as a *prefix* on a few pre-aspirated symbols)
    ("ʲ", ""),   # palatalized
    ("ˤ", ""),   # pharyngealized
    ("ʱ", ""),   # breathy voiced
    ("ː", ":"),  # long -- Kirshenbaum's own length marker, appended rather than dropped
    ("̃", "~"),  # nasalized (combining tilde) -- Kirshenbaum's own nasalization marker
    ("̥", ""),   # combining ring below (voicelessness)
    ("̺", ""),   # combining inverted bridge below (apical)
    ("̻", ""),   # combining square below (laminal)
)
"""Modifier characters stripped, one at a time, when a symbol has no
direct ``_BASE_BY_IPA`` entry -- each strip re-checks the base table
against the remaining string, so e.g. ``"kʼ"`` (ejective k) falls back to
plain ``"k"``, ``"aː"`` (long a) becomes ``"a:"`` (Kirshenbaum's own
length notation, not silently dropped), and ``"ẽ"`` (nasalized e) becomes
``"e~"``. Order matters only in that length/nasalization are *appended*
to the resolved base rather than just deleted -- every other modifier is
a pure loss of distinctiveness, an honest approximation, not an error.

Matched against the **NFD-decomposed** form of the symbol (see
``convert_symbol``): a nasalized vowel like ``"ã"`` is stored precomposed
(one real Unicode codepoint, U+00E3) in this project's own phoneme pool,
unlike every other modifier here, which is already its own standalone
character -- normalizing first means both cases fall through the same
single code path instead of needing a separate one for nasalization."""


def convert_symbol(ipa_symbol: str) -> str:
    """Converts one IPA symbol (already tokenized -- see ``convert_word``)
    to its own Kirshenbaum mnemonic, falling back through
    ``_MODIFIER_STRIP`` when there's no direct entry, then (for a
    diphthong -- this project's own two-vowel compound symbols, e.g.
    ``"ai"``/``"au"``) trying to split it into two already-mapped base
    vowels. A genuinely unmappable symbol (most click-cluster
    combinations, e.g. ``"ŋǀʼ"``) falls back to its own nearest manner-
    of-articulation letter -- a click letter for a click cluster, ``"n"``
    for an unmapped nasal, or the symbol's own first character as a last
    resort, never a crash."""
    if ipa_symbol in _BASE_BY_IPA:
        return _BASE_BY_IPA[ipa_symbol]
    remaining = unicodedata.normalize("NFD", ipa_symbol)
    suffix = ""
    for modifier, replacement in _MODIFIER_STRIP:
        if modifier in remaining:
            remaining = remaining.replace(modifier, "")
            suffix += replacement
            if remaining in _BASE_BY_IPA:
                return _BASE_BY_IPA[remaining] + suffix
    for first_vowel, first_kirshenbaum in _BASE_BY_IPA.items():
        if ipa_symbol.startswith(first_vowel) and ipa_symbol[len(first_vowel):] in _BASE_BY_IPA:
            return first_kirshenbaum + _BASE_BY_IPA[ipa_symbol[len(first_vowel):]]
    # A click cluster (e.g. "ŋǀʼ") or other genuinely unmapped combination
    # -- fall back to whichever click letter it contains, else "n" for an
    # unmapped nasal cluster, else the first character as a last resort.
    for click, mnemonic in (("ǀ", "l!"), ("ǃ", "!"), ("ǂ", "c!"), ("ǁ", "lZ!")):
        if click in ipa_symbol:
            return mnemonic
    if ipa_symbol.startswith("ŋ"):
        return "N"
    return remaining[:1] if remaining else "@"


def convert_word(ipa_text: str, tone_numbers: dict[ToneLevel, str] | None = None) -> str:
    """Converts a whole word's own stored IPA (as ``LexicalEntry.ipa``
    stores it, including ``STRESS_MARK``/``WORD_ACCENT_MARK``/tone
    diacritics) into a Kirshenbaum phoneme string ready to wrap in
    ``[[...]]`` for espeak-ng. ``STRESS_MARK`` becomes Kirshenbaum's own
    leading ``'`` primary-stress marker (placed immediately before the
    stressed syllable's own onset, matching Kirshenbaum's convention of
    marking stress on the syllable, not the vowel); tone diacritics and
    ``WORD_ACCENT_MARK`` are dropped entirely (no real espeak-ng
    equivalent -- see this module's own docstring) unless ``tone_numbers``
    is given: a ``ToneLevel`` -> pitch-contour digits map (eSpeak's Mandarin
    voice reads ``A55``/``A35``/``A214``/``A51`` as its four tones), appended
    right after the tone-bearing vowel."""
    raw_tokens = ipa_tokenizer.tokenize(ipa_text, _ALL_SYMBOLS + (STRESS_MARK, WORD_ACCENT_MARK))
    out: list[str] = []
    pending_stress = False
    for symbol, deco in raw_tokens:
        if symbol == STRESS_MARK:
            pending_stress = True
            continue
        if symbol == WORD_ACCENT_MARK:
            continue
        piece = convert_symbol(symbol)
        if tone_numbers:
            tone = next((level for level, mark in TONE_DIACRITICS.items() if mark in deco), None)
            if tone is not None and tone in tone_numbers:
                piece += tone_numbers[tone]
        if pending_stress:
            piece = "'" + piece
            pending_stress = False
        out.append(piece)
    return "".join(out)
