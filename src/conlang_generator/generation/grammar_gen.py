"""Seeded typological-parameter selection, weighted toward cross-linguistic
frequencies (SOV/SVO dominate word order; nominative-accusative dominates
alignment), nudged -- probabilistically, see ``trait_bias.biased_probability``
-- by a few graded traits:

- ``traits.isolation`` / ``traits.community_scale`` push morphology toward
  the rarer, more internally-elaborated polysynthetic/agglutinative types
  (small, tight-knit, low-contact communities tolerate more grammatical
  complexity -- Trudgill's sociolinguistic typology) and raise the odds of
  ergative alignment.
- ``traits.contact_intensity`` pulls the opposite way, toward
  isolating/analytic morphology (a standard creolization/high-contact
  tendency).

``spec.force_isolated`` bypasses the probabilities entirely (maximal
polysynthetic/agglutinative pull, guaranteed ergative alignment) -- the
deterministic testing/override channel.

``uses_root_and_pattern`` is a separate axis (see
``core.grammar.GrammarProfile``'s own docstring for why it isn't a 5th
``MorphologicalType`` value) with a low base rate -- real root-and-pattern
morphology is a narrow typological category -- boosted, along with
``FUSIONAL`` specifically, when ``traits.source_languages`` matches a
reference profile with ``root_and_pattern=True`` (Arabic): the same
"clamp toward the matched reference" shape ``phonology_gen._reference_clamp``
already uses for tonal/vowel harmony, reimplemented here since it's
grammar-specific data. ``traits.source_language_strictness`` pulls that
boost further toward certainty (a no-op at its default ``0.0``) -- see
``phonology_gen.py``'s own module docstring for the shared mechanism.

``word_order``/``alignment``/``has_articles``/``has_overt_copula``/
``adjective_after_noun``/``cases`` get this same reference-bias treatment
now too, via each matched profile's own ``real_word_order``/``real_
alignment``/``real_has_articles``/``real_has_overt_copula``/``real_
adjective_after_noun``/``real_case_count`` (``None`` when a profile hasn't
been curated for these facts yet -- abstains, same convention as every
other optional reference field). ``source_language_weights`` is
consulted from the start here, exactly the same ``match_profiles_
weighted`` mechanism ``phonology_gen.py``/``romanization_gen.py``/``word_
class_gen.py`` already use.

Illustrative, not a rigorous typological model. ``plural_suffix``/
``templates`` are left unset here; ``generator.py`` fills in actual
phonological forms once the phoneme inventory exists.
"""

from __future__ import annotations

import random

from conlang_generator.core.grammar import Alignment, GrammarProfile, MorphologicalType, WordOrder
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.reference_languages import (
    ReferenceLanguageProfile,
    match_profiles,
    match_profiles_weighted,
)
from conlang_generator.generation.trait_bias import biased_probability

WeightedProfiles = tuple[tuple[ReferenceLanguageProfile, float], ...]

_WORD_ORDERS = [WordOrder.SOV, WordOrder.SVO, WordOrder.VSO, WordOrder.VOS, WordOrder.OVS, WordOrder.OSV]
_WORD_ORDER_WEIGHTS = [45, 42, 9, 3, 1, 1]  # rough cross-linguistic frequency ordering
_WORD_ORDER_REFERENCE_BOOST = 3.0  # same "*4 at full weight" shape phonology_gen.py's own coda_weights boost uses

_CASE_LABELS = ("nominative", "accusative", "genitive", "dative", "locative")

_TENSE_LABELS_TWO_WAY = ("past", "non_past")
_TENSE_LABELS_THREE_WAY = ("past", "present", "future")
"""Two illustrative tense systems -- a simple past/non-past split (a real
cross-linguistic pattern, e.g. Japanese) or the more familiar 3-way past/
present/future -- rolled per language with no reference bias of its own
(no per-profile tense-system data curated yet)."""

_MIN_WEIGHT = 1.0  # rng.choices needs positive weights; floor after nudging

_ROOT_AND_PATTERN_BASE_RATE = 0.03  # narrow typological category by default
_ROOT_AND_PATTERN_REFERENCE_RATE = 0.85  # dominant, not absolute, when a matched profile uses it
_STRICT_FUSIONAL_WEIGHT_CEILING = 200.0  # dwarfs every other morphological-type weight at strictness=1.0

