"""English <-> conlang translation.

Explicit v0 limitations, by design:

- No real parser. Exactly three sentence shapes are recognized: a two-content-
  word predicate-adjective sentence ("the mountain is high"), a three-
  content-word subject-verb-object sentence ("I see the mountain"), and
  everything else falls back to naive word-for-word substitution in the
  original order.
- English tokens are matched to glosses via exact match, a trailing-``s``
  strip, or (for tense detection -- see ``_detect_tense_and_lemma_candidates``)
  a small irregular-past lookup plus a regular ``-ed``/``-ied`` strip -- no
  real lemmatization or parsing beyond that.
- Conlang -> English reconstruction assumes the *English* side is always
  canonical SVO; this is a simplification, not a model of English syntax.

Real inflection (case, tense, subject agreement, articles, an overt copula)
is applied on the way to the conlang when the target language's own
``GrammarProfile`` says it has the feature -- see ``_apply_case``/
``_apply_verb_inflection``/``_maybe_prefix_article``/the predicate-adjective
pattern's own copula handling below. Applying an affix re-derives the
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
A 3-token sentence is genuinely ambiguous once a copula exists (subject-
copula-adjective and subject-verb-object both look like 3 plain tokens) --
resolved by testing the copula hypothesis first (does the verb-position
token decode specifically against the "be" entry?) and falling back to the
transitive reading when it doesn't.

Unknown *English* content words trigger word coinage (see ``expansion.py``);
an unknown *conlang* word that can't be decoded via ``_decode_noun``/
``_decode_verb`` either (there is no English gloss to reverse-coin from)
surfaces as ``<unknown:...>`` in the rough gloss line.
"""

from __future__ import annotations

import hashlib
import random
import re
import unicodedata
from dataclasses import dataclass

from conlang_generator.core.grammar import Alignment, GrammarProfile, InflectionAffix, WordOrder
from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from conlang_generator.core.romanization import apply_grammatical_spelling
from conlang_generator.generation import inflection_gen, stress_gen, word_accent_gen
from conlang_generator.generation.reference_languages import match_profiles
from conlang_generator.llm.base import LLMClient, LLMRequest
from conlang_generator.llm.pricing import DEFAULT_MODEL
from conlang_generator.translation import expansion

_ARTICLES = {"a", "an", "the"}
_COPULAS = {"is", "are", "am", "was", "were", "be", "been", "being"}
_PAST_COPULAS = {"was", "were"}

