"""Deterministic IPA -> Latin transliteration, kept separate from IPA storage.

A ``RomanizationScheme`` never touches the stored IPA; it only renders a
display form. Rules are tried longest-``ipa``-pattern-first so multi-symbol
sequences (e.g. affricates, toned vowels) are matched before their
single-symbol parts.

A rule can optionally be conditioned two different ways, which are *not*
interchangeable:

- ``following``/``preceding`` -- a tuple of *tags* that must intersect the
  immediate neighbor's own computed tag set. A tag is either a literal ipa
  symbol (matches an exact neighboring phoneme, e.g. Mandarin pinyin writes
  /y/ as "u" instead of "ü" specifically after j/q/x/y:
  ``preceding=("j", "q", "x", "y")``) or one of the classes
  ``"vowel"``/``"consonant"``/``"boundary"`` (nothing there) or
  ``"front_vowel"``/``"back_vowel"`` (French/Italian/Spanish spell a
  consonant differently before a front vs. back vowel, e.g. "g" before
  "e"/"i" vs. "ge" before "a"/"o"/"u" to keep it soft). These describe the
  *neighbor*.
- ``syllable`` -- a tuple containing ``"syllable_open"`` and/or
  ``"syllable_closed"``, describing this symbol's *own* structural
  position, not a neighbor's (Dutch marks vowel length by doubling only in
  a closed syllable: "vuur" /vy:r/ vs. "vuren" /'vy:.rən/ -- the vowel's
  own openness, computed by looking at what follows *it*, under the
  maximal-onset principle: open if nothing follows, or if the following
  consonant(s) belong to the *next* syllable's onset rather than this
  one's coda). A vowel can't be conditioned on its own frontness the way
  it can on syllable position -- its identity (which ipa symbol it is)
  already fixes that, so unlike ``syllable`` there's no self-referential
  form of ``front_vowel``/``back_vowel`` to speak of.

All of this comes from plain symbol-set data supplied by whoever builds
the scheme -- ``core/`` itself has no phonological knowledge. When several
of a symbol's rules match a position, the more specific one wins (an
exact-symbol match beats a class match; matching on more conditions beats
matching on fewer). When multiple rules tie at the winning specificity --
genuine spelling alternatives for the same sound in the same context,
e.g. real French ``/o/`` being "o"/"au"/"eau" with no phonological rule
to predict which -- ``RomanizationRule.weight`` breaks the tie via a
reproducible weighted pick (see ``apply()``'s own docstring for why this
doesn't need an external RNG).

``OrthographyCategory`` (bottom of this module) names a *typology* --
digraph vs. diacritic vs. monoletter exotic-symbol spelling, a vowel-
length-marking convention, short-vowel-triggered consonant doubling, and
a tone-marking strategy -- that ``generation.romanization_gen`` uses to
build a coherent, nameable ``RomanizationScheme`` (logged onto it via
``category_name``/``tone_strategy``/``tone_markers`` for provenance) and
that a ``ReferenceLanguageProfile`` can optionally point at. Tone-mark
placement is the one category axis ``apply()`` itself has real branching
for -- see its own docstring.
"""

from __future__ import annotations

import hashlib
import random
import re
import unicodedata
from enum import Enum

from pydantic import BaseModel

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.phonology import WordAccentCategory

_CLASS_TAGS = frozenset(
    {
        "vowel", "consonant", "boundary", "front_vowel", "back_vowel",
        "long_vowel", "short_vowel", "syllable_open", "syllable_closed",
    }
)

_TRIPLE_LETTER_RUN = re.compile(r"(.)\1{2,}")
"""Matches 3+ consecutive identical characters -- used by ``RomanizationScheme.apply()``
to collapse an accidental triple letter (e.g. two adjacent consonant
tokens each independently doubling/staying plain landing next to each
other) down to a real double. No orthography this project models ever
intentionally writes a letter three times in a row, so this is an
unconditional final cleanup, not a strictness-gated one."""

_DIAERESIS_MAP: dict[str, str] = {"a": "ä", "e": "ë", "i": "ï", "o": "ö", "u": "ü"}
"""``SyllableBoundaryMarker.DIAERESIS``'s letter substitution table --
real French tréma (Noël, naïve)."""

_STRESS_ACCENT_MAP: dict[str, str] = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú"}
"""``stress_accent_marking``'s letter substitution table -- real
Spanish's acute accent (á/é/í/ó/ú), rewriting the stressed vowel's own
first letter in place, the same shape ``_DIAERESIS_MAP`` already uses for
French tréma."""

STRESS_MARK = "ˈ"
"""IPA primary stress: MODIFIER LETTER VERTICAL LINE (U+02C8), inserted
directly before a stressed syllable's onset -- ``generation.word_builder``/
``generation.root_pattern``'s own stress-assignment machinery
(``generation.stress_gen``) embeds this in a word's raw IPA string, so
``core`` -- which knows nothing about ``generation`` -- is the shared home
for the literal character both sides need to agree on, the same role
``core.phonology.TONE_DIACRITICS`` already plays for tone. Not a Unicode
*combining* mark (``unicodedata.combining()`` is 0 for it) and it precedes
the syllable it marks rather than decorating one vowel from behind, so
``_tokenize`` gives it its own explicit handling below rather than
reusing the trailing-combining-mark slurp tone diacritics ride on."""


def predict_default_stress(
    num_syllables: int, pattern: str, final_coda: tuple[str, ...] = (), final_nucleus: str = ""
) -> int:
    """The syllable index (0-based) ``pattern`` alone would predict, with
    no per-word randomness. Lives here (not in ``generation.stress_gen``,
    which imports it back) because ``apply()``'s own
    ``"irregular_only"`` stress-accent rendering needs it directly, and
    ``core`` can't depend on ``generation`` -- same reasoning as
    ``STRESS_MARK`` itself living here. ``final_coda`` -- the word's own
    last syllable's coda consonants, empty if it ends in a vowel -- is
    only consulted by ``"penultimate_or_final_by_coda"`` (real Spanish:
    the default is penultimate if the word ends in a vowel or in
    ``n``/``s``, final otherwise). ``final_nucleus`` -- that same last
    syllable's own vowel -- is only consulted by
    ``"final_unless_unstressed_vowel"`` (real Portuguese: penultimate
    only if the word ends in unstressed a/e/o, final otherwise --
    genuinely the *opposite* shape from Spanish's own rule, which is why
    it needs the vowel's own identity rather than just the coda: both
    "ends in a/e/o" and "ends in i/u" alike have an empty ``final_coda``,
    so the coda alone can't distinguish real Portuguese's two cases).
    Every pattern not named above ignores both. Unrecognized or empty
    ``pattern`` falls back to plain penultimate -- one of the
    cross-linguistically most common unmarked defaults, the same role
    ``"penultimate"`` itself plays when explicitly curated."""
    if num_syllables <= 1:
        return 0
    if pattern == "final":
        return num_syllables - 1
    if pattern == "initial":
        return 0
    if pattern == "penultimate_or_final_by_coda":
        if not final_coda or final_coda[-1] in ("n", "s"):
            return num_syllables - 2
        return num_syllables - 1
    if pattern == "final_unless_unstressed_vowel":
        if final_nucleus in ("a", "e", "o"):
            return num_syllables - 2
        return num_syllables - 1
    return num_syllables - 2  # "penultimate", "lexical", and the generic fallback


