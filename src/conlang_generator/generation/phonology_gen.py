"""Seeded phoneme-inventory generation.

One uniform mechanism drives inventory membership: every consonant/vowel in
the candidate pool gets an independent inclusion draw at
``rng.random() < prevalence`` (see ``Consonant.prevalence``/
``Vowel.prevalence``), except symbols with a trait link (ejectives,
the uvular series, harshness-tagged fricatives/affricates/nasal), which use
``biased_probability(prevalence, trait_strength)`` instead -- same helper
used everywhere else trait strength scales a probability. A handful of
real, illustrative typological tendencies ride on top of that:

- an (almost) universal implicational rule: a voiced stop/affricate is only
  drawn once its voiceless counterpart is present -- guaranteed by
  construction, not modeled probabilistically.
- ``traits.altitude`` boosts the odds of the whole ejective series, per
  Everett (2013)'s cross-linguistic correlation between ejectives and
  high-altitude regions.
- ``traits.isolation`` boosts the whole uvular series (rarer places of
  articulation retained by more idiosyncratic/isolated inventories) and,
  modestly, vowel harmony (elaborated morphophonological systems).
- ``traits.aesthetic_harshness`` re-weights harsh- vs. soft-leaning
  fricatives, the affricate pair, and the velar nasal -- a "vibe" knob
  independent of the tendencies above.

Phonotactics (onset/coda cluster legality) are derived from the sonority
sequencing principle (``generation/sonority.py``) rather than hand-listed,
so they generalize automatically as the phoneme pool grows -- no longer
tied to a specific fixed symbol set. Coda typology (none / sonorant-only /
unrestricted) and vowel harmony are picked per generated language.

``spec.force_high_altitude``/``force_isolated``/``force_tonal`` bypass the
matching probability entirely (the deterministic testing/override channel
-- see ``core.spec.GenerationSpec``).

Not literally exhaustive IPA (diacritics, secondary articulations, and most
non-pulmonic consonants beyond a few illustrative clicks/implosives stay
out of scope). Prevalence values are illustrative approximations informed
by general typological consensus (e.g. Maddieson's cross-linguistic
surveys), not precise statistics.
"""

from __future__ import annotations

import random

from conlang_generator.core.phonology import (
    Consonant,
    Manner,
    Place,
    PhonemeInventory,
    SyllableStructure,
    ToneLevel,
    ToneSystem,
    Vowel,
    VowelBackness,
    VowelHeight,
    WordAccentSystem,
)
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import ipa_tokenizer, sonority, word_accent_gen
from conlang_generator.generation.reference_languages import ReferenceLanguageProfile, match_profiles
from conlang_generator.generation.trait_bias import biased_probability

# -- Stops and affricates: voiceless drawn first, voiced only if the
# voiceless counterpart was drawn (the implicational universal). --
_p = Consonant(ipa="p", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, prevalence=0.92)
_b = Consonant(ipa="b", place=Place.BILABIAL, manner=Manner.STOP, voiced=True, prevalence=0.65)
_t = Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, prevalence=0.92)
_d = Consonant(ipa="d", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=True, prevalence=0.65)
_k = Consonant(ipa="k", place=Place.VELAR, manner=Manner.STOP, voiced=False, prevalence=0.90)
_g = Consonant(ipa="g", place=Place.VELAR, manner=Manner.STOP, voiced=True, prevalence=0.55)
_tt = Consonant(ipa="ʈ", place=Place.RETROFLEX, manner=Manner.STOP, voiced=False, prevalence=0.12)
_dd = Consonant(ipa="ɖ", place=Place.RETROFLEX, manner=Manner.STOP, voiced=True, prevalence=0.08)
_c = Consonant(ipa="c", place=Place.PALATAL, manner=Manner.STOP, voiced=False, prevalence=0.15)
_ff = Consonant(ipa="ɟ", place=Place.PALATAL, manner=Manner.STOP, voiced=True, prevalence=0.10)
_tsh = Consonant(ipa="tʃ", place=Place.POSTALVEOLAR, manner=Manner.AFFRICATE, voiced=False, prevalence=0.40)
_dzh = Consonant(ipa="dʒ", place=Place.POSTALVEOLAR, manner=Manner.AFFRICATE, voiced=True, prevalence=0.28)
# Real Hungarian/Polish "c"/"dz" -- a plain alveolar affricate, common
# enough cross-linguistically (also German/Italian "z", Japanese "tsu")
# to sit in the unconditional pairs list alongside tʃ/dʒ rather than a
# gated group, the same "ordinary enough to always be in the draw pool"
# status every other member here already has.
_ts = Consonant(ipa="ts", place=Place.ALVEOLAR, manner=Manner.AFFRICATE, voiced=False, prevalence=0.30)
_dz = Consonant(ipa="dz", place=Place.ALVEOLAR, manner=Manner.AFFRICATE, voiced=True, prevalence=0.18)

_STOP_AND_AFFRICATE_PAIRS: tuple[tuple[Consonant, Consonant], ...] = (
    (_p, _b), (_t, _d), (_k, _g), (_tt, _dd), (_c, _ff), (_tsh, _dzh), (_ts, _dz),
)

_GLOTTAL_STOP = Consonant(ipa="ʔ", place=Place.GLOTTAL, manner=Manner.STOP, voiced=False, prevalence=0.60)

_EJECTIVES = (
    Consonant(ipa="pʼ", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, ejective=True, prevalence=0.40),
    Consonant(ipa="tʼ", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, ejective=True, prevalence=0.40),
    Consonant(ipa="kʼ", place=Place.VELAR, manner=Manner.STOP, voiced=False, ejective=True, prevalence=0.40),
)
_EJECTIVE_GROUP_BASE_RATE = 0.08

_UVULAR_GROUP = (
    Consonant(ipa="q", place=Place.UVULAR, manner=Manner.STOP, voiced=False, prevalence=0.15),
    Consonant(ipa="ɢ", place=Place.UVULAR, manner=Manner.STOP, voiced=True, prevalence=0.08),
    Consonant(ipa="χ", place=Place.UVULAR, manner=Manner.FRICATIVE, voiced=False, prevalence=0.14),
    Consonant(ipa="ʁ", place=Place.UVULAR, manner=Manner.FRICATIVE, voiced=True, prevalence=0.10),
)
_UVULAR_GROUP_BASE_RATE = 0.12

# Aspiration (Hindi, Thai, Ancient Greek, Korean's three-way stop contrast)
# and pharyngealization/"emphatics" (Arabic's ط ص ض ظ) -- secondary
# articulations, no existing graded trait obviously links to either, so
# (like the exotic click/implosive pool) these are pure base-rate +
# reference-bias groups.
_ASPIRATED_GROUP = (
    Consonant(ipa="pʰ", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, aspirated=True, prevalence=0.35),
    Consonant(ipa="tʰ", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, aspirated=True, prevalence=0.35),
    Consonant(ipa="kʰ", place=Place.VELAR, manner=Manner.STOP, voiced=False, aspirated=True, prevalence=0.35),
)
_ASPIRATED_GROUP_BASE_RATE = 0.10

_PHARYNGEALIZED_GROUP = (
    Consonant(ipa="tˤ", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, pharyngealized=True, prevalence=0.10),
    Consonant(ipa="dˤ", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=True, pharyngealized=True, prevalence=0.08),
    Consonant(ipa="sˤ", place=Place.ALVEOLAR, manner=Manner.FRICATIVE, voiced=False, pharyngealized=True, prevalence=0.08),
    Consonant(ipa="ðˤ", place=Place.DENTAL, manner=Manner.FRICATIVE, voiced=True, pharyngealized=True, prevalence=0.05),
)
_PHARYNGEALIZED_GROUP_BASE_RATE = 0.06

