"""Core-vocabulary generation.

Word *forms* are always phonotactically valid by construction: a handful of
candidate forms are built deterministically from the seeded RNG
(``word_builder.build_word``), and the LLM's only job is to pick the
best-sounding one for the requested meaning. This keeps the creative step
cheap, cache-friendly, and impossible to produce an invalid word -- there is
no free-form generation to validate or repair.
"""

from __future__ import annotations

import math
import random

from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from conlang_generator.core.phonology import Manner, PhonemeInventory, SyllableStructure, ToneSystem
from conlang_generator.core.romanization import RomanizationScheme, apply_grammatical_spelling
from conlang_generator.generation import stress_gen, word_builder
from conlang_generator.generation.reference_languages import ReferenceLanguageProfile, match_profiles
from conlang_generator.llm.base import LLMClient, LLMRequest
from conlang_generator.llm.pricing import DEFAULT_MODEL

# A small Swadesh-style core-meaning list, enough to demonstrate generation
# and translation end to end. Expanding this list is one of the easiest ways
# to grow a v0 language's usefulness.
CORE_MEANINGS: tuple[tuple[str, PartOfSpeech], ...] = (
    ("I", PartOfSpeech.PRONOUN),
    ("you", PartOfSpeech.PRONOUN),
    ("he", PartOfSpeech.PRONOUN),
    ("we", PartOfSpeech.PRONOUN),
    ("this", PartOfSpeech.PRONOUN),
    ("that", PartOfSpeech.PRONOUN),
    ("water", PartOfSpeech.NOUN),
    ("fire", PartOfSpeech.NOUN),
    ("sun", PartOfSpeech.NOUN),
    ("moon", PartOfSpeech.NOUN),
    ("mountain", PartOfSpeech.NOUN),
    ("stone", PartOfSpeech.NOUN),
    ("tree", PartOfSpeech.NOUN),
    ("rain", PartOfSpeech.NOUN),
    ("wind", PartOfSpeech.NOUN),
    ("person", PartOfSpeech.NOUN),
    ("child", PartOfSpeech.NOUN),
    ("mother", PartOfSpeech.NOUN),
    ("father", PartOfSpeech.NOUN),
    ("animal", PartOfSpeech.NOUN),
    ("bird", PartOfSpeech.NOUN),
    ("fish", PartOfSpeech.NOUN),
    ("hand", PartOfSpeech.NOUN),
    ("eye", PartOfSpeech.NOUN),
    ("name", PartOfSpeech.NOUN),
    ("big", PartOfSpeech.ADJECTIVE),
    ("small", PartOfSpeech.ADJECTIVE),
    ("high", PartOfSpeech.ADJECTIVE),
    ("low", PartOfSpeech.ADJECTIVE),
    ("good", PartOfSpeech.ADJECTIVE),
    ("bad", PartOfSpeech.ADJECTIVE),
    ("hot", PartOfSpeech.ADJECTIVE),
    ("cold", PartOfSpeech.ADJECTIVE),
    ("new", PartOfSpeech.ADJECTIVE),
    ("old", PartOfSpeech.ADJECTIVE),
    ("go", PartOfSpeech.VERB),
    ("come", PartOfSpeech.VERB),
    ("see", PartOfSpeech.VERB),
    ("eat", PartOfSpeech.VERB),
    ("drink", PartOfSpeech.VERB),
    ("say", PartOfSpeech.VERB),
    ("know", PartOfSpeech.VERB),
    ("sleep", PartOfSpeech.VERB),
    ("give", PartOfSpeech.VERB),
    ("one", PartOfSpeech.NUMERAL),
    ("two", PartOfSpeech.NUMERAL),
    ("three", PartOfSpeech.NUMERAL),
    ("not", PartOfSpeech.PARTICLE),
    ("and", PartOfSpeech.PARTICLE),
)


_FUNCTION_LIKE_POS = {PartOfSpeech.PRONOUN, PartOfSpeech.PARTICLE}

STABILITY_TIER: dict[PartOfSpeech, float] = {
    # Real-world lexical-replacement rate isn't flat across vocabulary --
    # glottochronology's core finding is that closed-class words (pronouns,
    # low numerals, basic particles) are far more resistant to replacement
    # than open-class content words, with basic nouns for natural
    # kinds/body parts in between and verbs/adjectives replacing fastest.
    # Used by ``sound_change.py`` as a multiplier on replacement's
    # effective half-life -- reuses each entry's existing ``pos`` rather
    # than a separate per-gloss table, since POS already captures the
    # dominant real effect for a vocabulary this basic.
    PartOfSpeech.PRONOUN: 4.0,
    PartOfSpeech.PARTICLE: 4.0,
    PartOfSpeech.NUMERAL: 4.0,
    PartOfSpeech.NOUN: 1.5,
    PartOfSpeech.VERB: 1.0,
    PartOfSpeech.ADJECTIVE: 1.0,
    PartOfSpeech.OTHER: 1.0,
}

