"""Deterministic romanization-rule generation.

Every generated scheme is built from five *independent* axes -- how an
exotic sound gets spelled (``ExoticSymbolStyle``: digraph, diacritic, or
monoletter), how vowel length is marked (``VowelLengthStrategy``: none,
doubling, macron, colon, or English-style trailing silent-e), whether a
short vowel doubles the following onset consonant (a bool), how tone
surfaces (``ToneMarkingStrategy``: inline diacritic, postposed
digit/letter, or unmarked), and whether/how two adjacent syllables get a
separator when the first ends in a vowel and the second begins with one
(``SyllableBoundaryMarker``: none, apostrophe, or hyphen -- Pinyin's own
real "Xi'an" vs. "Xian" rule) -- see ``core.romanization.OrthographyCategory``.
``_CATEGORIES`` holds a handful of named *anchor* instances for real,
attested combinations (``germanic-doubling-style``, ``wade-giles-style``,
``pinyin-style``, ``silent-e-style``, etc.), but nothing restricts a
generated language to one of those bundles: absent a force or a
reference-profile/prompt match, ``_roll_independent_axes`` picks each axis
on its own, so combinations no single anchor has (Dutch/German-style
doubling *with* Wade-Giles-style tone digits, say) are freely reachable.
The winning category is applied consistently across the whole phoneme
inventory, so the result reads as one coherent "vibe" rather than a random
mix, and every one of its axes is logged onto the built scheme (
``category_name``/``tone_strategy``/``tone_markers``/
``vowel_length_strategy``/``short_vowel_consonant_doubling``/
``exotic_symbol_style``/``syllable_boundary_marker``) so it's fully
visible in a saved language's ``romanization.yaml``.

Three things can steer *which* category a language lands on, in
increasing order of certainty:

- When ``contact_languages`` matches a profile in ``reference_languages``,
  its own hand-curated ``orthography`` rules blend in probabilistically
  per symbol (e.g. a language biased toward Dutch is likely, not certain,
  to spell /u/ as "oe"), and, if the profile declares one, its
  ``orthography_category`` gets one probabilistic shot at winning the
  whole-scheme category roll (Dutch's own profile leans toward
  "germanic-doubling-style").
- ``requested_orthography_style`` -- a name the prompt classifier
  extracted directly from the user's wording (e.g. "mark tone with
  numbers, Wade-Giles style") -- gets the same kind of probabilistic shot,
  after any reference-profile match.
- ``forced_orthography`` (an ``OrthographyForce``) is the unconditional
  channel: ``style`` picks a named anchor outright, no ``rng`` involved;
  any other field on it overrides *just that one axis* on top of whatever
  ``style``/the roll/the bias produced, so forced axes compose freely
  (``OrthographyForce(style="germanic-doubling-style",
  tone_strategy=POSTPOSED_DIGIT)`` combines two different anchors' axes on
  purpose). This is the "for testing, or when you want a specific style"
  channel -- same spirit as ``core.spec.GenerationSpec``'s
  ``force_isolated``/``force_high_altitude``/``force_tonal``, and the only
  one of the three that's a guarantee rather than a lean.

For a symbol *not* covered by any matched profile's curated rules, the
fallback still tries to stay in the family: ``_rules_for_symbol`` prefers
a matched reference profile's own *named-anchor* exotic-symbol table
(e.g. a Dutch-biased language still leans digraph -- "sch", "ch" -- for an
uncurated exotic sound, not whatever the independently-resolved whole-
scheme category happens to use) over the scheme's own flat fallback,
which only applies when no active contact language has any convention for
that symbol at all -- see ``_rules_for_symbol``'s own docstring for the
full priority order.

A reference profile's orthography can define more than one rule for the
same symbol, conditioned via ``core.romanization.RomanizationRule``'s
``following``/``preceding`` tags (e.g. Dutch spells a long vowel with a
doubled letter in a closed syllable but a single letter in an open one --
"vuur" vs. "vuren"; Mandarin pinyin spells /y/ as "u" instead of "ü"
specifically after j/q/x/y); when the reference roll succeeds, *every*
variant for that symbol is carried over, not just one, so the context
distinction survives into the built scheme. A category's own
``vowel_length_strategy``/``short_vowel_consonant_doubling`` axes are
realized the same way, but *generated* against the actual inventory
rather than hand-curated -- see ``_generate_length_rules``/
``_generate_doubling_rules``. ``PhonemeInventory``-derived
``vowel_symbols``/``legal_onset_clusters``/``vowel_backness``/
``vowel_length`` are attached to every scheme this module builds so
``RomanizationScheme.apply()`` can actually resolve that context -- see
its own docstring.

``evolve_romanization()`` is the equivalent for an already-generated
language undergoing sound change (``generation/sound_change.py``): spelling
inertia plus rare, discrete reform and gradual orthography-only drift,
decided per *symbol* so every word sharing a symbol stays consistent --
see its own docstring. It reconstructs and carries forward the base
scheme's own category exactly (``_category_from_scheme``, reading the
axis fields the scheme already stores directly -- never an approximation)
rather than rolling a fresh one or re-consulting reference-language bias,
so a language's orthographic "family" doesn't randomly flip mid-evolution.
``forced_orthography`` is still honored, though -- a deliberate,
user-triggered whole-scheme reform (unlike the *automatic* probabilistic
reform noted as unmodeled in ``architecture/OVERVIEW.md``'s known
limitations).
"""

from __future__ import annotations

import random
import unicodedata
from collections.abc import Callable

from conlang_generator.core.phonology import TONE_DIACRITICS, Consonant, PhonemeInventory, ToneLevel, Vowel
from conlang_generator.core.romanization import (
    ExoticSymbolStyle,
    OrthographyCategory,
    OrthographyForce,
    RomanizationRule,
    RomanizationScheme,
    SyllableBoundaryMarker,
    ToneMarkingStrategy,
    VowelLengthStrategy,
)
from conlang_generator.generation import sonority
from conlang_generator.generation.reference_languages import ReferenceLanguageProfile, match_profiles

_EJECTIVE_SPELLING_MARKS = ("'", "’")  # ascii apostrophe, right single quote

