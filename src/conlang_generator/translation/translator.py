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

Remaining v0 limitations, by design: single-clause only (the plan's own
flat slot list supports noun-phrase-level coordination -- "the mountain
and the river" -- but not multiple independent clauses, relative clauses,
or subordination); no question formation; negation is a single particle
slot with no per-language negation-position typology curated.

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
from conlang_generator.generation import inflection_gen, stress_gen, tone_sandhi, word_accent_gen
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
    grammar: GrammarProfile, tense_label: str | None, agreement_label: str
) -> InflectionAffix | None:
    """Composes this sentence's own tense affix and agreement affix into
    one synthetic ``InflectionAffix`` (tense first, then agreement) so
    ``inflection_gen.apply_affix`` only needs to re-derive stress once --
    see that function's own docstring for why two separate calls would be
    wasteful (and arguably incorrect). ``None`` when neither axis
    contributes anything (an untensed, agreement-less-by-coincidence verb
    -- not a real case in this project today, since ``agreement_affixes``
    always has a ``"default"`` entry, but kept honest regardless)."""
    tense_affix = next((a for a in grammar.tense_affixes if a.label == tense_label), None) if tense_label else None
    agreement_affix = next((a for a in grammar.agreement_affixes if a.label == agreement_label), None)
    prefix = (tense_affix.prefix if tense_affix else ()) + (agreement_affix.prefix if agreement_affix else ())
    suffix = (tense_affix.suffix if tense_affix else ()) + (agreement_affix.suffix if agreement_affix else ())
    if not prefix and not suffix:
        return None
    return InflectionAffix(label="tense+agreement", prefix=prefix, suffix=suffix)


def _case_affix_salt(entry: LexicalEntry, case_label: str) -> str:
    """The rng salt for marking ``entry`` with ``case_label`` -- shared
    verbatim between encoding (``_apply_case``) and decoding (``_decode_
    noun``) so both sides derive the *identical* rng stream and therefore
    the identical stress/re-rendering outcome for the same (entry, case)
    pair. Deliberately keyed only on ``entry.ipa``/``case_label`` -- never
    on the original English token or sentence, which decoding has no way
    to reconstruct from an observed conlang word alone."""
    return f"case:{entry.ipa}:{case_label}"


def _verb_affix_salt(entry: LexicalEntry, tense_label: str | None, agreement_label: str) -> str:
    """The rng salt for marking ``entry`` with a given tense+agreement
    combination -- same "identical salt on both sides" contract as
    ``_case_affix_salt``, keyed on the *resolved* labels (not the raw
    English verb/subject tokens, which decoding never has)."""
    return f"verb:{entry.ipa}:{tense_label}:{agreement_label}"


def _apply_case(language: Language, entry: LexicalEntry, case_label: str | None) -> tuple[str, str]:
    """Returns this entry's own ``(romanization, ipa)``, case-marked when
    ``case_label`` names a case this language's own ``GrammarProfile.cases``
    actually has (and a matching ``case_affixes`` entry exists) --
    unmarked (this entry's own bare citation form) otherwise, e.g. an
    isolating language, or the argument alignment leaves bare (only one
    argument is ever case-marked per sentence -- see ``translate_to_
    conlang``'s own SVO handling)."""
    grammar = language.grammar
    if case_label is None or case_label not in grammar.cases:
        return entry.romanization, entry.ipa
    affix = next((a for a in grammar.case_affixes if a.label == case_label), None)
    if affix is None:
        return entry.romanization, entry.ipa
    rng = _translation_rng(language, _case_affix_salt(entry, case_label))
    ipa = inflection_gen.apply_affix(rng, affix, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language))
    romanization = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), entry.pos)
    return romanization, ipa