WORD_ACCENT_MARK = "ˀ"
"""IPA MODIFIER LETTER GLOTTAL STOP (U+02C0) -- the real convention for
Danish stød, appended after the affected rime (nucleus + coda), not just
the vowel (stød is a property of the whole rime). Only used when
``WordAccentSystem.realization == "glottalization"`` and the word carries
``WordAccentCategory.ACCENT_1``; the ``"pitch"`` realization (Swedish/
Norwegian) instead reuses ``core.phonology.TONE_DIACRITICS``' combining
characters directly (see ``generation.word_accent_gen.mark_word_accent``),
since a genuine two-way pitch contrast needs a mark on both categories,
unlike stød's presence/absence shape. Not a Unicode *combining* mark
(same non-combining, own-token status as ``STRESS_MARK`` above, for the
same reasons) -- ``core`` is the shared home both ``ipa_tokenizer.py`` and
``word_builder.py`` need to agree on, the same role ``STRESS_MARK`` plays."""

_PITCH_WORD_ACCENT_CHARS = frozenset({"́", "̀", "̂", "̏"})
"""The literal combining characters either pitch-based word-accent
realization can produce -- combining acute and combining grave (used by
both ``"pitch"`` and, reused, ``"pitch_and_length"``; the same values
``core.phonology.TONE_DIACRITICS[ToneLevel.HIGH]``/``[ToneLevel.LOW]``
hold), plus combining circumflex (U+0302) and combining double grave
(U+030F), the two additional marks ``"pitch_and_length"``'s real 4-way
Serbo-Croatian tone x length contrast needs (see
``generation.word_accent_gen._TONE_LENGTH_DIACRITICS``). Duplicated as
bare literals here rather than importing ``TONE_DIACRITICS``/
``ToneLevel`` -- ``ToneMarkingStrategy``'s own docstring below documents
that this module deliberately never imports ``ToneLevel``, staying
decoupled from tone semantics; this is a coincidence of which characters
look right, not a real dependency on tone. ``RomanizationScheme.apply()``
uses this set to strip a word-accent mark out of a vowel's ``deco``
before it's mistaken for real tone decoration -- safe only because a
word-accented language is never also a tone language (see
``generation.phonology_gen``'s mutual-exclusivity guard)."""


def predict_default_word_accent(
    num_syllables: int,
    accented_nucleus: str,
    accented_coda: tuple[str, ...],
    pattern: str,
    accented_syllable_index: int = 0,
) -> WordAccentCategory:
    """The word-accent category ``pattern`` alone would predict for the
    word's accented syllable (its stressed syllable, or syllable 0 for a
    monosyllable -- stød is canonically a monosyllable phenomenon, unlike
    stress marking, which skips monosyllables entirely; see
    ``generation.word_builder.build_word``). Lives here, not in
    ``generation.word_accent_gen`` (which imports it back), for the same
    reason ``predict_default_stress`` does: a future
    ``word_accent_marking == "irregular_only"``-style rendering in
    ``apply()`` would need it directly, and ``core`` can't depend on
    ``generation``.

    ``accented_syllable_index`` (0-based, within the word) is only
    consulted by ``"initial_falling_elsewhere_rising"`` below -- every
    other pattern ignores it, same "only the pattern that needs an axis
    reads it" convention ``final_coda`` already has in
    ``predict_default_stress``.

    Unlike ``predict_default_stress``, there's no generic cross-linguistic
    fallback -- most languages don't have this feature at all, so an
    unrecognized/empty ``pattern`` is never actually reached in practice
    (``WordAccentSystem`` simply isn't enabled for such a language --
    see ``generation.phonology_gen``). Still handled defensively (returns
    ``ACCENT_2``, the cross-linguistically unmarked member) rather than
    raising, the same defensive-but-inert posture ``predict_default_stress``
    takes for a pattern it doesn't recognize.

    - ``"monosyllabic_heavy"`` (Danish stød): ``ACCENT_1`` if
      ``num_syllables == 1`` and the accented syllable is "heavy" --
      ``accented_nucleus`` is long or a diphthong (a plain string-length
      proxy, ``len(accented_nucleus) >= 2``, since every long-vowel/
      diphthong symbol this project models is itself 2+ characters --
      the same pragmatic symbol-string heuristic
      ``"penultimate_or_final_by_coda"`` above already uses instead of
      importing ``generation.sonority``'s ``Consonant``-based check,
      which ``core`` can't do), or ``accented_coda`` ends in a sonorant.
      ``ACCENT_2`` otherwise -- a defensible approximation of stød's real,
      more nuanced conditioning, not a full account.
    - ``"underived_monosyllable"`` (Swedish/Norwegian pitch accent):
      ``ACCENT_1`` if ``num_syllables == 1``, else ``ACCENT_2`` -- real
      monomorphemic monosyllables default to accent 1, everything
      polysyllabic/suffixed/compound defaults to accent 2.
    - ``"initial_falling_elsewhere_rising"`` (Serbo-Croatian's own real
      *tone* default -- see ``accented_syllable_index`` below):
      ``ACCENT_1`` (falling) if the accented syllable is the word's
      first one (index 0 -- true for every monosyllable too), else
      ``ACCENT_2`` (rising). A genuine, commonly-cited BCMS
      generalization: falling accents cluster on word-initial syllables
      and monosyllables, rising accents occur elsewhere. Reuses
      ``ACCENT_1``/``ACCENT_2`` for the *tone* dimension only -- real
      Serbo-Croatian's accent is actually tone x length (4-way); the
      *length* half is handled separately by
      ``generation.word_accent_gen.assign_word_accent_with_length``,
      since it's substantially lexical rather than shape-predictable
      (unlike tone, which has this real positional tendency).
    """
    if pattern == "monosyllabic_heavy":
        heavy = num_syllables == 1 and (
            len(accented_nucleus) >= 2 or (accented_coda and accented_coda[-1] in _SONORANT_SYMBOLS)
        )
        return WordAccentCategory.ACCENT_1 if heavy else WordAccentCategory.ACCENT_2
    if pattern == "underived_monosyllable":
        return WordAccentCategory.ACCENT_1 if num_syllables == 1 else WordAccentCategory.ACCENT_2
    if pattern == "initial_falling_elsewhere_rising":
        return WordAccentCategory.ACCENT_1 if accented_syllable_index == 0 else WordAccentCategory.ACCENT_2
    return WordAccentCategory.ACCENT_2


