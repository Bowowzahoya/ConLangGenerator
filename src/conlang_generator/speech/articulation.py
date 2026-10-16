"""Plain-language articulation descriptions ("put your tongue tip
against the ridge behind your teeth...") for a language's own phoneme
inventory -- the pronunciation guide's content layer, no TTS involved.

Composed algorithmically from ``core.phonology``'s own typed place/
manner/height/backness/modifier fields, the same lookup-and-branch shape
``speech.phoneme_coverage.describe_gap`` already uses for its own
(shorter, exact-vs-approximate) explanations -- not a hand-curated
table. There are ~200 total IPA symbols across this project's global
pool but far fewer underlying building blocks (11 ``Place`` values, 10
``Manner`` values, 7 ``VowelHeight`` values, 3 ``VowelBackness`` values,
plus a handful of boolean modifier flags); every symbol's description is
assembled from these at call time.

Operates on one language's own actual inventory
(``language.phonology.consonants``/``.vowels``), not the global
``generation.phonology_gen.ALL_CONSONANTS``/``ALL_VOWELS`` pool
``phoneme_coverage.py`` rates engines against -- a sound guide only ever
needs to describe sounds that language really uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from conlang_generator.core.language import Language
from conlang_generator.core.phonology import (
    CLICK_CHARACTERS,
    Consonant,
    Manner,
    Place,
    Vowel,
    VowelBackness,
    VowelHeight,
)
from conlang_generator.generation import ipa_tokenizer

_PLACE_PHRASES: dict[Place, str] = {
    Place.BILABIAL: "press your lips together",
    Place.LABIODENTAL: "touch your lower lip to your upper front teeth",
    Place.DENTAL: "touch your tongue tip to the back of your upper front teeth",
    Place.ALVEOLAR: "touch your tongue tip to the ridge just behind your upper front teeth",
    Place.POSTALVEOLAR: "touch your tongue tip or blade just behind that ridge",
    Place.RETROFLEX: "curl your tongue tip back toward the roof of your mouth",
    Place.PALATAL: "raise the body of your tongue to the hard palate, the roof of your mouth",
    Place.VELAR: "raise the back of your tongue to the soft palate, further back on the roof of your mouth",
    Place.UVULAR: "raise the back of your tongue to the uvula, far back in your throat",
    Place.PHARYNGEAL: "narrow the back of your throat (the pharynx)",
    Place.GLOTTAL: "use your vocal cords themselves, not your tongue or lips",
}

_MANNER_PHRASES: dict[Manner, str] = {
    Manner.STOP: "fully block the airflow for a moment, then release it suddenly",
    Manner.NASAL: "let the air flow out through your nose instead of your mouth",
    Manner.FRICATIVE: "leave a narrow gap there so the air hisses or buzzes through",
    Manner.AFFRICATE: "fully block the airflow, then release it slowly into a hiss, rather than suddenly",
    Manner.APPROXIMANT: "narrow the gap there without quite causing friction",
    Manner.TRILL: "let that part of your tongue vibrate rapidly against the spot",
    Manner.TAP: "touch that spot once, briefly",
    Manner.LATERAL_APPROXIMANT: "let the air flow around the sides of your tongue",
    Manner.LATERAL_FRICATIVE: "let the air hiss around the sides of your tongue",
    Manner.LATERAL_AFFRICATE: "fully block the airflow, then release it into a hiss around the sides of your tongue",
}

_CLICK_PHRASE = "pull your tongue sharply away from that spot to make a sharp clicking sound, made independently of your lungs' airflow"
"""Clicks aren't a ``Manner`` value (see ``CLICK_CHARACTERS``'s own
docstring) -- a click's own real airstream mechanism (velaric, not
pulmonic) is different enough from every other consonant here that it
replaces the manner clause entirely rather than supplementing it."""

_HEIGHT_PHRASES: dict[VowelHeight, str] = {
    VowelHeight.CLOSE: "raise your tongue high, close to the roof of your mouth",
    VowelHeight.NEAR_CLOSE: "raise your tongue nearly as high as it will go",
    VowelHeight.CLOSE_MID: "raise your tongue to about two-thirds of the way up",
    VowelHeight.MID: "hold your tongue roughly in the middle, neither high nor low",
    VowelHeight.OPEN_MID: "lower your tongue to about one-third of the way up",
    VowelHeight.NEAR_OPEN: "lower your tongue nearly all the way down",
    VowelHeight.OPEN: "lower your tongue and drop your jaw, mouth wide open",
}

_BACKNESS_PHRASES: dict[VowelBackness, str] = {
    VowelBackness.FRONT: "bunch it toward the front of your mouth",
    VowelBackness.CENTRAL: "keep it resting in the middle of your mouth",
    VowelBackness.BACK: "pull it back toward your throat",
}

_PLACE_LABELS: dict[Place, str] = {p: p.value for p in Place}
_MANNER_LABELS: dict[Manner, str] = {m: m.value.replace("_", " ") for m in Manner}
_HEIGHT_LABELS: dict[VowelHeight, str] = {h: h.value.replace("_", "-") for h in VowelHeight}
_BACKNESS_LABELS: dict[VowelBackness, str] = {b: b.value for b in VowelBackness}


def _is_click(ipa: str) -> bool:
    return any(ch in CLICK_CHARACTERS for ch in ipa)


# --- a real word that contains each sound, for the pronunciation guide's
# "like the X in <word>" line -- English preferred, a well-known other
# language otherwise (requested directly by a user: "add a word in
# English that has it, if available, otherwise from another language").
# Keyed on the same structured (place, manner, voiced) / (height,
# backness, rounded) identity ``describe_consonant``/``describe_vowel``
# already use, not on raw IPA strings -- a modified symbol (``"pʰ"``,
# ``"tʼ"``, ``"aː"``, ...) therefore reuses its own base's example
# unchanged (the modifier itself is already explained in prose by
# ``describe_consonant``/``describe_vowel``'s own "extras" list, so "like
# the p in English 'pin', ... followed by a puff of extra breath
# (aspirated)" reads naturally without a second, aspirated-specific
# example). Deliberately incomplete rather than forced: a handful of
# genuinely rare sounds (voiced uvular stop, the bilabial and palatal
# clicks, close-mid back unrounded) have no citation here at all rather
# than a shaky one -- the whole point of this feature is a *trustworthy*
# anchor, and a wrong-sounding "famous" example would be worse than
# silence. Not exhaustive of every real-world language that has a given
# sound -- one well-chosen, widely-recognizable example per sound, not a
# ranked list; "ordered by how famous" is reflected by always choosing
# the single most recognizable option rather than an obscure one.
_CONSONANT_EXAMPLES: dict[tuple[Place, Manner, bool], tuple[str, str]] = {
    (Place.ALVEOLAR, Manner.AFFRICATE, False): ("Zeit", "German"),
    (Place.ALVEOLAR, Manner.AFFRICATE, True): ("kids", "English"),
    (Place.ALVEOLAR, Manner.FRICATIVE, False): ("sun", "English"),
    (Place.ALVEOLAR, Manner.FRICATIVE, True): ("zoo", "English"),
    (Place.ALVEOLAR, Manner.LATERAL_AFFRICATE, False): ("Tlaxcala", "Nahuatl"),
    (Place.ALVEOLAR, Manner.LATERAL_APPROXIMANT, True): ("light", "English"),
    (Place.ALVEOLAR, Manner.LATERAL_FRICATIVE, False): ("Llanelli", "Welsh"),
    (Place.ALVEOLAR, Manner.NASAL, True): ("no", "English"),
    (Place.ALVEOLAR, Manner.STOP, False): ("top", "English"),
    (Place.ALVEOLAR, Manner.STOP, True): ("dog", "English"),
    (Place.ALVEOLAR, Manner.TAP, True): ("pero", "Spanish"),
    (Place.ALVEOLAR, Manner.TRILL, False): ("Rhys", "Welsh"),
    (Place.ALVEOLAR, Manner.TRILL, True): ("perro", "Spanish"),
    (Place.BILABIAL, Manner.APPROXIMANT, True): ("we", "English"),
    (Place.BILABIAL, Manner.FRICATIVE, False): ("Fuji", "Japanese"),
    (Place.BILABIAL, Manner.FRICATIVE, True): ("haber", "Spanish"),
    (Place.BILABIAL, Manner.NASAL, True): ("mom", "English"),
    (Place.BILABIAL, Manner.STOP, False): ("pin", "English"),
    (Place.BILABIAL, Manner.STOP, True): ("bed", "English"),
    (Place.DENTAL, Manner.FRICATIVE, False): ("think", "English"),
    (Place.DENTAL, Manner.FRICATIVE, True): ("this", "English"),
    (Place.GLOTTAL, Manner.FRICATIVE, False): ("hat", "English"),
    (Place.GLOTTAL, Manner.FRICATIVE, True): ("hora", "Czech"),
    (Place.GLOTTAL, Manner.STOP, False): ("uh-oh", "English"),
    (Place.LABIODENTAL, Manner.APPROXIMANT, True): ("water", "Dutch"),
    (Place.LABIODENTAL, Manner.FRICATIVE, False): ("fun", "English"),
    (Place.LABIODENTAL, Manner.FRICATIVE, True): ("van", "English"),
    (Place.LABIODENTAL, Manner.NASAL, True): ("comfort", "English"),
    (Place.PALATAL, Manner.AFFRICATE, False): ("jī", "Mandarin"),
    (Place.PALATAL, Manner.AFFRICATE, True): ("ji", "Japanese"),
    (Place.PALATAL, Manner.APPROXIMANT, True): ("yes", "English"),
    (Place.PALATAL, Manner.FRICATIVE, False): ("ich", "German"),
    (Place.PALATAL, Manner.FRICATIVE, True): ("yo", "Spanish"),
    (Place.PALATAL, Manner.LATERAL_APPROXIMANT, True): ("famiglia", "Italian"),
    (Place.PALATAL, Manner.NASAL, True): ("año", "Spanish"),
    (Place.PALATAL, Manner.STOP, False): ("kutya", "Hungarian"),
    (Place.PALATAL, Manner.STOP, True): ("magyar", "Hungarian"),
    (Place.PHARYNGEAL, Manner.FRICATIVE, False): ("Bahrain", "Arabic"),
    (Place.PHARYNGEAL, Manner.FRICATIVE, True): ("Iraq", "Arabic"),
    (Place.POSTALVEOLAR, Manner.AFFRICATE, False): ("chip", "English"),
    (Place.POSTALVEOLAR, Manner.AFFRICATE, True): ("jump", "English"),
    (Place.POSTALVEOLAR, Manner.FRICATIVE, False): ("shoe", "English"),
    (Place.POSTALVEOLAR, Manner.FRICATIVE, True): ("measure", "English"),
    (Place.RETROFLEX, Manner.AFFRICATE, False): ("zhōng", "Mandarin"),
    (Place.RETROFLEX, Manner.AFFRICATE, True): ("dżem", "Polish"),
    (Place.RETROFLEX, Manner.APPROXIMANT, True): ("red", "English"),
    (Place.RETROFLEX, Manner.FRICATIVE, False): ("shū", "Mandarin"),
    (Place.RETROFLEX, Manner.FRICATIVE, True): ("rì", "Mandarin"),
    (Place.RETROFLEX, Manner.LATERAL_APPROXIMANT, True): ("kal", "Tamil"),
    (Place.RETROFLEX, Manner.NASAL, True): ("barn", "Swedish"),
    (Place.RETROFLEX, Manner.STOP, False): ("Taj Mahal", "Hindi"),
    (Place.RETROFLEX, Manner.STOP, True): ("bord", "Swedish"),
    (Place.RETROFLEX, Manner.TAP, True): ("ladka", "Hindi"),
    (Place.UVULAR, Manner.FRICATIVE, False): ("Chanukah", "Hebrew"),
    (Place.UVULAR, Manner.FRICATIVE, True): ("rouge", "French"),
    (Place.UVULAR, Manner.NASAL, True): ("hon", "Japanese"),
    (Place.UVULAR, Manner.STOP, False): ("Qatar", "Arabic"),
    (Place.VELAR, Manner.APPROXIMANT, True): ("fuego", "Spanish"),
    (Place.VELAR, Manner.FRICATIVE, False): ("loch", "Scottish English"),
    (Place.VELAR, Manner.FRICATIVE, True): ("lago", "Spanish"),
    (Place.VELAR, Manner.NASAL, True): ("sing", "English"),
    (Place.VELAR, Manner.STOP, False): ("cat", "English"),
    (Place.VELAR, Manner.STOP, True): ("go", "English"),
    # No entry for (UVULAR, STOP, True) -- ``ɢ``/``ʛ`` are genuinely rare
    # (a few Caucasian/Inuit languages); no widely-recognizable example.
}

_CLICK_EXAMPLES: dict[str, tuple[str, str]] = {
    "ǀ": ("cula", "Zulu"),  # dental click, the letter "c"
    "ǃ": ("qina", "Zulu"),  # (post)alveolar click, the letter "q"
    "ǁ": ("Xhosa", "Xhosa"),  # lateral click, the letter "x" -- the language's own name
    # No entry for "ǂ" (palatal click) or "ʘ" (bilabial click) -- both
    # genuinely rare, found mainly in Khoisan languages with no example
    # word recognizable enough to call "famous".
}

_VOWEL_EXAMPLES: dict[tuple[VowelHeight, VowelBackness, bool], tuple[str, str]] = {
    (VowelHeight.CLOSE, VowelBackness.BACK, False): ("sushi", "Japanese"),
    (VowelHeight.CLOSE, VowelBackness.BACK, True): ("food", "English"),
    (VowelHeight.CLOSE, VowelBackness.CENTRAL, False): ("мы", "Russian"),
    (VowelHeight.CLOSE, VowelBackness.FRONT, False): ("see", "English"),
    (VowelHeight.CLOSE, VowelBackness.FRONT, True): ("tu", "French"),
    (VowelHeight.CLOSE_MID, VowelBackness.BACK, True): ("no", "Spanish"),
    (VowelHeight.CLOSE_MID, VowelBackness.FRONT, False): ("mesa", "Spanish"),
    (VowelHeight.CLOSE_MID, VowelBackness.FRONT, True): ("deux", "French"),
    (VowelHeight.MID, VowelBackness.CENTRAL, False): ("sofa", "English"),
    (VowelHeight.NEAR_CLOSE, VowelBackness.BACK, True): ("book", "English"),
    (VowelHeight.NEAR_CLOSE, VowelBackness.FRONT, False): ("bit", "English"),
    (VowelHeight.NEAR_OPEN, VowelBackness.CENTRAL, False): ("cup", "English"),
    (VowelHeight.NEAR_OPEN, VowelBackness.FRONT, False): ("cat", "English"),
    (VowelHeight.OPEN, VowelBackness.BACK, False): ("father", "English"),
    (VowelHeight.OPEN, VowelBackness.CENTRAL, False): ("casa", "Spanish"),
    (VowelHeight.OPEN_MID, VowelBackness.BACK, True): ("law", "English"),
    (VowelHeight.OPEN_MID, VowelBackness.FRONT, False): ("bed", "English"),
    (VowelHeight.OPEN_MID, VowelBackness.FRONT, True): ("sœur", "French"),
    # No entry for (CLOSE_MID, BACK, False) -- ``ɤ`` (found in Korean/
    # Vietnamese among others) has no single widely-recognizable example.
}

_SYMBOL_EXAMPLE_OVERRIDES: dict[str, tuple[str, str]] = {
    # Syllabic r and the r-colored schwa share their vowel-table bucket
    # with plain ``ɨ``/``ə`` (the data model has no separate "syllabic"
    # dimension for them) but are distinctive enough to deserve their own
    # citation rather than silently reusing ``ɨ``'s.
    "r̩": ("butter", "English"),
    "ɻ̩": ("butter", "English"),
    "ɚ": ("better", "English"),
}


def _consonant_example(c: Consonant) -> tuple[str, str] | None:
    if c.ipa in _SYMBOL_EXAMPLE_OVERRIDES:
        return _SYMBOL_EXAMPLE_OVERRIDES[c.ipa]
    if _is_click(c.ipa):
        click_char = next(ch for ch in c.ipa if ch in CLICK_CHARACTERS)
        return _CLICK_EXAMPLES.get(click_char)
    return _CONSONANT_EXAMPLES.get((c.place, c.manner, c.voiced))


def _vowel_example(v: Vowel) -> tuple[str, str] | None:
    if v.ipa in _SYMBOL_EXAMPLE_OVERRIDES:
        return _SYMBOL_EXAMPLE_OVERRIDES[v.ipa]
    return _VOWEL_EXAMPLES.get((v.height, v.backness, v.rounded))


def describe_consonant(c: Consonant) -> str:
    """One plain-language sentence covering place, manner, voicing, and
    every modifier flag that's actually set."""
    voicing = "voiced" if c.voiced else "voiceless"
    buzzing = "with your vocal cords buzzing" if c.voiced else "without your vocal cords buzzing"
    manner_clause = _CLICK_PHRASE if _is_click(c.ipa) else _MANNER_PHRASES[c.manner]
    sentence = f"{_PLACE_PHRASES[c.place].capitalize()}, then {manner_clause}, {buzzing} ({voicing})."
    extras: list[str] = []
    if c.ejective:
        extras.append("with a sharp pop released by closing and lifting your glottis instead of your lungs (an ejective)")
    if c.aspirated:
        extras.append("followed by a puff of extra breath (aspirated)")
    if c.breathy:
        extras.append("in a loose, breathy, murmured voice")
    if c.pharyngealized:
        extras.append("while tightening the back of your throat at the same time (pharyngealized)")
    if c.palatalized:
        extras.append("while raising the middle of your tongue toward the roof of your mouth at the same time (palatalized)")
    if c.long:
        extras.append("held noticeably longer than usual")
    if extras:
        sentence = sentence.rstrip(".") + ", " + ", ".join(extras) + "."
    return sentence


