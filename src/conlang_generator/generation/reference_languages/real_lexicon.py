"""Real vocabularies of the reference languages: for each curated language a
``lexicons/<name>.yaml`` mapping a ``lexicon_gen.ALL_MEANINGS`` gloss to
``[spelling, ipa]`` -- or ``[spelling, ipa, loan]`` for an obvious
loanword (see ``loan_glosses``). The IPA is transcribed (best-effort, not linguist-
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
    return {gloss: (str(entry[0]), str(entry[1])) for gloss, entry in raw.items()}


@functools.lru_cache(maxsize=None)
def loan_glosses(profile_name: str) -> frozenset[str]:
    """Glosses whose curated word is tagged ``loan`` (a third list element):
    an obvious loanword, e.g. Swahili *kabla* (Arabic) or Basque *triste*
    (Romance). Tagging is deliberately partial -- "obvious", not an etymological
    survey -- and only affects ``lexicon_audit``, which by default does not hold
    loans to the language's native phonotactics."""
    path = _LEXICONS_DIR / lexicon_filename(profile_name)
    if not path.exists():
        return frozenset()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return frozenset(gloss for gloss, entry in raw.items() if len(entry) > 2 and str(entry[2]) == "loan")


def curated_profiles() -> tuple[ReferenceLanguageProfile, ...]:
    return tuple(p for p in REFERENCE_LANGUAGES if real_words(p.name))
