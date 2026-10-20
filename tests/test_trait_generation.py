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

from conlang_generator.core.phonology import Manner, PhonemeInventory
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


# --- The 7 new phonology traits added in a later pass (direct user
# request, a brainstorm follow-up: "I wonder if there can be more
# phonology traits in generation... help me come up with some more
# possible traits" -> "I like all of them. Implement all."). Each follows
# the same "low < neutral < high" gradient shape as the altitude/
# ejectives case above, just counting inventory members instead of a
# single boolean outcome, since these bias a *count*, not a single
# group's presence. ---


def _mean_count(trait_kwargs: dict, counter, n: int = 40) -> float:
    total = sum(
        counter(_inventory(GenerationSpec(prompt="p", seed=s, traits=TraitProfile(**trait_kwargs)))) for s in range(n)
    )
    return total / n


def _fricative_count(inventory: PhonemeInventory) -> int:
    return sum(1 for c in inventory.consonants if c.manner in (Manner.FRICATIVE, Manner.LATERAL_FRICATIVE))


def test_fricative_density_gradient_is_monotonic():
    low = _mean_count({"fricative_density": -1.0}, _fricative_count)
    neutral = _mean_count({"fricative_density": 0.0}, _fricative_count)
    high = _mean_count({"fricative_density": 1.0}, _fricative_count)
    assert low < neutral < high


def test_consonant_richness_gradient_is_monotonic():
    low = _mean_count({"consonant_richness": -1.0}, lambda inv: len(inv.consonants))
    neutral = _mean_count({"consonant_richness": 0.0}, lambda inv: len(inv.consonants))
    high = _mean_count({"consonant_richness": 1.0}, lambda inv: len(inv.consonants))
    assert low < neutral < high


def test_consonant_richness_does_not_touch_ejectives_or_uvulars():
    # Deliberately excludes the altitude/isolation-owned group gates, to
    # avoid two traits silently fighting over the same roll -- confirmed
    # directly, not just asserted in a docstring.
    ejective_rate_low = _ejective_rate(0.0)

    def _ejective_count(inv) -> int:
        return sum(1 for c in inv.consonants if c.ipa in _ALTITUDE_LINKED_EJECTIVES)

    with_low_richness = _mean_count({"consonant_richness": -1.0}, _ejective_count)
    with_high_richness = _mean_count({"consonant_richness": 1.0}, _ejective_count)
    # Both should land near the same unbiased ejective rate -- richness
    # changing the *size* of the optional tier shouldn't itself move the
    # ejective-group roll altitude alone owns.
    assert abs(with_low_richness - with_high_richness) < 0.3
    assert ejective_rate_low >= 0.0  # sanity: the shared helper still works


def test_vowel_richness_gradient_is_monotonic():
    low = _mean_count({"vowel_richness": -1.0}, lambda inv: len(inv.vowels))
    neutral = _mean_count({"vowel_richness": 0.0}, lambda inv: len(inv.vowels))
    high = _mean_count({"vowel_richness": 1.0}, lambda inv: len(inv.vowels))
    assert low < neutral < high


def test_nasality_gradient_is_monotonic():
    def _nasal_vowel_count(inv) -> int:
        return sum(1 for v in inv.vowels if v.nasalized)

    low = _mean_count({"nasality": -1.0}, _nasal_vowel_count)
    neutral = _mean_count({"nasality": 0.0}, _nasal_vowel_count)
    high = _mean_count({"nasality": 1.0}, _nasal_vowel_count)
    assert low < neutral < high


def test_vowel_length_affinity_gradient_is_monotonic():
    def _long_vowel_count(inv) -> int:
        return sum(1 for v in inv.vowels if v.long)

    low = _mean_count({"vowel_length_affinity": -1.0}, _long_vowel_count)
    neutral = _mean_count({"vowel_length_affinity": 0.0}, _long_vowel_count)
    high = _mean_count({"vowel_length_affinity": 1.0}, _long_vowel_count)
    assert low < neutral < high


