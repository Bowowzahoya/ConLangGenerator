"""Seeded citation-form word-class-paradigm generation -- one independent
roll per part of speech. See ``core.grammar.WordClass``'s own docstring for
what a "class" is (real Latin noun declensions, French verb conjugations,
Swahili noun-class prefixes) and why it's deliberately *not* the same
mechanism as ``core.romanization.MuteSuffixRule`` (a class's own prefix/
suffix is genuine phonological content, baked into a word's actual IPA at
coinage time -- not a cosmetic, silent spelling addition).

This is step one of a staged grammar roadmap (part-of-speech labeling +
per-POS word shape here; real inflection -- case/conjugation/agreement --
and LLM-driven sentence construction are later, separate steps).
``core.grammar.GrammarProfile.cases``/``plural_suffix`` stay untouched and
still have no consumer -- those are that later inflection step's own job,
not this one's.

Called once per language, alongside where ``generator.py`` already builds
``plural_suffix`` (reusing the exact same "one syllable via
``word_builder.build_syllable``" precedent) -- a language's own set of
classes is a fixed, whole-language fact, the same way ``plural_suffix``/
``templates``/``cases`` already are, not something re-rolled per word.

``assign_word_class`` (below) picks *which* class a word belongs to --
an unconditioned, per-word roll, appropriate for real lexical/arbitrary
variation. A real phonologically-*conditioned* suffix (Turkish's own
vowel-harmony-agreeing ``-mak``/``-mek`` infinitive, Persian's own
voicing-agreeing ``-tan``/``-dan``) is a genuinely different thing --
not a choice *among* classes, but real allomorphy *within* one class,
resolved from the stem's own phonology rather than rolled -- see
``core.grammar.WordClass.condition`` and ``apply_word_class``'s own
docstring for where and how that resolution actually happens.
"""

from __future__ import annotations

import random

from conlang_generator.core.grammar import WordClass
from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure, VowelBackness
from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import ipa_tokenizer, phonology_gen, word_accent_gen, word_builder
from conlang_generator.generation.reference_languages import match_profiles
from conlang_generator.generation.trait_bias import biased_probability

_ALL_PARTS_OF_SPEECH = tuple(PartOfSpeech)
_ALL_SYMBOLS: tuple[str, ...] = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(
    v.ipa for v in phonology_gen.ALL_VOWELS
)
"""The full global phoneme pool's own symbols -- see ``apply_word_class``'s
own docstring for why tokenization needs this rather than just a
specific run's own generated ``PhonemeInventory``."""
_VOWEL_BACKNESS: dict[str, VowelBackness] = {v.ipa: v.backness for v in phonology_gen.ALL_VOWELS}
_CONSONANT_VOICED: dict[str, bool] = {c.ipa: c.voiced for c in phonology_gen.ALL_CONSONANTS}
"""Looked up against the same *global* pool ``_ALL_SYMBOLS`` already
tokenizes against (not just a specific run's own ``PhonemeInventory``),
for the same reason -- see ``WordClass.condition``'s own docstring for
what these resolve (vowel-harmony backness, final-consonant voicing)."""

# Real, well-documented cross-linguistic asymmetry: multi-class citation-
# form paradigms (declension, conjugation, noun-class agreement) are
# heavily concentrated in nouns/verbs/adjectives; pronouns/particles/
# numerals/other overwhelmingly don't vary in citation shape by class the
# same way (most are either invariant or irregular/suppletive rather than
# following a regular paradigm). Illustrative base rates, not a corpus
# statistic -- same honesty standard as every other base rate in this
# project (e.g. grammar_gen.py's own `_ROOT_AND_PATTERN_BASE_RATE`).
_INVENTED_CLASS_BASE_RATE: dict[PartOfSpeech, float] = {
    PartOfSpeech.NOUN: 0.22,
    PartOfSpeech.VERB: 0.20,
    PartOfSpeech.ADJECTIVE: 0.12,
    PartOfSpeech.PRONOUN: 0.03,
    PartOfSpeech.PARTICLE: 0.02,
    PartOfSpeech.NUMERAL: 0.02,
    PartOfSpeech.OTHER: 0.05,
}
_MIN_INVENTED_CLASSES = 2
_MAX_INVENTED_CLASSES = 4
_MIN_CLASS_PREVALENCE = 0.3
_MAX_CLASS_PREVALENCE = 1.0
_REFERENCE_ADOPTION_RATE = 0.7
"""Same "usually, not always, adopt the matched language's own real
convention" weight ``romanization_gen.py``'s own
``_REFERENCE_ORTHOGRAPHY_WEIGHT`` already uses for reused orthography
rules/onset-nucleus pairs."""
_GENERIC_DEVIATION_RATE = 0.08
"""Illustrative fallback when some POS got more than one class but no
matched reference profile curates its own real rate -- most words follow
their own assigned class; a modest minority are irregular/suppletive,
the same "sensible generic baseline" role
``stress_gen._GENERIC_STRESS_DEVIATION_RATE`` already plays."""