_SONORANT_SYMBOLS = frozenset({"m", "n", "ŋ", "ɳ", "l", "r", "ɾ", "ʁ", "j", "w"})
"""Coda consonant symbols treated as sonorant for ``"monosyllabic_heavy"``
above -- a small hardcoded set (not a lookup into
``generation.sonority.sonority``'s ``Consonant``-based ranking, which
``core`` can't import) covering every sonorant symbol this project's
phoneme pool defines."""


def _stable_local_choice(payload: str, options: list, weights: list[float]):
    """A weighted pick that's reproducible for the same ``payload`` (and
    changes when the candidate set itself changes) without needing an
    external ``rng`` threaded through every caller -- same
    ``hashlib``-based stable-seed pattern ``translation/expansion.py``'s
    own ``_derived_seed`` already uses for coining, not Python's built-in
    ``hash()`` (randomized per process by default, which would break
    ``GenerationSpec.seed`` reproducibility across runs). Keeps
    ``RomanizationScheme.apply()`` a pure function of ``ipa_text`` for a
    given scheme, which ``sound_change.py``'s reform-detection logic
    relies on (it calls ``apply()`` twice on the same IPA -- current vs.
    pre-reform scheme -- and compares the results)."""
    seed = int(hashlib.sha256(payload.encode("utf-8")).hexdigest(), 16) % (2**32)
    return random.Random(seed).choices(options, weights=weights)[0]


class RomanizationRule(BaseModel, frozen=True):
    ipa: str
    latin: str
    following: tuple[str, ...] = ()
    preceding: tuple[str, ...] = ()
    syllable: tuple[str, ...] = ()
    weight: float = 1.0
    """When more than one of this symbol's rules match the same position
    with equal specificity (see ``RomanizationScheme.apply()``), this is
    its relative share of a weighted pick among them -- e.g. real French
    ``/o/`` genuinely is "o"/"au"/"eau" depending on the specific word,
    with no phonological rule to predict which. Irrelevant (never
    consulted) when a symbol has only one matching rule for a position,
    which is still true almost everywhere -- this field changes nothing
    for a rule that never ties with another."""


class JointSpelling(BaseModel, frozen=True):
    """A real spelling convention that consumes *two* adjacent phonemes'
    letters at once, for the cases where neither phoneme's own
    independent spelling survives in the combined result -- unlike
    ``RomanizationRule.following``/``preceding`` conditioning (which lets
    one symbol's *own* spelling depend on its neighbor, but always
    leaves the neighbor to contribute its own separate letter too). Real
    French `/w/`+`/a/` -> "oi" is the motivating case: `/w/`'s own
    elsewhere-spelling is "ou" and `/a/`'s own is "a", but neither
    survives in "oi" -- so simply conditioning `/w/`'s own rule on
    ``following=("a",)`` (as this project briefly did) still leaves the
    following `/a/` free to append its own "a", wrongly producing "oia".
    Used two ways, symmetric in shape: ``RomanizationScheme.onset_nucleus_spellings``
    (``first`` = onset consonant, ``second`` = nucleus vowel) and
    ``nucleus_coda_spellings`` (``first`` = nucleus vowel, ``second`` =
    coda consonant) -- see ``apply()``'s own docstring for how the two
    compose and which wins when both could apply to the same vowel.
    Genuinely three-way (onset+nucleus+coda, fused indivisibly) spelling
    has no verified real-language case motivating it, so it isn't
    modeled -- most whole-syllable-*looking* conventions actually
    decompose into one symbol's own conditioned rule (real English
    "-ight" is `/aɪ/`'s own spelling conditioned on `following=("t",)`;
    the coda keeps its own ordinary "t", no joint consumption needed)."""

    first: str
    second: str
    latin: str
    weight: float = 1.0
    """Same role as ``RomanizationRule.weight`` -- a reproducible
    weighted pick among several joint entries tied for the same
    ``(first, second)`` pair, irrelevant when there's only one."""


class ToneMarkingStrategy(str, Enum):
    """How a tone diacritic on a vowel's IPA symbol (see
    ``core.phonology.ToneSystem.mark``) surfaces in the Latin spelling.
    ``RomanizationScheme.apply`` treats a tone mark as an opaque combining
    character -- it never imports ``core.phonology``'s ``ToneLevel``, so
    this stays decoupled from tone semantics; a category just supplies a
    ``(mark character, replacement text)`` table via ``tone_markers``."""

    VOWEL_DIACRITIC = "vowel_diacritic"
    """Today's only behavior: the mark stays inline on the vowel."""
    POSTPOSED_DIGIT = "postposed_digit"
    """Wade-Giles / numbered-Pinyin style: a digit after the syllable."""
    POSTPOSED_LETTER = "postposed_letter"
    """Zhuang-style: a letter after the syllable."""
    UNMARKED = "unmarked"
    """Tone simply isn't written."""


class VowelLengthStrategy(str, Enum):
    """How a phonemically long vowel (``core.phonology.Vowel.long``) is
    distinguished in spelling from its short counterpart."""

    NONE = "none"
    """Length isn't marked in the spelling at all."""
    DOUBLING = "doubling"
    """The letter is doubled, e.g. "a"/"aa" -- Dutch, Finnish, Estonian.
    Only makes visual sense in a closed syllable (see
    ``RomanizationRule.syllable``), unlike the other two strategies."""
    MACRON = "macron"
    """A macron over the letter, e.g. "ā" -- the scholarly convention
    shared by Latin, Hawaiian, and Japanese romaji transliteration."""
    COLON = "colon"
    """An ASCII colon after the letter, e.g. "a:" -- an informal but
    attested transliteration stand-in for IPA's own length mark."""
    SILENT_E = "silent_e"
    """English-style: the vowel keeps its plain short-vowel letter, but a
    mute "e" is appended after the syllable's own coda when that syllable
    would otherwise read as closed/short ("mat" vs. "mate") -- an open
    syllable already reads long with nothing appended, the same as
    ``DOUBLING``'s open-syllable case. Realized in ``apply()`` itself
    (see ``RomanizationScheme``), not as a generated ``RomanizationRule``,
    since the "e" lands *after* the coda consonant(s), not on the vowel's
    own token."""