def _apply_verb_inflection(
    language: Language, entry: LexicalEntry, tense_label: str | None, agreement_label: str
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
    resolved_tense = tense_label if tense_label in grammar.tenses else None
    resolved_agreement = agreement_label if agreement_label in inflection_gen.AGREEMENT_LABELS else "default"
    affix = _combined_tense_agreement_affix(grammar, resolved_tense, resolved_agreement)
    if affix is None:
        return entry.romanization, entry.ipa
    rng = _translation_rng(language, _verb_affix_salt(entry, resolved_tense, resolved_agreement))
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


def translate_to_conlang(
    text: str, language: Language, llm_client: LLMClient
) -> TranslationResult:
    plan = sentence_planner.plan_sentence(text, language, llm_client)
    coined: list[LexicalEntry] = []
    working_language = language

    romanization_parts: list[str] = []
    ipa_parts: list[str] = []
    gloss_parts: list[str | None] = []
    for slot in plan.slots:
        rendered: tuple[str, str] | None = None
        entry: LexicalEntry | None = None
        if slot.kind == "content" and slot.gloss:
            pos = sentence_planner.POS_BY_PLAN_STRING.get(slot.pos, PartOfSpeech.NOUN)
            working_language, entry = _lookup_or_coin(
                working_language, slot.gloss, pos, coined, llm_client, lemma_candidates=[slot.gloss]
            )
            rendered = (
                _apply_verb_inflection(working_language, entry, slot.tense, slot.agreement or "default")
                if pos is PartOfSpeech.VERB
                else _apply_case(working_language, entry, slot.case)
            )
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
                else _apply_case(working_language, entry, slot.case)
            )
        elif slot.kind == "copula":
            entry = working_language.lexicon.by_gloss("be")
            if entry is not None:
                rendered = _apply_verb_inflection(working_language, entry, slot.tense, slot.agreement or "default")
        elif slot.kind in _BARE_GLOSS_BY_SLOT_KIND:
            entry = working_language.lexicon.by_gloss(_BARE_GLOSS_BY_SLOT_KIND[slot.kind])
            if entry is not None:
                rendered = (entry.romanization, entry.ipa)

        if rendered is not None:
            romanization_parts.append(rendered[0])
            ipa_parts.append(rendered[1])
            gloss_parts.append(entry.primary_gloss if entry is not None else None)

    return TranslationResult(
        text=" ".join(romanization_parts),
        ipa=" ".join(tone_sandhi.apply_sandhi(ipa_parts, language.tone_system, gloss_parts)),
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
    return None


def _decode_verb(language: Language, token: str) -> tuple[LexicalEntry, str | None] | None:
    """The verb-position counterpart of ``_decode_noun`` -- returns
    ``(entry, tense_label)`` (``None`` for the tense when this language
    has no tense system, or the exact bare form matched)."""
    normalized = _normalize(token)
    verb_entries = [e for e in language.lexicon.entries if e.pos is PartOfSpeech.VERB]
    for entry in verb_entries:
        if _normalize(entry.romanization) == normalized:
            return entry, None
    tense_options: list[str | None] = [None] + list(language.grammar.tenses)
    for entry in verb_entries:
        for tense_label in tense_options:
            for agreement_label in inflection_gen.AGREEMENT_LABELS:
                affix = _combined_tense_agreement_affix(language.grammar, tense_label, agreement_label)
                if affix is None:
                    continue
                rng = _translation_rng(language, _verb_affix_salt(entry, tense_label, agreement_label))
                ipa = inflection_gen.apply_affix(
                    rng, affix, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language)
                )
                candidate = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), entry.pos)
                if _normalize(candidate) == normalized:
                    return entry, tense_label
    return None


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


def translate_to_english(
    text: str, language: Language, llm_client: LLMClient
) -> TranslationResult:
    raw_tokens = unicodedata.normalize("NFC", text).strip().split()
    the_entry = language.lexicon.by_gloss("the")
    the_normalized = _normalize(the_entry.romanization) if the_entry is not None else None
    tokens = [t for t in raw_tokens if the_normalized is None or _normalize(t) != the_normalized]

    # Per-token, structure-agnostic decode -- the plan-driven encoder can
    # produce genuinely arbitrary structure, so there's no fixed sentence
    # shape left to special-case on the way back (see this module's own
    # docstring). ``plain`` feeds a deterministic fake/fallback answer
    # (and the real fluency LLM's own "if all else fails" text);
    # ``annotated`` gives a real LLM the case/tense information a bare
    # gloss sequence would otherwise lose.
    plain: list[str] = []
    annotated: list[str] = []
    for tok in tokens:
        entry = language.lexicon.by_form(tok)
        if entry is not None:
            plain.append(entry.primary_gloss)
            annotated.append(entry.primary_gloss)
            continue
        noun_decoded = _decode_noun(language, tok)
        if noun_decoded is not None:
            noun_entry, case_label = noun_decoded
            plain.append(noun_entry.primary_gloss)
            annotated.append(
                noun_entry.primary_gloss
                if case_label == "unmarked"
                else f"{noun_entry.primary_gloss} (case: {case_label})"
            )
            continue
        verb_decoded = _decode_verb(language, tok)
        if verb_decoded is not None:
            verb_entry, tense_label = verb_decoded
            gloss = _english_verb_gloss(verb_entry, tense_label)
            plain.append(gloss)
            annotated.append(gloss if tense_label is None else f"{gloss} (tense: {tense_label})")
            continue
        plain.append(f"<unknown:{tok}>")
        annotated.append(f"<unknown:{tok}>")

    plain_draft = " ".join(plain)
    annotated_draft = " ".join(annotated)
    request = LLMRequest(
        system=(
            "You turn an annotated rough English gloss sequence from a "
            "constructed-language translation into one natural, fluent "
            "English sentence. Each word is its English gloss, optionally "
            "annotated with '(case: X)' (this word's grammatical role -- "
            "e.g. an accusative/absolutive/ergative-marked word is "
            "typically a direct object) or '(tense: X)' (a verb's "
            "detected tense -- render it as the matching English tense). "
            "Keep the meaning and the word order's implied roles; do not "
            "add new content; drop the annotations themselves from your "
            "output."
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
