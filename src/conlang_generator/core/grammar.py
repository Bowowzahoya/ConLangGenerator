"""Typological grammar parameters.

This is a small set of value objects describing where a language sits on a few
well-known typological axes -- not a rule engine or a parser. The translation
pipeline (``translation/translator.py``) only implements the handful of
sentence patterns needed to demonstrate these parameters end to end; see its
module docstring for the explicit limitations.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from conlang_generator.core.lexicon import PartOfSpeech


class WordOrder(str, Enum):
    SOV = "SOV"
    SVO = "SVO"
    VSO = "VSO"
    VOS = "VOS"
    OVS = "OVS"
    OSV = "OSV"


class MorphologicalType(str, Enum):
    ISOLATING = "isolating"
    AGGLUTINATIVE = "agglutinative"
    FUSIONAL = "fusional"
    POLYSYNTHETIC = "polysynthetic"


class Alignment(str, Enum):
    NOMINATIVE_ACCUSATIVE = "nominative_accusative"
    ERGATIVE_ABSOLUTIVE = "ergative_absolutive"


class WordTemplate(BaseModel, frozen=True):
    """One root-and-pattern (templatic) word shape -- see
    ``generation/root_pattern.py``. ``skeleton`` is a sequence where
    ``"C"`` consumes the next unused root consonant, in order, and
    anything else is a literal ipa symbol (this template's own fixed
    vowel or affix, e.g. Arabic's place-noun ``m-`` prefix) -- chosen once
    per language, from that language's actual phoneme inventory, and
    reused for every word built from it, the same way a real template's
    vowel pattern doesn't vary by root (every Arabic Form-I perfective
    verb uses the same a-a pattern: kataba, darasa, ...)."""

    name: str
    pos: PartOfSpeech
    skeleton: tuple[str, ...]


class GrammarProfile(BaseModel, frozen=True):
    word_order: WordOrder
    morphological_type: MorphologicalType
    alignment: Alignment
    has_articles: bool
    adjective_after_noun: bool
    has_overt_copula: bool
    cases: tuple[str, ...] = ()
    plural_suffix: str | None = None
    uses_root_and_pattern: bool = False
    """Whether this language derives nouns/verbs/adjectives via Semitic-
    style root-and-pattern morphology -- orthogonal to
    ``morphological_type`` (which measures synthesis: morphemes per word,
    how cleanly they segment), not a value on that same axis. Arabic is
    fusional *and* root-and-pattern at once; treating the two as
    competing values would be a real typological contradiction."""
    templates: tuple[WordTemplate, ...] = ()
    """Populated only when ``uses_root_and_pattern`` -- see
    ``generation/root_pattern.py``'s ``generate_templates()``. Left empty
    by ``grammar_gen.py`` and filled in afterward once the phoneme
    inventory exists, the same relationship ``plural_suffix`` already has
    to it."""