_DIGRAPH_TABLE: dict[str, str] = {
    "ʃ": "sh", "ʒ": "zh", "tʃ": "ch", "dʒ": "j", "ŋ": "ng",
    "x": "kh", "χ": "kh", "ʔ": "'", "ɾ": "r", "j": "y",
    "pʼ": "p'", "tʼ": "t'", "kʼ": "k'",
    "ɛ": "e", "ɔ": "o", "ə": "e", "ɨ": "y",
    # Retroflex, uvular, palatal, pharyngeal, dental, click, and implosive
    # series, plus the near-close/open vowels -- no symbol in
    # phonology_gen.py's shared pool should fall through to a raw IPA
    # glyph. ASCII-only, per this style's own promise.
    "ʈ": "tr", "ɖ": "dr", "ɟ": "gy", "ɢ": "gg", "ʁ": "rh",
    "ɳ": "nr", "ɲ": "ny", "ʂ": "sr", "ʐ": "zr", "ɬ": "lh",
    "ħ": "hh", "ʕ": "3", "θ": "th", "ð": "dh", "ç": "hy", "ʝ": "jh",
    "ǀ": "c", "ǃ": "q", "ǂ": "tc", "ǁ": "xh",
    "ɓ": "bh", "ɗ": "d'", "ʄ": "j'", "ɠ": "gh",
    "ɪ": "i", "ʊ": "u", "æ": "ae", "ɐ": "uh", "ɑ": "aa", "ø": "eu", "œ": "ue",
    # Secondary articulations (aspiration, pharyngealization/"emphatics")
    # and phonemic vowel length. "ph"/"th"/"kh" (the standard aspiration
    # digraph) and doubled letters (the standard length digraph) are
    # already spoken for by θ/x-χ and ɑ respectively in this table, so
    # aspiration uses a capital-H marker instead, length a literal colon
    # (a common ASCII stand-in for IPA's own "ː"), and emphatics the real
    # Arabizi (informal Arabic chat) numeral convention -- ط=6, ص=9,
    # ض=9', ظ=6'.
    "ɣ": "gh", "pʰ": "pH", "tʰ": "tH", "kʰ": "kH",
    "tˤ": "6", "dˤ": "9'", "sˤ": "9", "ðˤ": "6'",
    "aː": "a:", "iː": "i:", "uː": "u:", "eː": "e:", "oː": "o:",
    # Palatalization: a trailing "y" (Hungarian's own real ny/ty digraphs
    # use exactly this convention). Gemination: no marking convention in
    # this style by default -- these are the *flat fallback* spellings
    # (plain letter, length lost) a `consonant_gemination_marked=False`
    # category actually renders; `_generate_gemination_rules` overrides
    # them with the doubled letter when that axis is on.
    "tʲ": "ty", "dʲ": "dy", "nʲ": "ny", "lʲ": "ly",
    "kː": "k", "tː": "t", "pː": "p", "sː": "s", "nː": "n", "lː": "l",
    # Diphthongs -- "ai"/"au"/"ei" need no entry at all (already plain
    # ASCII, so the identity fallback already spells them correctly); the
    # rest reuse this style's own existing rendering of their non-ASCII
    # component, for consistency, except "œy" (Dutch "ui"), hand-picked
    # as the real, unambiguous spelling rather than composed from œ/y's
    # own separate mappings (which would give an unrecognizable result).
    "ɔi": "oi", "ɛi": "ei", "œy": "ui",
    # Nasalized vowels (Portuguese/French/Hindi-style): trailing "n",
    # the common ASCII stand-in for a nasalization mark.
    "ã": "an", "ẽ": "en", "ĩ": "in", "õ": "on", "ũ": "un",
    # Breathy/murmured voice (Hindi's own 4th stop series): "bh"/"gh"
    # already denote the implosives ɓ/ɠ above in this style -- a
    # deliberate, documented merge (same "shallow styles accept some
    # collisions" precedent ʃ/ʂ/ɕ already uses in monoletter style below),
    # not an oversight, and also the *authentic* Hindi spelling.
    "bʱ": "bh", "dʱ": "dh", "ɡʱ": "gh",
    # Nahuatl's own /tɬ/ -- "tl" is its real, common ASCII rendering
    # (literally how "Nahuatl" itself is spelled).
    "tɬ": "tl",
    # Pre-aspiration (Icelandic-style): h-*prefix*, contrasting post-
    # aspiration's own capital-H *suffix* just above.
    "ʰp": "hp", "ʰt": "ht", "ʰk": "hk",
    # Turkish's own dotless-ı vowel -- merges with plain /i/ in this
    # ASCII-only style (diacritic style below uses the real letter).
    "ɯ": "i",
}
_DIACRITIC_TABLE: dict[str, str] = {
    "ʃ": "š", "ʒ": "ž", "tʃ": "č", "dʒ": "ǯ", "ŋ": "ṅ",
    "x": "ḥ", "χ": "ḥ", "ʔ": "’", "ɾ": "r", "j": "y",
    "pʼ": "p̓", "tʼ": "t̓", "kʼ": "k̓",
    "ɛ": "ë", "ɔ": "ö", "ə": "ě", "ɨ": "ï",
    # Same coverage as the digraph style above, using Latin-Extended
    # letters and real transliteration conventions where one exists (ɲ->ň,
    # ʕ->ʿ). Clicks have no diacritic tradition in any real orthography, so
    # they reuse the same plain-letter convention as the digraph style.
    "ʈ": "ṭ", "ɖ": "ḍ", "ɟ": "ď", "ɢ": "ġ", "ʁ": "ř",
    "ɳ": "ṇ", "ɲ": "ň", "ʂ": "ṣ", "ʐ": "ẓ", "ɬ": "ł",
    "ħ": "ḫ", "ʕ": "ʿ", "θ": "ŧ", "ð": "đ", "ç": "ç", "ʝ": "ĵ",
    "ǀ": "c", "ǃ": "q", "ǂ": "tc", "ǁ": "xh",
    "ɓ": "bh", "ɗ": "dh", "ʄ": "jh", "ɠ": "gh",
    "ɪ": "i", "ʊ": "u", "æ": "æ", "ɐ": "ă", "ɑ": "ȧ", "ø": "ø", "œ": "œ",
    # ɣ reuses Turkish "ğ" (a historically velar-fricative-derived sound in
    # that language) -- ɢ already has "ġ" above, so this stays distinct.
    # Aspiration and pharyngealization keep their own IPA modifier letters
    # (ʰ, ˤ) as their diacritic-style spelling -- both are already
    # legitimate Latin-adjacent modifier letters, not exotic additions, and
    # this avoids colliding with the retroflex series' ṭ/ḍ/ṣ/ẓ above. Long
    # vowels use the standard scholarly macron convention (ā ī ū ē ō --
    # Latin, Japanese romaji, Hawaiian, Arabic transliteration all use this).
    "ɣ": "ğ", "pʰ": "pʰ", "tʰ": "tʰ", "kʰ": "kʰ",
    "tˤ": "tˤ", "dˤ": "dˤ", "sˤ": "sˤ", "ðˤ": "ðˤ",
    "aː": "ā", "iː": "ī", "uː": "ū", "eː": "ē", "oː": "ō",
    # Palatalization keeps its own IPA modifier letter (ʲ) as-is, same
    # treatment aspiration/pharyngealization's modifier letters already
    # got. Gemination fallback (see the digraph table's own comment).
    "tʲ": "tʲ", "dʲ": "dʲ", "nʲ": "nʲ", "lʲ": "lʲ",
    "kː": "k", "tː": "t", "pː": "p", "sː": "s", "nː": "n", "lː": "l",
    # Diphthongs (see the digraph table's own comment for "ai"/"au"/"ei").
    # "ɛi" stays distinct from the plain "ei" diphthong here (unlike
    # digraph style, which conflates them) -- diacritic style generally
    # keeps such distinctions where digraph/monoletter don't.
    "ɔi": "öi", "ɛi": "ëi", "œy": "ui",
    # Nasalized vowels keep the real IPA nasalization mark (identity --
    # already legitimate Latin-Extended letters, same treatment aspiration/
    # pharyngealization/palatalization's own modifier letters got above).
    "ã": "ã", "ẽ": "ẽ", "ĩ": "ĩ", "õ": "õ", "ũ": "ũ",
    # Breathy/murmured voice keeps its own real IPA modifier letter (ʱ),
    # identity, same treatment as aspiration's ʰ -- no collision here,
    # unlike the digraph style's bh/dh/gh (see its own comment).
    "bʱ": "bʱ", "dʱ": "dʱ", "ɡʱ": "ɡʱ",
    "tɬ": "tł",
    # Pre-aspiration keeps its own real IPA modifier letter (ʰ) as-is,
    # identity, same treatment as post-aspiration.
    "ʰp": "ʰp", "ʰt": "ʰt", "ʰk": "ʰk",
    # Turkish's own real dotless-ı letter.
    "ɯ": "ı",
}
# A "shallow"/phonemic system in the spirit of Finnish, Swahili, or
# informal Georgian transliteration -- one ASCII letter per sound, even at
# the cost of merging some distinctions the other two tables keep separate
# (e.g. the whole retroflex/postalveolar fricative cluster folds toward
# plain "s"/"z"; ejective/aspiration/pharyngealization marks are dropped
# entirely rather than spelled). Same key coverage as the tables above.
_MONOLETTER_TABLE: dict[str, str] = {
    "ʃ": "x", "ʒ": "j", "tʃ": "c", "dʒ": "q", "ŋ": "n",
    "x": "h", "χ": "h", "ʔ": "'", "ɾ": "r", "j": "y",
    "pʼ": "p", "tʼ": "t", "kʼ": "k",
    "ɛ": "e", "ɔ": "o", "ə": "a", "ɨ": "i",
    "ʈ": "t", "ɖ": "d", "ɟ": "j", "ɢ": "g", "ʁ": "r",
    "ɳ": "n", "ɲ": "n", "ʂ": "s", "ʐ": "z", "ɬ": "l",
    "ħ": "h", "ʕ": "a", "θ": "t", "ð": "d", "ç": "h", "ʝ": "y",
    "ǀ": "c", "ǃ": "q", "ǂ": "x", "ǁ": "z",
    "ɓ": "b", "ɗ": "d", "ʄ": "j", "ɠ": "g",
    "ɪ": "i", "ʊ": "u", "æ": "e", "ɐ": "a", "ɑ": "a", "ø": "o", "œ": "o",
    "ɣ": "g", "pʰ": "p", "tʰ": "t", "kʰ": "k",
    "tˤ": "t", "dˤ": "d", "sˤ": "s", "ðˤ": "d",
    "aː": "a", "iː": "i", "uː": "u", "eː": "e", "oː": "o",
    # Palatalization dropped entirely (merged with the plain consonant),
    # same "shallow system accepts some merging" precedent ejectives
    # already use above. Gemination fallback (see digraph table comment).
    "tʲ": "t", "dʲ": "d", "nʲ": "n", "lʲ": "l",
    "kː": "k", "tː": "t", "pː": "p", "sː": "s", "nː": "n", "lː": "l",
    # Diphthongs are the one deliberate exception to this style's own
    # one-letter philosophy -- they're inherently two-part sounds, and no
    # real "shallow" orthography actually collapses one to a single
    # letter, so these stay two-letter like the other styles' renderings
    # (see the digraph table's own comment for "ai"/"au"/"ei").
    "ɔi": "oi", "ɛi": "ei", "œy": "ui",
    # Nasalization dropped entirely, same "shallow, merges some
    # distinctions" precedent every other marked feature above uses.
    "ã": "a", "ẽ": "e", "ĩ": "i", "õ": "o", "ũ": "u",
    # Breathy voice dropped, merges with the plain voiced stop.
    "bʱ": "b", "dʱ": "d", "ɡʱ": "g",
    "tɬ": "l",
    # Pre-aspiration dropped, merges with the plain voiceless stop.
    "ʰp": "p", "ʰt": "t", "ʰk": "k",
    "ɯ": "i",
}

