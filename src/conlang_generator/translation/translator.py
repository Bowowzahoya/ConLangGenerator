"""English <-> conlang translation.

An LLM-drafted ``translation.sentence_planner.SentencePlan`` decides this
sentence's own *structure* -- word order, which arguments get case-marked,
whether an article/copula/negation/conjunction appears, what tense/
agreement a finite verb takes -- see that module's own docstring for the
LLM/deterministic-rendering boundary. This module never asks an LLM to
invent a word's actual spelling or phonology; ``translate_to_conlang``
only ever renders a plan's slots via the *existing* deterministic
primitives below (``_lookup_or_coin``, ``_apply_case``,
``_apply_verb_inflection``).

Text is translated one sentence at a time (each sentence gets its own plan
and mood: declarative, imperative, yes/no question, wh-question). Remaining
v0 limitations, by design: a sentence's plan is a tree -- a "clause" slot
holds a nested plan (complement/relative/adverbial, depth-capped) rendered
in place with its linking word; a finite verb takes aspect and verbal mood
as well as tense and agreement; there is still no special subordinate verb
form; negation is a single particle
slot with no per-language negation-position typology curated; punctuation
is not rendered.

Real inflection (case, tense, subject agreement, articles, an overt copula)
is applied on the way to the conlang when the target language's own
``GrammarProfile`` says it has the feature -- see ``_apply_case``/
``_apply_verb_inflection`` below. Applying an affix re-derives the
affected word's stress via ``generation.inflection_gen.apply_affix`` (the
same shared mechanism ``word_class_gen.apply_word_class`` uses for
citation-class marking -- see ``core.grammar.InflectionAffix``'s own
docstring for why the two are different types), seeded from a stable hash of
``(language.spec.seed, a per-call salt)`` so repeated calls on the same
input stay reproducible without a public rng parameter (the same "hash the
payload into a local seed" precedent ``core.romanization._stable_local_
choice`` already uses).

Decoding that same inflection back out on the way to English
(``translate_to_english``) is generate-and-compare, not a parse -- see
``_decode_noun``/``_decode_verb``'s own docstrings for why (spelling isn't a
clean invertible function in general, the same reason ``sound_change.py``'s
own reform-detection compares via ``apply()`` rather than string surgery).
Decoding no longer assumes any fixed sentence shape or position: every
conlang token is tried independently against an exact match, then
``_decode_noun``, then ``_decode_verb`` -- since the plan-driven encoder can
now produce genuinely arbitrary structure, there is no longer a small fixed
set of shapes to special-case on the way back.

Unknown *English* content words trigger word coinage (see ``expansion.py``);
an unknown *conlang* word that can't be decoded via ``_decode_noun``/
``_decode_verb`` either (there is no English gloss to reverse-coin from)
surfaces as ``<unknown:...>`` in the rough gloss line.
"""

from __future__ import annotations

import hashlib
import random
import unicodedata
from dataclasses import dataclass

from conlang_generator.core.grammar import GrammarProfile, InflectionAffix
from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from conlang_generator.core.romanization import apply_grammatical_spelling
from conlang_generator.generation import inflection_gen, noun_class_gen, stress_gen, tone_sandhi, word_accent_gen
from conlang_generator.generation.reference_languages import match_profiles
from conlang_generator.llm.base import LLMClient, LLMRequest
from conlang_generator.llm.pricing import DEFAULT_MODEL
from conlang_generator.translation import expansion, names, sentence_planner

_IRREGULAR_LEMMA_BY_PAST = {
    "went": "go", "saw": "see", "came": "come", "ate": "eat", "drank": "drink",
    "said": "say", "knew": "know", "slept": "sleep", "gave": "give",
}
"""Enough to cover this project's own core-vocabulary verb list -- no real
lemmatizer, matching this module's own "no real parser" standard. A verb
outside this small closed set falls through to the regular ``-ed``/``-ied``
strip below."""
_PAST_FORM_BY_LEMMA = {lemma: past for past, lemma in _IRREGULAR_LEMMA_BY_PAST.items()}
"""The reverse of ``_IRREGULAR_LEMMA_BY_PAST`` -- used by ``translate_to_
english`` (via ``_english_verb_gloss``) to reconstruct a past-tense English
gloss once a conlang verb has been decoded back to its lemma and a
``"past"`` tense reading."""
_PARTICIPLE_BY_LEMMA = {
    "see": "seen", "go": "gone", "eat": "eaten", "give": "given", "know": "known", "come": "come", "drink": "drunk",
}
"""Irregular past participles for the perfect (a regular ``-ed`` otherwise)."""


@dataclass(frozen=True)
class TranslationResult:
    text: str
    ipa: str
    language: Language
    """Possibly updated -- new words may have been coined during translation."""
    coined: tuple[LexicalEntry, ...] = ()
    pattern: str = "llm-plan"


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


def _translation_rng(language: Language, salt: str) -> random.Random:
    """A stable, reproducible rng for one specific affix-application call --
    hashes ``(language.spec.seed, salt)`` into a local seed, the same
    "hash the payload into a local seed" precedent
    ``core.romanization._stable_local_choice`` already uses, so repeated
    calls on the same input/language/salt always agree without needing a
    public rng parameter on this module's own translation functions."""
    payload = f"{language.spec.seed}:{salt}".encode("utf-8")
    return random.Random(int(hashlib.sha256(payload).hexdigest(), 16))


def _stress_and_word_accent_kwargs(language: Language) -> dict:
    """Sources the same ``stress_pattern``/``stress_deviation_rate``/
    ``word_accent_*``/``strictness`` values ``sound_change._coin_native_word``
    already re-derives for a word coined after initial generation --
    these aren't persisted on ``Language`` itself (only pure functions of
    ``source_languages``), so they're recomputed fresh here rather than
    read off ``language.romanization``, which only keeps what ``apply()``
    itself needs for rendering, not for re-coining."""
    reference_profiles = match_profiles(language.spec.traits.source_languages)
    strictness = language.spec.traits.source_language_strictness if reference_profiles else 0.0
    stress_pattern, stress_deviation_rate = stress_gen.resolve_stress_pattern(reference_profiles)
    word_accent_pattern = ""
    word_accent_deviation_rate: float | None = None
    word_accent_length_rate: float | None = None
    word_accent_window: int | None = None
    if language.word_accent.enabled:
        (
            _, word_accent_pattern, word_accent_deviation_rate, word_accent_length_rate, word_accent_window,
        ) = word_accent_gen.resolve_word_accent(reference_profiles)
    return {
        "stress_pattern": stress_pattern,
        "stress_deviation_rate": stress_deviation_rate,
        "stress_strictness": strictness,
        "word_accent_realization": language.word_accent.realization if language.word_accent.enabled else "",
        "word_accent_pattern": word_accent_pattern,
        "word_accent_deviation_rate": word_accent_deviation_rate,
        "word_accent_length_rate": word_accent_length_rate,
        "word_accent_window": word_accent_window,
    }