# Phonemic consonant length (Italian "sono"/"sonno", Finnish "kukka"/"kuka",
# Japanese sokuon) and palatalization (Russian тʲ/дʲ/etc., spelled with a
# trailing letter -- ь/ъ in Cyrillic, an apostrophe or "y" in Latin
# transliteration) -- same "no existing graded trait obviously links to
# either" reasoning as aspiration/pharyngealization above, so both are
# pure base-rate + reference-bias groups too. Long consonants reuse the
# same "ː" length-mark character `_VOWEL_EXTRAS` already uses for long
# vowels, each paired with a high-prevalence plain counterpart already in
# this pool (k/t/n/s/l/p) so `romanization_gen.py`'s pairing usually
# resolves -- see its own module for that side.
_GEMINATE_GROUP = (
    Consonant(ipa="kː", place=Place.VELAR, manner=Manner.STOP, voiced=False, long=True, prevalence=0.12),
    Consonant(ipa="tː", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, long=True, prevalence=0.12),
    Consonant(ipa="pː", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, long=True, prevalence=0.10),
    Consonant(ipa="sː", place=Place.ALVEOLAR, manner=Manner.FRICATIVE, voiced=False, long=True, prevalence=0.10),
    Consonant(ipa="nː", place=Place.ALVEOLAR, manner=Manner.NASAL, voiced=True, long=True, prevalence=0.10),
    Consonant(ipa="lː", place=Place.ALVEOLAR, manner=Manner.LATERAL_APPROXIMANT, voiced=True, long=True, prevalence=0.08),
)
_GEMINATE_GROUP_BASE_RATE = 0.10

_PALATALIZED_GROUP = (
    Consonant(ipa="tʲ", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, palatalized=True, prevalence=0.10),
    Consonant(ipa="dʲ", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=True, palatalized=True, prevalence=0.08),
    Consonant(ipa="nʲ", place=Place.ALVEOLAR, manner=Manner.NASAL, voiced=True, palatalized=True, prevalence=0.08),
    Consonant(ipa="lʲ", place=Place.ALVEOLAR, manner=Manner.LATERAL_APPROXIMANT, voiced=True, palatalized=True, prevalence=0.08),
    # Real Russian contrasts palatalized/plain across nearly its whole
    # consonant inventory, not just the four coronals above -- these
    # extend the same shared group (more members, same mechanism) rather
    # than adding Russian-specific selection code, so any future language
    # with a comparably pervasive palatalization system benefits too.
    Consonant(ipa="pʲ", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, palatalized=True, prevalence=0.06),
    Consonant(ipa="bʲ", place=Place.BILABIAL, manner=Manner.STOP, voiced=True, palatalized=True, prevalence=0.06),
    Consonant(ipa="mʲ", place=Place.BILABIAL, manner=Manner.NASAL, voiced=True, palatalized=True, prevalence=0.06),
    Consonant(ipa="fʲ", place=Place.LABIODENTAL, manner=Manner.FRICATIVE, voiced=False, palatalized=True, prevalence=0.04),
    Consonant(ipa="vʲ", place=Place.LABIODENTAL, manner=Manner.FRICATIVE, voiced=True, palatalized=True, prevalence=0.05),
    Consonant(ipa="sʲ", place=Place.ALVEOLAR, manner=Manner.FRICATIVE, voiced=False, palatalized=True, prevalence=0.06),
    Consonant(ipa="zʲ", place=Place.ALVEOLAR, manner=Manner.FRICATIVE, voiced=True, palatalized=True, prevalence=0.04),
    Consonant(ipa="kʲ", place=Place.VELAR, manner=Manner.STOP, voiced=False, palatalized=True, prevalence=0.06),
    Consonant(ipa="xʲ", place=Place.VELAR, manner=Manner.FRICATIVE, voiced=False, palatalized=True, prevalence=0.03),
    Consonant(ipa="rʲ", place=Place.ALVEOLAR, manner=Manner.TRILL, voiced=True, palatalized=True, prevalence=0.05),
)
_PALATALIZED_GROUP_BASE_RATE = 0.08

# Alveolo-palatal affricates (real Polish "ć"/"dź", Mandarin "j"/"q"-ish,
# Japanese's own affricate before /i/) -- typologically rarer than the
# plain alveolar `ts`/`dz` pair above (concentrated in a handful of
# language families rather than broadly common), so this stays a gated
# group, the same "marked enough to need its own base rate" status
# aspiration/pharyngealization/palatalization already have, rather than
# joining the unconditional pairs list.
_ALVEOLO_PALATAL_GROUP = (
    Consonant(ipa="tɕ", place=Place.PALATAL, manner=Manner.AFFRICATE, voiced=False, prevalence=0.10),
    Consonant(ipa="dʑ", place=Place.PALATAL, manner=Manner.AFFRICATE, voiced=True, prevalence=0.07),
)
_ALVEOLO_PALATAL_GROUP_BASE_RATE = 0.08

# Murmured/breathy voice (Hindi/Bengali's 4th stop series alongside plain
# voiceless/voiceless-aspirated/plain-voiced) -- same "no obvious trait
# correlate" reasoning as the groups above.
_BREATHY_GROUP = (
    Consonant(ipa="bʱ", place=Place.BILABIAL, manner=Manner.STOP, voiced=True, breathy=True, prevalence=0.30),
    Consonant(ipa="dʱ", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=True, breathy=True, prevalence=0.30),
    Consonant(ipa="ɡʱ", place=Place.VELAR, manner=Manner.STOP, voiced=True, breathy=True, prevalence=0.30),
)
_BREATHY_GROUP_BASE_RATE = 0.12

# Pre-aspiration (Icelandic-style /ʰp ʰt ʰk/) -- a genuinely different
# typological choice from post-aspiration (`_ASPIRATED_GROUP` above), not
# a variant of it, so it's gated independently: a language can roll
# post-aspiration, pre-aspiration, both, or neither. Reuses `aspirated`
# rather than a new direction flag -- the only existing consumer of that
# flag (kinship-reduplication's marked-sound exclusion) treats it as
# "has an aspiration-related mark," direction-agnostically, and nothing
# else reads it.
_PRE_ASPIRATED_GROUP = (
    Consonant(ipa="ʰp", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, aspirated=True, prevalence=0.30),
    Consonant(ipa="ʰt", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, aspirated=True, prevalence=0.30),
    Consonant(ipa="ʰk", place=Place.VELAR, manner=Manner.STOP, voiced=False, aspirated=True, prevalence=0.30),
)
_PRE_ASPIRATED_GROUP_BASE_RATE = 0.08  # rarer cross-linguistically than post-aspiration

_m = Consonant(ipa="m", place=Place.BILABIAL, manner=Manner.NASAL, voiced=True, prevalence=0.95)
_n = Consonant(ipa="n", place=Place.ALVEOLAR, manner=Manner.NASAL, voiced=True, prevalence=0.95)
_ng = Consonant(ipa="ŋ", place=Place.VELAR, manner=Manner.NASAL, voiced=True, prevalence=0.55)
_NASAL_POOL = (
    _m, _n, _ng,
    Consonant(ipa="ɳ", place=Place.RETROFLEX, manner=Manner.NASAL, voiced=True, prevalence=0.08),
    Consonant(ipa="ɲ", place=Place.PALATAL, manner=Manner.NASAL, voiced=True, prevalence=0.15),
)