def generate_word_classes(
    rng: random.Random,
    spec: GenerationSpec,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    uses_root_and_pattern: bool,
) -> tuple[tuple[WordClass, ...], float | None]:
    """Returns this language's own ``(word_classes, word_class_deviation_
    rate)``. Root-and-pattern languages (``uses_root_and_pattern``) never
    get *invented* classes -- real Semitic morphology's own case/gender
    system interacts with root-and-pattern derivation in ways well beyond
    this step's scope, left an explicit boundary rather than solved here
    -- but a matched reference profile's own curated classes are still
    honored regardless, the same way ``root_and_pattern`` matching doesn't
    otherwise gate any of this module's own reference-adoption logic."""
    traits = spec.traits
    reference_profiles = match_profiles(traits.source_languages)
    strictness = traits.source_language_strictness if reference_profiles else 0.0

    classes: list[WordClass] = []
    any_multi_class = False
    for pos in _ALL_PARTS_OF_SPEECH:
        reference_classes = tuple(c for p in reference_profiles for c in p.word_classes if c.pos is pos)
        if reference_classes:
            adoption_rate = _REFERENCE_ADOPTION_RATE
            if strictness > 0.0:
                adoption_rate = biased_probability(adoption_rate, strictness)
            if rng.random() < adoption_rate:
                classes.extend(reference_classes)
                if len(reference_classes) > 1:
                    any_multi_class = True
            # A failed adoption roll means this POS simply gets no class
            # marking this run -- not a fallback to invented classes, the
            # same "the roll either gives you the real thing or nothing"
            # shape `_roll_grammatical_spelling`'s own mute-suffix reuse
            # already has.
            continue
        if uses_root_and_pattern:
            continue
        base_rate = _INVENTED_CLASS_BASE_RATE[pos]
        if rng.random() >= base_rate:
            continue
        num_classes = rng.randint(_MIN_INVENTED_CLASSES, _MAX_INVENTED_CLASSES)
        # No cross-linguistic tendency to lean on for "prefixing vs.
        # suffixing" absent a reference match -- a flat coin flip, the
        # same honesty `grammar_gen.py`'s own `has_articles`/
        # `adjective_after_noun` rolls already have.
        is_prefixing = rng.random() < 0.5
        for i in range(num_classes):
            name = f"{pos.value} class {i + 1}"
            prevalence = rng.uniform(_MIN_CLASS_PREVALENCE, _MAX_CLASS_PREVALENCE)
            if is_prefixing:
                affix = word_builder.build_class_prefix(rng, inventory, structure)
                classes.append(WordClass(name=name, pos=pos, prefix=affix, prevalence=prevalence))
            else:
                affix = word_builder.build_class_suffix(rng, inventory, structure)
                classes.append(WordClass(name=name, pos=pos, suffix=affix, prevalence=prevalence))
        any_multi_class = True

    if not any_multi_class:
        return tuple(classes), None
    deviation_rate = next(
        (p.word_class_deviation_rate for p in reference_profiles if p.word_class_deviation_rate is not None),
        _GENERIC_DEVIATION_RATE,
    )
    return tuple(classes), deviation_rate