_BOOLEAN_REFERENCE_TRUE_CEILING = 0.9  # dominant, not absolute, when matched profiles agree the axis is true
_BOOLEAN_REFERENCE_FALSE_FLOOR = 0.1  # symmetric suppression when matched profiles agree the axis is false

_ERGATIVE_REFERENCE_TRUE_FLOOR = 0.75  # same soft-clamp floor phonology_gen._reference_clamp already uses
_ERGATIVE_REFERENCE_FALSE_CEILING = 0.08


def _boolean_reference_bias(
    base_rate: float, weighted_profiles: WeightedProfiles, attr: str, strictness: float
) -> float:
    """Weighted-fraction reference bias for a plain optional-boolean
    typological axis (``has_articles``/``has_overt_copula``/``adjective_
    after_noun``) -- the same "boost toward the matched value, suppress
    toward its opposite at high strictness" shape ``uses_root_and_
    pattern_probability`` below already has, generalized into one helper
    since three different axes in this file need the identical treatment.
    Each matched profile's own value is ``True``/``False``/``None``
    (uncurated, abstains) -- ``weighted_true``/``weighted_false`` are
    independently capped at 1.0 and, since a single profile can only ever
    contribute to one of the two, can't both be positive from the same
    profile. A no-op (returns ``base_rate`` unchanged) when no matched
    profile has curated this attribute at all -- reproduces today's flat
    coin-flip exactly."""
    weighted_true = min(1.0, sum(weight for profile, weight in weighted_profiles if getattr(profile, attr) is True))
    weighted_false = min(1.0, sum(weight for profile, weight in weighted_profiles if getattr(profile, attr) is False))
    if weighted_true > 0.0:
        rate = base_rate + weighted_true * (_BOOLEAN_REFERENCE_TRUE_CEILING - base_rate)
        return biased_probability(rate, strictness * weighted_true) if strictness > 0.0 else rate
    if weighted_false > 0.0:
        rate = base_rate + weighted_false * (_BOOLEAN_REFERENCE_FALSE_FLOOR - base_rate)
        return biased_probability(rate, -strictness * weighted_false) if strictness > 0.0 else rate
    return base_rate


