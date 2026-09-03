"""Phoneme inventories, tone systems, and syllable-structure (phonotactic) models.

All models are frozen; derive a changed copy with ``model_copy(update=...)``.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class Place(str, Enum):
    BILABIAL = "bilabial"
    LABIODENTAL = "labiodental"
    DENTAL = "dental"
    ALVEOLAR = "alveolar"
    POSTALVEOLAR = "postalveolar"
    RETROFLEX = "retroflex"
    PALATAL = "palatal"
    VELAR = "velar"
    UVULAR = "uvular"
    PHARYNGEAL = "pharyngeal"
    GLOTTAL = "glottal"


class Manner(str, Enum):
    STOP = "stop"
    NASAL = "nasal"
    FRICATIVE = "fricative"
    AFFRICATE = "affricate"
    APPROXIMANT = "approximant"
    TRILL = "trill"
    TAP = "tap"
    LATERAL_APPROXIMANT = "lateral_approximant"
    LATERAL_FRICATIVE = "lateral_fricative"
    LATERAL_AFFRICATE = "lateral_affricate"


class Consonant(BaseModel, frozen=True):
    ipa: str
    place: Place
    manner: Manner
    voiced: bool
    ejective: bool = False
    aspirated: bool = False
    pharyngealized: bool = False
    long: bool = False
    palatalized: bool = False
    breathy: bool = False
    """Murmured/breathy voice (Hindi/Bengali-style, e.g. ``"bʱ"``) --
    phonemically voiced *and* breathy simultaneously, a 4th member
    alongside plain voiceless/voiceless-aspirated/plain-voiced stops,
    not a variant of ``voiced`` or ``aspirated`` alone."""
    prevalence: float = 0.5
    """Rough cross-linguistic commonness, ~0-1. Reused two ways: as this
    symbol's inclusion probability when a language's inventory is built
    (generation/phonology_gen.py), and as its sampling weight among
    whichever symbols made it into a given inventory when words are built
    (generation/word_builder.py). Illustrative approximation (informed by
    general typological consensus, e.g. Maddieson's surveys), not a
    precise statistic."""


class VowelHeight(str, Enum):
    CLOSE = "close"
    NEAR_CLOSE = "near_close"
    CLOSE_MID = "close_mid"
    MID = "mid"
    OPEN_MID = "open_mid"
    NEAR_OPEN = "near_open"
    OPEN = "open"


class VowelBackness(str, Enum):
    FRONT = "front"
    CENTRAL = "central"
    BACK = "back"


class Vowel(BaseModel, frozen=True):
    ipa: str
    height: VowelHeight
    backness: VowelBackness
    rounded: bool
    long: bool = False
    diphthong: bool = False
    """Whether this ``ipa`` symbol is a diphthong (e.g. ``"ɛi"``) rather
    than a monophthong -- stored as its own atomic, multi-character
    symbol (same pattern as affricates/long vowels/geminate consonants),
    so ``height``/``backness``/``rounded`` reflect its *onset* quality,
    the standard way a diphthong gets classified when a model needs one
    value per axis. Consulted only where "simple, unmarked" vowels
    matter (``generation/word_builder.py``'s kinship-reduplication
    filter) -- phonotactics and romanization matching don't care whether
    a vowel symbol happens to be one or two characters."""
    nasalized: bool = False
    """Nasalized (e.g. ``"ã"``, combining tilde) -- Portuguese/French/
    Hindi-style. Same "marked, not simple/unmarked" treatment as
    ``diphthong`` in ``generation/word_builder.py``'s kinship-
    reduplication filter."""
    prevalence: float = 0.5
    """See ``Consonant.prevalence`` -- same meaning, same illustrative-
    approximation caveat."""


class PhonemeInventory(BaseModel, frozen=True):
    consonants: tuple[Consonant, ...]
    vowels: tuple[Vowel, ...]

    def consonant_symbols(self) -> tuple[str, ...]:
        return tuple(c.ipa for c in self.consonants)

    def vowel_symbols(self) -> tuple[str, ...]:
        return tuple(v.ipa for v in self.vowels)

    def all_symbols(self) -> tuple[str, ...]:
        return self.consonant_symbols() + self.vowel_symbols()


class ToneLevel(str, Enum):
    """A tone as a diacritic-bearing suffix applied to a vowel's IPA symbol."""

    LOW = "low"
    MID = "mid"
    HIGH = "high"
    RISING = "rising"
    FALLING = "falling"


TONE_DIACRITICS: dict[ToneLevel, str] = {
    ToneLevel.LOW: "̀",  # combining grave
    ToneLevel.MID: "̄",  # combining macron
    ToneLevel.HIGH: "́",  # combining acute
    ToneLevel.RISING: "̌",  # combining caron
    ToneLevel.FALLING: "̂",  # combining circumflex
}
"""Public (not just an implementation detail of `ToneSystem.mark`) because
`generation.romanization_gen` also needs these exact mark characters to
build a postposed-tone `core.romanization.OrthographyCategory`'s
`tone_markers` table -- see that module."""


class ToneSystem(BaseModel, frozen=True):
    enabled: bool = False
    levels: tuple[ToneLevel, ...] = ()

    def mark(self, vowel_ipa: str, tone: ToneLevel) -> str:
        """Apply a tone's combining diacritic to a vowel symbol."""
        if not self.enabled:
            return vowel_ipa
        return vowel_ipa + TONE_DIACRITICS[tone]


class SyllableStructure(BaseModel, frozen=True):
    """A coarse phonotactic template: (onset) nucleus (coda).

    ``max_onset``/``max_coda`` of 0 forbid consonants in that position; 1 allows a
    single consonant; >=2 allows consonant clusters, but only the pairs listed in
    ``allowed_onset_clusters``/``allowed_coda_clusters`` (checked when
    ``max_onset``/``max_coda`` >= 2). ``allowed_coda_consonants=None`` means
    any consonant is allowed as a single coda; a coda profile that restricts
    codas to sonorants (or forbids them, via ``max_coda=0``) is expressed
    with these same fields -- see ``generation/phonology_gen.py``.
    ``excluded_coda_consonants`` layers a further, independent negative
    constraint on the coda's final segment (e.g. devoicing) on top of
    whichever of those coda profiles is otherwise in effect.
    """

    max_onset: int = 1
    max_coda: int = 1
    allowed_onset_clusters: tuple[tuple[str, str], ...] = ()
    allowed_coda_clusters: tuple[tuple[str, str], ...] = ()
    allowed_coda_consonants: tuple[str, ...] | None = None  # None = any consonant
    excluded_coda_consonants: tuple[str, ...] = ()
    """Symbols that can never be the *final* segment of a coda (single or
    cluster) -- e.g. voiced obstruents for a language with final-obstruent-
    devoicing phonotactics (real Dutch/German/Russian). Orthogonal to
    ``allowed_coda_consonants``: that's a positive whitelist (``None`` =
    unrestricted, or the sonorant-only coda profile's set); this is a
    negative constraint layered on top, checked independently -- see
    ``generation/phonology_gen.py``."""
    vowel_harmony: bool = False
    """Backness (front/back) vowel harmony -- see
    ``generation/word_builder.py``'s ``build_word``."""

    def is_valid_syllable(
        self, onset: tuple[str, ...], coda: tuple[str, ...]
    ) -> bool:
        if len(onset) > self.max_onset:
            return False
        if len(onset) == 2 and onset not in self.allowed_onset_clusters:
            return False
        if len(onset) > 2:
            return False
        if len(coda) > self.max_coda:
            return False
        if len(coda) == 2 and coda not in self.allowed_coda_clusters:
            return False
        if len(coda) > 2:
            return False
        if (
            self.allowed_coda_consonants is not None
            and len(coda) == 1
            and coda[0] not in self.allowed_coda_consonants
        ):
            return False
        if coda and coda[-1] in self.excluded_coda_consonants:
            return False
        return True