_ROLE_ORDER: dict[WordOrder, tuple[str, str, str]] = {
    WordOrder.SOV: ("S", "O", "V"),
    WordOrder.SVO: ("S", "V", "O"),
    WordOrder.VSO: ("V", "S", "O"),
    WordOrder.VOS: ("V", "O", "S"),
    WordOrder.OVS: ("O", "V", "S"),
    WordOrder.OSV: ("O", "S", "V"),
}

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
english`` to reconstruct a past-tense English gloss once a conlang verb
has been decoded back to its lemma and a ``"past"`` tense reading."""

_AGREEMENT_LABEL_BY_PRONOUN = {"i": "I", "you": "you", "he": "he", "we": "we"}
"""Maps a lowercased English subject-pronoun token to the matching
``generation.inflection_gen.AGREEMENT_LABELS`` entry -- any other subject
(a coined or looked-up noun) gets ``"default"``, the real cross-linguistic
"3rd person is the unmarked default" pattern."""

_PRONOUN_TOKENS = {"i", "you", "he", "we", "this", "that"}
"""This project's own full ``lexicon_gen.CORE_MEANINGS`` pronoun set --
consulted by ``_maybe_prefix_article`` so a pronoun never gets "the"
prepended (no real language does this) even though ``used_article`` is
tracked per *sentence*, not per noun phrase (this module's own "no real
parser" limitation -- with only one shared flag, without this exclusion a
transitive sentence's own pronominal subject would wrongly inherit the
object's own article)."""


@dataclass(frozen=True)
class TranslationResult:
    text: str
    ipa: str
    language: Language
    """Possibly updated -- new words may have been coined during translation."""
    coined: tuple[LexicalEntry, ...] = ()
    pattern: str = "word-for-word"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


def _lemma_candidates(token: str) -> list[str]:
    candidates = [token]
    if token.endswith("s") and len(token) > 1:
        candidates.append(token[:-1])
    return candidates


def _detect_tense_and_lemma_candidates(token: str) -> tuple[str, list[str]]:
    """Returns ``(detected_tense, lemma_candidates)`` -- ``"past"`` for a
    recognized irregular past form or a regular ``-ed``/``-ied`` ending,
    ``"non_past"`` otherwise (falling back to ``_lemma_candidates``'s own
    trailing-``s`` strip, unchanged from before this project modeled tense
    at all)."""
    if token in _IRREGULAR_LEMMA_BY_PAST:
        return "past", [_IRREGULAR_LEMMA_BY_PAST[token]]
    if token.endswith("ied") and len(token) > 3:
        return "past", [token[:-3] + "y"]
    if token.endswith("ed") and len(token) > 2:
        return "past", [token[:-2]]
    return "non_past", _lemma_candidates(token)


def _tense_label(detected_tense: str, tenses: tuple[str, ...]) -> str | None:
    """Maps a detected ``"past"``/``"non_past"`` reading onto whichever
    label this language's own rolled ``GrammarProfile.tenses`` system
    actually has for it (a 2-way ``("past", "non_past")`` system or a 3-way
    ``("past", "present", "future")`` one -- see ``grammar_gen.py``).
    ``None`` when this language has no tense system at all, or (for a
    3-way system) no meaningful non-past English tense was actually
    detected -- this module never tries to recognize a periphrastic
    English future ("will go")."""
    if detected_tense == "past":
        return "past" if "past" in tenses else None
    if "non_past" in tenses:
        return "non_past"
    if "present" in tenses:
        return "present"
    return None


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


def _apply_verb_inflection(language: Language, entry: LexicalEntry, detected_tense: str, subject_tok: str) -> tuple[str, str]:
    """The verb/copula-side counterpart of ``_apply_case`` -- composes and
    applies this sentence's own tense+agreement affix (see
    ``_combined_tense_agreement_affix``), or returns the bare citation
    form unchanged when this language has neither tense nor a real
    agreement suffix worth attaching (never actually empty today, since
    ``agreement_affixes`` always has a ``"default"`` entry, but the
    ``None`` case is still handled honestly)."""
    grammar = language.grammar
    tense_label = _tense_label(detected_tense, grammar.tenses)
    agreement_label = _AGREEMENT_LABEL_BY_PRONOUN.get(subject_tok, "default")
    affix = _combined_tense_agreement_affix(grammar, tense_label, agreement_label)
    if affix is None:
        return entry.romanization, entry.ipa
    rng = _translation_rng(language, _verb_affix_salt(entry, tense_label, agreement_label))
    ipa = inflection_gen.apply_affix(rng, affix, entry.ipa, language.phonology, **_stress_and_word_accent_kwargs(language))
    romanization = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), entry.pos)
    return romanization, ipa


def _maybe_prefix_article(
    language: Language, romanization: str, ipa: str, used_article: bool, subject_or_object_tok: str
) -> tuple[str, str]:
    """Prepends this language's own coined "the" lexeme when the English
    input actually used an article, this language's own ``GrammarProfile.
    has_articles`` says it has one at all (``lexicon_gen.CONDITIONAL_
    MEANINGS`` guarantees the lexeme only exists in that case), and this
    particular argument isn't a pronoun (see ``_PRONOUN_TOKENS``'s own
    docstring for why that check matters given ``used_article`` is tracked
    per sentence, not per noun phrase)."""
    if not (used_article and language.grammar.has_articles) or subject_or_object_tok in _PRONOUN_TOKENS:
        return romanization, ipa
    article = language.lexicon.by_gloss("the")
    if article is None:
        return romanization, ipa
    return f"{article.romanization} {romanization}", f"{article.ipa} {ipa}"


def _lookup_or_coin(
    language: Language,
    token: str,
    pos: PartOfSpeech,
    coined: list[LexicalEntry],
    llm_client: LLMClient,
    lemma_candidates: list[str] | None = None,
) -> tuple[Language, LexicalEntry]:
    for candidate in lemma_candidates if lemma_candidates is not None else _lemma_candidates(token):
        entry = language.lexicon.by_gloss(candidate)
        if entry is not None:
            return language, entry

    new_entry = expansion.coin_word(language, token, pos, llm_client)
    coined.append(new_entry)
    updated = language.with_new_words(
        (new_entry,),
        reason=f"coined '{new_entry.romanization}' for '{token}' during translation",
    )
    return updated, new_entry