_FRICATIVE_POOL = (
    Consonant(ipa="s", place=Place.ALVEOLAR, manner=Manner.FRICATIVE, voiced=False, prevalence=0.80),
    Consonant(ipa="ʃ", place=Place.POSTALVEOLAR, manner=Manner.FRICATIVE, voiced=False, prevalence=0.35),
    Consonant(ipa="x", place=Place.VELAR, manner=Manner.FRICATIVE, voiced=False, prevalence=0.30),
    Consonant(ipa="ɣ", place=Place.VELAR, manner=Manner.FRICATIVE, voiced=True, prevalence=0.18),
    Consonant(ipa="ʒ", place=Place.POSTALVEOLAR, manner=Manner.FRICATIVE, voiced=True, prevalence=0.20),
    Consonant(ipa="ʂ", place=Place.RETROFLEX, manner=Manner.FRICATIVE, voiced=False, prevalence=0.10),
    Consonant(ipa="ʐ", place=Place.RETROFLEX, manner=Manner.FRICATIVE, voiced=True, prevalence=0.06),
    Consonant(ipa="ɬ", place=Place.ALVEOLAR, manner=Manner.LATERAL_FRICATIVE, voiced=False, prevalence=0.08),
    Consonant(ipa="ħ", place=Place.PHARYNGEAL, manner=Manner.FRICATIVE, voiced=False, prevalence=0.05),
    Consonant(ipa="ʕ", place=Place.PHARYNGEAL, manner=Manner.FRICATIVE, voiced=True, prevalence=0.05),
    Consonant(ipa="f", place=Place.LABIODENTAL, manner=Manner.FRICATIVE, voiced=False, prevalence=0.45),
    Consonant(ipa="h", place=Place.GLOTTAL, manner=Manner.FRICATIVE, voiced=False, prevalence=0.55),
    Consonant(ipa="z", place=Place.ALVEOLAR, manner=Manner.FRICATIVE, voiced=True, prevalence=0.28),
    Consonant(ipa="v", place=Place.LABIODENTAL, manner=Manner.FRICATIVE, voiced=True, prevalence=0.22),
    Consonant(ipa="θ", place=Place.DENTAL, manner=Manner.FRICATIVE, voiced=False, prevalence=0.10),
    Consonant(ipa="ð", place=Place.DENTAL, manner=Manner.FRICATIVE, voiced=True, prevalence=0.10),
    Consonant(ipa="ç", place=Place.PALATAL, manner=Manner.FRICATIVE, voiced=False, prevalence=0.08),
    Consonant(ipa="ʝ", place=Place.PALATAL, manner=Manner.FRICATIVE, voiced=True, prevalence=0.06),
)
# "Vibe" tagging for aesthetic_harshness -- illustrative sound symbolism, not
# a linguistic universal.
_HARSH_LEANING_FRICATIVES = {"ʃ", "x", "ɣ", "s", "ʒ", "ʂ", "ʐ", "ħ", "ʕ", "ɬ"}
_SOFT_LEANING_FRICATIVES = {"f", "h", "z", "v", "θ", "ð", "ç", "ʝ"}

_APPROXIMANT_POOL = (
    Consonant(ipa="l", place=Place.ALVEOLAR, manner=Manner.LATERAL_APPROXIMANT, voiced=True, prevalence=0.75),
    Consonant(ipa="ɾ", place=Place.ALVEOLAR, manner=Manner.TAP, voiced=True, prevalence=0.50),
    Consonant(ipa="r", place=Place.ALVEOLAR, manner=Manner.TRILL, voiced=True, prevalence=0.35),
    Consonant(ipa="j", place=Place.PALATAL, manner=Manner.APPROXIMANT, voiced=True, prevalence=0.72),
    Consonant(ipa="w", place=Place.BILABIAL, manner=Manner.APPROXIMANT, voiced=True, prevalence=0.70),
)

# Very low-prevalence "exotic" extras -- non-pulmonic consonants, areally
# concentrated (clicks: Khoisan and neighbors; implosives: parts of Africa
# and Southeast Asia) rather than broadly common, but worth having for
# isolated/fantasy-flavored prompts.
_EXOTIC_POOL = (
    Consonant(ipa="ǀ", place=Place.DENTAL, manner=Manner.STOP, voiced=False, prevalence=0.015),
    Consonant(ipa="ǃ", place=Place.POSTALVEOLAR, manner=Manner.STOP, voiced=False, prevalence=0.015),
    Consonant(ipa="ǂ", place=Place.PALATAL, manner=Manner.STOP, voiced=False, prevalence=0.01),
    Consonant(ipa="ǁ", place=Place.ALVEOLAR, manner=Manner.LATERAL_FRICATIVE, voiced=False, prevalence=0.01),
    Consonant(ipa="ɓ", place=Place.BILABIAL, manner=Manner.STOP, voiced=True, prevalence=0.08),
    Consonant(ipa="ɗ", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=True, prevalence=0.08),
    Consonant(ipa="ʄ", place=Place.PALATAL, manner=Manner.STOP, voiced=True, prevalence=0.05),
    Consonant(ipa="ɠ", place=Place.VELAR, manner=Manner.STOP, voiced=True, prevalence=0.05),
    # Nahuatl's own /tɬ/ -- deliberately voiceless-only, not a
    # voiced/voiceless pair like _STOP_AND_AFFRICATE_PAIRS: a voiced
    # lateral affricate is real but markedly rarer cross-linguistically.
    Consonant(ipa="tɬ", place=Place.ALVEOLAR, manner=Manner.LATERAL_AFFRICATE, voiced=False, prevalence=0.1),
)

_MIN_CONSONANTS = 8
_MIN_VOWELS = 3

