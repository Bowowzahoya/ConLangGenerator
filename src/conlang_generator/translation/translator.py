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

import dataclasses
import hashlib
import random
import unicodedata
from dataclasses import dataclass

from conlang_generator.core.grammar import GrammarProfile, InflectionAffix
from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from conlang_generator.core.romanization import apply_grammatical_spelling
from conlang_generator.generation import (
    classifier_gen,
    inflection_gen,
    noun_class_gen,
    pronoun_gen,
    stress_gen,
    subordination_gen,
    comparison_gen,
    np_followups_gen,
    tone_sandhi,
    voice_np_gen,
    word_accent_gen,
)
from conlang_generator.generation.reference_languages import match_profiles
from conlang_generator.llm.base import LLMClient, LLMRequest
from conlang_generator.llm.pricing import DEFAULT_MODEL
from conlang_generator.translation import expansion, names, sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot

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
    verb_number: str | None = None,
    polite: bool = False,
    evidential_label: str | None = None,
    negative: bool = False,
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
    number_affix = (
        next((a for a in grammar.verb_number_affixes if a.label == verb_number), None) if verb_number else None
    )
    polite_affix = next((a for a in grammar.verb_polite_affixes if a.label == "polite"), None) if polite else None
    evidential_affix = (
        next((a for a in grammar.evidential_affixes if a.label == evidential_label), None) if evidential_label else None
    )
    negative_affix = next((a for a in grammar.verb_negative_affixes if a.label == "negative"), None) if negative else None
    parts = [
        voice_affix, aspect_affix, tense_affix, mood_affix, evidential_affix, negative_affix, agreement_affix,
        number_affix, polite_affix, object_affix,
    ]
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
    verb_number: str | None = None,
    polite: bool = False,
    evidential_label: str | None = None,
    negative: bool = False,
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
    if verb_number:
        salt += f":n={verb_number}"
    if polite:
        salt += ":h=polite"
    if evidential_label:
        salt += f":e={evidential_label}"
    if negative:
        salt += ":neg"
    return salt


def _noun_affix(
    grammar: GrammarProfile,
    case_label: str | None,
    number_label: str | None,
    possessed: bool = False,
    possessor_person: str | None = None,
    class_marker: str | None = None,
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
    person_affix = (
        next((a for a in grammar.possessor_person_affixes if a.label == possessor_person), None)
        if possessor_person
        else None
    )
    marker_affix = (
        next((a for a in grammar.class_marker_affixes if a.label == class_marker), None) if class_marker else None
    )
    if number_affix is None and possessed_affix is None and person_affix is None and marker_affix is None:
        return case_affix, resolved_case
    parts = [marker_affix, number_affix, person_affix, possessed_affix, case_affix]
    prefix = tuple(sym for part in parts if part for sym in part.prefix)
    suffix = tuple(sym for part in parts if part for sym in part.suffix)
    return InflectionAffix(label="number+case", prefix=prefix, suffix=suffix), resolved_case


def _noun_affix_salt(
    entry: LexicalEntry,
    case_label: str | None,
    number_label: str | None,
    possessed: bool = False,
    possessor_person: str | None = None,
    class_marker: str | None = None,
) -> str:
    """``_case_affix_salt`` for a case-only marking (so every pre-number
    sentence keeps its exact rng stream); a distinct salt once number or
    possession is involved. Shared by encoding and decoding like the other
    salts."""
    if number_label is None and not possessed and not possessor_person and not class_marker:
        return _case_affix_salt(entry, case_label or "")
    return (
        f"noun:{entry.ipa}:{case_label}:{number_label}"
        + (":possessed" if possessed else "")
        + (f":pp={possessor_person}" if possessor_person else "")
        + (f":cm={class_marker}" if class_marker else "")
    )


def _apply_case(
    language: Language,
    entry: LexicalEntry,
    case_label: str | None,
    number_label: str | None = None,
    possessed: bool = False,
    possessor_person: str | None = None,
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
    resolved_person = (
        possessor_person if any(a.label == possessor_person for a in grammar.possessor_person_affixes) else None
    )
    marker = (
        _entry_class(language, entry)
        if grammar.class_marking != "none" and entry.pos is PartOfSpeech.NOUN and not names.is_name_entry(entry)
        else None
    )
    affix, resolved_case = _noun_affix(grammar, case_label, number_label, resolved_possessed, resolved_person, marker)
    if affix is None:
        return entry.romanization, entry.ipa
    resolved_number = number_label if any(a.label == number_label for a in grammar.number_affixes) else None
    rng = _translation_rng(
        language, _noun_affix_salt(entry, resolved_case, resolved_number, resolved_possessed, resolved_person, marker)
    )
    ipa = inflection_gen.apply_affix(rng, affix, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language))
    romanization = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), entry.pos)
    return romanization, ipa


def _verb_form_salt(
    entry: LexicalEntry, verb_form: str, agreement: str | None = None, case: str | None = None
) -> str:
    salt = f"form:{entry.ipa}:{verb_form}"
    if agreement:
        salt += f":agr={agreement}"
    if case:
        salt += f":case={case}"
    return salt


def _non_finite_affix(
    grammar: GrammarProfile, form_affix: InflectionAffix, agreement: str | None, case: str | None
) -> InflectionAffix:
    """The non-finite form's suffix, followed by its controller's agreement
    suffix (infinitive) or its function's case suffix (nominalization)."""
    if agreement is None and case is None:
        return form_affix
    parts = [form_affix]
    if agreement is not None:
        parts.append(next((a for a in grammar.agreement_affixes if a.label == agreement), None))
    if case is not None:
        parts.append(next((a for a in grammar.case_affixes if a.label == case), None))
    return InflectionAffix(
        label="non-finite",
        prefix=tuple(sym for part in parts if part for sym in part.prefix),
        suffix=tuple(sym for part in parts if part for sym in part.suffix),
    )


def _imperative_salt(entry: LexicalEntry) -> str:
    return f"mood:{entry.ipa}:imperative"


def _prohibitive_salt(entry: LexicalEntry) -> str:
    return f"mood:{entry.ipa}:prohibitive"


def _finite_verb_indices(language: Language, slots) -> list[int]:
    """Indices of the finite verb/copula slots (the ones that take inflection)."""
    grammar = language.grammar
    has_be = language.lexicon.by_gloss("be") is not None
    found = []
    for index, slot in enumerate(slots):
        if slot.verb_form in grammar.verb_forms:
            continue
        if slot.kind == "copula" and has_be:
            found.append(index)
        elif slot.kind == "content" and slot.pos == "verb" and slot.gloss:
            found.append(index)
    return found


def _negation_absorption(language: Language, slots, imperative: bool) -> tuple[set[int], set[int], set[int]]:
    """``(negative verbs, prohibitive verbs, dropped negation slots)``: with a
    negative suffix (``affix``/``both``) a negation slot marks its nearest
    finite verb (and, for ``affix``, no longer renders as a word); in a
    language with a prohibitive, a negated command takes that mood on its verb
    instead of any negation word."""
    grammar = language.grammar
    prohibitive_ok = any(a.label == "prohibitive" for a in grammar.mood_affixes)
    affix_ok = grammar.negation_strategy in ("affix", "both") and bool(grammar.verb_negative_affixes)
    negatives: set[int] = set()
    prohibitives: set[int] = set()
    dropped: set[int] = set()
    if not (affix_ok or (imperative and prohibitive_ok)):
        return negatives, prohibitives, dropped
    verbs = _finite_verb_indices(language, slots)
    if not verbs:
        return negatives, prohibitives, dropped
    for index, slot in enumerate(slots):
        if slot.kind != "negation":
            continue
        target = min(verbs, key=lambda v: (abs(v - index), v))
        if imperative:
            if prohibitive_ok and target == verbs[0]:
                prohibitives.add(target)
                dropped.add(index)
        elif affix_ok:
            negatives.add(target)
            if grammar.negation_strategy == "affix":
                dropped.add(index)
    return negatives, prohibitives, dropped


_EVIDENTIAL_ADVERB = {"reported": "reportedly", "inferred": "apparently", "witnessed": "visibly"}
_AUXILIARY_ENGLISH = {
    "past": "did", "future": "will", "perfective": "has", "imperfective": "was", "progressive": "is",
    "perfect": "has", "habitual": "usually", "irrealis": "might", "subjunctive": "might",
    "conditional": "would", "potential": "can",
}


def _auxiliary_entries(
    language: Language, labels: list[str], coined: list[LexicalEntry], llm_client: LLMClient
) -> tuple[Language, list[LexicalEntry]]:
    """The auxiliary words (``aux-<label>``) for these labels, coined on first use."""
    entries = []
    for label in labels:
        gloss = inflection_gen.AUXILIARY_GLOSS_PREFIX + label
        language, entry = _lookup_or_coin(language, gloss, PartOfSpeech.PARTICLE, coined, llm_client, [gloss])
        entries.append(entry)
    return language, entries


def _split_auxiliary_tokens(language: Language, tokens: list[str]) -> tuple[list[str], dict[int, list[str]]]:
    """Takes the auxiliary words out of a token list and returns the labels
    each one carries, keyed by the index (in the shortened list) of the verb
    it belongs to -- the next token, or the previous with ``after``."""
    after = language.grammar.auxiliary_position == "after"
    kept: list[str] = []
    hosts: dict[int, list[str]] = {}
    for token in tokens:
        entry = language.lexicon.by_form(token)
        if entry is not None and entry.primary_gloss.startswith(inflection_gen.AUXILIARY_GLOSS_PREFIX):
            label = entry.primary_gloss[len(inflection_gen.AUXILIARY_GLOSS_PREFIX):]
            hosts.setdefault(max(len(kept) - 1, 0) if after else len(kept), []).append(label)
            continue
        kept.append(token)
    return kept, hosts


