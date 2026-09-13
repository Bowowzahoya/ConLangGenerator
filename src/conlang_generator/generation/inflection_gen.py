"""Case, tense, and subject-agreement affix generation -- the sentence-
role-driven counterpart to ``word_class_gen.py``'s lexeme-fixed citation-
class paradigms (see ``core.grammar.InflectionAffix``'s own docstring for
why the two are deliberately different types sharing only a low-level
mechanism).

Generation here mirrors ``generator.py``'s own two-phase relationship for
``plural_suffix``/``templates``: ``grammar_gen.generate_grammar`` rolls
*which labels* exist (``GrammarProfile.cases``/``tenses``, plus the fixed
5-label agreement set) before the phoneme inventory exists, and the
functions below fill in each label's own actual phonological form once it
does -- called from ``generator.py`` alongside ``word_classes``.

Applying an already-generated affix to a specific word at translation time
(``translation/translator.py``) is ``apply_affix``, a thin wrapper around
``word_builder.attach_affix_and_restress`` -- the same "attach a prefix/
suffix, re-derive stress/word-accent" primitive ``word_class_gen.apply_
word_class`` also calls, extracted there specifically so this module
doesn't need to depend on ``WordClass`` at all.
"""

from __future__ import annotations

import random

from conlang_generator.core.grammar import InflectionAffix
from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure
from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK
from conlang_generator.generation import ipa_tokenizer, phonology_gen, word_builder

_ALL_SINGLE_CHAR_SYMBOLS: frozenset[str] = frozenset(
    s
    for s in tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    if len(s) == 1
)
"""Same "every single-character global symbol, plus only whichever multi-
character symbols this run's own inventory actually has" tokenization
pool ``word_class_gen.py``'s own identically-named constant uses, for the
identical reason (a multi-character global symbol from some unrelated
profile's own palette could otherwise mis-parse two real, adjacent
single-character phonemes at a stem+affix boundary as that unrelated
phoneme instead) -- duplicated locally rather than imported, since it's a
small, self-contained computation and this module otherwise has no
reason to depend on ``word_class_gen.py`` at all."""

AGREEMENT_LABELS: tuple[str, ...] = ("I", "you", "he", "we", "default")
"""The 4 core pronoun glosses this project's own ``lexicon_gen.CORE_
MEANINGS`` actually has, plus ``"default"`` for any non-pronoun/noun
subject -- the real cross-linguistic "3rd person is the unmarked default"
pattern, not an abstract person/number grid this project's own pronoun
set doesn't otherwise use (see ``InflectionAffix.label``'s own
docstring)."""


def generate_case_affixes(
    rng: random.Random, inventory: PhonemeInventory, structure: SyllableStructure, cases: tuple[str, ...]
) -> tuple[InflectionAffix, ...]:
    """One invented suffix per label in ``cases`` -- empty when ``cases``
    is empty (an isolating, or otherwise case-less, language). No harmony
    conditioning: unlike an invented ``WordClass``, these are grammar-
    driven labels, not a phonologically-conditioned allomorph pair."""
    return tuple(
        InflectionAffix(label=case, suffix=word_builder.build_class_suffix(rng, inventory, structure))
        for case in cases
    )


def generate_tense_affixes(
    rng: random.Random, inventory: PhonemeInventory, structure: SyllableStructure, tenses: tuple[str, ...]
) -> tuple[InflectionAffix, ...]:
    """The tense-axis mirror of ``generate_case_affixes`` -- one invented
    suffix per label in ``tenses``."""
    return tuple(
        InflectionAffix(label=tense, suffix=word_builder.build_class_suffix(rng, inventory, structure))
        for tense in tenses
    )


def generate_agreement_affixes(
    rng: random.Random, inventory: PhonemeInventory, structure: SyllableStructure
) -> tuple[InflectionAffix, ...]:
    """One invented suffix per label in ``AGREEMENT_LABELS`` -- unlike
    ``cases``/``tenses``, this axis's own label set is fixed rather than
    independently rolled, so there's no "roll whether this language has
    it at all" step the way case/tense have. A real, if minor,
    simplification: not every real language marks subject agreement on
    the verb at all (Mandarin/Japanese don't) -- illustrative, same
    honesty standard as every other base rate/axis in this project that
    doesn't yet have a curated per-language fact to gate on."""
    return tuple(
        InflectionAffix(label=label, suffix=word_builder.build_class_suffix(rng, inventory, structure))
        for label in AGREEMENT_LABELS
    )


def apply_affix(
    rng: random.Random,
    affix: InflectionAffix | None,
    ipa: str,
    inventory: PhonemeInventory,
    stress_pattern: str,
    stress_deviation_rate: float | None,
    stress_strictness: float,
    word_accent_realization: str = "",
    word_accent_pattern: str = "",
    word_accent_deviation_rate: float | None = None,
    word_accent_length_rate: float | None = None,
    word_accent_window: int | None = None,
) -> str:
    """Attaches ``affix`` (a single case, tense, or agreement label's own
    generated form) onto ``ipa`` and re-derives stress/word-accent on the
    result -- a no-op when ``affix`` is ``None`` or carries no actual
    prefix/suffix. To compose two affixes onto the same word in one call
    (this project's own tense+agreement combination -- see ``core.
    grammar.InflectionAffix``'s own docstring), pass a single synthetic
    ``InflectionAffix`` whose own ``suffix`` is the two labels' suffixes
    concatenated, rather than calling this twice: two calls would
    correctly attach both affixes but re-derive stress twice, wastefully
    (and, for the second call, arguably even incorrectly re-marking an
    already-final position). Tokenizes ``ipa`` the same way ``word_class_
    gen.apply_word_class`` does (every single-character global symbol,
    plus only whichever multi-character symbols this run's own inventory
    actually has), for the identical reason -- see ``_ALL_SINGLE_CHAR_
    SYMBOLS``'s own docstring."""
    if affix is None or not (affix.prefix or affix.suffix):
        return ipa
    known_symbols = tuple(_ALL_SINGLE_CHAR_SYMBOLS | {symbol for symbol in inventory.all_symbols() if len(symbol) > 1})
    stripped = ipa.replace(STRESS_MARK, "").replace(WORD_ACCENT_MARK, "")
    raw_tokens = ipa_tokenizer.tokenize(stripped, known_symbols)
    stem_symbols = tuple(symbol + deco for symbol, deco in raw_tokens)
    return word_builder.attach_affix_and_restress(
        rng, affix.prefix, stem_symbols, affix.suffix, inventory,
        stress_pattern, stress_deviation_rate, stress_strictness,
        word_accent_realization=word_accent_realization,
        word_accent_pattern=word_accent_pattern,
        word_accent_deviation_rate=word_accent_deviation_rate,
        word_accent_length_rate=word_accent_length_rate,
        word_accent_window=word_accent_window,
    )