_VOWEL_ANCHORS = (
    Vowel(ipa="i", height=VowelHeight.CLOSE, backness=VowelBackness.FRONT, rounded=False, prevalence=0.95),
    Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=0.97),
    Vowel(ipa="u", height=VowelHeight.CLOSE, backness=VowelBackness.BACK, rounded=True, prevalence=0.90),
)
_VOWEL_EXTRAS = (
    Vowel(ipa="e", height=VowelHeight.CLOSE_MID, backness=VowelBackness.FRONT, rounded=False, prevalence=0.55),
    Vowel(ipa="o", height=VowelHeight.CLOSE_MID, backness=VowelBackness.BACK, rounded=True, prevalence=0.55),
    Vowel(ipa="ɛ", height=VowelHeight.OPEN_MID, backness=VowelBackness.FRONT, rounded=False, prevalence=0.35),
    Vowel(ipa="ɔ", height=VowelHeight.OPEN_MID, backness=VowelBackness.BACK, rounded=True, prevalence=0.35),
    Vowel(ipa="ə", height=VowelHeight.MID, backness=VowelBackness.CENTRAL, rounded=False, prevalence=0.45),
    Vowel(ipa="ɨ", height=VowelHeight.CLOSE, backness=VowelBackness.CENTRAL, rounded=False, prevalence=0.15),
    Vowel(ipa="ɪ", height=VowelHeight.NEAR_CLOSE, backness=VowelBackness.FRONT, rounded=False, prevalence=0.20),
    Vowel(ipa="ʊ", height=VowelHeight.NEAR_CLOSE, backness=VowelBackness.BACK, rounded=True, prevalence=0.18),
    Vowel(ipa="æ", height=VowelHeight.NEAR_OPEN, backness=VowelBackness.FRONT, rounded=False, prevalence=0.15),
    Vowel(ipa="ɐ", height=VowelHeight.NEAR_OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=0.10),
    Vowel(ipa="ɑ", height=VowelHeight.OPEN, backness=VowelBackness.BACK, rounded=False, prevalence=0.15),
    Vowel(ipa="y", height=VowelHeight.CLOSE, backness=VowelBackness.FRONT, rounded=True, prevalence=0.06),
    Vowel(ipa="ø", height=VowelHeight.CLOSE_MID, backness=VowelBackness.FRONT, rounded=True, prevalence=0.05),
    Vowel(ipa="œ", height=VowelHeight.OPEN_MID, backness=VowelBackness.FRONT, rounded=True, prevalence=0.04),
    # Genuine same-quality length pairs (Arabic /a/ vs. /aː/, etc.) -- a
    # different real-world strategy from Dutch's quality-shifted length
    # marking (i vs. ɪ), both already representable via distinct symbols;
    # these specifically model languages where length alone is contrastive.
    Vowel(ipa="aː", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, long=True, prevalence=0.10),
    Vowel(ipa="iː", height=VowelHeight.CLOSE, backness=VowelBackness.FRONT, rounded=False, long=True, prevalence=0.09),
    Vowel(ipa="uː", height=VowelHeight.CLOSE, backness=VowelBackness.BACK, rounded=True, long=True, prevalence=0.09),
    Vowel(ipa="eː", height=VowelHeight.CLOSE_MID, backness=VowelBackness.FRONT, rounded=False, long=True, prevalence=0.05),
    Vowel(ipa="oː", height=VowelHeight.CLOSE_MID, backness=VowelBackness.BACK, rounded=True, long=True, prevalence=0.05),
    # Long front-rounded/long-æ counterparts (real Hungarian "ő"/"ű",
    # Finnish's own long "ä"/"ö"/"y") -- same same-quality length-pair
    # strategy as aː/iː/uː/eː/oː above, each sharing its short
    # counterpart's exact height/backness/rounded so
    # romanization_gen._short_counterpart's existing matching pairs them
    # up automatically, no new code needed on that side.
    Vowel(ipa="æː", height=VowelHeight.NEAR_OPEN, backness=VowelBackness.FRONT, rounded=False, long=True, prevalence=0.04),
    Vowel(ipa="øː", height=VowelHeight.CLOSE_MID, backness=VowelBackness.FRONT, rounded=True, long=True, prevalence=0.03),
    Vowel(ipa="yː", height=VowelHeight.CLOSE, backness=VowelBackness.FRONT, rounded=True, long=True, prevalence=0.03),
    # Diphthongs -- each its own atomic, multi-character symbol (same
    # pattern as the long vowels just above), classified by its *onset*
    # quality (the standard way to give a diphthong one height/backness/
    # roundedness value). "ai"/"au"/"ei" deliberately reuse component
    # letters that are already plain ASCII in every romanization style,
    # so they need no table entry there -- see romanization_gen.py.
    Vowel(ipa="ai", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, diphthong=True, prevalence=0.15),
    Vowel(ipa="au", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, diphthong=True, prevalence=0.12),
    Vowel(ipa="ɔi", height=VowelHeight.OPEN_MID, backness=VowelBackness.BACK, rounded=True, diphthong=True, prevalence=0.08),
    Vowel(ipa="ei", height=VowelHeight.CLOSE_MID, backness=VowelBackness.FRONT, rounded=False, diphthong=True, prevalence=0.10),
    Vowel(ipa="ɛi", height=VowelHeight.OPEN_MID, backness=VowelBackness.FRONT, rounded=False, diphthong=True, prevalence=0.10),
    Vowel(ipa="œy", height=VowelHeight.OPEN_MID, backness=VowelBackness.FRONT, rounded=True, diphthong=True, prevalence=0.05),
    # Nasalized vowels (Portuguese/French/Hindi-style) -- combining tilde
    # (U+0303), same atomic-multi-character-symbol pattern as the long
    # vowels/diphthongs above, drawn independently per symbol like every
    # other _VOWEL_EXTRAS member (no group gate).
    Vowel(ipa="ã", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, nasalized=True, prevalence=0.15),
    Vowel(ipa="ẽ", height=VowelHeight.CLOSE_MID, backness=VowelBackness.FRONT, rounded=False, nasalized=True, prevalence=0.13),
    Vowel(ipa="ĩ", height=VowelHeight.CLOSE, backness=VowelBackness.FRONT, rounded=False, nasalized=True, prevalence=0.12),
    Vowel(ipa="õ", height=VowelHeight.CLOSE_MID, backness=VowelBackness.BACK, rounded=True, nasalized=True, prevalence=0.13),
    Vowel(ipa="ũ", height=VowelHeight.CLOSE, backness=VowelBackness.BACK, rounded=True, nasalized=True, prevalence=0.12),
    # Turkish's own dotless-ı vowel -- the pool's existing close vowels
    # are front unrounded (i), back/front rounded (u/y), and central
    # unrounded (ɨ), but no close *back* unrounded vowel until now.
    Vowel(ipa="ɯ", height=VowelHeight.CLOSE, backness=VowelBackness.BACK, rounded=False, prevalence=0.12),
    # Real Serbo-Croatian syllabic /r/ (vrt "garden", trg "square", Krk)
    # -- a whole syllable with no vowel at all, /r/ itself carrying the
    # nucleus. Modeled as one more `Vowel` pool member (U+0329 COMBINING
    # VERTICAL LINE BELOW, the real standard IPA syllabic-consonant
    # diacritic) since `PhonemeInventory` separates consonants/vowels
    # purely by which list an entry sits in, with no deeper structural
    # "is this really a vowel" check anywhere in word_builder.py/
    # sonority.py -- this slots into onset/nucleus/coda selection,
    # frequency tiers, stress and romanization through the exact existing
    # machinery every other vowel uses. height/backness are the closest
    # defensible vocoid classification, not a real claim that syllabic
    # /r/ "is" a close central vowel. Low prevalence, matching this
    # pool's own established "rare exotic member" rate (y/ø/œ).
    Vowel(ipa="r̩", height=VowelHeight.CLOSE, backness=VowelBackness.CENTRAL, rounded=False, prevalence=0.04),
)

_TONE_LEVEL_SETS = (
    (ToneLevel.LOW, ToneLevel.HIGH),
    (ToneLevel.LOW, ToneLevel.MID, ToneLevel.HIGH),
    (ToneLevel.LOW, ToneLevel.MID, ToneLevel.HIGH, ToneLevel.FALLING),
)

_VOWEL_HARMONY_BASE_RATE = 0.22
_CODA_PROFILES = ("none", "sonorant", "unrestricted")
_CODA_PROFILE_WEIGHTS = (15, 35, 50)

# Onset+nucleus co-occurrence, no-source-language roll (see
# _resolve_onset_nucleus_restriction): "probably more likely blacklist"
# per the project's own design call -- most real languages are closer to
# "mostly permissive with a few gaps" than to Mandarin's small, nearly-
# closed syllabary.
_BLACKLIST_MODE_BASE_RATE = 0.7
_RANDOM_BLACKLIST_FRACTION = 0.15  # a modest slice of the full space -- plenty stays legal
_RANDOM_WHITELIST_EXTRA_FRACTION = 0.5  # on top of the coverage floor, for realistic variety

ALL_CONSONANTS: tuple[Consonant, ...] = (
    tuple(x for pair in _STOP_AND_AFFRICATE_PAIRS for x in pair)
    + (_GLOTTAL_STOP,) + _EJECTIVES + _UVULAR_GROUP
    + _ASPIRATED_GROUP + _PHARYNGEALIZED_GROUP + _GEMINATE_GROUP + _PALATALIZED_GROUP
    + _ALVEOLO_PALATAL_GROUP
    + _NASAL_POOL + _FRICATIVE_POOL + _APPROXIMANT_POOL + _EXOTIC_POOL
    + _BREATHY_GROUP + _PRE_ASPIRATED_GROUP
)
"""Every consonant this package models, regardless of a given language's
inventory -- shared with ``sound_change.py``, which needs to look up any
symbol evolution might produce."""
ALL_VOWELS: tuple[Vowel, ...] = _VOWEL_ANCHORS + _VOWEL_EXTRAS
"""See ``ALL_CONSONANTS``."""


def _fricative_inclusion_probability(fricative: Consonant, harshness: float) -> float:
    if fricative.ipa in _HARSH_LEANING_FRICATIVES:
        return biased_probability(fricative.prevalence, harshness)
    if fricative.ipa in _SOFT_LEANING_FRICATIVES:
        return biased_probability(fricative.prevalence, -harshness)
    return fricative.prevalence


def _reference_biased_rate(
    base_rate: float, symbol: str, reference_symbols: frozenset[str], strictness: float = 0.0
) -> float:
    """Milestone 5: when ``TraitProfile.source_languages`` matched one or
    more real-language profiles, soft-bias every inclusion draw toward
    their palette -- boost symbols they use, suppress ones they don't --
    rather than overriding the probabilistic mechanism outright. A no-op
    (returns ``base_rate`` unchanged) when no reference is active.

    ``strictness`` (``TraitProfile.source_language_strictness``) layers an
    extra pull on top of that soft result, toward certainty for a
    reference symbol and toward impossibility for a non-reference one --
    a no-op at the default ``0.0`` (returns the soft result unchanged,
    byte-identical to this function before ``strictness`` existed),
    exactly ``1.0``/``0.0`` at ``strictness=1.0`` (hard restriction),
    smoothly graded in between. Reuses ``biased_probability`` directly:
    ``strictness`` is already a zero-to-one "positive strength," so this
    is just its signed form."""
    if not reference_symbols:
        return base_rate
    in_reference = symbol in reference_symbols
    soft_rate = max(base_rate, 0.85) if in_reference else base_rate * 0.3
    if strictness <= 0.0:
        return soft_rate
    return biased_probability(soft_rate, strictness if in_reference else -strictness)