def _split_periphrastic(
    language: Language, tense: str | None, aspect: str | None, mood: str | None
) -> tuple[str | None, str | None, str | None, list[str]]:
    """Removes the tense/aspect/mood labels this language spells with an
    auxiliary word and returns them (in tense, aspect, mood order)."""
    grammar = language.grammar
    labels = grammar.periphrastic_labels
    auxiliaries: list[str] = []
    if tense in labels and tense in grammar.tenses:
        auxiliaries.append(tense)
        tense = None
    if aspect in labels and aspect in grammar.aspects:
        auxiliaries.append(aspect)
        aspect = None
    if mood in labels and mood in grammar.moods:
        auxiliaries.append(mood)
        mood = None
    return tense, aspect, mood, auxiliaries


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
    verb_number_label: str | None = None,
    polite: bool = False,
    verb_form: str | None = None,
    nominal_case: str | None = None,
    evidential: str | None = None,
    negative: bool = False,
    prohibitive: bool = False,
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
        prohibitive_affix = next((a for a in grammar.mood_affixes if a.label == "prohibitive"), None)
        if prohibitive and prohibitive_affix is not None:
            imperative = prohibitive_affix  # a negated command: the verb carries the negation
        if imperative is None:
            return entry.romanization, entry.ipa
        salt = _prohibitive_salt(entry) if imperative is prohibitive_affix else _imperative_salt(entry)
        rng = _translation_rng(language, salt)
        ipa = inflection_gen.apply_affix(
            rng, imperative, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language)
        )
        romanization = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), entry.pos)
        return romanization, ipa
    if verb_form is not None and verb_form in grammar.verb_forms:
        # A non-finite form carries its own suffix instead of tense and agreement
        # (an infinitive may still agree with its controller, a nominalization
        # take the case of its function).
        form_affix = next((a for a in grammar.verb_form_affixes if a.label == verb_form), None)
        if form_affix is not None:
            extra_agreement = (
                agreement_label
                if verb_form == "infinitive" and grammar.infinitive_agrees and agreement_label in pronoun_gen.PERSON_LABELS
                else None
            )
            extra_case = (
                nominal_case
                if verb_form == "nominalized" and grammar.nominalized_takes_case and nominal_case in grammar.cases
                else None
            )
            affix = _non_finite_affix(grammar, form_affix, extra_agreement, extra_case)
            rng = _translation_rng(language, _verb_form_salt(entry, verb_form, extra_agreement, extra_case))
            ipa = inflection_gen.apply_affix(
                rng, affix, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language)
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
    resolved_number = verb_number_label if verb_number_label and grammar.verb_number_agreement else None
    resolved_polite = bool(polite and grammar.verb_politeness)
    resolved_evidential = evidential if evidential in grammar.evidentials else None
    resolved_negative = bool(negative and grammar.verb_negative_affixes)
    affix = _combined_tense_agreement_affix(
        grammar, resolved_tense, resolved_agreement, resolved_aspect, resolved_verb_mood, resolved_object,
        resolved_voice, resolved_number, resolved_polite, resolved_evidential, resolved_negative,
    )
    if affix is None:
        return entry.romanization, entry.ipa
    rng = _translation_rng(
        language,
        _verb_affix_salt(
            entry, resolved_tense, resolved_agreement, resolved_aspect, resolved_verb_mood, resolved_object,
            resolved_voice, resolved_number, resolved_polite, resolved_evidential, resolved_negative,
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


_OBJECT_PERSON_BY_GLOSS = pronoun_gen.PERSON_BY_GLOSS


def grammar_now_case(language: Language) -> str | None:
    """The case that marks the standard of a comparison, or ``None``."""
    grammar = language.grammar
    return grammar.comparative_case if grammar.comparative_strategy == "case" and grammar.comparative_case else None


def _class_gloss(gloss: str) -> str:
    """A suppletive plural (``child-plural``) belongs to its singular's class."""
    split = voice_np_gen.suppletive_split(gloss)
    return split[0] if split is not None and split[1] == "plural" else gloss


def _class_label_of(language: Language, gloss: str | None) -> str | None:
    """The ``"class:<name>"`` agreement label of the noun with lemma
    ``gloss`` (``None`` in a language with no noun classes)."""
    if not gloss:
        return None
    gloss = _class_gloss(gloss)
    grammar = language.grammar
    entry = _find_word(language, gloss) if grammar.noun_class_assignment == "formal" else None
    noun_cls = noun_class_gen.assigned_class(
        grammar.noun_classes, language.spec.seed, gloss, grammar.noun_class_assignment, entry.ipa if entry else None
    )
    return noun_class_gen.class_agreement_label(noun_cls) if noun_cls else None


def _entry_class(language: Language, entry: LexicalEntry) -> str | None:
    """The class name of a lexicon noun (``None`` in a language without
    classes) -- from its own gloss and, in a ``formal`` language, its form."""
    grammar = language.grammar
    if not grammar.noun_classes:
        return None
    return noun_class_gen.assigned_class(
        grammar.noun_classes, language.spec.seed, _class_gloss(entry.primary_gloss), grammar.noun_class_assignment,
        entry.ipa,
    )


def _verb_agreement(language: Language, slot: sentence_planner.PlannedSlot) -> tuple[str, str | None]:
    """``(subject agreement label, object agreement label)`` for a finite
    verb/copula slot: a noun subject's class replaces the ``"default"``
    (3rd person) label; an object is agreed with only in a language with
    object agreement (a pronoun by person, a noun by class)."""
    if slot.voice == "impersonal" or (slot.voice == "passive" and language.grammar.passive_agreement == "none"):
        return "default", None  # no subject to agree with / the passive does not agree
    agreement = slot.agreement or "default"
    if agreement == "default" and slot.subject_gloss:
        subject_class = _class_label_of(language, slot.subject_gloss)
        if subject_class in _agreement_labels(language.grammar):
            agreement = subject_class
    object_label: str | None = None
    if language.grammar.object_agreement and slot.object_gloss:
        if slot.object_gloss in (pronoun_gen.REFLEXIVE_GLOSS, pronoun_gen.RECIPROCAL_GLOSS):
            object_label = agreement if agreement in pronoun_gen.PERSON_LABELS else None
        else:
            object_label = _OBJECT_PERSON_BY_GLOSS.get(slot.object_gloss) or _class_label_of(
                language, slot.object_gloss
            )
    return agreement, object_label


def _class_agreement_salt(
    entry: LexicalEntry,
    noun_cls: str | None,
    degree: str | None = None,
    number: str | None = None,
    case: str | None = None,
) -> str:
    """Rng salt for an agreeing word: the earlier salts when there is no
    number or case agreement (so existing output is unchanged), distinct
    salts otherwise."""
    if degree is None:
        salt = f"classagr:{entry.ipa}:{noun_cls}"
    elif noun_cls is None:
        salt = f"degree:{entry.ipa}:{degree}"
    else:
        salt = f"classagr:{entry.ipa}:{noun_cls}:d={degree}"
    if number:
        salt += f":n={number}"
    if case:
        salt += f":c={case}"
    return salt


def _apply_class_agreement(
    language: Language,
    entry: LexicalEntry,
    class_label: str | None,
    degree_label: str | None = None,
    number_label: str | None = None,
    case_label: str | None = None,
) -> tuple[str, str]:
    """An agreeing word (article, adjective, demonstrative, numeral,
    possessive) ``entry`` taking the class of its noun (``class_label``: a
    ``"class:<name>"`` label or a bare class name), its number and its case,
    plus an adjective's ``degree_label`` suffix -- bare when the language has
    none of them. The suffixes are composed in the order degree, class,
    number, case."""
    grammar = language.grammar
    noun_cls = (class_label or "").removeprefix(noun_class_gen.CLASS_AGREEMENT_PREFIX) or None
    class_affix = next((a for a in grammar.class_affixes if a.label == noun_cls), None) if noun_cls else None
    degree_affix = next((a for a in grammar.degree_affixes if a.label == degree_label), None) if degree_label else None
    number_affix = next((a for a in grammar.number_affixes if a.label == number_label), None) if number_label else None
    case_affix = next((a for a in grammar.case_affixes if a.label == case_label), None) if case_label else None
    parts = [degree_affix, class_affix, number_affix, case_affix]
    if not any(parts):
        return entry.romanization, entry.ipa
    affix = InflectionAffix(
        label="adjective-agreement",
        prefix=tuple(sym for part in parts if part for sym in part.prefix),
        suffix=tuple(sym for part in parts if part for sym in part.suffix),
    )
    rng = _translation_rng(
        language,
        _class_agreement_salt(
            entry,
            noun_cls if class_affix is not None else None,
            degree_label if degree_affix is not None else None,
            number_label if number_affix is not None else None,
            case_label if case_affix is not None else None,
        ),
    )
    ipa = inflection_gen.apply_affix(rng, affix, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language))
    romanization = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), entry.pos)
    return romanization, ipa


_TRANSPARENT_KINDS = (
    "article", "indefinite_article", "specific_article", "demonstrative", "possessive_pronoun", "classifier", "copula",
    "negation", "conjunction",
)


def _is_transparent(slot) -> bool:
    """A slot an agreement search looks through on its way to the noun."""
    if slot.kind in _TRANSPARENT_KINDS:
        return True
    return slot.kind == "content" and (
        slot.pos in ("adjective", "adverb", "numeral", "quantifier", "preposition") or slot.possessive
    )


def _search_noun(slots, index: int, step: int) -> int | None:
    j = index + step
    while 0 <= j < len(slots):
        slot = slots[j]
        if slot.kind == "content" and slot.gloss and slot.pos in ("noun", "pronoun") and not slot.possessive:
            return j
        if not _is_transparent(slot):
            return None
        j += step
    return None


def _agreement_target(language: Language, slots, index: int, category: str) -> int | None:
    """The index of the noun slot the word at ``slots[index]`` agrees with,
    worked out from position (the planner need not name it): the next noun for
    an article, numeral or possessive, the next or previous one for a
    demonstrative and an adjective according to the language's own order, and
    the other side as a fallback (a predicate adjective sits across the
    copula from its subject)."""
    grammar = language.grammar
    after = (
        grammar.demonstrative_after_noun if category == "demonstrative"
        else grammar.adjective_after_noun if category == "adjective"
        else False
    )
    if category == "adjective" and grammar.adjective_placement == "split" and slots[index].gloss:
        after = np_followups_gen.adjective_class(slots[index].gloss) not in grammar.adjective_before_classes
    first, second = (-1, 1) if after else (1, -1)
    target = _search_noun(slots, index, first)
    if target is None and category in ("adjective", "demonstrative"):
        target = _search_noun(slots, index, second)
    return target


def _agreement_features(
    language: Language, slots, index: int, category: str, named_noun: str | None = None
) -> tuple[str | None, str | None, str | None]:
    """``(class label, number label, case label)`` the word at ``slots[index]``
    of ``category`` agrees in, for the categories the language has as
    agreement targets. ``named_noun`` is a noun the planner named
    (``agrees_with``); it decides the class but not the number or case."""
    grammar = language.grammar
    target = _agreement_target(language, slots, index, category)
    noun = slots[target] if target is not None else None
    class_label = None
    if grammar.noun_classes and category in grammar.class_agreement_targets:
        gloss = named_noun or (noun.gloss if noun is not None else None)
        class_label = _class_label_of(language, gloss)
    number_label = None
    if noun is not None and category in grammar.number_agreement_targets:
        effective = _effective_number(language, slots, target)
        if effective is not None and any(a.label == effective for a in grammar.number_affixes):
            number_label = effective
    case_label = None
    if noun is not None and category in grammar.case_agreement_targets:
        if noun.case in grammar.cases and any(a.label == noun.case for a in grammar.case_affixes):
            case_label = noun.case
    return class_label, number_label, case_label


def _agreement_options(grammar: GrammarProfile, category: str):
    """The class, number and case options (``None`` first) an agreeing word of
    ``category`` may carry."""
    class_options = [None] + ([a.label for a in grammar.class_affixes] if category in grammar.class_agreement_targets else [])
    number_options = [None] + ([a.label for a in grammar.number_affixes] if category in grammar.number_agreement_targets else [])
    case_options = [None] + ([a.label for a in grammar.case_affixes] if category in grammar.case_agreement_targets else [])
    return class_options, number_options, case_options


_FUNCTION_PARTICLES = frozenset({"the", "a", "not", "and", "of", "than", "as", "rel"})


def _agreement_category(entry: LexicalEntry) -> str | None:
    """The agreement category of a lexicon word (``None`` if it does not agree)."""
    if entry.pos is PartOfSpeech.ADJECTIVE:
        return "adjective"
    if entry.pos is PartOfSpeech.PARTICLE and "-" not in entry.primary_gloss and entry.primary_gloss not in _FUNCTION_PARTICLES:
        return "adverb"  # an adverb word: it only ever carries a degree suffix
    if entry.primary_gloss in ("this", "that", "this-article", "that-article"):
        return "demonstrative"
    if entry.primary_gloss == np_followups_gen.SPECIFIC_ARTICLE_GLOSS:
        return "article"
    if entry.primary_gloss.startswith(pronoun_gen.POSSESSIVE_GLOSS_PREFIX):
        return "possessive"
    if entry.pos is PartOfSpeech.NUMERAL:
        return "numeral"
    return None


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


def _takes_classifier(slot: sentence_planner.PlannedSlot, grammar: GrammarProfile) -> bool:
    """A numeral, a demonstrative or one of the language's classified
    quantifiers is followed by a classifier when a noun follows it."""
    if slot.kind == "demonstrative":
        return True
    if slot.kind != "content":
        return False
    if slot.pos == "numeral":
        return True
    return slot.pos == "quantifier" and slot.gloss.replace(" ", "-") in grammar.classified_quantifiers


