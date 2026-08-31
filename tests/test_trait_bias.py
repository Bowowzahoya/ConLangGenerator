from conlang_generator.generation.trait_bias import biased_probability


def test_zero_strength_returns_base_rate():
    assert biased_probability(0.1, 0.0) == 0.1


def test_full_strength_reaches_certainty():
    assert biased_probability(0.1, 1.0) == 1.0


def test_monotonic_in_strength():
    values = [biased_probability(0.1, s / 10) for s in range(11)]
    assert values == sorted(values)
    assert len(set(values)) == 11


def test_strength_is_clamped_to_unit_interval():
    assert biased_probability(0.1, -5.0) == 0.1
    assert biased_probability(0.1, 5.0) == 1.0
