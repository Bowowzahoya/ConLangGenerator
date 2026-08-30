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
from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure, ToneSystem
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
) -> LexicalEntry:
    """Build candidate forms deterministically, then ask the LLM to pick one."""
    num_syllables = rng.choice([1, 1, 2, 2, 3])

    tones: tuple = ()
    tone_marks: tuple[str, ...] = ()
    if tone_system.enabled:
        tones = tuple(rng.choice(tone_system.levels) for _ in range(num_syllables))
        tone_marks = tuple(tone_system.mark("", tone) for tone in tones)

    seen: set[str] = set()
    candidates: list[str] = []
    for _ in range(num_candidates):
        word = word_builder.build_word(rng, inventory, structure, num_syllables, tone_marks)
        if word not in seen:
            seen.add(word)
            candidates.append(word)

    if len(candidates) == 1:
        chosen = candidates[0]
    else:
        prompt = (
            f"Language: {language_name}. Choose the best-sounding word for the "
            f"meaning '{gloss}' ({pos.value}) from these candidates:\n"
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
