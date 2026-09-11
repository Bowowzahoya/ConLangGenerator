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


class WordClass(BaseModel, frozen=True):
    """One citation-form word-shape class within a single part of
    speech -- real Latin noun declensions (1st ``-a``, 2nd masc ``-us``,
    2nd neut ``-um``), real French verb conjugations (``-er``/``-ir``/
    ``-re``), real Bantu noun-class prefixes (``m-``/``wa-``, ``ki-``/
    ``vi-``). ``prefix``/``suffix`` are literal IPA symbols -- genuine
    phonological content, not a spelling-only convention (that's
    ``core.romanization.MuteSuffixRule``'s own separate job, for a real
    silent letter with no phonological correlate at all, e.g. French's
    own infinitive silent "-r"). A class with both empty is legal
    (a POS that's marked, if at all, only by which class a word belongs
    to, not by any actual affix) but unusual -- most curated/invented
    classes have at least one of the two set. Typed value object only,
    no rule engine -- the same spirit ``WordTemplate`` already has."""

    name: str
    pos: PartOfSpeech
    prefix: tuple[str, ...] = ()
    suffix: tuple[str, ...] = ()
    prevalence: float = 1.0
    """Relative frequency among this POS's own classes -- same role
    ``phonology_gen.py``'s own ``Consonant``/``Vowel.prevalence`` already
    plays, consulted by a weighted choice, not a probability in its own
    right."""


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
    word_classes: tuple[WordClass, ...] = ()
    """This language's own real or invented citation-form paradigms,
    grouped implicitly by each member's own ``pos`` (a POS with zero
    members here simply never gets any class marking -- most real
    languages' pronouns/particles/numerals, and every isolating
    language's every POS). Populated by
    ``generation/word_class_gen.py``, consulted at word-coinage time in
    ``lexicon_gen.propose_word``/``root_pattern.propose_templatic_word``/
    ``sound_change``'s own coining functions -- unlike ``cases``/
    ``plural_suffix`` above, this field has a real, live consumer."""
    word_class_deviation_rate: float | None = None
    """Chance a word that would otherwise get a class assignment is
    instead treated as unclassed (no prefix/suffix at all) -- real
    morphological irregularity/suppletion, the same per-language
    "usually X, sometimes not" shape ``stress_deviation_rate`` already
    has elsewhere. ``None`` (the common case -- most POS in most
    languages have at most one class, where "deviation" is meaningless)
    means not applicable; only set when some POS actually has more than
    one class."""