# Digit/letter markers a postposed-tone category maps `core.phonology`'s
# five `ToneLevel` diacritics onto. Arbitrary assignments (this project's
# `ToneSystem` is a generic five-level illustrative model, not tied to any
# one real language's actual tone inventory) but fixed and named, the same
# "illustrative, not exhaustive" spirit as everywhere else in this module.
_WADE_GILES_TONE_MARKERS = tuple(
    (TONE_DIACRITICS[level], digit)
    for level, digit in zip(
        (ToneLevel.LOW, ToneLevel.MID, ToneLevel.HIGH, ToneLevel.RISING, ToneLevel.FALLING), "12345"
    )
)
_ZHUANG_TONE_MARKERS = tuple(
    (TONE_DIACRITICS[level], letter)
    for level, letter in zip(
        (ToneLevel.LOW, ToneLevel.MID, ToneLevel.HIGH, ToneLevel.RISING, ToneLevel.FALLING),
        ("z", "j", "x", "q", "h"),
    )
)

_DIGRAPH_CATEGORY = OrthographyCategory(
    name="digraph-style",
    description="Exotic sounds spelled with two-letter ASCII digraphs (ʃ -> sh); no vowel-length or tone-marking convention beyond the default inline diacritic.",
    exotic_style=_DIGRAPH_TABLE,
    exotic_symbol_style=ExoticSymbolStyle.DIGRAPH,
)
_DIACRITIC_CATEGORY = OrthographyCategory(
    name="diacritic-style",
    description="Exotic sounds spelled with a single Latin-Extended letter (ʃ -> š); no vowel-length or tone-marking convention beyond the default inline diacritic.",
    exotic_style=_DIACRITIC_TABLE,
    exotic_symbol_style=ExoticSymbolStyle.DIACRITIC,
)
_MONOLETTER_CATEGORY = OrthographyCategory(
    name="monoletter-style",
    description="A shallow, near-phonemic system: one ASCII letter per sound wherever possible, in the spirit of Finnish, Swahili, or informal Georgian transliteration.",
    exotic_style=_MONOLETTER_TABLE,
    exotic_symbol_style=ExoticSymbolStyle.MONOLETTER,
)
_GERMANIC_DOUBLING_CATEGORY = OrthographyCategory(
    name="germanic-doubling-style",
    description="Dutch/German-like: a long vowel doubles its letter in a closed syllable (a/aa), and a short vowel doubles the *following* onset consonant instead (zitten vs. zaten).",
    # Digraph, not diacritic -- real Dutch/German orthography marks its
    # exotic sounds with two-letter combinations (sch, ch, ng, sj, tj),
    # not accented letters; a Slavic-style š/ě/č fallback doesn't read as
    # Germanic at all.
    exotic_style=_DIGRAPH_TABLE,
    exotic_symbol_style=ExoticSymbolStyle.DIGRAPH,
    vowel_length_strategy=VowelLengthStrategy.DOUBLING,
    short_vowel_consonant_doubling=True,
)
_SCHOLARLY_MACRON_CATEGORY = OrthographyCategory(
    name="scholarly-macron-style",
    description="Latin/Hawaiian/Japanese-romaji-like: a long vowel always takes a macron (ā), regardless of syllable shape.",
    exotic_style=_DIGRAPH_TABLE,
    exotic_symbol_style=ExoticSymbolStyle.DIGRAPH,
    vowel_length_strategy=VowelLengthStrategy.MACRON,
)
_WADE_GILES_CATEGORY = OrthographyCategory(
    name="wade-giles-style",
    description="Wade-Giles-like: tone is written as a digit after the syllable rather than a diacritic on the vowel.",
    exotic_style=_DIACRITIC_TABLE,
    exotic_symbol_style=ExoticSymbolStyle.DIACRITIC,
    tone_strategy=ToneMarkingStrategy.POSTPOSED_DIGIT,
    tone_markers=_WADE_GILES_TONE_MARKERS,
)
_ZHUANG_CATEGORY = OrthographyCategory(
    name="zhuang-style",
    description="Inspired by (not a literal reproduction of) Zhuang's real tone-letter convention: tone is written as a letter after the syllable rather than a diacritic on the vowel.",
    exotic_style=_DIGRAPH_TABLE,
    exotic_symbol_style=ExoticSymbolStyle.DIGRAPH,
    tone_strategy=ToneMarkingStrategy.POSTPOSED_LETTER,
    tone_markers=_ZHUANG_TONE_MARKERS,
)
_PINYIN_CATEGORY = OrthographyCategory(
    name="pinyin-style",
    description="Pinyin-like: tone stays an inline diacritic on the vowel (the same default every other non-postposed category uses), but a vowel-initial syllable following a vowel-final one gets an apostrophe separator (\"Xi'an\" vs. \"Xian\") -- a real, well-known second romanization of the same language Wade-Giles-style names, differing specifically on tone marking.",
    exotic_style=_DIACRITIC_TABLE,
    exotic_symbol_style=ExoticSymbolStyle.DIACRITIC,
    syllable_boundary_marker=SyllableBoundaryMarker.APOSTROPHE,
)
_SILENT_E_CATEGORY = OrthographyCategory(
    name="silent-e-style",
    description="English-like: a long vowel keeps its plain short-vowel letter, but a mute \"e\" is appended after the syllable's own coda when it would otherwise read short (\"mat\" vs. \"mate\").",
    exotic_style=_DIGRAPH_TABLE,
    exotic_symbol_style=ExoticSymbolStyle.DIGRAPH,
    vowel_length_strategy=VowelLengthStrategy.SILENT_E,
)
_GEMINATION_CATEGORY = OrthographyCategory(
    name="gemination-style",
    description="Finnish/Italian/Japanese-like: a phonemically long/geminate consonant doubles its own letter (kukka vs. kuka), independent of any neighboring vowel.",
    exotic_style=_DIACRITIC_TABLE,
    exotic_symbol_style=ExoticSymbolStyle.DIACRITIC,
    consonant_gemination_marked=True,
)
_CATEGORIES = (
    _DIGRAPH_CATEGORY,
    _DIACRITIC_CATEGORY,
    _MONOLETTER_CATEGORY,
    _GERMANIC_DOUBLING_CATEGORY,
    _SCHOLARLY_MACRON_CATEGORY,
    _WADE_GILES_CATEGORY,
    _ZHUANG_CATEGORY,
    _PINYIN_CATEGORY,
    _SILENT_E_CATEGORY,
    _GEMINATION_CATEGORY,
)
_CATEGORIES_BY_NAME = {category.name: category for category in _CATEGORIES}
ORTHOGRAPHY_STYLE_NAMES: tuple[str, ...] = tuple(_CATEGORIES_BY_NAME)
"""Public -- the valid `OrthographyForce.style`/`--orthography-style`
names, for CLI help text and validation."""