def assign_word_class(
    rng: random.Random,
    word_classes: tuple[WordClass, ...],
    deviation_rate: float | None,
    pos: PartOfSpeech,
) -> WordClass | None:
    """Picks this word's own class (weighted by ``WordClass.prevalence``,
    the same role ``Consonant``/``Vowel.prevalence`` already play
    elsewhere -- a plain ``rng.choices`` here rather than
    ``word_builder.weighted_choice``, which is coupled to phoneme objects
    specifically via their own ``.ipa`` attribute), or ``None`` when this
    POS has no classes at all, or the ``deviation_rate`` roll makes this
    word an irregular exception (the same ``rng.random() < rate`` shape
    every other deviation-rate consumer in this project already uses)."""
    classes = tuple(c for c in word_classes if c.pos is pos)
    if not classes:
        return None
    if deviation_rate is not None and rng.random() < deviation_rate:
        return None
    return rng.choices(classes, weights=[c.prevalence for c in classes])[0]


def _resolve_harmony_backness(bare_stem_symbols: tuple[str, ...]) -> VowelBackness:
    """This stem's own harmony class -- see ``WordClass.condition``'s own
    ``"vowel_harmony"`` docstring for the exact rule (last non-``CENTRAL``
    vowel, scanning from the end; ``BACK`` when the stem has none)."""
    for symbol in reversed(bare_stem_symbols):
        backness = _VOWEL_BACKNESS.get(symbol)
        if backness is not None and backness is not VowelBackness.CENTRAL:
            return backness
    return VowelBackness.BACK


def _resolve_final_voiced(bare_stem_symbols: tuple[str, ...]) -> bool | None:
    """Whether this stem's own final segment is a voiced consonant -- see
    ``WordClass.condition``'s own ``"final_voicing"`` docstring. ``None``
    when the stem is vowel-final (no final consonant to condition on) or,
    degenerately, empty."""
    if not bare_stem_symbols:
        return None
    return _CONSONANT_VOICED.get(bare_stem_symbols[-1])


def _resolve_conditioned_suffix(word_class: WordClass, bare_stem_symbols: tuple[str, ...]) -> tuple[str, ...]:
    """The class's own actually-applicable ``suffix``, resolving
    ``condition``-based allomorphy (if any) against the real stem it's
    about to attach to. A no-op (returns ``word_class.suffix`` unchanged)
    for an ordinary, unconditioned class."""
    if word_class.condition == "vowel_harmony":
        backness = _resolve_harmony_backness(bare_stem_symbols)
        return word_class.suffix if backness is VowelBackness.FRONT else word_class.suffix_alt
    if word_class.condition == "final_voicing":
        voiced = _resolve_final_voiced(bare_stem_symbols)
        if voiced:
            return word_class.suffix_alt
        return word_class.suffix
    return word_class.suffix


def _resolve_position_classes(rng: random.Random, word_class: WordClass) -> tuple[str, ...]:
    """This class's own composite position-class prefix -- one
    independently weighted-rolled option's symbols from each slot in
    ``word_class.position_classes``, in order (real Navajo-style
    polysynthetic verb-prefix structure -- see that field's own
    docstring). Empty when ``position_classes`` is empty, the ordinary
    case."""
    resolved: list[str] = []
    for slot in word_class.position_classes:
        option = rng.choices(slot.options, weights=[o.prevalence for o in slot.options])[0]
        resolved.extend(option.symbols)
    return tuple(resolved)


