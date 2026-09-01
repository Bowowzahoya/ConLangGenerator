"""Diachronic sound change: evolves an *existing* language's lexicon via
regular sound-change rules, rather than generating a fresh one.

Pure rule-based, no LLM -- historical sound change is a rule-application
process, not a creative one, so this stays free, instant, and reproducible.

Six illustrative rule categories, applied in order to every lexicon entry's
IPA (tokenized -- see ``ipa_tokenizer.py`` -- so tone-diacritic decoration
survives even when the base vowel it's on changes):

- cluster simplification: a 2-consonant run drops its lower-sonority member.
- lenition: a voiceless stop between two vowels becomes voiced.
- final devoicing: a word-final voiced obstruent becomes voiceless.
- palatalization: k/g before a front vowel becomes tʃ/dʒ.
- vowel reduction: a non-first vowel becomes ə.
- ejective drift: a plain stop gains ejective release.

Each rule has an illustrative "half-life" in years (documented per rule,
not precise) and a saturating rate model: ``rate(years) = 1 -
exp(-years/effective_half_life)``, so a small ``years`` changes little
(recognizable) and a large one approaches -- never reaches -- total
replacement. ``effective_half_life`` is scaled by the one relevant graded
trait per rule-cluster (``contact_intensity`` for the three simplification-
leaning rules -- contact/creolization accelerates simplification;
``altitude`` for ejective drift -- Everett 2013, same link fresh generation
already uses): positive trait strength shortens the half-life (faster
change), negative lengthens it. `final_devoicing`/`palatalization` aren't
trait-linked in this v1 -- kept deliberately narrow.

Grammar and tone system are copied from the base language unchanged (word-
level focus only, per current project direction). The evolved
``PhonemeInventory``/``SyllableStructure``/``RomanizationScheme`` are
recomputed from what the evolved lexicon actually uses -- the old ones may
not cover phonemes gained through evolution (e.g. ə, a new ejective).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import Lexicon
from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure, VowelBackness
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import ipa_tokenizer, phonology_gen, romanization_gen, sonority

_VOICELESS_TO_VOICED: dict[str, str] = {
    "p": "b", "t": "d", "k": "g", "ʈ": "ɖ", "c": "ɟ", "tʃ": "dʒ",
    "s": "z", "f": "v", "ʃ": "ʒ", "ʂ": "ʐ", "θ": "ð", "ç": "ʝ", "χ": "ʁ",
}
_VOICED_TO_VOICELESS: dict[str, str] = {voiced: voiceless for voiceless, voiced in _VOICELESS_TO_VOICED.items()}
_PALATALIZATION: dict[str, str] = {"k": "tʃ", "g": "dʒ"}
_PLAIN_TO_EJECTIVE: dict[str, str] = {"p": "pʼ", "t": "tʼ", "k": "kʼ"}

_HALF_LIVES = {
    "lenition": 150.0,
    "final_devoicing": 200.0,
    "cluster_simplification": 200.0,
    "palatalization": 300.0,
    "vowel_reduction": 150.0,
    "ejective_drift": 400.0,
}

Token = tuple[str, str]  # (base symbol, trailing combining-mark decoration)


@dataclass(frozen=True)
class _Rates:
    lenition: float
    final_devoicing: float
    cluster_simplification: float
    palatalization: float
    vowel_reduction: float
    ejective_drift: float


def _saturating_rate(years: int, base_half_life: float, trait_strength: float) -> float:
    multiplier = max(0.15, 1.0 - 0.6 * trait_strength)
    effective_half_life = base_half_life * multiplier
    return 1.0 - math.exp(-years / effective_half_life)


def _compute_rates(years: int, traits: TraitProfile) -> _Rates:
    contact = traits.contact_intensity
    return _Rates(
        lenition=_saturating_rate(years, _HALF_LIVES["lenition"], contact),
        final_devoicing=_saturating_rate(years, _HALF_LIVES["final_devoicing"], 0.0),
        cluster_simplification=_saturating_rate(years, _HALF_LIVES["cluster_simplification"], contact),
        palatalization=_saturating_rate(years, _HALF_LIVES["palatalization"], 0.0),
        vowel_reduction=_saturating_rate(years, _HALF_LIVES["vowel_reduction"], contact),
        ejective_drift=_saturating_rate(years, _HALF_LIVES["ejective_drift"], traits.altitude),
    )


def _simplify_clusters(tokens: list[Token], rng: random.Random, rate: float, consonant_by_ipa: dict) -> list[Token]:
    if rate <= 0:
        return tokens
    result: list[Token] = []
    i = 0
    while i < len(tokens):
        symbol = tokens[i][0]
        if (
            i + 1 < len(tokens)
            and symbol in consonant_by_ipa
            and tokens[i + 1][0] in consonant_by_ipa
            and rng.random() < rate
        ):
            c1, c2 = consonant_by_ipa[symbol], consonant_by_ipa[tokens[i + 1][0]]
            result.append(tokens[i + 1] if sonority.sonority(c1) <= sonority.sonority(c2) else tokens[i])
            i += 2
            continue
        result.append(tokens[i])
        i += 1
    return result


def _apply_lenition(tokens: list[Token], rng: random.Random, rate: float, vowel_by_ipa: dict) -> list[Token]:
    if rate <= 0:
        return tokens
    result = list(tokens)
    for i, (symbol, deco) in enumerate(result):
        if symbol not in _VOICELESS_TO_VOICED or i == 0 or i == len(result) - 1:
            continue
        if result[i - 1][0] in vowel_by_ipa and result[i + 1][0] in vowel_by_ipa and rng.random() < rate:
            result[i] = (_VOICELESS_TO_VOICED[symbol], deco)
    return result


def _apply_final_devoicing(tokens: list[Token], rng: random.Random, rate: float, consonant_by_ipa: dict) -> list[Token]:
    if rate <= 0 or not tokens:
        return tokens
    result = list(tokens)
    symbol, deco = result[-1]
    consonant = consonant_by_ipa.get(symbol)
    if consonant is not None and consonant.voiced and symbol in _VOICED_TO_VOICELESS and rng.random() < rate:
        result[-1] = (_VOICED_TO_VOICELESS[symbol], deco)
    return result


def _apply_palatalization(tokens: list[Token], rng: random.Random, rate: float, vowel_by_ipa: dict) -> list[Token]:
    if rate <= 0:
        return tokens
    result = list(tokens)
    for i, (symbol, deco) in enumerate(result):
        if symbol not in _PALATALIZATION or i + 1 >= len(result):
            continue
        next_vowel = vowel_by_ipa.get(result[i + 1][0])
        if next_vowel is not None and next_vowel.backness == VowelBackness.FRONT and rng.random() < rate:
            result[i] = (_PALATALIZATION[symbol], deco)
    return result


def _apply_vowel_reduction(tokens: list[Token], rng: random.Random, rate: float, vowel_by_ipa: dict) -> list[Token]:
    if rate <= 0:
        return tokens
    result = list(tokens)
    seen_first_vowel = False
    for i, (symbol, deco) in enumerate(result):
        if symbol not in vowel_by_ipa:
            continue
        if not seen_first_vowel:
            seen_first_vowel = True
            continue
        if symbol != "ə" and rng.random() < rate:
            result[i] = ("ə", deco)
    return result


def _apply_ejective_drift(tokens: list[Token], rng: random.Random, rate: float) -> list[Token]:
    if rate <= 0:
        return tokens
    result = list(tokens)
    for i, (symbol, deco) in enumerate(result):
        if symbol in _PLAIN_TO_EJECTIVE and rng.random() < rate:
            result[i] = (_PLAIN_TO_EJECTIVE[symbol], deco)
    return result


def _evolve_ipa(
    ipa: str, rng: random.Random, rates: _Rates, known_symbols: tuple[str, ...], consonant_by_ipa: dict, vowel_by_ipa: dict
) -> str:
    tokens = ipa_tokenizer.tokenize(ipa, known_symbols)
    tokens = _simplify_clusters(tokens, rng, rates.cluster_simplification, consonant_by_ipa)
    tokens = _apply_lenition(tokens, rng, rates.lenition, vowel_by_ipa)
    tokens = _apply_final_devoicing(tokens, rng, rates.final_devoicing, consonant_by_ipa)
    tokens = _apply_palatalization(tokens, rng, rates.palatalization, vowel_by_ipa)
    tokens = _apply_vowel_reduction(tokens, rng, rates.vowel_reduction, vowel_by_ipa)
    tokens = _apply_ejective_drift(tokens, rng, rates.ejective_drift)
    return "".join(symbol + deco for symbol, deco in tokens)


def _recompute_syllable_structure(base: SyllableStructure, consonants: tuple) -> SyllableStructure:
    onset_pairs = tuple(
        (c1.ipa, c2.ipa) for c1 in consonants for c2 in consonants if c1 is not c2 and sonority.is_legal_onset_cluster(c1, c2)
    )
    if base.max_coda == 0:
        max_coda, allowed_coda_consonants, allowed_coda_clusters = 0, None, ()
    elif base.allowed_coda_consonants is not None:
        sonorants = tuple(c.ipa for c in consonants if c.ipa == "ʔ" or sonority.sonority(c) >= 3)
        max_coda, allowed_coda_consonants, allowed_coda_clusters = (1, sonorants, ()) if sonorants else (0, None, ())
    else:
        coda_pairs = tuple(
            (c1.ipa, c2.ipa) for c1 in consonants for c2 in consonants if c1 is not c2 and sonority.is_legal_coda_cluster(c1, c2)
        )
        max_coda = base.max_coda
        allowed_coda_consonants = None
        allowed_coda_clusters = coda_pairs if max_coda >= 2 else ()

    return SyllableStructure(
        max_onset=base.max_onset,
        max_coda=max_coda,
        allowed_onset_clusters=onset_pairs if base.max_onset >= 2 else (),
        allowed_coda_clusters=allowed_coda_clusters,
        allowed_coda_consonants=allowed_coda_consonants,
        vowel_harmony=base.vowel_harmony,
    )


def evolve_language(name: str, base: Language, years: int, traits: TraitProfile, seed: int) -> Language:
    rng = random.Random(seed)
    rates = _compute_rates(years, traits)

    consonant_by_ipa = {c.ipa: c for c in phonology_gen.ALL_CONSONANTS}
    vowel_by_ipa = {v.ipa: v for v in phonology_gen.ALL_VOWELS}
    known_symbols = tuple(consonant_by_ipa) + tuple(vowel_by_ipa)

    evolved_ipas = [
        _evolve_ipa(entry.ipa, rng, rates, known_symbols, consonant_by_ipa, vowel_by_ipa)
        for entry in base.lexicon.entries
    ]

    used_symbols: set[str] = set()
    for ipa in evolved_ipas:
        used_symbols.update(ipa_tokenizer.symbols_only(ipa, known_symbols))
    consonants = tuple(sorted((c for c in phonology_gen.ALL_CONSONANTS if c.ipa in used_symbols), key=lambda c: -c.prevalence))
    vowels = tuple(sorted((v for v in phonology_gen.ALL_VOWELS if v.ipa in used_symbols), key=lambda v: -v.prevalence))
    inventory = PhonemeInventory(consonants=consonants, vowels=vowels)

    syllable_structure = _recompute_syllable_structure(base.syllable_structure, consonants)
    romanization = romanization_gen.generate_romanization(rng, inventory)

    evolved_entries = tuple(
        entry.model_copy(update={"ipa": ipa, "romanization": romanization.apply(ipa)})
        for entry, ipa in zip(base.lexicon.entries, evolved_ipas)
    )

    spec = GenerationSpec(
        prompt=f"evolved from '{base.name}' over {years} years",
        seed=seed,
        traits=traits,
    )

    return Language(
        name=name,
        spec=spec,
        phonology=inventory,
        syllable_structure=syllable_structure,
        tone_system=base.tone_system,
        romanization=romanization,
        grammar=base.grammar,
        lexicon=Lexicon(entries=evolved_entries, idioms=base.lexicon.idioms),
        history=base.history + (f"evolved {years} years (seed={seed})",),
    )
