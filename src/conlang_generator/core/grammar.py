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


class GrammarProfile(BaseModel, frozen=True):
    word_order: WordOrder
    morphological_type: MorphologicalType
    alignment: Alignment
    has_articles: bool
    adjective_after_noun: bool
    has_overt_copula: bool
    cases: tuple[str, ...] = ()
    plural_suffix: str | None = None
