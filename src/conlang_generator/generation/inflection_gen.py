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
from conlang_generator.generation import word_builder

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