class SyllableBoundaryMarker(str, Enum):
    """Whether/how two adjacent syllables get a separator when the first
    ends in a vowel and the second begins with one -- without one, the
    two vowel letters read as a single ambiguous sequence (Pinyin's own
    real rule: "Xi'an" vs. "Xian"). A diphthong is its own atomic,
    multi-character symbol (``core.phonology.Vowel.diphthong``), so
    ``RomanizationScheme.apply()``'s greedy longest-match always prefers
    it over decomposing into two adjacent single-character vowel tokens
    when *that scheme* has it registered -- meaning two adjacent vowel
    symbols mean a genuine hiatus specifically when the *language* in
    question doesn't have that sequence as one of its own diphthongs,
    the same way a real listener's own language would parse it. This is
    safe in practice for anything this project's own generation actually
    produces: `generation.word_builder`'s syllable builder always inserts
    an onset consonant between two nuclei whenever `max_onset >= 1` (the
    common case), so two bare vowel nuclei never end up literally
    adjacent to begin with. The member's own value *is* the
    literal marker text, unlike ``tone_markers`` (no per-language lookup
    table needed) -- except ``DIAERESIS``, which isn't an inserted
    character at all (see its own docstring)."""

    NONE = ""
    APOSTROPHE = "'"
    HYPHEN = "-"
    DIAERESIS = "diaeresis"
    """Real French tréma (Noël, naïve): marks that two adjacent vowel
    *letters* are read as separate sounds, not blended into one of the
    language's established digraph readings -- unlike ``APOSTROPHE``/
    ``HYPHEN``, this doesn't insert a character *between* the two vowels;
    it modifies the *second* vowel's own letter (a -> ä, e -> ë, i -> ï,
    o -> ö, u -> ü). ``apply()`` special-cases this value for exactly
    that reason -- its own value here isn't literal marker text the way
    the other members' are."""


class ExoticSymbolStyle(str, Enum):
    """How a phoneme with no obvious single Latin letter gets spelled,
    absent a more specific rule (reference-language deviation, or one of
    ``OrthographyCategory``'s other generated rules)."""

    MONOLETTER = "monoletter"
    """One ASCII letter per sound, even at the cost of merging some
    distinctions -- a "shallow"/phonemic system in the spirit of Finnish,
    Swahili, or informal Georgian transliteration."""
    DIGRAPH = "digraph"
    """A two-letter ASCII sequence, e.g. "ʃ" -> "sh"."""
    DIACRITIC = "diacritic"
    """A single Latin-Extended letter, e.g. "ʃ" -> "š"."""


class MuteSuffixRule(BaseModel, frozen=True):
    pos: PartOfSpeech
    suffix: str
    """Appended to a word's romanized spelling with no corresponding IPA
    change -- a real French infinitive's silent "-r" ("parler" /paʁle/),
    not sentence-driven agreement (this project has no live inflectional
    system for a word's spelling to vary by -- see
    ``GrammaticalSpelling``'s own docstring)."""


class GrammaticalSpelling(BaseModel, frozen=True):
    """A language's part-of-speech-keyed spelling conventions --
    genuinely grammar-driven (needs a word's POS), so deliberately kept
    separate from ``RomanizationScheme.apply()`` itself, which stays a
    pure function of an IPA string with no grammatical context. Applied
    once, when a word is coined (``apply_grammatical_spelling``), not
    re-evaluated per sentence -- this models a word's fixed *citation
    form* convention (real German capitalizes every common noun in its
    dictionary form, real French infinitives end in a silent "r" in
    their dictionary form), not agreement that varies by which sentence
    the word appears in, which would need a live inflectional system
    this project doesn't have (``GrammarProfile.plural_suffix``/``cases``
    are generated but have no consumer anywhere yet)."""

    capitalized_pos: tuple[PartOfSpeech, ...] = ()
    all_caps_pos: tuple[PartOfSpeech, ...] = ()
    """Deliberately rarer and gated behind `GenerationSpec.allow_all_caps`
    (default off) at roll time -- no real language does this, it's the
    purely fictional-flavor case."""
    mute_suffix_by_pos: tuple[MuteSuffixRule, ...] = ()


def apply_grammatical_spelling(scheme: "RomanizationScheme", latin: str, pos: PartOfSpeech) -> str:
    """The explicit "second step with grammatical context" a word's
    spelling gets after ``RomanizationScheme.apply()`` (which never sees
    a POS at all) -- mute suffix first, then capitalization/all-caps
    (all-caps wins over plain capitalization if a POS is somehow in both
    tuples, though `_roll_grammatical_spelling` never actually produces
    that overlap)."""
    gs = scheme.grammatical_spelling
    for rule in gs.mute_suffix_by_pos:
        if rule.pos is pos:
            latin += rule.suffix
    if pos in gs.all_caps_pos:
        return latin.upper()
    if pos in gs.capitalized_pos:
        return latin[:1].upper() + latin[1:]
    return latin


