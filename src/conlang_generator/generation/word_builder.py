"""Deterministic, phonotactically-valid word construction from a seeded RNG.

This is the one place that actually assembles IPA strings; it's reused for
whole lexicon entries (multiple syllables) and short grammatical affixes
(one syllable), so both are guaranteed to obey the language's own
``SyllableStructure``.

Phoneme selection is weighted by each candidate's ``prevalence`` (see
``core/phonology.py``) rather than uniform -- the same phonemes that are
more likely to be *in* a language's inventory are also more likely to show
up often *within* words once they are (the schwa-in-English effect).
"""

from __future__ import annotations

import random
from typing import Callable

from conlang_generator.core.phonology import (
    Consonant,
    Manner,
    PhonemeInventory,
    SyllableStructure,
    Vowel,
    VowelBackness,
    VowelHeight,
)
from conlang_generator.generation import stress_gen, word_accent_gen

_SMALL_HEIGHTS = (VowelHeight.CLOSE, VowelHeight.NEAR_CLOSE)
_BIG_HEIGHTS = (VowelHeight.OPEN, VowelHeight.NEAR_OPEN)
_OPEN_HEIGHTS = (VowelHeight.OPEN, VowelHeight.NEAR_OPEN)


def weighted_choice(rng: random.Random, options: tuple, multipliers: dict[str, float] | None = None):
    """``multipliers`` (symbol -> multiplier on top of its own
    ``prevalence``, e.g. ``SyllableStructure.onset_symbol_multipliers``)
    is an in-word sampling-frequency adjustment, not a replacement for
    ``prevalence`` -- a symbol absent from it keeps its plain
    ``prevalence`` unchanged (multiplier ``1.0``). ``None`` (every
    existing caller except ``_build_onset``/``_build_coda``/
    ``_choose_nucleus``) is a full no-op, byte-identical to this
    function before ``multipliers`` existed."""
    m = multipliers or {}
    weights = [max(o.prevalence * m.get(o.ipa, 1.0), 0.001) for o in options]
    return rng.choices(options, weights=weights)[0]


def _cluster_weight(cluster: tuple[str, str], by_symbol: dict[str, float], multipliers: dict[str, float] | None = None) -> float:
    m = multipliers or {}
    w0 = by_symbol.get(cluster[0], 0.001) * m.get(cluster[0], 1.0)
    w1 = by_symbol.get(cluster[1], 0.001) * m.get(cluster[1], 1.0)
    return max(w0 * w1, 0.001)


def _filter_by_adjacency(items: tuple, key: Callable, is_legal: Callable[[str], bool]) -> tuple:
    """Narrows ``items`` (cluster tuples or single-consonant/vowel
    candidates) to those whose adjacency-relevant member -- extracted by
    ``key`` -- ``is_legal`` accepts. Same "only narrow if it doesn't go
    empty" defensive shape used throughout this module for every other
    hard local constraint (``_choose_nucleus``'s onset-nucleus filter,
    ``excluded_onset_consonants``/``excluded_coda_consonants`` above)."""
    legal = tuple(item for item in items if is_legal(key(item)))
    return legal or items


def _build_onset(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    prev_coda_final: str | None = None,
) -> tuple[str, ...]:
    if structure.max_onset == 0:
        return ()
    onset_multipliers = dict(structure.onset_symbol_multipliers)
    if structure.max_onset >= 2 and structure.allowed_onset_clusters and rng.random() < 0.3:
        clusters = structure.allowed_onset_clusters
        if prev_coda_final is not None:
            clusters = _filter_by_adjacency(
                clusters, key=lambda c: c[0], is_legal=lambda s: structure.is_valid_boundary(prev_coda_final, s)
            )
        by_symbol = {c.ipa: c.prevalence for c in inventory.consonants}
        weights = [_cluster_weight(c, by_symbol, onset_multipliers) for c in clusters]
        return rng.choices(clusters, weights=weights)[0]
    candidates = inventory.consonants
    if structure.excluded_onset_consonants:
        # `or candidates` is defensive, same fallback shape `_build_coda`
        # already uses for `excluded_coda_consonants` -- not expected to
        # fire in practice, since a restricted-onset symbol is only ever
        # added when it's already present in the inventory.
        restricted = tuple(c for c in candidates if c.ipa not in structure.excluded_onset_consonants) or candidates
        candidates = restricted
    if prev_coda_final is not None:
        candidates = _filter_by_adjacency(
            candidates, key=lambda c: c.ipa, is_legal=lambda s: structure.is_valid_boundary(prev_coda_final, s)
        )
    return (weighted_choice(rng, candidates, onset_multipliers).ipa,)