# How often a symbol covered by a matched reference language's own spelling
# convention actually uses it, vs. falling through to the generic style --
# organic/free rather than a literal copy (see module docstring). Also
# reused as the weight for preferring a matched reference profile's own
# declared `orthography_category`, or the prompt-requested one, over an
# independently-rolled/inherited category.
_REFERENCE_ORTHOGRAPHY_WEIGHT = 0.7

# Materializes a bare axis choice (from a force, or an independent roll)
# into the concrete data an OrthographyCategory needs.
_EXOTIC_STYLE_TABLES: dict[ExoticSymbolStyle, dict[str, str]] = {
    ExoticSymbolStyle.MONOLETTER: _MONOLETTER_TABLE,
    ExoticSymbolStyle.DIGRAPH: _DIGRAPH_TABLE,
    ExoticSymbolStyle.DIACRITIC: _DIACRITIC_TABLE,
}
_TONE_MARKERS_BY_STRATEGY: dict[ToneMarkingStrategy, tuple[tuple[str, str], ...]] = {
    ToneMarkingStrategy.POSTPOSED_DIGIT: _WADE_GILES_TONE_MARKERS,
    ToneMarkingStrategy.POSTPOSED_LETTER: _ZHUANG_TONE_MARKERS,
}

# Illustrative, not exhaustive, relative weights for the *unforced*,
# no-reference-match independent roll (`_roll_independent_axes`) -- most
# real languages don't mark phonemic vowel length distinctly at all, and
# among languages that do mark tone in writing, an inline diacritic is the
# more common convention, but every option stays reachable.
_EXOTIC_SYMBOL_STYLE_WEIGHTS: dict[ExoticSymbolStyle, float] = {
    ExoticSymbolStyle.DIGRAPH: 1.0,
    ExoticSymbolStyle.DIACRITIC: 1.0,
    ExoticSymbolStyle.MONOLETTER: 1.0,
}
_VOWEL_LENGTH_STRATEGY_WEIGHTS: dict[VowelLengthStrategy, float] = {
    VowelLengthStrategy.NONE: 4.0,
    VowelLengthStrategy.DOUBLING: 1.0,
    VowelLengthStrategy.MACRON: 1.0,
    VowelLengthStrategy.COLON: 1.0,
    VowelLengthStrategy.SILENT_E: 1.0,
}
_SYLLABLE_BOUNDARY_MARKER_WEIGHTS: dict[SyllableBoundaryMarker, float] = {
    SyllableBoundaryMarker.NONE: 6.0,
    SyllableBoundaryMarker.APOSTROPHE: 1.0,
    SyllableBoundaryMarker.HYPHEN: 1.0,
}
_TONE_STRATEGY_WEIGHTS: dict[ToneMarkingStrategy, float] = {
    ToneMarkingStrategy.VOWEL_DIACRITIC: 3.0,
    ToneMarkingStrategy.POSTPOSED_DIGIT: 1.0,
    ToneMarkingStrategy.POSTPOSED_LETTER: 1.0,
    ToneMarkingStrategy.UNMARKED: 1.0,
}
# Independent of the vowel-length axis -- English doubles a consonant
# after a short vowel ("running" vs. "runing") without ever doubling a
# vowel letter for length, so this doesn't need `vowel_length_strategy ==
# DOUBLING` to make sense on its own.
_SHORT_VOWEL_DOUBLING_RATE = 0.25
# Independent of short_vowel_consonant_doubling above too -- this marks a
# phonemic length distinction the consonant already has on its own
# (Italian/Finnish/Japanese), not one derived from a neighboring vowel.
_CONSONANT_GEMINATION_RATE = 0.2


