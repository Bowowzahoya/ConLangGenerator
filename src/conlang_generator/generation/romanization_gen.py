"""Deterministic romanization-rule generation.

Picks one of two conventional styles for non-ASCII IPA symbols -- digraphs
(``ʃ`` -> ``sh``) or diacritics (``ʃ`` -> ``š``) -- and applies it consistently
across the whole phoneme inventory, so the result reads as one coherent
"vibe" rather than a random mix.
"""

from __future__ import annotations

import random

from conlang_generator.core.phonology import PhonemeInventory
from conlang_generator.core.romanization import RomanizationRule, RomanizationScheme

_DIGRAPH_STYLE: dict[str, str] = {
    "ʃ": "sh", "ʒ": "zh", "tʃ": "ch", "dʒ": "j", "ŋ": "ng",
    "x": "kh", "χ": "kh", "ʔ": "'", "ɾ": "r", "j": "y",
    "pʼ": "p'", "tʼ": "t'", "kʼ": "k'",
    "ɛ": "e", "ɔ": "o", "ə": "e", "ɨ": "y",
}
_DIACRITIC_STYLE: dict[str, str] = {
    "ʃ": "š", "ʒ": "ž", "tʃ": "č", "dʒ": "ǯ", "ŋ": "ṅ",
    "x": "ḥ", "χ": "ḥ", "ʔ": "’", "ɾ": "r", "j": "y",
    "pʼ": "p̓", "tʼ": "t̓", "kʼ": "k̓",
    "ɛ": "ë", "ɔ": "ö", "ə": "ě", "ɨ": "ï",
}


def generate_romanization(rng: random.Random, inventory: PhonemeInventory) -> RomanizationScheme:
    style = rng.choice([_DIGRAPH_STYLE, _DIACRITIC_STYLE])
    rules: list[RomanizationRule] = []
    for symbol in inventory.all_symbols():
        latin = style.get(symbol, symbol)
        rules.append(RomanizationRule(ipa=symbol, latin=latin))
    return RomanizationScheme(rules=tuple(rules))