def generate_grammar(rng: random.Random, spec: GenerationSpec) -> GrammarProfile:
    traits = spec.traits
    reference_profiles = match_profiles(traits.source_languages)
    weighted_profiles = match_profiles_weighted(traits.source_languages, traits.source_language_weights)
    strictness = traits.source_language_strictness if reference_profiles else 0.0

    # Weighted-union, not a flat cross-linguistic-frequency roll: a
    # matched profile's own real_word_order gets its weight's worth of
    # boost (same "*4 at full weight" shape phonology_gen.py's own
    # coda_weights uses for coda_profile), then strictness further
    # reshapes the whole distribution toward it. A no-op (byte-identical
    # to the original flat _WORD_ORDER_WEIGHTS) when no matched profile
    # has curated real_word_order at all.
    word_order_weight: dict[WordOrder, float] = {}
    for profile, weight in weighted_profiles:
        if profile.real_word_order is not None:
            word_order_weight[profile.real_word_order] = min(
                1.0, word_order_weight.get(profile.real_word_order, 0.0) + weight
            )
    word_order_weights = list(_WORD_ORDER_WEIGHTS)
    if word_order_weight:
        word_order_weights = [
            w * (1 + _WORD_ORDER_REFERENCE_BOOST * word_order_weight.get(order, 0.0))
            for order, w in zip(_WORD_ORDERS, word_order_weights)
        ]
        if strictness > 0.0:
            total = sum(word_order_weights)
            word_order_weights = [
                total * biased_probability(
                    w / total,
                    strictness * word_order_weight.get(order, 0.0) if word_order_weight.get(order, 0.0) > 0.0 else -strictness,
                )
                for order, w in zip(_WORD_ORDERS, word_order_weights)
            ]
    word_order = rng.choices(_WORD_ORDERS, weights=word_order_weights)[0]

    # Weighted fraction, not a boolean-any: a language that's 30%-weighted
    # toward a root-and-pattern source (Arabic) should nudge fusional/
    # root-and-pattern odds up only a little, not as hard as a fully-
    # weighted match would -- feeds both the `fusional_floor` interpolation
    # and `uses_root_and_pattern_probability` below continuously.
    weighted_root_and_pattern = min(1.0, sum(weight for profile, weight in weighted_profiles if profile.root_and_pattern))
    root_and_pattern_reference = weighted_root_and_pattern > 0.0

    isolation_strength = 1.0 if spec.force_isolated else traits.isolation
    morph_weights = {
        MorphologicalType.FUSIONAL: 30.0,
        MorphologicalType.AGGLUTINATIVE: 30.0 + isolation_strength * 10 + traits.community_scale * 10,
        MorphologicalType.ISOLATING: 25.0 - isolation_strength * 15 + traits.contact_intensity * 25,
        MorphologicalType.POLYSYNTHETIC: 15.0 + isolation_strength * 20 + traits.community_scale * 15 - traits.contact_intensity * 15,
    }
    if root_and_pattern_reference:
        # Arabic's inflectional system is empirically fusional -- bias
        # toward that value specifically, not just "any of the four".
        # `strictness` scales the boost further (not just the flat 60.0
        # ceiling) -- morphological_type is a 4-way weighted choice, not a
        # boolean, so there's no clean "certainty" to pull toward the way
        # the other reference-bias axes have; a very large ceiling weight
        # is the closest equivalent, dwarfing the other three options.
        # `weighted_root_and_pattern` then interpolates continuously
        # between the unboosted baseline and that ceiling -- at full
        # weight (a single matched profile, or several agreeing ones) this
        # reduces to exactly the old flat floor.
        fusional_ceiling = 60.0
        if strictness > 0.0:
            fusional_ceiling = fusional_ceiling + strictness * (_STRICT_FUSIONAL_WEIGHT_CEILING - fusional_ceiling)
        fusional_floor = morph_weights[MorphologicalType.FUSIONAL] + weighted_root_and_pattern * (
            fusional_ceiling - morph_weights[MorphologicalType.FUSIONAL]
        )
        morph_weights[MorphologicalType.FUSIONAL] = max(morph_weights[MorphologicalType.FUSIONAL], fusional_floor)
    morph_weights = {k: max(_MIN_WEIGHT, v) for k, v in morph_weights.items()}
    morphological_type = rng.choices(
        list(morph_weights.keys()), weights=list(morph_weights.values())
    )[0]

    # Weighted-fraction interpolation between the narrow base rate and the
    # reference-dominant rate, not a boolean cliff -- at full weight (a
    # single matched profile, or several agreeing ones) this reduces to
    # exactly the old two-value choice.
    uses_root_and_pattern_probability = _ROOT_AND_PATTERN_BASE_RATE + weighted_root_and_pattern * (
        _ROOT_AND_PATTERN_REFERENCE_RATE - _ROOT_AND_PATTERN_BASE_RATE
    )
    if strictness > 0.0:
        # Symmetric pull, same shape as _reference_biased_rate elsewhere:
        # boosts when a matched source language really is root-and-pattern
        # (Arabic), suppresses toward exactly 0% at strictness=1.0 when it
        # isn't (English should never roll Semitic-style morphology at
        # full strictness). A no-op when there's no source language at
        # all -- strictness is already forced to 0.0 in that case, above.
        uses_root_and_pattern_probability = biased_probability(
            uses_root_and_pattern_probability,
            strictness * weighted_root_and_pattern if root_and_pattern_reference else -strictness,
        )
    uses_root_and_pattern = rng.random() < uses_root_and_pattern_probability

    ergative_probability = (
        1.0 if spec.force_isolated else biased_probability(0.12, traits.isolation)
    )
    # Alignment has a real curated *opposite* to lean on (unlike most
    # boolean axes, where absence never distinguishes "curated false" from
    # "uncurated") -- weighted_ergative/weighted_nominative are each
    # independently capped at 1.0 and, since a profile's own real_
    # alignment is one Alignment value or None, can't both be positive
    # from the same profile. A no-op (untouched trait-only baseline) when
    # no matched profile has curated real_alignment at all.
    weighted_ergative = min(
        1.0, sum(weight for profile, weight in weighted_profiles if profile.real_alignment is Alignment.ERGATIVE_ABSOLUTIVE)
    )
    weighted_nominative = min(
        1.0, sum(weight for profile, weight in weighted_profiles if profile.real_alignment is Alignment.NOMINATIVE_ACCUSATIVE)
    )
    if weighted_ergative > 0.0:
        ergative_probability = _ERGATIVE_REFERENCE_TRUE_FLOOR + weighted_ergative * (
            max(ergative_probability, _ERGATIVE_REFERENCE_TRUE_FLOOR) - _ERGATIVE_REFERENCE_TRUE_FLOOR
        )
        if strictness > 0.0:
            ergative_probability = biased_probability(ergative_probability, strictness * weighted_ergative)
    elif weighted_nominative > 0.0:
        ergative_probability = min(ergative_probability, _ERGATIVE_REFERENCE_FALSE_CEILING)
        if strictness > 0.0:
            ergative_probability = biased_probability(ergative_probability, -strictness * weighted_nominative)
    alignment = (
        Alignment.ERGATIVE_ABSOLUTIVE
        if rng.random() < ergative_probability
        else Alignment.NOMINATIVE_ACCUSATIVE
    )

    has_articles_probability = _boolean_reference_bias(0.5, weighted_profiles, "real_has_articles", strictness)
    has_articles = rng.random() < has_articles_probability
    adjective_after_noun_probability = _boolean_reference_bias(
        0.5, weighted_profiles, "real_adjective_after_noun", strictness
    )
    adjective_after_noun = rng.random() < adjective_after_noun_probability
    has_overt_copula_probability = _boolean_reference_bias(0.6, weighted_profiles, "real_has_overt_copula", strictness)
    has_overt_copula = rng.random() < has_overt_copula_probability

    cases: tuple[str, ...] = ()
    if morphological_type is not MorphologicalType.ISOLATING:
        # Same unbiased roll as before, always -- preserves the exact rng
        # draw and, at strictness=0 or with no curated real_case_count
        # among matched profiles, the exact outcome. Only once both are
        # present does strictness nudge the result toward the weighted
        # average of matched profiles' own real case count (mirroring
        # phonology_gen._resolve_position_multipliers's weighted-average
        # shape) -- a single fully-weighted match at strictness=1.0
        # converges exactly to that language's own real count, including
        # 0 (a real, curated lack of case marking, e.g. French/English/
        # Mandarin/Swahili/Thai/Dutch) even for a rolled non-isolating
        # morphological_type, since case marking and synthesis are
        # independent typological axes.
        num_cases = rng.choice([2, 3, 4])
        curated_case_counts = [
            (profile.real_case_count, weight)
            for profile, weight in weighted_profiles
            if profile.real_case_count is not None
        ]
        if curated_case_counts and strictness > 0.0:
            total_weight = min(1.0, sum(weight for _, weight in curated_case_counts))
            target_count = sum(count * weight for count, weight in curated_case_counts) / sum(
                weight for _, weight in curated_case_counts
            )
            num_cases = round(num_cases + strictness * total_weight * (target_count - num_cases))
            num_cases = max(0, min(len(_CASE_LABELS), num_cases))
        if num_cases > 0:
            cases = tuple(_CASE_LABELS[:num_cases])

    # No cross-linguistic tendency this project curates to lean on for
    # which tense system a language has -- an illustrative coin flip, the
    # same honesty `is_prefixing`'s own invented-class coin flip already
    # has (see `word_class_gen.py`).
    tenses = _TENSE_LABELS_THREE_WAY if rng.random() < 0.5 else _TENSE_LABELS_TWO_WAY

    return GrammarProfile(
        word_order=word_order,
        morphological_type=morphological_type,
        alignment=alignment,
        has_articles=has_articles,
        adjective_after_noun=adjective_after_noun,
        has_overt_copula=has_overt_copula,
        cases=cases,
        tenses=tenses,
        plural_suffix=None,
        uses_root_and_pattern=uses_root_and_pattern,
        templates=(),
    )