class RomanizationScheme(BaseModel, frozen=True):
    rules: tuple[RomanizationRule, ...]
    vowel_symbols: tuple[str, ...] = ()
    """Which of this scheme's ipa symbols are vowels -- needed to compute
    the vowel/consonant, backness, and syllable-openness tags. Empty means
    no rule here uses adjacency conditions (or the builder didn't supply
    this), in which case every symbol just uses its unconditioned rule,
    identical to this scheme's pre-context-sensitivity behavior."""
    legal_onset_clusters: tuple[tuple[str, str], ...] = ()
    """Which 2-consonant sequences are a legal syllable onset in this
    language -- lets a whole cluster shift to the next syllable under the
    maximal-onset principle, not just a single consonant."""
    vowel_backness: tuple[tuple[str, str], ...] = ()
    """``(symbol, "front"|"back"|"central")`` pairs, for the
    ``"front_vowel"``/``"back_vowel"`` tags."""
    vowel_length: tuple[tuple[str, str], ...] = ()
    """``(symbol, "long"|"short")`` pairs, for the ``"long_vowel"``/
    ``"short_vowel"`` tags -- same role as ``vowel_backness`` above."""
    category_name: str = ""
    """A purely cosmetic, human-readable label for whichever
    ``generation.romanization_gen`` ``OrthographyCategory`` built this
    scheme -- a named preset's own name when one exactly matches (an
    explicit force, or a successful reference-profile/prompt bias), a
    synthesized description of the composed axes otherwise (empty for a
    scheme built without one, e.g. directly in a test). Never load-
    bearing: every axis this scheme actually needs (for ``apply()`` or
    for regenerating new rules during evolution) is one of the fields
    below, read directly -- this field is not looked up against a
    registry for anything."""
    tone_strategy: ToneMarkingStrategy = ToneMarkingStrategy.VOWEL_DIACRITIC
    tone_markers: tuple[tuple[str, str], ...] = ()
    """``(combining-mark character, postposed marker text)`` pairs, used
    when ``tone_strategy`` is ``POSTPOSED_DIGIT``/``POSTPOSED_LETTER``."""
    vowel_length_strategy: VowelLengthStrategy = VowelLengthStrategy.NONE
    short_vowel_consonant_doubling: bool = False
    exotic_symbol_style: ExoticSymbolStyle = ExoticSymbolStyle.DIGRAPH
    syllable_boundary_marker: SyllableBoundaryMarker = SyllableBoundaryMarker.NONE
    stress_accent_marking: str = ""
    """Whether/how this scheme's real orthography writes word stress at
    all -- ``""`` (the common case: most languages never write it, so
    ``STRESS_MARK`` is simply consumed and never rendered -- see
    ``apply()``), ``"irregular_only"`` (real Spanish: an accent mark
    appears only on the vowel of a syllable whose stress deviates from
    what ``generation.stress_gen.predict_default_stress`` would have
    predicted by default for this word -- pizza/pero are unmarked
    because they follow the rule, corazón/está are marked because they
    don't), ``"final_only"`` (real Italian: an accent mark appears
    whenever the *last* syllable is stressed -- città/perché --
    regardless of whether that's "regular" by any other measure). A
    per-``ReferenceLanguageProfile`` override, the same role
    ``syllable_boundary_marker`` plays for French's own tréma -- not
    every language pointing at the same ``OrthographyCategory`` shares
    this, so it's resolved independently rather than baked into the
    category itself."""
    stress_pattern: str = ""
    """The matched profile's own ``stress_pattern`` (see
    ``ReferenceLanguageProfile``'s own docstring) -- carried onto the
    scheme purely so ``apply()`` can recompute what this word's default
    stress *would* have been for ``"irregular_only"`` marking, without
    needing a word's part of speech or any other context ``apply()``
    doesn't already have. Empty means no curated pattern -- the generic
    baseline (see ``stress_gen.predict_default_stress``)."""
    word_accent_realization: str = ""
    """This scheme's own matched profile's ``word_accent_realization``
    (``""`` | ``"glottalization"`` | ``"pitch"`` -- see
    ``ReferenceLanguageProfile``'s own docstring), carried onto the scheme
    so ``apply()`` knows how to *not* leak the corresponding IPA-internal
    mark into Latin output even when ``word_accent_marking`` is ``""``
    (the common case -- no target profile's real orthography writes this
    feature): ``"glottalization"``'s ``WORD_ACCENT_MARK`` is consumed via
    a side channel the same way ``STRESS_MARK`` already is;
    ``"pitch"``'s two reused ``TONE_DIACRITICS`` characters need this
    field specifically to tell them apart from a *genuine* tone
    diacritic riding the same combining-mark slot -- safe because a
    language is never simultaneously tonal and word-accented (see
    ``generation.phonology_gen``'s mutual-exclusivity guard), so within
    one scheme these characters can only ever mean one or the other."""
    word_accent_marking: str = ""
    """Whether/how this scheme's real orthography writes the word-accent
    contrast at all -- ``""`` (every profile curated so far: real Danish/
    Swedish/Norwegian orthography writes neither stød nor pitch accent),
    or ``"marked"`` (a real or fictional language that *does* write it --
    designed for, not yet exercised by any curated profile). Same
    per-``ReferenceLanguageProfile`` override role ``stress_accent_marking``
    plays for stress."""
    consonant_gemination_marked: bool = False
    """Whether a phonemically long/geminate consonant (``core.phonology.Consonant.long``,
    e.g. Italian "sono" vs. "sonno") doubles its own letter -- distinct
    from ``short_vowel_consonant_doubling`` above, which *derives*
    doubling from a neighboring short vowel rather than marking a length
    distinction the consonant already has on its own. Unlike vowel
    length there's no real cross-linguistic variety in *how* gemination
    gets spelled (doubling is the near-universal Latin-alphabet
    convention), so this is a bare bool, not a strategy enum.

    This field plus the five above it (``tone_strategy``/``tone_markers``
    included) are the complete, independent set of axes
    ``generation.romanization_gen``'s ``OrthographyCategory`` composes --
    stored directly (not just ``category_name``) so evolution can
    reconstruct the exact category that built this scheme
    (``_category_from_scheme``) instead of inferring an approximation
    from which symbol happens to have which letter."""
    grammatical_spelling: GrammaticalSpelling = GrammaticalSpelling()
    """POS-keyed capitalization/all-caps/mute-suffix conventions -- unlike
    every axis above, genuinely needs a word's part of speech, which
    ``apply()`` never receives, so it's applied separately via the
    module-level ``apply_grammatical_spelling`` instead of inside
    ``apply()`` itself. Carried forward unchanged by ``evolve_romanization``
    (not re-rolled), same treatment every other axis on this class gets."""
    onset_nucleus_spellings: tuple[JointSpelling, ...] = ()
    """Real conventions that jointly spell an onset consonant + the
    nucleus vowel right after it, consuming both letters at once (real
    French `/w/`+`/a/` -> "oi") -- see ``JointSpelling``'s own docstring
    for why this is a different mechanism from per-symbol conditioning.
    Empty (every scheme until a profile curates some) is a no-op --
    ``apply()`` falls back to today's independent per-symbol spelling."""
    nucleus_coda_spellings: tuple[JointSpelling, ...] = ()
    """The coda-side mirror of ``onset_nucleus_spellings`` -- a nucleus
    vowel + the coda consonant right after it spelled jointly. No
    verified real-language case currently populates this (most
    nucleus+coda-*looking* conventions decompose into ordinary
    conditioning -- see ``JointSpelling``'s docstring), but the mechanism
    is symmetric so it's ready the moment one does."""

    def _known_symbols(self) -> list[str]:
        return sorted({rule.ipa for rule in self.rules}, key=len, reverse=True)

    def _tokenize(self, ipa_text: str) -> tuple[list[tuple[str | None, str, str]], int | None, int | None]:
        """Greedy longest-match against this scheme's own ipa symbols.
        Returns ``(tokens, stress_before, word_accent_after)``: ``tokens``
        is a list of ``(symbol, decoration, raw)`` triples exactly as
        before (a matched symbol carries its trailing combining-mark
        decoration in ``decoration``, ``raw`` empty; an unrecognized
        character is carried in ``raw`` verbatim, ``symbol`` is ``None``
        -- this scheme's long-standing "unmapped input passes through
        unchanged" contract). ``stress_before`` is the index into
        ``tokens`` that ``STRESS_MARK`` immediately preceded (``None`` if
        absent); ``word_accent_after`` is the index ``WORD_ACCENT_MARK``
        (the ``"glottalization"``-realization word-accent mark)
        immediately *followed* (``None`` if absent) -- the mirror-image
        side channel, since that mark trails its rime rather than leading
        its onset. Neither is itself a token, so every existing consumer
        of ``tokens`` (neighbor-tag lookups, coda-run-length, joint-
        spelling resolution) sees exactly the same list it always has,
        with zero risk of either marker being mistaken for a real phoneme
        anywhere in this scheme's own following/preceding conditioning."""
        known = self._known_symbols()
        tokens: list[tuple[str | None, str, str]] = []
        stress_before: int | None = None
        word_accent_after: int | None = None
        i = 0
        while i < len(ipa_text):
            if ipa_text[i] == STRESS_MARK:
                stress_before = len(tokens)
                i += 1
                continue
            if ipa_text[i] == WORD_ACCENT_MARK:
                word_accent_after = len(tokens) - 1
                i += 1
                continue
            matched = next((s for s in known if ipa_text.startswith(s, i)), None)
            if matched is None:
                tokens.append((None, "", ipa_text[i]))
                i += 1
                continue
            i += len(matched)
            deco = ""
            while i < len(ipa_text) and unicodedata.combining(ipa_text[i]):
                deco += ipa_text[i]
                i += 1
            tokens.append((matched, deco, ""))
        return tokens, stress_before, word_accent_after

    def _coda_run_length(self, tokens: list[tuple[str | None, str, str]], index: int) -> int | None:
        """How many of this vowel's immediately-following consonant tokens
        belong to *its own* syllable coda, as opposed to the next
        syllable's onset, under the maximal-onset principle (``None`` if
        ``index`` isn't a vowel token). Shared by ``_syllable_openness``
        (open iff this is 0) and ``apply()``'s postposed-tone placement
        (a marker is flushed once this many coda tokens have passed)."""
        symbol = tokens[index][0]
        if symbol is None or symbol not in self.vowel_symbols:
            return None
        rest = tokens[index + 1 :]
        consonant_run: list[str] = []
        j = 0
        while j < len(rest) and rest[j][0] is not None and rest[j][0] not in self.vowel_symbols:
            consonant_run.append(rest[j][0])  # type: ignore[arg-type]
            j += 1
        if j == len(rest):
            return len(consonant_run)  # word-final: all belong to this syllable's coda
        if len(consonant_run) <= 1:
            return 0
        if len(consonant_run) == 2 and tuple(consonant_run) in self.legal_onset_clusters:
            return 0
        return len(consonant_run) - 1

    def _syllable_openness(self, tokens: list[tuple[str | None, str, str]], index: int) -> str | None:
        """This token's *own* syllable-openness tag (``None`` if it isn't
        a vowel) -- a self-referential property, not a neighbor's."""
        coda_len = self._coda_run_length(tokens, index)
        if coda_len is None:
            return None
        return "syllable_open" if coda_len == 0 else "syllable_closed"

    def _neighbor_tags(self, tokens: list[tuple[str | None, str, str]], index: int) -> frozenset[str]:
        """The tag set a ``following``/``preceding`` condition matches
        against: the neighbor's own symbol, plus its vowel/consonant and
        backness class. Out-of-range (word start/end) or an unrecognized
        character both count as ``"boundary"``. Deliberately excludes
        syllable-openness -- that's self-referential, checked via
        ``syllable`` instead, never as something a neighbor "has"."""
        if index < 0 or index >= len(tokens):
            return frozenset({"boundary"})
        symbol = tokens[index][0]
        if symbol is None:
            return frozenset({"boundary"})
        tags = {symbol}
        if symbol in self.vowel_symbols:
            tags.add("vowel")
            backness = dict(self.vowel_backness).get(symbol)
            if backness in ("front", "back"):
                tags.add(f"{backness}_vowel")
            length = dict(self.vowel_length).get(symbol)
            if length in ("long", "short"):
                tags.add(f"{length}_vowel")
        else:
            tags.add("consonant")
        return frozenset(tags)

    @staticmethod
    def _specificity(rule: RomanizationRule) -> int:
        score = 0
        for tags in (rule.preceding, rule.following, rule.syllable):
            if tags:
                score += 1
                if any(tag not in _CLASS_TAGS for tag in tags):
                    score += 1  # an exact-symbol tag is more specific than a class tag
        return score

    def _resolve_joint_spellings(
        self, tokens: list[tuple[str | None, str, str]], ipa_text: str
    ) -> tuple[dict[int, str], set[int]]:
        """A single left-to-right pass deciding which token positions
        emit a joint spelling (``emits``, index -> the chosen ``latin``
        for *both* this position and the next) and which are consumed by
        a preceding one (``consumed``, contribute an empty ``latin``).
        Onset+nucleus is checked before nucleus+coda at each position, and
        since this walks left to right, a vowel already claimed by its
        *preceding* onset (added to ``consumed`` before this same vowel's
        own turn comes up) never also tries to claim its own following
        coda -- the documented precedence from ``JointSpelling``'s
        docstring falls out of the iteration order for free, no separate
        conflict check needed."""
        onset_nucleus_by_pair: dict[tuple[str, str], list[JointSpelling]] = {}
        for j in self.onset_nucleus_spellings:
            onset_nucleus_by_pair.setdefault((j.first, j.second), []).append(j)
        nucleus_coda_by_pair: dict[tuple[str, str], list[JointSpelling]] = {}
        for j in self.nucleus_coda_spellings:
            nucleus_coda_by_pair.setdefault((j.first, j.second), []).append(j)

        emits: dict[int, str] = {}
        consumed: set[int] = set()
        if not onset_nucleus_by_pair and not nucleus_coda_by_pair:
            return emits, consumed  # no-op fast path -- every existing scheme

        def _pick(candidates: list[JointSpelling], index: int) -> str:
            if len(candidates) == 1:
                return candidates[0].latin
            chosen = _stable_local_choice(f"{ipa_text}:{index}", candidates, [c.weight for c in candidates])
            return chosen.latin

        for index, (symbol, _deco, _raw) in enumerate(tokens):
            if symbol is None or index in consumed:
                continue
            next_symbol = tokens[index + 1][0] if index + 1 < len(tokens) else None
            if next_symbol is None:
                continue
            if symbol not in self.vowel_symbols and next_symbol in self.vowel_symbols:
                candidates = onset_nucleus_by_pair.get((symbol, next_symbol))
                if candidates:
                    emits[index] = _pick(candidates, index)
                    consumed.add(index + 1)
                    continue
            if symbol in self.vowel_symbols and next_symbol not in self.vowel_symbols:
                candidates = nucleus_coda_by_pair.get((symbol, next_symbol))
                if candidates:
                    emits[index] = _pick(candidates, index)
                    consumed.add(index + 1)
        return emits, consumed

    def apply(self, ipa_text: str) -> str:
        """Greedily rewrite an IPA string into its Latin romanization.

        The result is normalized to NFC (precomposed accents, e.g. a single
        'é' codepoint) so it matches what a human typing or copy-pasting the
        romanization would produce -- IPA itself is left untouched, since
        combining diacritics are the conventional IPA representation.

        A tone mark riding a vowel's decoration is handled per
        ``tone_strategy``: ``VOWEL_DIACRITIC`` (the default) leaves it
        inline, unchanged from this method's original behavior;
        ``UNMARKED`` drops it; ``POSTPOSED_DIGIT``/``POSTPOSED_LETTER``
        looks it up in ``tone_markers`` and, instead of appending it
        inline, defers it until this vowel's own syllable coda (see
        ``_coda_run_length``) has been emitted -- i.e. right before the
        next syllable's onset, or at the very end of the word.

        Two more axes get narrow, independent handling here.
        ``vowel_length_strategy == SILENT_E``: a vowel tagged ``"long"``
        in ``vowel_length`` that lands in a closed syllable schedules a
        literal "e" into the *same* deferred-marker mechanism the
        postposed-tone case uses, flushed at the same position (English
        "mat" vs. "mate" -- an open syllable already reads long, nothing
        scheduled). ``syllable_boundary_marker``: unlike the other axes,
        this is immediate, not deferred -- when a vowel token's
        immediately preceding token was also a vowel (a hiatus for *this*
        scheme specifically -- see ``SyllableBoundaryMarker``'s own
        docstring for why a registered diphthong never gets mistaken for
        one), the marker is emitted right before that vowel's own letter
        (Pinyin's own real rule: "Xi'an" vs. "Xian") -- except
        ``DIAERESIS``, which instead rewrites that vowel's own letter in
        place (real French tréma: Noël, naïve).

        ``stress_accent_marking`` is the same "rewrite this vowel's own
        letter in place" shape, keyed on ``STRESS_MARK`` in the raw IPA
        (extracted by ``_tokenize`` into ``stress_before``, never a real
        token) instead of on hiatus: ``""`` (most languages) leaves it
        untouched, ``"final_only"`` (real Italian) marks it when the
        stressed syllable is the word's own last one, ``"irregular_only"``
        (real Spanish) marks it when the actual stressed syllable differs
        from what ``predict_default_stress`` would have predicted from
        ``stress_pattern`` alone.

        Word accent (``word_accent_realization``/``word_accent_marking``)
        never rewrites a letter today (every curated profile leaves it
        unmarked -- ``word_accent_marking`` stays a designed-for, not-yet-
        built hook, the same "abstain when uncurated" honesty every other
        axis here practices), but still needs to make sure neither
        realization's IPA-internal mark leaks into Latin output:
        ``"glottalization"``'s ``WORD_ACCENT_MARK`` is consumed via the
        ``word_accent_after`` side channel (extracted by ``_tokenize``,
        mirroring ``stress_before``) and simply never emitted;
        ``"pitch"``'s two reused ``TONE_DIACRITICS`` characters are
        stripped from whichever vowel's ``deco`` carries them before the
        existing tone-decoration logic below ever sees them -- safe only
        because a word-accented language is never also tonal (see
        ``generation.phonology_gen``), so within one scheme these
        characters can only mean one thing.
        """
        tokens, stress_before, word_accent_after = self._tokenize(ipa_text)
        rules_by_ipa: dict[str, list[RomanizationRule]] = {}
        for rule in self.rules:
            rules_by_ipa.setdefault(rule.ipa, []).append(rule)
        tone_marker_map = dict(self.tone_markers)
        postposed = self.tone_strategy in (ToneMarkingStrategy.POSTPOSED_DIGIT, ToneMarkingStrategy.POSTPOSED_LETTER)
        vowel_length_map = dict(self.vowel_length)
        joint_emits, joint_consumed = self._resolve_joint_spellings(tokens, ipa_text)

        # Stress-accent bookkeeping, computed once up front the same way
        # `rules_by_ipa`/`tone_marker_map` are -- `actual_stress_syllable`
        # is which syllable (0-based, by vowel count) `stress_before`
        # falls on, `final_coda_symbols` is the word's own last syllable's
        # coda (both feed `stress_accent_marking`'s "irregular_only" check
        # below, which needs to know the same thing `stress_gen.assign_stress`
        # knew at build time -- but re-derived from the tokenized string
        # itself, not threaded through, since `apply()` never receives a
        # word's original per-syllable structure, only its flat IPA).
        vowel_indices = [i for i, t in enumerate(tokens) if t[0] in self.vowel_symbols]
        num_syllables = len(vowel_indices)
        actual_stress_syllable = (
            sum(1 for i in vowel_indices if i < stress_before) if stress_before is not None else None
        )
        final_coda_symbols = (
            tuple(t[0] for t in tokens[vowel_indices[-1] + 1 :] if t[0] is not None) if vowel_indices else ()
        )
        stress_pending = False

        pending_markers: dict[int, list[str]] = {}
        out: list[str] = []
        for index, (symbol, deco, raw) in enumerate(tokens):
            if index == stress_before:
                stress_pending = True
            out.extend(pending_markers.pop(index, ()))
            if symbol is None:
                out.append(raw)
                continue
            preceding_tags = self._neighbor_tags(tokens, index - 1)
            following_tags = self._neighbor_tags(tokens, index + 1)
            own_syllable_tag = self._syllable_openness(tokens, index)
            own_tags = {own_syllable_tag} if own_syllable_tag else set()
            if index in joint_emits:
                latin = joint_emits[index]
            elif index in joint_consumed:
                # Already spelled out by the preceding position's joint
                # entry -- this position contributes nothing further to
                # `latin`, but still runs its own deco/tone-mark/silent-e/
                # hiatus handling below exactly as usual.
                latin = ""
            else:
                matches = []
                for rule in rules_by_ipa.get(symbol, []):
                    if rule.preceding and not (set(rule.preceding) & preceding_tags):
                        continue
                    if rule.following and not (set(rule.following) & following_tags):
                        continue
                    if rule.syllable and not (set(rule.syllable) & own_tags):
                        continue
                    matches.append(rule)
                if not matches:
                    latin = symbol
                else:
                    best_score = max(self._specificity(rule) for rule in matches)
                    top = [rule for rule in matches if self._specificity(rule) == best_score]
                    if len(top) == 1:
                        latin = top[0].latin
                    else:
                        # Genuine alternatives (e.g. real French "o"/"au"/"eau"
                        # for the same /o/) -- a weighted pick, reproducible
                        # per token position rather than a fresh roll every
                        # call (see `_stable_local_choice`).
                        chosen = _stable_local_choice(
                            f"{ipa_text}:{index}", top, [rule.weight for rule in top]
                        )
                        latin = chosen.latin

            if (
                deco
                and self.word_accent_realization in ("pitch", "pitch_and_length")
                and self.word_accent_marking == ""
            ):
                # These characters are reused `TONE_DIACRITICS` (or, for
                # `"pitch_and_length"`, the two additional real Slavistic
                # marks -- see `word_accent_gen._TONE_LENGTH_DIACRITICS`),
                # not real tone -- strip them before the tone-decoration
                # logic below gets a chance to treat them as such. Safe
                # unconditionally: a word-accented language is never
                # simultaneously tonal.
                deco = "".join(ch for ch in deco if ch not in _PITCH_WORD_ACCENT_CHARS)

            if deco and self.tone_strategy == ToneMarkingStrategy.UNMARKED:
                deco = ""
            elif deco and postposed and any(ch in tone_marker_map for ch in deco):
                marker_text = "".join(tone_marker_map.get(ch, ch) for ch in deco)
                deco = ""
                flush_index = index + 1 + (self._coda_run_length(tokens, index) or 0)
                pending_markers.setdefault(flush_index, []).append(marker_text)

            if (
                self.vowel_length_strategy == VowelLengthStrategy.SILENT_E
                and own_syllable_tag == "syllable_closed"
                and vowel_length_map.get(symbol) == "long"
            ):
                flush_index = index + 1 + (self._coda_run_length(tokens, index) or 0)
                pending_markers.setdefault(flush_index, []).append("e")

            if self.syllable_boundary_marker and symbol in self.vowel_symbols and index > 0 and tokens[index - 1][0] in self.vowel_symbols:
                if self.syllable_boundary_marker == SyllableBoundaryMarker.DIAERESIS:
                    # Not an inserted character -- real French tréma
                    # modifies the *second* vowel's own letter instead
                    # (Noël, naïve). Left unchanged if it doesn't start
                    # with a plain vowel letter this table covers.
                    first = _DIAERESIS_MAP.get(latin[:1])
                    if first is not None:
                        latin = first + latin[1:]
                else:
                    out.append(self.syllable_boundary_marker.value)

            if stress_pending and symbol in self.vowel_symbols:
                # This is the stressed syllable's own nucleus -- the
                # first (and only) vowel reached since `stress_before`.
                # `""` (the common case, most languages never write
                # stress) leaves `latin` untouched; the other two modes
                # rewrite this vowel's own first letter in place, the
                # same shape `_DIAERESIS_MAP` above already uses.
                is_final_syllable = actual_stress_syllable == num_syllables - 1
                should_mark = (self.stress_accent_marking == "final_only" and is_final_syllable) or (
                    self.stress_accent_marking == "irregular_only"
                    and actual_stress_syllable
                    != predict_default_stress(num_syllables, self.stress_pattern, final_coda_symbols)
                )
                if should_mark:
                    accented = _STRESS_ACCENT_MAP.get(latin[:1])
                    if accented is not None:
                        latin = accented + latin[1:]
                stress_pending = False

            out.append(latin + deco)
        out.extend(pending_markers.pop(len(tokens), ()))
        collapsed = _TRIPLE_LETTER_RUN.sub(r"\1\1", "".join(out))
        return unicodedata.normalize("NFC", collapsed)


