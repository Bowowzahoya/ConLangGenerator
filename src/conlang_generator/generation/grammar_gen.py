"""Seeded typological-parameter selection, weighted toward cross-linguistic
frequencies (SOV/SVO dominate word order; nominative-accusative dominates
alignment) with a small nudge from ``spec.isolated`` toward the rarer,
more-marked options -- illustrative, not a rigorous typological model.

``plural_suffix`` is left unset here; ``generator.py`` fills in an actual
phonological form once the phoneme inventory exists.
"""

from __future__ import annotations

import random

from conlang_generator.core.grammar import Alignment, GrammarProfile, MorphologicalType, WordOrder
from conlang_generator.core.spec import GenerationSpec

_WORD_ORDERS = [WordOrder.SOV, WordOrder.SVO, WordOrder.VSO, WordOrder.VOS, WordOrder.OVS, WordOrder.OSV]
_WORD_ORDER_WEIGHTS = [45, 42, 9, 3, 1, 1]  # rough cross-linguistic frequency ordering

_CASE_LABELS = ("nominative", "accusative", "genitive", "dative", "locative")


def generate_grammar(rng: random.Random, spec: GenerationSpec) -> GrammarProfile:
    word_order = rng.choices(_WORD_ORDERS, weights=_WORD_ORDER_WEIGHTS)[0]

    morph_weights = {
        MorphologicalType.FUSIONAL: 30,
        MorphologicalType.AGGLUTINATIVE: 30,
        MorphologicalType.ISOLATING: 25,
        MorphologicalType.POLYSYNTHETIC: 15,
    }
    if spec.isolated:
        morph_weights[MorphologicalType.POLYSYNTHETIC] += 20
        morph_weights[MorphologicalType.AGGLUTINATIVE] += 10
        morph_weights[MorphologicalType.ISOLATING] -= 15
    morphological_type = rng.choices(
        list(morph_weights.keys()), weights=list(morph_weights.values())
    )[0]

    ergative_probability = 0.35 if spec.isolated else 0.12
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
