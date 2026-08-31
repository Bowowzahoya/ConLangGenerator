"""Orchestrates one language's generation: phonology -> romanization ->
grammar -> core lexicon, all seeded from ``spec.seed`` for reproducibility."""

from __future__ import annotations

import random

from conlang_generator.core.grammar import MorphologicalType
from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import Lexicon
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import grammar_gen, lexicon_gen, phonology_gen, romanization_gen, word_builder
from conlang_generator.llm.base import LLMClient


def generate_language(name: str, spec: GenerationSpec, llm_client: LLMClient) -> Language:
    rng = random.Random(spec.seed)

    inventory, syllable_structure, tone_system = phonology_gen.generate_phonology(rng, spec)
    romanization = romanization_gen.generate_romanization(rng, inventory)
    grammar = grammar_gen.generate_grammar(rng, spec)

    if grammar.morphological_type is not MorphologicalType.ISOLATING:
        affix = word_builder.build_syllable(rng, inventory, syllable_structure)
        grammar = grammar.model_copy(update={"plural_suffix": affix})

    entries = tuple(
        lexicon_gen.propose_word(
            rng,
            inventory,
            syllable_structure,
            tone_system,
            romanization,
            gloss,
            pos,
            llm_client,
            name,
            context=spec.traits.salient_context,
        )
        for gloss, pos in lexicon_gen.CORE_MEANINGS
    )

    return Language(
        name=name,
        spec=spec,
        phonology=inventory,
        syllable_structure=syllable_structure,
        tone_system=tone_system,
        romanization=romanization,
        grammar=grammar,
        lexicon=Lexicon(entries=entries),
        history=("generated core language",),
    )
