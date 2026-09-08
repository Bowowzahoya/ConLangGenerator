"""Word accent: a closed, binary lexical prosodic contrast tied to a
word's own stressed syllable -- real Danish stød / Swedish and Norwegian
pitch accent (see ``core.phonology.WordAccentCategory`` for why these are
modeled as one mechanism with two ``realization``s, not two features).

Architecturally closer to ``stress_gen.py`` than to tone: like stress, the
category can't be decided until the accented syllable's own shape is
known (real Danish stød depends on the syllable's actual nucleus length
and coda sonority), so ``word_builder.build_word`` calls this only after
its own ``stress_index`` is resolved -- see that module's own docstring.
Unlike stress, there is no generic cross-linguistic fallback: most
languages don't have this feature at all, so ``assign_word_accent``
returns ``None`` (not a category) whenever the system isn't actually
gated in for this word, rather than falling back to some baseline the
way ``stress_gen.assign_stress`` always falls back to a stress position.

``predict_default_word_accent`` (re-exported here from
``core.romanization``, which owns it for the same "``apply()`` needs it
directly, and ``core`` can't depend on ``generation``" reason
``predict_default_stress`` does) is pure and deterministic."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from conlang_generator.core.phonology import TONE_DIACRITICS, ToneLevel, WordAccentCategory
from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK, predict_default_word_accent
from conlang_generator.generation import stress_gen

if TYPE_CHECKING:
    from conlang_generator.generation.reference_languages import ReferenceLanguageProfile

_GENERIC_WORD_ACCENT_DEVIATION_RATE = 0.2
"""Fallback lexical-exception rate when a matched profile curates
``word_accent_pattern`` but not its own ``word_accent_deviation_rate`` --
same "sensible generic baseline" role ``stress_gen._GENERIC_STRESS_DEVIATION_RATE``
plays, not a claim about any specific unmatched language."""

_PITCH_DIACRITICS: dict[WordAccentCategory, str] = {
    WordAccentCategory.ACCENT_1: TONE_DIACRITICS[ToneLevel.HIGH],
    WordAccentCategory.ACCENT_2: TONE_DIACRITICS[ToneLevel.LOW],
}
"""Reuses ``core.phonology.TONE_DIACRITICS``' two proven-safe combining
characters directly for the ``"pitch"`` realization's own two accent
marks, without coupling to ``ToneSystem`` itself -- see
``core.phonology.WordAccentSystem``'s own docstring for why this stays a
separate mechanism from tone despite sharing these two characters. Both
categories get a real mark here (unlike the ``"glottalization"``
realization's presence/absence shape), since pitch accent is a genuine
two-way contrast."""


def resolve_word_accent(
    reference_profiles: tuple["ReferenceLanguageProfile", ...],
) -> tuple[str, str, float | None]:
    """The first matched profile that has curated
    ``word_accent_realization`` wins outright -- same first-match, no-
    blending rule ``stress_gen.resolve_stress_pattern`` uses, for the same
    reason (there's no meaningful "halfway between glottalization and
    pitch"). ``("", "", None)`` when none have -- callers treat an empty
    ``realization`` as "this run's language doesn't have this feature",
    never attempting ``assign_word_accent`` at all."""
    for profile in reference_profiles:
        if profile.word_accent_realization:
            return profile.word_accent_realization, profile.word_accent_pattern, profile.word_accent_deviation_rate
    return "", "", None


def assign_word_accent(
    rng: random.Random,
    num_syllables: int,
    accented_nucleus: str,
    accented_coda: tuple[str, ...],
    pattern: str,
    deviation_rate: float | None,
    strictness: float,
) -> WordAccentCategory | None:
    """Picks this word's own word-accent category, or ``None`` if the
    system isn't gated in for it. ``pattern``/``deviation_rate`` are the
    already-resolved values from ``resolve_word_accent`` above -- this
    module has no dependency on ``reference_languages`` itself, the same
    separation ``stress_gen.py`` already keeps from it.

    Unlike ``stress_gen.assign_stress``, there's no generic-baseline
    ``else`` branch: when the ``rng.random() < strictness`` roll doesn't
    gate in (or ``pattern`` is empty), this word simply gets no word
    accent at all, since most languages don't have this feature and
    there's no sensible cross-linguistic default to fall back to the way
    stress always has one."""
    if not pattern:
        return None
    strictness = max(0.0, min(1.0, strictness))
    if rng.random() >= strictness:
        return None
    default = predict_default_word_accent(num_syllables, accented_nucleus, accented_coda, pattern)
    rate = deviation_rate if deviation_rate is not None else _GENERIC_WORD_ACCENT_DEVIATION_RATE
    if rng.random() < rate:
        other = WordAccentCategory.ACCENT_2 if default == WordAccentCategory.ACCENT_1 else WordAccentCategory.ACCENT_1
        return other
    return default


def mark_word_accent(category: WordAccentCategory | None, realization: str) -> str:
    """The literal mark (possibly empty) this word's accented syllable
    gets spliced with -- see ``word_builder.build_word`` for exactly
    where. ``category is None`` (the system didn't gate in for this word)
    always yields ``""``, regardless of ``realization``.

    ``"glottalization"`` (Danish stød): ``WORD_ACCENT_MARK`` for
    ``ACCENT_1``, ``""`` for ``ACCENT_2`` -- real stød convention treats
    absence as the unmarked default, not a second positive mark, unlike
    the genuine two-way ``"pitch"`` contrast below.
    ``"pitch"`` (Swedish/Norwegian): one of ``_PITCH_DIACRITICS``'s two
    combining characters, chosen by ``category`` -- both categories are
    marked here."""
    if category is None:
        return ""
    if realization == "glottalization":
        return WORD_ACCENT_MARK if category == WordAccentCategory.ACCENT_1 else ""
    if realization == "pitch":
        return _PITCH_DIACRITICS[category]
    return ""


def mark_stress_and_word_accent(
    rng: random.Random,
    filled_symbols: tuple[str, ...],
    vowel_symbols: frozenset[str],
    stress_pattern: str,
    stress_deviation_rate: float | None,
    stress_strictness: float,
    word_accent_realization: str = "",
    word_accent_pattern: str = "",
    word_accent_deviation_rate: float | None = None,
) -> str:
    """The templatic-word-formation counterpart of
    ``word_builder.build_word``'s own combined stress+word-accent handling,
    for ``root_pattern.py``'s (and ``sound_change._coin_native_word``'s)
    flat, already-filled skeleton -- no per-syllable build loop to hook
    into there, same reason ``stress_gen.mark_stress`` exists. Reimplements
    ``mark_stress``'s own syllabify-then-assign-stress steps rather than
    layering on top of it, since word accent needs the actual stress
    *index* (to find its accented syllable's own nucleus/coda for
    ``predict_default_word_accent``), which ``mark_stress`` computes but
    doesn't expose. An empty ``word_accent_pattern`` (the common case)
    makes the word-accent step a pure no-op, so this is a safe drop-in
    replacement for every ``mark_stress`` call site regardless of whether
    that language has word accent at all."""
    starts = stress_gen.syllable_onset_starts(filled_symbols, vowel_symbols)
    num_syllables = len(starts)
    vowel_indices = [i for i, s in enumerate(filled_symbols) if s in vowel_symbols]

    insert_at: int | None = None
    stress_index: int | None = None
    if num_syllables > 1:
        final_coda = tuple(filled_symbols[vowel_indices[-1] + 1 :]) if vowel_indices else ()
        stress_index = stress_gen.assign_stress(
            rng, num_syllables, final_coda, stress_pattern, stress_deviation_rate, stress_strictness
        )
        insert_at = starts[stress_index]

    mark_before: dict[int, str] = {insert_at: STRESS_MARK} if insert_at is not None else {}
    mark_after: dict[int, str] = {}
    if word_accent_pattern:
        accented_syllable = stress_index if stress_index is not None else 0
        syllable_start = starts[accented_syllable]
        syllable_end = starts[accented_syllable + 1] if accented_syllable + 1 < num_syllables else len(filled_symbols)
        nucleus_index = next(i for i in vowel_indices if syllable_start <= i < syllable_end)
        accented_nucleus = filled_symbols[nucleus_index]
        accented_coda = filled_symbols[nucleus_index + 1 : syllable_end]
        accent_category = assign_word_accent(
            rng, num_syllables, accented_nucleus, accented_coda,
            word_accent_pattern, word_accent_deviation_rate, stress_strictness,
        )
        accent_mark = mark_word_accent(accent_category, word_accent_realization)
        if accent_mark:
            # Glottalization marks the whole rime -- after its last
            # symbol (the nucleus itself when there's no coda). Pitch is a
            # combining diacritic -- it needs to ride the nucleus directly.
            mark_after[syllable_end - 1 if word_accent_realization == "glottalization" else nucleus_index] = accent_mark

    return "".join(
        mark_before.get(i, "") + symbol + mark_after.get(i, "") for i, symbol in enumerate(filled_symbols)
    )