def _weighted_choice(rng: random.Random, weights: dict) -> object:
    options = list(weights)
    return rng.choices(options, weights=[weights[option] for option in options])[0]


def _synthesize_name(
    exotic_symbol_style: ExoticSymbolStyle,
    vowel_length_strategy: VowelLengthStrategy,
    short_vowel_consonant_doubling: bool,
    tone_strategy: ToneMarkingStrategy,
    syllable_boundary_marker: SyllableBoundaryMarker,
    consonant_gemination_marked: bool,
) -> str:
    """A human-readable label built from axis values directly, used
    whenever the actual combination doesn't (or no longer, after a force
    override) exactly match one of `_CATEGORIES`' named anchors -- so it
    never falsely claims to *be* a real system it only resembles."""
    parts = [exotic_symbol_style.value]
    if vowel_length_strategy != VowelLengthStrategy.NONE:
        parts.append(vowel_length_strategy.value)
    if short_vowel_consonant_doubling:
        parts.append("short-vowel-doubling")
    if tone_strategy != ToneMarkingStrategy.VOWEL_DIACRITIC:
        parts.append(tone_strategy.value)
    if syllable_boundary_marker != SyllableBoundaryMarker.NONE:
        parts.append(f"boundary={syllable_boundary_marker.name.lower()}")
    if consonant_gemination_marked:
        parts.append("gemination-marked")
    return " + ".join(parts)


def _roll_independent_axes(rng: random.Random) -> OrthographyCategory:
    """The unforced, no-reference/prompt-match fallback: each axis rolled
    on its own rather than picking one of `_CATEGORIES`' fixed bundles --
    see the module docstring for why."""
    exotic_symbol_style = _weighted_choice(rng, _EXOTIC_SYMBOL_STYLE_WEIGHTS)
    vowel_length_strategy = _weighted_choice(rng, _VOWEL_LENGTH_STRATEGY_WEIGHTS)
    short_vowel_consonant_doubling = rng.random() < _SHORT_VOWEL_DOUBLING_RATE
    tone_strategy = _weighted_choice(rng, _TONE_STRATEGY_WEIGHTS)
    syllable_boundary_marker = _weighted_choice(rng, _SYLLABLE_BOUNDARY_MARKER_WEIGHTS)
    consonant_gemination_marked = rng.random() < _CONSONANT_GEMINATION_RATE
    return OrthographyCategory(
        name=_synthesize_name(
            exotic_symbol_style,
            vowel_length_strategy,
            short_vowel_consonant_doubling,
            tone_strategy,
            syllable_boundary_marker,
            consonant_gemination_marked,
        ),
        description="Independently rolled per axis -- not necessarily matching any named anchor preset.",
        exotic_style=_EXOTIC_STYLE_TABLES[exotic_symbol_style],
        exotic_symbol_style=exotic_symbol_style,
        vowel_length_strategy=vowel_length_strategy,
        short_vowel_consonant_doubling=short_vowel_consonant_doubling,
        tone_strategy=tone_strategy,
        tone_markers=_TONE_MARKERS_BY_STRATEGY.get(tone_strategy, ()),
        syllable_boundary_marker=syllable_boundary_marker,
        consonant_gemination_marked=consonant_gemination_marked,
    )


def _apply_axis_overrides(category: OrthographyCategory, force: OrthographyForce) -> OrthographyCategory:
    """Overrides just the axes `force` actually sets (other than `style`,
    already resolved by the caller) on top of `category`, composing freely
    with whichever named anchor/roll/bias produced it."""
    updates: dict[str, object] = {}
    if force.exotic_symbol_style is not None and force.exotic_symbol_style != category.exotic_symbol_style:
        updates["exotic_symbol_style"] = force.exotic_symbol_style
        updates["exotic_style"] = _EXOTIC_STYLE_TABLES[force.exotic_symbol_style]
    if force.vowel_length_strategy is not None and force.vowel_length_strategy != category.vowel_length_strategy:
        updates["vowel_length_strategy"] = force.vowel_length_strategy
    if (
        force.short_vowel_consonant_doubling is not None
        and force.short_vowel_consonant_doubling != category.short_vowel_consonant_doubling
    ):
        updates["short_vowel_consonant_doubling"] = force.short_vowel_consonant_doubling
    if force.tone_strategy is not None and force.tone_strategy != category.tone_strategy:
        updates["tone_strategy"] = force.tone_strategy
        updates["tone_markers"] = _TONE_MARKERS_BY_STRATEGY.get(force.tone_strategy, ())
    if force.syllable_boundary_marker is not None and force.syllable_boundary_marker != category.syllable_boundary_marker:
        updates["syllable_boundary_marker"] = force.syllable_boundary_marker
    if (
        force.consonant_gemination_marked is not None
        and force.consonant_gemination_marked != category.consonant_gemination_marked
    ):
        updates["consonant_gemination_marked"] = force.consonant_gemination_marked
    if not updates:
        return category
    merged = category.model_copy(update=updates)
    name = _synthesize_name(
        merged.exotic_symbol_style,
        merged.vowel_length_strategy,
        merged.short_vowel_consonant_doubling,
        merged.tone_strategy,
        merged.syllable_boundary_marker,
        merged.consonant_gemination_marked,
    )
    description = f"Composed from '{category.name}' with a forced override on: {', '.join(sorted(updates))}."
    return merged.model_copy(update={"name": name, "description": description})


