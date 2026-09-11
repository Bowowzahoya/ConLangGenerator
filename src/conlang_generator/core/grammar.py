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
    condition: str = ""
    """When non-empty, this class's own ``suffix`` isn't a fixed literal
    the way an ordinary class's is -- it names a real, stem-internal
    phonological rule that picks between ``suffix`` and ``suffix_alt`` at
    coinage time, once the stem it's attaching to actually exists (see
    ``generation.word_class_gen.apply_word_class``). This is a genuinely
    different mechanism from choosing *among several WordClass entries*
    (an unconditioned weighted roll, appropriate for real lexical/
    arbitrary variation like Basque's own irregular verb endings): a
    conditioned suffix is real allomorphy of *one* grammatical class,
    where a flat random pick between two literal forms would be actively
    wrong roughly half the time (e.g. Turkish's own real vowel-harmony-
    conditioned ``-mak``/``-mek`` infinitive -- picking between them
    without looking at the stem would routinely produce a front-vowel
    stem with the back-vowel suffix or vice versa, directly contradicting
    this language's own already-curated ``vowel_harmony: true``).

    ``"vowel_harmony"``: ``suffix`` is this class's own *front*-harmony
    form, ``suffix_alt`` its *back*-harmony form (real Turkish/Finnish/
    Mongolian-style backness harmony -- see
    ``core.phonology.VowelBackness``). Resolved from the stem's own last
    non-``CENTRAL`` vowel, scanning from the end (the vowel nearest the
    suffix boundary, the one real harmony actually conditions on); a stem
    with no non-``CENTRAL`` vowel at all falls back to the back-harmony
    form (this project's own global vowel pool classifies a fully-open
    "a" as ``CENTRAL`` rather than a harmony-participating ``BACK``, even
    though real Turkic/Mongolic "a" behaves as a back vowel for harmony
    purposes -- since "a" is also that pool's single most common vowel,
    defaulting the "no clear signal" case to back gets the single most
    frequent real case right rather than by accident).

    ``"final_voicing"``: ``suffix`` is this class's own form used after a
    voiceless stem-final consonant, ``suffix_alt`` after a voiced one
    (real Persian-style ``-tan``/``-dan`` infinitive, conditioned by
    simple final-consonant voicing agreement rather than vowel harmony).
    A stem with no final consonant at all (vowel-final) falls back to
    ``suffix``.

    Only ``suffix``/``suffix_alt`` are ever conditioned -- ``prefix`` has
    no conditioned counterpart, since none of this project's own curated
    conditioned classes need one; a future prefixing case would need its
    own ``prefix_alt`` added alongside this, not a reuse of these same
    fields."""
    suffix_alt: tuple[str, ...] = ()
    """The stem-conditioned alternate to ``suffix`` -- see ``condition``'s
    own docstring for which real phonological value each field
    represents per condition type. Must stay empty when ``condition`` is
    ``""`` (an ordinary, unconditioned class has only one real suffix
    form, ``suffix`` itself)."""
    position_classes: tuple[PositionClass, ...] = ()
    """An ordered sequence of independently-rolled position-class slots
    -- real Navajo-style polysynthetic verb-prefix morphology, where
    several distinct grammatical categories (subject agreement,
    classifier, ...) each contribute their own morpheme to a single word
    *simultaneously*, unlike an ordinary ``WordClass`` (one alternative
    paradigm chosen *among* several by ``assign_word_class``'s own
    unconditioned roll). Every slot here always resolves to something
    (possibly a real null/zero option) for every word of this class --
    concatenated in order, before ``prefix`` and the stem, by
    ``generation.word_class_gen.apply_word_class``'s own
    ``_resolve_position_classes`` helper. Orthogonal to
    ``condition``/``suffix_alt`` (that axis conditions the *suffix* on
    the stem's own phonology; this one builds a composite *prefix* from
    several independent rolls) -- a class can use either, both, or
    neither. Like ``condition``, this only ever reaches a generated
    language via reference-profile adoption (a matched profile's own
    curated ``WordClass`` carried through verbatim) -- the invented-class
    path never sets it, so an unrelated/fictional language can't roll
    one on its own."""


class PositionClassOption(BaseModel, frozen=True):
    """One real morpheme choice within a single position-class slot --
    e.g. real Navajo's own classifier slot has a small real paradigm,
    each member its own option here. ``symbols=()`` is a real,
    legitimate option (a genuine null/zero morpheme -- Navajo's own zero
    classifier is the single most common real choice, not a
    placeholder)."""

    name: str
    symbols: tuple[str, ...] = ()
    prevalence: float = 1.0


class PositionClass(BaseModel, frozen=True):
    """One position-class slot in a polysynthetic word's own prefix
    structure -- a real, named grammatical category (e.g. "classifier")
    with its own small paradigm of real ``PositionClassOption``s,
    resolved by an independent weighted roll every time a ``WordClass``
    carrying it gets applied. Real Athabaskanist terminology (Young &
    Morgan; Rice; Hardy) for exactly this concept -- Navajo's own
    verb-prefix positions are conventionally described this way in the
    literature."""

    name: str
    options: tuple[PositionClassOption, ...]


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
