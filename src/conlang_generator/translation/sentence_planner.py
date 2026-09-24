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

_SLOT_KINDS = (
    "content", "article", "copula", "negation", "conjunction", "name", "clause", "demonstrative",
    "indefinite_article",
)

NUMBER_LABELS = ("plural", "dual")

MAX_CLAUSE_DEPTH = 3
"""How deeply a clause slot may nest inside another. A clause nested deeper is
flattened into its parent's slots (its own words are kept, only the linking
word and the nesting are lost) rather than dropped."""

CLAUSE_ROLES = ("complement", "relative", "adverbial")

_ARTICLES = {"a", "an", "the"}


@dataclass(frozen=True)
class PlannedSlot:
    kind: str
    """One of ``"content"`` (an ordinary word), ``"article"`` (this
    language's own "the"), ``"copula"`` (this language's own "be"),
    ``"negation"`` (this language's own "not"), ``"conjunction"`` (this
    language's own "and"), ``"name"`` (a foreign proper name, handled per
    the language's ``foreign_names`` trait -- see ``translation/names.py``),
    ``"clause"`` (a subordinate clause nested inside this one -- see
    ``clause``)."""
    gloss: str = ""
    """The base English lemma (e.g. "see", not "saw") for ``kind="content"``;
    the name exactly as written, capitalization kept, for ``kind="name"``;
    the linking word ("that", "because", "if", "when", "which", ...) for
    ``kind="clause"`` (empty when the clause needs none)."""
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
    number: str | None = None
    """``"plural"``, ``"dual"`` or ``None`` (singular, unmarked) -- only ever
    meaningful on a noun ("content" with pos "noun"); a label the language
    lacks is ignored at render time."""
    possessive: bool = False
    """On the possessor of a possession phrase ("my dog": the pronoun slot
    "I"; "Bruno's leg": the name slot): the renderer marks the possession
    per the language's own strategy (genitive case, a particle after the
    possessor, or an affix on the possessed noun that follows)."""
    aspect: str | None = None
    """One of this language's own ``GrammarProfile.aspects`` labels, or
    ``None`` -- only ever meaningful on a finite verb or the copula."""
    verb_mood: str | None = None
    """One of this language's own ``GrammarProfile.moods`` labels (never
    ``"imperative"``, which is the sentence's mood), or ``None`` -- only
    ever meaningful on a finite verb or the copula."""
    agrees_with: str | None = None
    """For an adjective: the lemma of the noun it modifies or is predicated
    of (only set in a language with noun classes)."""
    subject_gloss: str | None = None
    """For a finite verb or the copula whose subject is an ordinary noun (not a
    pronoun or name): that noun's lemma, so the verb can agree with its
    class (only set in a language with noun classes)."""
    object_gloss: str | None = None
    """For a finite verb in a language with object agreement: the lemma of
    its direct object (a noun, or a pronoun I/you/he/we)."""
    clause: SentencePlan | None = None
    """For ``kind="clause"``: the subordinate clause's own plan (its slots are
    rendered in place; its ``mood`` is ignored -- only a main clause can be an
    imperative or a question)."""
    role: str | None = None
    """For ``kind="clause"``: one of ``CLAUSE_ROLES`` (informational; all three
    render the same way, a linking word plus the nested clause)."""


MOODS = ("declarative", "imperative", "question", "wh_question")
"""``"question"`` is a yes/no question (gets the language's question
particle); ``"wh_question"`` is a content question whose own question word
("what", "who", ...) is an ordinary content slot and takes no particle."""


