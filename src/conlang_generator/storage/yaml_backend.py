"""Default ``LanguageRepository``: one directory per language, split into a
few human-readable/diffable YAML files.

Chosen as the starting backend per the project owner's preference to hand-
inspect everything early on; a ``sql_backend.py`` can implement the same
``LanguageRepository`` protocol later without callers changing.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from conlang_generator.core.language import Language, slugify

_FILE_FIELDS: dict[str, tuple[str, ...]] = {
    "meta": ("name", "spec", "history"),
    "phonology": ("phonology", "syllable_structure", "tone_system"),
    "romanization": ("romanization",),
    "grammar": ("grammar",),
    "lexicon": ("lexicon",),
}


class YamlLanguageRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _dir(self, slug: str) -> Path:
        return self._root / slug

    def save(self, language: Language) -> None:
        data = language.model_dump(mode="json")
        directory = self._dir(language.slug)
        directory.mkdir(parents=True, exist_ok=True)
        for filename, fields in _FILE_FIELDS.items():
            chunk = {field: data[field] for field in fields}
            path = directory / f"{filename}.yaml"
            path.write_text(
                yaml.safe_dump(chunk, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )

    def load(self, name: str) -> Language:
        slug = slugify(name)
        directory = self._dir(slug)
        if not directory.exists():
            raise FileNotFoundError(
                f"no language stored for {name!r} (looked in {directory})"
            )
        merged: dict = {}
        for filename in _FILE_FIELDS:
            path = directory / f"{filename}.yaml"
            merged.update(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
        return Language.model_validate(merged)

    def list(self) -> list[str]:
        if not self._root.exists():
            return []
        return sorted(p.name for p in self._root.iterdir() if p.is_dir())

    def exists(self, name: str) -> bool:
        return self._dir(slugify(name)).exists()