# Sound symbolism for specific glosses -- distinct from the whole-language
# aesthetic_harshness "vibe": these are documented tendencies tied to a
# *particular meaning*, not the language as a whole.
_KINSHIP_MANNER_CLASSES: dict[str, tuple[Manner, ...]] = {
    # The "mama"/"papa" convergence (Jakobson 1960): infants' earliest
    # producible sounds get recruited as address terms for caregivers,
    # independently across unrelated language families -- nasal onsets
    # skew toward "mother", oral stops toward "father".
    "mother": (Manner.NASAL,),
    "father": (Manner.STOP,),
}
_KINSHIP_PATTERN_PROBABILITY = 0.8

_SIZE_BIAS_GLOSSES: dict[str, str] = {
    # Size sound symbolism (Sapir 1929 and later replications): high front
    # vowels statistically evoke smallness cross-linguistically, low back
    # vowels largeness.
    "small": "small",
    "big": "big",
}


_GENERIC_AVERAGE_SYLLABLES = 1.35
"""The pivot a curated ``ReferenceLanguageProfile.core_vocabulary_average_syllables``
tilts away from -- deliberately equal to the recalibrated content-word
table's own mean below, so "no source language" and "strictness=0.0" both
naturally coincide with this same realistic default, no separate no-op
case needed. Recalibrated (see ``choose_syllable_count``'s own docstring)
from a hand-counted average across this project's own ``CORE_MEANINGS``
glosses translated into English (~1.14), Dutch (~1.27), French (~1.35),
and German (~1.43) -- the old generic default of ~1.7 ran higher than
even German's real figure."""

_LENGTH_BIAS_TILT_SCALE = 4.5
"""Tuned so a curated profile at ``strictness=1.0`` produces a clearly
measurable, but not cartoonish, shift in sampled average syllable count --
real cross-linguistic differences in core-vocabulary average syllable
count are inherently modest (this project's own four curated profiles
span only ~1.14-1.43), so a much larger scale than other
``biased_probability``-style constants in this codebase is needed for the
tilt to actually move the sampled mean toward that curated figure -- see
``choose_syllable_count``."""


def choose_syllable_count(
    rng: random.Random,
    pos: PartOfSpeech,
    favor_short: bool,
    average_syllables: float | None = None,
    strictness: float = 0.0,
) -> int:
    """``average_syllables`` (a matched ``source_languages`` profile's own
    ``core_vocabulary_average_syllables``, when curated) and ``strictness``
    together tilt the chosen base table toward that language's own real
    word-length tendency, via exponential tilting: each candidate count's
    weight is scaled by ``exp(theta * count)``, which smoothly shifts the
    distribution's mean up (a longer-than-generic language) or down
    (shorter), and -- unlike every other ``source_language_strictness``-
    gated mechanism in this project -- can never zero out an option, even
    at ``strictness=1.0``. That's a deliberate choice: those other
    mechanisms model genuine categorical restrictions (a sound either can
    or can't open a syllable), but average word length is a statistical
    *tendency* -- even Mandarin has some bisyllabic roots, even German has
    plenty of monosyllabic words -- so this always leaves every count
    reachable. A no-op (returns the base table unchanged) when
    ``average_syllables`` is ``None`` (no curated match) or
    ``strictness <= 0.0``, same "no source language, no bias" guarantee
    every other axis in this feature already has.
    """
    if pos in _FUNCTION_LIKE_POS:
        counts, weights = (1, 2, 3), (90, 9, 1)
    elif favor_short:
        counts, weights = (1, 2, 3), (70, 25, 5)
    else:
        counts, weights = (1, 2, 3, 4), (15, 35, 35, 15)
    if average_syllables is not None and strictness > 0.0:
        theta = _LENGTH_BIAS_TILT_SCALE * strictness * (average_syllables - _GENERIC_AVERAGE_SYLLABLES)
        weights = [w * math.exp(theta * c) for w, c in zip(weights, counts)]
    return rng.choices(counts, weights=weights)[0]


def _resolve_average_syllables(reference_profiles: tuple[ReferenceLanguageProfile, ...]) -> float | None:
    """Averages ``core_vocabulary_average_syllables`` across every matched
    profile that has curated it, ignoring ones that haven't (abstain, same
    convention as every other curated field in this feature) -- ``None``
    when none of them have."""
    values = [
        p.core_vocabulary_average_syllables for p in reference_profiles if p.core_vocabulary_average_syllables is not None
    ]
    return sum(values) / len(values) if values else None




def _propose_kinship_word(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    tone_system: ToneSystem,
    romanization: RomanizationScheme,
    gloss: str,
    pos: PartOfSpeech,
    gloss_key: str,
) -> LexicalEntry | None:
    """Try the mama/papa-style reduplicated pattern; ``None`` means the
    inventory has no matching consonant class and the caller should fall
    back to ``propose_word``'s normal candidate-build/LLM-choice path."""
    tone = rng.choice(tone_system.levels) if tone_system.enabled else None
    tone_mark = tone_system.mark("", tone) if tone is not None else ""
    word = word_builder.build_reduplicated_word(
        rng, inventory, _KINSHIP_MANNER_CLASSES[gloss_key], tone_mark=tone_mark,
        excluded_onset_consonants=structure.excluded_onset_consonants,
    )
    if word is None:
        return None
    return LexicalEntry(
        ipa=word,
        romanization=apply_grammatical_spelling(romanization, romanization.apply(word), pos),
        glosses=(gloss,),
        pos=pos,
        tones=(tone, tone) if tone is not None else (),
    )


