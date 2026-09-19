"""Real vocabularies of the reference languages: for each curated language a
``lexicons/<name>.yaml`` mapping a ``lexicon_gen.ALL_MEANINGS`` gloss to
``[spelling, ipa]``. The IPA is transcribed (best-effort, not linguist-
verified) to this project's modeled phoneme set -- no true /ts/-style gaps,
diphthongs only as modeled symbols -- so every word tokenizes fully against
``phonology_gen``'s global symbol pool (enforced by ``tests/test_real_
lexicons.py``).

Used by ``generation/real_words.py`` to build a generated language's words
from a source language's actual vocabulary (the separate word strictness),
and by ``experiments/lexicons.py``.
"""

from __future__ import annotations

import functools
from pathlib import Path

import yaml

from conlang_generator.generation.reference_languages import REFERENCE_LANGUAGES, ReferenceLanguageProfile

_LEXICONS_DIR = Path(__file__).parent / "lexicons"


def lexicon_filename(profile_name: str) -> str:
    return profile_name.lower().replace(" ", "_").replace("-", "_") + ".yaml"


@functools.lru_cache(maxsize=None)
def real_words(profile_name: str) -> dict[str, tuple[str, str]]:
    """``{gloss: (spelling, ipa)}`` for a curated language, or ``{}`` when
    this project has no curated vocabulary for it."""
    path = _LEXICONS_DIR / lexicon_filename(profile_name)
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {gloss: (str(pair[0]), str(pair[1])) for gloss, pair in raw.items()}


def curated_profiles() -> tuple[ReferenceLanguageProfile, ...]:
    return tuple(p for p in REFERENCE_LANGUAGES if real_words(p.name))
