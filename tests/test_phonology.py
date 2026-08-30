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