def _following_noun_index(slots, index: int) -> int | None:
    """The index of the noun a numeral/demonstrative at ``slots[index]``
    quantifies: the first later noun slot, looking past adjectives, adverbs
    and further numerals only."""
    for j in range(index + 1, len(slots)):
        later = slots[j]
        if later.kind == "content" and later.pos == "noun" and later.gloss:
            return j
        if later.kind == "content" and later.pos in ("adjective", "adverb", "numeral", "quantifier"):
            continue
        return None
    return None


def _classifier_slot(
    language: Language, noun_gloss: str, categories: tuple[str, ...], possessive: bool = False
) -> PlannedSlot:
    """The synthetic classifier slot for the noun ``noun_gloss``: the noun
    itself when it is a repeater (numeral classifiers only), else a word from
    the language's lexical pool, else the classifier of its category."""
    grammar = language.grammar
    seed = language.spec.seed
    if not possessive and classifier_gen.is_repeater(seed, noun_gloss, grammar.repeater_rate):
        return PlannedSlot(kind="classifier", gloss=f"{classifier_gen.REPEATER_GLOSS_PREFIX}{noun_gloss.strip().lower()}")
    if grammar.classifier_assignment == "lexical" and grammar.classifier_pool_size:
        index = classifier_gen.lexical_index(seed, noun_gloss, grammar.classifier_pool_size)
        return PlannedSlot(kind="classifier", gloss=classifier_gen.lexical_gloss(index, possessive))
    category = classifier_gen.classifier_category(noun_gloss, categories)
    gloss = classifier_gen.possessive_classifier_gloss(category) if possessive else classifier_gen.classifier_gloss(category)
    return PlannedSlot(kind="classifier", gloss=gloss)


def _is_possessor_word(grammar: GrammarProfile, slot) -> bool:
    """A slot that renders as a word standing for the possessor (a possessive
    noun/pronoun/name, or a possessive pronoun that is a word, not a suffix)."""
    if slot.kind in ("content", "name"):
        return slot.possessive
    if slot.kind == "possessive_pronoun":
        if slot.gloss == "self":
            return grammar.reflexive_possessive == "word"
        return grammar.possessive_pronouns == "words"
    return False


def _with_classifiers(language: Language, slots) -> tuple:
    """The plan's slots with a synthetic ``"classifier"`` slot placed after
    each numeral (and, where the language says so, demonstrative) that
    quantifies a noun -- before the noun, or, in a noun-numeral-classifier
    language, the numeral and classifier moved behind the noun. A noun after a
    numeral above "one" loses its number (the numeral carries it)."""
    grammar = language.grammar
    if not grammar.uses_classifiers:
        return tuple(slots)
    categories = grammar.classifier_categories or classifier_gen.LEGACY_CATEGORIES
    deferred: set[int] = set()
    classified_nouns: set[int] = set()
    before_noun: dict[int, PlannedSlot] = {}
    after_trigger: dict[int, PlannedSlot] = {}
    after_noun: dict[int, list[PlannedSlot]] = {}
    replaced: dict[int, PlannedSlot] = {}
    for i, slot in enumerate(slots):
        if not _takes_classifier(slot, grammar):
            continue
        is_numeral = slot.kind == "content"
        if not is_numeral and not grammar.classifier_with_demonstrative:
            continue
        j = _following_noun_index(slots, i)
        if j is None:
            if slot.classifier_for:  # "two of them": the classifier stands in for the missing noun
                after_trigger[i] = _classifier_slot(language, slot.classifier_for, categories)
            continue
        classified_nouns.add(j)
        classifier_slot = _classifier_slot(language, slots[j].gloss, categories)
        if is_numeral and slot.gloss not in _NUMERAL_ONE:
            replaced[j] = dataclasses.replace(replaced.get(j, slots[j]), number=None)
        if is_numeral and grammar.classifier_after_noun:
            deferred.add(i)
            after_noun.setdefault(j, []).extend([slot, classifier_slot])
        else:
            after_trigger[i] = classifier_slot
    if grammar.possessive_classifiers:
        for i, slot in enumerate(slots):
            if not _is_possessor_word(grammar, slot):
                continue
            j = _following_noun_index(slots, i)
            if j is None:
                continue
            classified_nouns.add(j)
            after_trigger[i] = _classifier_slot(language, slots[j].gloss, categories, possessive=True)
    if grammar.classifier_with_adjective:
        for i, slot in enumerate(slots):
            if not _is_attributive_adjective(slot):
                continue
            right = i + 1
            while right < len(slots) and (_is_attributive_adjective(slots[right]) or slots[right].kind == "conjunction"):
                right += 1
            left = i - 1
            while left >= 0 and (_is_attributive_adjective(slots[left]) or slots[left].kind == "conjunction"):
                left -= 1
            if right < len(slots) and _is_np_head(slots[right]) and slots[right].pos == "noun":
                noun, before = right, True
            elif left >= 0 and _is_np_head(slots[left]) and slots[left].pos == "noun":
                noun, before = left, False
            else:
                continue
            if noun in classified_nouns:
                continue
            classified_nouns.add(noun)
            classifier_slot = _classifier_slot(language, slots[noun].gloss, categories)
            if before:
                before_noun[noun] = classifier_slot
            else:
                after_noun.setdefault(noun, []).append(classifier_slot)
    result: list[PlannedSlot] = []
    for i, slot in enumerate(slots):
        if i in deferred:
            continue
        if i in before_noun:
            result.append(before_noun[i])
        result.append(replaced.get(i, slot))
        if i in after_trigger:
            result.append(after_trigger[i])
        result.extend(after_noun.get(i, []))
    return tuple(result)


def _dropped_subject_pronouns(language: Language, slots) -> set[int]:
    """Indices of subject pronoun slots to omit (``pro_drop`` languages): for
    each finite verb/copula whose planned agreement names a person, the first
    pronoun slot of that person (preferring one marked as a subject case,
    else a bare one) -- the verb's own agreement suffix carries it."""
    dropped: set[int] = set()
    if not language.grammar.pro_drop:
        return dropped
    for slot in slots:
        is_finite = slot.kind == "copula" or (slot.kind == "content" and slot.pos == "verb")
        if not is_finite or slot.agreement not in pronoun_gen.PERSON_LABELS:
            continue
        candidates = [
            j
            for j, cand in enumerate(slots)
            if j not in dropped
            and cand.kind == "content"
            and cand.pos == "pronoun"
            and not cand.possessive
            and cand.case in (None, "nominative", "ergative")
            and pronoun_gen.person_label(cand.gloss) == slot.agreement
        ]
        subject_marked = [j for j in candidates if slots[j].case in ("nominative", "ergative")]
        chosen = (subject_marked or candidates or [None])[0]
        if chosen is not None:
            dropped.add(chosen)
    return dropped


def _normalize_possessives(language: Language, slots) -> tuple:
    """A ``possessive_pronoun`` slot in a language that has no special form
    for it is just the personal pronoun as a possessor: everywhere for
    ``regular`` possessive pronouns, and for ``self`` ("his own") when the
    language has no reflexive possessive (it then reads as ``he``)."""
    grammar = language.grammar
    normalized = []
    for slot in slots:
        if slot.kind == "possessive_pronoun":
            own = slot.gloss == "self"
            partial = (
                not own and grammar.possessive_pronouns == "words" and bool(grammar.possessive_word_persons)
                and pronoun_gen.person_label(slot.gloss) not in grammar.possessive_word_persons
            )
            if (own and grammar.reflexive_possessive == "none") or (
                not own and grammar.possessive_pronouns == "regular"
            ) or partial:
                slot = dataclasses.replace(
                    slot, kind="content", pos="pronoun", possessive=True, gloss="he" if own else slot.gloss
                )
        normalized.append(slot)
    return tuple(normalized)


_NP_MODIFIER_KINDS = (
    "article", "indefinite_article", "specific_article", "demonstrative", "possessive_pronoun", "classifier",
)


def _is_np_head(slot) -> bool:
    if slot.possessive or not slot.gloss:
        return False
    return (slot.kind == "content" and slot.pos in ("noun", "pronoun")) or slot.kind == "name"


def _is_np_modifier(slot) -> bool:
    if slot.kind in _NP_MODIFIER_KINDS:
        return True
    if slot.kind in ("content", "name") and slot.possessive:
        return True
    return slot.kind == "content" and slot.pos in ("adjective", "numeral", "quantifier")


def _np_extent(language: Language, slots, adposition_index: int, forward: bool):
    """``(first, last, head)`` of the noun phrase directly after (``forward``) or
    before an adposition, or ``None``."""
    head = None
    if forward:
        first, last, j = adposition_index + 1, None, adposition_index + 1
        while j < len(slots):
            slot = slots[j]
            if head is None:
                if _is_np_head(slot):
                    head = last = j
                elif not _is_np_modifier(slot):
                    break
            elif (
                slot.kind == "content" and slot.pos == "adjective" and language.grammar.adjective_after_noun
            ):
                last = j
            else:
                break
            j += 1
        return (first, last, head) if head is not None else None
    last, first, j = adposition_index - 1, None, adposition_index - 1
    while j >= 0:
        slot = slots[j]
        if head is None:
            if _is_np_head(slot):
                head = first = j
            elif _is_np_modifier(slot):
                first = j
            else:
                break
        elif _is_np_modifier(slot):
            first = j
        else:
            break
        j -= 1
    return (first, last, head) if head is not None else None


def _is_attributive_adjective(slot) -> bool:
    return slot.kind == "content" and slot.pos == "adjective" and bool(slot.gloss)


def _reduced_demonstrative(
    language: Language, entry: LexicalEntry, coined: list[LexicalEntry]
) -> tuple[Language, LexicalEntry]:
    """The clitic form of a demonstrative (``this-article``: onset and first
    vowel), made on first use; the full word when nothing shorter exists."""
    gloss = f"{entry.primary_gloss}-article"
    existing = language.lexicon.by_gloss(gloss)
    if existing is not None:
        return language, existing
    ipa = np_followups_gen.derive_article_ipa(entry.ipa, language.phonology)
    if ipa is None:
        return language, entry
    spelled = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), PartOfSpeech.PARTICLE)
    if language.lexicon.by_form(spelled) is not None:
        return language, entry
    reduced = entry.model_copy(
        update={"ipa": ipa, "romanization": spelled, "glosses": (gloss,), "tones": tuple(entry.tones[:1])}
    )
    coined.append(reduced)
    return language.with_new_words((reduced,), reason=f"reduced '{entry.primary_gloss}' to '{spelled}'"), reduced


def _double_definiteness(language: Language, slots) -> tuple:
    """In a language that doubles definiteness, a demonstrative also brings the
    definite article ("the this dog") -- placed before the phrase."""
    grammar = language.grammar
    if not (grammar.demonstrative_doubling and grammar.has_articles):
        return tuple(slots)
    article_kinds = ("article", "indefinite_article", "specific_article")
    inserts: list[int] = []
    for index, slot in enumerate(slots):
        if slot.kind != "demonstrative":
            continue
        head = _agreement_target(language, slots, index, "demonstrative")
        if head is None:
            continue
        start = min(index, head)
        if start > 0 and slots[start - 1].kind in article_kinds:
            continue
        inserts.append(start)
    out = list(slots)
    for position in sorted(set(inserts), reverse=True):
        out.insert(position, PlannedSlot(kind="article"))
    return tuple(out)


