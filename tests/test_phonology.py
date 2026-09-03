from conlang_generator.core.phonology import SyllableStructure


def test_onset_cluster_requires_allowlist():
    structure = SyllableStructure(max_onset=2, max_coda=1, allowed_onset_clusters=(("s", "t"),))
    assert structure.is_valid_syllable(("s", "t"), ())
    assert not structure.is_valid_syllable(("p", "l"), ())  # not in allowlist


def test_onset_over_max_is_invalid():
    structure = SyllableStructure(max_onset=1, max_coda=1)
    assert not structure.is_valid_syllable(("s", "t"), ())


def test_coda_zero_forbids_any_coda():
    structure = SyllableStructure(max_onset=1, max_coda=0)
    assert structure.is_valid_syllable(("p",), ())
    assert not structure.is_valid_syllable(("p",), ("k",))


def test_restricted_coda_set():
    structure = SyllableStructure(max_onset=1, max_coda=1, allowed_coda_consonants=("n",))
    assert structure.is_valid_syllable((), ("n",))
    assert not structure.is_valid_syllable((), ("k",))


def test_excluded_coda_consonants_blocks_only_the_final_position():
    structure = SyllableStructure(max_onset=1, max_coda=1, excluded_coda_consonants=("d",))
    assert not structure.is_valid_syllable((), ("d",))
    assert structure.is_valid_syllable((), ("t",))

    # A 2-consonant coda is only checked on its *final* member -- "d" as
    # the non-final member of a cluster stays legal, matching real
    # final-obstruent devoicing's own scope (word-final position only).
    clustered = SyllableStructure(
        max_onset=1, max_coda=2, allowed_coda_clusters=(("d", "t"), ("t", "d")), excluded_coda_consonants=("d",)
    )
    assert clustered.is_valid_syllable((), ("d", "t"))
    assert not clustered.is_valid_syllable((), ("t", "d"))


def test_excluded_coda_consonants_is_independent_of_allowed_coda_consonants():
    # The two fields are orthogonal: a symbol can be in the positive
    # whitelist and still get blocked by the negative exclusion.
    structure = SyllableStructure(
        max_onset=1, max_coda=1, allowed_coda_consonants=("n", "d"), excluded_coda_consonants=("d",)
    )
    assert structure.is_valid_syllable((), ("n",))
    assert not structure.is_valid_syllable((), ("d",))
