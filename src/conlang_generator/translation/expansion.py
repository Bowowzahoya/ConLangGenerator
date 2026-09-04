"""Coins a new word for a gloss the language doesn't have yet.

Reuses ``generation.lexicon_gen.propose_word`` (or, for a root-and-pattern
language's noun/verb/adjective glosses, ``generation.root_pattern.
propose_templatic_word``) so a coined word is phonotactically identical in
kind to a word generated at creation time. The per-word RNG is derived
from a stable hash of ``(language.spec.seed, gloss)`` -- not from the
shared generation RNG stream -- so coining is reproducible independent of
what order words happen to be requested in.
"""

from __future__ import annotations

import hashlib
import random

from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from conlang_generator.generation import root_pattern
from conlang_generator.generation.lexicon_gen import propose_word
from conlang_generator.llm.base import LLMClient


def _derived_seed(language: Language, salt: str) -> int:
    payload = f"{language.spec.seed}:{salt}".encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest(), 16) % (2**32)


def coin_word(
    language: Language, gloss: str, pos: PartOfSpeech, llm_client: LLMClient
) -> LexicalEntry:
    for attempt in range(6):
        salt = gloss if attempt == 0 else f"{gloss}#{attempt}"
        rng = random.Random(_derived_seed(language, salt))
        if language.grammar.uses_root_and_pattern and pos in root_pattern.TEMPLATIC_POS:
            entry = root_pattern.propose_templatic_word(
                rng,
                language.phonology,
                language.grammar.templates,
                language.romanization,
                gloss,
                pos,
                llm_client,
                language.name,
                structure=language.syllable_structure,
                context=language.spec.traits.salient_context,
            )
        else:
            entry = propose_word(
                rng,
                language.phonology,
                language.syllable_structure,
                language.tone_system,
                language.romanization,
                gloss,
                pos,
                llm_client,
                language.name,
                context=language.spec.traits.salient_context,
                favor_short=False,
            )
        if language.lexicon.by_form(entry.romanization) is None:
            return entry
    return entry  # extremely unlikely collision streak; accept it rather than loop forever