def _arrange_adjectives(language: Language, slots) -> tuple:
    """Puts the adjectives around each noun where this language has them: on
    their class's side in a ``split`` language, in the class order of
    ``adjective_stack_order`` (mirrored after the noun) when stacked, and
    joined by "and" when the language links them. A language with none of
    these keeps the planner's arrangement. An adjective directly after a noun
    in a sentence with no verb is a predicate ("the dog big"), so a split
    language leaves it be."""
    grammar = language.grammar
    if grammar.adjective_placement == "global" and not grammar.adjective_stack_order and not grammar.adjective_stack_linker:
        return tuple(slots)
    has_finite = any(s.kind == "copula" or (s.kind == "content" and s.pos == "verb") for s in slots)
    out = list(slots)
    i = 0
    while i < len(out):
        if not _is_np_head(out[i]) or out[i].kind == "name":
            i += 1
            continue
        left = i
        while left > 0:
            if _is_attributive_adjective(out[left - 1]):
                left -= 1
            elif out[left - 1].kind == "conjunction" and left >= 2 and _is_attributive_adjective(out[left - 2]):
                left -= 2  # "big and red dog": the planner's own "and" is re-decided below
            else:
                break
        right = i
        while right + 1 < len(out):
            if _is_attributive_adjective(out[right + 1]):
                right += 1
            elif (
                out[right + 1].kind == "conjunction" and right + 2 < len(out)
                and _is_attributive_adjective(out[right + 2])
            ):
                right += 2
            else:
                break
        adjectives = [a for a in out[left:i] + out[i + 1:right + 1] if a.kind == "content"]
        if not adjectives:
            i += 1
            continue
        split = grammar.adjective_placement == "split"
        if split and not has_finite and right > i and left == i:
            i = right + 1
            continue
        order = grammar.adjective_stack_order
        rank = (lambda a: order.index(np_followups_gen.adjective_class(a.gloss))) if order else (lambda a: 0)
        if split:
            before = [a for a in adjectives if np_followups_gen.adjective_class(a.gloss) in grammar.adjective_before_classes]
            after = [a for a in adjectives if a not in before]
        elif grammar.adjective_after_noun:
            before, after = [], list(adjectives)
        else:
            before, after = list(adjectives), []
        before = sorted(before, key=rank)
        after = sorted(after, key=rank, reverse=bool(order))

        def linked(group):
            joined: list = []
            for position, adjective in enumerate(group):
                if position and grammar.adjective_stack_linker:
                    joined.append(PlannedSlot(kind="conjunction"))
                joined.append(adjective)
            return joined

        rebuilt = linked(before) + [out[i]] + linked(after)
        out[left:right + 1] = rebuilt
        i = left + len(rebuilt)
    return tuple(out)


def _arrange_adpositions(language: Language, slots) -> tuple:
    """Puts each adposition on the language's own side of its noun phrase
    whatever the planner wrote, makes it govern the case it corresponds to
    (``adposition_case_strategy``) and, where a locative/instrumental case (or the
    instrumental passive agent) stands in for it, drops the adposition and case-marks
    the noun instead."""
    grammar = language.grammar
    out = list(slots)
    i = 0
    while i < len(out):
        slot = out[i]
        if not (slot.kind == "content" and slot.pos == "preposition" and slot.gloss):
            i += 1
            continue
        gloss = slot.gloss.strip().lower()
        if gloss in ("than", "as"):
            i += 1
            continue
        forward = not grammar.postpositional
        extent = _np_extent(language, out, i, forward)
        if extent is None:
            forward = not forward
            extent = _np_extent(language, out, i, forward)
        if extent is None:
            i += 1
            continue
        first, last, head = extent
        if gloss == "of" and grammar.drop_measure_of:
            measure_at = i - 1 if forward else first - 1
            if (
                0 <= measure_at < len(out) and _is_np_head(out[measure_at])
                and out[measure_at].gloss.strip().lower() in voice_np_gen.MEASURE_NOUNS
            ):
                out.pop(i)  # "a cup of water": the measure noun and the mass noun sit side by side
                continue
        target = voice_np_gen.ADPOSITION_CASES.get(gloss)
        if target is not None and target not in grammar.cases:
            fallback = voice_np_gen.FALLBACK_CASES.get(gloss)
            if fallback in grammar.cases:
                target = fallback
        drop = govern = False
        if target is not None and target in grammar.cases:
            agent_case = gloss == "by" and grammar.passive_agent == "case"
            drop = target in voice_np_gen.REPLACEABLE_CASES and (
                grammar.adposition_case_strategy == "case_only" or agent_case
            )
            govern = drop or grammar.adposition_case_strategy in ("governs", "case_only")
        if govern and out[head].case is None:
            out[head] = dataclasses.replace(out[head], case=target)
        out.pop(i)
        if forward:
            first, last = first - 1, last - 1
        if drop:
            continue
        insert_at = last + 1 if grammar.postpositional else first
        out.insert(insert_at, slot)
        i = max(i, insert_at) + 1
    return tuple(out)


def _unmarked_possessors(language: Language, slots) -> set[int]:
    """Indices of possessor slots whose possession is inalienable (body parts,
    kin) in a language that leaves those unmarked."""
    if not language.grammar.inalienable_possession:
        return set()
    found: set[int] = set()
    for index, slot in enumerate(slots):
        if not (slot.possessive and slot.kind in ("content", "name")):
            continue
        head = next((later for later in slots[index + 1:] if _is_np_head(later)), None)
        if head is not None and voice_np_gen.is_inalienable(head.gloss):
            found.add(index)
    return found


def _suppletive_form_kind(language: Language, slots, index: int, pos: PartOfSpeech) -> str | None:
    """``"plural"``/``"comparative"``/``"superlative"`` when this noun or
    adjective slot needs its language's separate irregular word."""
    grammar = language.grammar
    slot = slots[index]
    gloss = (slot.gloss or "").strip().lower()
    if pos is PartOfSpeech.NOUN and gloss in grammar.suppletive_plurals:
        return "plural" if _effective_number(language, slots, index) == "plural" else None
    if pos is PartOfSpeech.ADJECTIVE and slot.degree in ("comparative", "superlative") and gloss in grammar.suppletive_degrees:
        return slot.degree
    return None


def _suppletive_case(language: Language, slot, pos: PartOfSpeech, possession: str, possessive_marked: bool = True) -> str | None:
    """The case whose suppletive pronoun word (I -> me) this pronoun slot needs,
    or ``None`` (a regular pronoun, or a person without suppletive forms)."""
    grammar = language.grammar
    if pos is not PartOfSpeech.PRONOUN or not grammar.suppletive_pronoun_persons:
        return None
    case = "genitive" if slot.possessive and possessive_marked and possession == "genitive" else slot.case
    if case is None or case not in grammar.cases or case in ("nominative", "absolutive"):
        return None
    person = pronoun_gen.person_label(slot.gloss)
    if person not in grammar.suppletive_pronoun_persons:
        return None
    limited = dict(grammar.suppletive_pronoun_case_limits).get(person)
    if limited is not None and case not in limited:
        return None  # this case of this person is regular: the ordinary case suffix
    return case


def _dropped_object_pronouns(language: Language, slots, already: set[int]) -> set[int]:
    """Indices of object pronoun slots to omit (``object_pro_drop``
    languages): for each finite verb whose object is a personal pronoun the
    verb's object agreement names, the accusative-marked pronoun slot of that
    person (else the last bare one) -- a subject pronoun is never taken."""
    dropped: set[int] = set()
    grammar = language.grammar
    if not grammar.object_pro_drop:
        return dropped
    object_labels = {a.label for a in grammar.object_agreement_affixes}
    for slot in slots:
        if slot.kind != "content" or slot.pos != "verb" or not slot.object_gloss:
            continue
        label = pronoun_gen.person_label(slot.object_gloss)
        if label is None or label not in object_labels:
            continue
        candidates = [
            j
            for j, cand in enumerate(slots)
            if j not in already
            and j not in dropped
            and cand.kind == "content"
            and cand.pos == "pronoun"
            and not cand.possessive
            and cand.case not in ("nominative", "ergative")
            and pronoun_gen.person_label(cand.gloss) == label
        ]
        accusative = [j for j in candidates if slots[j].case in ("accusative", "dative")]
        chosen = accusative[0] if accusative else (candidates[-1] if candidates else None)
        if chosen is not None:
            dropped.add(chosen)
    return dropped


def _linker_follows_clause(language: Language, role: str | None = None) -> bool:
    """Whether a subordinating word ("that", "because", "who") goes after its
    clause. A relative clause's word follows a clause that precedes its noun
    and leads one that follows it (a correlative's always leads); any other
    clause follows the language's rolled ``subordinator_position``. A language
    saved before that field existed keeps the earlier rule: after the clause in
    a verb-final language, before it otherwise."""
    grammar = language.grammar
    if role == "coordinate":
        return False
    if role == "relative":
        if grammar.relativization == "correlative":
            return False
        return grammar.relative_clause_position == "before_noun"
    if grammar.subordinator_position:
        return grammar.subordinator_position == "after"
    return grammar.word_order.value in ("SOV", "OSV")


def _linker_gloss(language: Language, slot, governor: str | None = None) -> str:
    """The gloss of the word that introduces the clause in ``slot``. A
    relative clause follows the language's own strategy: no word for a gap
    (unless the relativized position is beyond what the gap reaches, when it
    takes the invariant word plus a resumptive pronoun), one invariant word for
    a particle or resumptive clause, a relative pronoun -- declined by the case
    of its function and the number of its head where the language does that --
    otherwise. A complement clause's complementizer follows the class of its
    governing verb where the language does that. A coordination is a word only
    in a language that coordinates clauses with one."""
    grammar = language.grammar
    if slot.role == "relative":
        strategy = grammar.relativization
        function = slot.rel_function or "subject"
        if strategy == "gap":
            if subordination_gen.beyond_reach(grammar.relativization_reach, function):
                return subordination_gen.RELATIVE_PARTICLE_GLOSS
            return ""
        if strategy in ("particle", "resumptive"):
            return subordination_gen.RELATIVE_PARTICLE_GLOSS
        if strategy == "particle" or strategy == "pronoun" or strategy == "correlative":
            base = slot.gloss if slot.gloss in ("who", "which") else (
                "which" if strategy == "correlative" else subordination_gen.DEFAULT_RELATIVE_PRONOUN
            )
            return subordination_gen.relative_pronoun_gloss(
                base, function, slot.number == "plural", grammar.relative_pronoun_declines,
                grammar.relative_pronoun_number, grammar.cases,
            )
    if slot.role == "complement" and slot.gloss and grammar.complementizer_by_verb and governor:
        complement_class = subordination_gen.complement_class(governor)
        if complement_class:
            return f"{slot.gloss}-{complement_class}"
    if slot.role == "coordinate":
        return (slot.gloss or "and") if grammar.clause_coordination == "word" else ""
    return slot.gloss


def _governing_verb(slots, index: int) -> str | None:
    """The lemma of the closest finite verb before ``slots[index]`` (the verb
    a complement clause completes)."""
    for earlier in reversed(slots[:index]):
        if earlier.kind == "content" and earlier.pos == "verb" and earlier.gloss:
            return earlier.gloss
    return None


def _annotate_relative_heads(slots) -> tuple:
    """Gives each relative clause slot the number of its head noun (the slot
    just before it), so a declining relative pronoun can agree with it."""
    out = list(slots)
    for i in range(1, len(out)):
        clause = out[i]
        head = out[i - 1]
        if clause.kind == "clause" and clause.role == "relative" and head.kind == "content" and head.pos in ("noun", "pronoun"):
            out[i] = dataclasses.replace(clause, number=head.number)
    return tuple(out)


def _arrange_coordination(language: Language, slots) -> tuple:
    """In a language that joins clauses with a medial verb, turns the last
    finite verb before a coordinate clause into that converb form."""
    grammar = language.grammar
    if grammar.clause_coordination != "converb" or "converb" not in grammar.verb_forms:
        return tuple(slots)
    out = list(slots)
    for i, slot in enumerate(out):
        if slot.kind == "clause" and slot.role == "coordinate":
            for j in range(i - 1, -1, -1):
                if out[j].kind == "content" and out[j].pos == "verb":
                    out[j] = dataclasses.replace(out[j], verb_form="converb")
                    break
    return tuple(out)