class OrthographyCategory(BaseModel, frozen=True):
    """A reusable orthography *typology* -- not a full per-language rule
    set (that's what ``ReferenceLanguageProfile.orthography`` and its own
    hand-curated ``RomanizationRule``s are for), but the handful of
    higher-level, genuinely independent conventions that make an
    orthography feel like a particular real-world family: how it spells
    an otherwise-exotic sound (``exotic_symbol_style``), whether/how it
    marks vowel length (``vowel_length_strategy``, including English's
    own trailing-silent-e convention), whether a short vowel makes the
    following onset consonant double (``short_vowel_consonant_doubling``),
    how tone (if any) surfaces (``tone_strategy``), and whether/how a
    vowel-initial syllable following a vowel-final one gets a separator
    (``syllable_boundary_marker``, Pinyin's own real "Xi'an" vs. "Xian"
    rule).

    ``generation.romanization_gen._CATEGORIES`` holds a handful of named
    *anchor* instances (e.g. ``"germanic-doubling-style"``,
    ``"wade-giles-style"``) for real, attested combinations -- useful as
    exact, keyword-forceable targets (``OrthographyForce.style``, below)
    and as what a ``ReferenceLanguageProfile`` can point at via its own
    ``orthography_category`` (a coarse "which family does this lean
    toward" signal). But since every field here is independent, nothing
    requires a language to use one of those fixed bundles: the *default*
    unforced case rolls each axis separately (``_roll_independent_axes``),
    so e.g. Dutch/German-style vowel-length doubling and Wade-Giles-style
    postposed-digit tone marking -- two different named anchors' axes --
    can and do co-occur in a freshly generated language."""

    name: str
    description: str
    exotic_style: dict[str, str]
    exotic_symbol_style: ExoticSymbolStyle = ExoticSymbolStyle.DIGRAPH
    """Which of the three conventions ``exotic_style`` itself follows --
    purely descriptive metadata (``apply()`` only ever consults
    ``exotic_style``/``rules`` directly), so a consumer can group or
    display categories by this axis without string-matching ``name``."""
    tone_strategy: ToneMarkingStrategy = ToneMarkingStrategy.VOWEL_DIACRITIC
    tone_markers: tuple[tuple[str, str], ...] = ()
    vowel_length_strategy: VowelLengthStrategy = VowelLengthStrategy.NONE
    short_vowel_consonant_doubling: bool = False
    """The Dutch/German/English-ish convention where an onset consonant
    doubles specifically because the *preceding* vowel is short (Dutch
    "zitten" vs "zaten", German "Bett") -- realized purely as data (a
    ``preceding=("short_vowel",)``-conditioned ``RomanizationRule`` per
    consonant), reusing the existing tag-matching machinery rather than
    any new code path in ``apply()``."""
    syllable_boundary_marker: SyllableBoundaryMarker = SyllableBoundaryMarker.NONE
    stress_accent_marking: str = ""
    """This category family's own baseline for whether/how stress gets
    written -- almost always ``""`` (real written stress-accent is
    genuinely rare typologically), the same "family default, overridden
    per-profile when curated" role ``syllable_boundary_marker`` plays for
    French's own tréma among ``diacritic-style`` languages -- see
    ``RomanizationScheme.stress_accent_marking``'s own docstring."""
    consonant_gemination_marked: bool = False
    """Whether a phonemically long/geminate consonant doubles its own
    letter (Italian "sono" vs. "sonno") -- distinct from
    ``short_vowel_consonant_doubling`` above, which derives doubling from
    a neighboring short *vowel* rather than the consonant's own length."""


