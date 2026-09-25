"""Morphophonology at affix boundaries: vowel harmony, hiatus resolution (elision or a
glide) and initial-consonant mutation.

- **Vowel harmony.** A language may make the vowels of its affixes agree with the stem's
  vowels in backness, height or rounding. ``harmony_pairs`` are
  the (first class, second class) counterparts the inventory really has; a stem's class is
  that of its last vowel for a suffix (its first for a prefix) that belongs to a pair
  (other vowels are neutral); an affix vowel in a pair takes the stem's class.
- **Boundary rule.** Where a vowel meets a vowel across an affix boundary, ``elision`` drops
  the vowel of the stem (before a suffix) or of the prefix (before the stem), and ``glide``
  inserts ``boundary_glide`` between them.
- **Mutation.** Certain cells (``mutation_cells``, e.g. ``"tense_affixes/past"``) change the
  stem's initial consonant by ``mutation_pairs`` (lenition: a voiceless stop voices, a voiced
  stop becomes the fricative of its place), as in the Celtic languages.

Rules are built from the grammar and applied by ``inflection_gen.apply_affix``; mutation is
applied to the stem by the translator (``_stem_ipa``). One independent rng stream, drawn last."""

from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass

from conlang_generator.core.grammar import GrammarProfile, MorphologicalType
from conlang_generator.core.phonology import Manner, PhonemeInventory, VowelBackness
from conlang_generator.generation import ipa_tokenizer

MUTATION_CELLS = (
    "case_affixes/genitive", "number_affixes/plural", "tense_affixes/past", "possession_affixes/possessed",
    "case_affixes/dative",
)
_HARMONY_RATE = {
    MorphologicalType.ISOLATING: 0.05, MorphologicalType.AGGLUTINATIVE: 0.55,
    MorphologicalType.FUSIONAL: 0.25, MorphologicalType.POLYSYNTHETIC: 0.35,
}
_BOUNDARY_RATES = (("none", 0.55), ("elision", 0.25), ("glide", 0.20))
_MUTATION_RATE = 0.15


def _base(symbol: str) -> str:
    """``symbol`` without its trailing combining marks (tone, length decorations)."""
    end = len(symbol)
    while end > 0 and unicodedata.combining(symbol[end - 1]):
        end -= 1
    return symbol[:end] or symbol


_HEIGHT_RANK = {
    "close": 0, "near_close": 1, "close_mid": 2, "mid": 3, "open_mid": 4, "near_open": 5, "open": 6,
}


def harmony_pairs(inventory: PhonemeInventory) -> tuple[str, tuple[tuple[str, str], ...]]:
    """The best harmony this inventory supports, as ``(feature, pairs)`` with at least two pairs
    so that it is audible: ``backness`` -- (front, back) vowels of the same height, preferring the
    same rounding; else ``height`` -- (higher, lower) vowels one step apart with the same backness
    and rounding (as in Bantu); else ``rounding`` -- (unrounded, rounded) of the same height and
    backness. ``("", ())`` when none."""
    simple = [v for v in inventory.vowels if not v.diphthong and not v.long and not v.nasalized]
    used: set[str] = set()
    backness = []
    for front in simple:
        if front.backness is not VowelBackness.FRONT:
            continue
        candidates = [
            b for b in simple
            if b.backness is VowelBackness.BACK and b.height is front.height and b.ipa not in used
        ]
        back = next((b for b in candidates if b.rounded == front.rounded), candidates[0] if candidates else None)
        if back is not None:
            used.add(back.ipa)
            backness.append((front.ipa, back.ipa))
    if len(backness) >= 2:
        return "backness", tuple(backness)
    used = set()
    height = []
    for high in simple:
        rank = _HEIGHT_RANK[high.height.value]
        low = next(
            (v for v in simple if v.backness is high.backness and v.rounded == high.rounded
             and _HEIGHT_RANK[v.height.value] == rank + 1 and v.ipa not in used and high.ipa not in used), None,
        )
        if low is not None:
            used |= {high.ipa, low.ipa}
            height.append((high.ipa, low.ipa))
    if len(height) >= 2:
        return "height", tuple(height)
    used = set()
    rounding = []
    for plain in simple:
        if plain.rounded:
            continue
        round_ = next(
            (r for r in simple if r.rounded and r.height is plain.height and r.backness is plain.backness), None
        )
        if round_ is not None:
            rounding.append((plain.ipa, round_.ipa))
    if len(rounding) >= 2:
        return "rounding", tuple(rounding)
    return "", ()


def mutation_pairs(inventory: PhonemeInventory) -> tuple[tuple[str, str], ...]:
    """Lenition of an initial consonant: a voiceless stop to its voiced twin, a voiced stop to the
    fricative of its place -- only pairs the inventory has."""
    consonants = inventory.consonants
    pairs: list[tuple[str, str]] = []
    for c in consonants:
        if c.manner is not Manner.STOP or c.ejective or c.aspirated or c.long:
            continue
        if not c.voiced:
            twin = next(
                (d for d in consonants if d.voiced and d.manner is Manner.STOP and d.place is c.place
                 and not (d.ejective or d.aspirated or d.long)), None,
            )
        else:
            twin = next(
                (d for d in consonants if d.voiced and d.manner is Manner.FRICATIVE and d.place is c.place), None
            )
        if twin is not None:
            pairs.append((c.ipa, twin.ipa))
    return tuple(pairs)


