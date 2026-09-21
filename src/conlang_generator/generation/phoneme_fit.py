"""Fitting a pronunciation to a language's own sounds and syllable rules.

Shared by ``translation/names.py`` (adapting a foreign proper name) and
``generation/real_words.py`` (deviating a real source-language word). Each
sound maps to the nearest inventory phoneme by feature distance (place/
manner/voicing for consonants, height/backness/rounding for vowels), and the
result is repaired to the language's syllable structure -- an epenthetic
vowel is inserted where a cluster/coda is illegal, and a consonant is
dropped only as a last resort. ``fit_ipa`` is deterministic; ``deviate_ipa``
additionally swaps sounds for near neighbours at a given probability, drawn
from a caller-supplied rng.
"""

from __future__ import annotations

import random

from conlang_generator.core.phonology import (
    Consonant, Manner, PhonemeInventory, Place, SyllableStructure, Vowel, VowelHeight,
)
from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK
from conlang_generator.generation import ipa_tokenizer, phonology_gen

_PLACE_ORDER = {place: i for i, place in enumerate(Place)}
_HEIGHT_ORDER = {height: i for i, height in enumerate(VowelHeight)}
_BACKNESS_ORDER = {"front": 0, "central": 1, "back": 2}
_CONSONANT_BY_IPA = {c.ipa: c for c in phonology_gen.ALL_CONSONANTS}
_VOWEL_BY_IPA = {v.ipa: v for v in phonology_gen.ALL_VOWELS}
ALL_SYMBOLS = tuple(_CONSONANT_BY_IPA) + tuple(_VOWEL_BY_IPA)

# Manners that sound alike enough to substitute at low cost.
_MANNER_COST: dict[frozenset[Manner], float] = {
    frozenset({Manner.STOP, Manner.AFFRICATE}): 1.0,
    frozenset({Manner.FRICATIVE, Manner.AFFRICATE}): 1.0,
    frozenset({Manner.TAP, Manner.TRILL}): 0.5,
    frozenset({Manner.TAP, Manner.APPROXIMANT}): 1.0,
    frozenset({Manner.TRILL, Manner.APPROXIMANT}): 1.5,
    frozenset({Manner.APPROXIMANT, Manner.LATERAL_APPROXIMANT}): 1.0,
    frozenset({Manner.TAP, Manner.LATERAL_APPROXIMANT}): 1.0,
    frozenset({Manner.TRILL, Manner.LATERAL_APPROXIMANT}): 1.5,
    frozenset({Manner.STOP, Manner.FRICATIVE}): 2.0,
    frozenset({Manner.STOP, Manner.NASAL}): 2.0,
}


def _consonant_distance(source: Consonant, target: Consonant) -> float:
    if source.ipa == target.ipa:
        return 0.0
    cost = 1.5 * abs(_PLACE_ORDER[source.place] - _PLACE_ORDER[target.place])
    if source.manner is not target.manner:
        cost += _MANNER_COST.get(frozenset({source.manner, target.manner}), 4.0)
    if source.voiced != target.voiced:
        cost += 1.0
    for attribute in ("ejective", "aspirated", "pharyngealized", "long", "palatalized", "breathy"):
        if getattr(source, attribute) != getattr(target, attribute):
            cost += 0.75
    return cost


def _vowel_distance(source: Vowel, target: Vowel) -> float:
    if source.ipa == target.ipa:
        return 0.0
    cost = 1.0 * abs(_HEIGHT_ORDER[source.height] - _HEIGHT_ORDER[target.height])
    cost += 1.5 * abs(_BACKNESS_ORDER[source.backness.value] - _BACKNESS_ORDER[target.backness.value])
    if source.rounded != target.rounded:
        cost += 1.0
    for attribute in ("long", "diphthong", "nasalized"):
        if getattr(source, attribute) != getattr(target, attribute):
            cost += 0.75
    return cost


def _nearest(symbol: str, inventory: PhonemeInventory) -> tuple[str, bool]:
    """The closest inventory phoneme to a foreign ``symbol``, and whether
    it is a vowel."""
    if symbol in _VOWEL_BY_IPA:
        source = _VOWEL_BY_IPA[symbol]
        best = min(inventory.vowels, key=lambda v: (_vowel_distance(source, v), -v.prevalence, v.ipa))
        return best.ipa, True
    source_c = _CONSONANT_BY_IPA[symbol]
    best_c = min(inventory.consonants, key=lambda c: (_consonant_distance(source_c, c), -c.prevalence, c.ipa))
    return best_c.ipa, False


def _epenthetic_vowel(inventory: PhonemeInventory) -> str:
    """The language's own most natural filler vowel: a schwa/central mid
    vowel when it has one, else its most prevalent plain vowel."""
    plain = [v for v in inventory.vowels if not (v.long or v.diphthong or v.nasalized)] or list(inventory.vowels)
    central = [v for v in plain if v.backness.value == "central"]
    return max(central or plain, key=lambda v: (v.prevalence, v.ipa)).ipa


def fit_ipa(guessed_ipa: str, inventory: PhonemeInventory, structure: SyllableStructure) -> str:
    """Re-fits a pronunciation to ``inventory`` and ``structure`` (see the
    module docstring)."""
    symbols = ipa_tokenizer.symbols_only(guessed_ipa.replace(STRESS_MARK, "").replace(WORD_ACCENT_MARK, ""), ALL_SYMBOLS)
    tokens: list[tuple[str, bool]] = [_nearest(s, inventory) for s in symbols]
    return _repair(tokens, inventory, structure)