class OrthographyForce(BaseModel, frozen=True):
    """Explicit, deterministic overrides for ``generation.romanization_gen``'s
    style selection -- the unconditional channel (same spirit as
    ``GenerationSpec``'s ``force_isolated``/``force_high_altitude``/
    ``force_tonal``): a prompt's wording, and a matched reference
    profile's own bias, are inference and can be wrong or absent; this is
    a guarantee, for testing or for when you want a specific style and
    nothing else.

    ``None`` on any field means "not forced, let the normal roll/bias
    decide." ``style`` picks one of ``generation.romanization_gen``'s
    named anchor presets outright (exact, no ``rng`` consumption); any of
    the other fields set *on top* override just that one axis, composing
    with whatever ``style`` (or the roll/bias, if ``style`` is unset)
    produced -- e.g. ``OrthographyForce(style="germanic-doubling-style",
    tone_strategy=POSTPOSED_DIGIT)`` is Dutch/German-style doubling with
    Wade-Giles-style tone digits, forced and reproducible, a combination
    no single named preset has on its own."""

    style: str | None = None
    exotic_symbol_style: ExoticSymbolStyle | None = None
    vowel_length_strategy: VowelLengthStrategy | None = None
    short_vowel_consonant_doubling: bool | None = None
    tone_strategy: ToneMarkingStrategy | None = None
    syllable_boundary_marker: SyllableBoundaryMarker | None = None
    consonant_gemination_marked: bool | None = None