def _build_coda(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    nucleus: str,
) -> tuple[str, ...]:
    if structure.max_coda == 0 or rng.random() < 0.4:
        return ()
    coda_multipliers = dict(structure.coda_symbol_multipliers)
    by_symbol = {c.ipa: c.prevalence for c in inventory.consonants}

    def is_legal_nucleus_coda(c: str) -> bool:
        pair = (nucleus, c)
        if structure.allowed_nucleus_coda_pairs is not None and pair not in structure.allowed_nucleus_coda_pairs:
            return False
        return pair not in structure.excluded_nucleus_coda_pairs

    if structure.max_coda >= 2 and structure.allowed_coda_clusters and rng.random() < 0.2:
        clusters = tuple(c for c in structure.allowed_coda_clusters if is_legal_nucleus_coda(c[0]))
        if clusters:
            weights = [_cluster_weight(c, by_symbol, coda_multipliers) for c in clusters]
            return rng.choices(clusters, weights=weights)[0]
        # No coda cluster is nucleus-coda-legal for this specific vowel --
        # fall through to the single-consonant branch below rather than
        # fabricating an illegal cluster (unlike `_build_onset`'s
        # "or candidates" fallbacks, a coda is always optional, so there's
        # an honest option here that doesn't exist for a mandatory onset).

    candidates = structure.allowed_coda_consonants or inventory.consonant_symbols()
    if structure.excluded_coda_consonants:
        # `or candidates` is defensive, not expected to fire in practice --
        # devoicing only excludes voiced obstruents, and the implicational
        # voiced-only-if-voiceless-present selection rule guarantees
        # plenty of non-excluded consonants (every voiceless obstruent,
        # every sonorant) always remain.
        candidates = tuple(c for c in candidates if c not in structure.excluded_coda_consonants) or candidates
    legal_candidates = tuple(c for c in candidates if is_legal_nucleus_coda(c))
    if not legal_candidates:
        # Same "honest empty result preferred over fabrication" choice as
        # `sonority.grade_against_attested`: a coda-eligible consonant set
        # this narrow (e.g. a sonorant-only coda profile combined with a
        # restrictive nucleus-coda pairing for this specific vowel) can
        # legitimately have zero legal codas for this syllable -- correctly
        # having no coda this time beats forcing an illegal one just to
        # have one, unlike the mandatory-onset case.
        return ()
    weights = [by_symbol.get(c, 0.001) * coda_multipliers.get(c, 1.0) for c in legal_candidates]
    return (rng.choices(legal_candidates, weights=weights)[0],)


def _choose_nucleus(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    onset_final: str | None = None,
    harmony_class: VowelBackness | None = None,
    size_bias: str | None = None,
) -> Vowel:
    """``size_bias`` ("small"/"big") is sound symbolism, not phonotactics --
    high front vowels statistically evoke smallness cross-linguistically,
    low back vowels largeness (Sapir 1929 and later replications). Applied
    as a soft preference, same as ``harmony_class``, and after it, so the
    two compose rather than one silently overriding the other.

    ``onset_final``'s legal-partner filtering runs *first*, as a hard
    constraint underneath both of those soft preferences (real
    onset+nucleus co-occurrence restrictions -- e.g. real English "dw-"
    never precedes a rounded vowel -- aren't a stylistic nudge the way
    harmony/size-bias are). Same defensive "only narrow the pool if it
    doesn't go empty" shape those two already use, so a stray/overly
    restrictive combination gets ignored rather than crashing generation."""
    vowels: tuple[Vowel, ...] = inventory.vowels
    if onset_final is not None:
        if structure.allowed_onset_nucleus_pairs is not None:
            legal = tuple(v for v in vowels if (onset_final, v.ipa) in structure.allowed_onset_nucleus_pairs)
            if legal:
                vowels = legal
        elif structure.excluded_onset_nucleus_pairs:
            legal = tuple(v for v in vowels if (onset_final, v.ipa) not in structure.excluded_onset_nucleus_pairs)
            if legal:
                vowels = legal
    if harmony_class is not None:
        matching = tuple(v for v in vowels if v.backness in (harmony_class, VowelBackness.CENTRAL))
        if matching and rng.random() < 0.9:  # small leak, like real harmony exceptions/loans
            vowels = matching
    if size_bias is not None:
        heights = _SMALL_HEIGHTS if size_bias == "small" else _BIG_HEIGHTS
        matching = tuple(v for v in vowels if v.height in heights)
        if matching and rng.random() < 0.8:
            vowels = matching
    return weighted_choice(rng, vowels, dict(structure.nucleus_symbol_multipliers))