def _repair(tokens: list[tuple[str, bool]], inventory: PhonemeInventory, structure: SyllableStructure) -> str:
    epenthetic = _epenthetic_vowel(inventory)
    if not any(is_vowel for _, is_vowel in tokens):
        tokens.append((epenthetic, True))

    for _ in range(4 * len(tokens) + 8):
        problem = first_problem(tokens, structure)
        if problem is None:
            break
        index, drop = problem
        if drop:
            del tokens[index]
        else:
            tokens.insert(index, (epenthetic, True))
        if not any(is_vowel for _, is_vowel in tokens):
            tokens.append((epenthetic, True))
    return "".join(symbol for symbol, _ in tokens)


def first_problem(tokens: list[tuple[str, bool]], structure: SyllableStructure) -> tuple[int, bool] | None:
    """The first spot where ``tokens`` isn't a legal word, as ``(index,
    drop)``: insert an epenthetic vowel *at* ``index``, or (``drop``) delete
    the consonant there because no vowel can rescue it."""
    nuclei = [i for i, (_, is_vowel) in enumerate(tokens) if is_vowel]
    onset: tuple[str, ...] = ()
    onset_start = 0
    for n, nucleus_index in enumerate(nuclei):
        nucleus = tokens[nucleus_index][0]
        # consonants between this nucleus and the next (or word end)
        run_start = nucleus_index + 1
        run_end = nuclei[n + 1] if n + 1 < len(nuclei) else len(tokens)
        run = tuple(symbol for symbol, _ in tokens[run_start:run_end])
        if n == 0:
            leading = tuple(symbol for symbol, _ in tokens[:nucleus_index])
            if not structure.is_valid_syllable(leading, nucleus, (), initial=True):
                return _fix_leading(leading, nucleus, structure)
            onset = leading

        if n + 1 == len(nuclei):
            if structure.is_valid_syllable(onset, nucleus, run, final=True, initial=(n == 0)):
                return None
            return _fix_final(onset, nucleus, run, run_start, structure)

        next_nucleus = tokens[nuclei[n + 1]][0]
        split = _find_split(onset, nucleus, run, next_nucleus, structure, initial=(n == 0))
        if split is None:
            if len(run) == 1:
                return run_start, True
            return run_start + 1, False
        onset = run[split:]
    return None


def _find_split(
    onset: tuple[str, ...], nucleus: str, run: tuple[str, ...], next_nucleus: str, structure: SyllableStructure,
    initial: bool = False,
) -> int | None:
    """How many of ``run``'s consonants close this syllable as its coda (the
    rest open the next syllable as its onset) -- maximal onset first."""
    for coda_len in range(len(run) + 1):
        coda, next_onset = run[:coda_len], run[coda_len:]
        if not structure.is_valid_syllable(onset, nucleus, coda, initial=initial):
            continue
        if not structure.is_valid_syllable(next_onset, next_nucleus, ()):
            continue
        if not structure.is_valid_boundary(coda[-1] if coda else None, next_onset[0] if next_onset else None):
            continue
        return coda_len
    return None


def _fix_leading(leading: tuple[str, ...], nucleus: str, structure: SyllableStructure) -> tuple[int, bool]:
    if len(leading) <= 1:
        return 0, True  # a lone consonant this language never allows to open a word
    return 1, False


def _fix_final(
    onset: tuple[str, ...], nucleus: str, coda: tuple[str, ...], coda_start: int, structure: SyllableStructure
) -> tuple[int, bool]:
    if len(coda) == 1:
        return coda_start + 1, False  # give the lone final consonant a vowel to lean on
    return coda_start + 1, False


def _neighbours(symbol: str, inventory: PhonemeInventory, count: int = 3) -> list[str]:
    """The ``count`` inventory phonemes nearest ``symbol`` (same class),
    excluding ``symbol`` itself."""
    if symbol in _VOWEL_BY_IPA or symbol in {v.ipa for v in inventory.vowels}:
        source = _VOWEL_BY_IPA.get(symbol)
        pool = [v for v in inventory.vowels if v.ipa != symbol]
        if source is not None:
            pool.sort(key=lambda v: (_vowel_distance(source, v), v.ipa))
        return [v.ipa for v in pool[:count]]
    source_c = _CONSONANT_BY_IPA.get(symbol)
    pool_c = [c for c in inventory.consonants if c.ipa != symbol]
    if source_c is not None:
        pool_c.sort(key=lambda c: (_consonant_distance(source_c, c), c.ipa))
    return [c.ipa for c in pool_c[:count]]


def deviate_ipa(
    ipa: str, inventory: PhonemeInventory, structure: SyllableStructure, rng: random.Random, probability: float
) -> str:
    """Like ``fit_ipa``, but each sound is also swapped, with the given
    per-sound ``probability``, for one of its nearest neighbours in
    ``inventory`` -- a looser variant of the same word that still uses only
    this language's own sounds and syllable shapes."""
    symbols = ipa_tokenizer.symbols_only(ipa.replace(STRESS_MARK, "").replace(WORD_ACCENT_MARK, ""), ALL_SYMBOLS)
    tokens: list[tuple[str, bool]] = []
    for symbol in symbols:
        mapped, is_vowel = _nearest(symbol, inventory)
        if rng.random() < probability:
            neighbours = _neighbours(mapped, inventory)
            if neighbours:
                mapped = rng.choice(neighbours)
        tokens.append((mapped, is_vowel))
    return _repair(tokens, inventory, structure)
