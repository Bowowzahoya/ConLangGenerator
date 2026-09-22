"""Named, holistic word-internal phonological rules -- the ones a per-symbol,
single-neighbor-conditioned mechanism (``core.romanization.RomanizationRule``'s
own ``preceding``/``following``) genuinely can't express, because they need
to scan a word's *whole* syllable sequence rather than one adjacent symbol.
Dispatched by ``ReferenceLanguageProfile.word_level_phonology`` (see its own
docstring for exactly where and when this runs relative to stress
assignment and affixation) -- one function per named rule, ``apply()`` is
the only public entry point.

Operates on the same ``(onset, nucleus, coda)`` syllable-tuple list
``word_builder.build_word`` already assembles internally, *not* on a flat
IPA string re-tokenized after the fact: each syllable's own onset/coda
split was already an unambiguous decision made while that syllable was
built, so working at this level sidesteps the maximal-onset resyllabification
ambiguity a flat-string rewrite would have to re-solve from scratch.
"""

from __future__ import annotations

from conlang_generator.core.phonology import SyllableStructure

Syllable = tuple[tuple[str, ...], str, tuple[str, ...]]

_SCHWA = "ə"
_BENGALI_INHERENT_VOWEL = "ɔ"


def apply(syllables: list[Syllable], rule: str, structure: SyllableStructure) -> list[Syllable]:
    """``syllables`` with ``rule`` applied (unchanged for ``""`` or an
    unrecognized name -- the same "abstain rather than crash on an
    uncurated/typo'd value" convention every other string-keyed profile
    field in this project already follows, e.g. ``stress_pattern``)."""
    if rule == "hindi_schwa_deletion":
        return _delete_inherent_vowel(syllables, structure, _SCHWA, allow_medial=True)
    if rule == "bengali_final_vowel_deletion":
        return _delete_inherent_vowel(syllables, structure, _BENGALI_INHERENT_VOWEL, allow_medial=False)
    if rule == "korean_assimilation":
        return _apply_korean_assimilation(syllables, structure)
    return syllables


def _delete_inherent_vowel(
    syllables: list[Syllable], structure: SyllableStructure, inherent_vowel: str, allow_medial: bool
) -> list[Syllable]:
    """The standard computational formulation of Hindi schwa deletion
    (Ohala 1983; Narasimhan, Sproat & Kiraz 2004's own widely-cited
    ``ə -> ∅ / VC_CV`` rule, as implemented in essentially every Hindi
    grapheme-to-phoneme system): a word's own *citation*-form spelling
    gives every consonant an inherent vowel by default (the real
    Devanagari akṣara convention this project's syllable-by-syllable
    generation already mirrors), and deletion then removes some of them
    to reach the real pronounced form.

    Word-final: the last syllable's own inherent vowel always deletes
    (real "nagar" from underlying na-ga-ra, never a bare word-final
    schwa/inherent-vowel in real spoken Hindi) -- unless this is the
    word's *only* syllable, since a word needs at least one nucleus.

    Medial (``allow_medial`` -- Hindi only, see below): scanning
    right-to-left, an internal syllable's own inherent vowel deletes when
    the syllable immediately to its *left* is itself closed (has a coda)
    -- the rule's own "VC" left-context; the "CV" right-context is
    trivially satisfied by any internal syllable (it's followed by an
    ordinary onset+vowel by definition), so the left-context check is the
    one this function actually needs to make. This is what real Hindi
    "dharm"/"mitr"-style closed-medial-syllable words come from (an
    underlying tri-syllabic C-schwa-C-schwa-C-schwa collapsing to one
    syllable once both its own inherent vowels delete).

    Bengali's own real facts are far less confidently documented for this
    project's own honesty standard (its inherent vowel /ɔ/ has its own,
    *different* realization/deletion pattern, and I don't have a citable
    formal medial rule the way Hindi has one) -- so ``allow_medial=False``
    keeps Bengali to only the one fact this project is confident about:
    real Bengali citation-form nouns of 2+ syllables regularly drop a
    word-final inherent vowel the same way Hindi's own final syllable
    does (see ``bengali.yaml``'s own comment on this).

    Every deletion is checked against ``structure.is_valid_syllable``
    before committing (the resulting merged coda has to actually be a
    legal cluster for this language) and simply skipped, not forced
    through, when it isn't -- the same "abstain rather than fabricate an
    illegal form" discipline ``word_builder._STRESS_REDUCTION_RATE``'s own
    legality check already practices."""
    if len(syllables) <= 1:
        return syllables
    syls = list(syllables)

    def merge_into_previous(index: int) -> bool:
        prev_onset, prev_nucleus, prev_coda = syls[index - 1]
        cur_onset, _, cur_coda = syls[index]
        new_coda = prev_coda + cur_onset + cur_coda
        is_final = index == len(syls) - 1
        is_initial = index - 1 == 0
        if not structure.is_valid_syllable(prev_onset, prev_nucleus, new_coda, is_final, is_initial):
            return False
        syls[index - 1] = (prev_onset, prev_nucleus, new_coda)
        del syls[index]
        return True

    if syls[-1][1] == inherent_vowel:
        merge_into_previous(len(syls) - 1)

    if allow_medial:
        i = len(syls) - 2
        while i >= 1:  # the word's own first syllable is never a deletion target
            if syls[i][1] == inherent_vowel and syls[i - 1][2]:  # preceding syllable is closed
                merge_into_previous(i)
            i -= 1

    return syls


