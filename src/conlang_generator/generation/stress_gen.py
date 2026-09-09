"""Primary lexical word-stress: which syllable of a word carries it.

Stored as the standard IPA mark ``ˈ`` (U+02C8), inserted directly before
the stressed syllable's onset in a word's own IPA string by
``word_builder.build_word`` -- the single source of truth (unlike tone,
which duplicates its embedded marks into ``LexicalEntry.tones``, nothing
here keeps a second, structured copy; every consumer that needs the
position re-derives it from the IPA string, the same way
``sound_change.py``/``core.romanization`` already re-tokenize it for other
purposes).

``predict_default_stress`` (re-exported here from ``core.romanization``,
which owns it -- ``apply()``'s own ``"irregular_only"`` stress-accent
rendering needs it directly, and ``core`` can't depend on ``generation``)
is pure and deterministic -- reused both to *assign* the common case
here and, unchanged, by ``apply()`` to know what a word's stress *would*
have been by default, for languages whose real orthography only marks
stress when it deviates from that default (real Spanish's á/é/í/ó/ú)."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from conlang_generator.core.romanization import STRESS_MARK, predict_default_stress

if TYPE_CHECKING:
    from conlang_generator.generation.reference_languages import ReferenceLanguageProfile

_GENERIC_STRESS_DEVIATION_RATE = 0.3
"""The generic, no-source-language baseline: even under a single
dominant cross-linguistic default, real languages still have some genuine
unpredictability -- this is the same "sensible generic baseline" role
``lexicon_gen._GENERIC_AVERAGE_SYLLABLES`` plays for word length, not a
claim that 30% of words in some specific real language deviate."""


def resolve_stress_pattern(reference_profiles: tuple["ReferenceLanguageProfile", ...]) -> tuple[str, float | None]:
    """The first matched profile that has curated ``stress_pattern`` wins
    outright -- unlike ``core_vocabulary_average_syllables``'s numeric
    average, stress *typology* isn't a thing that sensibly blends across
    two unrelated languages (there's no meaningful "halfway between
    final-stress and initial-stress"). ``("", None)`` when none have --
    ``assign_stress`` already falls back to a generic baseline for that
    case. Shared by ``lexicon_gen.propose_word`` and
    ``root_pattern.propose_templatic_word`` so both resolve a matched
    source language's stress typology the same way."""
    for profile in reference_profiles:
        if profile.stress_pattern:
            return profile.stress_pattern, profile.stress_deviation_rate
    return "", None


def syllable_onset_starts(symbols: tuple[str, ...], vowel_symbols: frozenset[str]) -> tuple[int, ...]:
    """The index into ``symbols`` where each syllable's own onset begins,
    under the maximal-onset principle (the same rule
    ``core.romanization``'s own ``_coda_run_length`` already applies to a
    *romanized* string -- this is the phoneme-symbol-level equivalent, for
    callers that don't have per-syllable onset/nucleus/coda data of their
    own the way ``word_builder.build_word`` does). A run of consonants
    strictly between two vowels: every member but the last stays with the
    preceding syllable's coda, the last one starts the next syllable's
    onset. The first entry is always 0. ``(0,)`` for a vowel-less input
    (shouldn't arise for a real template, but stays defensive rather than
    raising)."""
    vowel_indices = [i for i, s in enumerate(symbols) if s in vowel_symbols]
    if not vowel_indices:
        return (0,)
    starts = [0]
    for prev_vowel, next_vowel in zip(vowel_indices, vowel_indices[1:]):
        starts.append(next_vowel - 1 if next_vowel - 1 > prev_vowel else next_vowel)
    return tuple(starts)


def mark_stress(
    rng: random.Random,
    filled_symbols: tuple[str, ...],
    vowel_symbols: frozenset[str],
    pattern: str,
    deviation_rate: float | None,
    strictness: float,
) -> str:
    """The templatic-word-formation counterpart of
    ``word_builder.build_word``'s own inline stress handling, for
    ``root_pattern.py``'s flat, already-filled skeleton (no per-syllable
    build loop to hook into there). Syllabifies via
    ``syllable_onset_starts``, assigns stress via ``assign_stress``, and
    returns the fully assembled string with ``STRESS_MARK`` spliced in
    before the stressed syllable's own onset -- omitted entirely for a
    monosyllable, same reasoning as ``word_builder.build_word``'s own
    handling of that case."""
    starts = syllable_onset_starts(filled_symbols, vowel_symbols)
    num_syllables = len(starts)
    if num_syllables <= 1:
        return "".join(filled_symbols)
    vowel_indices = [i for i, s in enumerate(filled_symbols) if s in vowel_symbols]
    final_coda = tuple(filled_symbols[vowel_indices[-1] + 1 :]) if vowel_indices else ()
    final_nucleus = filled_symbols[vowel_indices[-1]] if vowel_indices else ""
    stress_index = assign_stress(rng, num_syllables, final_coda, pattern, deviation_rate, strictness, final_nucleus)
    insert_at = starts[stress_index]
    return "".join(
        (STRESS_MARK if i == insert_at else "") + symbol for i, symbol in enumerate(filled_symbols)
    )


def assign_stress(
    rng: random.Random,
    num_syllables: int,
    final_coda: tuple[str, ...],
    pattern: str,
    deviation_rate: float | None,
    strictness: float,
    final_nucleus: str = "",
) -> int:
    """Picks the actual stressed syllable for one word: the
    ``pattern``-predicted default, occasionally overridden by a real
    deviation -- graded by ``strictness`` the same way every other
    reference-derived axis in ``phonology_gen.py`` is (0.0 = pure
    generic baseline, 1.0 = ``deviation_rate`` itself). ``pattern``/
    ``deviation_rate`` are the already-resolved values from whichever
    matched ``ReferenceLanguageProfile`` won (see
    ``resolve_stress_pattern`` above) -- this module has no
    dependency on ``reference_languages`` itself, the same separation
    ``word_builder.py`` already keeps from it. Never consulted for a
    monosyllable -- ``predict_default_stress`` already special-cases
    that, and there's nothing to deviate *to*. ``final_nucleus`` (the
    word's own last syllable's vowel) is passed straight through to
    ``predict_default_stress`` -- only ``"final_unless_unstressed_vowel"``
    (real Portuguese) reads it, every other pattern ignores it, same
    "only the pattern that needs an axis reads it" convention
    ``final_coda`` already has.

    ``strictness`` gates whether *this word* uses the curated pattern's
    own default+deviation-rate at all, rather than partially blending
    them with the generic baseline -- there's no coherent "70% initial-
    stress, 30% penultimate" middle ground for a single word the way a
    numeric rate can smoothly interpolate, so ``rng.random() < strictness``
    picks one pairing or the other outright per word (deterministically
    always the curated pairing at ``strictness=1.0``, since
    ``random()`` never reaches 1.0; always the generic pairing at
    ``strictness=0.0``)."""
    if num_syllables <= 1:
        return 0
    strictness = max(0.0, min(1.0, strictness))
    if pattern and rng.random() < strictness:
        default = predict_default_stress(num_syllables, pattern, final_coda, final_nucleus)
        rate = deviation_rate if deviation_rate is not None else _GENERIC_STRESS_DEVIATION_RATE
    else:
        default = predict_default_stress(num_syllables, "", final_coda, final_nucleus)
        rate = _GENERIC_STRESS_DEVIATION_RATE
    if rng.random() < rate:
        alternatives = [i for i in range(num_syllables) if i != default]
        return rng.choice(alternatives)
    return default