@dataclass(frozen=True)
class SentencePlan:
    slots: tuple[PlannedSlot, ...]
    mood: str = "declarative"


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    """Splits on sentence-final punctuation followed by whitespace, keeping
    the punctuation on each sentence (it is the planner's cue for mood).
    Empty input yields no sentences; text with no terminal punctuation is
    one sentence."""
    return [part.strip() for part in _SENTENCE_SPLIT.split(text.strip()) if part.strip()]


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
    aspects_desc = (
        ", ".join(grammar.aspects) if grammar.aspects else 'none -- never set "aspect" on anything'
    )
    moods_desc = (
        ", ".join(grammar.moods) if grammar.moods else 'none -- never set "verb_mood" on anything'
    )
    classes_desc = (
        ", ".join(grammar.noun_classes)
        if grammar.noun_classes
        else 'none -- never set "agrees_with", "subject_gloss" or "object_gloss"'
    )
    object_agreement_desc = (
        "yes" if grammar.object_agreement else 'no -- never set "object_gloss"'
    )
    number_desc = "plural" + (" and dual" if any(a.label == "dual" for a in grammar.number_affixes) else "")
    demonstrative_desc = "AFTER" if grammar.demonstrative_after_noun else "BEFORE"
    adposition_desc = (
        "POSTPOSITIONS: an adposition slot goes AFTER its noun phrase"
        if grammar.postpositional
        else "PREPOSITIONS: an adposition slot goes BEFORE its noun phrase"
    )
    possession_desc = {
        "genitive": "the possessor takes the genitive case (the renderer does it)",
        "particle": "a possessive particle follows the possessor (the renderer adds it)",
        "affix": "the possessed noun takes a suffix (the renderer adds it)",
        "none": "the possessor simply stands next to the possessed noun",
    }.get(grammar.possession, "the possessor simply stands next to the possessed noun")
    numeral_desc = (
        "a noun after a numeral above one still takes the plural"
        if grammar.plural_after_numeral
        else "a noun after a numeral above one stays singular (the renderer drops the number)"
    )
    optional_kinds = []
    if grammar.has_indefinite_article:
        optional_kinds.append('"indefinite_article" (English "a"/"an" -- no other field needed)')
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
- aspects this language actually has: {aspects_desc}.
- number: singular is unmarked; this language has {number_desc}.
- demonstratives come {demonstrative_desc} their noun; adpositions are {adposition_desc}; numerals stand directly before their noun ({numeral_desc}).
- possession: {possession_desc}.
- noun classes this language actually has: {classes_desc}. A noun's class \
is worked out by a separate step from its lemma; articles and adjectives \
agree with it, and so can a verb.
- the verb also agrees with its direct object: {object_agreement_desc}.
- verbal moods (other than the imperative) this language actually has: \
{moods_desc}.
- adjective_after_noun: {grammar.adjective_after_noun} -- a predicate \
adjective's own position relative to its subject.
- optional slot kinds available in this language: {optional_desc}.

Every slot is a JSON object with a "kind" field: "content", "article", \
"negation", "conjunction", "name" are always available; "copula" only when listed \
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

A noun that is plural in the English ("mountains", "the dogs") is ONE "content" slot with the singular lemma as "gloss" and "number":"plural" (never the plural spelling as the gloss, and never omit the number). Singular nouns have no "number" field.

A finite verb or copula slot may also set "aspect" (one of this \
language's own aspects above, chosen by the English wording: progressive \
"is seeing" -> progressive, or imperfective if that is the closest label \
available; perfect "has seen" -> perfect, or perfective; simple past or \
completed events -> perfective; "used to"/"usually" -> habitual, or \
imperfective) and "verb_mood" (one of this language's own verbal moods \
above: "would see" -> conditional; "may/can see" -> potential; a wish or \
"if I were" -> subjunctive; any of these -> irrealis when that is the only \
label). Tense and aspect are independent: "I was seeing" is tense past + \
aspect progressive. Omit "aspect"/"verb_mood" when the English is plain, or \
when this language has no fitting label. Never write English auxiliaries \
("have", "would", "may", "is" before -ing) as their own slots: they are \
expressed only through these fields.

Noun-phrase pieces, each its own slot placed next to its noun as the bullets above say: a demonstrative is {{"kind":"demonstrative","gloss":"this"}} or "that" ("these"/"those" are the demonstrative plus the noun with "number":"plural"); a numeral is an ordinary "content" slot with pos "numeral" ("two dogs": numeral two, then dog with "number" -- "dual" when exactly two and the language has a dual, otherwise "plural"); an English "a"/"an" is an "indefinite_article" slot only when this language has one, otherwise nothing. Possession ("my dog", "the dog's bone", "Bruno's leg"): the possessor is its own slot with "possessive":true placed directly before the possessed noun -- for a pronoun possessor the pronoun itself ("my" -> the pronoun "I", "your" -> "you", "his"/"her" -> "he", "our" -> "we", "their" -> "they"). Never add the possessive marking yourself.

