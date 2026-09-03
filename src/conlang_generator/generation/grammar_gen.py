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
``FUSIONAL`` specifically, when ``traits.contact_languages`` matches a
reference profile with ``root_and_pattern=True`` (Arabic): the same
"clamp toward the matched reference" shape ``phonology_gen._reference_clamp``
already uses for tonal/vowel harmony, reimplemented here since it's
grammar-specific data.

Illustrative, not a rigorous typological model. ``plural_suffix``/
``templates`` are left unset here; ``generator.py`` fills in actual
phonological forms once the phoneme inventory exists.
"""

from __future__ import annotations

import random

from conlang_generator.core.grammar import Alignment, GrammarProfile, MorphologicalType, WordOrder
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.reference_languages import match_profiles
from conlang_generator.generation.trait_bias import biased_probability

_WORD_ORDERS = [WordOrder.SOV, WordOrder.SVO, WordOrder.VSO, WordOrder.VOS, WordOrder.OVS, WordOrder.OSV]
_WORD_ORDER_WEIGHTS = [45, 42, 9, 3, 1, 1]  # rough cross-linguistic frequency ordering

_CASE_LABELS = ("nominative", "accusative", "genitive", "dative", "locative")

_MIN_WEIGHT = 1.0  # rng.choices needs positive weights; floor after nudging

_ROOT_AND_PATTERN_BASE_RATE = 0.03  # narrow typological category by default
_ROOT_AND_PATTERN_REFERENCE_RATE = 0.85  # dominant, not absolute, when a matched profile uses it


def generate_grammar(rng: random.Random, spec: GenerationSpec) -> GrammarProfile:
    traits = spec.traits
    word_order = rng.choices(_WORD_ORDERS, weights=_WORD_ORDER_WEIGHTS)[0]
    reference_profiles = match_profiles(traits.contact_languages)
    root_and_pattern_reference = any(p.root_and_pattern for p in reference_profiles)

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
        morph_weights[MorphologicalType.FUSIONAL] = max(morph_weights[MorphologicalType.FUSIONAL], 60.0)
    morph_weights = {k: max(_MIN_WEIGHT, v) for k, v in morph_weights.items()}
    morphological_type = rng.choices(
        list(morph_weights.keys()), weights=list(morph_weights.values())
    )[0]

    uses_root_and_pattern_probability = (
        _ROOT_AND_PATTERN_REFERENCE_RATE if root_and_pattern_reference else _ROOT_AND_PATTERN_BASE_RATE
    )
    uses_root_and_pattern = rng.random() < uses_root_and_pattern_probability

    ergative_probability = (
        1.0 if spec.force_isolated else biased_probability(0.12, traits.isolation)
    )
    alignment = (
        Alignment.ERGATIVE_ABSOLUTIVE
        if rng.random() < ergative_probability
        else Alignment.NOMINATIVE_ACCUSATIVE
    )

    has_articles = rng.random() < 0.5
    adjective_after_noun = rng.random() < 0.5
    has_overt_copula = rng.random() < 0.6

    cases: tuple[str, ...] = ()
    if morphological_type is not MorphologicalType.ISOLATING:
        num_cases = rng.choice([2, 3, 4])
        cases = tuple(_CASE_LABELS[:num_cases])

    return GrammarProfile(
        word_order=word_order,
        morphological_type=morphological_type,
        alignment=alignment,
        has_articles=has_articles,
        adjective_after_noun=adjective_after_noun,
        has_overt_copula=has_overt_copula,
        cases=cases,
        plural_suffix=None,
        uses_root_and_pattern=uses_root_and_pattern,
        templates=(),
    )
