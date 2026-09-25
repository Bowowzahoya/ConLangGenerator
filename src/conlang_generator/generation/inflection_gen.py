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


def generate_number_affixes(
    rng: random.Random, inventory: PhonemeInventory, structure: SyllableStructure
) -> tuple[InflectionAffix, ...]:
    """The single plural suffix (singular is the unmarked bare form)."""
    return (InflectionAffix(label="plural", suffix=word_builder.build_class_suffix(rng, inventory, structure)),)


def generate_mood_affixes(
    rng: random.Random, inventory: PhonemeInventory, structure: SyllableStructure
) -> tuple[InflectionAffix, ...]:
    """The single imperative suffix (indicative is the unmarked form)."""
    return (InflectionAffix(label="imperative", suffix=word_builder.build_class_suffix(rng, inventory, structure)),)


def generate_question_particle(
    rng: random.Random, inventory: PhonemeInventory, structure: SyllableStructure
) -> str:
    """The IPA of a free yes/no question particle -- one legal
    syllable, so it is a pronounceable standalone word."""
    return word_builder.build_syllable(rng, inventory, structure)


ASPECT_SYSTEMS: tuple[tuple[str, ...], ...] = (
    (),
    ("perfective", "imperfective"),
    ("perfective", "progressive", "perfect", "habitual"),
)
MOOD_SYSTEMS: tuple[tuple[str, ...], ...] = (
    (),
    ("irrealis",),
    ("subjunctive", "conditional", "potential"),
)


def roll_aspects(rng: random.Random) -> tuple[str, ...]:
    """No aspect (25%), two-way (45%) or four-way (30%) -- illustrative, like
    the tense roll (no curated per-language aspect facts to lean on)."""
    roll = rng.random()
    return ASPECT_SYSTEMS[0] if roll < 0.25 else ASPECT_SYSTEMS[1] if roll < 0.7 else ASPECT_SYSTEMS[2]


def roll_moods(rng: random.Random) -> tuple[str, ...]:
    """No verbal mood (30%), just irrealis (35%) or subjunctive/conditional/
    potential (35%)."""
    roll = rng.random()
    return MOOD_SYSTEMS[0] if roll < 0.3 else MOOD_SYSTEMS[1] if roll < 0.65 else MOOD_SYSTEMS[2]


def distinct_suffixes(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    labels: tuple[str, ...],
    taken: frozenset[tuple[str, ...]],
) -> tuple[InflectionAffix, ...]:
    """One invented suffix per label, re-drawn (up to 30 times) while it
    equals one already ``taken`` (by another label of the verb paradigm), so
    that aspect and mood labels are actually distinguishable in the output.
    With a very small inventory the last draw is accepted as-is."""
    used = set(taken)
    affixes: list[InflectionAffix] = []
    for label in labels:
        suffix = word_builder.build_class_suffix(rng, inventory, structure)
        for _ in range(30):
            if suffix not in used:
                break
            suffix = word_builder.build_class_suffix(rng, inventory, structure)
        used.add(suffix)
        affixes.append(InflectionAffix(label=label, suffix=suffix))
    return tuple(affixes)


def generate_aspect_affixes(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    aspects: tuple[str, ...],
    taken: frozenset[tuple[str, ...]] = frozenset(),
) -> tuple[InflectionAffix, ...]:
    """One invented suffix per aspect label, distinct from each other and
    from ``taken`` (the verb paradigm's other suffixes)."""
    return distinct_suffixes(rng, inventory, structure, aspects, taken)


def generate_verbal_mood_affixes(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    moods: tuple[str, ...],
    taken: frozenset[tuple[str, ...]] = frozenset(),
) -> tuple[InflectionAffix, ...]:
    """One invented suffix per verbal mood label (not the imperative, which
    ``generate_mood_affixes`` makes), distinct like ``generate_aspect_affixes``."""
    return distinct_suffixes(rng, inventory, structure, moods, taken)


VOICE_SYSTEMS_NOM_ACC: tuple[tuple[str, ...], ...] = ((), ("passive",), ("passive", "causative"))
_VOICE_WEIGHTS_NOM_ACC = (0.15, 0.50, 0.35)
VOICE_SYSTEMS_ERGATIVE: tuple[tuple[str, ...], ...] = (
    (),
    ("antipassive",),
    ("antipassive", "causative"),
    ("passive", "antipassive"),
)
_VOICE_WEIGHTS_ERGATIVE = (0.15, 0.35, 0.25, 0.25)


