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
    "phonology": ("phonology", "syllable_structure", "tone_system", "word_accent"),
    "romanization": ("romanization",),
    "script": ("script",),
    "grammar": ("grammar",),
    "lexicon": ("lexicon",),
}
"""Every ``Language`` field must appear in exactly one of these groups --
a field left out isn't an error (``save`` just never writes it, ``load``
silently falls back to its own pydantic default via ``model_validate``),
so a missing entry here is invisible until someone notices a round-
tripped language quietly lost that field's own real value. Caught once
already: ``word_accent`` was missing from day one (added after this
dict was last touched) and ``script`` would have shipped the same way
without this comment -- a stored language's own word-accent system was
silently discarded and replaced with the default `WordAccentSystem()`
on every single load, for every language saved since that feature
existed, with nothing erroring to surface it."""


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
            if not path.is_file():
                # A file group added after this language was first saved
                # (e.g. "script.yaml", added once languages could have an
                # invented script) -- missing here, not corrupt; every
                # field it would have carried just falls back to its own
                # pydantic default via model_validate below, the same
                # backward-compatible "an old save predates this field"
                # handling a field *within* an existing file already
                # gets. A real "language" directory with a *required*
                # group's own file missing (meta/phonology/romanization/
                # grammar/lexicon) still fails loudly, just later, when
                # model_validate hits the field it needed.
                continue
            merged.update(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
        return Language.model_validate(merged)

    def list(self) -> list[str]:
        if not self._root.exists():
            return []
        return sorted(p.name for p in self._root.iterdir() if p.is_dir())

    def exists(self, name: str) -> bool:
        return self._dir(slugify(name)).exists()

    def has_script(self, slug: str) -> bool:
        """Whether this language has an invented script, without loading
        (and fully validating) the whole language -- just the one small
        ``script.yaml`` file, for the web UI's own language pickers to
        cheaply list every saved language's own script status at once.
        ``False`` for a pre-script-feature save with no ``script.yaml``
        at all, the same backward-compatible reading ``load`` gives it."""
        path = self._dir(slug) / "script.yaml"
        if not path.is_file():
            return False
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data.get("script") is not None
