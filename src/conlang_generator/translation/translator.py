"""English <-> conlang translation.

Explicit v0 limitations, by design:

- No real parser. Exactly three sentence shapes are recognized: a two-content-
  word predicate-adjective sentence ("the mountain is high"), a three-
  content-word subject-verb-object sentence ("I see the mountain"), and
  everything else falls back to naive word-for-word substitution in the
  original order.
- English tokens are matched to glosses via exact match or a trailing-``s``
  strip -- no real lemmatization.
- Conlang -> English reconstruction assumes the *English* side is always
  canonical SVO; this is a simplification, not a model of English syntax.

Unknown *English* content words trigger word coinage (see ``expansion.py``);
unknown *conlang* words cannot be reverse-coined (there is no English gloss to
coin from) and surface as ``<unknown:...>`` in the rough gloss line.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from conlang_generator.core.grammar import WordOrder
from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from conlang_generator.llm.base import LLMClient, LLMRequest
from conlang_generator.llm.pricing import DEFAULT_MODEL
from conlang_generator.translation import expansion

_ARTICLES = {"a", "an", "the"}
_COPULAS = {"is", "are", "am", "was", "were", "be", "been", "being"}

_ROLE_ORDER: dict[WordOrder, tuple[str, str, str]] = {
    WordOrder.SOV: ("S", "O", "V"),
    WordOrder.SVO: ("S", "V", "O"),
    WordOrder.VSO: ("V", "S", "O"),
    WordOrder.VOS: ("V", "O", "S"),
    WordOrder.OVS: ("O", "V", "S"),
    WordOrder.OSV: ("O", "S", "V"),
}


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


def _lemma_candidates(token: str) -> list[str]:
    candidates = [token]
    if token.endswith("s") and len(token) > 1:
        candidates.append(token[:-1])
    return candidates


def _lookup_or_coin(
    language: Language,
    token: str,
    pos: PartOfSpeech,
    coined: list[LexicalEntry],
    llm_client: LLMClient,
) -> tuple[Language, LexicalEntry]:
    for candidate in _lemma_candidates(token):
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
    tokens = [t for t in raw_tokens if t not in _ARTICLES]
    has_copula = any(t in _COPULAS for t in tokens)
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
        ordered = (
            [subject_entry, adj_entry]
            if working_language.grammar.adjective_after_noun
            else [adj_entry, subject_entry]
        )
        pattern = "predicate-adjective"
    elif len(content_tokens) == 3:
        subject_tok, verb_tok, obj_tok = content_tokens
        working_language, subject_entry = _lookup_or_coin(
            working_language, subject_tok, PartOfSpeech.NOUN, coined, llm_client
        )
        working_language, verb_entry = _lookup_or_coin(
            working_language, verb_tok, PartOfSpeech.VERB, coined, llm_client
        )
        working_language, obj_entry = _lookup_or_coin(
            working_language, obj_tok, PartOfSpeech.NOUN, coined, llm_client
        )
        roles = {"S": subject_entry, "V": verb_entry, "O": obj_entry}
        ordered = [roles[r] for r in _ROLE_ORDER[working_language.grammar.word_order]]
        pattern = "subject-verb-object"
    else:
        ordered = []
        for tok in content_tokens:
            working_language, entry = _lookup_or_coin(
                working_language, tok, PartOfSpeech.NOUN, coined, llm_client
            )
            ordered.append(entry)
        pattern = "word-for-word"

    conlang_text = " ".join(e.romanization for e in ordered)
    ipa_text = " ".join(e.ipa for e in ordered)
    return TranslationResult(
        text=conlang_text,
        ipa=ipa_text,
        language=working_language,
        coined=tuple(coined),
        pattern=pattern,
    )


def translate_to_english(
    text: str, language: Language, llm_client: LLMClient
) -> TranslationResult:
    tokens = unicodedata.normalize("NFC", text).strip().split()
    entries: list[LexicalEntry | None] = [language.lexicon.by_form(tok) for tok in tokens]
    known = [e for e in entries if e is not None]
    pattern = "word-for-word"

    if len(entries) == 3 and len(known) == 3:
        roles = _ROLE_ORDER[language.grammar.word_order]
        role_to_entry = dict(zip(roles, entries))
        ordered_glosses = [
            role_to_entry["S"].primary_gloss,
            role_to_entry["V"].primary_gloss,
            role_to_entry["O"].primary_gloss,
        ]
        pattern = "subject-verb-object"
    elif len(entries) == 2 and len(known) == 2:
        first, second = entries
        noun_entry = first if first.pos == PartOfSpeech.NOUN else second
        adj_entry = second if noun_entry is first else first
        ordered_glosses = [noun_entry.primary_gloss, "is", adj_entry.primary_gloss]
        pattern = "predicate-adjective"
    else:
        ordered_glosses = [
            entry.primary_gloss if entry is not None else f"<unknown:{tok}>"
            for entry, tok in zip(entries, tokens)
        ]

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