def roll_voices(rng: random.Random, ergative: bool) -> tuple[str, ...]:
    """A voice system: none, passive (+ causative) in a nominative-accusative
    language; none, antipassive (+ causative or passive) in an ergative one --
    the antipassive being the ergative languages' typical detransitivizer."""
    systems = VOICE_SYSTEMS_ERGATIVE if ergative else VOICE_SYSTEMS_NOM_ACC
    weights = _VOICE_WEIGHTS_ERGATIVE if ergative else _VOICE_WEIGHTS_NOM_ACC
    return rng.choices(systems, weights=weights)[0]


def generate_voice_affixes(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    voices: tuple[str, ...],
    taken: frozenset[tuple[str, ...]] = frozenset(),
) -> tuple[InflectionAffix, ...]:
    """One invented suffix per voice label, distinct like the aspect ones."""
    return distinct_suffixes(rng, inventory, structure, voices, taken)


def _insert_infix(stem_symbols, raw_tokens, affix: InflectionAffix, inventory: PhonemeInventory):
    """``stem_symbols`` with ``affix.infix`` put after the first consonant (at the very start of
    a vowel-initial stem) or before the last vowel (at the end of a vowelless one)."""
    vowels = set(inventory.vowel_symbols()) | {
        symbol for symbol, _ in raw_tokens if symbol and symbol[0] in "aeiouəɛɔɪʊɐɑæøyɨɯɤ"
    }
    is_vowel = [symbol in vowels for symbol, _ in raw_tokens]
    if affix.infix_at == "before_last_vowel":
        vowel_positions = [i for i, v in enumerate(is_vowel) if v]
        at = vowel_positions[-1] if vowel_positions else len(stem_symbols)
    else:
        at = 1 if stem_symbols and not is_vowel[0] else 0
    return stem_symbols[:at] + tuple(affix.infix) + stem_symbols[at:]


_KNOWN_SYMBOLS_CACHE: dict[int, tuple[object, tuple[str, ...]]] = {}


def _known_symbols_for(inventory: PhonemeInventory) -> tuple[str, ...]:
    """The tokenizer's symbol set for ``inventory`` -- the single-character pool
    plus its multi-character phonemes -- computed once per inventory (the cache
    holds the inventory, so an id is never reused while it is cached)."""
    cached = _KNOWN_SYMBOLS_CACHE.get(id(inventory))
    if cached is not None and cached[0] is inventory:
        return cached[1]
    known = tuple(_ALL_SINGLE_CHAR_SYMBOLS | {symbol for symbol in inventory.all_symbols() if len(symbol) > 1})
    if len(_KNOWN_SYMBOLS_CACHE) >= 32:
        _KNOWN_SYMBOLS_CACHE.clear()
    _KNOWN_SYMBOLS_CACHE[id(inventory)] = (inventory, known)
    return known


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
    if affix is None or not (affix.prefix or affix.suffix or affix.infix):
        return ipa
    known_symbols = _known_symbols_for(inventory)
    stripped = ipa.replace(STRESS_MARK, "").replace(WORD_ACCENT_MARK, "")
    raw_tokens = ipa_tokenizer.tokenize(stripped, known_symbols)
    stem_symbols = tuple(symbol + deco for symbol, deco in raw_tokens)
    if affix.infix:
        stem_symbols = _insert_infix(stem_symbols, raw_tokens, affix, inventory)
    return word_builder.attach_affix_and_restress(
        rng, affix.prefix, stem_symbols, affix.suffix, inventory,
        stress_pattern, stress_deviation_rate, stress_strictness,
        word_accent_realization=word_accent_realization,
        word_accent_pattern=word_accent_pattern,
        word_accent_deviation_rate=word_accent_deviation_rate,
        word_accent_length_rate=word_accent_length_rate,
        word_accent_window=word_accent_window,
    )


# ---------------------------------------------------------------------------
# Aspect/mood follow-ups: evidentiality, negation strategy, prohibitives,
# auxiliary (periphrastic) tenses/aspects/moods, and suffix collisions.
# ---------------------------------------------------------------------------

EVIDENTIAL_SYSTEMS: tuple[tuple[str, ...], ...] = (
    (),
    ("reported",),
    ("inferred", "reported"),
    ("witnessed", "inferred", "reported"),
)
_EVIDENTIAL_WEIGHTS = (0.55, 0.15, 0.15, 0.15)
NEGATION_STRATEGIES = (("particle", 0.55), ("affix", 0.25), ("both", 0.20))
PERIPHRASTIC_CANDIDATES = (
    "past", "future", "perfective", "imperfective", "progressive", "perfect", "habitual",
    "irrealis", "subjunctive", "conditional", "potential",
)
"""The labels a language may express with an auxiliary word (only those it
actually has are kept)."""
_PERIPHRASTIC_RATE = 0.25
AUXILIARY_GLOSS_PREFIX = "aux-"