def _build_syllable_parts(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    harmony_class: VowelBackness | None = None,
    size_bias: str | None = None,
    prev_coda_final: str | None = None,
) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    """The shared core of ``build_syllable``/``build_word``: builds one
    syllable's ``(onset, nucleus, coda)``. ``prev_coda_final`` -- the
    previous syllable's final coda consonant, when building a
    multi-syllable word -- lets the onset choice respect a cross-syllable
    coda-then-onset boundary restriction; ``None`` (word start, or a
    standalone single-syllable use like ``build_syllable``) skips that
    check entirely, same as every other position-dependent filter in this
    module being a no-op when its trigger is absent."""
    onset = _build_onset(rng, inventory, structure, prev_coda_final)
    onset_final = onset[-1] if onset else None
    nucleus = _choose_nucleus(rng, inventory, structure, onset_final, harmony_class, size_bias).ipa
    coda = _build_coda(rng, inventory, structure, nucleus)
    assert structure.is_valid_syllable(onset, nucleus, coda), (onset, nucleus, coda)
    # No assert on `is_valid_boundary` here, unlike the line above: unlike
    # a coda (always optional -- `_build_coda` can honestly return `()`
    # rather than fabricate an illegal one), an onset is mandatory
    # whenever `max_onset >= 1`, so `_build_onset`'s boundary filter falls
    # back to its unfiltered candidate pool (the same defensive shape
    # `excluded_onset_consonants` already uses) rather than leaving the
    # onset unbuildable -- a best-effort choice by construction, not
    # always a provably legal one, so asserting it here would risk
    # crashing generation on the rare case that fallback actually fires.
    return onset, nucleus, coda


def build_syllable(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    tone_mark: str = "",
    harmony_class: VowelBackness | None = None,
    size_bias: str | None = None,
) -> str:
    onset, nucleus, coda = _build_syllable_parts(rng, inventory, structure, harmony_class, size_bias)
    return "".join(onset) + nucleus + tone_mark + "".join(coda)


def build_class_suffix(rng: random.Random, inventory: PhonemeInventory, structure: SyllableStructure) -> tuple[str, ...]:
    """An invented citation-form class *suffix* (``generation.word_
    class_gen``'s own real Latin-``-us``/French-``-er``-style ending, for
    a language with no matched reference profile of its own) -- a
    nucleus plus optional legal coda, deliberately with **no onset**, so
    ``[any stem-final segment] + [this suffix]`` is always phonotactically
    safe by construction (vowel-initial can never form an illegal
    cluster) without needing a general phonotactic-repair mechanism. A
    real, if simplified, pattern -- many real declension endings genuinely
    are vowel-only (Latin's own ``-a``, Italian's ``-o``/``-a``/``-e``)."""
    nucleus = _choose_nucleus(rng, inventory, structure).ipa
    coda = _build_coda(rng, inventory, structure, nucleus)
    return (nucleus,) + coda


def build_class_prefix(rng: random.Random, inventory: PhonemeInventory, structure: SyllableStructure) -> tuple[str, ...]:
    """The prefixing counterpart of ``build_class_suffix`` -- an onset
    plus nucleus, deliberately with **no coda**, so ``[this prefix] +
    [any stem-initial segment]`` is always safe the same way (real Bantu
    noun-class prefixes like Swahili's own ``m-``/``ki-`` are exactly
    this CV shape)."""
    onset = _build_onset(rng, inventory, structure)
    nucleus = _choose_nucleus(rng, inventory, structure, onset[-1] if onset else None).ipa
    return onset + (nucleus,)


_STRESS_REDUCTION_RATE = 0.6
"""How often an eligible non-stressed syllable's nucleus reduces to
schwa when ``reduce_unstressed_vowels`` fires, at ``stress_strictness=1.0``
-- illustrative, not a corpus statistic (same honesty standard as every
other curated rate in this project), scaled to describe real English's
own famously aggressive reduction (about/sofa, item/silent) without
claiming every single non-stressed vowel in every language with this
feature reduces every time."""