def _category_from_scheme(scheme: RomanizationScheme) -> OrthographyCategory:
    """Reconstructs the exact `OrthographyCategory` that built `scheme`,
    directly from the axis fields it stores -- never an approximation,
    since a scheme already carries every axis (`tone_strategy`/
    `tone_markers`/`vowel_length_strategy`/`short_vowel_consonant_doubling`/
    `exotic_symbol_style`/`syllable_boundary_marker`/
    `consonant_gemination_marked`) rather than just a name to look up."""
    return OrthographyCategory(
        name=scheme.category_name,
        description="Reconstructed from a RomanizationScheme's own stored axes.",
        exotic_style=_EXOTIC_STYLE_TABLES[scheme.exotic_symbol_style],
        exotic_symbol_style=scheme.exotic_symbol_style,
        vowel_length_strategy=scheme.vowel_length_strategy,
        short_vowel_consonant_doubling=scheme.short_vowel_consonant_doubling,
        tone_strategy=scheme.tone_strategy,
        tone_markers=scheme.tone_markers,
        syllable_boundary_marker=scheme.syllable_boundary_marker,
        consonant_gemination_marked=scheme.consonant_gemination_marked,
    )


def _reference_orthography(contact_languages: tuple[str, ...]) -> dict[str, list[RomanizationRule]]:
    """``{ipa_symbol: [rule, ...]}`` -- a symbol may have more than one
    variant rule (e.g. Dutch's open/closed vowel-length pair, or a
    specific-segment-conditioned pair like Mandarin's ü/u after j/q/x/y).
    First matched profile wins for a given (ipa, following, preceding,
    syllable) combination if more than one contact language defines it."""
    by_symbol: dict[str, list[RomanizationRule]] = {}
    for profile in match_profiles(contact_languages):
        for rule in profile.orthography:
            existing = by_symbol.setdefault(rule.ipa, [])
            condition = (rule.following, rule.preceding, rule.syllable)
            if not any((r.following, r.preceding, r.syllable) == condition for r in existing):
                existing.append(rule)
    return by_symbol


def _short_counterpart(vowel: Vowel, inventory: PhonemeInventory) -> Vowel | None:
    """The vowel in `inventory` sharing `vowel`'s height/backness/rounding
    but not its length -- the phoneme a length-marking rule for `vowel`
    needs to know the "base" spelling of."""
    for other in inventory.vowels:
        if not other.long and other.height == vowel.height and other.backness == vowel.backness and other.rounded == vowel.rounded:
            return other
    return None


def _vowel_length_tags(inventory: PhonemeInventory) -> tuple[tuple[str, str], ...]:
    """``(symbol, "long"|"short")`` pairs for ``RomanizationScheme.vowel_length``
    -- but *only* for a vowel genuinely paired with a same-quality long/
    short counterpart in this inventory (``Vowel.long`` true on one side,
    false on the other, same height/backness/rounding), not every vowel's
    own bare ``.long`` flag. This matters: several reference languages
    (Dutch's own hand-curated "y" for its /y:/, for instance) mark length
    entirely through spelling convention -- a syllable-conditioned
    ``RomanizationRule`` pair, not the ``.long`` feature at all -- so a
    plain "tag every vowel by its own `.long` value" would mislabel every
    one of their vowels as "short" and spuriously trigger
    ``short_vowel_consonant_doubling`` after all of them, not just the
    ones a category's own generic length contrast actually applies to."""
    tags: list[tuple[str, str]] = []
    for vowel in inventory.vowels:
        if not vowel.long:
            continue
        short = _short_counterpart(vowel, inventory)
        if short is None:
            continue
        tags.append((vowel.ipa, "long"))
        tags.append((short.ipa, "short"))
    return tuple(tags)


def _scheme_context(
    inventory: PhonemeInventory,
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...], tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    vowel_backness = tuple((v.ipa, v.backness.value) for v in inventory.vowels)
    return (
        inventory.vowel_symbols(),
        sonority.legal_onset_pairs(inventory.consonants),
        vowel_backness,
        _vowel_length_tags(inventory),
    )


_MACRON_LETTERS = {"a": "ā", "e": "ē", "i": "ī", "o": "ō", "u": "ū"}


def _generate_length_rules(category: OrthographyCategory, inventory: PhonemeInventory) -> list[RomanizationRule]:
    """Vowel-length rules for every long vowel in `inventory` that has a
    matching short counterpart -- generalizes the exact syllable-
    conditioned doubling pattern Dutch's own hand-curated `vuur`/`vuren`
    rules already use (real macron/colon conventions mark length
    everywhere, not just in a closed syllable, unlike doubling, which
    only reads sensibly there) to any category/inventory pair. A long
    vowel with no short counterpart in this particular inventory falls
    through untouched -- the caller's flat `exotic_style` fallback (which
    already has an unconditioned entry for every long-vowel symbol) covers
    it."""
    if category.vowel_length_strategy == VowelLengthStrategy.NONE:
        return []
    rules: list[RomanizationRule] = []
    for vowel in inventory.vowels:
        if not vowel.long:
            continue
        short = _short_counterpart(vowel, inventory)
        if short is None:
            continue
        base_letter = category.exotic_style.get(short.ipa, short.ipa)
        if category.vowel_length_strategy == VowelLengthStrategy.DOUBLING:
            rules.append(RomanizationRule(ipa=vowel.ipa, latin=base_letter * 2, syllable=("syllable_closed",)))
            rules.append(RomanizationRule(ipa=vowel.ipa, latin=base_letter, syllable=("syllable_open",)))
        elif category.vowel_length_strategy == VowelLengthStrategy.MACRON:
            rules.append(RomanizationRule(ipa=vowel.ipa, latin=_MACRON_LETTERS.get(base_letter, base_letter + "̄")))
        elif category.vowel_length_strategy == VowelLengthStrategy.COLON:
            rules.append(RomanizationRule(ipa=vowel.ipa, latin=base_letter + ":"))
        elif category.vowel_length_strategy == VowelLengthStrategy.SILENT_E:
            # Unconditioned: the same plain letter in both syllable types --
            # the trailing "e" itself comes from RomanizationScheme.apply()'s
            # own deferred-marker buffering (see its docstring), not from a
            # generated rule, since it lands after the coda, not on this
            # vowel's own token.
            rules.append(RomanizationRule(ipa=vowel.ipa, latin=base_letter))
    return rules


def _generate_doubling_rules(category: OrthographyCategory, inventory: PhonemeInventory) -> list[RomanizationRule]:
    """A ``preceding=("short_vowel",)``-conditioned doubled-letter rule per
    consonant, when the category marks a short vowel by doubling the
    *following* onset consonant instead (Dutch "zitten" vs "zaten",
    German "Bett") -- paired with the plain unconditioned rule for every
    other position, the same "conditioned variant + unconditioned
    fallback" pair ``_generate_length_rules``'s ``DOUBLING`` branch
    returns, so a consonant not preceded by a short vowel still has a
    rule to match instead of falling through to a raw, unmapped symbol.
    Skipped for a consonant whose own rendering isn't a single ASCII
    letter -- doubling a digraph ("ch" -> "chch") reads as a typo, not a
    spelling convention, so this only fires for the plain, single-letter
    consonants the doubling convention is actually attested for."""
    if not category.short_vowel_consonant_doubling:
        return []
    rules: list[RomanizationRule] = []
    for consonant in inventory.consonants:
        base_letter = category.exotic_style.get(consonant.ipa, consonant.ipa)
        if len(base_letter) != 1:
            continue
        rules.append(RomanizationRule(ipa=consonant.ipa, latin=base_letter * 2, preceding=("short_vowel",)))
        rules.append(RomanizationRule(ipa=consonant.ipa, latin=base_letter))
    return rules


