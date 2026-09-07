"""A small, hand-curated set of real languages' rough phonological +
orthographic profiles, used to bias generation toward "sounds like X" /
"mix of X and Y" when ``TraitProfile.source_languages`` names one we
recognize -- see ``TraitProfile.source_language_strictness`` for the dial
that turns that bias into a hard restriction.

Symbol sets are restricted to symbols already in ``phonology_gen.py``'s
pools (so matching against a generated inventory is a plain set
intersection). These are illustrative typological sketches for flavor, not
authoritative phonological descriptions -- real language phonology is far
richer than what our own symbol pool and phonotactic model can represent
(no consonant length/gemination as a phonemic feature; no noun-class
morphology; root-and-pattern morphology models word-*shape* only, not
derivational relatedness between words -- see
``generation/root_pattern.py``). ``orthography`` rules are similarly
illustrative -- see ``core/romanization.py``'s module docstring for what
they can and can't express (local adjacency conditions; not stress,
morphology-driven spelling, or word-level algorithmic romanization like
Korean's or Hindi's).

Each profile lives in its own file under ``reference_languages/profiles/``
(one YAML document per language -- adding a language is "add a file," no
code change needed), loaded here into ``ReferenceLanguageProfile`` via the
same ``model_dump()``/``model_validate()`` round-trip
``storage/yaml_backend.py`` already uses for saved languages. A profile's
YAML shape mirrors ``ReferenceLanguageProfile``'s fields directly:

```yaml
name: Dutch
aliases: [nederlands]
consonants: [p, b, t, d, k, f, v, s, z, x, h, m, n, "ŋ", l, r, w, j]
vowels: [i, "ɪ", e, "ɛ", a, "ɑ", "ɔ", o, u, y, "ø", "œ", "ə"]
coda_profile: unrestricted      # "none" | "sonorant" | "unrestricted"
max_onset: 2
tonal: false
vowel_harmony: false            # optional, defaults false
root_and_pattern: false         # optional, defaults false -- see the field's own docstring
coda_devoicing: false           # optional, defaults false -- see the field's own docstring
orthography_category: ""        # optional, defaults "" -- see the field's own docstring
syllable_boundary_marker: ""    # optional, defaults "" -- e.g. "diaeresis", overrides just this one axis
onset_nucleus_spellings:        # optional, defaults empty -- joint spelling, consumes both letters
  - {first: w, second: a, latin: oi}
nucleus_coda_spellings: []      # optional, defaults empty -- same shape, coda-side mirror
orthography:                    # optional, defaults empty
  - {ipa: a, latin: aa, syllable: [syllable_closed]}    # "kaas"
  - {ipa: a, latin: a, syllable: [syllable_open]}       # "kazen"
  - {ipa: x, latin: ch}                                 # unconditioned ("nacht")
restricted_onset_consonants: []  # optional, defaults empty -- see the field's own docstring
attested_onset_clusters: []      # optional, defaults empty -- e.g. [[s, p], [s, t]]
restricted_coda_consonants: []   # optional, defaults empty -- see the field's own docstring
restricted_onset_nucleus_pairs: []  # optional, defaults empty -- e.g. [[w, u]] (blacklist mode)
attested_onset_nucleus_pairs: []    # optional, defaults empty -- whitelist mode, mutually exclusive with the above
attested_coda_clusters: []          # optional, defaults empty -- e.g. [[s, t]]
restricted_nucleus_coda_pairs: []   # optional, defaults empty -- e.g. [[i, "ŋ"]] (blacklist mode)
attested_nucleus_coda_pairs: []     # optional, defaults empty -- whitelist mode, mutually exclusive with the above
restricted_coda_onset_pairs: []     # optional, defaults empty -- cross-syllable, blacklist mode
attested_coda_onset_pairs: []       # optional, defaults empty -- cross-syllable, whitelist mode
core_vocabulary_average_syllables: null  # optional, defaults null -- e.g. 1.43, a hand-counted illustrative average
onset_frequency_tiers:              # optional, defaults empty -- in-word frequency by word-type productivity
  very_common: [s, t]
  common: [p, b, d]
  uncommon: [z]
  rare: ["ð"]
nucleus_frequency_tiers: {}         # optional, defaults empty -- same tier shape, for vowels
coda_frequency_tiers: {}            # optional, defaults empty -- same tier shape, for coda consonants
```

``orthography`` entries are ``RomanizationRule``s -- see its docstring for
what ``following``/``preceding`` (neighbor tags: exact symbols, or a
computed class -- ``vowel``/``consonant``/``boundary``/``front_vowel``/
``back_vowel``) and ``syllable`` (this symbol's own structural position --
``syllable_open``/``syllable_closed``) mean, and why they're separate.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.romanization import JointSpelling, MuteSuffixRule, RomanizationRule

_PROFILES_DIR = Path(__file__).parent / "profiles"


class ReferenceLanguageProfile(BaseModel, frozen=True):
    name: str
    aliases: tuple[str, ...] = ()
    consonants: tuple[str, ...]
    vowels: tuple[str, ...]
    coda_profile: str  # "none" | "sonorant" | "unrestricted"
    max_onset: int
    tonal: bool
    vowel_harmony: bool = False
    root_and_pattern: bool = False
    """Whether this language uses Semitic-style root-and-pattern
    (templatic) derivational morphology -- orthogonal to
    `core.grammar.MorphologicalType` (which measures synthesis: morphemes
    per word, how cleanly they segment), not a value on that same axis.
    Arabic is fusional *and* root-and-pattern simultaneously; this field
    is how `grammar_gen.py` biases toward the latter independently of the
    former. See `generation/root_pattern.py`."""
    coda_devoicing: bool = False
    """Whether this language categorically excludes voiced obstruents
    from coda-final position (real Dutch/German/Russian/Turkish-style
    final-obstruent devoicing as a *static* phonotactic fact, not just
    `sound_change.py`'s diachronic `final_devoicing` rule). Only matters
    when `coda_profile` is `"unrestricted"` -- moot for `"none"`/
    `"sonorant"`, which never allow obstruents in coda position at all.
    See `generation/phonology_gen.py`'s own `generate_phonology()`."""
    orthography: tuple[RomanizationRule, ...] = ()
    """A handful of that language's own real spelling conventions,
    restricted to symbols this module's own ``consonants``/``vowels``
    cover and to what this project's phonology can represent (no
    diphthongs). Illustrative/approximate, same spirit as the
    phonological fields above -- not a full orthography. Empty for
    languages we haven't curated spelling conventions for yet."""
    orthography_category: str = ""
    """The name of a ``generation.romanization_gen`` ``OrthographyCategory``
    (e.g. ``"germanic-doubling-style"``) this language's own conventions
    lean toward -- a coarse, optional "which family" signal separate from
    (and layered under) the specific per-symbol deviations in
    ``orthography`` above: ``generate_romanization`` probabilistically
    biases the *whole scheme's* category toward this one when this
    profile matches, same spirit as ``orthography`` itself."""
    syllable_boundary_marker: str = ""
    """Overrides just this one axis of whichever category wins for this
    language (a ``core.romanization.SyllableBoundaryMarker`` value, e.g.
    ``"diaeresis"``) -- for a convention specific to this language, not
    shared by its whole ``orthography_category`` family (real French
    tréma -- Noël, naïve -- isn't a trait of every ``"diacritic-style"``
    language; Icelandic/Persian/Portuguese/Quechua/Russian/Spanish/
    Tibetan/Turkish also point at that same category and don't use it).
    Empty (the common case) means no override -- the normal category roll
    decides this axis, same convention as every other curated field."""
    onset_nucleus_spellings: tuple[JointSpelling, ...] = ()
    """Real conventions that jointly spell an onset consonant + the
    nucleus vowel right after it, consuming both letters at once (real
    French ``/w/``+``/a/`` -> "oi" -- see ``core.romanization.JointSpelling``'s
    own docstring for why this needs a different mechanism from
    ``orthography``'s per-symbol conditioning). Empty (the common case)
    means not curated -- abstains, same convention as every other field
    above. Only consulted when ``source_language_strictness`` > 0."""
    nucleus_coda_spellings: tuple[JointSpelling, ...] = ()
    """The coda-side mirror of ``onset_nucleus_spellings`` -- a nucleus
    vowel + the coda consonant right after it spelled jointly. No profile
    currently curates this (see ``JointSpelling``'s own docstring for
    why most nucleus+coda-*looking* conventions turn out not to need
    it), but the mechanism is symmetric and ready for one that does."""
    capitalized_pos: tuple[PartOfSpeech, ...] = ()
    """Part-of-speech categories this language's real orthography always
    capitalizes in citation form (e.g. German's own every-common-noun
    capitalization) -- a hint ``romanization_gen.py``'s grammatical-
    spelling roll leans toward when this profile matches, same spirit as
    ``orthography_category`` above but for ``core.romanization.
    GrammaticalSpelling.capitalized_pos``."""
    mute_suffix_by_pos: tuple[MuteSuffixRule, ...] = ()
    """This language's own real POS-keyed silent-letter spelling
    convention (e.g. French infinitive verbs' silent "-r") -- same
    "hint the roll leans toward when matched" role as
    ``capitalized_pos`` above, for ``core.romanization.
    GrammaticalSpelling.mute_suffix_by_pos``."""
    restricted_onset_consonants: tuple[str, ...] = ()
    """Consonants this language never uses to open a syllable (single or
    as part of a cluster) -- e.g. /ŋ/ in German/English, which is
    coda/medial only. Only consulted when a matched
    ``TraitProfile.source_language_strictness`` > 0 -- see
    ``generation/phonology_gen.py``. Empty means not curated yet for
    this language (most profiles), same "illustrative, not exhaustive"
    spirit as ``orthography``."""
    attested_onset_clusters: tuple[tuple[str, str], ...] = ()
    """A curated, illustrative (not exhaustive) list of this language's
    own real 2-consonant onset clusters, restricted to symbols this
    profile models -- narrows the generic sonority-legal combinatorial
    space (``generation/sonority.py``) down to real attested pairs when
    strictness is active. Empty means no curated list yet -- falls back
    to the generic sonority-only legality check."""
    restricted_coda_consonants: tuple[str, ...] = ()
    """Consonants this language never uses to close a syllable -- the
    coda-side mirror of ``restricted_onset_consonants`` (e.g. English
    /j/,/w/: what looks like a word-final glide in English spelling
    ["cow", "day"] is actually part of a diphthong vowel, not a true
    consonant coda). Verified per-language, not a blanket rule -- French
    genuinely has real word-final /j/ (soleil, travail), so it must NOT
    appear here for French. Only consulted when strictness > 0; empty
    means not curated yet, same spirit as the fields above."""
    restricted_onset_nucleus_pairs: tuple[tuple[str, str], ...] = ()
    """Blacklist mode: ``(last-onset-consonant, nucleus)`` pairs this
    language never combines -- e.g. English ``(w, u)``/``(w, o)``/
    ``(w, "ʊ")``: real "dw-"/"tw-"/"kw-"/"gw-" never precede a rounded
    vowel, keyed on the shared final onset consonant "w" so it covers
    every cluster ending in it, not just one specific cluster. A profile
    populates *at most one* of this and ``attested_onset_nucleus_pairs``,
    never both -- whichever is non-empty determines this language's mode
    (see ``generation/phonology_gen.py``). Empty (the common case) means
    not curated yet -- abstains from the multi-language combination
    entirely, not the same as "verified permissive everywhere". Only
    consulted when ``source_language_strictness`` > 0."""
    attested_onset_nucleus_pairs: tuple[tuple[str, str], ...] = ()
    """Whitelist mode: the ``(last-onset-consonant, nucleus)`` pairs that
    are the *only* ones legal (Mandarin-style small syllabary) -- see
    ``restricted_onset_nucleus_pairs`` above for the mode-inference rule
    and the abstain-when-empty semantics."""
    attested_coda_clusters: tuple[tuple[str, str], ...] = ()
    """A curated, illustrative (not exhaustive) list of this language's
    own real 2-consonant coda clusters, restricted to symbols this
    profile models -- the coda-side mirror of ``attested_onset_clusters``,
    narrowing the generic sonority-legal combinatorial space down to real
    attested pairs when strictness is active. Empty means no curated list
    yet -- falls back to the generic sonority-only legality check. Only
    consulted for the ``"unrestricted"`` ``coda_profile`` branch (a
    ``"none"``/``"sonorant"`` profile never builds coda clusters at all)."""
    restricted_nucleus_coda_pairs: tuple[tuple[str, str], ...] = ()
    """Blacklist mode: ``(nucleus, coda[0])`` pairs this language never
    combines -- e.g. real English /ŋ/ only closes a syllable after a
    lax/checked vowel (sing, sung, hang), never a tense vowel or
    diphthong. The coda-side mirror of ``restricted_onset_nucleus_pairs``;
    same mode-inference/abstain-when-empty rule against
    ``attested_nucleus_coda_pairs``, only consulted when
    ``source_language_strictness`` > 0."""
    attested_nucleus_coda_pairs: tuple[tuple[str, str], ...] = ()
    """Whitelist mode: the ``(nucleus, coda[0])`` pairs that are the only
    ones legal -- see ``restricted_nucleus_coda_pairs`` above for the
    mode-inference rule and the abstain-when-empty semantics."""
    restricted_coda_onset_pairs: tuple[tuple[str, str], ...] = ()
    """Blacklist mode, cross-syllable: ``(previous syllable's final coda
    consonant, next syllable's first onset consonant)`` pairs this
    language never combines at a word-internal syllable boundary. Same
    mode-inference/abstain-when-empty rule against
    ``attested_coda_onset_pairs``; only consulted when
    ``source_language_strictness`` > 0. See
    ``core.phonology.SyllableStructure.is_valid_boundary``."""
    attested_coda_onset_pairs: tuple[tuple[str, str], ...] = ()
    """Whitelist mode, cross-syllable: the ``(prev coda, next onset)``
    pairs that are the only ones legal at a word-internal syllable
    boundary -- see ``restricted_coda_onset_pairs`` above."""
    core_vocabulary_average_syllables: float | None = None
    """A rough, hand-counted average syllable count across this project's
    own core-vocabulary-equivalent word list for this language --
    illustrative, not a rigorous corpus statistic, same honesty standard
    as every other curated field. ``None`` (the common case) means not
    curated -- abstains from the multi-language average entirely, same
    convention as every other field above. Only consulted when
    ``source_language_strictness`` > 0 -- see
    ``generation/lexicon_gen.py``'s ``choose_syllable_count``."""
    onset_frequency_tiers: dict[str, tuple[str, ...]] = {}
    """How often each of this language's own legal onset consonants
    shows up *within* words, once it's in the inventory -- a different
    axis from ``restricted_onset_consonants``/``attested_onset_clusters``
    (which govern whether a symbol/cluster can appear there at all) and
    from ``Consonant.prevalence`` (a single cross-linguistic value used
    for every position alike). Keys are the tier names
    ``"very_common"``/``"common"``/``"uncommon"``/``"rare"``; values are
    the symbols in that tier for this position, judged by **word-type
    productivity** (how many distinct words use this sound here), not
    token/corpus frequency -- those diverge sharply for closed function-
    word classes (real English ``/ð/`` is extremely frequent in running
    text purely via "the/this/that/these/those/then/than/there/they",
    but is one of the *smallest* onset classes by word-type count).
    Covers only symbols actually legal in this position for this
    profile. Empty (the common case) means not curated -- abstains, same
    convention as every other field above. Only consulted when
    ``source_language_strictness`` > 0 -- see
    ``generation/phonology_gen.py``'s ``_resolve_position_multipliers``
    and ``core.phonology.SyllableStructure.onset_symbol_multipliers``."""
    nucleus_frequency_tiers: dict[str, tuple[str, ...]] = {}
    """The nucleus-position mirror of ``onset_frequency_tiers`` -- same
    tier names, same word-type-productivity judgment, covering this
    profile's own vowels."""
    coda_frequency_tiers: dict[str, tuple[str, ...]] = {}
    """The coda-position mirror of ``onset_frequency_tiers``. Frequency
    genuinely differs by position for the same symbol -- e.g. real
    Dutch's ``/x/`` is a rare onset (near loanword-only: chaos, chemie)
    but one of the most productive codas in the language (the
    "-cht"/"-acht" family: nacht, recht, acht) -- which is why this is
    three separate fields rather than one flat per-symbol table."""

    def symbols(self) -> frozenset[str]:
        return frozenset(self.consonants) | frozenset(self.vowels)


def _load_profile(path: Path) -> ReferenceLanguageProfile:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ReferenceLanguageProfile.model_validate(data)


REFERENCE_LANGUAGES: tuple[ReferenceLanguageProfile, ...] = tuple(
    _load_profile(path) for path in sorted(_PROFILES_DIR.glob("*.yaml"))
)


def match_profiles(names: tuple[str, ...]) -> tuple[ReferenceLanguageProfile, ...]:
    """Case-insensitive match against name+aliases; unknown names are
    silently ignored (best-effort, same spirit as everything else
    ``source_languages`` touches)."""
    matched = []
    for raw_name in names:
        needle = raw_name.strip().lower()
        for profile in REFERENCE_LANGUAGES:
            if needle == profile.name.lower() or needle in profile.aliases:
                matched.append(profile)
                break
    return tuple(matched)