def build_word(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    num_syllables: int,
    tone_marks: tuple[str, ...] = (),
    size_bias: str | None = None,
    stress_pattern: str = "",
    stress_deviation_rate: float | None = None,
    stress_strictness: float = 0.0,
    reduce_unstressed_vowels: bool = False,
    word_accent_realization: str = "",
    word_accent_pattern: str = "",
    word_accent_deviation_rate: float | None = None,
    word_accent_strictness: float = 0.0,
    word_accent_length_rate: float | None = None,
    word_accent_window: int | None = None,
) -> str:
    """``stress_pattern``/``stress_deviation_rate``/``stress_strictness``
    are the already-resolved values from whichever matched
    ``ReferenceLanguageProfile`` won (see
    ``lexicon_gen._resolve_stress_pattern``) -- this module has no
    dependency on ``reference_languages`` itself, only on
    ``stress_gen``, which doesn't either. Stress can't be decided until
    *after* every syllable is built (unlike a tone mark, which is fixed
    per syllable in advance): real Spanish's own default rule depends on
    the word's actual final coda, which only exists once the last
    syllable has actually been chosen -- so this collects every
    syllable's ``(onset, nucleus, coda)`` first, calls
    ``stress_gen.assign_stress`` with the real final syllable's own
    coda, and only then assembles the final string with
    ``stress_gen.STRESS_MARK`` prepended to the stressed syllable's own
    onset.

    ``reduce_unstressed_vowels`` (this run's matched
    ``ReferenceLanguageProfile.stress_driven_vowel_reduction`` -- see
    its own docstring) is real English/German/Dutch-style *synchronic*
    reduction, distinct from ``sound_change.py``'s own diachronic
    ``vowel_reduction`` rule (a generic drift-over-time tendency applied
    regardless of this flag): once stress is known, every *other*
    syllable's own already-chosen nucleus is a candidate to be swapped
    for "ə" outright (never re-drawn through the normal weighted
    machinery -- this is a targeted rewrite of one already-valid choice
    for another, the same "post-hoc probabilistic rewrite" shape
    ``sound_change._apply_vowel_reduction`` already uses), at
    ``_STRESS_REDUCTION_RATE`` scaled by ``stress_strictness``. A no-op
    whenever "ə" isn't actually in this run's own generated vowel
    inventory, or whenever swapping it in would violate this language's
    own nucleus-coda pairing rules (e.g. real English's own /ŋ/-only-
    after-a-checked-vowel restriction -- schwa doesn't license it) --
    checked via ``structure.is_valid_syllable`` before committing,
    skipped (not fabricated) rather than forced through, same
    "honest empty result over an invalid one" discipline
    ``_build_coda`` already practices.

    ``word_accent_*`` (this run's matched ``ReferenceLanguageProfile``'s
    own word-accent axes -- see ``generation.word_accent_gen``) marks the
    word's *accented* syllable -- its stressed syllable, or syllable 0
    for a monosyllable. Deliberately **not** ``stress_index`` directly:
    unlike ``STRESS_MARK``, which skips monosyllables (nothing to
    contrast against), real Danish stød is canonically a monosyllable
    phenomenon, so a monosyllable still needs an accented-syllable index
    even though ``stress_index`` is ``None`` for it. An empty
    ``word_accent_pattern`` (the common case -- most languages don't have
    this feature) makes this whole block a no-op, mirroring how an empty
    ``stress_pattern`` already falls through to a generic default rather
    than raising. ``"positional_pitch_accent"`` (real Japanese) is the one
    exception to "marks the accented syllable" above -- it marks every
    syllable at once, entirely independent of stress, via its own
    ``accent_marks`` array rather than the single ``accented_index`` this
    paragraph otherwise describes."""
    marks = tone_marks or ("",) * num_syllables
    harmony_class: VowelBackness | None = None
    if structure.vowel_harmony:
        harmony_class = rng.choice([VowelBackness.FRONT, VowelBackness.BACK])
    syllables: list[tuple[tuple[str, ...], str, tuple[str, ...]]] = []
    prev_coda_final: str | None = None
    for _ in range(num_syllables):
        onset, nucleus, coda = _build_syllable_parts(rng, inventory, structure, harmony_class, size_bias, prev_coda_final)
        syllables.append((onset, nucleus, coda))
        prev_coda_final = coda[-1] if coda else None
    # A monosyllable's own single syllable is trivially "the stressed
    # one" -- marking it conveys nothing (there's no other syllable to
    # contrast it with), the same reasoning real dictionary transcription
    # conventions already use to omit it there.
    stress_index = (
        stress_gen.assign_stress(
            rng, num_syllables, syllables[-1][2], stress_pattern, stress_deviation_rate, stress_strictness,
            syllables[-1][1], stress_gen.first_long_vowel_index(tuple(s[1] for s in syllables)),
        )
        if num_syllables > 1
        else None
    )
    accented_index = stress_index if stress_index is not None else 0
    accent_marks: tuple[str, ...] = ("",) * num_syllables
    if word_accent_pattern:
        if word_accent_realization == "positional_pitch_accent":
            # Unlike every other realization below, this one marks
            # potentially *every* syllable (not just the accented/stressed
            # one), entirely independent of stress -- see
            # `word_accent_gen.assign_positional_pitch_accent`'s own
            # docstring for why real Japanese kernel placement has no
            # shape-based default to compute here at all.
            kernel_index = word_accent_gen.assign_positional_pitch_accent(
                rng, num_syllables, word_accent_strictness, word_accent_window
            )
            long_nucleus_at_kernel = kernel_index is not None and syllables[kernel_index][1].endswith("ː")
            accent_marks = word_accent_gen.mark_positional_pitch_accent(kernel_index, num_syllables, long_nucleus_at_kernel)
        else:
            accented_nucleus, accented_coda = syllables[accented_index][1], syllables[accented_index][2]
            if word_accent_realization == "pitch_and_length":
                accent = word_accent_gen.assign_word_accent_with_length(
                    rng, num_syllables, accented_index,
                    word_accent_pattern, word_accent_deviation_rate, word_accent_length_rate, word_accent_strictness,
                )
                accent_mark = word_accent_gen.mark_word_accent_with_length(accent)
            else:
                accent_category = word_accent_gen.assign_word_accent(
                    rng, num_syllables, accented_nucleus, accented_coda,
                    word_accent_pattern, word_accent_deviation_rate, word_accent_strictness,
                )
                accent_mark = word_accent_gen.mark_word_accent(accent_category, word_accent_realization)
            accent_marks = tuple(accent_mark if i == accented_index else "" for i in range(num_syllables))
    if reduce_unstressed_vowels and num_syllables > 1 and "ə" in inventory.vowel_symbols():
        reduction_rate = _STRESS_REDUCTION_RATE * max(0.0, min(1.0, stress_strictness))
        for i, (onset, nucleus, coda) in enumerate(syllables):
            if i == stress_index or nucleus == "ə" or rng.random() >= reduction_rate:
                continue
            if structure.is_valid_syllable(onset, "ə", coda):
                syllables[i] = (onset, "ə", coda)
    parts: list[str] = []
    for i, (onset, nucleus, coda) in enumerate(syllables):
        prefix = stress_gen.STRESS_MARK if i == stress_index else ""
        this_accent_mark = accent_marks[i]
        if word_accent_realization == "glottalization":
            # Stød marks the whole rime, not just the vowel -- appended
            # after the coda rather than riding the nucleus.
            parts.append(prefix + "".join(onset) + nucleus + marks[i] + "".join(coda) + this_accent_mark)
        else:
            # A combining pitch diacritic (or no word accent at all) needs
            # a base vowel to ride -- goes right after the nucleus, same
            # position `marks[i]` (tone) already uses.
            parts.append(prefix + "".join(onset) + nucleus + this_accent_mark + marks[i] + "".join(coda))
    return "".join(parts)