def _arrange_correlative_adverbials(language: Language, slots) -> tuple:
    """In a language with correlative adverbials, moves each "if"/"when"/
    "the more" clause to the front and starts the main clause with its
    correlate ("then")."""
    if not language.grammar.correlative_adverbials:
        return tuple(slots)
    out = list(slots)
    front: list[PlannedSlot] = []
    correlates: list[PlannedSlot] = []
    for i in range(len(out) - 1, -1, -1):
        slot = out[i]
        if slot.kind != "clause" or slot.role != "adverbial" or i == 0:
            continue
        key = slot.gloss.strip().lower().replace(" ", "-")
        if key not in subordination_gen.CORRELATIVE_LINKERS:
            continue
        out.pop(i)
        front.insert(0, slot)
        correlates.append(PlannedSlot(kind="content", gloss=subordination_gen.CORRELATE_GLOSS[key], pos="adverb"))
    if not front:
        return tuple(slots)
    return tuple(front + correlates[:1] + out)


def _reduce_conjunct(main_slots, clause) -> sentence_planner.SentencePlan:
    """Conjunction reduction: the second conjunct drops a subject pronoun that
    repeats the first clause's own subject pronoun."""
    first = next((s for s in main_slots if s.kind == "content" and s.pos == "pronoun" and not s.possessive), None)
    if first is None or clause is None:
        return clause
    out = list(clause.slots)
    for i, s in enumerate(out):
        if s.kind == "content" and s.pos == "pronoun" and not s.possessive and s.gloss.lower() == first.gloss.lower():
            del out[i]
            break
    return sentence_planner.SentencePlan(slots=tuple(out), mood=clause.mood)


def _subordinate_mood(language: Language, slot, linker_gloss: str) -> str | None:
    """The verbal mood forced on the verbs of an "if"/"unless"/"so that"
    clause in a language whose subordinate clauses take the subjunctive or
    irrealis (``None`` otherwise, or when the language has no such mood)."""
    grammar = language.grammar
    if not grammar.subordinate_mood_use or slot.role != "adverbial":
        return None
    if linker_gloss.strip().lower().replace(" ", "-") not in subordination_gen.IRREALIS_LINKERS:
        return None
    return next((m for m in ("subjunctive", "irrealis", "conditional") if m in grammar.moods), None)


def _main_clause_mood(language: Language, slots) -> str | None:
    """In a language whose "if" sentences put the main clause in the
    conditional, the mood its finite verbs take when a sentence has an "if" or
    "unless" clause (``None`` otherwise, or without such a mood)."""
    grammar = language.grammar
    if not grammar.conditional_main_mood:
        return None
    has_conditional = any(
        s.kind == "clause" and s.role == "adverbial" and s.gloss.strip().lower() in ("if", "unless") for s in slots
    )
    if not has_conditional:
        return None
    return next((m for m in ("conditional", "irrealis", "subjunctive") if m in grammar.moods), None)


def _subordinate_tense(language: Language, slot, linker_gloss: str) -> str | None:
    """The tense forced on the verbs of an "if"/"unless" clause in a language
    with ``conditional_clause_tense`` (only if it has that tense)."""
    grammar = language.grammar
    if not grammar.conditional_clause_tense or slot.role != "adverbial":
        return None
    if linker_gloss.strip().lower() not in ("if", "unless"):
        return None
    return grammar.conditional_clause_tense if grammar.conditional_clause_tense in grammar.tenses else None


def _np_start(slots, head: int) -> int:
    """The index where the noun phrase headed by ``slots[head]`` begins:
    walking back over its determiners, numerals, adjectives and possessors."""
    k = head
    while k > 0:
        previous = slots[k - 1]
        modifier = (
            previous.kind in (
                "article", "indefinite_article", "specific_article", "demonstrative", "possessive_pronoun", "classifier"
            )
            or (previous.kind == "content" and (previous.possessive or previous.pos in ("adjective", "numeral", "quantifier", "adverb")))
        )
        if not modifier:
            break
        k -= 1
    return k


def _arrange_relatives(language: Language, slots) -> tuple:
    """Moves each relative-clause slot (which the planner writes right after
    its noun) where the language puts it: unchanged after the noun; before the
    whole noun phrase in a ``before_noun`` language; at the front of the plan,
    with the correlate "that" added before the noun in the main clause, in a
    ``correlative`` language."""
    grammar = language.grammar
    correlative = grammar.relativization == "correlative"
    if grammar.relative_clause_position == "after_noun" and not correlative:
        return tuple(slots)
    out = list(slots)
    front: list[PlannedSlot] = []
    for i in range(len(out) - 1, -1, -1):
        clause = out[i]
        if clause.kind != "clause" or clause.role != "relative" or i == 0:
            continue
        head = i - 1
        if out[head].kind not in ("content", "name") or (out[head].kind == "content" and out[head].pos not in ("noun", "pronoun")):
            continue
        start = _np_start(out, head)
        out.pop(i)
        if correlative:
            out.insert(start, PlannedSlot(kind="demonstrative", gloss="that"))
            front.insert(0, clause)
        else:
            out.insert(start, clause)
    return tuple(front + out)


