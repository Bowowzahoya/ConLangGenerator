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
from conlang_generator.generation import pronoun_gen, subordination_gen
from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.llm.base import LLMClient, LLMRequest
from conlang_generator.llm.pricing import DEFAULT_MODEL

POS_BY_PLAN_STRING: dict[str, PartOfSpeech] = {
    "noun": PartOfSpeech.NOUN,
    "verb": PartOfSpeech.VERB,
    "adjective": PartOfSpeech.ADJECTIVE,
    "pronoun": PartOfSpeech.PRONOUN,
    "numeral": PartOfSpeech.NUMERAL,
    "quantifier": PartOfSpeech.NUMERAL,
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
    "indefinite_article", "possessive_pronoun",
)

NUMBER_LABELS = ("plural", "dual")

MAX_CLAUSE_DEPTH = 3
"""How deeply a clause slot may nest inside another. A clause nested deeper is
flattened into its parent's slots (its own words are kept, only the linking
word and the nesting are lost) rather than dropped."""

CLAUSE_ROLES = ("complement", "relative", "adverbial", "nominal", "coordinate")
RELATIVE_FUNCTION_LABELS = ("subject", "object", "oblique", "possessor")

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
    evidential: str | None = None
    """One of this language's own ``GrammarProfile.evidentials`` labels (the
    source of the speaker's information), or ``None`` -- only ever meaningful
    on a finite verb or the copula."""
    verb_mood: str | None = None
    """One of this language's own ``GrammarProfile.moods`` labels (never
    ``"imperative"``, which is the sentence's mood), or ``None`` -- only
    ever meaningful on a finite verb or the copula."""
    subject_number: str | None = None
    """``"plural"`` on a finite verb whose subject is plural, in a language
    whose verbs agree in number."""
    polite: bool = False
    """On a finite verb whose subject is ``you-polite``, in a language whose
    verbs carry politeness."""
    rel_function: str | None = None
    """On a relative clause slot: the position of the relativized noun inside
    its own clause (``subject``, ``object``, ``oblique``, ``possessor``)."""
    verb_form: str | None = None
    """``"infinitive"``, ``"nominalized"`` or ``"participle"``: a non-finite verb
    (no tense or agreement), only in a language that has that form -- the verb of
    a same-subject complement ("I want TO SEE"), a nominalized clause, or a
    reduced relative ("the man SLEEPING")."""
    voice: str | None = None
    """One of this language's own ``GrammarProfile.voices`` labels
    (``passive``/``antipassive``/``causative``), or ``None`` for the active --
    only ever meaningful on a finite verb. The planner also reassigns the
    arguments (subject, case marking, the agent phrase) to match."""
    degree: str | None = None
    """``"comparative"`` or ``"superlative"`` on an adjective, in a language
    that marks that degree with a suffix (otherwise the planner uses a word
    slot "more"/"most" and leaves this ``None``)."""
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
    evidentials_desc = (
        ", ".join(grammar.evidentials) if grammar.evidentials else 'none -- never set "evidential" on anything'
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
    voices_desc = (
        ", ".join(grammar.voices) if grammar.voices else 'none -- never set "voice" on anything'
    )
    existential_desc = (
        'X followed by a finite "content" verb with gloss "exist" (pos "verb", tense/agreement like any verb; '
        "agreement with X)"
        if grammar.existential == "verb"
        else (
            "X followed by the copula slot (agreement with X)"
            if grammar.has_overt_copula
            else "just the noun phrase X (this language has no overt copula)"
        )
    )
    dative_desc = 'the dative case ("case":"dative")' if "dative" in grammar.cases else (
        'possessor marking ("possessive":true on the possessor slot, as for "my dog")'
    )
    possession_clause_desc = (
        'a transitive sentence whose verb is the content verb "have" (pos "verb"): the possessor is the subject '
        "and the possessed is the object, case-marked as for any transitive sentence"
        if grammar.possession_clause == "have"
        else (
            f"there is no verb \"have\": the possessor comes FIRST, taking {dative_desc}, followed by the "
            "existential construction above whose X is the possessed noun phrase (a plain subject: no object case)"
        )
    )
    comparative_desc = (
        'set "degree":"comparative" on the adjective slot (this language has a comparative suffix)'
        if grammar.comparative_marking == "affix"
        else 'put a content slot with gloss "more" and pos "adverb" directly before the adjective'
    )
    superlative_desc = (
        'set "degree":"superlative" on the adjective slot (this language has a superlative suffix)'
        if grammar.superlative_marking == "affix"
        else 'put a content slot with gloss "most" and pos "adverb" directly before the adjective'
    )
    standard_desc = {
        "particle": (
            'a content slot with gloss "than" and pos "preposition" together with the standard noun phrase '
            "(placed per this language's adposition order)"
        ),
        "case": f'the standard noun phrase takes the "{grammar.comparative_case}" case (no extra word)',
        "exceed": (
            'no word for "than": after the adjective put a content verb with gloss "exceed" (pos "verb", '
            "tense/agreement like any verb) whose object is the standard noun phrase, and no copula is needed"
        ),
    }.get(grammar.comparative_strategy, "the standard noun phrase, unmarked")
    pronoun_list = ", ".join(pronoun_gen.pronoun_glosses(grammar))
    pronoun_rules = [
        'English "he/him" -> "he"',
        'English "she" -> ' + ('"she"' if grammar.third_person_gender else '"he" (no separate "she")'),
        'English "it" (a personal subject/object) -> ' + ('"it"' if grammar.third_person_gender else '"he"'),
        'English "they/them" -> "they"',
        'English "you" addressing one person -> "you"'
        + (
            ' (or "you-polite" when addressing someone with respect: a stranger, a superior, "sir", "madam")'
            if grammar.honorific_you
            else ""
        ),
        'English "you" addressing several people ("you all", "you guys") -> "you-plural"',
        'English "we/us" -> '
        + (
            '"we-inclusive" when the listener is part of the group, otherwise "we-exclusive"'
            if grammar.clusivity
            else '"we"'
        ),
    ]
    pronoun_rules_text = "; ".join(pronoun_rules)
    pro_drop_word = "yes" if grammar.pro_drop else "no"
    reflexive_desc = {
        "word": 'an object pronoun slot with gloss "self" (case-marked like any object)',
        "affix": 'NO object slot: set "voice":"reflexive" on the verb',
        "none": "an ordinary object pronoun of the subject's own person",
    }[grammar.reflexive_marking] if grammar.reflexive_marking in ("word", "affix", "none") else "an ordinary pronoun"
    reciprocal_desc = {
        "word": 'an object pronoun slot with gloss "each-other" (case-marked like any object)',
        "affix": 'NO object slot: set "voice":"reciprocal" on the verb',
        "none": "an ordinary object pronoun",
    }.get(grammar.reciprocal_marking, "an ordinary pronoun")
    possessive_pronoun_desc = (
        'the personal-pronoun possessor slot with "possessive":true, as for any possessor'
        if grammar.possessive_pronouns == "regular"
        else 'a slot {"kind":"possessive_pronoun","gloss":"<the personal pronoun gloss>"} ("my" -> gloss "I", '
        '"your" -> "you", "his" -> "he", "their" -> "they", "our" -> "we"...) directly before the possessed noun '
        "-- never a separate possessive marking, and never the pronoun slot itself"
    )
    suppletive_desc = (
        "the personal pronouns " + ", ".join(grammar.suppletive_pronoun_persons)
        + " have case forms that are words of their own (like I/me); still write the ordinary pronoun slot "
        "with its case (\"accusative\", \"dative\", \"genitive\"...) -- the renderer picks the right word"
        if grammar.suppletive_pronoun_persons
        else "personal pronouns take the ordinary case marking"
    )
    own_desc = (
        'a slot {"kind":"possessive_pronoun","gloss":"self"} directly before the possessed noun ("his own dog", '
        '"her own house": the owner is the sentence\'s subject); never the ordinary possessive'
        if grammar.reflexive_possessive in ("word", "affix")
        else "no separate form: use the ordinary possessive of the subject's own person"
    )
    possessive_classifier_desc = (
        "a possessor word is followed by a possessive classifier that the renderer adds itself -- never write one"
        if grammar.possessive_classifiers
        else "no classifier after a possessor"
    )
    relative_desc = {
        "pronoun": 'the clause slot\'s "gloss" is a relative pronoun: "who" for a person, "which" otherwise',
        "particle": 'the clause slot\'s "gloss" is "rel" (one invariant relative word for every relative clause)',
        "gap": (
            'NO linking word (leave the clause slot\'s "gloss" empty) and NO slot at all for the relativized '
            "noun phrase inside the clause -- that position is simply empty"
        ),
        "resumptive": (
            'the clause slot\'s "gloss" is "rel", and the relativized noun phrase is kept inside the clause as '
            "a pronoun slot (a resumptive pronoun)"
        ),
        "correlative": (
            'the clause slot\'s "gloss" is "which"; the renderer moves the clause to the front of the sentence '
            'and adds "that" before the noun in the main clause'
        ),
    }.get(grammar.relativization, "a relative pronoun")
    forms_desc = (
        "this language has " + ", ".join(grammar.verb_forms) + ": set \"verb_form\" on a non-finite verb -- "
        + (
            'the "infinitive" for a complement with the SAME subject as the main verb ("I want to see the river": '
            "a complement clause slot with an empty gloss whose own verb is the infinitive, no subject slot, no "
            "tense/agreement); "
            if "infinitive" in grammar.verb_forms
            else ""
        )
        + (
            'the "nominalized" form for a clause used as a noun ("seeing the river is good"); '
            if "nominalized" in grammar.verb_forms
            else ""
        )
        + (
            'the "participle" for a reduced relative ("the man sleeping"). '
            if "participle" in grammar.verb_forms
            else ""
        )
        + "Otherwise use a finite clause."
        if grammar.verb_forms
        else "no non-finite verb forms: always use a finite clause, repeating the subject"
    )
    subordinate_mood_desc = (
        'a clause introduced by "if", "unless", "so that" or "although" puts its verb in the subjunctive/irrealis '
        "(the renderer does it if the language has one -- do not set it yourself)"
        if grammar.subordinate_mood_use
        else "subordinate clauses use the ordinary verb forms"
    )
    strategy = grammar.relativization
    beyond = [f for f in ("subject", "object", "oblique", "possessor") if subordination_gen.beyond_reach(grammar.relativization_reach, f)]
    reach_desc = (
        f"the plain strategy reaches up to the {grammar.relativization_reach} position; a relative clause on "
        + (", ".join(beyond) if beyond else "no position")
        + ' keeps a resumptive pronoun slot for the relativized noun inside the clause (the renderer then uses the word "rel")'
        if strategy in ("gap", "particle", "resumptive") and beyond
        else "every position is reached by this language's strategy"
    )
    declension_bits = []
    if grammar.relative_pronoun_declines:
        declension_bits.append("takes the case of its function (who/whom/whose)")
    if grammar.relative_pronoun_number:
        declension_bits.append("has a plural")
    declension_desc = (
        "the relative pronoun " + " and ".join(declension_bits) + ' -- still write "who"/"which"; the renderer picks the form'
        if declension_bits and strategy in ("pronoun", "correlative")
        else "the relative word does not decline"
    )
    infinitive_agreement_desc = (
        'an infinitive agrees with its controller: set "agreement" (I/you/he/we) on the infinitive verb to the '
        'controller\'s person -- the subject for "I want to go", the object for "I told him to go"'
        if grammar.infinitive_agrees and "infinitive" in grammar.verb_forms
        else "an infinitive carries no agreement"
    )
    nominal_desc = (
        'a clause used as a noun ("I like seeing the river", "seeing is good") is a clause slot with "role":"nominal" '
        'and an empty gloss whose verb has "verb_form":"nominalized"'
        + (
            '; set "case" on the clause slot to the argument\'s case (the renderer puts it on the nominalized verb)'
            if grammar.nominalized_takes_case
            else ""
        )
        if "nominalized" in grammar.verb_forms
        else "no nominalized clauses: use a finite clause"
    )
    conditional_desc = (
        'in a sentence with an "if"/"unless" clause the renderer puts the main verb in the conditional and '
        + (f"the \"if\" clause verb in the {grammar.conditional_clause_tense} tense unless you set one; " if grammar.conditional_clause_tense else "")
        + "do not set these yourself"
        if grammar.conditional_main_mood or grammar.conditional_clause_tense
        else "conditional sentences use the ordinary verb forms"
    )
    correlative_desc = (
        '"if"/"when" clauses come first with "then" starting the main clause, and "the more..., the more..." is two '
        'parallel parts: write an adverbial clause slot with gloss "the-more" holding the first part and the main slots '
        "the second; the renderer does the fronting and the correlates"
        if grammar.correlative_adverbials
        else 'write "the more..., the more..." as an adverbial clause slot with gloss "the-more"'
    )
    coordination_desc = {
        "word": 'a conjunction word joins the clauses (the renderer places it)',
        "converb": 'no conjunction: the first clause\'s last verb becomes a medial form (the renderer does it)',
        "juxtapose": "the clauses simply follow each other with no conjunction",
    }.get(grammar.clause_coordination, "a conjunction word joins the clauses")
    complementizer_desc = (
        'the complementizer depends on the class of the governing verb (speech, desire, perception, factive): still '
        'write "that" as the gloss; the renderer chooses'
        if grammar.complementizer_by_verb
        else 'one complementizer ("that") for every verb'
    )
    verb_extras = []
    if grammar.verb_number_agreement:
        verb_extras.append('set "subject_number":"plural" on a finite verb whose subject is plural (a plural pronoun, or a plural noun)')
    if grammar.verb_politeness:
        verb_extras.append('set "polite":true on a finite verb whose subject is "you-polite"')
    verb_extras_text = "; ".join(verb_extras) if verb_extras else "verbs here carry no number or politeness (never set those fields)"
    object_drop_word = "yes" if grammar.object_pro_drop else "no"
    classified = ", ".join(grammar.classified_quantifiers) if grammar.classified_quantifiers else "none"
    classifier_desc = (
        'a numeral or demonstrative directly before a noun is followed by a CLASSIFIER word that the renderer '
        "adds itself -- never write one; the noun stays singular after a numeral. A quantifier "
        "(many, few, some, several, all, every, each, both, how-many) is a content slot with pos "
        f'"quantifier" placed like a numeral; these quantifiers also take a classifier (added by the renderer): {classified}'
        if grammar.uses_classifiers
        else "no classifiers"
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
- evidentials this language actually has: {evidentials_desc}.
- personal pronouns: use exactly these glosses on "pronoun" slots: {pronoun_list}. \
Mapping: {pronoun_rules_text}. When the verb agrees in person and the language \
drops subject pronouns ({pro_drop_word}), still write the pronoun \
slot: the renderer omits it.
- classifiers: {classifier_desc}.
- reflexives ("he sees himself"): {reflexive_desc}. Reciprocals ("they see each \
other"): {reciprocal_desc}.
- possessive pronouns ("my dog", "their house"): {possessive_pronoun_desc}.
- relative clauses ("the dog that sleeps"): {relative_desc}. Always write the \
clause slot directly after its noun; the renderer moves it if this language \
puts relative clauses before their noun.
- position of the relativized noun: set "rel_function" on every relative clause slot to "subject" ("the dog \
that sleeps"), "object" ("the dog that I see": the clause has NO object slot), "oblique" ("the house in \
which I live") or "possessor" ("the man whose dog sleeps": the clause holds the possessed noun with no \
possessor); {reach_desc}. {declension_desc}.
- non-finite verb forms: {forms_desc}. {infinitive_agreement_desc}. Nominalizations: {nominal_desc}.
- conditionals: {conditional_desc}. Correlatives: {correlative_desc}.
- coordinated clauses ("I see the dog and I hear the cat"): a clause slot with "role":"coordinate" and gloss \
"and"/"but"/"or" holding the second clause; {coordination_desc}.
- complementizers: {complementizer_desc}.
- subordinate moods: {subordinate_mood_desc}.
- reflexive possessives ("his own dog"): {own_desc}.
- pronouns in a non-nominative case: {suppletive_desc}.
- classifiers after a possessor: {possessive_classifier_desc}.
- verb agreement in number and politeness: {verb_extras_text}.
- object pronouns omitted when the verb's object agreement names them: \
{object_drop_word} (still write the pronoun slot; the renderer omits it).
- comparison ("X is bigger/more beautiful than Y"): the comparative of an \
adjective: {comparative_desc}; the standard of comparison (Y): \
{standard_desc}. The superlative ("the biggest", "most beautiful"): \
{superlative_desc}. Never write the English "-er"/"-est" forms as the gloss: \
the gloss is the plain adjective lemma ("big").
- existential sentences ("there is/are X", "is there X?"): {existential_desc}. \
Never write a slot for the English "there".
- possession clauses ("I have a dog", "the man had two horses"): \
{possession_clause_desc}. (Possession INSIDE a noun phrase, "my dog", is the \
separate "possessive" mechanism.)
- voices (besides the ordinary active) this language actually has: \
{voices_desc}.
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
"verb", "adjective", "pronoun", "numeral", "quantifier", "adverb", "preposition", "other"). Never drop a meaningful word: degree words and adverbs ("very", "extremely", "quickly"), prepositions ("in", "on"), and every other content word each get their own "content" slot (pos "adverb"/"preposition"), placed next to the word they modify (a degree adverb directly before its adjective). A "content" slot may \
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
expressed only through these fields (the renderer decides whether a label is \
a verb suffix or an auxiliary word). A verb may also set "evidential" (one \
of the evidentials above) when the English states the source of the \
information: "reportedly"/"allegedly"/"they say" -> reported; \
"apparently"/"evidently"/"must have" -> inferred; "I saw that" -> witnessed; \
never write those adverbs as slots when you use the field. Negation stays \
one {{"kind":"negation"}} slot; the renderer may fold it into the verb.

Noun-phrase pieces, each its own slot placed next to its noun as the bullets above say: a demonstrative is {{"kind":"demonstrative","gloss":"this"}} or "that" ("these"/"those" are the demonstrative plus the noun with "number":"plural"); a numeral is an ordinary "content" slot with pos "numeral" ("two dogs": numeral two, then dog with "number" -- "dual" when exactly two and the language has a dual, otherwise "plural"); an English "a"/"an" is an "indefinite_article" slot only when this language has one, otherwise nothing. Possession ("my dog", "the dog's bone", "Bruno's leg"): the possessor is its own slot with "possessive":true placed directly before the possessed noun -- for a pronoun possessor the pronoun itself ("my" -> the pronoun "I", "your" -> "you", "his"/"her" -> "he", "our" -> "we", "their" -> "they"). Never add the possessive marking yourself.

Voice, only when the voices bullet lists it: set "voice" on the finite \
verb slot (never on the copula) and reassign the arguments to match. \
"passive" ("the dog is seen by the man", "the river was crossed"): the \
patient is the sentence's subject and takes NO object case (under \
nominative-accusative it is the plain subject; under ergative-absolutive it is \
absolutive -- either way, no "accusative"/"ergative"); the agent, if stated, \
is an oblique phrase: a "content" slot with gloss "by" and pos "preposition" \
followed by (a postposition: preceded by) the agent noun phrase, with no \
case; the verb agrees with the patient; drop the English "is/was" and \
participle -- the passive verb carries tense and "voice":"passive". \
"antipassive" (ergative-absolutive languages: "the man eats" with the \
patient demoted or omitted): the agent is the plain absolutive subject (NO \
"ergative" case); a demoted patient, if stated, takes no case (or the dative \
if the language has one). "causative" ("I made the dog see the river"): the \
verb is the caused action with "voice":"causative"; the subject is the \
causer, the causee ("the dog") is a direct-object noun phrase, and any \
original object follows it, plain. When this language lacks the needed \
voice, reword as an ordinary active sentence (a passive with a stated agent: \
make the agent the subject; without one, use the pronoun "they" as subject). \
Never write an English auxiliary ("is", "was", "made") for a voice as its \
own slot.

Agreement (only where the two bullets above allow it): the renderer works \
out from position which noun an adjective, article, demonstrative, numeral \
or possessive agrees with (in class, number and case, as this language does), \
so "agrees_with" is optional -- set it only when the noun is not next to the \
adjective. An adjective slot may set "agrees_with" to the lemma of the noun it modifies or, as a predicate, \
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
            "relativization": grammar.relativization,
            "infinitive_agrees": "true" if grammar.infinitive_agrees else "false",
            "relativization_reach": grammar.relativization_reach,
            "verb_forms": ",".join(grammar.verb_forms),
            "subordinate_mood_use": "true" if grammar.subordinate_mood_use else "false",
            "reflexive_marking": grammar.reflexive_marking,
            "reciprocal_marking": grammar.reciprocal_marking,
            "possessive_pronouns": grammar.possessive_pronouns,
            "reflexive_possessive": grammar.reflexive_possessive,
            "verb_number_agreement": "true" if grammar.verb_number_agreement else "false",
            "verb_politeness": "true" if grammar.verb_politeness else "false",
            "object_pro_drop": "true" if grammar.object_pro_drop else "false",
            "clusivity": "true" if grammar.clusivity else "false",
            "third_person_gender": "true" if grammar.third_person_gender else "false",
            "honorific_you": "true" if grammar.honorific_you else "false",
            "comparative_strategy": grammar.comparative_strategy,
            "comparative_case": grammar.comparative_case,
            "comparative_marking": grammar.comparative_marking,
            "superlative_marking": grammar.superlative_marking,
            "existential": grammar.existential,
            "possession_clause": grammar.possession_clause,
            "cases": ",".join(grammar.cases),
            "voices": ",".join(grammar.voices),
            "postpositional": "true" if grammar.postpositional else "false",
            "has_indefinite_article": "true" if grammar.has_indefinite_article else "false",
            "demonstrative_after_noun": "true" if grammar.demonstrative_after_noun else "false",
            "number_labels": ",".join(a.label for a in grammar.number_affixes),
            "possession": grammar.possession,
            "noun_classes": ",".join(grammar.noun_classes),
            "object_agreement": "true" if grammar.object_agreement else "false",
            "verb_moods": ",".join(grammar.moods),
            "evidentials": ",".join(grammar.evidentials),
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
                    rel_function=item.get("rel_function") if item.get("rel_function") in RELATIVE_FUNCTION_LABELS else None,
                    case=_coerce_optional_str(item.get("case")),
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
                evidential=_coerce_optional_str(item.get("evidential")),
                voice=_coerce_optional_str(item.get("voice")),
                verb_form=_coerce_optional_str(item.get("verb_form")),
                subject_number="plural" if item.get("subject_number") == "plural" else None,
                polite=item.get("polite") is True,
                degree=item.get("degree") if item.get("degree") in ("comparative", "superlative") else None,
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
