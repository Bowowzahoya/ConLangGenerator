"""The top-level aggregate: everything needed to generate, translate, and
pronounce text in one constructed language."""

from __future__ import annotations

import re

from pydantic import BaseModel

from conlang_generator.core.grammar import GrammarProfile
from conlang_generator.core.lexicon import Idiom, LexicalEntry, Lexicon
from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure, ToneSystem
from conlang_generator.core.romanization import RomanizationScheme
from conlang_generator.core.spec import GenerationSpec


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise ValueError(f"name {name!r} has no usable characters for a slug")
    return slug


class Language(BaseModel, frozen=True):
    name: str
    spec: GenerationSpec
    phonology: PhonemeInventory
    syllable_structure: SyllableStructure
    tone_system: ToneSystem
    romanization: RomanizationScheme
    grammar: GrammarProfile
    lexicon: Lexicon = Lexicon()
    history: tuple[str, ...] = ()
    """Human-readable log of post-generation expansions (new words, idioms)."""

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def with_new_words(
        self, entries: tuple[LexicalEntry, ...], reason: str
    ) -> Language:
        return self.model_copy(
            update={
                "lexicon": self.lexicon.with_entries(entries),
                "history": self.history + (reason,),
            }
        )

    def with_new_idiom(self, idiom: Idiom, reason: str) -> Language:
        return self.model_copy(
            update={
                "lexicon": self.lexicon.with_idiom(idiom),
                "history": self.history + (reason,),
            }
        )
