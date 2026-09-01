"""Core-vocabulary generation.

Word *forms* are always phonotactically valid by construction: a handful of
candidate forms are built deterministically from the seeded RNG
(``word_builder.build_word``), and the LLM's only job is to pick the
best-sounding one for the requested meaning. This keeps the creative step
cheap, cache-friendly, and impossible to produce an invalid word -- there is
no free-form generation to validate or repair.
"""

from __future__ import annotations

import random

from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from conlang_generator.core.phonology import Manner, PhonemeInventory, SyllableStructure, ToneSystem
from conlang_generator.core.romanization import RomanizationScheme
from conlang_generator.generation import word_builder
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


def _choose_syllable_count(rng: random.Random, pos: PartOfSpeech, favor_short: bool) -> int:
    if pos in _FUNCTION_LIKE_POS:
        counts, weights = (1, 2, 3), (75, 20, 5)
    elif favor_short:
        counts, weights = (1, 2, 3), (45, 40, 15)
    else:
        counts, weights = (1, 2, 3, 4), (15, 35, 35, 15)
    return rng.choices(counts, weights=weights)[0]


def _propose_kinship_word(
    rng: random.Random,
    inventory: PhonemeInventory,
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
    word = word_builder.build_reduplicated_word(rng, inventory, _KINSHIP_MANNER_CLASSES[gloss_key], tone_mark=tone_mark)
    if word is None:
        return None
    return LexicalEntry(
        ipa=word,
        romanization=romanization.apply(word),
        glosses=(gloss,),
        pos=pos,
        tones=(tone, tone) if tone is not None else (),
    )


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
    """
    gloss_key = gloss.lower()

    if gloss_key in _KINSHIP_MANNER_CLASSES and rng.random() < _KINSHIP_PATTERN_PROBABILITY:
        kinship_entry = _propose_kinship_word(rng, inventory, tone_system, romanization, gloss, pos, gloss_key)
        if kinship_entry is not None:
            return kinship_entry

    num_syllables = _choose_syllable_count(rng, pos, favor_short)
    size_bias = _SIZE_BIAS_GLOSSES.get(gloss_key)

    tones: tuple = ()
    tone_marks: tuple[str, ...] = ()
    if tone_system.enabled:
        tones = tuple(rng.choice(tone_system.levels) for _ in range(num_syllables))
        tone_marks = tuple(tone_system.mark("", tone) for tone in tones)

    seen: set[str] = set()
    candidates: list[str] = []
    for _ in range(num_candidates):
        word = word_builder.build_word(rng, inventory, structure, num_syllables, tone_marks, size_bias=size_bias)
        if word not in seen:
            seen.add(word)
            candidates.append(word)

    if len(candidates) == 1:
        chosen = candidates[0]
    else:
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
        chosen = candidates[index]

    return LexicalEntry(
        ipa=chosen,
        romanization=romanization.apply(chosen),
        glosses=(gloss,),
        pos=pos,
        tones=tones,
    )
