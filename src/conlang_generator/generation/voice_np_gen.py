"""Voice and noun-phrase follow-ups: more voices (middle, applicative,
impersonal), how the passive agent and the passive's agreement work, trial and
collective number, locative/instrumental case, how adpositions relate to case
(kept and governing a case, or replaced by it), irregular (suppletive) plurals
and comparatives, and inalienable possession.

Everything here is drawn from one independent rng stream so that no existing
seed's earlier choices shift."""

from __future__ import annotations

import random

from conlang_generator.core.grammar import MorphologicalType
from conlang_generator.generation.noun_class_gen import semantic_field

EXTRA_VOICES = ("middle", "applicative", "impersonal")
_EXTRA_VOICE_RATE = 0.25
RESULT_VERB_POOL = (
    "break", "open", "close", "die", "fall", "kill", "catch", "burn", "freeze", "stop", "begin",
    "wake", "split", "join", "tear", "cut", "rise",
)
"""Candidates for a serial verb construction's own result slot (the resultative subtype only --
Mandarin's own 打破 "hit-break" = to break) -- every one confirmed present in `lexicon_gen.
ALL_MEANINGS` as a verb gloss, not assumed. A real language recruits a small, particular subset of
these (see `_SERIAL_RESULT_POOL_SIZE`), not the open verb class -- real SVCs are typologically
restrictive about which verbs can fill the result slot."""
_SVC_RATE = {
    MorphologicalType.ISOLATING: 0.45, MorphologicalType.AGGLUTINATIVE: 0.15,
    MorphologicalType.FUSIONAL: 0.10, MorphologicalType.POLYSYNTHETIC: 0.20,
}
"""Isolating languages weighted highest -- Mandarin/Thai/Niger-Congo's own real typological skew
toward serial verb constructions -- nonzero everywhere else, since SVCs aren't exclusively an
isolating-language property (west African languages with agglutinative tendencies have them too)."""
_SERIAL_RESULT_POOL_SIZE = (3, 4, 5, 6)
DIRECTIONAL_VERB_POOL = ("go", "come", "arrive", "leave", "return", "climb", "turn")
"""Candidates for a serial verb construction's own directional slot (the directional subtype --
Japanese's own 飛び出す "fly-out" = to jump out) -- every one confirmed present in `lexicon_gen.
ALL_MEANINGS` as a verb gloss. Deliberately excludes rise/fall (already claimed by `RESULT_VERB_
POOL`, and genuinely ambiguous between a resultative and directional reading) to keep the two pools
disjoint. Smaller than `RESULT_VERB_POOL` -- realistic, not a shortfall: real deictic/path verb
inventories are typically small, closed, grammaticalized sets cross-linguistically (Mandarin's own
directional-complement system has about 8 core members: 来/去/上/下/进/出/回/过)."""
_SERIAL_DIRECTIONAL_POOL_SIZE = (2, 3, 4, 5)
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
SUPPLETIVE_SUFFIXES = ("plural", "comparative", "superlative", "past", "non_past", "present", "future")
TENSE_SUFFIXES = ("past", "non_past", "present", "future")
"""The subset of ``SUPPLETIVE_SUFFIXES`` that are verb tenses, not a noun's
plural or an adjective's degree -- used by ``translator.py``'s tense-
suppletion render/decode checks."""

_GRAMMAR_FIELD_BY_KIND = {
    "plural": "suppletive_plurals",
    "comparative": "suppletive_degrees",
    "superlative": "suppletive_degrees",
    "past": "suppletive_past",
    "non_past": "suppletive_non_past",
    "present": "suppletive_present",
    "future": "suppletive_future",
}
_KNOWN_DICT_BY_KIND = {
    "plural": IRREGULAR_PLURALS,
    "past": IRREGULAR_PASTS,
    "comparative": SUPPLETIVE_DEGREES,
    "superlative": SUPPLETIVE_DEGREES,
}
"""No hardcoded-English-irregular dict exists for ``non_past``/``present``/
``future`` -- there's no real-English-irregular concept for them, only a
user-seeded lemma ever populates those three grammar fields."""


def suppletive_field(kind: str) -> str:
    """The ``GrammarProfile`` tuple field tracking which lemmas are
    suppletive for ``kind`` -- shared by generation (folding a seeded
    lemma in), decode (``suppletive_split``), and verb rendering (the
    tense-suppletion check in ``translator.py``)."""
    return _GRAMMAR_FIELD_BY_KIND[kind]

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


def suppletive_split(gloss: str, grammar=None) -> tuple[str, str] | None:
    """``(base, kind)`` for a suppletive form's gloss (``child-plural``).

    ``grammar``, when given, also recognizes a user-seeded lemma (one in
    ``grammar.suppletive_plurals``/``_degrees``/``_past``) alongside the
    hardcoded-irregular dicts below -- see the "seed words" generation
    pass (``generation/seed_examples.py``) for how a lemma gets there."""
    for kind in SUPPLETIVE_SUFFIXES:
        if gloss.endswith("-" + kind) and len(gloss) > len(kind) + 1:
            base = gloss[: -(len(kind) + 1)]
            known = _KNOWN_DICT_BY_KIND.get(kind, {})
            seeded = () if grammar is None else getattr(grammar, suppletive_field(kind))
            return (base, kind) if (base in known or base in seeded) else None  # not a pronoun like "you-plural"
    return None


def suppletive_reading(base: str, kind: str) -> str:
    """The English word for a suppletive form: children, better, best...
    ``non_past``/``present`` read as the bare gloss, ``future`` as "will
    {gloss}" -- crude (no agreement, no real English-irregular concept
    for a tense label), but consistent with the "+ed"/"more X" fallbacks
    below for a lemma outside the hardcoded dicts."""
    if kind == "plural":
        return IRREGULAR_PLURALS.get(base, base + "s")
    if kind == "past":
        return IRREGULAR_PASTS.get(base, base + "ed")
    if kind in ("non_past", "present"):
        return base
    if kind == "future":
        return f"will {base}"
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
    has_serial_verbs = rng.random() < _SVC_RATE.get(grammar.morphological_type, 0.2)
    serial_pool_size = rng.choice(_SERIAL_RESULT_POOL_SIZE)
    sampled_result_verbs = tuple(rng.sample(RESULT_VERB_POOL, serial_pool_size))
    serial_directional_pool_size = rng.choice(_SERIAL_DIRECTIONAL_POOL_SIZE)
    sampled_directional_verbs = tuple(rng.sample(DIRECTIONAL_VERB_POOL, serial_directional_pool_size))
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
        "has_serial_verbs": has_serial_verbs,
        "serial_result_verbs": sampled_result_verbs if has_serial_verbs else (),
        "serial_directional_verbs": sampled_directional_verbs if has_serial_verbs else (),
    }
