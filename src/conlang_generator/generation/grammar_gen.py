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

Illustrative, not a rigorous typological model. ``plural_suffix`` is left
unset here; ``generator.py`` fills in an actual phonological form once the
phoneme inventory exists.
"""

from __future__ import annotations

import random

from conlang_generator.core.grammar import Alignment, GrammarProfile, MorphologicalType, WordOrder
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.trait_bias import biased_probability

_WORD_ORDERS = [WordOrder.SOV, WordOrder.SVO, WordOrder.VSO, WordOrder.VOS, WordOrder.OVS, WordOrder.OSV]
_WORD_ORDER_WEIGHTS = [45, 42, 9, 3, 1, 1]  # rough cross-linguistic frequency ordering

_CASE_LABELS = ("nominative", "accusative", "genitive", "dative", "locative")

_MIN_WEIGHT = 1.0  # rng.choices needs positive weights; floor after nudging


def generate_grammar(rng: random.Random, spec: GenerationSpec) -> GrammarProfile:
    traits = spec.traits
    word_order = rng.choices(_WORD_ORDERS, weights=_WORD_ORDER_WEIGHTS)[0]

    isolation_strength = 1.0 if spec.force_isolated else traits.isolation
    morph_weights = {
        MorphologicalType.FUSIONAL: 30.0,
        MorphologicalType.AGGLUTINATIVE: 30.0 + isolation_strength * 10 + traits.community_scale * 10,
        MorphologicalType.ISOLATING: 25.0 - isolation_strength * 15 + traits.contact_intensity * 25,
        MorphologicalType.POLYSYNTHETIC: 15.0 + isolation_strength * 20 + traits.community_scale * 15 - traits.contact_intensity * 15,
    }
    morph_weights = {k: max(_MIN_WEIGHT, v) for k, v in morph_weights.items()}
    morphological_type = rng.choices(
        list(morph_weights.keys()), weights=list(morph_weights.values())
    )[0]

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
    )
