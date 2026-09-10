"""Verifies that a graded trait's strength scales directly to probability
(0 -> base rate, 1 -> certainty -- see ``generation/trait_bias.py``), and
that ``force_*`` flags guarantee an outcome unconditionally, independent of
``traits`` -- the two structurally separate channels described in
``core/spec.py``."""

from conlang_generator.core.language import Language
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient

_SEEDS = range(200)


_ALTITUDE_LINKED_EJECTIVES = frozenset({"pʼ", "tʼ", "kʼ"})
"""The specific ejective stops Everett (2013)'s altitude correlation
covers (phonology_gen.py's own `_EJECTIVES`/`traits.altitude` group).
Later batches added other, unrelated `ejective=True` consonants (Nama's
glottalized clicks, Navajo's ejective affricates) that draw from their
own flat prevalence rather than this altitude-biased group -- a generic
`c.ejective` check would no longer isolate altitude's effect once those
exist in the pool."""


def _has_ejectives(language: Language) -> bool:
    return any(c.ipa in _ALTITUDE_LINKED_EJECTIVES for c in language.phonology.consonants)


def _ejective_rate(altitude: float) -> float:
    client = FakeLLMClient()
    hits = sum(
        _has_ejectives(
            generate_language(
                "Test", GenerationSpec(prompt="p", seed=s, traits=TraitProfile(altitude=altitude)), client
            )
        )
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


def test_force_high_altitude_guarantees_ejectives_independent_of_traits():
    client = FakeLLMClient()
    for seed in range(50):
        spec = GenerationSpec(prompt="p", seed=seed, force_high_altitude=True)
        assert _has_ejectives(generate_language("Test", spec, client))
