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
    inflection_gen,
    lexicon_gen,
    phonology_gen,
    romanization_gen,
    root_pattern,
    word_builder,
    word_class_gen,
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
        spec.traits.source_language_weights,
    )
    grammar = grammar_gen.generate_grammar(rng, spec)

    if grammar.morphological_type is not MorphologicalType.ISOLATING:
        affix = word_builder.build_syllable(rng, inventory, syllable_structure)
        grammar = grammar.model_copy(update={"plural_suffix": affix})

    if grammar.uses_root_and_pattern:
        templates = root_pattern.generate_templates(rng, inventory)
        grammar = grammar.model_copy(update={"templates": templates})

    word_classes, word_class_deviation_rate = word_class_gen.generate_word_classes(
        rng, spec, inventory, syllable_structure, grammar.uses_root_and_pattern, grammar.morphological_type
    )
    grammar = grammar.model_copy(
        update={"word_classes": word_classes, "word_class_deviation_rate": word_class_deviation_rate}
    )

    case_affixes = inflection_gen.generate_case_affixes(rng, inventory, syllable_structure, grammar.cases)
    tense_affixes = inflection_gen.generate_tense_affixes(rng, inventory, syllable_structure, grammar.tenses)
    agreement_affixes = inflection_gen.generate_agreement_affixes(rng, inventory, syllable_structure)
    grammar = grammar.model_copy(
        update={"case_affixes": case_affixes, "tense_affixes": tense_affixes, "agreement_affixes": agreement_affixes}
    )

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

    def build_core_pending(gloss: str, pos: PartOfSpeech) -> lexicon_gen.PendingWord | LexicalEntry:
        if grammar.uses_root_and_pattern and pos in root_pattern.TEMPLATIC_POS:
            return root_pattern.build_pending_templatic_word(
                rng,
                inventory,
                grammar.templates,
                romanization,
                gloss,
                pos,
                structure=syllable_structure,
                source_languages=spec.traits.source_languages,
                strictness=spec.traits.source_language_strictness,
                word_accent_system=word_accent_system,
                word_classes=grammar.word_classes,
                word_class_deviation_rate=grammar.word_class_deviation_rate,
            )
        return lexicon_gen.build_pending_word(
            rng,
            inventory,
            syllable_structure,
            tone_system,
            word_accent_system,
            romanization,
            gloss,
            pos,
            source_languages=spec.traits.source_languages,
            strictness=spec.traits.source_language_strictness,
            word_classes=grammar.word_classes,
            word_class_deviation_rate=grammar.word_class_deviation_rate,
        )

    def normalized_form(romanization_str: str) -> str:
        return unicodedata.normalize("NFC", romanization_str).lower()

    known_forms = {normalized_form(entry.romanization) for entry in seed_entries}

    eligible_meanings = []
    for gloss, pos in lexicon_gen.select_meanings(spec.vocabulary_size):
        if gloss.lower() in seeded_glosses:
            continue
        gate_attr = lexicon_gen.CONDITIONAL_MEANINGS.get(gloss)
        if gate_attr is not None and not getattr(grammar, gate_attr):
            continue
        eligible_meanings.append((gloss, pos))

    def build_and_pick(meanings: list[tuple[str, PartOfSpeech]], use_llm: bool) -> list[LexicalEntry]:
        # Build every word's candidate pool (algorithmic), then make every
        # pick at once -- one batched LLM request when word_selection is
        # "llm" (instead of one call per word), or a plain seeded pick, with
        # no LLM call at all, otherwise.
        built = [build_core_pending(gloss, pos) for gloss, pos in meanings]
        pending_words = [item for item in built if isinstance(item, lexicon_gen.PendingWord)]
        if use_llm and spec.word_selection == "llm":
            chosen_candidates = lexicon_gen.choose_best_candidates_batch(
                pending_words, llm_client, name, spec.traits.salient_context
            )
        else:
            chosen_candidates = [
                lexicon_gen.resolve_candidate(
                    rng, pw.candidates, pw.gloss, pw.pos, llm_client, name, spec.traits.salient_context, "algorithmic"
                )
                for pw in pending_words
            ]
        chosen_iter = iter(chosen_candidates)
        return [item if isinstance(item, LexicalEntry) else item.finish(next(chosen_iter)) for item in built]

    generated_entries = build_and_pick(eligible_meanings, use_llm=True)

    # Retry a romanization collision with a word already placed in this
    # lexicon (same discipline as translation.expansion.coin_word), since
    # Lexicon.by_form returns only the first match and a homograph would
    # make the other word unreachable via it. Retries re-pick every still-
    # colliding word together and never call the LLM (an aesthetic pick
    # is pointless when the point is just to avoid a clash); after 20
    # rounds a still-colliding word is accepted as-is.
    unresolved: list[int] = []
    for index, entry in enumerate(generated_entries):
        if normalized_form(entry.romanization) in known_forms:
            unresolved.append(index)
        else:
            known_forms.add(normalized_form(entry.romanization))
    for _ in range(20):
        if not unresolved:
            break
        retried = build_and_pick([eligible_meanings[i] for i in unresolved], use_llm=False)
        still_colliding: list[int] = []
        for index, entry in zip(unresolved, retried):
            generated_entries[index] = entry
            if normalized_form(entry.romanization) in known_forms:
                still_colliding.append(index)
            else:
                known_forms.add(normalized_form(entry.romanization))
        unresolved = still_colliding
    for index in unresolved:
        known_forms.add(normalized_form(generated_entries[index].romanization))
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