def _combined_tense_agreement_affix(
    grammar: GrammarProfile,
    tense_label: str | None,
    agreement_label: str,
    aspect_label: str | None = None,
    mood_label: str | None = None,
    object_label: str | None = None,
    voice_label: str | None = None,
) -> InflectionAffix | None:
    """Composes this sentence's own aspect, tense, verbal mood and agreement
    affixes (in that order) into one synthetic ``InflectionAffix`` so
    ``inflection_gen.apply_affix`` only needs to re-derive stress once --
    see that function's own docstring for why separate calls would be
    wasteful (and arguably incorrect). With no aspect or mood this is exactly
    the earlier tense-then-agreement composition. ``None`` when nothing
    contributes anything."""
    tense_affix = next((a for a in grammar.tense_affixes if a.label == tense_label), None) if tense_label else None
    aspect_affix = next((a for a in grammar.aspect_affixes if a.label == aspect_label), None) if aspect_label else None
    mood_affix = next((a for a in grammar.mood_affixes if a.label == mood_label), None) if mood_label else None
    agreement_affix = next((a for a in grammar.agreement_affixes if a.label == agreement_label), None)
    object_affix = (
        next((a for a in grammar.object_agreement_affixes if a.label == object_label), None) if object_label else None
    )
    voice_affix = next((a for a in grammar.voice_affixes if a.label == voice_label), None) if voice_label else None
    parts = [voice_affix, aspect_affix, tense_affix, mood_affix, agreement_affix, object_affix]
    prefix = tuple(sym for part in parts if part for sym in part.prefix)
    suffix = tuple(sym for part in parts if part for sym in part.suffix)
    if not prefix and not suffix:
        return None
    return InflectionAffix(label="verb-inflection", prefix=prefix, suffix=suffix)


def _case_affix_salt(entry: LexicalEntry, case_label: str) -> str:
    """The rng salt for marking ``entry`` with ``case_label`` -- shared
    verbatim between encoding (``_apply_case``) and decoding (``_decode_
    noun``) so both sides derive the *identical* rng stream and therefore
    the identical stress/re-rendering outcome for the same (entry, case)
    pair. Deliberately keyed only on ``entry.ipa``/``case_label`` -- never
    on the original English token or sentence, which decoding has no way
    to reconstruct from an observed conlang word alone."""
    return f"case:{entry.ipa}:{case_label}"


def _verb_affix_salt(
    entry: LexicalEntry,
    tense_label: str | None,
    agreement_label: str,
    aspect_label: str | None = None,
    mood_label: str | None = None,
    object_label: str | None = None,
    voice_label: str | None = None,
) -> str:
    """The rng salt for marking ``entry`` with a given tense+agreement
    (+ aspect, verbal mood) combination -- same "identical salt on both
    sides" contract as ``_case_affix_salt``, keyed on the *resolved* labels
    (not the raw English verb/subject tokens, which decoding never has).
    Without aspect/mood it is exactly the earlier salt."""
    salt = f"verb:{entry.ipa}:{tense_label}:{agreement_label}"
    if aspect_label:
        salt += f":a={aspect_label}"
    if mood_label:
        salt += f":m={mood_label}"
    if object_label:
        salt += f":o={object_label}"
    if voice_label:
        salt += f":v={voice_label}"
    return salt


def _noun_affix(
    grammar: GrammarProfile, case_label: str | None, number_label: str | None, possessed: bool = False
) -> tuple[InflectionAffix | None, str | None]:
    """This noun's own affix (number, then possessed, then case, composed into
    one synthetic affix so stress is re-derived once -- see ``_combined_tense_
    agreement_affix``) and the case label actually used (``None`` when the
    language lacks that case). ``(None, None)`` when nothing marks the noun."""
    resolved_case = case_label if case_label in grammar.cases else None
    case_affix = next((a for a in grammar.case_affixes if a.label == resolved_case), None) if resolved_case else None
    if case_affix is None:
        resolved_case = None
    number_affix = (
        next((a for a in grammar.number_affixes if a.label == number_label), None) if number_label else None
    )
    possessed_affix = next((a for a in grammar.possession_affixes if a.label == "possessed"), None) if possessed else None
    if number_affix is None and possessed_affix is None:
        return case_affix, resolved_case
    parts = [number_affix, possessed_affix, case_affix]
    prefix = tuple(sym for part in parts if part for sym in part.prefix)
    suffix = tuple(sym for part in parts if part for sym in part.suffix)
    return InflectionAffix(label="number+case", prefix=prefix, suffix=suffix), resolved_case


def _noun_affix_salt(
    entry: LexicalEntry, case_label: str | None, number_label: str | None, possessed: bool = False
) -> str:
    """``_case_affix_salt`` for a case-only marking (so every pre-number
    sentence keeps its exact rng stream); a distinct salt once number or
    possession is involved. Shared by encoding and decoding like the other
    salts."""
    if number_label is None and not possessed:
        return _case_affix_salt(entry, case_label or "")
    return f"noun:{entry.ipa}:{case_label}:{number_label}" + (":possessed" if possessed else "")


def _apply_case(
    language: Language,
    entry: LexicalEntry,
    case_label: str | None,
    number_label: str | None = None,
    possessed: bool = False,
) -> tuple[str, str]:
    """Returns this entry's own ``(romanization, ipa)``, marked for number
    (``"plural"``/``"dual"``), possession (``possessed``) and/or case when the
    labels name a real feature of this language's own ``GrammarProfile`` --
    unmarked (this entry's own bare citation form) otherwise, e.g. an
    isolating language with no case, or the argument alignment leaves it bare
    (only one argument is ever case-marked per sentence -- see ``translate_to_
    conlang``'s own SVO handling)."""
    grammar = language.grammar
    resolved_possessed = possessed and any(a.label == "possessed" for a in grammar.possession_affixes)
    affix, resolved_case = _noun_affix(grammar, case_label, number_label, resolved_possessed)
    if affix is None:
        return entry.romanization, entry.ipa
    resolved_number = number_label if any(a.label == number_label for a in grammar.number_affixes) else None
    rng = _translation_rng(language, _noun_affix_salt(entry, resolved_case, resolved_number, resolved_possessed))
    ipa = inflection_gen.apply_affix(rng, affix, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language))
    romanization = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), entry.pos)
    return romanization, ipa