def apply_word_class(
    rng: random.Random,
    word_class: WordClass | None,
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
    """Concatenates the assigned class's own literal prefix/suffix
    phonemes onto ``ipa`` -- real phonological content from this point
    on, riding through ``RomanizationScheme.apply()`` and every later
    sound-change rule exactly like any other phoneme in the word. A
    no-op when ``word_class`` is ``None`` or carries no actual prefix/
    suffix (an "unmarked" class, e.g. German's own real masculine/
    neuter nouns -- see german.yaml).

    Critically, this *re-derives* stress (and word accent) on the full,
    now-longer word rather than trusting whatever ``ipa`` already had
    baked in: a real position-dependent pattern (French's own real
    final-syllable stress being the clearest case) would otherwise still
    land on the *stem's* own former final syllable, no longer the word's
    true final syllable once a vowel-bearing suffix syllable follows it.
    Strips ``STRESS_MARK``/``WORD_ACCENT_MARK`` from ``ipa``, re-
    tokenizes the raw phonemes against this run's own inventory (so a
    multi-character symbol like "kʰ" or "aː" stays one unit, not several
    characters), concatenates prefix + stem + suffix, and re-marks the
    whole thing via ``word_accent_gen.mark_stress_and_word_accent`` --
    the same flat-symbol-sequence marking mechanism
    ``root_pattern.propose_templatic_word``/``sound_change.py``'s own
    templatic coining already use for a word with no per-syllable build
    loop of its own.

    Known gap, left unsolved for this first pass: a tone mark (if any)
    stays attached to whichever base vowel it was already on in the
    stem (``ipa_tokenizer.tokenize`` preserves trailing combining
    marks), but a *new* vowel contributed by the suffix/prefix itself
    gets no tone mark of its own. None of this batch's own validation
    profiles combine tone with word classes (Mandarin has no word
    classes; Swahili isn't tonal), so this doesn't surface there -- a
    real future affix-tone interaction, not forgotten, just genuinely
    out of this step's scope.

    Tokenizes against the *full global* phoneme pool
    (``phonology_gen.ALL_CONSONANTS``/``ALL_VOWELS``), not just
    ``inventory``'s own generated symbols -- deliberately: a root-and-
    pattern word's own literal template characters (real Arabic's own
    "m-" place-noun prefix, hardcoded in ``root_pattern.generate_
    templates()`` regardless of what this run's inventory happens to
    contain) aren't guaranteed to already be members of ``inventory``
    itself, and tokenizing against too narrow a symbol set would
    silently drop them (``ipa_tokenizer.tokenize``'s own documented
    behavior for an unrecognized character).

    When ``word_class.condition`` is set, the suffix actually used isn't
    ``word_class.suffix`` verbatim -- it's resolved against the real
    stem's own bare (decoration-stripped) symbols via
    ``_resolve_conditioned_suffix`` (real Turkish/Finnish/Mongolian
    vowel-harmony agreement, or real Persian final-consonant-voicing
    agreement -- see ``WordClass.condition``'s own docstring). This is
    exactly why class *selection* (``assign_word_class``) and suffix
    *resolution* (here) are different steps at different times: which
    grammatical class a word belongs to is a per-word roll unrelated to
    the stem's own phonology, but which surface allomorph that class's
    own suffix takes is not a roll at all -- it's read directly off the
    one stem it's actually attaching to, which only exists by the time
    this function runs.

    ``word_class.position_classes``, when non-empty, contributes a
    further composite prefix ahead of ``word_class.prefix`` -- one
    independently weighted-rolled option per slot, via
    ``_resolve_position_classes`` (real Navajo-style polysynthetic
    verb-prefix structure -- see ``WordClass.position_classes``'s own
    docstring). Unlike the ``condition`` resolution above, this doesn't
    read anything off the stem -- each slot's own roll is unconditioned,
    the same "independent per-word roll" shape ``assign_word_class``'s
    own class selection already has, just repeated once per slot instead
    of once for the whole class."""
    if word_class is None or not (word_class.prefix or word_class.suffix or word_class.position_classes):
        return ipa
    known_symbols = _ALL_SYMBOLS
    stripped = ipa.replace(STRESS_MARK, "").replace(WORD_ACCENT_MARK, "")
    raw_tokens = ipa_tokenizer.tokenize(stripped, known_symbols)
    stem_symbols = tuple(symbol + deco for symbol, deco in raw_tokens)
    suffix = _resolve_conditioned_suffix(word_class, tuple(symbol for symbol, _ in raw_tokens))
    position_prefix = _resolve_position_classes(rng, word_class)
    filled_symbols = position_prefix + word_class.prefix + stem_symbols + suffix
    vowel_symbols = frozenset(inventory.vowel_symbols())
    return word_accent_gen.mark_stress_and_word_accent(
        rng, filled_symbols, vowel_symbols, stress_pattern, stress_deviation_rate, stress_strictness,
        word_accent_realization=word_accent_realization,
        word_accent_pattern=word_accent_pattern,
        word_accent_deviation_rate=word_accent_deviation_rate,
        word_accent_length_rate=word_accent_length_rate,
        word_accent_window=word_accent_window,
    )
