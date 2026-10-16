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

    def as_dict(self) -> dict:
        return {"ipa": self.ipa, "kind": self.kind, "label": self.label, "description": self.description}


def _consonant_entry(c: Consonant) -> PhonemeGuideEntry:
    return PhonemeGuideEntry(ipa=c.ipa, kind="consonant", label=_consonant_label(c), description=describe_consonant(c))


def _vowel_entry(v: Vowel) -> PhonemeGuideEntry:
    return PhonemeGuideEntry(ipa=v.ipa, kind="vowel", label=_vowel_label(v), description=describe_vowel(v))


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
