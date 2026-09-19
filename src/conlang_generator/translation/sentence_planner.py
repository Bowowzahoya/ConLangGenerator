"""Plans a sentence's own *structure* before ``translator.py`` renders its
phonology.

The LLM's only job here is to decide word order, which arguments (if any)
get case-marked, whether an article/copula/negation/conjunction appears,
and which tense/agreement a finite verb takes -- never to invent an actual
foreign word form itself. Its output is a ``SentencePlan``: an ordered list
of ``PlannedSlot``s, each naming an English lemma/role or a function-word
kind, that ``translation.translator.translate_to_conlang`` walks and
renders via the *existing*, already-tested rendering primitives
(``_lookup_or_coin``, ``_apply_case``, ``_apply_verb_inflection``) -- the
same "LLM picks among/describes deterministically-built material" boundary
``generation/lexicon_gen.py``'s own module docstring already establishes.

Parsing is lenient by design, mirroring ``generation/prompt_classifier.py``'s
own ``_parse``: a malformed field degrades to a safe default rather than
raising, and a totally unparseable response (or one with zero usable slots)
falls back to a trivial one-slot-per-content-word plan -- the same
word-for-word safety net ``translator.py`` always had.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.llm.base import LLMClient, LLMRequest
from conlang_generator.llm.pricing import DEFAULT_MODEL

POS_BY_PLAN_STRING: dict[str, PartOfSpeech] = {
    "noun": PartOfSpeech.NOUN,
    "verb": PartOfSpeech.VERB,
    "adjective": PartOfSpeech.ADJECTIVE,
    "pronoun": PartOfSpeech.PRONOUN,
    "numeral": PartOfSpeech.NUMERAL,
    "adverb": PartOfSpeech.PARTICLE,
    "preposition": PartOfSpeech.PARTICLE,
    "other": PartOfSpeech.OTHER,
}
"""Maps a ``PlannedSlot.pos`` string (JSON-friendly, what the LLM/parser
actually produces) to the real ``core.lexicon.PartOfSpeech`` enum
``translator.py``'s rendering step needs -- kept here, not in
``translator.py``, since this module owns the plan's own string vocabulary."""

_SLOT_KINDS = ("content", "article", "copula", "negation", "conjunction")

_ARTICLES = {"a", "an", "the"}


@dataclass(frozen=True)
class PlannedSlot:
    kind: str
    """One of ``"content"`` (an ordinary word), ``"article"`` (this
    language's own "the"), ``"copula"`` (this language's own "be"),
    ``"negation"`` (this language's own "not"), ``"conjunction"`` (this
    language's own "and")."""
    gloss: str = ""
    """The base English lemma (e.g. "see", not "saw") -- only meaningful
    for ``kind="content"``."""
    pos: str = ""
    """One of ``POS_BY_PLAN_STRING``'s own keys -- only meaningful for
    ``kind="content"``."""
    case: str | None = None
    """One of this language's own real ``GrammarProfile.cases`` labels, or
    ``None`` -- only ever meaningful on a noun/pronoun argument."""
    tense: str | None = None
    """One of this language's own real ``GrammarProfile.tenses`` labels, or
    ``None`` -- only ever meaningful on a finite verb or the copula."""
    agreement: str | None = None
    """One of ``generation.inflection_gen.AGREEMENT_LABELS``, or ``None``
    -- only ever meaningful on a finite verb or the copula."""


@dataclass(frozen=True)
class SentencePlan:
    slots: tuple[PlannedSlot, ...]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def _word_for_word_fallback(text: str) -> SentencePlan:
    """The final safety net -- one bare, uninflected content slot per
    English content word, in the original order, matching the naive
    word-for-word fallback ``translator.py`` always had for input it
    couldn't otherwise structure."""
    tokens = [t for t in _tokenize(text) if t not in _ARTICLES]
    return SentencePlan(slots=tuple(PlannedSlot(kind="content", gloss=t, pos="noun") for t in tokens))


