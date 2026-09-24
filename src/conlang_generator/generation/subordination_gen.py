"""Subordination: how a language builds clauses inside clauses.

Rolled per language from its own independent rng stream:

- ``subordinator_position``: a subordinating word ("that", "because", "if")
  goes ``"before"`` or ``"after"`` its clause -- after in about 70% of
  verb-final languages, before in about 85% of the others (the usual
  correlation, now a rolled fact rather than a rule).
- ``relativization``: how a relative clause is marked -- ``"pronoun"`` (a
  relative pronoun, who/which), ``"particle"`` (one invariant relative word),
  ``"gap"`` (no word at all: the clause simply precedes or follows its noun
  with the relativized position left empty, as in Japanese), ``"resumptive"``
  (an invariant word plus a pronoun kept in the clause, as in Arabic) or
  ``"correlative"`` (the relative clause comes first, and the main clause
  points back at it with "that", as in Hindi).
- ``relative_clause_position``: ``"after_noun"`` or ``"before_noun"`` (mostly
  before in object-before-verb languages).
- ``verb_forms``: the non-finite forms the verb has -- ``"infinitive"`` (a
  same-subject complement: "I want to see"), ``"nominalized"`` and
  ``"participle"`` (a reduced relative: "the man sleeping") -- each a suffix
  that replaces tense and agreement.
- ``subordinate_mood_use``: whether "if"/"unless"/"so that"/"although" clauses
  put their verb in the language's subjunctive/irrealis mood (if it has one).

Illustrative, not a rigorous typological model (see docs/LIMITATIONS.md).
"""

from __future__ import annotations

import random

_VERB_FINAL = ("SOV", "OSV")
_AFTER_IF_VERB_FINAL = 0.70
_AFTER_OTHERWISE = 0.15
_RELATIVIZATION = (("pronoun", 0.30), ("particle", 0.30), ("gap", 0.20), ("resumptive", 0.10), ("correlative", 0.10))
_BEFORE_NOUN_IF_OV = 0.65
_BEFORE_NOUN_OTHERWISE = 0.15
_VERB_FORM_RATES = (("infinitive", 0.65), ("nominalized", 0.45), ("participle", 0.40))
_SUBORDINATE_MOOD_RATE = 0.50

VERB_FORM_LABELS = tuple(label for label, _ in _VERB_FORM_RATES) + ("converb",)
"""Every non-finite form a language can have (``converb`` -- a medial verb that
joins clauses without a conjunction -- is rolled by ``roll_subordination_followups``)."""

IRREALIS_LINKERS = frozenset({"if", "unless", "lest", "so-that", "in-order-that", "although"})
"""Subordinators (spaces written as hyphens) whose clause takes the
subjunctive/irrealis in a language with ``subordinate_mood_use``."""

RELATIVE_PARTICLE_GLOSS = "rel"
DEFAULT_RELATIVE_PRONOUN = "who"


def roll_subordination(rng: random.Random, word_order: str, postpositional: bool) -> dict[str, object]:
    """The subordination fields of ``GrammarProfile`` (every draw always made,
    so the stream is stable)."""
    after_rate = _AFTER_IF_VERB_FINAL if word_order in _VERB_FINAL else _AFTER_OTHERWISE
    subordinator_position = "after" if rng.random() < after_rate else "before"
    relativization_roll = rng.random()
    relativization = _RELATIVIZATION[-1][0]
    cumulative = 0.0
    for label, weight in _RELATIVIZATION:
        cumulative += weight
        if relativization_roll < cumulative:
            relativization = label
            break
    before_rate = _BEFORE_NOUN_IF_OV if postpositional else _BEFORE_NOUN_OTHERWISE
    relative_clause_position = "before_noun" if rng.random() < before_rate else "after_noun"
    verb_forms = tuple(label for label, rate in _VERB_FORM_RATES if rng.random() < rate)
    return {
        "subordinator_position": subordinator_position,
        "relativization": relativization,
        "relative_clause_position": relative_clause_position,
        "verb_forms": verb_forms,
        "subordinate_mood_use": rng.random() < _SUBORDINATE_MOOD_RATE,
    }


# ---------------------------------------------------------------------------
# Follow-ups: relativization reach, relative pronoun forms, infinitive
# agreement, case-marked nominalizations, conditional sequencing, correlative
# adverbials, clause coordination and complementizer choice.
# ---------------------------------------------------------------------------

RELATIVE_FUNCTIONS = ("subject", "object", "oblique", "possessor")
"""The position of the relativized noun inside its own clause (the noun phrase
accessibility hierarchy, most to least accessible)."""

FUNCTION_CASE = {"object": "accusative", "oblique": "dative", "possessor": "genitive"}
"""The case a declining relative pronoun takes for each non-subject function."""

_REACH_RATES = (("subject", 0.25), ("object", 0.35), ("oblique", 0.25), ("possessor", 0.15))
_COORDINATION_RATES = (("word", 0.55), ("converb", 0.25), ("juxtapose", 0.20))