def _imperative_salt(entry: LexicalEntry) -> str:
    return f"mood:{entry.ipa}:imperative"


def _apply_verb_inflection(
    language: Language,
    entry: LexicalEntry,
    tense_label: str | None,
    agreement_label: str,
    mood: str = "declarative",
    aspect_label: str | None = None,
    verb_mood_label: str | None = None,
    object_label: str | None = None,
    voice_label: str | None = None,
) -> tuple[str, str]:
    """The verb/copula-side counterpart of ``_apply_case`` -- composes and
    applies this sentence's own tense+agreement affix (see
    ``_combined_tense_agreement_affix``), or returns the bare citation
    form unchanged when this language has neither tense nor a real
    agreement suffix worth attaching (never actually empty today, since
    ``agreement_affixes`` always has a ``"default"`` entry, but the
    ``None`` case is still handled honestly). ``tense_label``/
    ``agreement_label`` come directly from the sentence plan's own
    ``PlannedSlot.tense``/``.agreement`` -- normalized here (an
    unavailable/invalid value falls back to ``None``/``"default"``) rather
    than by the caller, so the exact same normalized values always feed
    both the affix lookup and its own rng salt (see
    ``_case_affix_salt``/``_verb_affix_salt``'s own docstrings for why an
    encode/decode salt mismatch is a real, previously-hit bug -- an
    unnormalized invalid label here would reintroduce it, since
    ``_decode_verb`` only ever tries genuinely valid labels)."""
    grammar = language.grammar
    if mood == "imperative":
        # An imperative takes its own marker instead of tense/agreement.
        imperative = next((a for a in grammar.mood_affixes if a.label == "imperative"), None)
        if imperative is None:
            return entry.romanization, entry.ipa
        rng = _translation_rng(language, _imperative_salt(entry))
        ipa = inflection_gen.apply_affix(
            rng, imperative, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language)
        )
        romanization = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), entry.pos)
        return romanization, ipa
    resolved_tense = tense_label if tense_label in grammar.tenses else None
    resolved_agreement = (
        agreement_label if agreement_label in _agreement_labels(grammar) else "default"
    )
    resolved_aspect = aspect_label if aspect_label in grammar.aspects else None
    resolved_verb_mood = verb_mood_label if verb_mood_label in grammar.moods else None
    resolved_object = (
        object_label if any(a.label == object_label for a in grammar.object_agreement_affixes) else None
    )
    resolved_voice = voice_label if voice_label in grammar.voices else None
    affix = _combined_tense_agreement_affix(
        grammar, resolved_tense, resolved_agreement, resolved_aspect, resolved_verb_mood, resolved_object,
        resolved_voice,
    )
    if affix is None:
        return entry.romanization, entry.ipa
    rng = _translation_rng(
        language,
        _verb_affix_salt(
            entry, resolved_tense, resolved_agreement, resolved_aspect, resolved_verb_mood, resolved_object,
            resolved_voice,
        ),
    )
    ipa = inflection_gen.apply_affix(rng, affix, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language))
    romanization = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), entry.pos)
    return romanization, ipa


def _gloss_variants(gloss: str) -> list[str]:
    """The gloss itself, then its likely singular/base spellings -- so a
    word coined earlier (e.g. "boat") is found again when a later request
    phrases it slightly differently ("Boats", "boats"), instead of being
    coined a second time under a different spelling."""
    base = gloss.strip().lower()
    variants = [base]
    if base.endswith("ies") and len(base) > 4:
        variants.append(base[:-3] + "y")
    if base.endswith("es") and len(base) > 3:
        variants.append(base[:-2])
    if base.endswith("s") and len(base) > 2:
        variants.append(base[:-1])
    return variants


def _find_word(language: Language, gloss: str) -> LexicalEntry | None:
    """An ordinary word by gloss -- proper-name entries (see ``names``) are
    skipped, so the name "Rose" never stands in for the word "rose"."""
    wanted = gloss.lower()
    for entry in language.lexicon.entries:
        if not names.is_name_entry(entry) and wanted in (g.lower() for g in entry.glosses):
            return entry
    return None


def _lookup_or_coin(
    language: Language,
    token: str,
    pos: PartOfSpeech,
    coined: list[LexicalEntry],
    llm_client: LLMClient,
    lemma_candidates: list[str],
) -> tuple[Language, LexicalEntry]:
    for candidate in [variant for lemma in lemma_candidates for variant in _gloss_variants(lemma)]:
        entry = _find_word(language, candidate)
        if entry is not None:
            return language, entry

    new_entry = expansion.coin_word(language, token, pos, llm_client)
    coined.append(new_entry)
    updated = language.with_new_words(
        (new_entry,),
        reason=f"coined '{new_entry.romanization}' for '{token}' during translation",
    )
    return updated, new_entry


_BARE_GLOSS_BY_SLOT_KIND = {"article": "the", "negation": "not", "conjunction": "and"}
"""The fixed core-vocabulary gloss each function-word ``PlannedSlot.kind``
always renders as its own bare citation form -- ``"copula"`` is deliberately
excluded, since unlike these three it still takes tense/agreement marking
like a finite verb."""


def _question_particle_first(language: Language) -> bool:
    """Illustrative placement: a yes/no question particle goes at the end
    of the sentence, except in verb-initial languages, where it goes at the
    start."""
    return language.grammar.word_order.value in ("VSO", "VOS")


def _agreement_labels(grammar: GrammarProfile) -> tuple[str, ...]:
    """Every subject-agreement label this language's verbs can take: the
    person labels, then any ``"class:<name>"`` ones."""
    extra = tuple(a.label for a in grammar.agreement_affixes if a.label not in inflection_gen.AGREEMENT_LABELS)
    return inflection_gen.AGREEMENT_LABELS + extra


_OBJECT_PERSON_BY_GLOSS = {"i": "I", "me": "I", "you": "you", "he": "he", "she": "he", "him": "he", "her": "he", "we": "we", "us": "we"}


def _class_label_of(language: Language, gloss: str | None) -> str | None:
    """The ``"class:<name>"`` agreement label of the noun with lemma
    ``gloss`` (``None`` in a language with no noun classes)."""
    if not gloss:
        return None
    noun_cls = noun_class_gen.noun_class(language.grammar.noun_classes, language.spec.seed, gloss)
    return noun_class_gen.class_agreement_label(noun_cls) if noun_cls else None