def describe_vowel(v: Vowel) -> str:
    """One plain-language sentence covering height, backness, rounding,
    and every modifier flag that's actually set."""
    rounding = "with rounded lips" if v.rounded else "with your lips relaxed, not rounded"
    sentence = f"{_HEIGHT_PHRASES[v.height].capitalize()}, and {_BACKNESS_PHRASES[v.backness]}, {rounding}."
    extras: list[str] = []
    if v.nasalized:
        extras.append("letting air flow through your nose at the same time")
    if v.diphthong:
        extras.append("gliding from this starting position into a second one within the same syllable")
    if v.long:
        extras.append("held noticeably longer than usual")
    if extras:
        sentence = sentence.rstrip(".") + ", " + ", ".join(extras) + "."
    return sentence


def _consonant_label(c: Consonant) -> str:
    voicing = "voiced" if c.voiced else "voiceless"
    modifiers = []
    if _is_click(c.ipa):
        modifiers.append("click")
    if c.ejective:
        modifiers.append("ejective")
    if c.aspirated:
        modifiers.append("aspirated")
    if c.breathy:
        modifiers.append("breathy")
    if c.pharyngealized:
        modifiers.append("pharyngealized")
    if c.palatalized:
        modifiers.append("palatalized")
    if c.long:
        modifiers.append("long")
    prefix = " ".join(modifiers + [voicing])
    return f"{prefix} {_PLACE_LABELS[c.place]} {_MANNER_LABELS[c.manner]}"