def roll_aspect_followups(rng: random.Random, grammar) -> dict[str, object]:
    """Rolls for evidentiality, negation strategy, a prohibitive, periphrastic
    labels and their position (every draw always made, so the count never
    depends on the grammar)."""
    roll = rng.random()
    cumulative = 0.0
    evidentials = EVIDENTIAL_SYSTEMS[0]
    for system, weight in zip(EVIDENTIAL_SYSTEMS, _EVIDENTIAL_WEIGHTS):
        cumulative += weight
        if roll < cumulative:
            evidentials = system
            break
    roll = rng.random()
    cumulative = 0.0
    strategy = NEGATION_STRATEGIES[-1][0]
    for label, weight in NEGATION_STRATEGIES:
        cumulative += weight
        if roll < cumulative:
            strategy = label
            break
    prohibitive = rng.random() < 0.30
    drawn = [rng.random() < _PERIPHRASTIC_RATE for _ in PERIPHRASTIC_CANDIDATES]
    available = {*grammar.tenses, *grammar.aspects, *grammar.moods}
    periphrastic = tuple(
        label for label, hit in zip(PERIPHRASTIC_CANDIDATES, drawn) if hit and label in available
    )
    position = "after" if rng.random() < 0.5 else "before"
    return {
        "evidentials": evidentials,
        "negation_strategy": strategy,
        "prohibitive": prohibitive,
        "periphrastic_labels": periphrastic,
        "auxiliary_position": position,
    }


_VERB_SUFFIX_FIELDS = (
    "tense_affixes", "agreement_affixes", "object_agreement_affixes", "mood_affixes", "aspect_affixes",
    "voice_affixes", "verb_number_affixes", "verb_polite_affixes", "verb_form_affixes", "evidential_affixes",
    "verb_negative_affixes",
)
_NOUN_SUFFIX_FIELDS = (
    "case_affixes", "number_affixes", "class_marker_affixes", "possession_affixes", "possessor_person_affixes",
)
_MODIFIER_SUFFIX_FIELDS = ("class_affixes", "degree_affixes")


def resolve_collisions(
    rng: random.Random, inventory: PhonemeInventory, structure: SyllableStructure, grammar, romanization=None
):
    """Re-draws any affix that is spelled like an earlier one that can occur on the
    same kind of word (verb, noun, adjective), so no two labels of a paradigm collapse
    into one form. The first occurrence keeps its exponent, so only actual collisions
    change: a suffix-only affix gets a new suffix (a longer one when the short shapes
    are used up), a prefixed or circumfixed one a new prefix, an infixed one a new
    infix. With ``romanization``, exponents spelled alike (a different phoneme with the
    same letter) count as colliding."""

    def spelled(symbols: tuple[str, ...]):
        if not symbols:
            return ""
        return romanization.apply("".join(symbols)).lower() if romanization is not None else symbols

    def key(affix: InflectionAffix):
        return (spelled(affix.prefix), spelled(affix.infix), spelled(affix.suffix))

    def redraw(affix: InflectionAffix, used: set) -> InflectionAffix:
        for attempt in range(120):
            if affix.prefix:
                onset, nucleus, _coda = word_builder._build_syllable_parts(rng, inventory, structure)
                candidate = affix.model_copy(update={"prefix": tuple(onset[:1]) + (nucleus,)})
            elif affix.infix:
                candidate = affix.model_copy(update={"infix": word_builder.build_class_suffix(rng, inventory, structure)})
            else:
                suffix = word_builder.build_class_suffix(rng, inventory, structure)
                for _ in range(attempt // 30):  # the short shapes are used up: allow a longer suffix
                    suffix = suffix + word_builder.build_class_suffix(rng, inventory, structure)
                candidate = affix.model_copy(update={"suffix": suffix})
            if key(candidate) not in used:
                return candidate
        return candidate

    updates: dict[str, tuple] = {}
    for fields in (_VERB_SUFFIX_FIELDS, _NOUN_SUFFIX_FIELDS, _MODIFIER_SUFFIX_FIELDS):
        used: set = set()
        for name in fields:
            affixes = getattr(grammar, name, ())
            changed = False
            fixed = []
            for affix in affixes:
                if not (affix.prefix or affix.suffix or affix.infix):
                    fixed.append(affix)
                    continue
                if key(affix) in used:
                    affix = redraw(affix, used)
                    changed = True
                used.add(key(affix))
                fixed.append(affix)
            if changed:
                updates[name] = tuple(fixed)
    return grammar.model_copy(update=updates) if updates else grammar
