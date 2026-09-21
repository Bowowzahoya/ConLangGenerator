"""Using real source-language words: the separate *word strictness*
(``TraitProfile.source_word_strictness``), independent of the sound
strictness (``source_language_strictness``) that only governs which sounds
the language may use.

Word strictness decides both **how many** pregenerated meanings follow a
real word (each, seeded and deterministic, with probability = the
strictness) and **how closely** they follow it: at ``1.0`` every word is an
exact copy of the real word (spelling verbatim, its sounds forced into the
inventory); below that each is a looser variant -- every sound swapped for a
near neighbour with probability ``(1 - strictness) * DEVIATION_SCALE`` --
restricted to the sounds the sound strictness allows, and re-spelled through
the language's own orthography. A meaning takes its word from a matched
source language (weighted by ``source_language_weights``) that has one
curated (``reference_languages/real_lexicon``); otherwise the LLM is asked
for it (``real_words_llm``), and with no answer the word simply stays
invented.

Planning (which words, from where) happens before phonology, because exact
copies must force their phonemes into the inventory; building the entries
happens after, once the inventory and romanization exist. A separate rng
(seeded from ``spec.seed``) is used throughout, so generation with word
strictness 0 draws exactly what it always did.
"""

from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass

from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from conlang_generator.core.phonology import (
    TONE_DIACRITICS, PhonemeInventory, SyllableStructure, ToneLevel, ToneSystem,
)
from conlang_generator.core.romanization import (
    STRESS_MARK, WORD_ACCENT_MARK, RomanizationScheme, apply_grammatical_spelling,
)
from conlang_generator.core.spec import GenerationSpec, SeedExample
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import ipa_tokenizer, phoneme_fit, phonology_gen, real_words_llm, stress_gen
from conlang_generator.generation.lexicon_gen import CONDITIONAL_MEANINGS
from conlang_generator.generation.reference_languages import match_profiles_weighted
from conlang_generator.generation.reference_languages import real_stress
from conlang_generator.generation.reference_languages.real_lexicon import real_words
from conlang_generator.llm.base import LLMClient

DEVIATION_SCALE = 0.6
"""Per-sound swap probability at word strictness 0 (it shrinks linearly to
0 at strictness 1). Below 1.0 there is always some chance a word survives
unchanged, so short words often do."""

WARNING_MARGIN = 0.25
"""How far word strictness may exceed sound strictness before it is worth a
warning -- see ``strictness_warnings``."""


@dataclass(frozen=True)
class RealChoice:
    gloss: str
    pos: PartOfSpeech
    language: str
    form: str
    ipa: str


def strictness_warnings(traits: TraitProfile) -> list[str]:
    """A high word strictness with a much lower sound strictness lets the
    real-derived words keep their own sounds while the rest of the language
    is free to sound very different -- a split vocabulary. Allowed, never
    blocked; surfaced by the CLI and web UI."""
    word, sound = traits.source_word_strictness, traits.source_language_strictness
    if word > 0.0 and word > sound + WARNING_MARGIN:
        return [
            f"word strictness ({word:.2f}) is well above sound strictness ({sound:.2f}): words based on real "
            "source-language words will keep their own sounds while the rest of the vocabulary may sound very "
            "different (a split vocabulary). Raise the sound strictness to keep the two consistent."
        ]
    return []


def plan_real_words(
    spec: GenerationSpec, meanings: list[tuple[str, PartOfSpeech]], llm_client: LLMClient
) -> list[RealChoice]:
    """Which meanings follow a real word, and that word (see the module
    docstring). Empty whenever word strictness is 0 or no named source
    language matches a reference profile."""
    strictness = spec.traits.source_word_strictness
    matched = match_profiles_weighted(spec.traits.source_languages, spec.traits.source_language_weights)
    if strictness <= 0.0 or not matched:
        return []
    rng = random.Random(f"{spec.seed}:real-words")
    seeded = {example.gloss.lower() for example in spec.seed_examples}

    curated: dict[str, RealChoice] = {}
    gaps: list[tuple[str, str, PartOfSpeech]] = []
    for gloss, pos in meanings:
        if gloss.lower() in seeded or gloss in CONDITIONAL_MEANINGS:
            continue
        if rng.random() >= strictness:
            continue
        having = [(p, w) for p, w in matched if gloss in real_words(p.name)]
        if having:
            profile = rng.choices([p for p, _ in having], weights=[w for _, w in having])[0]
            form, ipa = real_words(profile.name)[gloss]
            curated[gloss] = RealChoice(gloss, pos, profile.name, form, ipa)
        else:
            profile = rng.choices([p for p, _ in matched], weights=[w for _, w in matched])[0]
            gaps.append((profile.name, gloss, pos))

    filled = real_words_llm.fetch_real_words(gaps, llm_client) if gaps else {}
    choices = dict(curated)
    for language, gloss, pos in gaps:
        answer = filled.get((language, gloss))
        if answer is not None:
            choices[gloss] = RealChoice(gloss, pos, language, answer[0], answer[1])
    return [choices[gloss] for gloss, _ in meanings if gloss in choices]


def exact_seed_examples(choices: list[RealChoice], strictness: float) -> tuple[SeedExample, ...]:
    """The exact-copy words (word strictness 1.0 only), as seed examples so
    ``phonology_gen`` forces their phonemes into the inventory."""
    if strictness < 1.0:
        return ()
    return tuple(SeedExample(gloss=c.gloss, form=c.form, ipa=c.ipa) for c in choices)