def _vowel_label(v: Vowel) -> str:
    modifiers = []
    if v.nasalized:
        modifiers.append("nasalized")
    if v.diphthong:
        modifiers.append("diphthong")
    if v.long:
        modifiers.append("long")
    rounding = "rounded" if v.rounded else "unrounded"
    prefix = " ".join(modifiers)
    label = f"{_HEIGHT_LABELS[v.height]} {_BACKNESS_LABELS[v.backness]} {rounding} vowel"
    return f"{prefix} {label}".strip()


@dataclass(frozen=True)
class PhonemeGuideEntry:
    ipa: str
    kind: Literal["consonant", "vowel"]
    label: str
    description: str
    example_word: str | None = None
    example_language: str | None = None
    """A real word containing this sound, and the language it's from --
    ``None`` for the handful of sounds with no widely-recognizable
    example (see ``_CONSONANT_EXAMPLES``'s own docstring note)."""

    def as_dict(self) -> dict:
        return {
            "ipa": self.ipa,
            "kind": self.kind,
            "label": self.label,
            "description": self.description,
            "example_word": self.example_word,
            "example_language": self.example_language,
        }


def _consonant_entry(c: Consonant) -> PhonemeGuideEntry:
    example = _consonant_example(c)
    return PhonemeGuideEntry(
        ipa=c.ipa,
        kind="consonant",
        label=_consonant_label(c),
        description=describe_consonant(c),
        example_word=example[0] if example else None,
        example_language=example[1] if example else None,
    )


