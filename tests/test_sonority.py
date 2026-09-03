import random

from conlang_generator.core.phonology import Consonant, Manner, Place
from conlang_generator.generation import sonority

_t = Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, prevalence=0.92)
_d = Consonant(ipa="d", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=True, prevalence=0.65)
_p = Consonant(ipa="p", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, prevalence=0.92)
_b = Consonant(ipa="b", place=Place.BILABIAL, manner=Manner.STOP, voiced=True, prevalence=0.65)
_k = Consonant(ipa="k", place=Place.VELAR, manner=Manner.STOP, voiced=False, prevalence=0.90)
_g = Consonant(ipa="g", place=Place.VELAR, manner=Manner.STOP, voiced=True, prevalence=0.55)
_l = Consonant(ipa="l", place=Place.ALVEOLAR, manner=Manner.LATERAL_APPROXIMANT, voiced=True, prevalence=0.75)
_r = Consonant(ipa="r", place=Place.ALVEOLAR, manner=Manner.TRILL, voiced=True, prevalence=0.6)
_n = Consonant(ipa="n", place=Place.ALVEOLAR, manner=Manner.NASAL, voiced=True, prevalence=0.9)
_s = Consonant(ipa="s", place=Place.ALVEOLAR, manner=Manner.FRICATIVE, voiced=False, prevalence=0.8)


def test_coronal_stop_plus_coronal_lateral_onset_is_excluded():
    # /tl-/, /dl-/ satisfy rising sonority but are cross-linguistically
    # avoided (English, among others) -- a narrower restriction than a
    # blanket "same place" rule.
    assert not sonority.is_legal_onset_cluster(_t, _l)
    assert not sonority.is_legal_onset_cluster(_d, _l)


def test_non_coronal_stop_plus_lateral_onset_stays_legal():
    assert sonority.is_legal_onset_cluster(_p, _l)
    assert sonority.is_legal_onset_cluster(_b, _l)
    assert sonority.is_legal_onset_cluster(_k, _l)
    assert sonority.is_legal_onset_cluster(_g, _l)


def test_coronal_coronal_clusters_other_than_stop_plus_lateral_stay_legal():
    # The exclusion is specifically a coronal stop followed by a coronal
    # lateral, not a blanket coronal+coronal ban -- /tr/, /sn/, /sl/ are
    # all common and real despite both segments sharing coronal place.
    assert sonority.is_legal_onset_cluster(_t, _r)
    assert sonority.is_legal_onset_cluster(_s, _n)
    assert sonority.is_legal_onset_cluster(_s, _l)


def test_thin_cluster_pairs_returns_empty_for_empty_input():
    rng = random.Random(1)
    assert sonority.thin_cluster_pairs(rng, (), 0.0) == ()


def test_thin_cluster_pairs_returns_a_subset_and_never_empty():
    pairs = (("p", "l"), ("k", "l"), ("t", "r"), ("s", "t"), ("f", "l"), ("b", "r"))
    for seed in range(50):
        rng = random.Random(seed)
        kept = sonority.thin_cluster_pairs(rng, pairs, 0.0)
        assert kept
        assert set(kept) <= set(pairs)


def test_thin_cluster_pairs_floor_keeps_one_pair_even_at_zero_survival_rate():
    pairs = (("p", "l"), ("k", "l"), ("t", "r"))
    rng = random.Random(1)
    kept = sonority.thin_cluster_pairs(rng, pairs, contact_intensity=1.0)
    assert len(kept) >= 1
    assert set(kept) <= set(pairs)


def test_thin_cluster_pairs_higher_contact_intensity_thins_more_on_average():
    pairs = tuple((f"c{i}", "l") for i in range(30))

    def _avg_kept(contact_intensity: float, seeds: range) -> float:
        total = 0
        for seed in seeds:
            kept = sonority.thin_cluster_pairs(random.Random(seed), pairs, contact_intensity)
            total += len(kept)
        return total / len(seeds)

    seeds = range(100)
    assert _avg_kept(0.8, seeds) < _avg_kept(0.0, seeds)


def test_legal_coda_pairs_mirrors_legal_onset_pairs_shape():
    consonants = (_t, _d, _k, _s, _n, _l, _r)
    coda_pairs = sonority.legal_coda_pairs(consonants)
    assert coda_pairs
    for c1_ipa, c2_ipa in coda_pairs:
        by_ipa = {c.ipa: c for c in consonants}
        assert sonority.is_legal_coda_cluster(by_ipa[c1_ipa], by_ipa[c2_ipa])