def build_real_entries(
    choices: list[RealChoice],
    strictness: float,
    seed: int,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    romanization: RomanizationScheme,
    tone_system: ToneSystem = ToneSystem(),
) -> tuple[LexicalEntry, ...]:
    rng = random.Random(f"{seed}:real-deviation")
    probability = (1.0 - strictness) * DEVIATION_SCALE
    entries = []
    for choice in choices:
        exact = strictness >= 1.0
        ipa = choice.ipa
        real_tones = ipa_tokenizer.tone_sequence(choice.ipa, _SYMBOLS)
        if not exact:
            deviated = phoneme_fit.deviate_ipa(choice.ipa, inventory, structure, rng, probability)
            unmarked = ipa_tokenizer.strip_tones(choice.ipa.replace(STRESS_MARK, "").replace(WORD_ACCENT_MARK, ""))
            # unchanged: keep the real spelling too
            exact = deviated == unmarked and _tones_fit(real_tones, tone_system)
            ipa = _with_tones(deviated, _fit_tones(real_tones, tone_system))
            # the real word's own stressed syllable carries over to the looser variant
            ipa = _with_stress(ipa, _real_stress_syllable(choice), inventory)
        tones = ipa_tokenizer.tone_sequence(ipa, _SYMBOLS)
        if exact:
            spelling = unicodedata.normalize("NFC", choice.form)
            notes = f"real word: {choice.language}"
        else:
            spelling = apply_grammatical_spelling(romanization, romanization.apply(ipa), choice.pos)
            notes = f"real-based word: {choice.language}"
        entries.append(
            LexicalEntry(
                ipa=ipa, romanization=spelling, glosses=(choice.gloss,), pos=choice.pos, tones=tones, notes=notes
            )
        )
    return tuple(entries)


_SYMBOLS = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)


def _real_stress_syllable(choice: "RealChoice") -> int | None:
    """Which syllable of the real word carries its curated stress mark (``None``
    for an unmarked word, a monosyllable, or a word the profile cannot read)."""
    if STRESS_MARK not in choice.ipa:
        return None
    try:
        return real_stress.stressed_syllable(choice.ipa, choice.language)
    except (StopIteration, ValueError, KeyError):
        return None


def _with_stress(ipa: str, syllable: int | None, inventory: PhonemeInventory) -> str:
    """``ipa`` with the stress mark before ``syllable`` (clamped to the word's last
    syllable); a monosyllable, or ``syllable is None``, stays unmarked."""
    if syllable is None:
        return ipa
    vowels = frozenset(v.ipa for v in inventory.vowels)
    tokens = [(s, d) for s, d in ipa_tokenizer.tokenize(ipa, _SYMBOLS) if s not in (STRESS_MARK, WORD_ACCENT_MARK)]
    starts = stress_gen.syllable_onset_starts(tuple(s for s, _ in tokens), vowels)
    if len(starts) < 2:
        return "".join(s + d for s, d in tokens)
    at = starts[min(syllable, len(starts) - 1)]
    return "".join((STRESS_MARK if i == at else "") + s + d for i, (s, d) in enumerate(tokens))


def _tones_fit(tones: tuple[ToneLevel, ...], tone_system: ToneSystem) -> bool:
    """A word keeps its real tones only when the language has a tone system
    holding every one of them (or the word has none)."""
    return not tones or (tone_system.enabled and set(tones) <= set(tone_system.levels))


# Nearest available level when the language lacks a tone: the same contour
# family first (rising ~ dipping), then the other levels.
_TONE_FALLBACKS = {
    ToneLevel.RISING: (ToneLevel.DIPPING, ToneLevel.HIGH, ToneLevel.MID, ToneLevel.LOW),
    ToneLevel.DIPPING: (ToneLevel.RISING, ToneLevel.LOW, ToneLevel.MID, ToneLevel.HIGH),
    ToneLevel.FALLING: (ToneLevel.LOW, ToneLevel.MID, ToneLevel.HIGH),
    ToneLevel.HIGH: (ToneLevel.RISING, ToneLevel.MID, ToneLevel.FALLING, ToneLevel.LOW),
    ToneLevel.MID: (ToneLevel.HIGH, ToneLevel.LOW, ToneLevel.RISING, ToneLevel.FALLING),
    ToneLevel.LOW: (ToneLevel.MID, ToneLevel.FALLING, ToneLevel.DIPPING, ToneLevel.HIGH),
    ToneLevel.NEUTRAL: (ToneLevel.MID, ToneLevel.LOW, ToneLevel.HIGH),
}


def _fit_tones(tones: tuple[ToneLevel, ...], tone_system: ToneSystem) -> tuple[ToneLevel, ...]:
    """The word's tones mapped onto the language's own tone levels (none at
    all when the language is not tonal)."""
    if not tone_system.enabled:
        return ()
    available = set(tone_system.levels)
    return tuple(
        tone if tone in available else next(t for t in _TONE_FALLBACKS[tone] if t in available)
        for tone in tones
    )


def _with_tones(ipa: str, tones: tuple[ToneLevel, ...]) -> str:
    """Attach ``tones`` to ``ipa``'s vowels in order (the last tone repeats
    over any extra syllables); an untoned word or language leaves it as is."""
    if not tones:
        return ipa
    vowels = {v.ipa for v in phonology_gen.ALL_VOWELS}
    out, seen = [], 0
    for symbol, deco in ipa_tokenizer.tokenize(ipa, _SYMBOLS):
        if symbol in vowels:
            symbol += TONE_DIACRITICS[tones[min(seen, len(tones) - 1)]]
            seen += 1
        out.append(symbol + deco)
    return "".join(out)
