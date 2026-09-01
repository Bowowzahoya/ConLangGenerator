from conlang_generator.generation.trait_bias import biased_probability


def test_zero_strength_returns_base_rate():
    assert biased_probability(0.1, 0.0) == 0.1


def test_full_positive_strength_reaches_certainty():
    assert biased_probability(0.1, 1.0) == 1.0


def test_full_negative_strength_reaches_zero():
    assert biased_probability(0.1, -1.0) == 0.0


def test_monotonic_across_full_bipolar_range():
    values = [biased_probability(0.3, s / 10) for s in range(-10, 11)]
    assert values == sorted(values)
    assert len(set(values)) == 21


def test_strength_is_clamped_to_bipolar_interval():
    assert biased_probability(0.1, -5.0) == 0.0
    assert biased_probability(0.1, 5.0) == 1.0