def _verb_agreement(language: Language, slot: sentence_planner.PlannedSlot) -> tuple[str, str | None]:
    """``(subject agreement label, object agreement label)`` for a finite
    verb/copula slot: a noun subject's class replaces the ``"default"``
    (3rd person) label; an object is agreed with only in a language with
    object agreement (a pronoun by person, a noun by class)."""
    agreement = slot.agreement or "default"
    if agreement == "default" and slot.subject_gloss:
        subject_class = _class_label_of(language, slot.subject_gloss)
        if subject_class in _agreement_labels(language.grammar):
            agreement = subject_class
    object_label: str | None = None
    if language.grammar.object_agreement and slot.object_gloss:
        object_label = _OBJECT_PERSON_BY_GLOSS.get(slot.object_gloss) or _class_label_of(language, slot.object_gloss)
    return agreement, object_label


def _class_agreement_salt(entry: LexicalEntry, noun_cls: str | None, degree: str | None = None) -> str:
    """Rng salt for an agreeing word: the earlier class-only salt when there is
    no degree (so existing output is unchanged), distinct salts otherwise."""
    if degree is None:
        return f"classagr:{entry.ipa}:{noun_cls}"
    if noun_cls is None:
        return f"degree:{entry.ipa}:{degree}"
    return f"classagr:{entry.ipa}:{noun_cls}:d={degree}"


def _apply_class_agreement(
    language: Language, entry: LexicalEntry, class_label: str | None, degree_label: str | None = None
) -> tuple[str, str]:
    """An article/adjective ``entry`` agreeing with a noun of class
    ``class_label`` (a ``"class:<name>"`` label or a bare class name) and/or
    carrying a ``degree_label`` (``"comparative"``/``"superlative"``) suffix --
    bare when the language has neither. The degree suffix sits closer to the
    root than the class one."""
    grammar = language.grammar
    noun_cls = (class_label or "").removeprefix(noun_class_gen.CLASS_AGREEMENT_PREFIX) or None
    class_affix = next((a for a in grammar.class_affixes if a.label == noun_cls), None) if noun_cls else None
    degree_affix = next((a for a in grammar.degree_affixes if a.label == degree_label), None) if degree_label else None
    if class_affix is None and degree_affix is None:
        return entry.romanization, entry.ipa
    parts = [degree_affix, class_affix]
    affix = InflectionAffix(
        label="adjective-agreement",
        prefix=tuple(sym for part in parts if part for sym in part.prefix),
        suffix=tuple(sym for part in parts if part for sym in part.suffix),
    )
    resolved_class = noun_cls if class_affix is not None else None
    resolved_degree = degree_label if degree_affix is not None else None
    rng = _translation_rng(language, _class_agreement_salt(entry, resolved_class, resolved_degree))
    ipa = inflection_gen.apply_affix(rng, affix, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language))
    romanization = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), entry.pos)
    return romanization, ipa


def _next_noun_gloss(slots, index: int) -> str | None:
    """The lemma of the first noun-like slot after ``slots[index]`` (what an
    article agrees with); ``None`` when there is none."""
    for later in slots[index + 1:]:
        if later.kind == "content" and later.gloss and later.pos in ("noun", "pronoun"):
            return later.gloss
        if later.kind == "name":
            return None
    return None


def _prev_noun_gloss(slots, index: int) -> str | None:
    """The lemma of the closest noun-like slot before ``slots[index]`` (what a
    demonstrative placed after its noun agrees with)."""
    for earlier in reversed(slots[:index]):
        if earlier.kind == "content" and earlier.gloss and earlier.pos in ("noun", "pronoun"):
            return earlier.gloss
        if earlier.kind == "name":
            return None
    return None


_NUMERAL_ONE = {"one", "1", "a", "an"}


def _effective_number(language: Language, slots, index: int) -> str | None:
    """The number label a noun slot really takes: the planned one, except that
    in a language whose nouns stay singular after a numeral above "one"
    (``plural_after_numeral`` false), a noun directly after such a numeral
    takes none."""
    slot = slots[index]
    if slot.number is None or language.grammar.plural_after_numeral or index == 0:
        return slot.number
    previous = slots[index - 1]
    if previous.kind == "content" and previous.pos == "numeral" and previous.gloss not in _NUMERAL_ONE:
        return None
    return slot.number


def _possessive_particle(language: Language) -> tuple[str, str] | None:
    ipa = language.grammar.possessive_particle
    return (language.romanization.apply(ipa), ipa) if ipa else None


def _linker_follows_clause(language: Language) -> bool:
    """Illustrative placement of a subordinating word ("that", "because",
    "who"): after its clause in verb-final languages (SOV, OSV, like
    Japanese -kara), before it everywhere else (like English "that")."""
    return language.grammar.word_order.value in ("SOV", "OSV")