def _group_reference_bias(
    probability: float, group_ipas: tuple[str, ...], reference_symbols: frozenset[str], strictness: float = 0.0
) -> float:
    """Same idea as ``_reference_biased_rate`` but for an all-or-nothing
    group gate (ejectives, the uvular series): boost the group's odds if
    the reference profile(s) use *any* member of it, suppress otherwise.
    ``strictness`` layers the same extra pull -- see
    ``_reference_biased_rate``'s own docstring. Note this only gates
    whether the group fires at all; once it does, ``_strict_group_members``
    separately grades which *individual* members actually get added."""
    if not reference_symbols:
        return probability
    any_member_matched = any(ipa in reference_symbols for ipa in group_ipas)
    soft_probability = max(probability, 0.75) if any_member_matched else min(probability, 0.05)
    if strictness <= 0.0:
        return soft_probability
    return biased_probability(soft_probability, strictness if any_member_matched else -strictness)


def _reference_clamp(
    probability: float,
    reference_profiles: tuple[ReferenceLanguageProfile, ...],
    attr: str,
    strictness: float = 0.0,
) -> float:
    """For boolean language-wide properties (tonal, vowel harmony): clamp
    the computed probability toward what the matched reference profile(s)
    say, rather than leaving it purely to the trait-driven base rate --
    "say" meaning *any* matched profile, so a multi-language match already
    behaves as a union (true if either has it, false only if neither
    does). ``strictness`` layers the same extra pull -- see
    ``_reference_biased_rate``'s own docstring -- becoming fully
    deterministic (exactly matching that union) at ``strictness=1.0``."""
    if not reference_profiles:
        return probability
    values = [getattr(p, attr) for p in reference_profiles]
    any_true = any(values)
    soft_probability = max(probability, 0.75) if any_true else min(probability, 0.08)
    if strictness <= 0.0:
        return soft_probability
    return biased_probability(soft_probability, strictness if any_true else -strictness)


def _strict_group_members(
    rng: random.Random, group: tuple, reference_symbols: frozenset[str], strictness: float
) -> tuple:
    """Once a group (or the always-on vowel anchors) has been decided to
    fire, this grades each individual *member's* own presence -- today's
    behavior is "every member joins unconditionally," a no-op here at the
    default ``strictness=0.0`` (``biased_probability(1.0, 0.0) == 1.0``,
    always included). At higher strictness a member not attested in any
    matched reference profile gets strictness-graded out, so a firing
    group only contributes what the reference language(s) actually have
    -- e.g. Finnish's only geminate is "kː", not the whole
    ``_GEMINATE_GROUP``; English has no plain "a", Nahuatl no "u", so
    ``_VOWEL_ANCHORS`` (unconditional today regardless of any bias) needs
    this too."""
    if not reference_symbols or strictness <= 0.0:
        return group
    kept = []
    for member in group:
        in_reference = member.ipa in reference_symbols
        if rng.random() < biased_probability(1.0, strictness if in_reference else -strictness):
            kept.append(member)
    return tuple(kept)


def _ensure_floor(
    rng: random.Random,
    selected: list,
    pool: tuple,
    minimum: int,
    reference_symbols: frozenset[str] = frozenset(),
    strictness: float = 0.0,
) -> list:
    if len(selected) >= minimum:
        return selected
    present = {p.ipa for p in selected}
    candidates = [p for p in pool if p.ipa not in present]
    if reference_symbols and strictness > 0.0:
        # Prefer padding from the reference languages' own palette first --
        # only once strictness is actually active, so plain
        # source_languages-only generation (strictness=0.0) stays a
        # byte-identical no-op. Confirmed necessary once it IS active:
        # some profiles sit exactly at `_MIN_CONSONANTS`/`_MIN_VOWELS`
        # (Hawaiian: 8 consonants; Pama-Nyungan/Quechua: 3 vowels) --
        # without this, topping up to the floor could leak an
        # off-reference symbol in even at full strictness.
        candidates.sort(key=lambda p: (p.ipa not in reference_symbols, -p.prevalence))
    else:
        candidates.sort(key=lambda p: -p.prevalence)
    for candidate in candidates:
        if len(selected) >= minimum:
            break
        selected.append(candidate)
    return selected


def _force_include(selected: list, pool: tuple, must_include: frozenset[str]) -> list:
    """Milestone 5: a seed example's phonemes are a hard floor on the
    generated inventory, unconditionally -- not just biased upward like
    ``_reference_biased_rate``. Unrecognized symbols (not anywhere in our
    modeled phoneme set) are silently skipped -- can't force-include
    something we have no ``Consonant``/``Vowel`` object for."""
    if not must_include:
        return selected
    present = {p.ipa for p in selected}
    by_ipa = {p.ipa: p for p in pool}
    for symbol in must_include:
        if symbol not in present and symbol in by_ipa:
            selected.append(by_ipa[symbol])
            present.add(symbol)
    return selected


def _select_consonants(
    rng: random.Random,
    spec: GenerationSpec,
    reference_symbols: frozenset[str],
    strictness: float = 0.0,
    must_include: frozenset[str] = frozenset(),
) -> list[Consonant]:
    traits = spec.traits
    consonants: list[Consonant] = []

    for voiceless, voiced in _STOP_AND_AFFRICATE_PAIRS:
        voiceless_rate = (
            biased_probability(voiceless.prevalence, traits.aesthetic_harshness)
            if voiceless.ipa == "tʃ"
            else voiceless.prevalence
        )
        voiceless_rate = _reference_biased_rate(voiceless_rate, voiceless.ipa, reference_symbols, strictness)
        if rng.random() < voiceless_rate:
            consonants.append(voiceless)
            voiced_rate = _reference_biased_rate(voiced.prevalence, voiced.ipa, reference_symbols, strictness)
            if rng.random() < voiced_rate:
                consonants.append(voiced)

    glottal_rate = _reference_biased_rate(_GLOTTAL_STOP.prevalence, _GLOTTAL_STOP.ipa, reference_symbols, strictness)
    if rng.random() < glottal_rate:
        consonants.append(_GLOTTAL_STOP)

    ejective_probability = (
        1.0 if spec.force_high_altitude else biased_probability(_EJECTIVE_GROUP_BASE_RATE, traits.altitude)
    )
    ejective_probability = _group_reference_bias(
        ejective_probability, tuple(e.ipa for e in _EJECTIVES), reference_symbols, strictness
    )
    if rng.random() < ejective_probability:
        consonants.extend(_strict_group_members(rng, _EJECTIVES, reference_symbols, strictness))

    uvular_probability = (
        1.0 if spec.force_isolated else biased_probability(_UVULAR_GROUP_BASE_RATE, traits.isolation)
    )
    uvular_probability = _group_reference_bias(
        uvular_probability, tuple(u.ipa for u in _UVULAR_GROUP), reference_symbols, strictness
    )
    if rng.random() < uvular_probability:
        consonants.extend(_strict_group_members(rng, _UVULAR_GROUP, reference_symbols, strictness))

    aspirated_probability = _group_reference_bias(
        _ASPIRATED_GROUP_BASE_RATE, tuple(c.ipa for c in _ASPIRATED_GROUP), reference_symbols, strictness
    )
    if rng.random() < aspirated_probability:
        consonants.extend(_strict_group_members(rng, _ASPIRATED_GROUP, reference_symbols, strictness))

    pharyngealized_probability = _group_reference_bias(
        _PHARYNGEALIZED_GROUP_BASE_RATE, tuple(c.ipa for c in _PHARYNGEALIZED_GROUP), reference_symbols, strictness
    )
    if rng.random() < pharyngealized_probability:
        consonants.extend(_strict_group_members(rng, _PHARYNGEALIZED_GROUP, reference_symbols, strictness))

    geminate_probability = _group_reference_bias(
        _GEMINATE_GROUP_BASE_RATE, tuple(c.ipa for c in _GEMINATE_GROUP), reference_symbols, strictness
    )
    if rng.random() < geminate_probability:
        consonants.extend(_strict_group_members(rng, _GEMINATE_GROUP, reference_symbols, strictness))

    palatalized_probability = _group_reference_bias(
        _PALATALIZED_GROUP_BASE_RATE, tuple(c.ipa for c in _PALATALIZED_GROUP), reference_symbols, strictness
    )
    if rng.random() < palatalized_probability:
        consonants.extend(_strict_group_members(rng, _PALATALIZED_GROUP, reference_symbols, strictness))

    alveolo_palatal_probability = _group_reference_bias(
        _ALVEOLO_PALATAL_GROUP_BASE_RATE, tuple(c.ipa for c in _ALVEOLO_PALATAL_GROUP), reference_symbols, strictness
    )
    if rng.random() < alveolo_palatal_probability:
        consonants.extend(_strict_group_members(rng, _ALVEOLO_PALATAL_GROUP, reference_symbols, strictness))

    for nasal in _NASAL_POOL:
        rate = biased_probability(nasal.prevalence, -traits.aesthetic_harshness) if nasal is _ng else nasal.prevalence
        rate = _reference_biased_rate(rate, nasal.ipa, reference_symbols, strictness)
        if rng.random() < rate:
            consonants.append(nasal)

    for fricative in _FRICATIVE_POOL:
        rate = _fricative_inclusion_probability(fricative, traits.aesthetic_harshness)
        rate = _reference_biased_rate(rate, fricative.ipa, reference_symbols, strictness)
        if rng.random() < rate:
            consonants.append(fricative)

    for approximant in _APPROXIMANT_POOL:
        rate = _reference_biased_rate(approximant.prevalence, approximant.ipa, reference_symbols, strictness)
        if rng.random() < rate:
            consonants.append(approximant)

    for exotic in _EXOTIC_POOL:
        rate = _reference_biased_rate(exotic.prevalence, exotic.ipa, reference_symbols, strictness)
        if rng.random() < rate:
            consonants.append(exotic)

    breathy_probability = _group_reference_bias(
        _BREATHY_GROUP_BASE_RATE, tuple(c.ipa for c in _BREATHY_GROUP), reference_symbols, strictness
    )
    if rng.random() < breathy_probability:
        consonants.extend(_strict_group_members(rng, _BREATHY_GROUP, reference_symbols, strictness))

    pre_aspirated_probability = _group_reference_bias(
        _PRE_ASPIRATED_GROUP_BASE_RATE, tuple(c.ipa for c in _PRE_ASPIRATED_GROUP), reference_symbols, strictness
    )
    if rng.random() < pre_aspirated_probability:
        consonants.extend(_strict_group_members(rng, _PRE_ASPIRATED_GROUP, reference_symbols, strictness))

    consonants = _force_include(consonants, ALL_CONSONANTS, must_include)
    return _ensure_floor(rng, consonants, ALL_CONSONANTS, _MIN_CONSONANTS, reference_symbols, strictness)