def _render_plan(
    plan: sentence_planner.SentencePlan,
    language: Language,
    llm_client: LLMClient,
    coined: list[LexicalEntry],
    forced_verb_mood: str | None = None,
    forced_verb_tense: str | None = None,
    forced_nominal_case: str | None = None,
) -> tuple[Language, list[str], list[str], list[str | None]]:
    working_language = language
    romanization_parts: list[str] = []
    ipa_parts: list[str] = []
    gloss_parts: list[str | None] = []
    mood_pending = plan.mood == "imperative"
    possessed_pending = False  # a possessor was rendered; the next noun takes the "possessed" affix
    possession = language.grammar.possession
    slots = _annotate_relative_heads(
        _double_definiteness(language, _arrange_adpositions(language, _arrange_adjectives(language, plan.slots)))
    )
    slots = _arrange_coordination(language, slots)
    slots = _arrange_relatives(language, slots)
    slots = _arrange_correlative_adverbials(language, slots)
    slots = _with_classifiers(language, _normalize_possessives(language, slots))
    main_mood = _main_clause_mood(language, slots)
    dropped_pronouns = _dropped_subject_pronouns(language, slots)
    dropped_pronouns = dropped_pronouns | _dropped_object_pronouns(language, slots, dropped_pronouns)
    negative_verbs, prohibitive_verbs, dropped_negations = _negation_absorption(
        language, slots, plan.mood == "imperative"
    )
    unmarked_possessors = _unmarked_possessors(language, slots)
    possessor_person_pending: str | None = None  # an affix-strategy possessor waiting for its noun
    for slot_index, slot in enumerate(slots):
        rendered: tuple[str, str] | None = None
        entry: LexicalEntry | None = None
        aux_entries: list[LexicalEntry] = []
        if slot_index in dropped_pronouns or slot_index in dropped_negations:
            continue
        marks_possession = slot.possessive and slot_index not in unmarked_possessors
        if slot.kind == "clause":
            if slot.clause is None:
                continue
            linker_gloss = _linker_gloss(working_language, slot, _governing_verb(slots, slot_index))
            nested_mood = _subordinate_mood(working_language, slot, linker_gloss)
            nested_tense = _subordinate_tense(working_language, slot, linker_gloss)
            nested_case = slot.case if slot.role == "nominal" and working_language.grammar.nominalized_takes_case else None
            nested_plan = slot.clause
            if slot.role == "coordinate" and working_language.grammar.conjunct_reduction:
                nested_plan = _reduce_conjunct(slots[:slot_index], slot.clause)
            working_language, nested_rom, nested_ipa, nested_gloss = _render_plan(
                nested_plan, working_language, llm_client, coined, nested_mood, nested_tense, nested_case
            )
            linker: tuple[str, str, str | None] | None = None
            if linker_gloss:
                working_language, linker_entry = _lookup_or_coin(
                    working_language, linker_gloss, PartOfSpeech.PARTICLE, coined, llm_client,
                    lemma_candidates=[linker_gloss],
                )
                linker = (linker_entry.romanization, linker_entry.ipa, linker_entry.primary_gloss)
            if linker is not None and _linker_follows_clause(working_language, slot.role):
                nested_rom, nested_ipa, nested_gloss = nested_rom + [linker[0]], nested_ipa + [linker[1]], nested_gloss + [linker[2]]
            elif linker is not None:
                nested_rom, nested_ipa, nested_gloss = [linker[0]] + nested_rom, [linker[1]] + nested_ipa, [linker[2]] + nested_gloss
            romanization_parts.extend(nested_rom)
            ipa_parts.extend(nested_ipa)
            gloss_parts.extend(nested_gloss)
            continue
        if slot.kind == "content" and slot.gloss:
            pos = sentence_planner.POS_BY_PLAN_STRING.get(slot.pos, PartOfSpeech.NOUN)
            suppletive_case = _suppletive_case(working_language, slot, pos, possession, marks_possession)
            lookup_gloss = pronoun_gen.suppletive_gloss(slot.gloss, suppletive_case) if suppletive_case else slot.gloss
            form_kind = _suppletive_form_kind(working_language, slots, slot_index, pos)
            if form_kind:
                lookup_gloss = voice_np_gen.suppletive_gloss(slot.gloss.strip().lower(), form_kind)
            working_language, entry = _lookup_or_coin(
                working_language, lookup_gloss, pos, coined, llm_client, lemma_candidates=[lookup_gloss]
            )
            if suppletive_case:
                rendered = (entry.romanization, entry.ipa)  # the case form is a word of its own
            elif pos is PartOfSpeech.VERB:
                agreement_label, object_label = _verb_agreement(working_language, slot)
                tense_in = slot.tense or forced_verb_tense
                aspect_in = slot.aspect
                mood_in = slot.verb_mood or forced_verb_mood or main_mood
                if not mood_pending and slot.verb_form not in working_language.grammar.verb_forms:
                    tense_in, aspect_in, mood_in, aux_labels = _split_periphrastic(
                        working_language, tense_in, aspect_in, mood_in
                    )
                    working_language, aux_entries = _auxiliary_entries(working_language, aux_labels, coined, llm_client)
                past_base = (slot.gloss or "").strip().lower()
                if (
                    tense_in == "past" and not mood_pending and past_base in working_language.grammar.suppletive_past
                    and slot.verb_form not in working_language.grammar.verb_forms
                ):
                    past_gloss = voice_np_gen.suppletive_gloss(past_base, "past")
                    working_language, entry = _lookup_or_coin(
                        working_language, past_gloss, PartOfSpeech.VERB, coined, llm_client, lemma_candidates=[past_gloss]
                    )
                    tense_in = None  # the past word carries the tense itself
                rendered = _apply_verb_inflection(
                    working_language, entry, tense_in, agreement_label,
                    "imperative" if mood_pending else "declarative",
                    aspect_in, mood_in, object_label, slot.voice,
                    slot.subject_number, slot.polite, slot.verb_form, forced_nominal_case,
                    slot.evidential, slot_index in negative_verbs, slot_index in prohibitive_verbs,
                )
                mood_pending = False
            elif pos is PartOfSpeech.ADJECTIVE and (
                (slot.degree and not form_kind)
                or any(_agreement_features(working_language, slots, slot_index, "adjective", slot.agrees_with))
            ):
                features = _agreement_features(working_language, slots, slot_index, "adjective", slot.agrees_with)
                degree_in = None if form_kind else slot.degree
                rendered = _apply_class_agreement(working_language, entry, features[0], degree_in, features[1], features[2])
            elif (
                slot.pos == "adverb" and slot.degree and working_language.grammar.adverb_degree
                and any(a.label == slot.degree for a in working_language.grammar.degree_affixes)
            ):
                rendered = _apply_class_agreement(working_language, entry, None, slot.degree)
            elif (
                pos is PartOfSpeech.NUMERAL
                and slot.pos == "numeral"
                and any(_agreement_features(working_language, slots, slot_index, "numeral"))
            ):
                features = _agreement_features(working_language, slots, slot_index, "numeral")
                rendered = _apply_class_agreement(working_language, entry, features[0], None, features[1], features[2])
            else:
                is_noun = pos is PartOfSpeech.NOUN
                rendered = _apply_case(
                    working_language,
                    entry,
                    "genitive" if marks_possession and possession == "genitive" else slot.case,
                    None if form_kind == "plural" else (
                        _effective_number(working_language, slots, slot_index) if is_noun else None
                    ),
                    possessed_pending and is_noun,
                    possessor_person_pending if is_noun else None,
                )
                if is_noun:
                    possessed_pending = False
                    possessor_person_pending = None
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
                    working_language, entry, "genitive" if marks_possession and possession == "genitive" else slot.case
                )
            )
        elif slot.kind == "copula":
            entry = working_language.lexicon.by_gloss("be")
            if entry is not None:
                agreement_label, object_label = _verb_agreement(working_language, slot)
                tense_in, aspect_in, mood_in = slot.tense, slot.aspect, slot.verb_mood
                if not mood_pending:
                    tense_in, aspect_in, mood_in, aux_labels = _split_periphrastic(
                        working_language, tense_in, aspect_in, mood_in
                    )
                    working_language, aux_entries = _auxiliary_entries(working_language, aux_labels, coined, llm_client)
                rendered = _apply_verb_inflection(
                    working_language, entry, tense_in, agreement_label,
                    "imperative" if mood_pending else "declarative",
                    aspect_in, mood_in, object_label, None, slot.subject_number, slot.polite,
                    evidential=slot.evidential, negative=slot_index in negative_verbs,
                    prohibitive=slot_index in prohibitive_verbs,
                )
                mood_pending = False
        elif slot.kind == "demonstrative":
            working_language, entry = _lookup_or_coin(
                working_language, slot.gloss or "this", PartOfSpeech.PRONOUN, coined, llm_client,
                lemma_candidates=[slot.gloss or "this"],
            )
            if working_language.grammar.deictic_articles and _agreement_target(
                working_language, slots, slot_index, "demonstrative"
            ) is not None:
                working_language, entry = _reduced_demonstrative(working_language, entry, coined)
            rendered = (entry.romanization, entry.ipa)
            features = _agreement_features(working_language, slots, slot_index, "demonstrative")
            if any(features):
                rendered = _apply_class_agreement(working_language, entry, features[0], None, features[1], features[2])
        elif slot.kind == "indefinite_article":
            if not working_language.grammar.has_indefinite_article:
                continue
            working_language, entry = _lookup_or_coin(
                working_language, "a", PartOfSpeech.PARTICLE, coined, llm_client, lemma_candidates=["a"]
            )
            rendered = (entry.romanization, entry.ipa)
            features = _agreement_features(working_language, slots, slot_index, "article")
            if any(features):
                rendered = _apply_class_agreement(working_language, entry, features[0], None, features[1], features[2])
        elif slot.kind == "specific_article":
            specific = working_language.grammar.has_specific_article
            if not specific and not working_language.grammar.has_indefinite_article:
                continue
            article_gloss = np_followups_gen.SPECIFIC_ARTICLE_GLOSS if specific else "a"
            working_language, entry = _lookup_or_coin(
                working_language, article_gloss, PartOfSpeech.PARTICLE, coined, llm_client,
                lemma_candidates=[article_gloss],
            )
            rendered = (entry.romanization, entry.ipa)
            features = _agreement_features(working_language, slots, slot_index, "article")
            if specific and any(features):
                rendered = _apply_class_agreement(working_language, entry, features[0], None, features[1], features[2])
        elif slot.kind == "possessive_pronoun":
            if slot.gloss == "self":
                if working_language.grammar.reflexive_possessive == "affix":
                    possessor_person_pending = "self"
                    continue
            elif working_language.grammar.possessive_pronouns == "affix":
                possessor_person_pending = pronoun_gen.person_label(slot.gloss)
                continue
            possessive_word = pronoun_gen.possessive_gloss(slot.gloss or "I")
            working_language, entry = _lookup_or_coin(
                working_language, possessive_word, PartOfSpeech.PRONOUN, coined, llm_client,
                lemma_candidates=[possessive_word],
            )
            rendered = (entry.romanization, entry.ipa)
            features = _agreement_features(working_language, slots, slot_index, "possessive")
            if any(features):
                rendered = _apply_class_agreement(working_language, entry, features[0], None, features[1], features[2])
        elif slot.kind == "classifier":
            if slot.gloss.startswith(classifier_gen.REPEATER_GLOSS_PREFIX):
                repeated = slot.gloss[len(classifier_gen.REPEATER_GLOSS_PREFIX):]
                working_language, entry = _lookup_or_coin(
                    working_language, repeated, PartOfSpeech.NOUN, coined, llm_client, lemma_candidates=[repeated]
                )
            else:
                working_language, entry = _lookup_or_coin(
                    working_language, slot.gloss, PartOfSpeech.PARTICLE, coined, llm_client,
                    lemma_candidates=[slot.gloss],
                )
            rendered = (entry.romanization, entry.ipa)
        elif slot.kind in _BARE_GLOSS_BY_SLOT_KIND:
            entry = working_language.lexicon.by_gloss(_BARE_GLOSS_BY_SLOT_KIND[slot.kind])
            if entry is not None:
                rendered = (entry.romanization, entry.ipa)
                if slot.kind == "article":
                    features = _agreement_features(working_language, slots, slot_index, "article")
                    if any(features):
                        rendered = _apply_class_agreement(
                            working_language, entry, features[0], None, features[1], features[2]
                        )

        if rendered is not None:
            before = working_language.grammar.auxiliary_position == "before"
            for aux_entry in aux_entries if before else ():
                romanization_parts.append(aux_entry.romanization)
                ipa_parts.append(aux_entry.ipa)
                gloss_parts.append(aux_entry.primary_gloss)
            romanization_parts.append(rendered[0])
            ipa_parts.append(rendered[1])
            gloss_parts.append(entry.primary_gloss if entry is not None else None)
            for aux_entry in () if before else aux_entries:
                romanization_parts.append(aux_entry.romanization)
                ipa_parts.append(aux_entry.ipa)
                gloss_parts.append(aux_entry.primary_gloss)
            if marks_possession and slot.kind in ("content", "name"):
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
    """Reverse of ``_apply_case``: returns ``(entry, label)`` for a noun-
    position conlang token -- ``"unmarked"`` for a bare/uninflected match (the
    common case), else the marking joined by ``+`` (``"accusative"``,
    ``"plural"``, ``"accusative+plural"``, ``"possessed"``, ``"poss:I"``...).
    Decoding is generate-and-compare, not a parse: since spelling isn't a
    clean invertible function in general (the same reason ``sound_change.py``'s
    own reform-detection compares via ``apply()`` rather than string
    surgery), this renders each real noun entry through ``_apply_case`` --
    which also adds the noun's own class marker in a language that has one --
    and compares it with the observed token. ``None`` when nothing matches."""
    normalized = _normalize(token)
    grammar = language.grammar
    # A subject/object argument may be a real noun or a pronoun -- both fill
    # the same syntactic slot.
    noun_entries = [e for e in language.lexicon.entries if e.pos in (PartOfSpeech.NOUN, PartOfSpeech.PRONOUN)]
    # With suffixes only, an inflected noun keeps its first two letters, so only
    # the nouns that start like the token can spell it (a prefix marker changes the start).
    other_prefixes = any(
        a.prefix for name in inflection_gen._NOUN_SUFFIX_FIELDS if name != "class_marker_affixes"
        for a in getattr(grammar, name)
    )
    if not other_prefixes:
        prefix = _stem_prefix(token)
        if any(a.prefix for a in grammar.class_marker_affixes):
            # A class prefix is the only thing that changes the start: compare with the marked bare form.
            noun_entries = [
                e for e in noun_entries if _stem_prefix(_apply_case(language, e, None, None)[0]) == prefix
            ]
        else:
            noun_entries = [e for e in noun_entries if _stem_prefix(e.romanization) == prefix]

    def spells(entry, case, number, possessed=False, person=None) -> bool:
        return _normalize(_apply_case(language, entry, case, number, possessed, person)[0]) == normalized

    for entry in noun_entries:
        if spells(entry, None, None):
            return entry, "unmarked"
    case_labels = [a.label for a in grammar.case_affixes]
    number_labels = [a.label for a in grammar.number_affixes]
    for entry in noun_entries:
        for case in case_labels:
            if spells(entry, case, None):
                return entry, case
    for entry in noun_entries:
        for number in number_labels:
            for case in [None, *case_labels]:
                if spells(entry, case, number):
                    return entry, number if case is None else f"{case}+{number}"
    if grammar.possession_affixes:
        for entry in noun_entries:
            for number in [None, *number_labels]:
                for case in [None, *case_labels]:
                    if spells(entry, case, number, True):
                        return entry, "+".join(p for p in (case, number, "possessed") if p)
    if grammar.possessor_person_affixes:
        for entry in noun_entries:
            for number in [None, *number_labels]:
                for case in [None, *case_labels]:
                    for person_affix in grammar.possessor_person_affixes:
                        if spells(entry, case, number, False, person_affix.label):
                            return entry, "+".join(p for p in (case, number, f"poss:{person_affix.label}") if p)
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
    """``(entry, class_name, degree_label)`` for an agreeing word (an adjective,
    demonstrative, numeral or possessive word) carrying a class, number, case
    and/or degree suffix; ``None`` when no combination spells ``token``.
    Plainest reading first."""
    normalized = _normalize(token)
    prefix = _stem_prefix(token)
    grammar = language.grammar
    degree_options: list[str | None] = [None] + [a.label for a in grammar.degree_affixes]
    for entry in language.lexicon.entries:
        category = _agreement_category(entry)
        if category is None or _stem_prefix(entry.romanization) != prefix:
            continue
        class_options, number_options, case_options = _agreement_options(grammar, category)
        combos = sorted(
            (
                (c, d, n, k)
                for c in class_options
                for d in (degree_options if category in ("adjective", "adverb") else [None])
                for n in number_options
                for k in case_options
                if c is not None or d is not None or n is not None or k is not None
            ),
            key=lambda combo: sum(x is not None for x in combo),
        )
        for class_label, degree_label, number_label, case_label in combos:
            candidate = _apply_class_agreement(language, entry, class_label, degree_label, number_label, case_label)
            if _normalize(candidate[0]) == normalized:
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
        class_options, number_options, case_options = _agreement_options(language.grammar, "article")
        for class_label in class_options:
            for number_label in number_options:
                for case_label in case_options:
                    if class_label is None and number_label is None and case_label is None:
                        continue
                    forms.add(
                        _normalize(_apply_class_agreement(language, entry, class_label, None, number_label, case_label)[0])
                    )
    return forms


_NO_EXTRA = (None, False, None, False)
"""``(verb number, polite, evidential, negative)`` with nothing marked."""