# Real Korean coda neutralization (this profile's own "seven-consonant
# rule", already enforced by korean.yaml's restricted_coda_consonants)
# means a generated word's own coda, wherever this function looks at one,
# is always already one of exactly these seven -- the same real surface
# inventory the assimilation rules below are stated over.
_HOMORGANIC_NASAL = {"p": "m", "t": "n", "k": "ŋ"}
"""Nasalization (비음화): an obstruent-stop coda followed by a nasal-onset
next syllable becomes that nasal's own place of articulation -- real 국물
gungmul "soup" (/k/+/m/ -> [ŋ]+[m]), 앞문 apmun "front door" (/p/+/m/ ->
[m]+[m]), 낱말 nanmal "word" (/t/+/n/ -> [n]+[n]). A productive, largely
exceptionless low-level phonetic rule (unlike palatalization, below),
triggered purely by the coda/onset pair -- no morpheme-boundary condition
to track."""

_TENSE_COUNTERPART = {"p": "pʼ", "t": "tʼ", "k": "kʼ", "tʃ": "tʃʼ"}
"""Tensification (경음화): an obstruent-stop coda followed by a plain
obstruent onset makes that onset tense -- real 학교 hakgyo "school"
(/k/+/k/ -> [k]+[kʼ]), 잡지 japji "magazine" (/p/+/tʃ/ -> [p]+[tʃʼ]).
Real Korean also tensifies a following /s/ (ㅆ), but this project's own
Korean profile doesn't model a distinct tense /s/ at all, so that one
member of the real series stays out of reach for the same "no symbol to
render it with" reason a handful of other profiles' own gaps already
have."""


def _apply_korean_assimilation(syllables: list[Syllable], structure: SyllableStructure) -> list[Syllable]:
    """Cross-syllable consonant assimilation at a coda/onset boundary --
    real Korean pronunciation regularly differs from what its own
    syllable blocks would suggest read one at a time. Unlike Hindi/Bengali
    inherent-vowel deletion above, this never changes syllable count or
    which nucleus is where -- it only ever rewrites one coda or onset
    consonant's own identity, so it's safe to scan every adjacent syllable
    pair once, left to right, independently.

    Three real, purely phonetically-conditioned rules (see
    ``_HOMORGANIC_NASAL``/``_TENSE_COUNTERPART``'s own docstrings for
    nasalization/tensification, and the lateralization branch below for
    real 신라 Silla -> [실라] sil-la / 칼날 kalnal -> [칼랄] kal-lal, /n/+/l/
    and /l/+/n/ both converging on /l/+/l/ regardless of direction). Their
    own trigger conditions are mutually exclusive (nasalization keys on the
    *onset* being nasal, tensification on it being a plain obstruent,
    lateralization on the pair being exactly {n, l}), so there's no
    ordering question between them -- at most one ever matches a given
    pair.

    Deliberately **not** modeled: real Korean palatalization (같이 gachi
    "together", from an underlying /t/+/i/) -- unlike the three rules
    above, that one is conditioned on a specific morpheme boundary (a
    t/tʰ-final root meeting an i-initial grammatical suffix/particle), not
    a purely phonetic environment, the same "needs live morphology this
    project doesn't have" gap the wider word-level-phonology survey
    already declined for Welsh mutation/Japanese rendaku/Arabic-Hebrew
    article assimilation.

    Every rewrite is checked against ``structure.is_valid_syllable``
    before committing and simply skipped, not forced through, when the
    result wouldn't actually be legal for this language -- the same
    "abstain rather than fabricate" discipline the inherent-vowel-deletion
    rules above already practice."""
    syls = list(syllables)
    for i in range(len(syls) - 1):
        onset, nucleus, coda = syls[i]
        next_onset, next_nucleus, next_coda = syls[i + 1]
        if not coda or not next_onset:
            continue
        c1, c2 = coda[-1], next_onset[0]
        new_c1, new_c2 = c1, c2
        if c1 in _HOMORGANIC_NASAL and c2 in ("m", "n"):
            new_c1 = _HOMORGANIC_NASAL[c1]
        elif {c1, c2} == {"n", "l"}:
            new_c1, new_c2 = "l", "l"
        elif c1 in _TENSE_COUNTERPART and c2 in _TENSE_COUNTERPART:
            new_c2 = _TENSE_COUNTERPART[c2]
        if new_c1 == c1 and new_c2 == c2:
            continue
        new_coda = coda[:-1] + (new_c1,)
        new_next_onset = (new_c2,) + next_onset[1:]
        if not structure.is_valid_syllable(onset, nucleus, new_coda, False, i == 0) or not structure.is_valid_syllable(
            new_next_onset, next_nucleus, next_coda, i + 1 == len(syls) - 1, False
        ):
            continue
        syls[i] = (onset, nucleus, new_coda)
        syls[i + 1] = (new_next_onset, next_nucleus, next_coda)
    return syls