def choose_best_candidate(
    rng: random.Random,
    candidates: list[str],
    gloss: str,
    pos: PartOfSpeech,
    llm_client: LLMClient,
    language_name: str,
    context: str = "",
) -> str:
    """Ask the LLM which of several deterministically-built candidate
    forms sounds best for ``gloss`` -- the one creative step in an
    otherwise fully rule-based pipeline, kept cheap and cache-friendly
    since the candidates themselves are already guaranteed valid. Shared
    by ``propose_word`` and ``root_pattern.propose_templatic_word`` so the
    LLM-request shape stays in one place.
    """
    if len(candidates) == 1:
        return candidates[0]
    context_line = f" Context: {context}." if context else ""
    prompt = (
        f"Language: {language_name}.{context_line} Choose the best-sounding "
        f"word for the meaning '{gloss}' ({pos.value}) from these candidates:\n"
        + "\n".join(f"{i + 1}. {c}" for i, c in enumerate(candidates))
        + "\nReply with only the number."
    )
    request = LLMRequest(
        system=(
            "You are helping design a constructed language's vocabulary. "
            "Pick the candidate word that best fits the requested meaning "
            "and part of speech, considering sound symbolism."
        ),
        prompt=prompt,
        model=DEFAULT_MODEL,
        max_tokens=8,
        purpose="lexicon.propose_word",
        metadata={
            "fake_strategy": "choose_index",
            "num_options": str(len(candidates)),
        },
    )
    response = llm_client.complete(request)
    digits = "".join(ch for ch in response.text if ch.isdigit())
    index = int(digits) - 1 if digits else 0
    if not (0 <= index < len(candidates)):
        index = 0
    return candidates[index]


def propose_word(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    tone_system: ToneSystem,
    romanization: RomanizationScheme,
    gloss: str,
    pos: PartOfSpeech,
    llm_client: LLMClient,
    language_name: str,
    num_candidates: int = 5,
    context: str = "",
    favor_short: bool = True,
    source_languages: tuple[str, ...] = (),
    strictness: float = 0.0,
) -> LexicalEntry:
    """Build candidate forms deterministically, then ask the LLM to pick one.

    ``context`` is free-text flavor (e.g. ``TraitProfile.salient_context``)
    appended to the LLM prompt when non-empty -- the "unknown unknowns"
    channel getting an actual, if modest, effect on word choice.

    ``favor_short`` implements Zipf's law of abbreviation (frequent/basic
    words are shorter, cross-linguistically) using the one frequency proxy
    this system has: core-vocabulary generation passes the default
    ``True``, later coinage of less-basic vocabulary
    (``translation/expansion.py``) passes ``False``. Function-like POS
    (pronouns, particles) skew short regardless, matching their own
    well-documented cross-linguistic brevity.

    ``source_languages``/``strictness`` resolve this call's own reference
    bias internally, the same self-contained way
    ``phonology_gen.generate_phonology``/``romanization_gen.generate_romanization``/
    ``grammar_gen.generate_grammar`` already do -- see
    ``choose_syllable_count``'s own docstring for what the resulting tilt
    actually does.
    """
    gloss_key = gloss.lower()

    if gloss_key in _KINSHIP_MANNER_CLASSES and rng.random() < _KINSHIP_PATTERN_PROBABILITY:
        kinship_entry = _propose_kinship_word(rng, inventory, structure, tone_system, romanization, gloss, pos, gloss_key)
        if kinship_entry is not None:
            return kinship_entry

    reference_profiles = match_profiles(source_languages)
    average_syllables = _resolve_average_syllables(reference_profiles)
    num_syllables = choose_syllable_count(rng, pos, favor_short, average_syllables, strictness)
    size_bias = _SIZE_BIAS_GLOSSES.get(gloss_key)
    stress_pattern, stress_deviation_rate = stress_gen.resolve_stress_pattern(reference_profiles)

    tones: tuple = ()
    tone_marks: tuple[str, ...] = ()
    if tone_system.enabled:
        tones = tuple(rng.choice(tone_system.levels) for _ in range(num_syllables))
        tone_marks = tuple(tone_system.mark("", tone) for tone in tones)

    seen: set[str] = set()
    candidates: list[str] = []
    for _ in range(num_candidates):
        word = word_builder.build_word(
            rng, inventory, structure, num_syllables, tone_marks, size_bias=size_bias,
            stress_pattern=stress_pattern, stress_deviation_rate=stress_deviation_rate, stress_strictness=strictness,
        )
        if word not in seen:
            seen.add(word)
            candidates.append(word)

    chosen = choose_best_candidate(rng, candidates, gloss, pos, llm_client, language_name, context)

    return LexicalEntry(
        ipa=chosen,
        romanization=apply_grammatical_spelling(romanization, romanization.apply(chosen), pos),
        glosses=(gloss,),
        pos=pos,
        tones=tones,
    )