def _vowel_entry(v: Vowel) -> PhonemeGuideEntry:
    example = _vowel_example(v)
    return PhonemeGuideEntry(
        ipa=v.ipa,
        kind="vowel",
        label=_vowel_label(v),
        description=describe_vowel(v),
        example_word=example[0] if example else None,
        example_language=example[1] if example else None,
    )


def full_inventory(language: Language) -> tuple[PhonemeGuideEntry, ...]:
    """Every symbol in ``language.phonology``'s own consonants and
    vowels, each described once."""
    return tuple(_consonant_entry(c) for c in language.phonology.consonants) + tuple(
        _vowel_entry(v) for v in language.phonology.vowels
    )


def word_inventory(language: Language, ipa_word: str) -> tuple[PhonemeGuideEntry, ...]:
    """``full_inventory`` filtered to the symbols actually present in
    ``ipa_word`` (via ``ipa_tokenizer.symbols_only``), deduplicated and
    ordered by first appearance in the word rather than place/manner
    order, so a reader can scan left-to-right through the word matching
    each sound to its description."""
    by_ipa = {e.ipa: e for e in full_inventory(language)}
    present = ipa_tokenizer.symbols_only(ipa_word, language.phonology.all_symbols())
    seen: set[str] = set()
    result: list[PhonemeGuideEntry] = []
    for symbol in present:
        if symbol in seen:
            continue
        entry = by_ipa.get(symbol)
        if entry is None:
            continue
        seen.add(symbol)
        result.append(entry)
    return tuple(result)


__all__ = ["PhonemeGuideEntry", "describe_consonant", "describe_vowel", "full_inventory", "word_inventory"]
