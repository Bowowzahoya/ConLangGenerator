"""The word store: lexical entries plus idioms, indexed for lookup both ways."""

from __future__ import annotations

import unicodedata
from enum import Enum

from pydantic import BaseModel

from conlang_generator.core.phonology import ToneLevel


class PartOfSpeech(str, Enum):
    NOUN = "noun"
    VERB = "verb"
    ADJECTIVE = "adjective"
    PRONOUN = "pronoun"
    PARTICLE = "particle"
    NUMERAL = "numeral"
    OTHER = "other"


class LexicalEntry(BaseModel, frozen=True):
    ipa: str
    romanization: str
    glosses: tuple[str, ...]
    """English meanings; ``glosses[0]`` is the primary/lookup gloss."""
    pos: PartOfSpeech
    tones: tuple[ToneLevel, ...] = ()
    """Tone per syllable, if the language's ``ToneSystem`` is enabled.
    Word accent (the other suprasegmental feature, real Danish stød /
    Swedish-Norwegian pitch accent) deliberately has no equivalent
    structured field here -- like stress, it's decided too late (after
    the accented syllable's own shape is known) to hand to
    ``LexicalEntry`` as a pre-computed value the way per-syllable tone
    is; the embedded IPA mark (``core.romanization.WORD_ACCENT_MARK`` or
    a reused ``TONE_DIACRITICS`` character) is its single source of
    truth, the same "no second, structured copy" convention
    ``generation.stress_gen``'s own module docstring establishes for
    ``STRESS_MARK``."""
    notes: str = ""
    root: tuple[str, ...] | None = None
    """The consonantal root this word was derived from, for root-and-
    pattern languages (``generation/root_pattern.py``) -- ``None`` for
    every other word. Recorded even though nothing reads it back yet, so
    a later derivational-relatedness feature (reusing an existing root for
    a semantically related new word) has the data already in place."""

    @property
    def primary_gloss(self) -> str:
        return self.glosses[0]


class Idiom(BaseModel, frozen=True):
    """A fixed multi-word expression that doesn't translate word-for-word."""

    conlang_text: str
    english_text: str
    literal_gloss: str = ""


class Lexicon(BaseModel, frozen=True):
    entries: tuple[LexicalEntry, ...] = ()
    idioms: tuple[Idiom, ...] = ()

    def by_gloss(self, gloss: str) -> LexicalEntry | None:
        gloss = gloss.lower()
        for entry in self.entries:
            if gloss in (g.lower() for g in entry.glosses):
                return entry
        return None

    def by_form(self, romanization: str) -> LexicalEntry | None:
        # NFC-normalize both sides: a human typing/pasting a romanized word
        # almost always produces precomposed accents (e.g. a single 'é'),
        # while stored forms are also NFC (see RomanizationScheme.apply) --
        # normalizing defensively here means a mismatch can't silently break
        # lookup if that invariant is ever violated.
        romanization = unicodedata.normalize("NFC", romanization).lower()
        for entry in self.entries:
            if unicodedata.normalize("NFC", entry.romanization).lower() == romanization:
                return entry
        return None

    def known_forms_by_length(self) -> tuple[str, ...]:
        """Romanized forms, longest first -- for greedy tokenization."""
        return tuple(
            sorted({e.romanization for e in self.entries}, key=len, reverse=True)
        )

    def with_entries(self, new_entries: tuple[LexicalEntry, ...]) -> Lexicon:
        return self.model_copy(update={"entries": self.entries + new_entries})

    def with_idiom(self, idiom: Idiom) -> Lexicon:
        return self.model_copy(update={"idioms": self.idioms + (idiom,)})
