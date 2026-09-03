"""The sonority sequencing principle (SSP): within a syllable, sonority
rises toward the nucleus and falls away from it -- it's why /pl/, /tr/,
/sp/ work as clusters and /lp/, /rt/ don't as onsets.

Sonority is *derived* from ``Consonant.manner`` via ``_SONORITY_RANK``
rather than stored as its own per-phoneme field, so it can't drift out of
sync with manner and there's one less thing to hand-assign per symbol.
"""

from __future__ import annotations

import random

from conlang_generator.core.phonology import Consonant, Manner, Place
from conlang_generator.generation.trait_bias import biased_probability

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


_ONSET_C1_MANNERS = {Manner.STOP, Manner.AFFRICATE, Manner.FRICATIVE, Manner.LATERAL_FRICATIVE}

# The well-documented cross-linguistic gap on /tl-/, /dl-/ (English, among
# others) despite satisfying rising sonority -- narrower than a blanket
# "same place" rule, which would incorrectly exclude real, common clusters
# like /sn-/, /sl-/ (s + coronal is fine; it's specifically a coronal stop
# followed by a coronal lateral that's avoided).
_CORONAL_PLACES = {Place.DENTAL, Place.ALVEOLAR, Place.POSTALVEOLAR}


def is_legal_onset_cluster(c1: Consonant, c2: Consonant) -> bool:
    """Rising sonority toward the nucleus, plus the well-documented
    cross-linguistic exception for word-initial /s/ + voiceless stop
    (the classic "s-cluster" case -- technically falling sonority, but
    treated as extrasyllabic/exceptional in phonological theory rather
    than illegal).

    Restricted to ``c1`` being an obstruent (stop/affricate/fricative):
    real onset clusters are overwhelmingly obstruent+sonorant (``pl``,
    ``tr``, ``fr``) -- a bare rising-sonority check would also accept
    nasal+liquid (``nr``, rank 3 < rank 4), which is cross-linguistically
    rare/marked as a word-initial cluster and not a pattern any of
    ``reference_languages``'s profiles (Dutch included) actually use.

    Also excludes a coronal stop followed by a coronal lateral (``tl``,
    ``dl``) -- see ``_CORONAL_PLACES``."""
    if c1.ipa == "s" and c2.manner is Manner.STOP and not c2.voiced:
        return True
    if not (c1.manner in _ONSET_C1_MANNERS and sonority(c1) < sonority(c2)):
        return False
    if (
        c1.manner is Manner.STOP
        and c2.manner is Manner.LATERAL_APPROXIMANT
        and c1.place in _CORONAL_PLACES
        and c2.place in _CORONAL_PLACES
    ):
        return False
    return True


def is_legal_coda_cluster(c1: Consonant, c2: Consonant) -> bool:
    """Falling sonority away from the nucleus -- the mirror image of
    onset legality."""
    return sonority(c1) > sonority(c2)


def legal_onset_pairs(consonants: tuple[Consonant, ...]) -> tuple[tuple[str, str], ...]:
    """Every legal 2-consonant onset cluster within a given consonant set,
    as ipa-symbol pairs -- shared by ``phonology_gen.generate_phonology``
    (initial generation), ``sound_change._recompute_syllable_structure``
    (which pairs are usable as clusters after evolution), and
    ``romanization_gen.py`` (which pairs let a syllable-conditioned
    romanization rule treat a whole cluster as belonging to the next
    syllable's onset, under the maximal-onset principle)."""
    return tuple(
        (c1.ipa, c2.ipa) for c1 in consonants for c2 in consonants if c1 is not c2 and is_legal_onset_cluster(c1, c2)
    )


def legal_coda_pairs(consonants: tuple[Consonant, ...]) -> tuple[tuple[str, str], ...]:
    """Every legal 2-consonant coda cluster within a given consonant set, as
    ipa-symbol pairs -- the coda-side mirror of ``legal_onset_pairs``,
    shared by ``phonology_gen.generate_phonology`` (initial generation) and
    ``sound_change._recompute_syllable_structure`` (post-evolution
    recomputation) so both stay in sync."""
    return tuple(
        (c1.ipa, c2.ipa) for c1 in consonants for c2 in consonants if c1 is not c2 and is_legal_coda_cluster(c1, c2)
    )


def exclude_final(
    pairs: tuple[tuple[str, str], ...], excluded_symbols: tuple[str, ...]
) -> tuple[tuple[str, str], ...]:
    """Every pair whose *second* (final) member isn't in
    ``excluded_symbols`` -- keeps a coda-cluster pool consistent with a
    final-position exclusion like devoicing (see
    ``core.phonology.SyllableStructure.excluded_coda_consonants``), so a
    thinned cluster can never end in a symbol that's actually illegal
    there."""
    if not excluded_symbols:
        return pairs
    return tuple(p for p in pairs if p[1] not in excluded_symbols)


_CLUSTER_SURVIVAL_BASE_RATE = 0.55


def thin_cluster_pairs(
    rng: random.Random, pairs: tuple[tuple[str, str], ...], contact_intensity: float = 0.0
) -> tuple[tuple[str, str], ...]:
    """Real languages use a gappier subset of their sonority-legal cluster
    space than the full combinatorial closure -- thin it via an
    independent per-pair draw, the same inclusion-draw idiom already used
    for individual phoneme selection (see ``phonology_gen.py``'s own
    docstring). ``contact_intensity`` pulls the survival rate down (heavy
    contact/creolization favors simpler phonotactics -- the same
    real-world mechanism ``sound_change.py``'s cluster-simplification rule
    already models on the evolution side), via the same
    ``biased_probability`` helper used throughout this codebase for
    trait-scaled probabilities. Always keeps at least one pair, so a
    language whose generation already decided to support clusters at all
    never silently ends up with none."""
    if not pairs:
        return pairs
    survival_rate = biased_probability(_CLUSTER_SURVIVAL_BASE_RATE, -contact_intensity)
    kept = tuple(p for p in pairs if rng.random() < survival_rate)
    return kept if kept else (rng.choice(pairs),)