CORRELATIVE_LINKERS = frozenset({"if", "when", "the-more"})
"""Adverbial subordinators that a language with ``correlative_adverbials``
fronts, adding a correlate ("then", "the-more") to the main clause."""
CORRELATE_GLOSS = {"if": "then", "when": "then", "the-more": "the-more"}

_SPEECH = frozenset({"say", "think", "believe", "tell", "claim", "hear", "guess", "suppose", "answer", "write"})
_DESIRE = frozenset({"want", "wish", "hope", "order", "ask", "demand", "need", "prefer", "command", "beg", "permit"})
_PERCEPTION = frozenset({"see", "watch", "notice", "feel", "smell", "observe"})
_FACTIVE = frozenset({"know", "regret", "realize", "forget", "remember", "learn", "discover", "understand"})
COMPLEMENT_CLASSES = ("speech", "desire", "perception", "factive")

_RELATIVE_BASES = ("who", "which")
_RELATIVE_ENGLISH = {
    "who": {"subject": "who", "object": "whom", "oblique": "whom", "possessor": "whose"},
    "which": {"subject": "which", "object": "which", "oblique": "which", "possessor": "whose"},
}


def roll_subordination_followups(rng: random.Random) -> dict[str, object]:
    """The follow-up rolls, drawn from the same stream after the earlier ones
    (which are unchanged)."""
    reach_roll = rng.random()
    reach = _REACH_RATES[-1][0]
    cumulative = 0.0
    for label, weight in _REACH_RATES:
        cumulative += weight
        if reach_roll < cumulative:
            reach = label
            break
    declines = rng.random() < 0.5
    number = rng.random() < 0.25
    infinitive_agrees = rng.random() < 0.35
    nominalized_takes_case = rng.random() < 0.5
    conditional_main_mood = rng.random() < 0.45
    conditional_past = rng.random() < 0.25
    correlative_adverbials = rng.random() < 0.25
    coordination_roll = rng.random()
    coordination = _COORDINATION_RATES[-1][0]
    cumulative = 0.0
    for label, weight in _COORDINATION_RATES:
        cumulative += weight
        if coordination_roll < cumulative:
            coordination = label
            break
    return {
        "relativization_reach": reach,
        "relative_pronoun_declines": declines,
        "relative_pronoun_number": number,
        "infinitive_agrees": infinitive_agrees,
        "nominalized_takes_case": nominalized_takes_case,
        "conditional_main_mood": conditional_main_mood,
        "conditional_clause_tense": "past" if conditional_past else "",
        "correlative_adverbials": correlative_adverbials,
        "clause_coordination": coordination,
        "conjunct_reduction": rng.random() < 0.5,
        "complementizer_by_verb": rng.random() < 0.4,
        "converb": rng.random() < 0.4,
    }


def beyond_reach(reach: str, function: str) -> bool:
    """Whether a relative clause on ``function`` lies beyond what the
    language's plain (gap or particle) strategy reaches."""
    order = RELATIVE_FUNCTIONS
    if function not in order or reach not in order:
        return False
    return order.index(function) > order.index(reach)


def relative_pronoun_gloss(base: str, function: str, plural: bool, declines: bool, has_number: bool, cases: tuple[str, ...]) -> str:
    """The lexicon gloss of the relative pronoun for a clause: the plain
    ``who``/``which``, or -- where the language declines it -- with the case of
    its function (``who-accusative``) and ``-plural`` for a plural head."""
    gloss = base
    case = FUNCTION_CASE.get(function)
    if declines and case is not None and case in cases:
        gloss = f"{base}-{case}"
    if has_number and plural:
        gloss += "-plural"
    return gloss


def relative_reading(gloss: str) -> str | None:
    """The English word (who/whom/whose/which) a relative pronoun gloss reads
    back as, or ``None`` if ``gloss`` is not one."""
    parts = gloss.strip().lower().split("-")
    if parts[0] not in _RELATIVE_BASES:
        return None
    rest = parts[1:]
    if rest and rest[-1] == "plural":
        rest = rest[:-1]
    if len(rest) > 1:
        return None
    case = rest[0] if rest else None
    function = next((f for f, c in FUNCTION_CASE.items() if c == case), "subject")
    return _RELATIVE_ENGLISH[parts[0]][function]


def complement_class(lemma: str) -> str | None:
    """The class of a governing verb that selects a complementizer."""
    word = lemma.strip().lower()
    for label, verbs in (("speech", _SPEECH), ("desire", _DESIRE), ("perception", _PERCEPTION), ("factive", _FACTIVE)):
        if word in verbs:
            return label
    return None


def complementizer_split(gloss: str) -> tuple[str, str] | None:
    """``(base, class)`` for a class-specific complementizer gloss
    (``that-desire``), else ``None``."""
    base, sep, label = gloss.strip().lower().rpartition("-")
    if sep and label in COMPLEMENT_CLASSES and base:
        return base, label
    return None
