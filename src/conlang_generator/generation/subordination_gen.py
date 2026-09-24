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

VERB_FORM_LABELS = tuple(label for label, _ in _VERB_FORM_RATES)

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