def _decode_verb_full(
    language: Language, token: str, finite_first: bool = False, skip_forms: bool = False,
    auxiliary_tense: bool = False,
) -> tuple[
    LexicalEntry, str | None, str | None, str | None, str | None, str | None, str | None, str | None, bool,
    str | None, str | None, bool,
] | None:
    """``(entry, tense_label, aspect_label, verb_mood_label, voice_label,
    agreement_label, object, number, polite, form case, evidential, negative)``
    for a verb-position token, with ``"imperative"`` (or ``"prohibitive"``)
    in the tense slot for a command. Generate-and-compare like ``_decode_noun``. The full search
    over tense x aspect x mood x voice x object x agreement is large, so it is
    staged (see below) and restricted to verbs whose first two letters match
    the token's (suffixes never change them); if that finds nothing, the
    earlier tense x agreement search runs over every verb. ``finite_first``
    (a verb with an auxiliary word beside it, hence probably no tense suffix of
    its own) tries the finite readings before the non-finite forms."""
    if finite_first and not skip_forms:
        finite = _decode_verb_full(
            language, token, finite_first=True, skip_forms=True, auxiliary_tense=auxiliary_tense
        )
        if finite is not None:
            return finite
    normalized = _normalize(token)
    verb_entries = [e for e in language.lexicon.entries if e.pos is PartOfSpeech.VERB]
    for entry in verb_entries:
        if _normalize(entry.romanization) == normalized:
            return entry, None, None, None, None, None, None, None, False, None, None, False
    def special(entries):
        """The command and non-finite readings of ``entries``."""
        imperative = next((a for a in language.grammar.mood_affixes if a.label == "imperative"), None)
        if imperative is not None:
            for entry in entries:
                rng = _translation_rng(language, _imperative_salt(entry))
                ipa = inflection_gen.apply_affix(
                    rng, imperative, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language)
                )
                candidate = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), entry.pos)
                if _normalize(candidate) == normalized:
                    return entry, "imperative", None, None, None, None, None, None, False, None, None, False
        prohibitive = next((a for a in language.grammar.mood_affixes if a.label == "prohibitive"), None)
        if prohibitive is not None:
            for entry in entries:
                rng = _translation_rng(language, _prohibitive_salt(entry))
                ipa = inflection_gen.apply_affix(
                    rng, prohibitive, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language)
                )
                candidate = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), entry.pos)
                if _normalize(candidate) == normalized:
                    return entry, "prohibitive", None, None, None, None, None, None, False, None, None, False
        grammar_forms = language.grammar
        form_candidates: list[tuple[InflectionAffix, str | None, str | None]] = []
        for form_affix in () if skip_forms else grammar_forms.verb_form_affixes:
            agreement_options: list[str | None] = [None]
            if form_affix.label == "infinitive" and grammar_forms.infinitive_agrees:
                agreement_options += list(pronoun_gen.PERSON_LABELS)
            case_options: list[str | None] = [None]
            if form_affix.label == "nominalized" and grammar_forms.nominalized_takes_case:
                case_options += list(grammar_forms.cases)
            form_candidates += [(form_affix, ag, cs) for ag in agreement_options for cs in case_options]
        # The plain forms first: a suffix plus an agreement or case suffix can spell
        # the same word as another form.
        form_candidates.sort(key=lambda c: (c[1] is not None) + (c[2] is not None))
        for form_affix, form_agreement, form_case in form_candidates:
            affix = _non_finite_affix(grammar_forms, form_affix, form_agreement, form_case)
            for entry in entries:
                rng = _translation_rng(language, _verb_form_salt(entry, form_affix.label, form_agreement, form_case))
                ipa = inflection_gen.apply_affix(
                    rng, affix, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language)
                )
                candidate = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), entry.pos)
                if _normalize(candidate) == normalized:
                    return entry, form_affix.label, None, None, None, form_agreement, None, None, False, form_case, None, False
        return None

    prefix = _stem_prefix(token)
    prefix_marked = any(a.prefix for name in inflection_gen._VERB_SUFFIX_FIELDS for a in getattr(language.grammar, name))
    # An inflected verb keeps its first two letters (suffixes never change them),
    # so an unknown token is only tried against the verbs that start like it.
    likely = verb_entries if prefix_marked else [e for e in verb_entries if _stem_prefix(e.romanization) == prefix]
    found_special = special(likely)
    if found_special is not None:
        return found_special
    kwargs = _stress_and_word_accent_kwargs(language)
    grammar = language.grammar
    tense_options: list[str | None] = [None] + list(grammar.tenses)
    aspect_options: list[str | None] = [None] + list(grammar.aspects)
    mood_options: list[str | None] = [None] + [m for m in grammar.moods if m != "imperative"]
    object_options: list[str | None] = [None] + [a.label for a in grammar.object_agreement_affixes]
    voice_options: list[str | None] = [None] + list(grammar.voices)
    number_polite: list[tuple[str | None, bool]] = [(None, False)]
    if grammar.verb_number_agreement:
        number_polite.append(("plural", False))
    if grammar.verb_politeness:
        number_polite.append((None, True))
        if grammar.verb_number_agreement:
            number_polite.append(("plural", True))
    evidential_options: list[str | None] = [None] + list(grammar.evidentials)
    negative_options = [False] + ([True] if grammar.verb_negative_affixes else [])
    marker_only = [
        (None, False, e, n) for e in evidential_options for n in negative_options if (e, n) != (None, False)
    ]
    extra_options = [(n, p, None, False) for n, p in number_polite] + [
        (n, p, e, g) for (_, _, e, g) in marker_only for n, p in number_polite
    ]
    agreement_options = _agreement_labels(grammar)

    def search(entries, aspects, moods, objects, voices, extras=(_NO_EXTRA,)):
        # Different label combinations can spell the same word (short
        # suffixes concatenate alike), so try the plainest reading first:
        # fewest optional labels, and a tense whenever the language has
        # tenses (the encoder normally supplies one).
        combos = sorted(
            (
                (tense_label, aspect_label, mood_label, object_label, voice_label, extra)
                for tense_label in tense_options
                for aspect_label in aspects
                for mood_label in moods
                for object_label in objects
                for voice_label in voices
                for extra in extras
            ),
            key=lambda c: (c[1] is not None) + (c[2] is not None) + (c[3] is not None) + (c[4] is not None)
            + (c[5][0] is not None) + c[5][1] + (c[5][2] is not None) + c[5][3]
            + (c[0] is None and bool(grammar.tenses) and not auxiliary_tense) + (c[0] is not None and auxiliary_tense),
        )
        for (
            tense_label, aspect_label, mood_label, object_label, voice_label,
            (number_label, polite, evidential_label, negative),
        ) in combos:
            for entry in entries:
                for agreement_label in agreement_options:
                    affix = _combined_tense_agreement_affix(
                        grammar, tense_label, agreement_label, aspect_label, mood_label, object_label, voice_label,
                        number_label, polite, evidential_label, negative,
                    )
                    if affix is None:
                        continue
                    rng = _translation_rng(
                        language,
                        _verb_affix_salt(
                            entry, tense_label, agreement_label, aspect_label, mood_label, object_label, voice_label,
                            number_label, polite, evidential_label, negative,
                        ),
                    )
                    ipa = inflection_gen.apply_affix(rng, affix, entry.ipa, language.phonology, **kwargs)
                    candidate = apply_grammatical_spelling(
                        language.romanization, language.romanization.apply(ipa), entry.pos
                    )
                    if _normalize(candidate) == normalized:
                        return (
                            entry, tense_label, aspect_label, mood_label, voice_label, agreement_label,
                            object_label, number_label, polite, None, evidential_label, negative,
                        )
        return None

    # Stages, cheapest first: tense x agreement x object agreement; then a
    # voice; then aspect/mood without an object marker (alone, and with a
    # voice); then aspect/mood with object agreement (only in languages that
    # have it at all).
    stages = [
        ([None], [None], object_options, [None], [_NO_EXTRA]),
        ([None], [None], [None], voice_options, [_NO_EXTRA]),
        ([None], [None], [None], [None], extra_options),
        (aspect_options, mood_options, [None], [None], [_NO_EXTRA]),
        (aspect_options, [None], [None], voice_options, [_NO_EXTRA]),
        (aspect_options, mood_options, object_options, [None], [_NO_EXTRA]),
    ]
    if marker_only:
        stages += [
            ([None], [None], object_options, [None], [_NO_EXTRA] + marker_only),
            (aspect_options, [None], [None], [None], [_NO_EXTRA] + marker_only),
            ([None], mood_options, [None], [None], [_NO_EXTRA] + marker_only),
        ]
    tried: list[tuple] = []
    for stage in stages:
        aspects, moods, objects, voices, extras = stage
        trivial = (len(aspects), len(moods), len(objects), len(voices), len(extras)) == (1, 1, 1, 1, 1)
        if stage in tried or (tried and trivial):
            continue
        tried.append(stage)
        found = search(likely, aspects, moods, objects, voices, extras)
        if found is not None:
            return found
    if len(likely) != len(verb_entries):
        rest = [e for e in verb_entries if e not in likely]
        found_rest = special(rest)
        if found_rest is not None:
            return found_rest
        return search(verb_entries, [None], [None], [None], [None], [_NO_EXTRA])
    return None


def _person_suffix_is_distinct(grammar: GrammarProfile, label: str, objects: bool = False) -> bool:
    """Whether the agreement suffix for person ``label`` (subject agreement, or
    object agreement with ``objects``) differs from every other one in its
    set, so a decoded suffix really names that person."""
    affixes = grammar.object_agreement_affixes if objects else grammar.agreement_affixes
    own = next((a for a in affixes if a.label == label), None)
    if own is None:
        return False
    return all(a.suffix != own.suffix for a in affixes if a.label != label)


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
        return "was" if tense_label == "past" else "will be" if tense_label == "future" else "is"
    if tense_label == "future":
        return f"will {entry.primary_gloss}"
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
    if voice_label == "middle":
        participle = _PARTICIPLE_BY_LEMMA.get(gloss) or _PAST_FORM_BY_LEMMA.get(gloss, gloss + "ed")
        return f"got {participle}" if tense_label == "past" else f"gets {participle}"
    if voice_label == "applicative":
        return f"{gloss} for"
    if voice_label == "impersonal":
        return f"one {gloss}s"
    if voice_label == "reflexive":
        return f"{gloss} oneself"
    if voice_label == "reciprocal":
        return f"{gloss} each other"
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


def _subordination_note(grammar: GrammarProfile) -> str:
    relative = {
        "pronoun": "relative clauses use a relative pronoun",
        "particle": 'relative clauses use the invariant word "rel"',
        "gap": "relative clauses have no linking word and leave the relativized noun out",
        "resumptive": 'relative clauses use the word "rel" and keep a pronoun for the relativized noun',
        "correlative": 'a relative clause comes first and the main clause points back with "that" (a correlative)',
    }.get(grammar.relativization, "relative clauses use a relative pronoun")
    position = "before" if grammar.relative_clause_position == "before_noun" else "after"
    forms = (
        "; non-finite verbs (annotated 'verb form') read as " + ", ".join(
            {
                "infinitive": "infinitives (to see)", "nominalized": "gerunds (seeing)",
                "participle": "participles (sleeping)", "converb": "medial verbs (see and ...)",
            }[f]
            for f in grammar.verb_forms
        )
        if grammar.verb_forms
        else ""
    )
    extras = []
    if grammar.relative_pronoun_declines:
        extras.append("the relative pronoun declines (who/whom/whose)")
    if grammar.complementizer_by_verb:
        extras.append("the complementizer depends on the governing verb")
    if grammar.correlative_adverbials:
        extras.append('"if"/"when" clauses come first with "then" in the main clause')
    coordination = {
        "word": "clauses are joined by a conjunction",
        "converb": "clauses are joined by a medial verb form (no conjunction)",
        "juxtapose": "clauses are simply juxtaposed",
    }.get(grammar.clause_coordination, "")
    if coordination:
        extras.append(coordination)
    tail = ("; " + "; ".join(extras)) if extras else ""
    return f" Subordination: {relative}, placed {position} its noun{forms}{tail}."


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
        + _subordination_note(grammar)
    )


