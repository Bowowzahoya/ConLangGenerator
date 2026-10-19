"""Verifies that a graded trait's strength scales directly to probability
(0 -> base rate, 1 -> certainty -- see ``generation/trait_bias.py``).
`test_maximal_trait_strength_reaches_certainty` below is also what used to
be covered separately by a now-removed `force_high_altitude` flag test:
that flag was `1.0 if force_high_altitude else biased_probability(base,
altitude)`, which is simply `biased_probability(base, 1.0)` -- i.e.
byte-identical to `altitude=1.0` -- so the flag (and its
`force_isolated` sibling) were removed as pure duplication of this exact
math, not a distinct capability."""

import random

from conlang_generator.core.phonology import PhonemeInventory
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import phonology_gen

_SEEDS = range(200)


_ALTITUDE_LINKED_EJECTIVES = frozenset({"pʼ", "tʼ", "kʼ"})
"""The specific ejective stops Everett (2013)'s altitude correlation
covers (phonology_gen.py's own `_EJECTIVES`/`traits.altitude` group).
Later batches added other, unrelated `ejective=True` consonants (Nama's
glottalized clicks, Navajo's ejective affricates) that draw from their
own flat prevalence rather than this altitude-biased group -- a generic
`c.ejective` check would no longer isolate altitude's effect once those
exist in the pool."""


def _inventory(spec: GenerationSpec) -> PhonemeInventory:
    """The inventory ``generate_language`` would give this spec. Phonology is
    the first thing it draws from ``Random(spec.seed)``, so calling
    ``generate_phonology`` directly is identical -- and skips generating a
    whole lexicon for each of these hundreds of seeds."""
    return phonology_gen.generate_phonology(random.Random(spec.seed), spec)[0]


def _has_ejectives(inventory: PhonemeInventory) -> bool:
    return any(c.ipa in _ALTITUDE_LINKED_EJECTIVES for c in inventory.consonants)


def _ejective_rate(altitude: float) -> float:
    hits = sum(
        _has_ejectives(_inventory(GenerationSpec(prompt="p", seed=s, traits=TraitProfile(altitude=altitude))))
        for s in _SEEDS
    )
    return hits / len(_SEEDS)


def test_moderate_trait_strength_shifts_rate_without_forcing_it():
    low_rate = _ejective_rate(0.0)
    moderate_rate = _ejective_rate(0.5)

    assert low_rate < moderate_rate
    assert 0.0 < moderate_rate < 1.0  # a moderate reading biases, doesn't force


def test_maximal_trait_strength_reaches_certainty():
    # A strength of 1.0 *is* the intended probability, not capped short of
    # it -- the classifier is what's expected to keep this rare in practice.
    assert _ejective_rate(1.0) == 1.0


def test_maximal_negative_trait_strength_suppresses_to_zero():
    # Bipolar traits: -1.0 is evidence for the *opposite* pole (definitely
    # lowland), suppressing the outcome below its base rate entirely --
    # not just "no push," which is what 0.0 already means.
    assert _ejective_rate(-1.0) == 0.0


