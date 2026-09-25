"""Voice and noun-phrase follow-ups: more voices (middle, applicative,
impersonal), how the passive agent and the passive's agreement work, trial and
collective number, locative/instrumental case, how adpositions relate to case
(kept and governing a case, or replaced by it), irregular (suppletive) plurals
and comparatives, and inalienable possession.

Everything here is drawn from one independent rng stream so that no existing
seed's earlier choices shift."""

from __future__ import annotations

import random

from conlang_generator.generation.noun_class_gen import semantic_field

EXTRA_VOICES = ("middle", "applicative", "impersonal")
_EXTRA_VOICE_RATE = 0.25
EXTRA_NUMBERS = ("trial", "collective")
_NUMBER_RATES = (0.12, 0.15)
EXTRA_CASES = ("locative", "instrumental")
_EXTRA_CASE_RATE = 0.35
ADPOSITION_STRATEGIES = (("none", 0.35), ("governs", 0.35), ("case_only", 0.30))

ADPOSITION_CASES = {
    "to": "dative", "for": "dative", "of": "genitive", "with": "instrumental", "by": "instrumental",
    "in": "locative", "on": "locative", "at": "locative", "under": "locative", "over": "locative",
    "near": "locative", "beside": "locative", "behind": "locative", "inside": "locative", "above": "locative",
    "below": "locative", "between": "locative", "among": "locative", "from": "ablative", "into": "allative",
    "toward": "allative", "towards": "allative", "onto": "allative", "without": "ablative",
}
"""The case each English adposition corresponds to."""
FALLBACK_CASES = {"with": "comitative", "to": "allative", "for": "allative", "without": "comitative"}
"""A second case an adposition may correspond to when the language lacks the first."""
REPLACEABLE_CASES = frozenset({"locative", "instrumental", "ablative", "allative", "comitative"})
"""Cases that can stand in for their adposition altogether."""
CASE_PREPOSITION = {
    "locative": "in", "instrumental": "with", "ablative": "from", "allative": "to", "comitative": "together with",
}
"""The English adposition a case-only noun is read back with."""
MEASURE_NOUNS = frozenset(
    "cup glass bottle bowl basket bag box pot piece handful pair group herd flock kind slice drop".split()
)
"""Nouns that measure a mass noun ("a cup of water")."""
IRREGULAR_PASTS = {
    "go": "went", "see": "saw", "come": "came", "eat": "ate", "drink": "drank", "say": "said", "know": "knew",
    "sleep": "slept", "give": "gave", "take": "took", "make": "made", "run": "ran", "write": "wrote",
}
"""Verbs whose past may be a word of its own."""

IRREGULAR_PLURALS = {
    "man": "men", "woman": "women", "child": "children", "foot": "feet", "tooth": "teeth", "mouse": "mice",
    "person": "people", "goose": "geese", "ox": "oxen",
}
SUPPLETIVE_DEGREES = {"good": ("better", "best"), "bad": ("worse", "worst")}
SUPPLETIVE_SUFFIXES = ("plural", "comparative", "superlative", "past")

_KIN = frozenset(
    "mother father brother sister son daughter wife husband child parent uncle aunt grandmother grandfather".split()
)


def is_inalienable(gloss: str) -> bool:
    """Body parts and kin, the nouns that are typically possessed inalienably."""
    word = gloss.strip().lower()
    return word in _KIN or semantic_field(word) == "body"


def suppletive_gloss(gloss: str, kind: str) -> str:
    """The lexicon gloss of the suppletive ``kind`` form of ``gloss``."""
    return f"{gloss}-{kind}"


def suppletive_split(gloss: str) -> tuple[str, str] | None:
    """``(base, kind)`` for a suppletive form's gloss (``child-plural``)."""
    for kind in SUPPLETIVE_SUFFIXES:
        if gloss.endswith("-" + kind) and len(gloss) > len(kind) + 1:
            base = gloss[: -(len(kind) + 1)]
            known = (
                IRREGULAR_PLURALS if kind == "plural" else IRREGULAR_PASTS if kind == "past" else SUPPLETIVE_DEGREES
            )
            return (base, kind) if base in known else None  # not a pronoun like "you-plural"
    return None


def suppletive_reading(base: str, kind: str) -> str:
    """The English word for a suppletive form: children, better, best..."""
    if kind == "plural":
        return IRREGULAR_PLURALS.get(base, base + "s")
    if kind == "past":
        return IRREGULAR_PASTS.get(base, base + "ed")
    pair = SUPPLETIVE_DEGREES.get(base)
    if pair is None:
        return f"more {base}" if kind == "comparative" else f"most {base}"
    return pair[0] if kind == "comparative" else pair[1]


def roll_followups(rng: random.Random, grammar) -> dict[str, object]:
    """Every draw is always made, so the count never depends on the grammar."""
    voice_hits = [rng.random() < _EXTRA_VOICE_RATE for _ in EXTRA_VOICES]
    passive_agreement = "none" if rng.random() < 0.4 else "patient"
    passive_agent = "case" if rng.random() < 0.4 else "word"
    number_hits = [rng.random() < rate for rate in _NUMBER_RATES]
    case_hits = [rng.random() < _EXTRA_CASE_RATE for _ in EXTRA_CASES]
    roll = rng.random()
    cumulative = 0.0
    strategy = ADPOSITION_STRATEGIES[-1][0]
    for label, weight in ADPOSITION_STRATEGIES:
        cumulative += weight
        if roll < cumulative:
            strategy = label
            break
    plural_gate = rng.random() < 0.4
    plural_hits = [rng.random() < 0.5 for _ in IRREGULAR_PLURALS]
    degree_gate = rng.random() < 0.4
    degree_hits = [rng.random() < 0.6 for _ in SUPPLETIVE_DEGREES]
    inalienable = rng.random() < 0.25
    return {
        "voices": tuple(v for v, hit in zip(EXTRA_VOICES, voice_hits) if hit and v not in grammar.voices),
        "passive_agreement": passive_agreement,
        "passive_agent": passive_agent,
        "numbers": tuple(n for n, hit in zip(EXTRA_NUMBERS, number_hits) if hit),
        # Extra cases only join a language that already marks case.
        "cases": tuple(
            c for c, hit in zip(EXTRA_CASES, case_hits) if hit and grammar.cases and c not in grammar.cases
        ),
        "adposition_case_strategy": strategy,
        "suppletive_plurals": tuple(g for g, hit in zip(IRREGULAR_PLURALS, plural_hits) if hit) if plural_gate else (),
        "suppletive_degrees": tuple(g for g, hit in zip(SUPPLETIVE_DEGREES, degree_hits) if hit) if degree_gate else (),
        "inalienable_possession": inalienable,
    }
