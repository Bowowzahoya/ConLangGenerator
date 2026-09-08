"""Orchestrates one language's generation: phonology -> romanization ->
grammar -> core lexicon, all seeded from ``spec.seed`` for reproducibility."""

from __future__ import annotations

import random
import unicodedata

from conlang_generator.core.grammar import MorphologicalType
from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import LexicalEntry, Lexicon, PartOfSpeech
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import (
    grammar_gen,
    lexicon_gen,
    phonology_gen,
    romanization_gen,
    root_pattern,
    word_builder,
)
from conlang_generator.llm.base import LLMClient


def generate_language(name: str, spec: GenerationSpec, llm_client: LLMClient) -> Language:
    rng = random.Random(spec.seed)

    inventory, syllable_structure, tone_system, word_accent_system = phonology_gen.generate_phonology(rng, spec)
    romanization = romanization_gen.generate_romanization(
        rng,
        inventory,
        spec.traits.source_languages,
        spec.traits.requested_orthography_style,
        spec.forced_orthography,
        spec.allow_all_caps,
        spec.traits.source_language_strictness,
    )
    grammar = grammar_gen.generate_grammar(rng, spec)

    if grammar.morphological_type is not MorphologicalType.ISOLATING:
        affix = word_builder.build_syllable(rng, inventory, syllable_structure)
        grammar = grammar.model_copy(update={"plural_suffix": affix})

    if grammar.uses_root_and_pattern:
        templates = root_pattern.generate_templates(rng, inventory)
        grammar = grammar.model_copy(update={"templates": templates})

    seed_entries = tuple(
        LexicalEntry(
            ipa=example.ipa,
            # The user's own spelling, verbatim -- not reconstructed from
            # `example.ipa` via the scheme. A seed word's IPA is often
            # itself an approximation (e.g. this project doesn't model
            # diphthongs, so a real diphthong gets collapsed to its nearest
            # monophthong), so rule-based reconstruction can never recover
            # the real spelling even in principle; `form` already has it.
            romanization=unicodedata.normalize("NFC", example.form),
            glosses=(example.gloss,),
            pos=PartOfSpeech.NOUN,  # v1 simplification -- no POS guessing for seed examples
        )
        for example in spec.seed_examples
    )
    seeded_glosses = {example.gloss.lower() for example in spec.seed_examples}

    generated_entries = []
    for gloss, pos in lexicon_gen.CORE_MEANINGS:
        if gloss.lower() in seeded_glosses:
            continue
        if grammar.uses_root_and_pattern and pos in root_pattern.TEMPLATIC_POS:
            entry = root_pattern.propose_templatic_word(
                rng,
                inventory,
                grammar.templates,
                romanization,
                gloss,
                pos,
                llm_client,
                name,
                structure=syllable_structure,
                context=spec.traits.salient_context,
                source_languages=spec.traits.source_languages,
                strictness=spec.traits.source_language_strictness,
                word_accent_system=word_accent_system,
            )
        else:
            entry = lexicon_gen.propose_word(
                rng,
                inventory,
                syllable_structure,
                tone_system,
                word_accent_system,
                romanization,
                gloss,
                pos,
                llm_client,
                name,
                context=spec.traits.salient_context,
                source_languages=spec.traits.source_languages,
                strictness=spec.traits.source_language_strictness,
            )
        generated_entries.append(entry)
    generated_entries = tuple(generated_entries)

    return Language(
        name=name,
        spec=spec,
        phonology=inventory,
        syllable_structure=syllable_structure,
        tone_system=tone_system,
        word_accent=word_accent_system,
        romanization=romanization,
        grammar=grammar,
        lexicon=Lexicon(entries=seed_entries + generated_entries),
        history=("generated core language",),
    )
