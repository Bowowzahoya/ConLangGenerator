from conlang_generator.core.phonology import SyllableStructure


def test_onset_cluster_requires_allowlist():
    structure = SyllableStructure(max_onset=2, max_coda=1, allowed_onset_clusters=(("s", "t"),))
    assert structure.is_valid_syllable(("s", "t"), "a", ())
    assert not structure.is_valid_syllable(("p", "l"), "a", ())  # not in allowlist


def test_onset_over_max_is_invalid():
    structure = SyllableStructure(max_onset=1, max_coda=1)
    assert not structure.is_valid_syllable(("s", "t"), "a", ())


def test_coda_zero_forbids_any_coda():
    structure = SyllableStructure(max_onset=1, max_coda=0)
    assert structure.is_valid_syllable(("p",), "a", ())
    assert not structure.is_valid_syllable(("p",), "a", ("k",))


def test_restricted_coda_set():
    structure = SyllableStructure(max_onset=1, max_coda=1, allowed_coda_consonants=("n",))
    assert structure.is_valid_syllable((), "a", ("n",))
    assert not structure.is_valid_syllable((), "a", ("k",))


def test_excluded_coda_consonants_blocks_only_the_final_position():
    structure = SyllableStructure(max_onset=1, max_coda=1, excluded_coda_consonants=("d",))
    assert not structure.is_valid_syllable((), "a", ("d",))
    assert structure.is_valid_syllable((), "a", ("t",))

    # A 2-consonant coda is only checked on its *final* member -- "d" as
    # the non-final member of a cluster stays legal, matching real
    # final-obstruent devoicing's own scope (word-final position only).
    clustered = SyllableStructure(
        max_onset=1, max_coda=2, allowed_coda_clusters=(("d", "t"), ("t", "d")), excluded_coda_consonants=("d",)
    )
    assert clustered.is_valid_syllable((), "a", ("d", "t"))
    assert not clustered.is_valid_syllable((), "a", ("t", "d"))


def test_excluded_coda_consonants_is_independent_of_allowed_coda_consonants():
    # The two fields are orthogonal: a symbol can be in the positive
    # whitelist and still get blocked by the negative exclusion.
    structure = SyllableStructure(
        max_onset=1, max_coda=1, allowed_coda_consonants=("n", "d"), excluded_coda_consonants=("d",)
    )
    assert structure.is_valid_syllable((), "a", ("n",))
    assert not structure.is_valid_syllable((), "a", ("d",))


def test_excluded_onset_nucleus_pairs_blocks_only_that_combination():
    structure = SyllableStructure(max_onset=1, max_coda=0, excluded_onset_nucleus_pairs=(("w", "u"),))
    assert not structure.is_valid_syllable(("w",), "u", ())
    assert structure.is_valid_syllable(("w",), "a", ())  # same onset, different nucleus -- fine
    assert structure.is_valid_syllable(("t",), "u", ())  # same nucleus, different onset -- fine


def test_excluded_onset_nucleus_pairs_keys_on_the_final_onset_consonant():
    # A cluster's *last* consonant is what's adjacent to the nucleus --
    # the pair check uses onset[-1], not the whole cluster.
    structure = SyllableStructure(
        max_onset=2, max_coda=0, allowed_onset_clusters=(("d", "w"),), excluded_onset_nucleus_pairs=(("w", "u"),)
    )
    assert not structure.is_valid_syllable(("d", "w"), "u", ())
    assert structure.is_valid_syllable(("d", "w"), "a", ())


def test_allowed_onset_nucleus_pairs_is_a_whitelist():
    structure = SyllableStructure(max_onset=1, max_coda=0, allowed_onset_nucleus_pairs=(("t", "a"),))
    assert structure.is_valid_syllable(("t",), "a", ())
    assert not structure.is_valid_syllable(("t",), "u", ())
    assert not structure.is_valid_syllable(("k",), "a", ())  # onset itself never attested at all


def test_onset_nucleus_pair_restrictions_dont_apply_without_an_onset():
    # A vowel-initial syllable has no onset[-1] to check against at all.
    structure = SyllableStructure(max_onset=1, max_coda=0, excluded_onset_nucleus_pairs=(("w", "u"),))
    assert structure.is_valid_syllable((), "u", ())


def test_excluded_nucleus_coda_pairs_blocks_only_that_combination():
    structure = SyllableStructure(max_onset=0, max_coda=1, excluded_nucleus_coda_pairs=(("i", "ŋ"),))
    assert not structure.is_valid_syllable((), "i", ("ŋ",))
    assert structure.is_valid_syllable((), "i", ("n",))  # same nucleus, different coda -- fine
    assert structure.is_valid_syllable((), "a", ("ŋ",))  # same coda, different nucleus -- fine


def test_excluded_nucleus_coda_pairs_keys_on_the_first_coda_consonant():
    # The coda's *first* consonant is what's adjacent to the nucleus --
    # the pair check uses coda[0], not the whole cluster.
    structure = SyllableStructure(
        max_onset=0, max_coda=2, allowed_coda_clusters=(("ŋ", "k"),), excluded_nucleus_coda_pairs=(("i", "ŋ"),)
    )
    assert not structure.is_valid_syllable((), "i", ("ŋ", "k"))
    assert structure.is_valid_syllable((), "a", ("ŋ", "k"))


def test_allowed_nucleus_coda_pairs_is_a_whitelist():
    structure = SyllableStructure(max_onset=0, max_coda=1, allowed_nucleus_coda_pairs=(("ɪ", "ŋ"),))
    assert structure.is_valid_syllable((), "ɪ", ("ŋ",))
    assert not structure.is_valid_syllable((), "ɪ", ("n",))
    assert not structure.is_valid_syllable((), "a", ("ŋ",))  # nucleus itself never attested at all


def test_nucleus_coda_pair_restrictions_dont_apply_without_a_coda():
    structure = SyllableStructure(max_onset=0, max_coda=1, excluded_nucleus_coda_pairs=(("i", "ŋ"),))
    assert structure.is_valid_syllable((), "i", ())


def test_is_valid_boundary_passes_when_either_side_is_absent():
    structure = SyllableStructure(excluded_coda_onset_boundary_pairs=(("t", "l"),))
    assert structure.is_valid_boundary(None, "l")  # word start -- no previous coda
    assert structure.is_valid_boundary("t", None)  # next syllable is vowel-initial


def test_excluded_coda_onset_boundary_pairs_is_a_blacklist():
    structure = SyllableStructure(excluded_coda_onset_boundary_pairs=(("t", "l"),))
    assert not structure.is_valid_boundary("t", "l")
    assert structure.is_valid_boundary("t", "n")  # same prev coda, different next onset -- fine
    assert structure.is_valid_boundary("k", "l")  # same next onset, different prev coda -- fine


def test_allowed_coda_onset_boundary_pairs_is_a_whitelist():
    structure = SyllableStructure(allowed_coda_onset_boundary_pairs=(("n", "d"),))
    assert structure.is_valid_boundary("n", "d")
    assert not structure.is_valid_boundary("n", "t")
    assert not structure.is_valid_boundary("k", "d")  # prev coda itself never attested at all