def _select_vowels(
    rng: random.Random,
    reference_symbols: frozenset[str],
    strictness: float = 0.0,
    must_include: frozenset[str] = frozenset(),
) -> list[Vowel]:
    vowels = list(_strict_group_members(rng, _VOWEL_ANCHORS, reference_symbols, strictness))
    for extra in _VOWEL_EXTRAS:
        rate = _reference_biased_rate(extra.prevalence, extra.ipa, reference_symbols, strictness)
        if rng.random() < rate:
            vowels.append(extra)
    vowels = _force_include(vowels, ALL_VOWELS, must_include)
    return _ensure_floor(rng, vowels, ALL_VOWELS, _MIN_VOWELS, reference_symbols, strictness)


def _sonorant_or_glottal_symbols(consonants: tuple[Consonant, ...]) -> tuple[str, ...]:
    return tuple(c.ipa for c in consonants if c.ipa == "ʔ" or sonority.sonority(c) >= 3)


def _resolve_pair_restriction(
    rng: random.Random,
    reference_profiles: tuple[ReferenceLanguageProfile, ...],
    strictness: float,
    first_symbols: tuple[str, ...],
    second_symbols: tuple[str, ...],
    phonotactic_restrictiveness: float,
    blacklist_field: str,
    whitelist_field: str,
) -> tuple[tuple[tuple[str, str], ...] | None, tuple[tuple[str, str], ...]]:
    """Resolves a local-adjacency co-occurrence restriction between two
    symbol positions (e.g. onset+nucleus, nucleus+coda, or a cross-syllable
    coda+next-onset boundary), returned as ``(allowed_pairs_or_None,
    excluded_pairs)`` for direct use as the corresponding pair of
    ``SyllableStructure`` fields. ``blacklist_field``/``whitelist_field``
    name the ``ReferenceLanguageProfile`` attributes to read for each
    matched profile -- this function is otherwise agnostic to which
    adjacency it's resolving.

    Two structurally different real patterns, chosen per matched reference
    profile by which field it populates (see
    ``ReferenceLanguageProfile.restricted_onset_nucleus_pairs``'s own
    docstring for the mode-inference rule): blacklist mode is a short list
    of *forbidden* combinations (most languages -- English's real "dw-"
    never preceding a rounded vowel); whitelist mode is a small, nearly-
    closed *attested* list against a much larger theoretical space
    (Mandarin-like). Multiple matched profiles combine via "the combined
    *legal* set is the union of each language's own legal set" -- which
    means blacklist-mode profiles *intersect* (a pair only stays forbidden
    if every one of them forbids it) while whitelist-mode profiles *union*
    (a pair is legal if either attests it); a mix of both collapses to
    blacklist semantics, since there's no whitelist representation once
    something else has already widened the legal set -- the combined
    blacklist is the intersection of all blacklists, minus the union of
    all whitelists as exemptions. Only when *every* matched profile is
    whitelist-mode does the result stay genuine (restrictive) whitelist
    semantics.

    No source language matched at all: this axis doesn't depend on source
    languages -- it rolls its own blacklist-or-whitelist mode from
    ``phonotactic_restrictiveness`` and synthesizes data from this run's
    own rolled inventory (there's nothing curated to draw from). A rolled
    whitelist gets a coverage floor first -- every symbol on each side
    keeps at least one legal partner on the other -- so it can never leave
    a symbol totally unreachable in this position, per "a whitelist should
    generally be large enough to support a language."
    """
    if reference_profiles:
        blacklist_profiles = [p for p in reference_profiles if getattr(p, blacklist_field)]
        whitelist_profiles = [p for p in reference_profiles if getattr(p, whitelist_field)]
        symbol_space = frozenset(first_symbols) | frozenset(second_symbols)

        if blacklist_profiles or not whitelist_profiles:
            combined_blacklist = frozenset(getattr(blacklist_profiles[0], blacklist_field)) if blacklist_profiles else frozenset()
            for profile in blacklist_profiles[1:]:
                combined_blacklist &= frozenset(getattr(profile, blacklist_field))
            combined_whitelist = frozenset().union(*(getattr(p, whitelist_field) for p in whitelist_profiles)) if whitelist_profiles else frozenset()
            effective_blacklist = frozenset(
                pair for pair in (combined_blacklist - combined_whitelist) if pair[0] in symbol_space and pair[1] in symbol_space
            )
            if strictness <= 0.0:
                return None, tuple(effective_blacklist)
            return None, tuple(pair for pair in effective_blacklist if rng.random() < biased_probability(1.0, strictness))
        else:
            combined_whitelist = frozenset(
                pair
                for pair in frozenset().union(*(getattr(p, whitelist_field) for p in whitelist_profiles))
                if pair[0] in symbol_space and pair[1] in symbol_space
            )
            if strictness <= 0.0:
                return (tuple(combined_whitelist) or None), ()
            kept = tuple(pair for pair in combined_whitelist if rng.random() < biased_probability(1.0, strictness))
            return (kept or None), ()

    # No source language at all -- roll mode, synthesize from this run's own inventory.
    all_pairs = tuple((a, b) for a in first_symbols for b in second_symbols)
    if not all_pairs:
        return None, ()
    blacklist_probability = biased_probability(_BLACKLIST_MODE_BASE_RATE, -phonotactic_restrictiveness)
    if rng.random() < blacklist_probability:
        num_restricted = round(len(all_pairs) * _RANDOM_BLACKLIST_FRACTION)
        return None, tuple(rng.sample(all_pairs, k=min(num_restricted, len(all_pairs))))

    attested: set[tuple[str, str]] = set()
    for a in first_symbols:
        attested.add((a, rng.choice(second_symbols)))
    for b in second_symbols:
        attested.add((rng.choice(first_symbols), b))
    remaining = [pair for pair in all_pairs if pair not in attested]
    rng.shuffle(remaining)
    extra_count = round(len(all_pairs) * _RANDOM_WHITELIST_EXTRA_FRACTION)
    attested.update(remaining[:extra_count])
    return tuple(attested), ()