def _drop_repeaters(language: Language, tokens: list[str]) -> list[str]:
    """Removes a noun repeated as its own classifier: the same noun twice in a
    row ("two dog dog"), or a noun, a numeral/quantifier and the noun again
    ("dog two dog")."""
    kept: list[str] = []
    for token in tokens:
        entry = language.lexicon.by_form(token)
        is_noun = entry is not None and entry.pos is PartOfSpeech.NOUN
        if is_noun and kept and _normalize(kept[-1]) == _normalize(token):
            continue
        if is_noun and len(kept) >= 2 and _normalize(kept[-2]) == _normalize(token):
            middle = language.lexicon.by_form(kept[-1])
            if middle is not None and middle.pos is PartOfSpeech.NUMERAL:
                continue
        kept.append(token)
    return kept


def translate_to_english(
    text: str, language: Language, llm_client: LLMClient
) -> TranslationResult:
    raw_tokens = unicodedata.normalize("NFC", text).strip().split()
    article_forms = _article_forms(language)
    tokens = [t for t in raw_tokens if _normalize(t) not in article_forms]
    if language.grammar.repeater_rate > 0.0:
        tokens = _drop_repeaters(language, tokens)
    tokens, auxiliary_labels = _split_auxiliary_tokens(language, tokens)

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
    seen_persons: set[str] = set()  # persons named by a pronoun already decoded in this sentence
    for token_index, tok in enumerate(tokens):
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
            gloss = entry.primary_gloss
            if gloss.startswith((classifier_gen.CLASSIFIER_GLOSS_PREFIX, classifier_gen.POSSESSIVE_CLASSIFIER_GLOSS_PREFIX)):
                continue  # a classifier carries no English word
            relative = subordination_gen.relative_reading(gloss)
            if relative is not None and gloss != relative:
                plain.append(relative)
                annotated.append(f"{relative} (relative pronoun)")
                continue
            complementizer = subordination_gen.complementizer_split(gloss)
            if complementizer is not None:
                plain.append(complementizer[0])
                annotated.append(f"{complementizer[0]} (complementizer for a {complementizer[1]} verb)")
                continue
            suppletive = pronoun_gen.suppletive_split(gloss)
            if suppletive is not None:
                base, case_name = suppletive
                seen_persons.add(pronoun_gen.person_label(base))
                plain.append(pronoun_gen.suppletive_reading(base, case_name))
                annotated.append(f"{pronoun_gen.english_reading(base)} (case: {case_name})")
                continue
            irregular_form = voice_np_gen.suppletive_split(gloss)
            if irregular_form is not None:
                reading = voice_np_gen.suppletive_reading(*irregular_form)
                plain.append(reading)
                annotated.append(reading)
                continue
            person = pronoun_gen.person_label(gloss)
            if person is not None:
                seen_persons.add(person)
            reading = pronoun_gen.english_reading(gloss)
            plain.append(reading)
            annotated.append(reading)
            continue
        noun_decoded = _decode_noun(language, tok)
        if noun_decoded is not None:
            noun_entry, case_label = noun_decoded
            parts = [] if case_label == "unmarked" else case_label.split("+")
            number_part = next((p for p in parts if p in sentence_planner.NUMBER_LABELS), None)
            case_part = next(
                (
                    p for p in parts
                    if p not in (*sentence_planner.NUMBER_LABELS, "possessed") and not p.startswith("poss:")
                ),
                None,
            )
            is_possessed = "possessed" in parts
            possessor_part = next((p[5:] for p in parts if p.startswith("poss:")), None)
            noun_gloss = pronoun_gen.english_reading(noun_entry.primary_gloss)
            irregular = voice_np_gen.suppletive_split(noun_entry.primary_gloss)
            if irregular is not None and irregular[1] == "plural":
                noun_gloss = voice_np_gen.suppletive_reading(*irregular)
                number_part = number_part or "plural"
            noun_plain = noun_gloss + ("s" if number_part and irregular is None else "")
            noun_plain = {"trial": f"three {noun_plain}", "collective": f"group of {noun_plain}"}.get(number_part, noun_plain)
            if case_part in voice_np_gen.CASE_PREPOSITION:
                standard_word = None
                if grammar_now_case(language) == case_part:  # the standard of a comparison
                    if any(p.startswith("as ") and p.endswith(" as") for p in plain):
                        standard_word = "as"
                    elif any(p == "more" or p.startswith("more ") or p.startswith("most ") for p in plain):
                        standard_word = "than"
                noun_plain = f"{standard_word or voice_np_gen.CASE_PREPOSITION[case_part]} {noun_plain}"
            plain.append(noun_plain)
            notes = (
                ([number_part] if number_part else [])
                + (["possessed"] if is_possessed else [])
                + ([f"possessed by: {'the subject (his/her/its own)' if possessor_part == 'self' else possessor_part}"]
                   if possessor_part else [])
                + ([f"case: {case_part}"] if case_part else [])
            )
            annotated.append(noun_gloss if not notes else f"{noun_gloss} ({', '.join(notes)})")
            continue
        adjective_decoded = (
            _decode_adjective_full(language, tok)
            if (
                language.grammar.class_affixes
                or language.grammar.degree_affixes
                or language.grammar.number_agreement_targets
                or language.grammar.case_agreement_targets
            )
            else None
        )
        if adjective_decoded is not None:
            adjective_entry, _, degree_label = adjective_decoded
            if adjective_entry.primary_gloss.startswith(classifier_gen.POSSESSIVE_CLASSIFIER_GLOSS_PREFIX):
                continue
            gloss = pronoun_gen.english_reading(adjective_entry.primary_gloss)
            irregular_degree = voice_np_gen.suppletive_split(adjective_entry.primary_gloss)
            if irregular_degree is not None and irregular_degree[1] in ("comparative", "superlative"):
                reading = voice_np_gen.suppletive_reading(*irregular_degree)
                plain.append(reading)
                annotated.append(reading)
                continue
            plain.append(comparison_gen.DEGREE_READING.get(degree_label or "", "{}").format(gloss))
            annotated.append(gloss if degree_label is None else f"{gloss} ({degree_label})")
            continue
        host_labels = auxiliary_labels.get(token_index, [])
        verb_full = _decode_verb_full(
            language, tok, finite_first=bool(host_labels),
            auxiliary_tense=any(label in language.grammar.tenses for label in host_labels),
        )
        if verb_full is not None:
            (
                verb_entry, tense_label, aspect_label, mood_label, voice_label, agreement_label,
                object_label, number_label, polite_label, form_case, evidential_label, negative_label,
            ) = verb_full
            past_split = voice_np_gen.suppletive_split(verb_entry.primary_gloss)
            if past_split is not None and past_split[1] == "past":
                verb_entry = verb_entry.model_copy(update={"glosses": (past_split[0],)})
                tense_label = tense_label or "past"
            if tense_label in subordination_gen.VERB_FORM_LABELS:
                gloss = verb_entry.primary_gloss
                reading = {
                    "infinitive": f"to {gloss}", "nominalized": f"{gloss}ing", "participle": f"{gloss}ing",
                    "converb": f"{gloss} and",
                }[tense_label]
                notes = [f"verb form: {tense_label}"]
                if agreement_label in pronoun_gen.PERSON_LABELS:
                    notes.append(f"controller: {agreement_label}")
                if form_case:
                    notes.append(f"case: {form_case}")
                plain.append(reading)
                annotated.append(f"{gloss} ({', '.join(notes)})")
                continue
            if tense_label == "imperative":
                is_imperative = True
                plain.append(verb_entry.primary_gloss)
                annotated.append(f"{verb_entry.primary_gloss} (mood: imperative)")
                continue
            if tense_label == "prohibitive":
                is_imperative = True
                plain.append(f"do not {verb_entry.primary_gloss}")
                annotated.append(f"{verb_entry.primary_gloss} (mood: imperative, negative)")
                continue
            for aux_label in auxiliary_labels.pop(token_index, []):
                grammar_now = language.grammar
                if aux_label in grammar_now.tenses and tense_label is None:
                    tense_label = aux_label
                elif aux_label in grammar_now.aspects and aspect_label is None:
                    aspect_label = aux_label
                elif aux_label in grammar_now.moods and mood_label is None:
                    mood_label = aux_label
            gloss = _english_verb_phrase(verb_entry, tense_label, aspect_label, mood_label, voice_label)
            if evidential_label in _EVIDENTIAL_ADVERB:
                gloss = f"{_EVIDENTIAL_ADVERB[evidential_label]} {gloss}"
            if negative_label and language.grammar.negation_strategy != "both":
                gloss = f"not {gloss}"
            if (
                language.grammar.pro_drop
                and agreement_label in pronoun_gen.PERSON_LABELS
                and agreement_label not in seen_persons
                and _person_suffix_is_distinct(language.grammar, agreement_label)
            ):
                gloss = f"{agreement_label} {gloss}"  # the dropped subject, read from the verb's agreement
            if (
                language.grammar.object_pro_drop
                and object_label in pronoun_gen.OBJECT_READING
                and object_label not in seen_persons
                and _person_suffix_is_distinct(language.grammar, object_label, objects=True)
            ):
                gloss = f"{gloss} {pronoun_gen.OBJECT_READING[object_label]}"  # the dropped object
            plain.append(gloss)
            notes = (["subject: plural"] if number_label else []) + (["polite"] if polite_label else []) + [
                f"{name}: {label}"
                for name, label in (
                    ("tense", tense_label), ("aspect", aspect_label), ("mood", mood_label), ("voice", voice_label),
                    ("evidential", evidential_label),
                )
                if label is not None
            ] + (["negative"] if negative_label else [])
            annotated.append(gloss if not notes else f"{gloss} ({', '.join(notes)})")
            continue
        plain.append(f"<unknown:{tok}>")
        annotated.append(f"<unknown:{tok}>")
    for leftover in auxiliary_labels.values():
        for label in leftover:  # an auxiliary word with no verb beside it
            plain.append(_AUXILIARY_ENGLISH.get(label, label))
            annotated.append(f"{_AUXILIARY_ENGLISH.get(label, label)} (auxiliary: {label})")

    plain_draft = " ".join(plain) + ("?" if is_question else "!" if is_imperative else "")
    annotated_draft = " ".join(annotated) + (
        " [this is a yes/no question]" if is_question else " [this is a command]" if is_imperative else ""
    )
    request = LLMRequest(
        system=(
            "You turn an annotated rough English gloss sequence from a "
            "constructed-language translation into one natural, fluent "
            "English sentence. Each word is its English gloss, optionally "
            "annotated with '(plural)'/'(dual)' (render the noun plural or with 'two'), '(trial)' (three of them) "
            "or '(collective)' (a group of them), "
            "'(possessed)' (owned by the preceding word), 'of' (a possessive marker between an "
            "owner and the thing owned), '(mood: imperative)' "
            "(a command), '(case: X)' (this word's grammatical role -- "
            "e.g. an accusative/absolutive/ergative-marked word is "
            "typically a direct object; locative means 'in/on/at' the word, instrumental 'with/by' it, ablative 'from', allative 'to/into', comitative 'together with') or '(tense: X)', '(aspect: X)', '(mood: X)' or '(voice: X)' (a verb's "
            "detected tense, aspect, verbal mood or voice -- render them as the matching English "
            "tense, progressive/perfect/habitual aspect, would/can/might, or a passive (the patient "
            "is the subject, the agent follows 'by'), antipassive (no object) or causative (make X do)). "
            "A '(comparative)', '(superlative)', '(equative)' (as X as), '(excessive)' (too X) or '(elative)' (very X) "
            "on an adjective or adverb is its degree. "
            "An '(evidential: X)' marks the source of the information "
            "(reportedly, apparently, or first-hand) and '(negative)' means the verb is negated. "
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
