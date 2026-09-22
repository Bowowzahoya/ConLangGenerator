"""Core-vocabulary generation.

Word *forms* are always phonotactically valid by construction: a handful of
candidate forms are built deterministically from the seeded RNG
(``word_builder.build_word``), and the final pick among them is either a
plain seeded-rng choice (``word_selection="algorithmic"``, the default, no
LLM call at all) or the LLM's best-sounding pick (``"llm"``, batched into one
request across the whole core vocabulary -- see ``choose_best_candidates_
batch``). Either way the step is cheap, cache-friendly, and impossible to
produce an invalid word -- there is no free-form generation to validate or
repair. Sound symbolism itself (mother/father, big/small) lives in the
candidate-*building* bias (``_propose_kinship_word``, ``_SIZE_BIAS_GLOSSES``),
not in this final pick.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Callable
from dataclasses import dataclass

from conlang_generator.core.grammar import WordClass
from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from conlang_generator.core.phonology import (
    Manner, PhonemeInventory, SyllableStructure, ToneLevel, ToneSystem, WordAccentSystem,
)
from conlang_generator.core.romanization import RomanizationScheme, apply_grammatical_spelling
from conlang_generator.generation import stress_gen, word_accent_gen, word_builder, word_class_gen
from conlang_generator.generation.extended_meanings import EXTENDED_MEANINGS
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
    ("the", PartOfSpeech.PARTICLE),
    ("be", PartOfSpeech.VERB),
)

ALL_MEANINGS: tuple[tuple[str, PartOfSpeech], ...] = CORE_MEANINGS + EXTENDED_MEANINGS
"""Every meaning this project can pregenerate, most basic first (the
original 51, then ``extended_meanings.EXTENDED_MEANINGS``) --
``GenerationSpec.vocabulary_size`` takes a prefix of this."""

ESSENTIAL_GLOSSES: frozenset[str] = frozenset(
    {"I", "you", "he", "we", "this", "that", "not", "and", "the", "be"}
)
"""Grammatical words translation itself relies on (pronouns for agreement,
negation/coordination/article/copula slots) -- always pregenerated even for
a very small ``vocabulary_size``."""


def select_meanings(vocabulary_size: int) -> list[tuple[str, PartOfSpeech]]:
    """The first ``vocabulary_size`` entries of ``ALL_MEANINGS``, plus any
    ``ESSENTIAL_GLOSSES`` a small size would otherwise cut. Anything not
    pregenerated is still coined on demand during translation
    (``translation/expansion.py``) and then reused."""
    chosen = list(ALL_MEANINGS[: max(0, vocabulary_size)])
    present = {gloss for gloss, _ in chosen}
    chosen.extend(entry for entry in ALL_MEANINGS if entry[0] in ESSENTIAL_GLOSSES and entry[0] not in present)
    return chosen


CONDITIONAL_MEANINGS: dict[str, str] = {"the": "has_articles", "be": "has_overt_copula"}
"""Maps a gloss in ``CORE_MEANINGS`` to the ``core.grammar.GrammarProfile``
boolean attribute that gates whether this run actually coins it at all --
a language without articles/an overt copula shouldn't have the
corresponding lexeme in the first place, unlike every other, always-
generated core meaning above. Consulted by ``generator.py``'s own
core-vocabulary loop."""


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
    stress_pattern: str = "",
    stress_deviation_rate: float | None = None,
    stress_strictness: float = 0.0,
    word_accent_realization: str = "",
    word_accent_pattern: str = "",
    word_accent_deviation_rate: float | None = None,
    word_accent_length_rate: float | None = None,
    word_accent_window: int | None = None,
    word_classes: tuple[WordClass, ...] = (),
    word_class_deviation_rate: float | None = None,
) -> LexicalEntry | None:
    """Try the mama/papa-style reduplicated pattern; ``None`` means the
    inventory has no matching consonant class and the caller should fall
    back to ``propose_word``'s normal candidate-build/LLM-choice path."""
    tone = rng.choice(_non_neutral(tone_system)) if tone_system.enabled else None
    tone_mark = tone_system.mark("", tone) if tone is not None else ""
    word = word_builder.build_reduplicated_word(
        rng, inventory, _KINSHIP_MANNER_CLASSES[gloss_key], tone_mark=tone_mark,
        excluded_onset_consonants=structure.excluded_onset_consonants,
        stress_pattern=stress_pattern, stress_deviation_rate=stress_deviation_rate, stress_strictness=stress_strictness,
        word_accent_realization=word_accent_realization, word_accent_pattern=word_accent_pattern,
        word_accent_deviation_rate=word_accent_deviation_rate, word_accent_strictness=stress_strictness,
        word_accent_length_rate=word_accent_length_rate, word_accent_window=word_accent_window,
    )
    if word is None:
        return None
    assigned_class = word_class_gen.assign_word_class(rng, word_classes, word_class_deviation_rate, pos)
    word = word_class_gen.apply_word_class(
        rng, assigned_class, word, inventory,
        stress_pattern, stress_deviation_rate, stress_strictness,
        word_accent_realization=word_accent_realization, word_accent_pattern=word_accent_pattern,
        word_accent_deviation_rate=word_accent_deviation_rate, word_accent_length_rate=word_accent_length_rate,
        word_accent_window=word_accent_window,
    )
    return LexicalEntry(
        ipa=word,
        romanization=apply_grammatical_spelling(romanization, romanization.apply(word), pos),
        glosses=(gloss,),
        pos=pos,
        tones=(tone, tone) if tone is not None else (),
        word_class=assigned_class.name if assigned_class is not None else None,
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


def resolve_candidate(
    rng: random.Random,
    candidates: list[str],
    gloss: str,
    pos: PartOfSpeech,
    llm_client: LLMClient,
    language_name: str,
    context: str = "",
    word_selection: str = "algorithmic",
) -> str:
    """Picks one of an already-built, already-valid candidate pool.
    ``word_selection="algorithmic"`` (the default) never touches the LLM --
    a uniform pick via the seeded ``rng``, so the choice stays
    reproducible per seed; ``"llm"`` delegates to ``choose_best_candidate``
    (one LLM call, sound-symbolism-informed). A single-candidate pool
    needs no choice under either mode. Candidate *building* is always
    algorithmic regardless -- this only governs the final pick."""
    if len(candidates) == 1:
        return candidates[0]
    if word_selection == "algorithmic":
        return rng.choice(candidates)
    return choose_best_candidate(rng, candidates, gloss, pos, llm_client, language_name, context)


@dataclass
class PendingWord:
    """One word whose deterministic candidate pool is built but whose
    final pick hasn't been made -- lets a caller (``generator.py``'s core-
    vocabulary loop) resolve every pending word's choice in one batched
    LLM request (``choose_best_candidates_batch``) instead of one call
    each. ``finish`` maps the chosen candidate to the finished entry (word
    class, stress re-derivation, spelling -- all algorithmic)."""

    gloss: str
    pos: PartOfSpeech
    candidates: list[str]
    finish: Callable[[str], LexicalEntry]


BATCH_CHUNK_SIZE = 100
"""Most words per batched request -- a full 400-word vocabulary becomes a
few requests of manageable size (and a bounded reply to parse) instead of
one very long one."""


def choose_best_candidates_batch(
    pending: list[PendingWord], llm_client: LLMClient, language_name: str, context: str = ""
) -> list[str]:
    """Chooses for every pending word, ``BATCH_CHUNK_SIZE`` words per LLM
    request (see ``_choose_chunk``)."""
    chosen: list[str] = []
    for start in range(0, len(pending), BATCH_CHUNK_SIZE):
        chosen.extend(_choose_chunk(pending[start : start + BATCH_CHUNK_SIZE], llm_client, language_name, context))
    return chosen


def _choose_chunk(
    pending: list[PendingWord], llm_client: LLMClient, language_name: str, context: str = ""
) -> list[str]:
    """One LLM request choosing among every pending word's candidates at
    once, instead of ``choose_best_candidate``'s one request per word.
    Returns the chosen candidate string per pending word, in order.
    Parsing is lenient (same spirit as ``prompt_classifier._parse``): any
    missing/out-of-range/malformed answer falls back to that word's first
    candidate, mirroring ``choose_best_candidate``'s own fallback."""
    if not pending:
        return []
    context_line = f" Context: {context}." if context else ""
    listing = "\n".join(
        f"{i}. {pw.gloss} ({pw.pos.value}): " + " ".join(f"{j + 1}) {c}" for j, c in enumerate(pw.candidates))
        for i, pw in enumerate(pending, start=1)
    )
    prompt = (
        f"Language: {language_name}.{context_line} For each numbered word below, choose the candidate "
        "that sounds best for its meaning. Reply with exactly one line per word in the form "
        "WORD_NUMBER:CANDIDATE_NUMBER (for example 1:3), and nothing else.\n" + listing
    )
    request = LLMRequest(
        system=(
            "You are helping design a constructed language's vocabulary. For each word, pick the "
            "candidate that best fits the requested meaning and part of speech, considering sound symbolism."
        ),
        prompt=prompt,
        model=DEFAULT_MODEL,
        max_tokens=max(256, 8 * len(pending)),
        purpose="lexicon.propose_words_batch",
        metadata={
            "fake_strategy": "batch_choose_index",
            "candidate_counts": ",".join(str(len(pw.candidates)) for pw in pending),
        },
    )
    response = llm_client.complete(request)
    answers = {int(w): int(c) for w, c in re.findall(r"(\d+)\s*[:.\-]\s*(\d+)", response.text)}
    chosen: list[str] = []
    for i, pw in enumerate(pending, start=1):
        index = answers.get(i, 1) - 1
        if not 0 <= index < len(pw.candidates):
            index = 0
        chosen.append(pw.candidates[index])
    return chosen


def _non_neutral(tone_system: ToneSystem) -> tuple:
    """The tone levels a word's *first* syllable may take: the neutral tone
    (real Mandarin's) only ever follows another syllable. Identical to
    ``tone_system.levels`` -- and draws the same -- for every language
    without a neutral tone."""
    levels = tuple(level for level in tone_system.levels if level is not ToneLevel.NEUTRAL)
    return levels or tone_system.levels


def build_pending_word(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    tone_system: ToneSystem,
    word_accent_system: WordAccentSystem,
    romanization: RomanizationScheme,
    gloss: str,
    pos: PartOfSpeech,
    num_candidates: int = 5,
    favor_short: bool = True,
    source_languages: tuple[str, ...] = (),
    strictness: float = 0.0,
    word_classes: tuple[WordClass, ...] = (),
    word_class_deviation_rate: float | None = None,
) -> PendingWord | LexicalEntry:
    """Build candidate forms deterministically -- everything ``propose_word``
    does short of the final pick. Returns a finished ``LexicalEntry``
    directly when ``_propose_kinship_word`` already resolved the word (no
    candidates, no choice, no LLM), otherwise a ``PendingWord`` whose
    ``finish`` completes it once a candidate is chosen (by
    ``resolve_candidate`` one word at a time, or
    ``choose_best_candidates_batch`` for many at once).

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

    ``word_accent_system`` (this run's own, already-resolved
    ``WordAccentSystem`` -- see ``phonology_gen.generate_phonology``) gates
    whether this word gets a word-accent mark at all, the same
    per-language-systemic role ``tone_system.enabled`` already plays for
    tone; when it's enabled, this call still resolves the actual
    ``word_accent_pattern``/``word_accent_deviation_rate`` fresh from
    ``reference_profiles`` (via ``word_accent_gen.resolve_word_accent``),
    the same "stored system decides *whether*, matched profile decides
    *how*" split ``tone_system.enabled``/``tone_system.levels`` already
    has.
    """
    gloss_key = gloss.lower()
    reference_profiles = match_profiles(source_languages)
    stress_pattern, stress_deviation_rate = stress_gen.resolve_stress_pattern(reference_profiles)
    word_accent_pattern = ""
    word_accent_deviation_rate: float | None = None
    word_accent_length_rate: float | None = None
    word_accent_window: int | None = None
    if word_accent_system.enabled:
        (
            _, word_accent_pattern, word_accent_deviation_rate, word_accent_length_rate, word_accent_window,
        ) = word_accent_gen.resolve_word_accent(reference_profiles)

    if gloss_key in _KINSHIP_MANNER_CLASSES and rng.random() < _KINSHIP_PATTERN_PROBABILITY:
        kinship_entry = _propose_kinship_word(
            rng, inventory, structure, tone_system, romanization, gloss, pos, gloss_key,
            stress_pattern=stress_pattern, stress_deviation_rate=stress_deviation_rate, stress_strictness=strictness,
            word_accent_realization=word_accent_system.realization, word_accent_pattern=word_accent_pattern,
            word_accent_deviation_rate=word_accent_deviation_rate, word_accent_length_rate=word_accent_length_rate,
            word_accent_window=word_accent_window,
            word_classes=word_classes, word_class_deviation_rate=word_class_deviation_rate,
        )
        if kinship_entry is not None:
            return kinship_entry

    average_syllables = _resolve_average_syllables(reference_profiles)
    num_syllables = choose_syllable_count(rng, pos, favor_short, average_syllables, strictness)
    size_bias = _SIZE_BIAS_GLOSSES.get(gloss_key)
    reduce_unstressed_vowels = any(p.stress_driven_vowel_reduction for p in reference_profiles)
    word_level_phonology = next((p.word_level_phonology for p in reference_profiles if p.word_level_phonology), "")

    tones: tuple = ()
    tone_marks: tuple[str, ...] = ()
    if tone_system.enabled:
        tones = tuple(
            rng.choice(_non_neutral(tone_system) if position == 0 else tone_system.levels)
            for position in range(num_syllables)
        )
        tone_marks = tuple(tone_system.mark("", tone) for tone in tones)

    seen: set[str] = set()
    candidates: list[str] = []
    for _ in range(num_candidates):
        word = word_builder.build_word(
            rng, inventory, structure, num_syllables, tone_marks, size_bias=size_bias,
            stress_pattern=stress_pattern, stress_deviation_rate=stress_deviation_rate, stress_strictness=strictness,
            reduce_unstressed_vowels=reduce_unstressed_vowels,
            word_accent_realization=word_accent_system.realization, word_accent_pattern=word_accent_pattern,
            word_accent_deviation_rate=word_accent_deviation_rate, word_accent_strictness=strictness,
            word_accent_length_rate=word_accent_length_rate, word_accent_window=word_accent_window,
            word_level_phonology=word_level_phonology, word_level_phonology_strictness=strictness,
        )
        if word not in seen:
            seen.add(word)
            candidates.append(word)

    def finish(chosen: str) -> LexicalEntry:
        assigned_class = word_class_gen.assign_word_class(rng, word_classes, word_class_deviation_rate, pos)
        chosen = word_class_gen.apply_word_class(
            rng, assigned_class, chosen, inventory,
            stress_pattern, stress_deviation_rate, strictness,
            word_accent_realization=word_accent_system.realization, word_accent_pattern=word_accent_pattern,
            word_accent_deviation_rate=word_accent_deviation_rate, word_accent_length_rate=word_accent_length_rate,
            word_accent_window=word_accent_window,
        )
        return LexicalEntry(
            ipa=chosen,
            romanization=apply_grammatical_spelling(romanization, romanization.apply(chosen), pos),
            glosses=(gloss,),
            pos=pos,
            tones=tones,
            word_class=assigned_class.name if assigned_class is not None else None,
        )

    return PendingWord(gloss=gloss, pos=pos, candidates=candidates, finish=finish)


def propose_word(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    tone_system: ToneSystem,
    word_accent_system: WordAccentSystem,
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
    word_classes: tuple[WordClass, ...] = (),
    word_class_deviation_rate: float | None = None,
    word_selection: str = "algorithmic",
) -> LexicalEntry:
    """Build candidate forms deterministically (``build_pending_word``),
    then pick one -- via a uniform seeded-rng pick by default
    (``word_selection="algorithmic"``, no LLM call at all) or one LLM
    call (``"llm"``, sound-symbolism-informed) -- see
    ``resolve_candidate``. ``context`` is free-text flavor (e.g.
    ``TraitProfile.salient_context``) appended to the LLM prompt when
    non-empty; only meaningful for ``"llm"``."""
    pending = build_pending_word(
        rng, inventory, structure, tone_system, word_accent_system, romanization, gloss, pos,
        num_candidates=num_candidates, favor_short=favor_short, source_languages=source_languages,
        strictness=strictness, word_classes=word_classes, word_class_deviation_rate=word_class_deviation_rate,
    )
    if isinstance(pending, LexicalEntry):
        return pending
    chosen = resolve_candidate(
        rng, pending.candidates, gloss, pos, llm_client, language_name, context, word_selection
    )
    return pending.finish(chosen)