def translate_to_conlang(
    text: str, language: Language, llm_client: LLMClient
) -> TranslationResult:
    raw_tokens = _tokenize(text)
    used_article = any(t in _ARTICLES for t in raw_tokens)
    tokens = [t for t in raw_tokens if t not in _ARTICLES]
    has_copula = any(t in _COPULAS for t in tokens)
    copula_tok = next((t for t in tokens if t in _COPULAS), None)
    content_tokens = [t for t in tokens if t not in _COPULAS]

    coined: list[LexicalEntry] = []
    working_language = language

    if has_copula and len(content_tokens) == 2:
        subject_tok, adj_tok = content_tokens
        working_language, subject_entry = _lookup_or_coin(
            working_language, subject_tok, PartOfSpeech.NOUN, coined, llm_client
        )
        working_language, adj_entry = _lookup_or_coin(
            working_language, adj_tok, PartOfSpeech.ADJECTIVE, coined, llm_client
        )
        subject_pair = _maybe_prefix_article(
            working_language, *_apply_case(working_language, subject_entry, None), used_article, subject_tok
        )
        adj_pair = (adj_entry.romanization, adj_entry.ipa)
        ordered_pairs = (
            [subject_pair, adj_pair] if working_language.grammar.adjective_after_noun else [adj_pair, subject_pair]
        )
        if working_language.grammar.has_overt_copula:
            copula_entry = working_language.lexicon.by_gloss("be")
            if copula_entry is not None:
                detected_tense = "past" if copula_tok in _PAST_COPULAS else "non_past"
                copula_pair = _apply_verb_inflection(working_language, copula_entry, detected_tense, subject_tok)
                # The copula always sits between subject and predicate --
                # real "the mountain is high"/"haute est la montagne"-style
                # languages both keep it in the middle regardless of which
                # side the adjective itself falls on (adjective_after_noun
                # only governs their own relative order, reused here rather
                # than adding a second, dedicated predicate-order flag).
                ordered_pairs = [ordered_pairs[0], copula_pair, ordered_pairs[1]]
        pattern = "predicate-adjective"
    elif len(content_tokens) == 3:
        subject_tok, verb_tok, obj_tok = content_tokens
        working_language, subject_entry = _lookup_or_coin(
            working_language, subject_tok, PartOfSpeech.NOUN, coined, llm_client
        )
        detected_tense, verb_lemma_candidates = _detect_tense_and_lemma_candidates(verb_tok)
        working_language, verb_entry = _lookup_or_coin(
            working_language, verb_tok, PartOfSpeech.VERB, coined, llm_client, verb_lemma_candidates
        )
        working_language, obj_entry = _lookup_or_coin(
            working_language, obj_tok, PartOfSpeech.NOUN, coined, llm_client
        )
        grammar = working_language.grammar
        # Only one argument is ever case-marked per sentence, matching a
        # common real simplification (many real languages leave one side
        # of the alignment zero-marked) -- the object under nominative-
        # accusative, a transitive subject under ergative-absolutive.
        subject_case = "ergative" if grammar.alignment is Alignment.ERGATIVE_ABSOLUTIVE else None
        object_case = "accusative" if grammar.alignment is Alignment.NOMINATIVE_ACCUSATIVE else None
        subject_pair = _maybe_prefix_article(
            working_language, *_apply_case(working_language, subject_entry, subject_case), used_article, subject_tok
        )
        object_pair = _maybe_prefix_article(
            working_language, *_apply_case(working_language, obj_entry, object_case), used_article, obj_tok
        )
        verb_pair = _apply_verb_inflection(working_language, verb_entry, detected_tense, subject_tok)
        roles = {"S": subject_pair, "V": verb_pair, "O": object_pair}
        ordered_pairs = [roles[r] for r in _ROLE_ORDER[grammar.word_order]]
        pattern = "subject-verb-object"
    else:
        ordered_pairs = []
        for tok in content_tokens:
            working_language, entry = _lookup_or_coin(
                working_language, tok, PartOfSpeech.NOUN, coined, llm_client
            )
            ordered_pairs.append((entry.romanization, entry.ipa))
        pattern = "word-for-word"

    conlang_text = " ".join(romanization for romanization, _ in ordered_pairs)
    ipa_text = " ".join(ipa for _, ipa in ordered_pairs)
    return TranslationResult(
        text=conlang_text,
        ipa=ipa_text,
        language=working_language,
        coined=tuple(coined),
        pattern=pattern,
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


def _decode_verb(
    language: Language, token: str, candidate_glosses: frozenset[str] | None = None
) -> tuple[LexicalEntry, str | None] | None:
    """The verb-position counterpart of ``_decode_noun`` -- returns
    ``(entry, tense_label)`` (``None`` for the tense when this language
    has no tense system, or the exact bare form matched). ``candidate_
    glosses``, when given, restricts the search to specific verbs (used
    by ``translate_to_english`` to test "is this token actually the
    copula?" without also matching some unrelated ordinary verb that
    happens to render identically for a different tense/agreement
    combination)."""
    normalized = _normalize(token)
    verb_entries = [e for e in language.lexicon.entries if e.pos is PartOfSpeech.VERB]
    if candidate_glosses is not None:
        verb_entries = [e for e in verb_entries if e.primary_gloss in candidate_glosses]
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

    pattern = "word-for-word"
    ordered_glosses: list[str] | None = None

    if len(tokens) == 3:
        if language.grammar.has_overt_copula:
            # The copula always sits in the *middle* position, regardless
            # of word_order -- see translate_to_conlang's own predicate-
            # adjective handling, which inserts it there unconditionally
            # (word_order only ever governs the *transitive* SVO
            # hypothesis tried below).
            copula_decoded = _decode_verb(language, tokens[1], candidate_glosses=frozenset({"be"}))
            if copula_decoded is not None:
                # Likewise, subject/adjective order here follows
                # adjective_after_noun directly (the same flag the
                # encoder itself reads), not word_order's own S/O
                # positions -- reading it back rather than re-deriving it.
                first_tok, second_tok = tokens[0], tokens[2]
                subject_tok, adj_tok = (
                    (first_tok, second_tok) if language.grammar.adjective_after_noun else (second_tok, first_tok)
                )
                subject_decoded = _decode_noun(language, subject_tok)
                adj_entry = language.lexicon.by_form(adj_tok)  # adjectives are never inflected
                if subject_decoded is not None and adj_entry is not None and adj_entry.pos is PartOfSpeech.ADJECTIVE:
                    _, tense_label = copula_decoded
                    copula_word = "was" if tense_label == "past" else "is"
                    ordered_glosses = [subject_decoded[0].primary_gloss, copula_word, adj_entry.primary_gloss]
                    pattern = "predicate-adjective"
        if ordered_glosses is None:
            roles = _ROLE_ORDER[language.grammar.word_order]
            role_to_token = dict(zip(roles, tokens))
            subject_decoded = _decode_noun(language, role_to_token["S"])
            object_decoded = _decode_noun(language, role_to_token["O"])
            verb_decoded = _decode_verb(language, role_to_token["V"])
            if subject_decoded is not None and object_decoded is not None and verb_decoded is not None:
                verb_entry, tense_label = verb_decoded
                ordered_glosses = [
                    subject_decoded[0].primary_gloss,
                    _english_verb_gloss(verb_entry, tense_label),
                    object_decoded[0].primary_gloss,
                ]
                pattern = "subject-verb-object"
    elif len(tokens) == 2:
        first, second = (language.lexicon.by_form(t) for t in tokens)
        if first is not None and second is not None:
            noun_entry = first if first.pos == PartOfSpeech.NOUN else second
            adj_entry = second if noun_entry is first else first
            ordered_glosses = [noun_entry.primary_gloss, "is", adj_entry.primary_gloss]
            pattern = "predicate-adjective"

    if ordered_glosses is None:
        # Best-effort per-token fallback -- try an exact match, then a
        # generic noun/verb decode, before giving up on that one token;
        # the whole sentence's own structure was either never 2 or 3
        # tokens after stripping articles, or one of the shapes above
        # failed to decode (an unknown coined word, most commonly).
        ordered_glosses = []
        for tok in tokens:
            entry = language.lexicon.by_form(tok)
            if entry is not None:
                ordered_glosses.append(entry.primary_gloss)
                continue
            noun_decoded = _decode_noun(language, tok)
            if noun_decoded is not None:
                ordered_glosses.append(noun_decoded[0].primary_gloss)
                continue
            verb_decoded = _decode_verb(language, tok)
            if verb_decoded is not None:
                ordered_glosses.append(_english_verb_gloss(*verb_decoded))
                continue
            ordered_glosses.append(f"<unknown:{tok}>")

    draft = " ".join(ordered_glosses)
    request = LLMRequest(
        system=(
            "You turn a rough English gloss sequence from a constructed-"
            "language translation into one natural English sentence. Keep "
            "the meaning; do not add new content."
        ),
        prompt=f"Rough gloss sequence: {draft}\nWrite a natural English sentence:",
        model=DEFAULT_MODEL,
        max_tokens=64,
        purpose="translate.fluency",
        metadata={"fake_strategy": "passthrough", "fallback_text": draft},
    )
    response = llm_client.complete(request)
    return TranslationResult(
        text=response.text, ipa="", language=language, coined=(), pattern=pattern
    )
