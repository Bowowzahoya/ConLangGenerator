"""Orchestrates one language's generation: phonology -> romanization ->
grammar -> core lexicon, all seeded from ``spec.seed`` for reproducibility."""

from __future__ import annotations

import random
import unicodedata

from conlang_generator.core.grammar import MorphologicalType
from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import LexicalEntry, Lexicon, PartOfSpeech
from conlang_generator.core.romanization import apply_grammatical_spelling
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import (
    grammar_gen,
    inflection_gen,
    classifier_gen,
    lexicon_gen,
    noun_class_gen,
    voice_np_gen,
    np_followups_gen,
    noun_phrase_gen,
    real_words,
    phonology_gen,
    pronoun_gen,
    romanization_gen,
    root_pattern,
    sound_change,
    subordination_gen,
    word_builder,
    word_class_gen,
)
from conlang_generator.llm.base import LLMClient


def generate_language(name: str, spec: GenerationSpec, llm_client: LLMClient) -> Language:
    rng = random.Random(spec.seed)

    # Which pregenerated meanings follow a real source-language word (word
    # strictness) is planned first, because exact copies (strictness 1.0)
    # must force their phonemes into the inventory.
    meanings = lexicon_gen.select_meanings(spec.vocabulary_size)
    real_choices = real_words.plan_real_words(spec, meanings, llm_client)
    phonology_spec = spec.model_copy(
        update={
            "seed_examples": spec.seed_examples
            + real_words.exact_seed_examples(real_choices, spec.traits.source_word_strictness)
        }
    )

    inventory, syllable_structure, tone_system, word_accent_system = phonology_gen.generate_phonology(
        rng, phonology_spec
    )
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

    # An independent rng stream: adding clause/number grammar must not shift
    # any draw the lexicon generation below makes from `rng`.
    clause_rng = random.Random(f"{spec.seed}:clause-grammar")
    grammar = grammar.model_copy(
        update={
            "number_affixes": inflection_gen.generate_number_affixes(clause_rng, inventory, syllable_structure),
            "mood_affixes": inflection_gen.generate_mood_affixes(clause_rng, inventory, syllable_structure),
            "question_particle": inflection_gen.generate_question_particle(clause_rng, inventory, syllable_structure),
        }
    )

    # Aspect and verbal mood: another independent stream, for the same reason.
    aspect_mood_rng = random.Random(f"{spec.seed}:aspect-mood")
    aspects = inflection_gen.roll_aspects(aspect_mood_rng)
    moods = inflection_gen.roll_moods(aspect_mood_rng)
    taken = frozenset(
        affix.suffix
        for affix in (*grammar.tense_affixes, *grammar.agreement_affixes, *grammar.mood_affixes)
    )
    aspect_affixes = inflection_gen.generate_aspect_affixes(
        aspect_mood_rng, inventory, syllable_structure, aspects, taken
    )
    verbal_mood_affixes = inflection_gen.generate_verbal_mood_affixes(
        aspect_mood_rng, inventory, syllable_structure, moods, taken | {a.suffix for a in aspect_affixes}
    )
    grammar = grammar.model_copy(
        update={
            "aspects": aspects,
            "aspect_affixes": aspect_affixes,
            "moods": moods,
            "mood_affixes": grammar.mood_affixes + verbal_mood_affixes,
        }
    )

    # Noun classes and the agreement they drive: a fourth independent stream.
    class_rng = random.Random(f"{spec.seed}:noun-class")
    noun_classes = noun_class_gen.roll_noun_classes(class_rng)
    object_agreement = noun_class_gen.roll_object_agreement(class_rng)
    taken = frozenset(
        affix.suffix
        for affix in (
            *grammar.tense_affixes, *grammar.agreement_affixes, *grammar.mood_affixes, *grammar.aspect_affixes,
        )
    )
    class_affixes, class_subject_affixes, object_affixes = noun_class_gen.generate_noun_class_grammar(
        class_rng, inventory, syllable_structure, noun_classes, object_agreement, taken
    )
    grammar = grammar.model_copy(
        update={
            "noun_classes": noun_classes,
            "class_affixes": class_affixes,
            "agreement_affixes": grammar.agreement_affixes + class_subject_affixes,
            "object_agreement": object_agreement,
            "object_agreement_affixes": object_affixes,
        }
    )

    # Noun-phrase grammar (dual, demonstratives, indefinite article,
    # possession): a fifth independent stream.
    np_rng = random.Random(f"{spec.seed}:noun-phrase")
    grammar = grammar.model_copy(
        update=noun_phrase_gen.generate_noun_phrase_grammar(np_rng, inventory, syllable_structure, grammar)
    )

    # Voice (passive/antipassive/causative): a sixth independent stream.
    voice_rng = random.Random(f"{spec.seed}:voice")
    voices = inflection_gen.roll_voices(voice_rng, grammar.alignment.value == "ergative_absolutive")
    voice_taken = frozenset(
        affix.suffix
        for affix in (
            *grammar.tense_affixes, *grammar.agreement_affixes, *grammar.mood_affixes, *grammar.aspect_affixes,
            *grammar.object_agreement_affixes,
        )
    )
    grammar = grammar.model_copy(
        update={
            "voices": voices,
            "voice_affixes": inflection_gen.generate_voice_affixes(
                voice_rng, inventory, syllable_structure, voices, voice_taken
            ),
        }
    )

    # Existential and possession-clause strategies: a seventh independent stream.
    existence_rng = random.Random(f"{spec.seed}:existence")
    grammar = grammar.model_copy(
        update={
            "existential": "verb" if existence_rng.random() < 0.45 else "copula",
            "possession_clause": "have" if existence_rng.random() < 0.55 else "dative_be",
        }
    )

    # Comparison and degree marking: an eighth independent stream.
    degree_rng = random.Random(f"{spec.seed}:degree")
    strategy_roll = degree_rng.random()
    oblique = next((c for c in ("locative", "dative", "genitive") if c in grammar.cases), "")
    if strategy_roll < 0.40 or (strategy_roll < 0.70 and not oblique):
        comparative_strategy = "particle"
    elif strategy_roll < 0.70:
        comparative_strategy = "case"
    else:
        comparative_strategy = "exceed"
    comparative_marking = "affix" if degree_rng.random() < 0.5 else "word"
    superlative_marking = "affix" if degree_rng.random() < 0.5 else "word"
    degree_labels = tuple(
        label
        for label, marking in (("comparative", comparative_marking), ("superlative", superlative_marking))
        if marking == "affix"
    )
    degree_taken = frozenset(
        affix.suffix for affix in (*grammar.class_affixes, *grammar.case_affixes, *grammar.number_affixes)
    )
    grammar = grammar.model_copy(
        update={
            "comparative_strategy": comparative_strategy,
            "comparative_case": oblique if comparative_strategy == "case" else "",
            "comparative_marking": comparative_marking,
            "superlative_marking": superlative_marking,
            "degree_affixes": inflection_gen.distinct_suffixes(
                degree_rng, inventory, syllable_structure, degree_labels, degree_taken
            ),
        }
    )

    # Classifiers and the pronoun system: a ninth and tenth independent stream.
    classifier_rng = random.Random(f"{spec.seed}:classifier")
    classifier_system = classifier_gen.roll_classifier_system(classifier_rng, grammar.morphological_type)
    uses_classifiers = bool(classifier_system["uses_classifiers"])
    pronoun_rng = random.Random(f"{spec.seed}:pronoun")
    pronoun_system = pronoun_gen.roll_pronoun_system(pronoun_rng, spec.traits.social_hierarchy)
    person_suffixes = [a.suffix for a in grammar.agreement_affixes if a.label in pronoun_gen.PERSON_LABELS]
    if len(set(person_suffixes)) < len(pronoun_gen.PERSON_LABELS):
        pronoun_system["pro_drop"] = False  # dropping a pronoun needs distinct person marking on the verb
    grammar = grammar.model_copy(
        update={
            **classifier_system,
            "plural_after_numeral": False if uses_classifiers else grammar.plural_after_numeral,
            **pronoun_system,
        }
    )

    # Reflexives, reciprocals, possessive pronouns, verb number/politeness and
    # object pro-drop: a further independent stream.
    extras_rng = random.Random(f"{spec.seed}:pronoun-extras")
    extras = pronoun_gen.roll_pronoun_extras(extras_rng)
    extras_taken = frozenset(
        affix.suffix
        for affix in (
            *grammar.tense_affixes, *grammar.agreement_affixes, *grammar.mood_affixes, *grammar.aspect_affixes,
            *grammar.voice_affixes, *grammar.object_agreement_affixes, *grammar.case_affixes,
            *grammar.number_affixes, *grammar.class_affixes, *grammar.possession_affixes, *grammar.degree_affixes,
        )
    )
    voice_labels = tuple(
        label
        for label, marking in (("reflexive", extras["reflexive_marking"]), ("reciprocal", extras["reciprocal_marking"]))
        if marking == "affix"
    )
    voice_extra_affixes = inflection_gen.distinct_suffixes(
        extras_rng, inventory, syllable_structure, voice_labels, extras_taken
    )
    extras_taken = extras_taken | {a.suffix for a in voice_extra_affixes}
    person_affix_labels = (
        pronoun_gen.PERSON_LABELS if extras["possessive_pronouns"] == "affix" else ()
    ) + (("self",) if extras["reflexive_possessive"] == "affix" else ())
    person_affixes = inflection_gen.distinct_suffixes(
        extras_rng, inventory, syllable_structure, person_affix_labels, extras_taken
    )
    extras_taken = extras_taken | {a.suffix for a in person_affixes}
    verb_number_affixes = (
        inflection_gen.distinct_suffixes(extras_rng, inventory, syllable_structure, ("plural",), extras_taken)
        if extras["verb_number_agreement"]
        else ()
    )
    extras_taken = extras_taken | {a.suffix for a in verb_number_affixes}
    verb_politeness = bool(grammar.honorific_you and extras["verb_politeness_wish"])
    verb_polite_affixes = (
        inflection_gen.distinct_suffixes(extras_rng, inventory, syllable_structure, ("polite",), extras_taken)
        if verb_politeness
        else ()
    )
    object_person_suffixes = [
        a.suffix for a in grammar.object_agreement_affixes if a.label in pronoun_gen.PERSON_LABELS
    ]
    object_pro_drop = bool(
        grammar.object_agreement
        and extras["object_pro_drop_wish"]
        and len(set(object_person_suffixes)) == len(pronoun_gen.PERSON_LABELS)
    )
    grammar = grammar.model_copy(
        update={
            "reflexive_marking": extras["reflexive_marking"],
            "reciprocal_marking": extras["reciprocal_marking"],
            "voices": grammar.voices + voice_labels,
            "voice_affixes": grammar.voice_affixes + voice_extra_affixes,
            "possessive_pronouns": extras["possessive_pronouns"],
            "possessor_person_affixes": person_affixes,
            "suppletive_pronoun_persons": extras["suppletive_pronoun_persons"],
            "reflexive_possessive": extras["reflexive_possessive"],
            "verb_number_agreement": extras["verb_number_agreement"],
            "verb_number_affixes": verb_number_affixes,
            "verb_politeness": verb_politeness,
            "verb_polite_affixes": verb_polite_affixes,
            "object_pro_drop": object_pro_drop,
        }
    )

    # Subordination: another independent stream.
    subordination_rng = random.Random(f"{spec.seed}:subordination")
    subordination = subordination_gen.roll_subordination(
        subordination_rng, grammar.word_order.value, grammar.postpositional
    )
    subordination_taken = frozenset(
        affix.suffix
        for affix in (
            *grammar.tense_affixes, *grammar.agreement_affixes, *grammar.mood_affixes, *grammar.aspect_affixes,
            *grammar.voice_affixes, *grammar.object_agreement_affixes, *grammar.verb_number_affixes,
            *grammar.verb_polite_affixes,
        )
    )
    followups = subordination_gen.roll_subordination_followups(subordination_rng)
    converb = bool(followups.pop("converb"))
    verb_forms = tuple(subordination["verb_forms"]) + (("converb",) if converb else ())
    grammar = grammar.model_copy(
        update={
            **subordination,
            **followups,
            "verb_forms": verb_forms,
            "verb_form_affixes": inflection_gen.distinct_suffixes(
                subordination_rng, inventory, syllable_structure, verb_forms, subordination_taken,
            ),
            # a converb-coordinating language needs the medial form
            "clause_coordination": (
                "word" if followups["clause_coordination"] == "converb" and not converb
                else followups["clause_coordination"]
            ),
        }
    )

    # Agreement follow-ups: another independent stream.
    agreement_rng = random.Random(f"{spec.seed}:agreement")
    agreement_extras = noun_class_gen.roll_agreement_extras(agreement_rng)
    class_marking = agreement_extras["class_marking"] if grammar.noun_classes else "none"
    marker_taken = frozenset(
        affix.suffix
        for affix in (*grammar.class_affixes, *grammar.case_affixes, *grammar.number_affixes)
    )
    if class_marking == "suffix":
        class_marker_affixes = inflection_gen.distinct_suffixes(
            agreement_rng, inventory, syllable_structure, tuple(grammar.noun_classes), marker_taken
        )
    elif class_marking == "prefix":
        class_marker_affixes = noun_class_gen.generate_class_prefixes(
            agreement_rng, inventory, syllable_structure, tuple(grammar.noun_classes)
        )
    else:
        class_marker_affixes = ()
    grammar = grammar.model_copy(
        update={
            "noun_class_assignment": agreement_extras["noun_class_assignment"] if grammar.noun_classes else "hash",
            "class_marking": class_marking,
            "class_marker_affixes": class_marker_affixes,
            "class_agreement_targets": agreement_extras["class_agreement_targets"],
            "number_agreement_targets": agreement_extras["number_agreement_targets"],
            "case_agreement_targets": agreement_extras["case_agreement_targets"],
        }
    )

    # Aspect/mood follow-ups: evidentials, negation strategy, prohibitive,
    # periphrastic labels -- another independent stream.
    followup_rng = random.Random(f"{spec.seed}:aspect-followups")
    followups = inflection_gen.roll_aspect_followups(followup_rng, grammar)
    taken = frozenset(
        affix.suffix
        for name in inflection_gen._VERB_SUFFIX_FIELDS
        for affix in getattr(grammar, name)
    )
    evidential_affixes = inflection_gen.distinct_suffixes(
        followup_rng, inventory, syllable_structure, tuple(followups["evidentials"]), taken
    )
    negative_affixes = (
        inflection_gen.distinct_suffixes(
            followup_rng, inventory, syllable_structure, ("negative",),
            taken | {a.suffix for a in evidential_affixes},
        )
        if followups["negation_strategy"] != "particle"
        else ()
    )
    prohibitive_affixes = (
        inflection_gen.distinct_suffixes(
            followup_rng, inventory, syllable_structure, ("prohibitive",),
            taken | {a.suffix for a in (*evidential_affixes, *negative_affixes)},
        )
        if followups["prohibitive"]
        else ()
    )
    grammar = grammar.model_copy(
        update={
            "evidentials": followups["evidentials"],
            "evidential_affixes": evidential_affixes,
            "negation_strategy": followups["negation_strategy"],
            "verb_negative_affixes": negative_affixes,
            "mood_affixes": grammar.mood_affixes + prohibitive_affixes,
            "periphrastic_labels": followups["periphrastic_labels"],
            "auxiliary_position": followups["auxiliary_position"],
        }
    )
    # Voice and noun-phrase follow-ups: one more independent stream.
    vnp_rng = random.Random(f"{spec.seed}:voice-np-followups")
    vnp = voice_np_gen.roll_followups(vnp_rng, grammar)
    vnp_taken = frozenset(
        affix.suffix
        for name in (*inflection_gen._VERB_SUFFIX_FIELDS, *inflection_gen._NOUN_SUFFIX_FIELDS)
        for affix in getattr(grammar, name)
    )
    vnp_voice_affixes = inflection_gen.distinct_suffixes(
        vnp_rng, inventory, syllable_structure, tuple(vnp["voices"]), vnp_taken
    )
    vnp_number_affixes = inflection_gen.distinct_suffixes(
        vnp_rng, inventory, syllable_structure, tuple(vnp["numbers"]), vnp_taken | {a.suffix for a in vnp_voice_affixes}
    )
    vnp_case_affixes = inflection_gen.distinct_suffixes(
        vnp_rng, inventory, syllable_structure, tuple(vnp["cases"]),
        vnp_taken | {a.suffix for a in (*vnp_voice_affixes, *vnp_number_affixes)},
    )
    grammar = grammar.model_copy(
        update={
            "voices": grammar.voices + tuple(vnp["voices"]),
            "voice_affixes": grammar.voice_affixes + vnp_voice_affixes,
            "number_affixes": grammar.number_affixes + vnp_number_affixes,
            "cases": grammar.cases + tuple(vnp["cases"]),
            "case_affixes": grammar.case_affixes + vnp_case_affixes,
            "passive_agreement": vnp["passive_agreement"],
            "passive_agent": vnp["passive_agent"],
            "adposition_case_strategy": vnp["adposition_case_strategy"],
            "suppletive_plurals": vnp["suppletive_plurals"],
            "suppletive_degrees": vnp["suppletive_degrees"],
            "inalienable_possession": vnp["inalienable_possession"],
        }
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
    real_entries = real_words.build_real_entries(
        real_choices, spec.traits.source_word_strictness, spec.seed, inventory, syllable_structure, romanization,
        tone_system,
    )
    seed_entries = seed_entries + real_entries
    seeded_glosses = {example.gloss.lower() for example in spec.seed_examples} | {
        entry.primary_gloss.lower() for entry in real_entries
    }

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
    for gloss, pos in meanings:
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

    # The question particle is a free word: re-roll it (own rng stream) if it
    # spells the same as a lexicon word, so it can be told apart on decoding.
    particle = grammar.question_particle
    for _ in range(50):
        if normalized_form(romanization.apply(particle)) not in known_forms:
            break
        particle = inflection_gen.generate_question_particle(clause_rng, inventory, syllable_structure)
    grammar = grammar.model_copy(update={"question_particle": particle})
    # Likewise the possessive particle (also distinct from the question particle).
    possessive = grammar.possessive_particle
    if possessive:
        taken_forms = known_forms | {normalized_form(romanization.apply(particle))}
        for _ in range(50):
            if normalized_form(romanization.apply(possessive)) not in taken_forms:
                break
            possessive = inflection_gen.generate_question_particle(np_rng, inventory, syllable_structure)
        grammar = grammar.model_copy(update={"possessive_particle": possessive})

    # Noun-phrase follow-ups, round two (own stream).
    np2 = np_followups_gen.roll_followups(random.Random(f"{spec.seed}:np-followups-2"), grammar)
    article_source = np2["article_source"]
    entries_now = list(seed_entries + generated_entries)
    if article_source == "demonstrative":
        the = next((i for i, e in enumerate(entries_now) if e.primary_gloss == "the"), None)
        that = next((e for e in entries_now if e.primary_gloss == "that"), None)
        derived = (
            np_followups_gen.derive_article_ipa(that.ipa, inventory)
            if that is not None and the is not None
            else None
        )
        if derived is not None:
            spelled = apply_grammatical_spelling(romanization, romanization.apply(derived), PartOfSpeech.PARTICLE)
            others = {normalized_form(e.romanization) for i, e in enumerate(entries_now) if i != the}
            if normalized_form(spelled) not in others:
                entries_now[the] = entries_now[the].model_copy(
                    update={"ipa": derived, "romanization": spelled, "tones": tuple(that.tones[:1])}
                )
            else:
                derived = None
        if derived is None:
            article_source = "own"
    grammar = grammar.model_copy(
        update={
            "suppletive_pronoun_case_limits": np2["suppletive_pronoun_case_limits"],
            "adjective_placement": np2["adjective_placement"],
            "adjective_before_classes": np2["adjective_before_classes"],
            "adjective_stack_order": np2["adjective_stack_order"],
            "adjective_stack_linker": np2["adjective_stack_linker"],
            "article_source": article_source,
            "has_specific_article": np2["has_specific_article"],
        }
    )

    # Noun-phrase follow-ups, round three (own stream).
    np3_rng = random.Random(f"{spec.seed}:np-followups-3")
    np3 = np_followups_gen.roll_round_three(np3_rng, grammar)
    np3_taken = frozenset(
        affix.suffix
        for name in (*inflection_gen._VERB_SUFFIX_FIELDS, *inflection_gen._NOUN_SUFFIX_FIELDS)
        for affix in getattr(grammar, name)
    )
    np3_case_affixes = inflection_gen.distinct_suffixes(
        np3_rng, inventory, syllable_structure, tuple(np3["cases"]), np3_taken
    )
    entries_now = list(entries_now)
    grammar = grammar.model_copy(
        update={
            "cases": grammar.cases + tuple(np3["cases"]),
            "case_affixes": grammar.case_affixes + np3_case_affixes,
            "classifier_with_adjective": np3["classifier_with_adjective"],
            "drop_measure_of": np3["drop_measure_of"],
            "possessive_word_persons": np3["possessive_word_persons"],
            "suppletive_past": np3["suppletive_past"],
            "deictic_articles": np3["deictic_articles"],
            "demonstrative_doubling": np3["demonstrative_doubling"],
        }
    )

    # Last, once every inflectional affix exists: no two labels of a paradigm may spell alike.
    grammar = inflection_gen.resolve_collisions(
        random.Random(f"{spec.seed}:distinct-suffixes"), inventory, syllable_structure, grammar
    )

    return Language(
        name=name,
        spec=spec,
        phonology=inventory,
        syllable_structure=syllable_structure,
        tone_system=tone_system,
        word_accent=word_accent_system,
        romanization=romanization,
        grammar=grammar,
        lexicon=Lexicon(entries=tuple(entries_now)),
        history=("generated core language",),
    )


def resolve_evolve_years(spec: GenerationSpec) -> int:
    """Explicit ``spec.evolve_years`` wins (``0`` meaning none); otherwise the
    time depth the prompt classifier inferred; otherwise ``0``."""
    years = spec.evolve_years if spec.evolve_years is not None else spec.traits.time_depth_years
    return max(0, years or 0)


def generate_evolved_language(name: str, spec: GenerationSpec, llm_client: LLMClient) -> Language:
    """``generate_language`` followed by ``resolve_evolve_years`` years of
    sound change (``sound_change.evolve_language``) when that is positive --
    e.g. "Dutch evolved forward 200 years": real Dutch words (word
    strictness), then two centuries of change. The result keeps the caller's
    own settings (word selection, vocabulary size, foreign names, ...) and
    records both steps in its history."""
    base = generate_language(name, spec, llm_client)
    years = resolve_evolve_years(spec)
    if years <= 0:
        return base
    evolved = sound_change.evolve_language(
        name, base, years, spec.traits, spec.seed, forced_orthography=spec.forced_orthography
    )
    kept_spec = evolved.spec.model_copy(
        update={
            "prompt": spec.prompt,
            "fantasy": spec.fantasy,
            "word_selection": spec.word_selection,
            "vocabulary_size": spec.vocabulary_size,
            "foreign_names": spec.foreign_names,
            "evolve_years": years,
            "force_isolated": spec.force_isolated,
            "force_high_altitude": spec.force_high_altitude,
            "force_tonal": spec.force_tonal,
            "forced_orthography": spec.forced_orthography,
            "allow_all_caps": spec.allow_all_caps,
        }
    )
    # Evolution overwrites each entry's note with its orthography path; keep
    # the real-word provenance (unless the word was replaced by a new one).
    carried = tuple(
        new.model_copy(update={"notes": f"{old.notes}; {new.notes}"})
        if old.notes.startswith("real") and "replaced" not in new.notes
        else new
        for old, new in zip(base.lexicon.entries, evolved.lexicon.entries)
    )
    lexicon = evolved.lexicon.model_copy(update={"entries": carried})
    return evolved.model_copy(update={"spec": kept_spec, "lexicon": lexicon})
