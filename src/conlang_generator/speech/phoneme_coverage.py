"""Per-engine, per-phoneme coverage: how faithfully eSpeak-ng and Windows
SAPI can actually voice this project's own ~200-symbol phoneme pool, not
just whether they voice tones (``speech.tts.TTSCapabilities``'s only
dimension today).

- ``"espeak"``: fidelity comes straight from ``speech.ipa_to_kirshenbaum.
  convert_symbol``'s own ``Fidelity`` rating -- that module already knows
  whether a symbol hit a clean 1:1 mapping, a lossy modifier-strip
  fallback, or a last-resort fallback, so this is a single source of
  truth, not a second table that could drift from the first.
- ``"sapi"``: SAPI takes literal IPA straight through to an opaque real
  OS voice (no conversion step exists to introspect), so there is no
  derivable signal -- only a small, honestly-scoped curated table of the
  plain IPA symbols that are literal members of a standard American-
  English phoneme inventory (``SAPI_EXACT_SYMBOLS``). Everything else is
  rated by the same ``Consonant``/``Vowel`` feature flags eSpeak's own
  approximations are explained with, not a separate judgment call.

Both engines' tone handling is already known from direct testing
(``speech.tts``): eSpeak voices every ``ToneLevel`` via its Mandarin
voice; SAPI strips tone marks entirely. ``word_fidelity`` folds that in
for SAPI; eSpeak needs no such override since nothing here degrades it.
"""

from __future__ import annotations

from conlang_generator.core.phonology import CLICK_CHARACTERS, Place
from conlang_generator.generation import ipa_tokenizer, phonology_gen
from conlang_generator.speech import ipa_to_kirshenbaum
from conlang_generator.speech.ipa_to_kirshenbaum import Fidelity

_ALL_SYMBOLS: tuple[str, ...] = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(
    v.ipa for v in phonology_gen.ALL_VOWELS
)
_CONSONANT_BY_IPA = {c.ipa: c for c in phonology_gen.ALL_CONSONANTS}

FIDELITY_RANK: dict[Fidelity, int] = {"poor": 0, "approximate": 1, "exact": 2}
"""Lower is worse -- used to find the *worst* fidelity across a word's
own symbols, and (by ``speech.engine_selection``) to compare engines
against each other."""

SAPI_EXACT_SYMBOLS: frozenset[str] = frozenset(
    {
        # Consonants (24) -- a standard American-English consonant
        # inventory. "r" stands in for English's real "ɹ", which isn't in
        # this project's own phoneme pool at all -- the closest available
        # symbol, not a phonetically exact match, same honesty-with-a-
        # footnote standard the rest of this project already holds.
        "p", "b", "t", "d", "k", "g", "tʃ", "dʒ", "f", "v", "θ", "ð",
        "s", "z", "ʃ", "ʒ", "h", "m", "n", "ŋ", "l", "r", "j", "w",
        # Vowels/diphthongs (~15) -- the plain monophthongs/diphthongs
        # already in the pool; excludes ɨ, front-rounded y/ø/œ, ɯ/ɤ.
        "i", "u", "e", "o", "a", "ɛ", "ɔ", "ə", "ɪ", "ʊ", "æ", "ɑ", "ai", "au", "ei",
    }
)
"""The plain IPA symbols a standard English SAPI voice plausibly renders
correctly. Deliberately small and principled (a real English phoneme
inventory, cross-checked against this project's own pool) rather than a
guess -- everything outside it falls through to ``_is_sapi_poor``'s
feature-flag check instead of being asserted "exact" without evidence."""


def _is_sapi_poor(symbol: str) -> bool:
    """A sound a standard English voice almost certainly can't even
    approximate -- not merely foreign to English (that's "approximate"),
    but phonetically absent from it altogether."""
    if any(ch in CLICK_CHARACTERS for ch in symbol):
        return True
    consonant = _CONSONANT_BY_IPA.get(symbol)
    if consonant is None:
        return False  # vowels never set these flags
    return consonant.ejective or consonant.breathy or consonant.pharyngealized or consonant.place is Place.PHARYNGEAL


def symbol_fidelity(symbol: str, engine: str) -> Fidelity:
    if engine == "espeak":
        return ipa_to_kirshenbaum.convert_symbol(symbol).fidelity
    if engine == "sapi":
        if symbol in SAPI_EXACT_SYMBOLS:
            return "exact"
        return "poor" if _is_sapi_poor(symbol) else "approximate"
    raise ValueError(f"unknown engine: {engine!r}")


def word_fidelity(ipa_word: str, engine: str) -> Fidelity:
    """The worst fidelity among ``ipa_word``'s own symbols (and, for
    ``"sapi"``, its tones -- SAPI strips every tone mark outright, a
    known, already-tested fact; eSpeak needs no such override since it
    already voices every ``ToneLevel`` via its Mandarin voice)."""
    symbols = ipa_tokenizer.symbols_only(ipa_word, _ALL_SYMBOLS)
    worst: Fidelity = min(
        (symbol_fidelity(s, engine) for s in symbols), key=FIDELITY_RANK.__getitem__, default="exact"
    )
    if engine == "sapi" and ipa_tokenizer.tone_sequence(ipa_word, _ALL_SYMBOLS):
        worst = min(worst, "poor", key=FIDELITY_RANK.__getitem__)
    return worst


def describe_gap(ipa_word: str, engine: str) -> tuple[str, ...]:
    """Human-readable reasons ``ipa_word`` scored below ``"exact"`` under
    ``engine`` -- one note per distinct reason actually present, reused
    verbatim by the later CLI/web-UI surfacing work instead of being
    re-derived there."""
    symbols = ipa_tokenizer.symbols_only(ipa_word, _ALL_SYMBOLS)
    reasons: list[str] = []
    if engine == "sapi" and ipa_tokenizer.tone_sequence(ipa_word, _ALL_SYMBOLS):
        reasons.append("tones are not voiced")
    seen: set[str] = set()
    for symbol in symbols:
        if symbol_fidelity(symbol, engine) == "exact":
            continue
        consonant = _CONSONANT_BY_IPA.get(symbol)
        if any(ch in CLICK_CHARACTERS for ch in symbol) and "click" not in seen:
            seen.add("click")
            reasons.append("click sounds are poorly approximated")
        elif consonant is not None and consonant.ejective and "ejective" not in seen:
            seen.add("ejective")
            reasons.append("ejective sounds are only approximated")
        elif consonant is not None and consonant.breathy and "breathy" not in seen:
            seen.add("breathy")
            reasons.append("breathy-voiced sounds are only approximated")
        elif consonant is not None and consonant.pharyngealized and "pharyngealized" not in seen:
            seen.add("pharyngealized")
            reasons.append("pharyngealized sounds are only approximated")
        elif consonant is not None and consonant.place is Place.PHARYNGEAL and "pharyngeal" not in seen:
            seen.add("pharyngeal")
            reasons.append("pharyngeal sounds are only approximated")
        elif "other" not in seen:
            seen.add("other")
            reasons.append("some sounds in this word are only approximated")
    return tuple(reasons)


__all__ = [
    "SAPI_EXACT_SYMBOLS", "FIDELITY_RANK", "symbol_fidelity", "word_fidelity", "describe_gap",
]