def _render_plan(
    plan: sentence_planner.SentencePlan,
    language: Language,
    llm_client: LLMClient,
    coined: list[LexicalEntry],
) -> tuple[Language, list[str], list[str], list[str | None]]:
    working_language = language
    romanization_parts: list[str] = []
    ipa_parts: list[str] = []
    gloss_parts: list[str | None] = []
    mood_pending = plan.mood == "imperative"
    possessed_pending = False  # a possessor was rendered; the next noun takes the "possessed" affix
    possession = language.grammar.possession
    for slot_index, slot in enumerate(plan.slots):
        rendered: tuple[str, str] | None = None
        entry: LexicalEntry | None = None
        if slot.kind == "clause":
            if slot.clause is None:
                continue
            working_language, nested_rom, nested_ipa, nested_gloss = _render_plan(
                slot.clause, working_language, llm_client, coined
            )
            linker: tuple[str, str, str | None] | None = None
            if slot.gloss:
                working_language, linker_entry = _lookup_or_coin(
                    working_language, slot.gloss, PartOfSpeech.PARTICLE, coined, llm_client,
                    lemma_candidates=[slot.gloss],
                )
                linker = (linker_entry.romanization, linker_entry.ipa, linker_entry.primary_gloss)
            if linker is not None and _linker_follows_clause(working_language):
                nested_rom, nested_ipa, nested_gloss = nested_rom + [linker[0]], nested_ipa + [linker[1]], nested_gloss + [linker[2]]
            elif linker is not None:
                nested_rom, nested_ipa, nested_gloss = [linker[0]] + nested_rom, [linker[1]] + nested_ipa, [linker[2]] + nested_gloss
            romanization_parts.extend(nested_rom)
            ipa_parts.extend(nested_ipa)
            gloss_parts.extend(nested_gloss)
            continue
        if slot.kind == "content" and slot.gloss:
            pos = sentence_planner.POS_BY_PLAN_STRING.get(slot.pos, PartOfSpeech.NOUN)
            working_language, entry = _lookup_or_coin(
                working_language, slot.gloss, pos, coined, llm_client, lemma_candidates=[slot.gloss]
            )
            if pos is PartOfSpeech.VERB:
                agreement_label, object_label = _verb_agreement(working_language, slot)
                rendered = _apply_verb_inflection(
                    working_language, entry, slot.tense, agreement_label,
                    "imperative" if mood_pending else "declarative",
                    slot.aspect, slot.verb_mood, object_label, slot.voice,
                )
                mood_pending = False
            elif pos is PartOfSpeech.ADJECTIVE and (
                (slot.agrees_with and working_language.grammar.noun_classes) or slot.degree
            ):
                rendered = _apply_class_agreement(
                    working_language,
                    entry,
                    _class_label_of(working_language, slot.agrees_with) if slot.agrees_with else None,
                    slot.degree,
                )
            else:
                is_noun = pos is PartOfSpeech.NOUN
                rendered = _apply_case(
                    working_language,
                    entry,
                    "genitive" if slot.possessive and possession == "genitive" else slot.case,
                    _effective_number(working_language, plan.slots, slot_index) if is_noun else None,
                    possessed_pending and is_noun,
                )
                if is_noun:
                    possessed_pending = False
        elif slot.kind == "name" and slot.gloss:
            entry = names.find_name_entry(working_language, slot.gloss)
            if entry is None:
                entry = names.make_name_entry(working_language, slot.gloss, llm_client)
                coined.append(entry)
                working_language = working_language.with_new_words(
                    (entry,), reason=f"added the name '{slot.gloss}' during translation"
                )
            # A kept name stays exactly as written (its sounds may lie outside
            # this language's inventory, so no case affix or re-spelling); an
            # adapted one is native-sounding and inflects like any noun.
            rendered = (
                (entry.romanization, entry.ipa)
                if names.resolve_foreign_names(working_language) == "keep"
                else _apply_case(
                    working_language, entry, "genitive" if slot.possessive and possession == "genitive" else slot.case
                )
            )
        elif slot.kind == "copula":
            entry = working_language.lexicon.by_gloss("be")
            if entry is not None:
                agreement_label, object_label = _verb_agreement(working_language, slot)
                rendered = _apply_verb_inflection(
                    working_language, entry, slot.tense, agreement_label,
                    "imperative" if mood_pending else "declarative",
                    slot.aspect, slot.verb_mood, object_label,
                )
                mood_pending = False
        elif slot.kind == "demonstrative":
            working_language, entry = _lookup_or_coin(
                working_language, slot.gloss or "this", PartOfSpeech.PRONOUN, coined, llm_client,
                lemma_candidates=[slot.gloss or "this"],
            )
            rendered = (entry.romanization, entry.ipa)
            if working_language.grammar.noun_classes:
                noun_gloss = (
                    _prev_noun_gloss(plan.slots, slot_index)
                    if working_language.grammar.demonstrative_after_noun
                    else _next_noun_gloss(plan.slots, slot_index)
                )
                rendered = _apply_class_agreement(working_language, entry, _class_label_of(working_language, noun_gloss))
        elif slot.kind == "indefinite_article":
            if not working_language.grammar.has_indefinite_article:
                continue
            working_language, entry = _lookup_or_coin(
                working_language, "a", PartOfSpeech.PARTICLE, coined, llm_client, lemma_candidates=["a"]
            )
            rendered = (entry.romanization, entry.ipa)
            if working_language.grammar.noun_classes:
                rendered = _apply_class_agreement(
                    working_language, entry, _class_label_of(working_language, _next_noun_gloss(plan.slots, slot_index))
                )
        elif slot.kind in _BARE_GLOSS_BY_SLOT_KIND:
            entry = working_language.lexicon.by_gloss(_BARE_GLOSS_BY_SLOT_KIND[slot.kind])
            if entry is not None:
                rendered = (entry.romanization, entry.ipa)
                if slot.kind == "article" and working_language.grammar.noun_classes:
                    rendered = _apply_class_agreement(
                        working_language, entry, _class_label_of(working_language, _next_noun_gloss(plan.slots, slot_index))
                    )

        if rendered is not None:
            romanization_parts.append(rendered[0])
            ipa_parts.append(rendered[1])
            gloss_parts.append(entry.primary_gloss if entry is not None else None)
            if slot.possessive and slot.kind in ("content", "name"):
                if possession == "particle" and _possessive_particle(working_language) is not None:
                    particle_rom, particle_ipa = _possessive_particle(working_language)
                    romanization_parts.append(particle_rom)
                    ipa_parts.append(particle_ipa)
                    gloss_parts.append(None)
                elif possession == "affix":
                    possessed_pending = True

    if plan.mood == "question" and language.grammar.question_particle:
        particle_ipa = language.grammar.question_particle
        particle = (language.romanization.apply(particle_ipa), particle_ipa)
        position = 0 if _question_particle_first(language) else len(romanization_parts)
        romanization_parts.insert(position, particle[0])
        ipa_parts.insert(position, particle[1])
        gloss_parts.insert(position, None)
    return working_language, romanization_parts, ipa_parts, gloss_parts


def translate_to_conlang(
    text: str, language: Language, llm_client: LLMClient
) -> TranslationResult:
    """Translates ``text`` one sentence at a time (``sentence_planner.
    split_sentences``): each gets its own plan -- and its own mood
    (declarative, imperative, yes/no or wh-question) -- and the rendered
    sentences are joined with a space. Sandhi is applied within a sentence,
    never across a sentence boundary."""
    coined: list[LexicalEntry] = []
    working_language = language
    romanization_sentences: list[str] = []
    ipa_sentences: list[str] = []
    for sentence in sentence_planner.split_sentences(text) or [text]:
        plan = sentence_planner.plan_sentence(sentence, working_language, llm_client)
        working_language, rom_parts, ipa_parts, gloss_parts = _render_plan(
            plan, working_language, llm_client, coined
        )
        romanization_sentences.append(" ".join(rom_parts))
        ipa_sentences.append(" ".join(tone_sandhi.apply_sandhi(ipa_parts, language.tone_system, gloss_parts)))

    return TranslationResult(
        text=" ".join(part for part in romanization_sentences if part),
        ipa=" ".join(part for part in ipa_sentences if part),
        language=working_language,
        coined=tuple(coined),
        pattern="llm-plan",
    )