def roll_morphophonology(rng: random.Random, grammar: GrammarProfile, inventory: PhonemeInventory) -> dict[str, object]:
    """Which of harmony, a boundary rule and mutation this language has (every draw always made)."""
    harmony_roll = rng.random()
    boundary_roll = rng.random()
    mutation_roll = rng.random()
    glide_roll = rng.random()
    cell_rolls = [rng.random() for _ in MUTATION_CELLS]
    feature, pairs = harmony_pairs(inventory)
    rate = _HARMONY_RATE.get(grammar.morphological_type, 0.3)
    has_harmony = feature != "" and harmony_roll < rate
    cumulative = 0.0
    boundary = "none"
    for label, weight in _BOUNDARY_RATES:
        cumulative += weight
        if boundary_roll < cumulative:
            boundary = label
            break
    glides = [s for s in inventory.consonant_symbols() if s in ("j", "w", "ʔ", "h")]
    glide = glides[int(glide_roll * len(glides))] if glides else ""
    if boundary == "glide" and not glide:
        boundary = "elision"
    available = []
    for cell in MUTATION_CELLS:
        field, _, label = cell.partition("/")
        if any(a.label == label for a in getattr(grammar, field, ())):
            available.append(cell)
    mutation = mutation_pairs(inventory)
    cells = tuple(c for c, roll in zip(MUTATION_CELLS, cell_rolls) if c in available and roll < 0.4)
    if not cells and available:
        cells = (available[int(cell_rolls[0] * len(available))],)
    has_mutation = mutation_roll < _MUTATION_RATE and bool(mutation) and bool(cells)
    return {
        "harmony": feature if has_harmony else "none",
        "harmony_pairs": pairs if has_harmony else (),
        "boundary_rule": boundary,
        "boundary_glide": glide if boundary == "glide" else "",
        "mutation_cells": cells if has_mutation else (),
        "mutation_pairs": mutation if has_mutation else (),
    }


@dataclass(frozen=True)
class Morphophonology:
    """The rules ``inflection_gen.apply_affix`` applies at an affix boundary."""

    classes: dict[str, tuple[int, str]]
    """Vowel -> (0 or 1, its counterpart in the other class); empty without harmony."""
    boundary: str
    glide: str
    vowels: frozenset[str]

    def _class_of(self, symbols, from_end: bool) -> int | None:
        order = reversed(symbols) if from_end else symbols
        for symbol in order:
            entry = self.classes.get(_base(symbol))
            if entry is not None:
                return entry[0]
        return None

    def _harmonize(self, exponent, stem_class: int | None):
        if not self.classes or stem_class is None:
            return tuple(exponent)
        out = []
        for symbol in exponent:
            entry = self.classes.get(_base(symbol))
            out.append(entry[1] if entry is not None and entry[0] != stem_class else symbol)
        return tuple(out)

    def apply(self, prefix, stem, suffix):
        """``(prefix, stem, suffix)`` after harmony and the boundary rule."""
        if prefix:
            prefix = self._harmonize(prefix, self._class_of(stem, False))
        if suffix:
            suffix = self._harmonize(suffix, self._class_of(stem, True))
        stem = tuple(stem)
        if self.boundary != "none":
            if suffix and stem and _base(stem[-1]) in self.vowels and _base(suffix[0]) in self.vowels:
                if self.boundary == "elision":
                    stem = stem[:-1]
                elif self.glide:
                    suffix = (self.glide,) + tuple(suffix)
            if prefix and stem and _base(prefix[-1]) in self.vowels and _base(stem[0]) in self.vowels:
                if self.boundary == "elision":
                    prefix = tuple(prefix)[:-1]
                elif self.glide:
                    prefix = tuple(prefix) + (self.glide,)
        return tuple(prefix), stem, tuple(suffix)


def build_rules(grammar: GrammarProfile, inventory: PhonemeInventory) -> Morphophonology | None:
    """The boundary rules of ``grammar`` (``None`` when it has none)."""
    if grammar.harmony == "none" and grammar.boundary_rule == "none":
        return None
    classes: dict[str, tuple[int, str]] = {}
    for first, second in grammar.harmony_pairs:
        classes[first] = (0, second)
        classes[second] = (1, first)
    return Morphophonology(
        classes=classes, boundary=grammar.boundary_rule, glide=grammar.boundary_glide,
        vowels=frozenset(inventory.vowel_symbols()),
    )


def mutate_initial(ipa: str, mapping: dict[str, str], known_symbols, vowel_symbols: frozenset[str]) -> str:
    """``ipa`` with its initial consonant replaced by its mutated form (unchanged when it starts with
    a vowel or a consonant that does not mutate)."""
    tokens = ipa_tokenizer.tokenize(ipa, known_symbols)
    marks = [i for i, (symbol, _) in enumerate(tokens) if symbol not in ("ˈ", "ˌ")]
    if not marks:
        return ipa
    index = marks[0]
    symbol, deco = tokens[index]
    if symbol in vowel_symbols or symbol not in mapping:
        return ipa
    tokens[index] = (mapping[symbol], deco)
    return "".join(symbol + deco for symbol, deco in tokens)
