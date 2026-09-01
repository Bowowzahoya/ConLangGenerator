"""The sonority sequencing principle (SSP): within a syllable, sonority
rises toward the nucleus and falls away from it -- it's why /pl/, /tr/,
/sp/ work as clusters and /lp/, /rt/ don't as onsets.

Sonority is *derived* from ``Consonant.manner`` via ``_SONORITY_RANK``
rather than stored as its own per-phoneme field, so it can't drift out of
sync with manner and there's one less thing to hand-assign per symbol.
"""

from __future__ import annotations

from conlang_generator.core.phonology import Consonant, Manner

_SONORITY_RANK: dict[Manner, int] = {
    Manner.STOP: 1,
    Manner.AFFRICATE: 1,
    Manner.FRICATIVE: 2,
    Manner.LATERAL_FRICATIVE: 2,
    Manner.NASAL: 3,
    Manner.TAP: 4,
    Manner.TRILL: 4,
    Manner.LATERAL_APPROXIMANT: 4,
    Manner.APPROXIMANT: 5,
}


def sonority(consonant: Consonant) -> int:
    return _SONORITY_RANK[consonant.manner]


def is_legal_onset_cluster(c1: Consonant, c2: Consonant) -> bool:
    """Rising sonority toward the nucleus, plus the well-documented
    cross-linguistic exception for word-initial /s/ + voiceless stop
    (the classic "s-cluster" case -- technically falling sonority, but
    treated as extrasyllabic/exceptional in phonological theory rather
    than illegal)."""
    if c1.ipa == "s" and c2.manner is Manner.STOP and not c2.voiced:
        return True
    return sonority(c1) < sonority(c2)


def is_legal_coda_cluster(c1: Consonant, c2: Consonant) -> bool:
    """Falling sonority away from the nucleus -- the mirror image of
    onset legality."""
    return sonority(c1) > sonority(c2)