def _consonant_short_counterpart(consonant: Consonant, inventory: PhonemeInventory) -> Consonant | None:
    """The consonant in `inventory` sharing `consonant`'s place/manner/
    voicing but not its length -- the same role `_short_counterpart`
    plays for vowels, just matched on place/manner/voiced instead of
    height/backness/rounding."""
    for other in inventory.consonants:
        if not other.long and other.place == consonant.place and other.manner == consonant.manner and other.voiced == consonant.voiced:
            return other
    return None


def _generate_gemination_rules(category: OrthographyCategory, inventory: PhonemeInventory) -> list[RomanizationRule]:
    """One unconditioned doubled-letter rule per phonemically long/
    geminate consonant with a resolved short counterpart, when the
    category marks gemination (Italian "sono" vs. "sonno"). Unlike
    `_generate_doubling_rules` above (which derives doubling from a
    *neighboring* short vowel), this doubling is unconditioned -- the
    geminate is its own distinct `ipa` symbol, so no `preceding`/
    `syllable` condition is needed, and unlike vowel length there's no
    syllable-position dependency either (a geminate is long everywhere,
    not just in a closed syllable). A long consonant with no short
    counterpart in this inventory falls through untouched -- the
    caller's flat `exotic_style` fallback (which already has an
    unconditioned single-letter entry for every geminate symbol) covers
    it, same as an unpaired long vowel does."""
    if not category.consonant_gemination_marked:
        return []
    rules: list[RomanizationRule] = []
    for consonant in inventory.consonants:
        if not consonant.long:
            continue
        short = _consonant_short_counterpart(consonant, inventory)
        if short is None:
            continue
        base_letter = category.exotic_style.get(short.ipa, short.ipa)
        rules.append(RomanizationRule(ipa=consonant.ipa, latin=base_letter * 2))
    return rules


def _structural_rules(category: OrthographyCategory, inventory: PhonemeInventory) -> dict[str, list[RomanizationRule]]:
    """`{ipa_symbol: [rule, ...]}` for this category's generated
    length/doubling rules against this specific inventory -- the middle
    tier of `_rules_for_symbol`'s priority, between a matched reference
    profile's own deviation and the category's flat fallback letter."""
    by_symbol: dict[str, list[RomanizationRule]] = {}
    for rule in (
        *_generate_length_rules(category, inventory),
        *_generate_doubling_rules(category, inventory),
        *_generate_gemination_rules(category, inventory),
    ):
        by_symbol.setdefault(rule.ipa, []).append(rule)
    return by_symbol


def _rules_for_symbol(
    symbol: str,
    reference: dict[str, list[RomanizationRule]],
    structural: dict[str, list[RomanizationRule]],
    category: OrthographyCategory,
    reference_profiles: tuple[ReferenceLanguageProfile, ...],
    rng: random.Random,
) -> list[RomanizationRule]:
    """The rule(s) a symbol with no old rule to inherit gets, in priority
    order: a matched reference-language deviation (probabilistic, existing
    behavior -- e.g. Dutch's own `vuur`/`vuren` pair) > a category-
    generated structural rule (length/doubling, also new but data-driven,
    so a matched reference profile's own curated rules always still win)
    > a matched reference profile's own *named-anchor* exotic-symbol table
    (e.g. a Dutch-biased language still leans digraph, not Slavic-diacritic,
    for a symbol Dutch's own profile doesn't curate a specific rule for --
    see romanization_gen.py's module docstring) > the scheme's own flat
    fallback letter, for a symbol no active contact language has any real
    convention for at all."""
    variants = reference.get(symbol)
    if variants and rng.random() < _REFERENCE_ORTHOGRAPHY_WEIGHT:
        return list(variants)
    generated = structural.get(symbol)
    if generated:
        return list(generated)
    contact_tables = [
        _CATEGORIES_BY_NAME[p.orthography_category].exotic_style
        for p in reference_profiles
        if p.orthography_category and p.orthography_category in _CATEGORIES_BY_NAME
    ]
    if contact_tables:
        table = contact_tables[0] if len(contact_tables) == 1 else rng.choice(contact_tables)
        return [RomanizationRule(ipa=symbol, latin=table.get(symbol, symbol))]
    return [RomanizationRule(ipa=symbol, latin=category.exotic_style.get(symbol, symbol))]


def _resolve_category(
    rng: random.Random,
    reference_profiles: tuple[ReferenceLanguageProfile, ...],
    requested_style_name: str,
    force: OrthographyForce,
    fallback_factory: Callable[[], OrthographyCategory],
) -> OrthographyCategory:
    """The shared category-resolution logic both `generate_romanization`
    and `evolve_romanization` use. `force.style` wins outright when set --
    an exact named anchor, no `rng` consumed at all, `ValueError` if the
    name isn't real (forcing is the "guarantee, fail loudly if misspelled"
    channel, unlike `contact_languages`' silent best-effort matching).
    Otherwise, each of a matched reference profile's own declared
    `orthography_category` (in order) and then `requested_style_name` (the
    prompt-classifier hint) gets one probabilistic shot at winning, same
    spirit as `_REFERENCE_ORTHOGRAPHY_WEIGHT` elsewhere in this module;
    nothing winning calls `fallback_factory()` -- a *callable*, not a
    precomputed value, so a caller that doesn't need it (a force or a bias
    already won) never burns its `rng` draws, keeping this project's
    RNG-consumption order stable regardless of which path wins. Any other
    field set on `force` then overrides just that one axis on top of
    whatever was resolved, always."""
    if force.style is not None:
        if force.style not in _CATEGORIES_BY_NAME:
            raise ValueError(f"Unknown orthography style {force.style!r}; valid names: {sorted(_CATEGORIES_BY_NAME)}")
        base = _CATEGORIES_BY_NAME[force.style]
    else:
        candidate_names = [p.orthography_category for p in reference_profiles if p.orthography_category]
        if requested_style_name:
            candidate_names.append(requested_style_name)
        base = None
        for candidate_name in candidate_names:
            if candidate_name and rng.random() < _REFERENCE_ORTHOGRAPHY_WEIGHT:
                candidate = _CATEGORIES_BY_NAME.get(candidate_name)
                if candidate is not None:
                    base = candidate
                    break
        if base is None:
            base = fallback_factory()
    return _apply_axis_overrides(base, force)