def _decode_noun(language: Language, token: str) -> tuple[LexicalEntry, str] | None:
    """Reverse of ``_apply_case``: returns ``(entry, case_label)`` for a
    noun-position conlang token, ``"unmarked"`` for a bare/uninflected
    match (the common case -- an isolating language, or the argument
    alignment leaves unmarked). Decoding is generate-and-compare, not a
    parse: since spelling isn't a clean invertible function in general
    (the same reason ``sound_change.py``'s own reform-detection compares
    via ``apply()`` rather than string surgery), this renders each real
    noun entry's own bare form and, if that doesn't match, each of its
    case-marked forms via the identical ``inflection_gen.apply_affix``
    path encoding used, then compares against the observed token. ``None``
    when no noun entry (marked or not) matches at all."""
    normalized = _normalize(token)
    # A subject/object argument may be a real noun or a pronoun (e.g. "I")
    # -- both fill the same syntactic slot, the same reason
    # translate_to_conlang's own _lookup_or_coin never restricts a
    # subject/object lookup to PartOfSpeech.NOUN (only the *coining*
    # fallback POS, for a genuinely new word, is NOUN).
    noun_entries = [e for e in language.lexicon.entries if e.pos in (PartOfSpeech.NOUN, PartOfSpeech.PRONOUN)]
    for entry in noun_entries:
        if _normalize(entry.romanization) == normalized:
            return entry, "unmarked"
    for entry in noun_entries:
        for affix in language.grammar.case_affixes:
            rng = _translation_rng(language, _case_affix_salt(entry, affix.label))
            ipa = inflection_gen.apply_affix(
                rng, affix, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language)
            )
            candidate = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), entry.pos)
            if _normalize(candidate) == normalized:
                return entry, affix.label
    for entry in noun_entries:
        for number_affix in language.grammar.number_affixes:
            for case_affix in [None, *language.grammar.case_affixes]:
                case_label = case_affix.label if case_affix else None
                affix, resolved_case = _noun_affix(language.grammar, case_label, number_affix.label)
                if affix is None:
                    continue
                rng = _translation_rng(language, _noun_affix_salt(entry, resolved_case, number_affix.label))
                ipa = inflection_gen.apply_affix(
                    rng, affix, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language)
                )
                candidate = apply_grammatical_spelling(
                    language.romanization, language.romanization.apply(ipa), entry.pos
                )
                if _normalize(candidate) == normalized:
                    return entry, number_affix.label if case_label is None else f"{case_label}+{number_affix.label}"
    if language.grammar.possession_affixes:
        for entry in noun_entries:
            for number_affix in [None, *language.grammar.number_affixes]:
                number_label = number_affix.label if number_affix else None
                for case_affix in [None, *language.grammar.case_affixes]:
                    case_label = case_affix.label if case_affix else None
                    affix, resolved_case = _noun_affix(language.grammar, case_label, number_label, True)
                    if affix is None:
                        continue
                    rng = _translation_rng(language, _noun_affix_salt(entry, resolved_case, number_label, True))
                    ipa = inflection_gen.apply_affix(
                        rng, affix, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language)
                    )
                    candidate = apply_grammatical_spelling(
                        language.romanization, language.romanization.apply(ipa), entry.pos
                    )
                    if _normalize(candidate) == normalized:
                        return entry, "+".join(p for p in (case_label, number_label, "possessed") if p)
    return None


def _initial_letter(text: str) -> str:
    stripped = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))
    return stripped[:1]


def _stem_prefix(text: str) -> str:
    """The first two letters, diacritics removed -- what an inflected verb
    keeps of its stem."""
    stripped = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))
    return stripped[:2]


def _decode_adjective_full(language: Language, token: str) -> tuple[LexicalEntry, str | None, str | None] | None:
    """``(entry, class_name, degree_label)`` for an adjective (or demonstrative)
    carrying a class-agreement and/or degree suffix; ``None`` when no
    combination spells ``token``. Plainest reading first."""
    normalized = _normalize(token)
    prefix = _stem_prefix(token)
    grammar = language.grammar
    class_options: list[str | None] = [None] + [a.label for a in grammar.class_affixes]
    degree_options: list[str | None] = [None] + [a.label for a in grammar.degree_affixes]
    combos = sorted(
        ((c, d) for c in class_options for d in degree_options if c is not None or d is not None),
        key=lambda cd: (cd[0] is not None) + (cd[1] is not None),
    )
    for entry in language.lexicon.entries:
        is_adjective = entry.pos is PartOfSpeech.ADJECTIVE
        if not (is_adjective or entry.primary_gloss in ("this", "that")) or _stem_prefix(entry.romanization) != prefix:
            continue
        for class_label, degree_label in combos:
            if degree_label is not None and not is_adjective:
                continue
            if _normalize(_apply_class_agreement(language, entry, class_label, degree_label)[0]) == normalized:
                return entry, class_label, degree_label
    return None


def _decode_adjective(language: Language, token: str) -> tuple[LexicalEntry, str] | None:
    """An adjective carrying a class-agreement suffix: ``(entry,
    class_name)``; ``None`` when no adjective plus class affix spells
    ``token``. (See ``_decode_adjective_full`` for degree suffixes.)"""
    full = _decode_adjective_full(language, token)
    return None if full is None or full[1] is None else (full[0], full[1])


def _article_forms(language: Language) -> set[str]:
    """Every spelling of "the" in this language: bare, plus one per noun class."""
    forms: set[str] = set()
    for gloss in ("the", "a"):
        entry = language.lexicon.by_gloss(gloss)
        if entry is None:
            continue
        forms.add(_normalize(entry.romanization))
        for affix in language.grammar.class_affixes:
            forms.add(_normalize(_apply_class_agreement(language, entry, affix.label)[0]))
    return forms


