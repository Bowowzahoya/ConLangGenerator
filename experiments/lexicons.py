"""Real seed vocabularies for evolution scenarios in ``experiments/evolution.py``.

Hand-transcribed, standard-Dutch-ish pronunciation, simplified to fit this
project's modeled phoneme set (no diphthongs or phonemic vowel length are
modeled, so e.g. "jij" /jɛi/ -> /jɛ/, "goed" /ɣut/ -> approximated with
plain /g/ since voiced velar fricative isn't in the pool). Close enough for
judging the sound-change engine's output, not a rigorous phonetic corpus.

Each entry is ``(gloss, spelling, ipa)`` and covers every
``generation.lexicon_gen.CORE_MEANINGS`` gloss.
"""

from __future__ import annotations

DUTCH: tuple[tuple[str, str, str], ...] = (
    ("I", "ik", "ɪk"),
    ("you", "jij", "jɛ"),
    ("he", "hij", "hɛ"),
    ("we", "wij", "wɛ"),
    ("this", "dit", "dɪt"),
    ("that", "dat", "dɑt"),
    ("water", "water", "watər"),
    ("fire", "vuur", "vyɾ"),
    ("sun", "zon", "zɔn"),
    ("moon", "maan", "man"),
    ("mountain", "berg", "bɛɾx"),
    ("stone", "steen", "sten"),
    ("tree", "boom", "bom"),
    ("rain", "regen", "ɾexən"),
    ("wind", "wind", "wɪnt"),
    ("person", "persoon", "pɛɾson"),
    ("child", "kind", "kɪnt"),
    ("mother", "moeder", "mudəɾ"),
    ("father", "vader", "vadəɾ"),
    ("animal", "dier", "diɾ"),
    ("bird", "vogel", "voxəl"),
    ("fish", "vis", "vɪs"),
    ("hand", "hand", "hɑnt"),
    ("eye", "oog", "ox"),
    ("name", "naam", "nam"),
    ("big", "groot", "grot"),
    ("small", "klein", "klɛn"),
    ("high", "hoog", "hox"),
    ("low", "laag", "lax"),
    ("good", "goed", "gut"),
    ("bad", "slecht", "slɛxt"),
    ("hot", "heet", "het"),
    ("cold", "koud", "kɔt"),
    ("new", "nieuw", "niw"),
    ("old", "oud", "ot"),
    ("go", "gaan", "gan"),
    ("come", "komen", "komən"),
    ("see", "zien", "zin"),
    ("eat", "eten", "etən"),
    ("drink", "drinken", "drɪŋkən"),
    ("say", "zeggen", "zɛxən"),
    ("know", "weten", "wetən"),
    ("sleep", "slapen", "slapən"),
    ("give", "geven", "gevən"),
    ("one", "een", "en"),
    ("two", "twee", "twe"),
    ("three", "drie", "dri"),
    ("not", "niet", "nit"),
    ("and", "en", "ɛn"),
)