Agreement (only where the two bullets above allow it): an adjective slot \
sets "agrees_with" to the lemma of the noun it modifies or, as a predicate, \
of the sentence's subject ("the red dog": agrees_with "dog"). A finite verb \
or copula whose subject is an ordinary noun (not a pronoun, not a name) \
keeps "agreement":"default" and sets "subject_gloss" to that noun's lemma; \
in a language with object agreement a finite verb also sets "object_gloss" \
to the lemma of its direct object (a pronoun object is "I", "you", "he" or \
"we"). Articles need nothing: the renderer agrees them with the next noun.

The sentence's "mood" is one of: "declarative" (the default), "imperative" (a command or request addressed to someone: the finite verb is a content slot with pos "verb" and NO "tense"/"agreement"; the subject "you" is left out), "question" (a yes/no question), "wh_question" (a question whose question word -- what, who, where, why, how -- is its own content slot, pos "pronoun" or "adverb"). Do not add any word for the mood yourself: a separate step adds this language's own question particle or imperative marking. A noun of direct address ("My friend, come here") is an ordinary noun content slot placed first, with no case.

A subordinate clause is ONE slot {{"kind":"clause","gloss":"<linking word>",\
"role":"<role>","clause":{{"slots":[...]}}}} whose "clause" holds that \
clause's own slots, ordered per this language's word order exactly like a \
main clause (its own subject, verb with tense/agreement, objects; nested \
clauses may nest again). "role" is "complement" ("I think THAT you are \
tired"; gloss "that"), "adverbial" ("because"/"if"/"when"/"although"/\
"while" as the gloss) or "relative" ("the man WHO sleeps"; gloss "who"/\
"which"/"that"). Never flatten a subordinate clause into the main clause's \
slots. Put a complement or adverbial clause slot after the main clause's own \
slots; put a relative clause slot directly after the noun it modifies. \
Do not repeat the linking word as a separate slot; the renderer places it \
per this language's own word order. A clause never has its own "mood".

Proper names of people and places (Bruno, Maria, Amsterdam) get a "name" \
slot with "gloss" set to the name exactly as written -- never translate, \
respell, or turn a name into a content word. A capitalized word at the \
very start of the sentence is a name only if it is not an ordinary English \
word ("Just", "You", "Come" are not names). A "name" slot may also set \
"case" like a noun. A possessor name ("Bruno's leg") is a name slot with \
"possessive":true directly before the possessed noun's own slot.

Worked examples (illustrative field values only -- always use *this* \
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

"I see Bruno" (a proper name is a "name" slot, case-marked like any \
object) -> [{{"kind":"content","gloss":"I","pos":"pronoun"}}, \
{{"kind":"content","gloss":"see","pos":"verb","tense":"<a real tense \
label>","agreement":"I"}}, {{"kind":"name","gloss":"Bruno","case":"<a real \
case label, if this alignment marks the object>"}}]

"I am very tired" (a degree adverb keeps its own slot right before the adjective it modifies -- never omit it) -> [{{"kind":"content","gloss":"I","pos":"pronoun"}}, {{"kind":"copula","tense":"<a real tense label>","agreement":"I"}}, {{"kind":"content","gloss":"very","pos":"adverb"}}, {{"kind":"content","gloss":"tired","pos":"adjective"}}]

"I see the mountain and the river" (coordination -- each coordinated noun \
phrase repeats its own article/case exactly as if it stood alone) -> \
[{{"kind":"content","gloss":"I","pos":"pronoun"}}, {{"kind":"content",\
"gloss":"see","pos":"verb","tense":"<...>","agreement":"I"}}, \
{{"kind":"article"}}, {{"kind":"content","gloss":"mountain","pos":"noun",\
"case":"<...>"}}, {{"kind":"conjunction"}}, {{"kind":"article"}}, \
{{"kind":"content","gloss":"river","pos":"noun","case":"<...>"}}]

"Come to the mountains!" (an imperative -- no subject, verb without \
tense/agreement; a plural noun carries "number") -> mood "imperative", \
[{{"kind":"content","gloss":"come","pos":"verb"}}, {{"kind":"content",\
"gloss":"to","pos":"preposition"}}, {{"kind":"article"}}, {{"kind":"content",\
"gloss":"mountain","pos":"noun","number":"plural"}}]

"I think you are tired" -> [{{"kind":"content","gloss":"I","pos":"pronoun"}}, \
{{"kind":"content","gloss":"think","pos":"verb","tense":"<...>",\
"agreement":"I"}}, {{"kind":"clause","gloss":"that","role":"complement",\
"clause":{{"slots":[{{"kind":"content","gloss":"you","pos":"pronoun"}}, \
{{"kind":"copula","tense":"<...>","agreement":"you"}}, {{"kind":"content",\
"gloss":"tired","pos":"adjective"}}]}}}}]

The examples above show only the slot array. Respond with ONLY a single \
JSON object {{"mood": "<mood>", "slots": [<slot objects>]}}, no prose, no \
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
            "aspects": ",".join(grammar.aspects),
            "has_indefinite_article": "true" if grammar.has_indefinite_article else "false",
            "demonstrative_after_noun": "true" if grammar.demonstrative_after_noun else "false",
            "number_labels": ",".join(a.label for a in grammar.number_affixes),
            "possession": grammar.possession,
            "noun_classes": ",".join(grammar.noun_classes),
            "object_agreement": "true" if grammar.object_agreement else "false",
            "verb_moods": ",".join(grammar.moods),
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


def _lemma(value: object) -> str | None:
    return value.strip().lower() if isinstance(value, str) and value.strip() else None


def _coerce_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _parse(text: str) -> SentencePlan | None:
    mood = "declarative"
    raw: object = None
    obj_match = re.search(r"\{.*\}", text, re.DOTALL)
    if obj_match is not None:
        try:
            parsed = json.loads(obj_match.group(0))
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and isinstance(parsed.get("slots"), list):
            raw = parsed["slots"]
            if parsed.get("mood") in MOODS:
                mood = parsed["mood"]
    if raw is None:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match is None:
            return None
        try:
            raw = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, list):
        return None

    slots = _slots_from_raw(raw, depth=0)
    if not slots:
        return None
    return SentencePlan(slots=tuple(slots), mood=mood)