def _decode_verb_full(
    language: Language, token: str
) -> tuple[LexicalEntry, str | None, str | None, str | None, str | None] | None:
    """``(entry, tense_label, aspect_label, verb_mood_label, voice_label)``
    for a verb-position token, with ``"imperative"`` in the tense slot for an
    imperative. Generate-and-compare like ``_decode_noun``. The full search
    over tense x aspect x mood x voice x object x agreement is large, so it is
    staged (see below) and restricted to verbs whose first two letters match
    the token's (suffixes never change them); if that finds nothing, the
    earlier tense x agreement search runs over every verb."""
    normalized = _normalize(token)
    verb_entries = [e for e in language.lexicon.entries if e.pos is PartOfSpeech.VERB]
    for entry in verb_entries:
        if _normalize(entry.romanization) == normalized:
            return entry, None, None, None, None
    imperative = next((a for a in language.grammar.mood_affixes if a.label == "imperative"), None)
    if imperative is not None:
        for entry in verb_entries:
            rng = _translation_rng(language, _imperative_salt(entry))
            ipa = inflection_gen.apply_affix(
                rng, imperative, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language)
            )
            candidate = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), entry.pos)
            if _normalize(candidate) == normalized:
                return entry, "imperative", None, None, None
    kwargs = _stress_and_word_accent_kwargs(language)
    grammar = language.grammar
    tense_options: list[str | None] = [None] + list(grammar.tenses)
    aspect_options: list[str | None] = [None] + list(grammar.aspects)
    mood_options: list[str | None] = [None] + [m for m in grammar.moods if m != "imperative"]
    object_options: list[str | None] = [None] + [a.label for a in grammar.object_agreement_affixes]
    voice_options: list[str | None] = [None] + list(grammar.voices)
    agreement_options = _agreement_labels(grammar)

    def search(entries, aspects, moods, objects, voices):
        # Different label combinations can spell the same word (short
        # suffixes concatenate alike), so try the plainest reading first:
        # fewest optional labels, and a tense whenever the language has
        # tenses (the encoder normally supplies one).
        combos = sorted(
            (
                (tense_label, aspect_label, mood_label, object_label, voice_label)
                for tense_label in tense_options
                for aspect_label in aspects
                for mood_label in moods
                for object_label in objects
                for voice_label in voices
            ),
            key=lambda c: (c[1] is not None) + (c[2] is not None) + (c[3] is not None) + (c[4] is not None)
            + (c[0] is None and bool(grammar.tenses)),
        )
        for tense_label, aspect_label, mood_label, object_label, voice_label in combos:
            for entry in entries:
                for agreement_label in agreement_options:
                    affix = _combined_tense_agreement_affix(
                        grammar, tense_label, agreement_label, aspect_label, mood_label, object_label, voice_label
                    )
                    if affix is None:
                        continue
                    rng = _translation_rng(
                        language,
                        _verb_affix_salt(
                            entry, tense_label, agreement_label, aspect_label, mood_label, object_label, voice_label
                        ),
                    )
                    ipa = inflection_gen.apply_affix(rng, affix, entry.ipa, language.phonology, **kwargs)
                    candidate = apply_grammatical_spelling(
                        language.romanization, language.romanization.apply(ipa), entry.pos
                    )
                    if _normalize(candidate) == normalized:
                        return entry, tense_label, aspect_label, mood_label, voice_label
        return None

    prefix = _stem_prefix(token)
    likely = [e for e in verb_entries if _stem_prefix(e.romanization) == prefix]
    # Stages, cheapest first: tense x agreement x object agreement; then a
    # voice; then aspect/mood without an object marker (alone, and with a
    # voice); then aspect/mood with object agreement (only in languages that
    # have it at all).
    stages = [
        ([None], [None], object_options, [None]),
        ([None], [None], [None], voice_options),
        (aspect_options, mood_options, [None], [None]),
        (aspect_options, [None], [None], voice_options),
        (aspect_options, mood_options, object_options, [None]),
    ]
    tried: list[tuple] = []
    for stage in stages:
        aspects, moods, objects, voices = stage
        if stage in tried or (tried and (len(aspects), len(moods), len(objects), len(voices)) == (1, 1, 1, 1)):
            continue
        tried.append(stage)
        found = search(likely, aspects, moods, objects, voices)
        if found is not None:
            return found
    if len(likely) != len(verb_entries):
        return search(verb_entries, [None], [None], [None], [None])
    return None


def _decode_verb(language: Language, token: str) -> tuple[LexicalEntry, str | None] | None:
    """The verb-position counterpart of ``_decode_noun`` -- returns
    ``(entry, tense_label)`` (``None`` for the tense when this language
    has no tense system, or the exact bare form matched; ``"imperative"``
    for an imperative). See ``_decode_verb_full`` for aspect and mood."""
    full = _decode_verb_full(language, token)
    return None if full is None else (full[0], full[1])


def _english_verb_gloss(entry: LexicalEntry, tense_label: str | None) -> str:
    """The English surface form for a decoded verb entry -- special-cased
    for "be" (the copula never takes a regular ``-ed``-style past, and
    isn't in ``_PAST_FORM_BY_LEMMA``'s own small irregular-verb list),
    otherwise the bare lemma for anything but a ``"past"`` reading, or
    ``_PAST_FORM_BY_LEMMA``'s irregular form/a regular ``-ed`` suffix."""
    if entry.primary_gloss == "be":
        return "was" if tense_label == "past" else "is"
    if tense_label != "past":
        return entry.primary_gloss
    return _PAST_FORM_BY_LEMMA.get(entry.primary_gloss, entry.primary_gloss + "ed")


def _english_verb_phrase(
    entry: LexicalEntry,
    tense_label: str | None,
    aspect_label: str | None,
    mood_label: str | None,
    voice_label: str | None = None,
) -> str:
    """A rough English rendering of a decoded verb with aspect/mood -- the
    plain fallback draft, not the fluent sentence (the LLM sees the labels)."""
    gloss = entry.primary_gloss
    if voice_label == "passive":
        participle = _PARTICIPLE_BY_LEMMA.get(gloss) or _PAST_FORM_BY_LEMMA.get(gloss, gloss + "ed")
        return f"was {participle}" if tense_label == "past" else f"is {participle}"
    if voice_label == "causative":
        return f"made {gloss}" if tense_label == "past" else f"makes {gloss}"
    if mood_label in ("conditional",):
        return f"would {gloss}"
    if mood_label in ("potential",):
        return f"can {gloss}"
    if mood_label in ("subjunctive", "irrealis"):
        return f"might {gloss}"
    if aspect_label in ("progressive", "imperfective"):
        return f"is {gloss}ing" if tense_label != "past" else f"was {gloss}ing"
    if aspect_label == "perfect":
        return f"has {_PARTICIPLE_BY_LEMMA.get(gloss) or _PAST_FORM_BY_LEMMA.get(gloss, gloss + 'ed')}"
    if aspect_label == "habitual":
        return f"usually {gloss}s"
    return _english_verb_gloss(entry, tense_label)