def _resolve_onset_nucleus_restriction(
    rng: random.Random,
    reference_profiles: tuple[ReferenceLanguageProfile, ...],
    strictness: float,
    consonant_symbols: tuple[str, ...],
    vowel_symbols: tuple[str, ...],
    phonotactic_restrictiveness: float,
) -> tuple[tuple[tuple[str, str], ...] | None, tuple[tuple[str, str], ...]]:
    """Onset+nucleus co-occurrence -- see ``_resolve_pair_restriction``."""
    return _resolve_pair_restriction(
        rng, reference_profiles, strictness, consonant_symbols, vowel_symbols, phonotactic_restrictiveness,
        "restricted_onset_nucleus_pairs", "attested_onset_nucleus_pairs",
    )


def _resolve_nucleus_coda_restriction(
    rng: random.Random,
    reference_profiles: tuple[ReferenceLanguageProfile, ...],
    strictness: float,
    vowel_symbols: tuple[str, ...],
    consonant_symbols: tuple[str, ...],
    phonotactic_restrictiveness: float,
) -> tuple[tuple[tuple[str, str], ...] | None, tuple[tuple[str, str], ...]]:
    """Nucleus+coda co-occurrence -- see ``_resolve_pair_restriction``."""
    return _resolve_pair_restriction(
        rng, reference_profiles, strictness, vowel_symbols, consonant_symbols, phonotactic_restrictiveness,
        "restricted_nucleus_coda_pairs", "attested_nucleus_coda_pairs",
    )


def _resolve_coda_onset_boundary_restriction(
    rng: random.Random,
    reference_profiles: tuple[ReferenceLanguageProfile, ...],
    strictness: float,
    consonant_symbols: tuple[str, ...],
    phonotactic_restrictiveness: float,
) -> tuple[tuple[tuple[str, str], ...] | None, tuple[tuple[str, str], ...]]:
    """Cross-syllable coda-then-next-onset co-occurrence -- see
    ``_resolve_pair_restriction``. Both sides draw from the same
    consonant pool."""
    return _resolve_pair_restriction(
        rng, reference_profiles, strictness, consonant_symbols, consonant_symbols, phonotactic_restrictiveness,
        "restricted_coda_onset_pairs", "attested_coda_onset_pairs",
    )


_FREQUENCY_TIER_WEIGHTS: dict[str, float] = {
    "very_common": 2.0, "common": 1.0, "uncommon": 0.5, "rare": 0.15,
}
"""Multipliers for ``_resolve_position_multipliers`` -- centered so
``"common"`` (the tier most symbols in any position actually fall into)
is exactly ``1.0``, i.e. unchanged from today's uninfluenced behavior."""


def _resolve_position_multipliers(
    symbols: tuple[str, ...],
    reference_profiles: tuple[ReferenceLanguageProfile, ...],
    strictness: float,
    field: str,
) -> tuple[tuple[str, float], ...]:
    """Resolves this run's own in-word sampling-weight multiplier per
    symbol for one position (onset/nucleus/coda), from a matched
    profile's own ``{onset,nucleus,coda}_frequency_tiers`` (``field``
    names which one). A multiplier, not a replacement value: an
    unmatched or uncurated symbol keeps its existing
    ``Consonant.prevalence``/``Vowel.prevalence`` exactly (multiplier
    ``1.0``), only symbols a matched profile actually tiers move at all
    -- see ``core.phonology.SyllableStructure.onset_symbol_multipliers``
    and ``word_builder.py`` for how the result is consumed.

    ``strictness`` linearly interpolates each tiered symbol's multiplier
    from ``1.0`` (no bias) toward its tier's weight (``_FREQUENCY_TIER_WEIGHTS``)
    -- not ``biased_probability``, which models pulling a probability
    toward certainty/impossibility; these are arbitrary positive sampling
    weights, not probabilities of a binary event. A no-op at
    ``strictness<=0`` or with no matched profile, same guarantee as every
    other axis in this feature. Multiple matched profiles disagreeing on
    a symbol's tier average their weights (not a union/intersection --
    there's no legal/illegal split here to combine that way)."""
    if not reference_profiles or strictness <= 0.0:
        return ()
    result = []
    for symbol in symbols:
        tier_weights = [
            _FREQUENCY_TIER_WEIGHTS[tier]
            for p in reference_profiles
            for tier, members in getattr(p, field).items()
            if symbol in members
        ]
        if not tier_weights:
            continue
        target = sum(tier_weights) / len(tier_weights)
        result.append((symbol, 1.0 + strictness * (target - 1.0)))
    return tuple(result)


