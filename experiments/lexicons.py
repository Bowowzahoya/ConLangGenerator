"""Real seed vocabularies for evolution scenarios in ``experiments/evolution.py``.

Hand-transcribed, standard-Dutch-ish pronunciation, simplified to fit this
project's modeled phoneme set. Diphthongs are now modeled (see
``core/phonology.py``'s ``Vowel.diphthong``) and used correctly below for
every word that actually has one ("jij" /jɛi/, "klein" /klɛin/, "koud"
/kaut/, etc.) -- phonemic vowel length is a separate, still-unretrofitted
simplification: this corpus still uses plain monophthongs throughout
rather than swapping in long-vowel symbols across every entry (see
``Vowel.long``). /ɣ/ (voiced velar fricative -- what Dutch "g" actually
is; Dutch has no native /g/ stop) is modeled and used correctly below.
Close enough for judging the sound-change engine's output, not a
rigorous phonetic corpus.

Each entry is ``(gloss, spelling, ipa)`` and covers every
``generation.lexicon_gen.CORE_MEANINGS`` gloss.
"""

from __future__ import annotations

DUTCH: tuple[tuple[str, str, str], ...] = (
    ("I", "ik", "ɪk"),
    ("you", "jij", "jɛi"),
    ("he", "hij", "hɛi"),
    ("we", "wij", "wɛi"),
    ("this", "dit", "dɪt"),
    ("that", "dat", "dɑt"),
    ("water", "water", "watər"),
    ("fire", "vuur", "vyɾ"),
    ("sun", "zon", "zɔn"),
    ("moon", "maan", "man"),
    ("mountain", "berg", "bɛɾx"),
    ("stone", "steen", "sten"),
    ("tree", "boom", "bom"),
    ("rain", "regen", "ɾeɣən"),
    ("wind", "wind", "wɪnt"),
    ("person", "persoon", "pɛɾson"),
    ("child", "kind", "kɪnt"),
    ("mother", "moeder", "mudəɾ"),
    ("father", "vader", "vadəɾ"),
    ("animal", "dier", "diɾ"),
    ("bird", "vogel", "voɣəl"),
    ("fish", "vis", "vɪs"),
    ("hand", "hand", "hɑnt"),
    ("eye", "oog", "ox"),
    ("name", "naam", "nam"),
    ("big", "groot", "ɣrot"),
    ("small", "klein", "klɛin"),
    ("high", "hoog", "hox"),
    ("low", "laag", "lax"),
    ("good", "goed", "ɣut"),
    ("bad", "slecht", "slɛxt"),
    ("hot", "heet", "het"),
    ("cold", "koud", "kaut"),
    ("new", "nieuw", "niw"),
    ("old", "oud", "aut"),
    ("go", "gaan", "ɣan"),
    ("come", "komen", "komən"),
    ("see", "zien", "zin"),
    ("eat", "eten", "etən"),
    ("drink", "drinken", "drɪŋkən"),
    ("say", "zeggen", "zɛɣən"),
    ("know", "weten", "wetən"),
    ("sleep", "slapen", "slapən"),
    ("give", "geven", "ɣevən"),
    ("one", "een", "en"),
    ("two", "twee", "twe"),
    ("three", "drie", "dri"),
    ("not", "niet", "nit"),
    ("and", "en", "ɛn"),
)