def _build_system_prompt(language: Language) -> str:
    grammar = language.grammar
    cases_desc = ", ".join(grammar.cases) if grammar.cases else 'none -- never set "case" on anything'
    tenses_desc = (
        ", ".join(grammar.tenses) if grammar.tenses else 'none -- never set "tense" on anything'
    )
    optional_kinds = []
    if grammar.has_articles:
        optional_kinds.append('"article" (a definite-article slot -- no other field needed)')
    if grammar.has_overt_copula:
        optional_kinds.append('"copula" ("to be" -- takes "tense"/"agreement" like a finite verb)')
    optional_desc = (
        "; ".join(optional_kinds)
        if optional_kinds
        else "none -- this language has neither articles nor an overt copula; "
        'never emit an "article" or "copula" slot'
    )

    return f"""You plan the *structure* of one sentence's translation into a \
constructed language -- word order, which arguments get case-marked, \
whether an article/copula/negation/conjunction appears -- as an ordered \
JSON list of word "slots". You never invent the actual foreign word forms \
yourself; a separate, deterministic step looks up or coins each word and \
applies whatever case/tense/agreement marking you specify.

This specific target language's own real grammar:
- word_order: {grammar.word_order.value} -- place content in this order, \
except an inserted copula always sits directly between the subject and the \
predicate adjective, regardless of word_order.
- alignment: {grammar.alignment.value}.
- grammatical cases this language actually has: {cases_desc}.
- tenses this language actually has: {tenses_desc}.
- adjective_after_noun: {grammar.adjective_after_noun} -- a predicate \
adjective's own position relative to its subject.
- optional slot kinds available in this language: {optional_desc}.

Every slot is a JSON object with a "kind" field: "content", "article", \
"negation", "conjunction" are always available; "copula" only when listed \
above. A "content" slot also needs "gloss" (the base English lemma, e.g. \
"see" not "saw", "mountain" not "mountains") and "pos" (one of "noun", \
"verb", "adjective", "pronoun", "numeral", "adverb", "preposition", "other"). Never drop a meaningful word: degree words and adverbs ("very", "extremely", "quickly"), prepositions ("in", "on"), and every other content word each get their own "content" slot (pos "adverb"/"preposition"), placed next to the word they modify (a degree adverb directly before its adjective). A "content" slot may \
also set "case" (one of this language's own cases above -- only on a \
noun/pronoun argument, and only when this sentence's own alignment \
actually calls for marking that particular argument; omit otherwise). A \
"content" slot whose "pos" is "verb", or a "copula" slot, may set "tense" \
(one of this language's own tenses above) and "agreement" (one of "I", \
"you", "he", "we", "default" -- "default" for any subject that isn't \
literally one of the first three pronouns, the ordinary cross-linguistic \
"3rd person is unmarked" pattern). Never set "case" on a verb, or \
"tense"/"agreement" on anything but a finite verb or the copula. Never \
emit an "article" slot immediately next to a pronoun (I/you/he/we/this/\
that) -- no real language does this, even when the English input itself \
used "the".

Five worked examples (illustrative field values only -- always use *this* \
language's own real case/tense labels listed above, never these \
placeholder names, and only emit "article"/"copula" slots when this \
language actually has them):

"I see the mountain" (a transitive sentence -- only one argument is ever \
case-marked, matching this language's own alignment: the object under \
nominative-accusative, or the subject under ergative-absolutive) -> \
[{{"kind":"content","gloss":"I","pos":"pronoun"}}, {{"kind":"content",\
"gloss":"see","pos":"verb","tense":"<a real tense label>",\
"agreement":"I"}}, {{"kind":"article"}}, {{"kind":"content",\
"gloss":"mountain","pos":"noun","case":"<a real case label, if this \
alignment marks the object>"}}]

"the mountain is high" (a predicate-adjective sentence -- the copula, \
when this language has one, always sits between the subject and the \
predicate) -> [{{"kind":"article"}}, {{"kind":"content","gloss":"mountain",\
"pos":"noun"}}, {{"kind":"copula","tense":"<a real tense label>",\
"agreement":"default"}}, {{"kind":"content","gloss":"high",\
"pos":"adjective"}}] -- reorder the subject/copula/adjective slots to \
match this language's own adjective_after_noun above.

"the mountain is not high" (negation is one standalone particle slot, \
placed next to the predicate it negates) -> [{{"kind":"article"}}, \
{{"kind":"content","gloss":"mountain","pos":"noun"}}, {{"kind":"copula",\
"tense":"<a real tense label>","agreement":"default"}}, \
{{"kind":"negation"}}, {{"kind":"content","gloss":"high",\
"pos":"adjective"}}]

"I am very tired" (a degree adverb keeps its own slot right before the adjective it modifies -- never omit it) -> [{{"kind":"content","gloss":"I","pos":"pronoun"}}, {{"kind":"copula","tense":"<a real tense label>","agreement":"I"}}, {{"kind":"content","gloss":"very","pos":"adverb"}}, {{"kind":"content","gloss":"tired","pos":"adjective"}}]

"I see the mountain and the river" (coordination -- each coordinated noun \
phrase repeats its own article/case exactly as if it stood alone) -> \
[{{"kind":"content","gloss":"I","pos":"pronoun"}}, {{"kind":"content",\
"gloss":"see","pos":"verb","tense":"<...>","agreement":"I"}}, \
{{"kind":"article"}}, {{"kind":"content","gloss":"mountain","pos":"noun",\
"case":"<...>"}}, {{"kind":"conjunction"}}, {{"kind":"article"}}, \
{{"kind":"content","gloss":"river","pos":"noun","case":"<...>"}}]

Respond with ONLY a single JSON array of slot objects, no prose, no \
markdown fences."""


def plan_sentence(text: str, language: Language, llm_client: LLMClient) -> SentencePlan:
    grammar = language.grammar
    request = LLMRequest(
        system=_build_system_prompt(language),
        prompt=text,
        model=DEFAULT_MODEL,
        max_tokens=500,
        purpose="translate.plan_sentence",
        metadata={
            "fake_strategy": "sentence_plan",
            "word_order": grammar.word_order.value,
            "alignment": grammar.alignment.value,
            "cases": ",".join(grammar.cases),
            "tenses": ",".join(grammar.tenses),
            "has_articles": "true" if grammar.has_articles else "false",
            "has_overt_copula": "true" if grammar.has_overt_copula else "false",
            "adjective_after_noun": "true" if grammar.adjective_after_noun else "false",
        },
    )
    response = llm_client.complete(request)
    plan = _parse(response.text)
    if plan is None:
        return _word_for_word_fallback(text)
    return plan


def _coerce_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _parse(text: str) -> SentencePlan | None:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match is None:
        return None
    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, list):
        return None

    slots: list[PlannedSlot] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind not in _SLOT_KINDS:
            continue
        gloss = item.get("gloss")
        gloss = gloss.strip().lower() if isinstance(gloss, str) else ""
        pos = item.get("pos")
        pos = pos if pos in POS_BY_PLAN_STRING else "noun"
        slots.append(
            PlannedSlot(
                kind=kind,
                gloss=gloss,
                pos=pos,
                case=_coerce_optional_str(item.get("case")),
                tense=_coerce_optional_str(item.get("tense")),
                agreement=_coerce_optional_str(item.get("agreement")),
            )
        )
    if not slots:
        return None
    return SentencePlan(slots=tuple(slots))


__all__ = ["PlannedSlot", "SentencePlan", "POS_BY_PLAN_STRING", "plan_sentence"]
