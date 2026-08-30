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


class Consonant(BaseModel, frozen=True):
    ipa: str
    place: Place
    manner: Manner
    voiced: bool
    ejective: bool = False


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


_TONE_DIACRITICS: dict[ToneLevel, str] = {
    ToneLevel.LOW: "̀",  # combining grave
    ToneLevel.MID: "̄",  # combining macron
    ToneLevel.HIGH: "́",  # combining acute
    ToneLevel.RISING: "̌",  # combining caron
    ToneLevel.FALLING: "̂",  # combining circumflex
}


class ToneSystem(BaseModel, frozen=True):
    enabled: bool = False
    levels: tuple[ToneLevel, ...] = ()

    def mark(self, vowel_ipa: str, tone: ToneLevel) -> str:
        """Apply a tone's combining diacritic to a vowel symbol."""
        if not self.enabled:
            return vowel_ipa
        return vowel_ipa + _TONE_DIACRITICS[tone]


class SyllableStructure(BaseModel, frozen=True):
    """A coarse phonotactic template: (onset) nucleus (coda).

    ``max_onset``/``max_coda`` of 0 forbid consonants in that position; 1 allows a
    single consonant; >=2 allows consonant clusters, but only the pairs listed in
    ``allowed_onset_clusters`` (checked when ``max_onset`` >= 2).
    """

    max_onset: int = 1
    max_coda: int = 1
    allowed_onset_clusters: tuple[tuple[str, str], ...] = ()
    allowed_coda_consonants: tuple[str, ...] | None = None  # None = any consonant

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
        if (
            self.allowed_coda_consonants is not None
            and len(coda) == 1
            and coda[0] not in self.allowed_coda_consonants
        ):
            return False
        return True
