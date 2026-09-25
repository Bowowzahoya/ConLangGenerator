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


class InflectionAffix(BaseModel, frozen=True):
    """One bound morpheme for a sentence-role-driven inflection axis
    (case, tense, subject agreement) -- deliberately distinct from
    ``WordClass``, which models a *lexeme-fixed, chosen-once-at-coinage*
    paradigm membership (a noun's own declension, a verb's own
    conjugation class). An ``InflectionAffix`` is the opposite shape: the
    *same* value gets applied fresh to whichever word actually needs it
    in a given sentence, decided by that word's own role there (the
    direct object needs the accusative case; the subject decides which
    agreement suffix the verb takes), never chosen once and baked into
    the lexicon entry the way a ``WordClass`` suffix is. The two share
    only the low-level "attach a prefix/suffix, re-derive stress" mechanism
    (``word_builder.attach_affix_and_restress``, which both ``word_class_
    gen.apply_word_class`` and ``generation.inflection_gen.apply_affix``
    call) -- carrying ``WordClass``'s own ``prevalence``/``condition``/
    ``position_classes`` here would be meaningless, since none of those
    "chosen among several options" concepts apply to a value that's
    always deterministically the right one for its own label."""

    label: str
    """Which value on its own axis this is -- a case label (e.g.
    ``"accusative"``, drawn from the same pool ``GrammarProfile.cases``
    already uses), a tense label (``"past"``, from ``GrammarProfile.
    tenses``), or an agreement label (one of the 4 core pronoun glosses
    this project's own ``lexicon_gen.CORE_MEANINGS`` already has --
    ``"I"``/``"you"``/``"he"``/``"we"`` -- plus ``"default"`` for any
    non-pronoun/noun subject, the real cross-linguistic "3rd person is
    the unmarked default" pattern)."""
    prefix: tuple[str, ...] = ()
    suffix: tuple[str, ...] = ()


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
    tenses: tuple[str, ...] = ()
    """This language's own illustrative tense-label set (e.g. ``("past",
    "non_past")`` or ``("past", "present", "future")``) -- rolled in
    ``grammar_gen.generate_grammar`` itself, a source-language-independent
    illustrative choice the same way ``is_prefixing``'s own invented-class
    coin flip is (no cross-linguistic tendency this project curates to
    lean on for which tense system a language has). Empty means this
    language marks no tense distinction at all. Parallel to ``cases``
    above; ``tense_affixes`` below is this set's own generated phonology."""
    case_affixes: tuple[InflectionAffix, ...] = ()
    """One invented suffix per label in ``cases`` -- filled in by
    ``generator.py`` once the phoneme inventory exists (the same two-
    phase relationship ``plural_suffix``/``templates`` already have),
    via ``generation.inflection_gen.generate_case_affixes``. Applied to a
    sentence's own subject/object per ``alignment`` at translation time
    (``translation/translator.py``), not baked into a ``LexicalEntry`` --
    unlike ``word_classes``, a noun's own case marking depends on its
    syntactic role in a given sentence, not a fact fixed at coinage."""
    tense_affixes: tuple[InflectionAffix, ...] = ()
    """One invented suffix per label in ``tenses`` -- same two-phase
    relationship and generation source as ``case_affixes``, applied to
    this sentence's own finite verb (or copula) at translation time."""
    agreement_affixes: tuple[InflectionAffix, ...] = ()
    """One invented suffix per subject-agreement label (this project's 4
    core pronoun glosses plus ``"default"`` -- see ``InflectionAffix.
    label``'s own docstring) -- same two-phase relationship and
    generation source as ``case_affixes``, applied to this sentence's own
    finite verb (or copula) at translation time, composed together with
    the tense affix into one combined suffix so stress is only re-derived
    once per word."""
    number_affixes: tuple[InflectionAffix, ...] = ()
    """One invented plural suffix (label ``"plural"``; singular is the
    unmarked bare form) -- same two-phase generation as ``case_affixes``
    (``inflection_gen.generate_number_affixes``), applied to a noun at
    translation time. Generated for every language, isolating ones too
    (there it acts as an attached plural clitic, like Mandarin 们); empty
    on a language saved before this field existed, which then marks no
    plural."""
    mood_affixes: tuple[InflectionAffix, ...] = ()
    """One invented imperative suffix (label ``"imperative"``), applied to
    the verb of an imperative sentence instead of tense/agreement."""
    question_particle: str = ""
    """The IPA of this language's own free yes/no question
    particle (a standalone word, not an affix). Empty means the language
    marks no yes/no questions (a language saved before this field existed). See ``translation.translator`` for where it
    is placed."""
    aspects: tuple[str, ...] = ()
    """This language's own aspect labels (empty: no aspect marking) -- a
    system separate from ``tenses``. Either two-way (``perfective``,
    ``imperfective``) or four-way (``perfective``, ``progressive``,
    ``perfect``, ``habitual``). ``aspect_affixes`` holds each label's own
    generated suffix."""
    aspect_affixes: tuple[InflectionAffix, ...] = ()
    moods: tuple[str, ...] = ()
    """This language's own *verbal* mood labels other than the imperative
    (empty: none): ``irrealis``, or ``subjunctive``/``conditional``/
    ``potential``. Their affixes live in ``mood_affixes`` beside
    ``"imperative"``."""
    noun_classes: tuple[str, ...] = ()
    """This language's own noun-class system (empty: none) -- one of
    ``generation.noun_class_gen.NOUN_CLASS_SYSTEMS``. A noun's class is
    derived from its gloss (``noun_class_gen.noun_class``), not stored, and
    shows only through agreement."""
    class_affixes: tuple[InflectionAffix, ...] = ()
    """One suffix per class, taken by an article or adjective agreeing with
    its noun."""
    object_agreement: bool = False
    """Whether the verb also agrees with its object."""
    object_agreement_affixes: tuple[InflectionAffix, ...] = ()
    """Person labels plus ``"class:<name>"`` labels; empty unless
    ``object_agreement``. (Subject agreement by class uses the same
    ``"class:<name>"`` labels inside ``agreement_affixes``.)"""
    plural_after_numeral: bool = True
    """Whether a noun after a numeral above "one" still takes the plural
    (``False``: it stays singular, as in Turkish)."""
    demonstrative_after_noun: bool = False
    has_indefinite_article: bool = False
    possession: str = "none"
    """How a possessor is marked: ``"genitive"`` (the genitive case),
    ``"particle"`` (a free word after the possessor), ``"affix"`` (a suffix on
    the possessed noun) or ``"none"`` (plain juxtaposition)."""
    possessive_particle: str = ""
    """IPA of the possessive particle (``possession == "particle"``)."""
    possession_affixes: tuple[InflectionAffix, ...] = ()
    """One ``"possessed"`` suffix (``possession == "affix"``)."""

    voices: tuple[str, ...] = ()
    """This language's own voice labels beyond the active (empty: none):
    ``passive``, ``antipassive`` (ergative-absolutive languages only) and/or
    ``causative``. A voice is a verb suffix (``voice_affixes``); the
    argument reassignment it implies (which noun is the subject, how an
    agent is marked) is planned by ``translation.sentence_planner``."""
    voice_affixes: tuple[InflectionAffix, ...] = ()

    existential: str = "copula"
    """How "there is X" is expressed: ``"copula"`` (X plus the copula, or just
    X in a language without an overt copula) or ``"verb"`` (X plus a
    dedicated verb "exist")."""
    possession_clause: str = "have"
    """How "A has B" is expressed: ``"have"`` (a transitive verb "have": A
    subject, B object) or ``"dative_be"`` (A first, in the dative -- or
    possessor-marked where there is no dative -- then the existential
    construction with B as its subject; no verb "have")."""

    comparative_strategy: str = "particle"
    """How the standard of a comparison ("bigger THAN Y") is marked:
    ``"particle"`` (a word "than" beside the standard), ``"case"`` (the
    standard takes ``comparative_case``, no extra word) or ``"exceed"`` (a
    verb "exceed" with the standard as its object)."""
    comparative_case: str = ""
    """The case of the standard when ``comparative_strategy == "case"``."""
    comparative_marking: str = "word"
    """``"affix"`` (a suffix on the adjective) or ``"word"`` (a word "more"
    before it)."""
    superlative_marking: str = "word"
    """``"affix"`` (a suffix) or ``"word"`` (a word "most")."""
    degree_affixes: tuple[InflectionAffix, ...] = ()
    """The ``"comparative"``/``"superlative"`` suffixes, present only for a
    degree whose marking is ``"affix"``."""

    uses_classifiers: bool = False
    """A classifier word (chosen by the noun's semantic category) follows a
    numeral or demonstrative before its noun; such a language keeps the noun
    singular after a numeral."""
    classifier_categories: tuple[str, ...] = ()
    """The noun categories that have a classifier of their own (a subset of
    ``generation.classifier_gen.CATEGORIES``, always with ``general``); empty
    on a classifier language saved before this field means the original six."""
    classifier_after_noun: bool = False
    """Noun-numeral-classifier order instead of numeral-classifier-noun."""
    classifier_with_demonstrative: bool = True
    """Whether a demonstrative also takes a classifier."""
    clusivity: bool = False
    """Inclusive/exclusive "we" (``we-inclusive``/``we-exclusive``)."""
    third_person_gender: bool = False
    """``she`` and ``it`` are pronouns of their own (else all map to ``he``)."""
    honorific_you: bool = False
    """A polite ``you-polite`` beside plain ``you``."""
    pro_drop: bool = False
    """A subject pronoun is omitted when the verb's agreement names the
    person."""

    reflexive_marking: str = "none"
    """``"word"`` (an object pronoun ``self``), ``"affix"`` (a ``reflexive``
    voice suffix on the verb, no object) or ``"none"`` (an ordinary pronoun of
    the subject's person)."""
    reciprocal_marking: str = "none"
    """The same for "each other" (``each-other`` / a ``reciprocal`` voice)."""
    possessive_pronouns: str = "regular"
    """``"regular"`` (the personal pronoun plus the language's possession
    marking), ``"words"`` (a possessive word per person, ``possessive-<gloss>``)
    or ``"affix"`` (a person suffix on the possessed noun)."""
    possessor_person_affixes: tuple[InflectionAffix, ...] = ()
    """One suffix per person (``I``/``you``/``he``/``we``) on a possessed noun,
    when ``possessive_pronouns == "affix"``."""
    verb_number_agreement: bool = False
    """The verb carries a ``plural`` suffix when its subject is plural."""
    verb_number_affixes: tuple[InflectionAffix, ...] = ()
    verb_politeness: bool = False
    """The verb carries a ``polite`` suffix when its subject is ``you-polite``
    (needs ``honorific_you``)."""
    verb_polite_affixes: tuple[InflectionAffix, ...] = ()
    object_pro_drop: bool = False
    """An object pronoun is omitted when the verb's object agreement names it
    (needs ``object_agreement`` with distinct person suffixes)."""

    suppletive_pronoun_persons: tuple[str, ...] = ()
    """The persons (``I``/``you``/``he``/``we``) whose non-nominative case forms
    are words of their own (I -> me, ``i-accusative``) instead of the pronoun
    plus a case suffix. Empty: every pronoun is regular."""
    reflexive_possessive: str = "none"
    """"His own": ``"word"`` (a possessive word ``possessive-self``),
    ``"affix"`` (a ``self`` entry in ``possessor_person_affixes``) or
    ``"none"`` (the ordinary possessive of the subject's person)."""
    possessive_classifiers: bool = False
    """A classifier (``possessive-classifier-<category>``) follows a possessor
    word before the possessed noun (a classifier language only)."""

    classifier_assignment: str = "category"
    """``"category"`` (a noun's classifier follows its meaning) or ``"lexical"``
    (each noun is assigned one of ``classifier_pool_size`` classifiers, by an
    arbitrary but stable rule)."""
    classifier_pool_size: int = 0
    repeater_rate: float = 0.0
    """The share of nouns that are their own classifier (a repeater)."""
    classified_quantifiers: tuple[str, ...] = ()
    """The quantifiers (of ``classifier_gen.QUANTIFIERS``) that take a
    classifier, as numerals do."""

    subordinator_position: str = ""
    """Where a subordinating word goes: ``"before"`` or ``"after"`` its clause
    (empty: the older rule -- after in a verb-final language, else before)."""
    relativization: str = "pronoun"
    """``"pronoun"``, ``"particle"``, ``"gap"``, ``"resumptive"`` or
    ``"correlative"`` -- see ``generation.subordination_gen``."""
    relative_clause_position: str = "after_noun"
    """``"after_noun"`` or ``"before_noun"``."""
    verb_forms: tuple[str, ...] = ()
    """The non-finite verb forms: ``infinitive``, ``nominalized``,
    ``participle``."""
    verb_form_affixes: tuple[InflectionAffix, ...] = ()
    """One suffix per non-finite form; it replaces tense and agreement."""
    subordinate_mood_use: bool = False
    """An "if"/"unless"/"so that"/"although" clause takes the subjunctive or
    irrealis (when the language has one)."""

    relativization_reach: str = "possessor"
    """How far down the accessibility hierarchy (subject, object, oblique,
    possessor) the plain gap/particle strategy reaches; a relative clause on a
    position beyond it uses the invariant word plus a resumptive pronoun. The
    default reaches everything (the earlier behaviour)."""
    relative_pronoun_declines: bool = False
    """The relative pronoun takes the case of its function (who/whom/whose)."""
    relative_pronoun_number: bool = False
    """The relative pronoun has a plural form."""
    infinitive_agrees: bool = False
    """An infinitive takes the agreement of its controller."""
    nominalized_takes_case: bool = False
    """A nominalized clause used as an argument takes its case."""
    conditional_main_mood: bool = False
    """The main clause of an "if" sentence takes the conditional mood."""
    conditional_clause_tense: str = ""
    """A tense (``"past"``) an "if" clause takes unless the planner set one."""
    correlative_adverbials: bool = False
    """"If"/"when"/"the more" clauses come first and the main clause opens with
    a correlate ("then")."""
    clause_coordination: str = "word"
    """``"word"`` (a conjunction between clauses), ``"converb"`` (the first
    verb is a medial form, no conjunction) or ``"juxtapose"``."""
    conjunct_reduction: bool = False
    """A second conjunct drops a subject pronoun it shares with the first."""
    complementizer_by_verb: bool = False
    """The complementizer depends on the class of the governing verb
    (speech, desire, perception, factive)."""

    class_agreement_targets: tuple[str, ...] = ("article", "adjective", "demonstrative", "possessive")
    """The word categories that agree with their noun in class (of
    ``noun_class_gen.AGREEMENT_CATEGORIES``); the default is what agreed before
    targets were rolled."""
    number_agreement_targets: tuple[str, ...] = ()
    """The categories that agree with their noun in number (plural/dual)."""
    case_agreement_targets: tuple[str, ...] = ()
    """The categories that agree with their noun in case."""
    class_marking: str = "none"
    """``"suffix"`` or ``"prefix"``: the noun itself carries its class
    (``class_marker_affixes``); ``"none"``: the class shows only through
    agreement."""
    class_marker_affixes: tuple[InflectionAffix, ...] = ()
    """One marker per class, for the noun itself (separate from
    ``class_affixes``, which the agreeing words take)."""
    noun_class_assignment: str = "hash"
    """How a noun with no natural gender/animacy gets its class: ``"hash"``,
    ``"semantic"`` (by semantic field) or ``"formal"`` (by final sound)."""

    evidentials: tuple[str, ...] = ()
    """This language's evidential labels (``witnessed``, ``inferred``,
    ``reported``), marking the source of the speaker's information on the
    verb; empty: no evidentiality. Marked only when the sentence plan asks."""
    evidential_affixes: tuple[InflectionAffix, ...] = ()
    negation_strategy: str = "particle"
    """How a verb is negated: ``"particle"`` (a separate word), ``"affix"``
    (a negative suffix on the verb) or ``"both"`` (particle *and* suffix, as
    in negative concord)."""
    verb_negative_affixes: tuple[InflectionAffix, ...] = ()
    """The single ``negative`` verb suffix (empty with ``"particle"``)."""
    periphrastic_labels: tuple[str, ...] = ()
    """Tense, aspect and verbal mood labels this language expresses with an
    auxiliary word (``aux-<label>`` in the lexicon) instead of a verb suffix."""
    auxiliary_position: str = "before"
    """``"before"`` or ``"after"`` the main verb."""

    passive_agreement: str = "patient"
    """``"patient"`` (the passive verb agrees with its subject, the patient) or
    ``"none"`` (it takes the default agreement)."""
    passive_agent: str = "word"
    """The passive agent is marked with a ``"word"`` ("by") or, when the language
    has an instrumental case, ``"case"``."""
    adposition_case_strategy: str = "none"
    """``"none"``; ``"governs"`` (an adposition stays and its noun takes the case
    it corresponds to); ``"case_only"`` (a locative/instrumental case replaces
    its adposition altogether, the rest govern)."""
    suppletive_plurals: tuple[str, ...] = ()
    """Nouns whose plural is a separate word (``child-plural``)."""
    suppletive_degrees: tuple[str, ...] = ()
    """Adjectives whose comparative/superlative are separate words."""
    inalienable_possession: bool = False
    """Body parts and kin are possessed without the possessive marking."""

    suppletive_pronoun_case_limits: tuple[tuple[str, tuple[str, ...]], ...] = ()
    """Per person in ``suppletive_pronoun_persons``, the only cases that have a
    word of their own (I/me); the person's other cases take the ordinary case
    suffix. A person with no entry is suppletive in every non-nominative case."""
    adjective_placement: str = "global"
    """``"global"`` (``adjective_after_noun`` for all) or ``"split"`` (the
    classes in ``adjective_before_classes`` precede the noun, the rest follow)."""
    adjective_before_classes: tuple[str, ...] = ()
    adjective_stack_order: tuple[str, ...] = ()
    """The order stacked adjectives take by class (quality, size, age, colour,
    other; mirrored after the noun); empty leaves the planner's order."""
    adjective_stack_linker: bool = False
    """Stacked adjectives are joined by "and"."""
    article_source: str = "own"
    """``"demonstrative"``: the definite article is a reduced "that"."""
    has_specific_article: bool = False
    """A third article for a specific indefinite ("a certain dog")."""

    classifier_with_adjective: bool = False
    """A classifier language also puts a classifier beside a noun's attributive
    adjective (before the noun, or between the noun and a following adjective)."""
    drop_measure_of: bool = False
    """"a cup of water" is written without "of": the measure noun and the mass noun
    are juxtaposed."""
    possessive_word_persons: tuple[str, ...] = ()
    """With ``possessive_pronouns == "words"``, the persons that have a possessive
    word of their own (empty: all); the rest use the personal pronoun as possessor."""
    suppletive_past: tuple[str, ...] = ()
    """Verbs whose past tense is a word of its own (``go-past`` = went)."""
    deictic_articles: bool = False
    """An attributive demonstrative is a reduced clitic form (``this-article``)."""
    demonstrative_doubling: bool = False
    """A demonstrative also takes the definite article ("the this dog")."""

    @property
    def postpositional(self) -> bool:
        """Object-before-verb orders (SOV, OSV, OVS) put adpositions after their
        noun; the rest put them before (the usual Greenberg correlation)."""
        return self.word_order.value in ("SOV", "OSV", "OVS")