def generate_romanization(
    rng: random.Random,
    inventory: PhonemeInventory,
    contact_languages: tuple[str, ...] = (),
    requested_orthography_style: str = "",
    forced_orthography: OrthographyForce = OrthographyForce(),
) -> RomanizationScheme:
    reference = _reference_orthography(contact_languages)
    reference_profiles = match_profiles(contact_languages)
    category = _resolve_category(
        rng, reference_profiles, requested_orthography_style, forced_orthography,
        fallback_factory=lambda: _roll_independent_axes(rng),
    )
    structural = _structural_rules(category, inventory)
    rules: list[RomanizationRule] = []
    for symbol in inventory.all_symbols():
        rules.extend(_rules_for_symbol(symbol, reference, structural, category, reference_profiles, rng))
    vowel_symbols, legal_onset_clusters, vowel_backness, vowel_length = _scheme_context(inventory)
    return RomanizationScheme(
        rules=tuple(rules),
        vowel_symbols=vowel_symbols,
        legal_onset_clusters=legal_onset_clusters,
        vowel_backness=vowel_backness,
        vowel_length=vowel_length,
        category_name=category.name,
        tone_strategy=category.tone_strategy,
        tone_markers=category.tone_markers,
        vowel_length_strategy=category.vowel_length_strategy,
        short_vowel_consonant_doubling=category.short_vowel_consonant_doubling,
        exotic_symbol_style=category.exotic_symbol_style,
        syllable_boundary_marker=category.syllable_boundary_marker,
        consonant_gemination_marked=category.consonant_gemination_marked,
    )


def _apply_orthography_drift(text: str, rng: random.Random, rate: float) -> str:
    """Orthography-only drift: spelling simplification independent of
    pronunciation. Two illustrative, not exhaustive, moves: diacritics
    dropping from writing over time (like "café" -> "cafe" in casual
    English spelling) and the ejective apostrophe mark being dropped from
    spelling even though the sound itself stays ejective. Each mark rolls
    independently."""
    if rate <= 0:
        return text
    decomposed = unicodedata.normalize("NFD", text)
    kept = [ch for ch in decomposed if not (unicodedata.combining(ch) and rng.random() < rate)]
    text = unicodedata.normalize("NFC", "".join(kept))
    return "".join(ch for ch in text if not (ch in _EJECTIVE_SPELLING_MARKS and rng.random() < rate))


def evolve_romanization(
    base_scheme: RomanizationScheme,
    new_inventory: PhonemeInventory,
    rng: random.Random,
    contact_languages: tuple[str, ...] = (),
    reform_rate: float = 0.0,
    drift_rate: float = 0.0,
    forced_orthography: OrthographyForce = OrthographyForce(),
) -> RomanizationScheme:
    """Orthographic inertia for sound-changed languages, decided per
    *symbol* rather than per word -- so every word sharing a symbol gets
    the exact same spelling for it, the way a real spelling convention
    (or a real spelling reform) applies uniformly across the vocabulary,
    not as an independent per-word coin flip.

    For each symbol still present in both the old scheme and the new
    inventory: with probability ``reform_rate`` it's *reformed* (the old
    rule(s) are dropped and fresh one(s) generated, same as for a genuinely
    new symbol -- a symbol with multiple old context-conditioned rules is
    reformed or kept as a whole group, never split); otherwise it's
    *frozen* (the inherited rule(s) are kept verbatim, even if the
    underlying sound changed -- why real orthographies end up with
    "silent" letters). ``reform_rate`` should be low by default so freeze
    dominates at short time depths -- real spelling reforms are rare,
    discrete events (Dutch's own history: 1804, 1863, 1946/47, 1996, 2005),
    not a continuous process.

    ``drift_rate`` then independently rolls, per *rule* in the resulting
    scheme, whether ``_apply_orthography_drift`` simplifies its grapheme --
    again decided once per symbol, not per word. Reform and drift run as
    two separate passes (not interleaved per symbol) specifically so that
    varying one rate alone, at a fixed seed, doesn't perturb the rng draws
    the other pass consumes -- each stays independently comparable, same
    reasoning as ``sound_change.py``'s same-seed-monotonicity tests.

    ``forced_orthography`` behaves exactly as it does in
    ``generate_romanization``, except reference-profile/prompt bias is
    deliberately *not* consulted here (only ``forced_orthography.style``
    can move the category away from what it already was): this keeps a
    language's orthographic family from randomly drifting on every
    evolution run just because ``contact_languages`` happens to be set,
    matching the "carried forward, not re-rolled" behavior described
    above -- a force is still honored, as a deliberate, user-triggered
    reform.
    """
    old_by_ipa: dict[str, list[RomanizationRule]] = {}
    for rule in base_scheme.rules:
        old_by_ipa.setdefault(rule.ipa, []).append(rule)
    category = _resolve_category(
        rng, (), "", forced_orthography,
        fallback_factory=lambda: _category_from_scheme(base_scheme),
    )
    reference = _reference_orthography(contact_languages)
    # Only the per-symbol exotic-table fallback consults contact_languages
    # here, not the whole-scheme category (see the docstring above) -- a
    # newly-reformed symbol with no curated rule of its own still leans on
    # its lineage's own conventions rather than a fully generic table.
    reference_profiles = match_profiles(contact_languages)
    structural = _structural_rules(category, new_inventory)

    rules: list[RomanizationRule] = []
    for symbol in new_inventory.all_symbols():
        keep_old = symbol in old_by_ipa and rng.random() >= reform_rate
        if keep_old:
            rules.extend(old_by_ipa[symbol])
        else:
            rules.extend(_rules_for_symbol(symbol, reference, structural, category, reference_profiles, rng))

    rules = [
        RomanizationRule(
            ipa=rule.ipa,
            latin=_apply_orthography_drift(rule.latin, rng, drift_rate),
            following=rule.following,
            preceding=rule.preceding,
            syllable=rule.syllable,
        )
        for rule in rules
    ]
    vowel_symbols, legal_onset_clusters, vowel_backness, vowel_length = _scheme_context(new_inventory)
    return RomanizationScheme(
        rules=tuple(rules),
        vowel_symbols=vowel_symbols,
        legal_onset_clusters=legal_onset_clusters,
        vowel_backness=vowel_backness,
        vowel_length=vowel_length,
        category_name=category.name,
        tone_strategy=category.tone_strategy,
        tone_markers=category.tone_markers,
        vowel_length_strategy=category.vowel_length_strategy,
        short_vowel_consonant_doubling=category.short_vowel_consonant_doubling,
        exotic_symbol_style=category.exotic_symbol_style,
        syllable_boundary_marker=category.syllable_boundary_marker,
        consonant_gemination_marked=category.consonant_gemination_marked,
    )