def _raw_slot_list(value: object) -> list | None:
    if isinstance(value, dict):
        value = value.get("slots")
    return value if isinstance(value, list) else None


def _slots_from_raw(raw: list, depth: int) -> list[PlannedSlot]:
    slots: list[PlannedSlot] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind not in _SLOT_KINDS:
            continue
        if kind == "clause":
            nested_raw = _raw_slot_list(item.get("clause"))
            nested = _slots_from_raw(nested_raw, depth + 1) if nested_raw is not None else []
            if not nested:
                continue
            if depth + 1 >= MAX_CLAUSE_DEPTH:
                slots.extend(nested)  # too deep: keep the words, lose the nesting
                continue
            linker = item.get("gloss")
            role = item.get("role")
            slots.append(
                PlannedSlot(
                    kind="clause",
                    gloss=linker.strip().lower() if isinstance(linker, str) else "",
                    pos="other",
                    role=role if role in CLAUSE_ROLES else None,
                    clause=SentencePlan(slots=tuple(nested)),
                )
            )
            continue
        gloss = item.get("gloss")
        gloss = ((gloss.strip() if kind == "name" else gloss.strip().lower()) if isinstance(gloss, str) else "")
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
                number=item.get("number") if item.get("number") in NUMBER_LABELS else None,
                possessive=item.get("possessive") is True,
                aspect=_coerce_optional_str(item.get("aspect")),
                verb_mood=_coerce_optional_str(item.get("verb_mood")),
                agrees_with=_lemma(item.get("agrees_with")),
                subject_gloss=_lemma(item.get("subject_gloss")),
                object_gloss=_lemma(item.get("object_gloss")),
            )
        )
    return slots


def flatten_slots(plan: SentencePlan) -> list[PlannedSlot]:
    """Every non-clause slot of ``plan`` in reading order, nested clauses
    expanded in place -- for callers that only need the words."""
    flat: list[PlannedSlot] = []
    for slot in plan.slots:
        if slot.kind == "clause" and slot.clause is not None:
            flat.extend(flatten_slots(slot.clause))
        else:
            flat.append(slot)
    return flat


__all__ = ["NUMBER_LABELS", "CLAUSE_ROLES", "MAX_CLAUSE_DEPTH", "flatten_slots", "MOODS", "PlannedSlot", "SentencePlan", "POS_BY_PLAN_STRING", "plan_sentence", "split_sentences"]
