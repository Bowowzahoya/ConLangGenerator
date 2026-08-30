"""The storage seam: swap ``YamlLanguageRepository`` for a future SQL-backed
implementation without touching any caller.

Kept intentionally narrow -- whole-``Language`` load/save only. Vocabulary
expansion works by loading, calling ``language.with_new_words(...)``, then
saving again; there is no per-entry API to keep this interface small.
"""

from __future__ import annotations

from typing import Protocol

from conlang_generator.core.language import Language


class LanguageRepository(Protocol):
    def save(self, language: Language) -> None: ...
    def load(self, name: str) -> Language: ...
    def list(self) -> list[str]: ...
    def exists(self, name: str) -> bool: ...