def generate_phonology(
    rng: random.Random, spec: GenerationSpec
) -> tuple[PhonemeInventory, SyllableStructure, ToneSystem, WordAccentSystem]:
    traits = spec.traits
    reference_profiles = match_profiles(traits.source_languages)
    reference_symbols: frozenset[str] = frozenset().union(*(p.symbols() for p in reference_profiles)) if reference_profiles else frozenset()
    strictness = traits.source_language_strictness if reference_profiles else 0.0

    seed_ipa_text = "".join(example.ipa or "" for example in spec.seed_examples)
    consonant_symbol_pool = tuple(c.ipa for c in ALL_CONSONANTS)
    vowel_symbol_pool = tuple(v.ipa for v in ALL_VOWELS)
    seed_tokens = ipa_tokenizer.symbols_only(seed_ipa_text, consonant_symbol_pool + vowel_symbol_pool)
    must_include_consonants = frozenset(t for t in seed_tokens if t in consonant_symbol_pool)
    must_include_vowels = frozenset(t for t in seed_tokens if t in vowel_symbol_pool)

    consonants = tuple(_select_consonants(rng, spec, reference_symbols, strictness, must_include_consonants))
    vowels = tuple(_select_vowels(rng, reference_symbols, strictness, must_include_vowels))
    inventory = PhonemeInventory(consonants=consonants, vowels=vowels)
    consonant_symbols = inventory.consonant_symbols()
    vowel_symbols_for_pairs = inventory.vowel_symbols()
    allowed_onset_nucleus_pairs, excluded_onset_nucleus_pairs = _resolve_onset_nucleus_restriction(
        rng, reference_profiles, strictness, consonant_symbols, vowel_symbols_for_pairs, traits.phonotactic_restrictiveness
    )
    allowed_nucleus_coda_pairs, excluded_nucleus_coda_pairs = _resolve_nucleus_coda_restriction(
        rng, reference_profiles, strictness, vowel_symbols_for_pairs, consonant_symbols, traits.phonotactic_restrictiveness
    )
    allowed_coda_onset_boundary_pairs, excluded_coda_onset_boundary_pairs = _resolve_coda_onset_boundary_restriction(
        rng, reference_profiles, strictness, consonant_symbols, traits.phonotactic_restrictiveness
    )

    # Onset-position restriction (e.g. /ŋ/ never opens a syllable in real
    # German/English) -- the onset-side mirror of the coda-devoicing
    # exclusion below, graded by strictness the same "rng.random() <
    # strictness per restricted symbol" way as every other axis in this
    # feature (a no-op at strictness=0.0, since `restricted_onset` only
    # matters once this loop actually runs).
    excluded_onset_consonants: tuple[str, ...] = ()
    if reference_profiles and strictness > 0.0:
        restricted_onset = frozenset().union(
            *(p.restricted_onset_consonants for p in reference_profiles)
        ) & set(consonant_symbols)
        excluded_onset_consonants = tuple(c for c in restricted_onset if rng.random() < strictness)

    onset_pairs = sonority.legal_onset_pairs(consonants)
    if excluded_onset_consonants:
        onset_pairs = tuple(p for p in onset_pairs if p[0] not in excluded_onset_consonants and p[1] not in excluded_onset_consonants)
    if reference_profiles and strictness > 0.0:
        attested_onset_clusters = frozenset().union(*(p.attested_onset_clusters for p in reference_profiles))
        onset_pairs = sonority.grade_against_attested(rng, onset_pairs, tuple(attested_onset_clusters), strictness)
    onset_cluster_probability = 0.5
    if reference_profiles:
        allows_onset_cluster = any(p.max_onset >= 2 for p in reference_profiles)
        onset_cluster_probability = 0.85 if allows_onset_cluster else 0.1
        if strictness > 0.0:
            onset_cluster_probability = biased_probability(
                onset_cluster_probability, strictness if allows_onset_cluster else -strictness
            )
    max_onset = 2 if onset_pairs and rng.random() < onset_cluster_probability else 1
    allowed_onset_clusters = (
        sonority.thin_cluster_pairs(rng, onset_pairs, traits.contact_intensity) if max_onset >= 2 else ()
    )

    coda_weights = list(_CODA_PROFILE_WEIGHTS)
    if reference_profiles:
        reference_coda_profiles = {p.coda_profile for p in reference_profiles}
        coda_weights = [w * 4 if profile in reference_coda_profiles else w for profile, w in zip(_CODA_PROFILES, coda_weights)]
        if strictness > 0.0:
            total = sum(coda_weights)
            coda_weights = [
                total * biased_probability(w / total, strictness if profile in reference_coda_profiles else -strictness)
                for profile, w in zip(_CODA_PROFILES, coda_weights)
            ]
    coda_profile = rng.choices(_CODA_PROFILES, weights=coda_weights)[0]

    # Coda-position restriction (e.g. /j//w/ never close a syllable in
    # real English -- what looks like a word-final glide in English
    # spelling is actually part of a diphthong vowel) -- the coda-side
    # mirror of the onset restriction above, same strictness grading.
    # Computed once, ahead of the coda_profile branches below, since a
    # curated-restricted sonorant would otherwise still slip through the
    # "sonorant" branch's own `_sonorant_or_glottal_symbols` whitelist.
    restricted_coda: frozenset[str] = frozenset()
    if reference_profiles and strictness > 0.0:
        restricted_coda = frozenset().union(
            *(p.restricted_coda_consonants for p in reference_profiles)
        ) & set(consonant_symbols)
        restricted_coda = frozenset(c for c in restricted_coda if rng.random() < strictness)

    excluded_coda_consonants: tuple[str, ...] = ()
    if coda_profile == "none":
        max_coda, allowed_coda_consonants, allowed_coda_clusters = 0, None, ()
    elif coda_profile == "sonorant":
        sonorants = tuple(s for s in _sonorant_or_glottal_symbols(consonants) if s not in restricted_coda)
        if sonorants:
            max_coda, allowed_coda_consonants, allowed_coda_clusters = 1, sonorants, ()
        else:
            max_coda, allowed_coda_consonants, allowed_coda_clusters = 0, None, ()
    else:  # unrestricted
        if any(p.coda_devoicing for p in reference_profiles):
            excluded_coda_consonants = tuple(
                c.ipa
                for c in consonants
                if c.voiced and c.manner in (
                    Manner.STOP, Manner.AFFRICATE, Manner.LATERAL_AFFRICATE, Manner.FRICATIVE, Manner.LATERAL_FRICATIVE,
                )
            )
        excluded_coda_consonants = tuple(frozenset(excluded_coda_consonants) | restricted_coda)
        coda_pairs = sonority.exclude_final(sonority.legal_coda_pairs(consonants), excluded_coda_consonants)
        if reference_profiles and strictness > 0.0:
            attested_coda_clusters = frozenset().union(*(p.attested_coda_clusters for p in reference_profiles))
            coda_pairs = sonority.grade_against_attested(rng, coda_pairs, tuple(attested_coda_clusters), strictness)
        if coda_pairs and rng.random() < 0.3:
            max_coda, allowed_coda_consonants, allowed_coda_clusters = (
                2, None, sonority.thin_cluster_pairs(rng, coda_pairs, traits.contact_intensity),
            )
        else:
            max_coda, allowed_coda_consonants, allowed_coda_clusters = 1, None, ()

    vowel_harmony_probability = biased_probability(_VOWEL_HARMONY_BASE_RATE, traits.isolation)
    vowel_harmony_probability = _reference_clamp(vowel_harmony_probability, reference_profiles, "vowel_harmony", strictness)
    vowel_harmony = rng.random() < vowel_harmony_probability

    # In-word sampling-frequency realism (distinct from every restriction
    # above, which governs whether a symbol/cluster can appear at all):
    # once a symbol is legal in a position, how often it actually shows
    # up there varies a lot by language and, independently, by position
    # for the very same symbol (real Dutch /x/ is onset-rare but one of
    # the most common codas) -- see `_resolve_position_multipliers`.
    onset_legal_symbols = tuple(c for c in consonant_symbols if c not in excluded_onset_consonants)
    coda_legal_symbols = (
        tuple(allowed_coda_consonants)
        if allowed_coda_consonants is not None
        else tuple(c for c in consonant_symbols if c not in excluded_coda_consonants)
    )
    onset_symbol_multipliers = _resolve_position_multipliers(
        onset_legal_symbols, reference_profiles, strictness, "onset_frequency_tiers"
    )
    nucleus_symbol_multipliers = _resolve_position_multipliers(
        vowel_symbols_for_pairs, reference_profiles, strictness, "nucleus_frequency_tiers"
    )
    coda_symbol_multipliers = _resolve_position_multipliers(
        coda_legal_symbols, reference_profiles, strictness, "coda_frequency_tiers"
    )

    syllable_structure = SyllableStructure(
        max_onset=max_onset,
        max_coda=max_coda,
        allowed_onset_clusters=allowed_onset_clusters,
        allowed_coda_clusters=allowed_coda_clusters,
        allowed_coda_consonants=allowed_coda_consonants,
        excluded_coda_consonants=excluded_coda_consonants,
        excluded_onset_consonants=excluded_onset_consonants,
        allowed_onset_nucleus_pairs=allowed_onset_nucleus_pairs,
        excluded_onset_nucleus_pairs=excluded_onset_nucleus_pairs,
        allowed_nucleus_coda_pairs=allowed_nucleus_coda_pairs,
        excluded_nucleus_coda_pairs=excluded_nucleus_coda_pairs,
        allowed_coda_onset_boundary_pairs=allowed_coda_onset_boundary_pairs,
        excluded_coda_onset_boundary_pairs=excluded_coda_onset_boundary_pairs,
        onset_symbol_multipliers=onset_symbol_multipliers,
        nucleus_symbol_multipliers=nucleus_symbol_multipliers,
        coda_symbol_multipliers=coda_symbol_multipliers,
        vowel_harmony=vowel_harmony,
    )

    tonal_probability = (
        1.0 if spec.force_tonal else biased_probability(0.35, traits.tonal_friendliness)
    )
    if not spec.force_tonal:
        tonal_probability = _reference_clamp(tonal_probability, reference_profiles, "tonal", strictness)
    if rng.random() < tonal_probability:
        levels = rng.choice(_TONE_LEVEL_SETS)
        tone_system = ToneSystem(enabled=True, levels=levels)
    else:
        tone_system = ToneSystem(enabled=False)

    # Word accent (real Danish stød / Swedish-Norwegian pitch accent) has
    # no trait dial of its own -- unlike `tonal_friendliness`, a
    # world-building "flavor" knob, this is a narrow, specific
    # typological feature that should only ever appear via an explicit
    # matched reference profile, the same reference-profile-only gating
    # `coda_devoicing`/`root_and_pattern`/`vowel_harmony` already use for
    # features with no trait backing them (starting the clamp from a base
    # probability of 0.0, rather than a trait-derived rate, guarantees
    # this never fires for an unmatched or unrelated-language run).
    # Mutually exclusive with tone (a real language is never both a tone
    # language and a pitch-accent language) -- skip the roll entirely
    # once `tonal` has already won.
    word_accent_realization, _, _, _ = word_accent_gen.resolve_word_accent(reference_profiles)
    if tone_system.enabled or not word_accent_realization:
        word_accent_system = WordAccentSystem(enabled=False)
    else:
        word_accent_probability = _reference_clamp(0.0, reference_profiles, "word_accent_realization", strictness)
        word_accent_system = (
            WordAccentSystem(enabled=True, realization=word_accent_realization)
            if rng.random() < word_accent_probability
            else WordAccentSystem(enabled=False)
        )

    return inventory, syllable_structure, tone_system, word_accent_system