def _construction_note(language: Language) -> str:
    """A sentence appended to the fluency prompt saying how this language
    expresses "there is X" and "A has B", so the model can read those
    constructions back as English (the decoded gloss sequence alone shows
    only "exist"/"be" and a dative or possessor-marked word)."""
    grammar = language.grammar
    existential = (
        'X plus the verb "exist"'
        if grammar.existential == "verb"
        else "X plus the copula \"be\" (or just X where there is no copula)"
    )
    possession = (
        'the ordinary transitive verb "have"'
        if grammar.possession_clause == "have"
        else (
            'no verb "have": it is written as A (in the dative or marked as a possessor) followed by '
            + ('"exist"' if grammar.existential == "verb" else '"be"')
            + " with B as its subject -- read that as \"A has B\""
        )
    )
    standard = {
        "particle": 'the standard of comparison follows a word "than"',
        "case": f"the standard of comparison is in the {grammar.comparative_case} case (no word for \"than\")",
        "exceed": 'comparison uses the verb "exceed" with the standard as its object (no word for "than")',
    }.get(grammar.comparative_strategy, "the standard of comparison is unmarked")
    degrees = (
        ("the comparative is a suffix" if grammar.comparative_marking == "affix" else 'the comparative is the word "more"')
        + ", "
        + ("the superlative a suffix" if grammar.superlative_marking == "affix" else 'the superlative the word "most"')
    )
    return (
        f' In this language "there is X" is expressed as {existential}, and "A has B" as {possession}.'
        f" Comparison: {degrees}; {standard}. Read these as ordinary English comparatives and superlatives."
    )


def translate_to_english(
    text: str, language: Language, llm_client: LLMClient
) -> TranslationResult:
    raw_tokens = unicodedata.normalize("NFC", text).strip().split()
    article_forms = _article_forms(language)
    tokens = [t for t in raw_tokens if _normalize(t) not in article_forms]

    # Per-token, structure-agnostic decode -- the plan-driven encoder can
    # produce genuinely arbitrary structure, so there's no fixed sentence
    # shape left to special-case on the way back (see this module's own
    # docstring). ``plain`` feeds a deterministic fake/fallback answer
    # (and the real fluency LLM's own "if all else fails" text);
    # ``annotated`` gives a real LLM the case/tense information a bare
    # gloss sequence would otherwise lose.
    plain: list[str] = []
    annotated: list[str] = []
    particle_ipa = language.grammar.question_particle
    particle_form = _normalize(language.romanization.apply(particle_ipa)) if particle_ipa else None
    possessive_ipa = language.grammar.possessive_particle
    possessive_form = _normalize(language.romanization.apply(possessive_ipa)) if possessive_ipa else None
    is_question = False
    is_imperative = False
    for tok in tokens:
        if particle_form is not None and _normalize(tok) == particle_form and language.lexicon.by_form(tok) is None:
            is_question = True
            continue
        if (
            possessive_form is not None
            and _normalize(tok) == possessive_form
            and language.lexicon.by_form(tok) is None
        ):
            plain.append("of")
            annotated.append("of")
            continue
        entry = language.lexicon.by_form(tok)
        if entry is not None:
            plain.append(entry.primary_gloss)
            annotated.append(entry.primary_gloss)
            continue
        noun_decoded = _decode_noun(language, tok)
        if noun_decoded is not None:
            noun_entry, case_label = noun_decoded
            parts = [] if case_label == "unmarked" else case_label.split("+")
            number_part = next((p for p in parts if p in ("plural", "dual")), None)
            case_part = next((p for p in parts if p not in ("plural", "dual", "possessed")), None)
            is_possessed = "possessed" in parts
            plain.append(noun_entry.primary_gloss + ("s" if number_part else ""))
            notes = (
                ([number_part] if number_part else [])
                + (["possessed"] if is_possessed else [])
                + ([f"case: {case_part}"] if case_part else [])
            )
            annotated.append(
                noun_entry.primary_gloss if not notes else f"{noun_entry.primary_gloss} ({', '.join(notes)})"
            )
            continue
        adjective_decoded = (
            _decode_adjective_full(language, tok)
            if language.grammar.class_affixes or language.grammar.degree_affixes
            else None
        )
        if adjective_decoded is not None:
            adjective_entry, _, degree_label = adjective_decoded
            gloss = adjective_entry.primary_gloss
            plain.append(
                f"more {gloss}" if degree_label == "comparative" else f"most {gloss}" if degree_label == "superlative" else gloss
            )
            annotated.append(gloss if degree_label is None else f"{gloss} ({degree_label})")
            continue
        verb_full = _decode_verb_full(language, tok)
        if verb_full is not None:
            verb_entry, tense_label, aspect_label, mood_label, voice_label = verb_full
            if tense_label == "imperative":
                is_imperative = True
                plain.append(verb_entry.primary_gloss)
                annotated.append(f"{verb_entry.primary_gloss} (mood: imperative)")
                continue
            gloss = _english_verb_phrase(verb_entry, tense_label, aspect_label, mood_label, voice_label)
            plain.append(gloss)
            notes = [
                f"{name}: {label}"
                for name, label in (
                    ("tense", tense_label), ("aspect", aspect_label), ("mood", mood_label), ("voice", voice_label)
                )
                if label is not None
            ]
            annotated.append(gloss if not notes else f"{gloss} ({', '.join(notes)})")
            continue
        plain.append(f"<unknown:{tok}>")
        annotated.append(f"<unknown:{tok}>")

    plain_draft = " ".join(plain) + ("?" if is_question else "!" if is_imperative else "")
    annotated_draft = " ".join(annotated) + (
        " [this is a yes/no question]" if is_question else " [this is a command]" if is_imperative else ""
    )
    request = LLMRequest(
        system=(
            "You turn an annotated rough English gloss sequence from a "
            "constructed-language translation into one natural, fluent "
            "English sentence. Each word is its English gloss, optionally "
            "annotated with '(plural)'/'(dual)' (render the noun plural or with 'two'), "
            "'(possessed)' (owned by the preceding word), 'of' (a possessive marker between an "
            "owner and the thing owned), '(mood: imperative)' "
            "(a command), '(case: X)' (this word's grammatical role -- "
            "e.g. an accusative/absolutive/ergative-marked word is "
            "typically a direct object) or '(tense: X)', '(aspect: X)', '(mood: X)' or '(voice: X)' (a verb's "
            "detected tense, aspect, verbal mood or voice -- render them as the matching English "
            "tense, progressive/perfect/habitual aspect, would/can/might, or a passive (the patient "
            "is the subject, the agent follows 'by'), antipassive (no object) or causative (make X do)). "
            "Keep the meaning and the word order's implied roles; do not "
            "add new content; drop the annotations themselves from your "
            "output."
            + _construction_note(language)
        ),
        prompt=f"Rough gloss sequence: {annotated_draft}\nWrite a natural English sentence:",
        model=DEFAULT_MODEL,
        max_tokens=64,
        purpose="translate.fluency",
        metadata={"fake_strategy": "passthrough", "fallback_text": plain_draft},
    )
    response = llm_client.complete(request)
    return TranslationResult(
        text=response.text, ipa="", language=language, coined=(), pattern="llm-plan"
    )