def build_reduplicated_word(
    rng: random.Random,
    inventory: PhonemeInventory,
    manner_classes: tuple[Manner, ...],
    tone_mark: str = "",
    excluded_onset_consonants: tuple[str, ...] = (),
    stress_pattern: str = "",
    stress_deviation_rate: float | None = None,
    stress_strictness: float = 0.0,
    word_accent_realization: str = "",
    word_accent_pattern: str = "",
    word_accent_deviation_rate: float | None = None,
    word_accent_strictness: float = 0.0,
    word_accent_length_rate: float | None = None,
    word_accent_window: int | None = None,
) -> str | None:
    """A same-syllable-twice word (``mama``/``papa``-shaped): one onset
    consonant restricted to ``manner_classes``, one vowel preferring open
    height, repeated. Models the cross-linguistic convergence of basic
    kinship terms on the simplest sounds a human infant can produce
    (Jakobson 1960) -- not a phonotactic *style* rule, so it deliberately
    bypasses most of ``SyllableStructure`` (no coda, no cluster, no
    frequency weighting). ``excluded_onset_consonants`` (this language's
    ``SyllableStructure.excluded_onset_consonants``) is the one exception
    still enforced -- unlike everything else this function skips, it's a
    hard phonotactic fact, not a stylistic preference (real Dutch /ŋ/
    categorically cannot open *any* syllable, kinship term or not; a
    naive manner-only filter would otherwise happily produce "ŋaŋa" for
    a Dutch-biased language, which no real Dutch word could ever be).

    Structurally this is just an ordinary 2-syllable, coda-less word for
    stress-assignment purposes (the two syllables happen to be
    segmentally identical, but real stress placement is still audible
    and still governed by the same language-specific rule -- English
    "mama" is genuinely MA-ma, not interchangeable with a hypothetical
    ma-MA), so ``stress_pattern``/``stress_deviation_rate``/
    ``stress_strictness`` are resolved and applied the same way
    ``build_word`` does, via the same ``stress_gen.assign_stress``.
    ``word_accent_*`` get the same treatment, via the same
    ``word_accent_gen`` calls ``build_word`` uses -- the accented syllable
    is always whichever of the two stress picked (never syllable 0 by a
    monosyllable fallback, since a reduplicated word is always 2
    syllables).

    Returns ``None`` if the inventory has no consonant in any of
    ``manner_classes`` (the caller should fall back to normal generation).
    """
    candidates: tuple[Consonant, ...] = tuple(
        c
        for c in inventory.consonants
        if c.manner in manner_classes
        and c.ipa not in excluded_onset_consonants
        and not (c.ejective or c.aspirated or c.pharyngealized or c.long or c.palatalized or c.breathy)
    )
    if not candidates:
        return None
    consonant = weighted_choice(rng, candidates)
    simple_vowels = tuple(v for v in inventory.vowels if not v.diphthong and not v.nasalized)
    open_vowels = tuple(v for v in simple_vowels if v.height in _OPEN_HEIGHTS)
    vowel = weighted_choice(rng, open_vowels or simple_vowels or inventory.vowels)
    syllable = consonant.ipa + vowel.ipa + tone_mark
    reduplicated_first_long = stress_gen.first_long_vowel_index((vowel.ipa, vowel.ipa))
    stress_index = stress_gen.assign_stress(
        rng, 2, (), stress_pattern, stress_deviation_rate, stress_strictness, vowel.ipa, reduplicated_first_long
    )
    accent_marks: tuple[str, str] = ("", "")
    if word_accent_pattern:
        if word_accent_realization == "positional_pitch_accent":
            kernel_index = word_accent_gen.assign_positional_pitch_accent(
                rng, 2, word_accent_strictness, word_accent_window
            )
            long_nucleus_at_kernel = kernel_index is not None and vowel.ipa.endswith("ː")
            accent_marks = word_accent_gen.mark_positional_pitch_accent(kernel_index, 2, long_nucleus_at_kernel)
        elif word_accent_realization == "pitch_and_length":
            accent = word_accent_gen.assign_word_accent_with_length(
                rng, 2, stress_index,
                word_accent_pattern, word_accent_deviation_rate, word_accent_length_rate, word_accent_strictness,
            )
            accent_mark = word_accent_gen.mark_word_accent_with_length(accent)
            accent_marks = (accent_mark if stress_index == 0 else "", accent_mark if stress_index == 1 else "")
        else:
            accent_category = word_accent_gen.assign_word_accent(
                rng, 2, vowel.ipa, (), word_accent_pattern, word_accent_deviation_rate, word_accent_strictness,
            )
            accent_mark = word_accent_gen.mark_word_accent(accent_category, word_accent_realization)
            accent_marks = (accent_mark if stress_index == 0 else "", accent_mark if stress_index == 1 else "")
    first_syllable = syllable + accent_marks[0]
    second_syllable = syllable + accent_marks[1]
    first = (stress_gen.STRESS_MARK if stress_index == 0 else "") + first_syllable
    second = (stress_gen.STRESS_MARK if stress_index == 1 else "") + second_syllable
    return first + second
