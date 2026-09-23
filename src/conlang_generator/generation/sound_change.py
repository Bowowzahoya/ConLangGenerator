"""Diachronic sound change: evolves an *existing* language's lexicon via
regular sound-change rules, rather than generating a fresh one.

Pure rule-based, no LLM -- historical sound change is a rule-application
process, not a creative one, so this stays free, instant, and reproducible.

Six illustrative rule categories, applied in order to every lexicon entry's
IPA (tokenized -- see ``ipa_tokenizer.py`` -- so tone-diacritic decoration
survives even when the base vowel it's on changes):

- cluster simplification: a 2-consonant run drops its lower-sonority member.
- lenition: a voiceless stop between two vowels becomes voiced.
- final devoicing: a word-final voiced obstruent becomes voiceless. Real
  orthography usually keeps spelling the *underlying* voiced form here
  (Dutch "berg" pronounced [bɛrx] but still spelled with "g", audible in
  "bergen") -- `_evolve_ipa` tracks this and hands `evolve_language`'s
  spelling-reconstruction step a second, spelling-oriented IPA string
  that reverts a word-final devoicing from *this run* back to its voiced
  form, so a freshly-reconstructed spelling follows the same
  morphophonemic principle instead of the bare surface pronunciation --
  see its own docstring for exactly when that hint does and doesn't
  survive the rest of the pipeline.
- palatalization: k/g before a front vowel becomes tʃ/dʒ.
- vowel reduction: a non-first vowel becomes ə.
- ejective drift: a plain stop gains ejective release.

Each rule has an illustrative "half-life" in years (grounded per rule
against a real, commonly-cited historical case -- still illustrative,
not precise quantitative calibration -- see ``_HALF_LIVES``) and a
saturating rate model: ``rate(years) = 1 -
exp(-years/effective_half_life)``, so a small ``years`` changes little
(recognizable) and a large one approaches -- never reaches -- total
replacement. ``effective_half_life`` is scaled by the one relevant graded
trait per rule-cluster (``contact_intensity`` for the three simplification-
leaning rules -- contact/creolization accelerates simplification;
``altitude`` for ejective drift -- Everett 2013, same link fresh generation
already uses): positive trait strength shortens the half-life (faster
change), negative lengthens it. ``ejective_drift`` additionally gets a
direct multiplicative suppression from positive ``contact_intensity``
(sustained heavy contact keeps this marked-feature innovation unlikely at
any time depth, not just slower to arrive). `final_devoicing`/
`palatalization` aren't trait-linked in this v1 -- kept deliberately narrow.

Grammar is copied from the base language unchanged (word-level focus only,
per current project direction). The tone system is copied unchanged too,
*unless* this run's own tonal status actually flips -- see
``_evolve_tone_system`` for the two real, structurally- and rate-gated
directions that can happen (detonalization: a tonal language loses tone,
accelerated by contact; tonogenesis: a non-tonal language with a real
coda-glottal-stop word gains a real high/low contrast the same way
Vietnamese's own tone system historically arose). The evolved
``PhonemeInventory``/``SyllableStructure`` are recomputed from what the
evolved lexicon actually uses (which, after a tone-system transition,
already reflects that transition's own effect -- a removed coda ``ʔ``, or
stripped tone marks -- since it runs before this reconstruction).

Orthography evolves via two independent mechanisms, not just re-derived
from the evolved IPA:

- **Replacement** (whole entry, IPA and spelling both, decided per lexicon
  entry): with contact languages active, a wholesale *borrowing* -- a fresh
  word coined from the contact language's own phoneme palette, romanized
  with that language's own spelling conventions (not respelled via this
  language's rules). Without contact languages, a *native replacement* --
  an unrelated same-language word coined for the meaning instead, same as
  fresh generation would coin one. Anchored to glottochronology's basic-
  vocabulary-replacement premise (core words get replaced at a roughly
  constant rate over centuries, boosted here by contact) *and* to how
  resistant that particular gloss's meaning-category tends to be
  cross-linguistically (``lexicon_gen.STABILITY_TIER`` -- pronouns/low
  numerals are far more resistant than general nouns).
- **Freeze / reform / drift** (decided per *symbol*, via
  ``romanization_gen.evolve_romanization()`` -- see its own docstring):
  every non-replaced entry's spelling comes from the one evolved
  ``RomanizationScheme`` returned by that call, so words sharing a symbol
  always share its spelling -- a real spelling convention (or a real
  spelling reform) applies uniformly, not as an independent per-word coin
  flip.

Replacement is decided first per entry; when it fires, that entry skips the
scheme-based spelling entirely (a freshly coined or borrowed word has no
old spelling to freeze to, and comes with its own). Treating this as one
outcome per entry per ``evolve_language`` call (not a fuller multi-stage
history) is a deliberate v1 simplification -- see
``architecture/OVERVIEW.md`` for what's out of scope.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import LexicalEntry, Lexicon
from conlang_generator.core.phonology import (
    TONE_DIACRITICS,
    LexicalToneSandhiRule,
    Manner,
    PhonemeInventory,
    SyllableStructure,
    ToneLevel,
    ToneSandhiRule,
    ToneSystem,
    VowelBackness,
)
from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK, OrthographyForce, apply_grammatical_spelling
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import (
    ipa_tokenizer,
    lexicon_gen,
    phonology_gen,
    reference_languages,
    romanization_gen,
    root_pattern,
    sonority,
    stress_gen,
    word_accent_gen,
    word_builder,
    word_class_gen,
)

_VOICELESS_TO_VOICED: dict[str, str] = {
    "p": "b", "t": "d", "k": "g", "ʈ": "ɖ", "c": "ɟ", "tʃ": "dʒ", "ts": "dz", "tɕ": "dʑ",
    "s": "z", "f": "v", "ʃ": "ʒ", "ʂ": "ʐ", "ɸ": "β", "ɕ": "ʑ", "ʈʂ": "ɖʐ", "θ": "ð", "ç": "ʝ", "χ": "ʁ", "x": "ɣ",
}
_VOICED_TO_VOICELESS: dict[str, str] = {voiced: voiceless for voiceless, voiced in _VOICELESS_TO_VOICED.items()}
_PALATALIZATION: dict[str, str] = {"k": "tʃ", "g": "dʒ"}
_PLAIN_TO_EJECTIVE: dict[str, str] = {"p": "pʼ", "t": "tʼ", "k": "kʼ"}

_HALF_LIVES = {
    # One of the most cross-linguistically common, phonetically-natural
    # (aerodynamically-driven) neutralizations -- the German/Dutch
    # Auslautverhärtung case this file's own docstring already illustrates
    # (Dutch "berg" [bɛrx]) is commonly described as establishing itself
    # relatively quickly once utterance-final devoicing pressure takes hold.
    "final_devoicing": 130.0,
    # The textbook English loss of onset /kn-/, /gn-/, /wr-/ clusters is
    # commonly dated to completing within a few centuries (roughly the
    # Early Modern English period, per orthoepists' testimony) -- a
    # relatively fast-diffusing simplification once triggered.
    "cluster_simplification": 170.0,
    # The textbook Western Romance intervocalic stop-lenition case (Latin
    # p/t/k > b/d/g > spirants/zero between vowels) is commonly described
    # as an early-medieval-centuries-scale process -- slower than the two
    # above since it's gradient (voicing, then spirantization, then loss,
    # is itself a multi-stage cline, not one categorical flip).
    "lenition": 200.0,
    # Unstressed-vowel-to-schwa reduction (English, Russian, Portuguese) is
    # well-attested but, like lenition, gradual/gradient rather than a
    # single categorical change.
    "vowel_reduction": 200.0,
    # Palatalization recurs independently across unrelated families
    # (Slavic, Romance, Japanese, Bantu), but each instance is well-
    # documented as proceeding through a long series of fine phonetic
    # increments before phonologizing categorically (the phonetic-
    # gradualness point associated with Ohala's work on sound change).
    "palatalization": 300.0,
    # The slowest of the six: ejective *innovation* (as opposed to mere
    # retention of an inherited series) is typologically far rarer than
    # the other five processes -- see the altitude trait link below
    # (Everett 2013).
    "ejective_drift": 400.0,
    # Tone *system*-level changes (see `_evolve_tone_system` below) --
    # deliberately not part of `_Rates`/`_compute_rates` above, since
    # unlike the six gradient/per-position rules there, each of these is
    # a single whole-language decision, not a rate applied independently
    # per eligible position.
    #
    # Detonalization: real Swahili's own well-documented loss of the
    # reconstructed Bantu tone system (commonly attributed to centuries
    # of sustained Arabic/trade-contact pressure and analytic
    # restructuring) is this project's own most citable real case for
    # this direction -- already reflected from the start in this
    # project's own curated Swahili profile (`tonal: false`), and now
    # reachable as a genuine *transition* during evolution too, not just
    # a fact a profile can start with.
    "detonalization": 350.0,
    # Tonogenesis: real Vietnamese's own classic tonogenesis (Haudricourt
    # 1954) and Punjabi's real, comparatively fast, well-documented
    # modern-era case (from breathy-voiced-onset loss) are both commonly
    # described unfolding over a few centuries to roughly a millennium --
    # this project models the *other* major cross-linguistic pathway
    # (coda-glottal-stop loss, the same mechanism behind Vietnamese's own
    # tonal origin) since it's the one this project's own phoneme/coda
    # machinery can actually detect and simulate; see
    # `_evolve_tone_system`'s own docstring for exactly how.
    "tonogenesis": 400.0,
    # Tone split: the *already-tonal* counterpart of tonogenesis -- the
    # same onset-voicing-loss mechanism (a voiced onset historically
    # lowered a following syllable's own pitch; once the voicing
    # contrast itself merges away, that pitch difference is what's left
    # to carry the distinction), just applied to a language that already
    # has some tone rather than none. Real anchor: Middle Chinese's own
    # 4-tone-into-8-tone register split, substantially complete by
    # around the Song-Yuan transition -- a comparable multi-century
    # timescale to tonogenesis's own Vietnamese/Punjabi cases, so this
    # shares roughly the same half-life. See `_YANG_TONE`'s own
    # docstring for exactly which existing tone categories this project
    # reuses as the "split into" outcome.
    "tone_split": 420.0,
    # Tone merger: real Middle Chinese's own "entering" (checked-syllable)
    # tone category dispersing into the other tones on the way to modern
    # Mandarin -- often described as a protracted, somewhat irregular
    # process rather than one clean cutover, so this stays the slowest of
    # the four tone-system-level half-lives.
    "tone_merger": 450.0,
    # Sandhi lexicalization: a live, context-conditioned ToneSandhiRule
    # loses its own conditioning and freezes into affected words' own
    # citation tones -- real Cantonese "changed tone" (變調) is this
    # project's own citable anchor, widely described as a fossilized
    # reflex of earlier, once-productive tone sandhi that a modern speaker
    # can no longer predict from any live phonological rule, just
    # memorizes per word. The slowest of all five tone-system-level
    # half-lives: unlike a merger (a clean, wholesale category collapse)
    # or a split (one mechanical onset-voicing-loss event), a rule
    # actually losing its own productivity and being reanalyzed as
    # per-word fact is a further, later diachronic stage on top of either.
    "sandhi_lexicalization": 500.0,
}

Token = tuple[str, str]  # (base symbol, trailing combining-mark decoration)


@dataclass(frozen=True)
class _Rates:
    lenition: float
    final_devoicing: float
    cluster_simplification: float
    palatalization: float
    vowel_reduction: float
    ejective_drift: float


def _saturating_rate(years: int, base_half_life: float, trait_strength: float) -> float:
    multiplier = max(0.15, 1.0 - 0.6 * trait_strength)
    effective_half_life = base_half_life * multiplier
    return 1.0 - math.exp(-years / effective_half_life)


def _compute_rates(years: int, traits: TraitProfile) -> _Rates:
    contact = traits.contact_intensity
    ejective_base = _saturating_rate(years, _HALF_LIVES["ejective_drift"], traits.altitude)
    # Contact/leveling suppresses this marked-feature innovation outright, not just
    # via a longer half-life -- a half-life stretch alone still creeps toward
    # certainty at long time depths regardless of how much contact pressure there
    # is, which is wrong: sustained heavy contact should keep ejectives unlikely
    # no matter how many years pass. A direct multiplier on the final rate holds
    # that suppression proportionally at any time depth. Isolation doesn't get a
    # symmetric boost here -- altitude already carries the positive case.
    ejective_drift = ejective_base * (1.0 - 0.8 * max(0.0, contact))
    return _Rates(
        lenition=_saturating_rate(years, _HALF_LIVES["lenition"], contact),
        final_devoicing=_saturating_rate(years, _HALF_LIVES["final_devoicing"], 0.0),
        cluster_simplification=_saturating_rate(years, _HALF_LIVES["cluster_simplification"], contact),
        palatalization=_saturating_rate(years, _HALF_LIVES["palatalization"], 0.0),
        vowel_reduction=_saturating_rate(years, _HALF_LIVES["vowel_reduction"], contact),
        ejective_drift=ejective_drift,
    )


def _reachable_sound_change_symbols(rates: _Rates) -> frozenset[str]:
    """The bounded set of IPA symbols this run's sound-change rules could
    actually introduce beyond the base language's own inventory, given
    ``rates``. Each rule maps a small, fixed set of symbols to another
    fixed symbol (``_VOICELESS_TO_VOICED``/``_PALATALIZATION``/
    ``_PLAIN_TO_EJECTIVE`` above, plus vowel reduction's "ə"), and a rule
    at rate 0 can never fire at all (every ``_apply_*``/
    ``_simplify_clusters`` function early-returns on ``rate <= 0``), so
    excluding an inactive rule's own targets keeps this as tight as the
    run can actually produce -- at ``years=0`` (every rate saturates to
    exactly 0) this is the empty set, so a language's reconstructed
    inventory is byte-for-byte the same tokenization as its base's own.

    This closure only needs one pass: `_evolve_ipa`'s six rules apply in
    a fixed order to an already-tokenized list, each looking only at
    symbols already in that list (either from the base language's own
    inventory, or from a fresh token this same closure already
    accounts for) -- no rule's own *output* symbol ever becomes a later
    rule's *input* trigger (lenition's voiced outputs aren't in
    ``_PALATALIZATION``'s keys, palatalization's affricate outputs
    aren't in ``_PLAIN_TO_EJECTIVE``'s keys, etc.), so there's no chain
    of introduced symbols enabling further introduced symbols to track.

    Used to keep ``ipa_tokenizer``'s own greedy-longest-match candidate
    set (see ``evolve_language``'s own ``known_symbols``/
    ``reconstruction_symbols``) from ever containing some *other*
    profile's coincidentally-same-spelled multi-character phoneme (e.g.
    Swahili's prenasalized stop "nz" in ``phonology_gen.ALL_CONSONANTS``)
    that this language's own words -- pre- or post-evolution -- could
    never actually produce, which would otherwise let the tokenizer
    mis-parse two real, adjacent single-character phonemes (one
    syllable's coda "n" immediately followed by the next syllable's
    onset "z") as that unrelated phoneme instead."""
    symbols: set[str] = set()
    if rates.lenition > 0:
        symbols.update(_VOICELESS_TO_VOICED.values())
    if rates.final_devoicing > 0:
        symbols.update(_VOICELESS_TO_VOICED.keys())
    if rates.palatalization > 0:
        symbols.update(_PALATALIZATION.values())
    if rates.vowel_reduction > 0:
        symbols.add("ə")
    if rates.ejective_drift > 0:
        symbols.update(_PLAIN_TO_EJECTIVE.values())
    return frozenset(symbols)


def _tokenizer_pool(all_single_char_symbols: frozenset[str], language_symbols: frozenset[str]) -> tuple[str, ...]:
    """A tokenizer candidate set that can never mis-parse two real,
    adjacent single-character phonemes as some unrelated multi-character
    one, while still never silently dropping a genuine single-character
    symbol that isn't part of ``language_symbols`` (e.g. a grammatical
    affix's own literal vowel -- a word-class suffix like a Dutch-style
    plural "-ən" injects its "ə" directly, the same "template characters
    aren't guaranteed to already be inventory members" situation
    ``word_class_gen.apply_word_class``'s own docstring already
    documents, so ``language_symbols`` alone would wrongly starve the
    tokenizer of a character that's genuinely there).

    The ambiguity this project's tokenizer bug (see ``evolve_language``'s
    own comment above) needs is structural: a *multi*-character candidate
    (2+ code points) that happens to equal the concatenation of two real,
    shorter tokens. A single-character candidate can never cause that --
    there's nothing shorter to wrongly prefer over it -- so every
    single-character symbol this project can ever model stays a
    candidate unconditionally, sourced from ``all_single_char_symbols``
    (every profile's own single-character phonemes, i.e. the previous,
    unrestricted global pool, minus every multi-character one). Only
    *multi*-character candidates get filtered down to ``language_symbols``
    -- the ones actually reachable by this specific language -- since
    those are the only candidates capable of ever winning a greedy-
    longest-match tie against two real, coincidentally-adjacent shorter
    tokens that were never meant to be read as one phoneme."""
    return tuple(all_single_char_symbols | {symbol for symbol in language_symbols if len(symbol) > 1})


_ORTHOGRAPHY_HALF_LIVES = {
    # Real, discrete Dutch spelling reforms (1804, 1863, 1946/47, 1996,
    # 2005) are ~50-150 years apart -- reform is rare relative to sound
    # change, so freeze dominates by default, especially at short `years`.
    "reform": 500.0,
    "drift": 200.0,
    # Glottochronology's commonly-cited retention rate for stable core
    # vocabulary (~80-86% per 1000 years) implies a half-life on the order
    # of 3200-4700 years -- this is the *default*-tier (verb/adjective)
    # baseline; lexicon_gen.STABILITY_TIER multiplies it up per entry
    # (pronouns/numerals end up effectively near-immortal).
    "replacement": 4000.0,
}


@dataclass(frozen=True)
class _OrthographyRates:
    reform: float
    drift: float


def _compute_orthography_rates(years: int, traits: TraitProfile) -> _OrthographyRates:
    return _OrthographyRates(
        # Positive orality_literacy (more literate/standardized) *lowers*
        # the reform rate -- standardization is why spelling freezes.
        reform=_saturating_rate(years, _ORTHOGRAPHY_HALF_LIVES["reform"], -traits.orality_literacy),
        drift=_saturating_rate(years, _ORTHOGRAPHY_HALF_LIVES["drift"], traits.contact_intensity),
    )


def _replacement_rate(years: int, traits: TraitProfile, pos) -> float:
    stability = lexicon_gen.STABILITY_TIER.get(pos, 1.0)
    return _saturating_rate(years, _ORTHOGRAPHY_HALF_LIVES["replacement"] * stability, traits.contact_intensity)


def _simplify_clusters(tokens: list[Token], rng: random.Random, rate: float, consonant_by_ipa: dict) -> list[Token]:
    if rate <= 0:
        return tokens
    result: list[Token] = []
    i = 0
    while i < len(tokens):
        symbol = tokens[i][0]
        if (
            i + 1 < len(tokens)
            and symbol in consonant_by_ipa
            and tokens[i + 1][0] in consonant_by_ipa
            and rng.random() < rate
        ):
            c1, c2 = consonant_by_ipa[symbol], consonant_by_ipa[tokens[i + 1][0]]
            result.append(tokens[i + 1] if sonority.sonority(c1) <= sonority.sonority(c2) else tokens[i])
            i += 2
            continue
        result.append(tokens[i])
        i += 1
    return result


def _adjacent_real_symbol(tokens: list[Token], index: int, step: int) -> str | None:
    """The nearest real phoneme symbol in ``tokens`` from ``index``,
    stepping by ``step`` (+1/-1), skipping past any ``STRESS_MARK``/
    ``WORD_ACCENT_MARK`` token in between -- both always sit at a
    syllable boundary, i.e. exactly where an intervocalic check like
    ``_apply_lenition``'s looks, so treating either as a real neighbor
    would wrongly break that check for every leniting consonant that
    happens to open a stressed syllable, or that sits right after a
    glottalization-realization word-accent mark (systematic, not a rare
    edge case -- unlike a couple of the other five rules' own narrower
    interactions with these markers, this one needs an explicit fix).
    ``None`` if there's no real symbol that way."""
    j = index + step
    while 0 <= j < len(tokens):
        if tokens[j][0] not in (STRESS_MARK, WORD_ACCENT_MARK):
            return tokens[j][0]
        j += step
    return None


def _apply_lenition(tokens: list[Token], rng: random.Random, rate: float, vowel_by_ipa: dict) -> list[Token]:
    if rate <= 0:
        return tokens
    result = list(tokens)
    for i, (symbol, deco) in enumerate(result):
        if symbol not in _VOICELESS_TO_VOICED or i == 0 or i == len(result) - 1:
            continue
        before = _adjacent_real_symbol(result, i, -1)
        after = _adjacent_real_symbol(result, i, 1)
        if before in vowel_by_ipa and after in vowel_by_ipa and rng.random() < rate:
            result[i] = (_VOICELESS_TO_VOICED[symbol], deco)
    return result


def _apply_final_devoicing(
    tokens: list[Token], rng: random.Random, rate: float, consonant_by_ipa: dict
) -> tuple[list[Token], str | None]:
    """Returns the (possibly) devoiced tokens plus, when devoicing actually
    fired this call, the *original voiced symbol* it replaced -- the one
    piece of diachronic context ``_evolve_ipa`` needs to let spelling
    follow the underlying/paradigmatic form (Dutch "berg" pronounced
    [bɛrx] but still spelled with "g") instead of the bare surface IPA,
    the way real orthography does. ``None`` when nothing devoiced.

    ``WORD_ACCENT_MARK`` (the ``"glottalization"``-realization word-accent
    mark) is the one systematic case a plain ``tokens[-1]`` lookup would
    get wrong here, unlike every other rule this marker touches: when the
    accented syllable is word-final (the common case), the mark itself,
    not the real final consonant, is the literal last token -- checked
    and skipped past explicitly, so the *real* final consonant still gets
    considered, with the mark left exactly where it was."""
    if rate <= 0 or not tokens:
        return tokens, None
    result = list(tokens)
    final_index = len(result) - 1
    if result[final_index][0] == WORD_ACCENT_MARK:
        final_index -= 1
    if final_index < 0:
        return result, None
    symbol, deco = result[final_index]
    consonant = consonant_by_ipa.get(symbol)
    if consonant is not None and consonant.voiced and symbol in _VOICED_TO_VOICELESS and rng.random() < rate:
        result[final_index] = (_VOICED_TO_VOICELESS[symbol], deco)
        return result, symbol
    return result, None


def _apply_palatalization(tokens: list[Token], rng: random.Random, rate: float, vowel_by_ipa: dict) -> list[Token]:
    if rate <= 0:
        return tokens
    result = list(tokens)
    for i, (symbol, deco) in enumerate(result):
        if symbol not in _PALATALIZATION or i + 1 >= len(result):
            continue
        next_vowel = vowel_by_ipa.get(result[i + 1][0])
        if next_vowel is not None and next_vowel.backness == VowelBackness.FRONT and rng.random() < rate:
            result[i] = (_PALATALIZATION[symbol], deco)
    return result


def _apply_vowel_reduction(tokens: list[Token], rng: random.Random, rate: float, vowel_by_ipa: dict) -> list[Token]:
    """Every vowel *except the stressed one* is a candidate to reduce
    toward schwa -- the real, stress-driven phenomenon this rule's own
    half-life comment already named (English/Russian/Portuguese). The
    protected vowel is whichever one immediately follows a real
    ``STRESS_MARK`` token, found fresh in *this* call's own ``tokens``
    (not threaded from word-building) since it needs to survive whatever
    ``_simplify_clusters``/``_apply_lenition``/``_apply_final_devoicing``
    already did to this same list earlier in ``_evolve_ipa``'s pipeline.
    Falls back to the older, position-blind "not the first vowel"
    heuristic when a word has no stress marker at all -- an uncurated
    language, or a coining path that doesn't assign one -- same
    abstain-gracefully discipline used throughout this project when
    curated/derived data is missing."""
    if rate <= 0:
        return tokens
    result = list(tokens)
    stress_index = next((i for i, (symbol, _) in enumerate(result) if symbol == STRESS_MARK), None)
    protected_index = (
        next((i for i in range(stress_index + 1, len(result)) if result[i][0] in vowel_by_ipa), None)
        if stress_index is not None
        else None
    )
    if protected_index is None:
        # No stress marker (or nothing followed it) -- the pre-stress
        # heuristic, spared vowel is just the first one in the word.
        protected_index = next((i for i, (symbol, _) in enumerate(result) if symbol in vowel_by_ipa), None)
    for i, (symbol, deco) in enumerate(result):
        if symbol not in vowel_by_ipa or i == protected_index:
            continue
        if symbol != "ə" and rng.random() < rate:
            result[i] = ("ə", deco)
    return result


def _apply_ejective_drift(tokens: list[Token], rng: random.Random, rate: float) -> list[Token]:
    if rate <= 0:
        return tokens
    result = list(tokens)
    for i, (symbol, deco) in enumerate(result):
        if symbol in _PLAIN_TO_EJECTIVE and rng.random() < rate:
            result[i] = (_PLAIN_TO_EJECTIVE[symbol], deco)
    return result


def _evolve_ipa(
    ipa: str, rng: random.Random, rates: _Rates, known_symbols: tuple[str, ...], consonant_by_ipa: dict, vowel_by_ipa: dict
) -> tuple[str, str]:
    """Returns ``(evolved_ipa, spelling_ipa)`` -- the real, surface-accurate
    pronunciation, and a second string identical to it except that a
    word-final symbol devoiced *this call* is reverted to its original
    voiced form, provided nothing later in the pipeline touched that same
    position again (palatalization/vowel reduction structurally never can
    -- see below; ejective drift can, if the devoiced symbol is a plain
    stop, so this is checked, not assumed). Callers should keep using
    ``evolved_ipa`` for everything phonemic (the stored pronunciation,
    inventory/phonotactics) and reach for ``spelling_ipa`` only when
    reconstructing a word's *romanization* -- see ``evolve_language``.
    """
    tokens = ipa_tokenizer.tokenize(ipa, known_symbols)
    tokens = _simplify_clusters(tokens, rng, rates.cluster_simplification, consonant_by_ipa)
    tokens = _apply_lenition(tokens, rng, rates.lenition, vowel_by_ipa)
    tokens, devoiced_from = _apply_final_devoicing(tokens, rng, rates.final_devoicing, consonant_by_ipa)
    # Palatalization only fires when a *following* vowel exists -- never
    # true for the last token -- and vowel reduction only ever touches
    # vowels, never this (consonant) position, so neither can invalidate
    # devoiced_from. Only ejective drift, which can touch any plain stop
    # anywhere including the last token, might.
    post_devoicing_final = tokens[-1] if devoiced_from is not None and tokens else None
    tokens = _apply_palatalization(tokens, rng, rates.palatalization, vowel_by_ipa)
    tokens = _apply_vowel_reduction(tokens, rng, rates.vowel_reduction, vowel_by_ipa)
    tokens = _apply_ejective_drift(tokens, rng, rates.ejective_drift)
    evolved = "".join(symbol + deco for symbol, deco in tokens)
    spelling = evolved
    if devoiced_from is not None and tokens and tokens[-1] == post_devoicing_final:
        spelling = "".join(symbol + deco for symbol, deco in tokens[:-1]) + devoiced_from + tokens[-1][1]
    return evolved, spelling


def _recompute_syllable_structure(
    base: SyllableStructure,
    consonants: tuple,
    rng: random.Random,
    traits: TraitProfile,
    lineage_profiles: tuple[reference_languages.ReferenceLanguageProfile, ...],
) -> SyllableStructure:
    symbols = {c.ipa for c in consonants}
    onset_pairs = sonority.legal_onset_pairs(consonants)
    allowed_onset_clusters = (
        sonority.thin_cluster_pairs(rng, onset_pairs, traits.contact_intensity) if base.max_onset >= 2 else ()
    )
    excluded_final_coda_consonants: tuple[str, ...] = ()
    if base.max_coda == 0:
        max_coda, allowed_coda_consonants, allowed_coda_clusters, excluded_coda_consonants = 0, None, (), ()
    elif base.allowed_coda_consonants is not None:
        sonorants = tuple(c.ipa for c in consonants if c.ipa == "ʔ" or c.long or sonority.sonority(c) >= 3)
        max_coda, allowed_coda_consonants, allowed_coda_clusters, excluded_coda_consonants = (
            (1, sonorants, (), ()) if sonorants else (0, None, (), ())
        )
    else:
        excluded_coda_consonants = ()
        if any(p.coda_devoicing for p in lineage_profiles):
            excluded_final_coda_consonants = tuple(
                c.ipa
                for c in consonants
                if c.voiced and c.manner in (
                    Manner.STOP, Manner.AFFRICATE, Manner.LATERAL_AFFRICATE, Manner.FRICATIVE, Manner.LATERAL_FRICATIVE,
                )
            )
        coda_pairs = sonority.exclude_final(sonority.legal_coda_pairs(consonants), excluded_coda_consonants)
        max_coda = base.max_coda
        allowed_coda_consonants = None
        allowed_coda_clusters = (
            sonority.thin_cluster_pairs(rng, coda_pairs, traits.contact_intensity) if max_coda >= 2 else ()
        )

    return SyllableStructure(
        max_onset=base.max_onset,
        max_coda=max_coda,
        allowed_onset_clusters=allowed_onset_clusters,
        allowed_coda_clusters=allowed_coda_clusters,
        allowed_onset_triples=tuple(t for t in base.allowed_onset_triples if all(s in symbols for s in t)),
        allowed_coda_triples=tuple(t for t in base.allowed_coda_triples if all(s in symbols for s in t)) if max_coda >= 2 else (),
        allowed_coda_consonants=allowed_coda_consonants,
        excluded_coda_consonants=excluded_coda_consonants,
        excluded_final_coda_consonants=excluded_final_coda_consonants,
        vowel_harmony=base.vowel_harmony,
    )


def _has_qualifying_coda_glottal_stop(tokens: list[Token], vowel_symbols: frozenset[str]) -> bool:
    """Whether this word has at least one real coda ``ʔ`` -- immediately
    after a vowel, and either word-final or immediately before a
    consonant (never before another vowel: under the maximal-onset
    principle real phonology already uses everywhere else in this
    project, an intervocalic ``ʔ`` belongs to the *next* syllable's own
    onset, not the previous one's coda, so it's structurally unrelated
    to tonogenesis and left untouched)."""
    for i, (symbol, _) in enumerate(tokens):
        if symbol != "ʔ" or i == 0 or tokens[i - 1][0] not in vowel_symbols:
            continue
        if i + 1 == len(tokens) or tokens[i + 1][0] not in vowel_symbols:
            return True
    return False


def _tonogenesis_ipa(ipa: str, known_symbols: tuple[str, ...], vowel_symbols: frozenset[str]) -> tuple[str, tuple]:
    """One word's own real glottal-coda-loss tonogenesis: every vowel
    immediately followed by a qualifying coda ``ʔ`` (see
    ``_has_qualifying_coda_glottal_stop``'s own docstring for exactly
    what qualifies) surfaces ``LOW`` and drops that ``ʔ``; every other
    vowel -- syllables that were never conditioned by a coda ``ʔ`` at
    all -- surfaces the real cross-linguistic elsewhere case, ``HIGH``.
    Returns the new ``(ipa, tones)`` pair, ``tones`` in the same
    left-to-right order ``LexicalEntry.tones`` already uses everywhere
    else."""
    tokens = ipa_tokenizer.tokenize(ipa, known_symbols)
    out: list[str] = []
    tones: list[ToneLevel] = []
    i = 0
    while i < len(tokens):
        symbol, deco = tokens[i]
        if symbol not in vowel_symbols:
            out.append(symbol + deco)
            i += 1
            continue
        has_glottal_coda = (
            i + 1 < len(tokens) and tokens[i + 1][0] == "ʔ"
            and (i + 2 == len(tokens) or tokens[i + 2][0] not in vowel_symbols)
        )
        tone = ToneLevel.LOW if has_glottal_coda else ToneLevel.HIGH
        tones.append(tone)
        out.append(symbol + deco + TONE_DIACRITICS[tone])
        i += 2 if has_glottal_coda else 1  # skip the ʔ token too, once consumed
    return "".join(out), tuple(tones)


def _tone_of(deco: str) -> ToneLevel | None:
    return next((level for level, mark in TONE_DIACRITICS.items() if mark in deco), None)


def _is_syllable_initial(tokens: list[Token], index: int, vowel_symbols: frozenset[str]) -> bool:
    """Whether the consonant at ``index`` opens its own syllable -- the
    position real onset-voicing-conditioned tone register-splitting (and
    tonogenesis more generally) actually cares about, not a second
    member of an onset cluster. Walks back past any
    ``STRESS_MARK``/``WORD_ACCENT_MARK`` token first (neither is a real
    phoneme position) -- the same skip ``_apply_final_devoicing``'s own
    docstring already documents needing, mirrored here for the onset
    side instead of the coda side."""
    i = index - 1
    while i >= 0 and tokens[i][0] in (STRESS_MARK, WORD_ACCENT_MARK):
        i -= 1
    return i < 0 or tokens[i][0] in vowel_symbols


_YANG_TONE: dict[ToneLevel, ToneLevel] = {
    # Real yin/yang tonal register splits (the same historical mechanism
    # behind Middle Chinese's own 4-tone-to-8-tone division, and the
    # onset-voicing-loss pathway behind Punjabi/Sino-Tibetan tonogenesis
    # more generally, see `_tonogenesis_ipa` above): once a syllable's
    # own onset voicing contrast merges away, its own tone splits into
    # two registers -- a syllable that used to have a *voiced* onset
    # surfaces distinctly lower than one that used to have a voiceless
    # one. This project's own `ToneLevel` doesn't separate register from
    # contour the way a full Chao-letter system would (see
    # `core.phonology.TONE_CONTOURS`'s own docstring) -- rather than
    # inventing new register-marked tone categories, this reuses
    # whichever *existing* category is this project's own closest real
    # match: `HIGH` (level, "55") pairs with `LOW` (near-level, "21",
    # real Standard Mandarin's own textbook register-low counterpart);
    # `RISING` ("35") pairs with `DIPPING` ("214") -- already documented
    # on `ToneLevel.DIPPING` itself as "a low tone that dips," i.e.
    # already this project's own low-register member of that exact pair,
    # not a new claim invented for this rule. `FALLING`/`MID` have no
    # defensible low-register partner in this project's own simplified
    # 7-category inventory and are deliberately left out of this table --
    # a voiced-onset `FALLING`/`MID` syllable still devoices its own
    # onset when a split fires (see `_tone_split_ipa` below), but keeps
    # its own tone unchanged, an honest partial coverage rather than a
    # fabricated pairing.
    ToneLevel.HIGH: ToneLevel.LOW,
    ToneLevel.RISING: ToneLevel.DIPPING,
}


def _has_qualifying_voiced_onset(
    tokens: list[Token], consonant_by_ipa: dict, vowel_symbols: frozenset[str]
) -> bool:
    """Whether this word has at least one real syllable-initial voiced
    obstruent onset immediately followed (possibly across the rest of
    its own onset cluster) by a vowel whose own current tone has a real
    register partner in ``_YANG_TONE`` -- the structural precondition
    for ``_tone_split_ipa`` to actually change anything (a voiced onset
    before a ``FALLING``/``MID``/untoned nucleus still devoices under a
    real split, but produces no *visible* tone change on its own, so it
    alone isn't "raw material" for this specific check)."""
    pending_yang = False
    for i, (symbol, deco) in enumerate(tokens):
        if symbol in vowel_symbols:
            if pending_yang and _tone_of(deco) in _YANG_TONE:
                return True
            pending_yang = False
            continue
        consonant = consonant_by_ipa.get(symbol)
        if (
            consonant is not None and consonant.voiced and symbol in _VOICED_TO_VOICELESS
            and _is_syllable_initial(tokens, i, vowel_symbols)
        ):
            pending_yang = True
    return False


def _tone_split_ipa(
    ipa: str, known_symbols: tuple[str, ...], consonant_by_ipa: dict, vowel_symbols: frozenset[str]
) -> tuple[str, tuple]:
    """One word's own real register-split tonogenesis-on-an-already-tonal
    language: a syllable-initial voiced obstruent onset devoices (the
    conditioning contrast this rule is *about* losing) and, when its own
    following vowel's current tone has a real partner in ``_YANG_TONE``,
    that vowel's own tone becomes that lower-register partner. Every
    other syllable -- voiceless/sonorant onset, or a tone with no
    defensible partner -- keeps both its own onset and its own tone
    exactly as they were. Returns the new ``(ipa, tones)`` pair, ``tones``
    covering every tone-bearing syllable in left-to-right order (unchanged
    ones included), the same shape ``LexicalEntry.tones`` already uses
    everywhere else, so this can simply replace an entry's own ``tones``
    outright rather than patching it."""
    tokens = ipa_tokenizer.tokenize(ipa, known_symbols)
    out: list[str] = []
    tones: list[ToneLevel] = []
    pending_yang = False
    for i, (symbol, deco) in enumerate(tokens):
        if symbol in vowel_symbols:
            tone = _tone_of(deco)
            if tone is not None:
                new_tone = _YANG_TONE.get(tone, tone) if pending_yang else tone
                tones.append(new_tone)
                if new_tone != tone:
                    deco = deco.replace(TONE_DIACRITICS[tone], TONE_DIACRITICS[new_tone])
            pending_yang = False
            out.append(symbol + deco)
            continue
        consonant = consonant_by_ipa.get(symbol)
        if (
            consonant is not None and consonant.voiced and symbol in _VOICED_TO_VOICELESS
            and _is_syllable_initial(tokens, i, vowel_symbols)
        ):
            out.append(_VOICED_TO_VOICELESS[symbol] + deco)
            pending_yang = True
            continue
        out.append(symbol + deco)
        # a non-onset-initial consonant (the coda of the *previous*
        # syllable, or the 2nd member of this syllable's own onset
        # cluster) doesn't reset `pending_yang` -- still "between" a
        # devoiced onset and its own vowel either way.
    return "".join(out), tuple(tones)


_MERGE_EXCLUDED_LEVELS = frozenset({ToneLevel.NEUTRAL})
"""Never a merger source or target: `NEUTRAL` is a real, but categorically
different, unstressed/pitch-underspecified status (see its own docstring
on `core.phonology.ToneLevel`), not a pitch register competing with the
others the way a genuine merger's own two categories are."""


def _tone_merger_pair(rng: random.Random, levels: tuple[ToneLevel, ...]) -> tuple[ToneLevel, ToneLevel] | None:
    """Picks ``(survivor, absorbed)`` from ``levels``'s own real pitch
    categories (see ``_MERGE_EXCLUDED_LEVELS``) -- ``None`` when fewer
    than 2 are eligible, an honest "nothing left to merge" abstention
    rather than a forced pick."""
    eligible = tuple(level for level in levels if level not in _MERGE_EXCLUDED_LEVELS)
    if len(eligible) < 2:
        return None
    survivor, absorbed = rng.sample(eligible, 2)
    return survivor, absorbed


def _tone_merger_ipa(
    ipa: str, known_symbols: tuple[str, ...], vowel_symbols: frozenset[str], survivor: ToneLevel, absorbed: ToneLevel
) -> tuple[str, tuple]:
    """``absorbed``'s own mark becomes ``survivor``'s wherever it occurs
    -- a plain character substitution is enough (unlike a split, a
    merger needs no onset/syllable inspection at all, real or invented:
    every instance of the absorbed category becomes the survivor,
    unconditionally). ``tones`` is read back from the *result*, the same
    "authoritative source is the IPA's own marks" approach every other
    tone-system transform here already uses, rather than threading the
    original ``tones`` tuple through a second, parallel code path."""
    replaced = ipa.replace(TONE_DIACRITICS[absorbed], TONE_DIACRITICS[survivor])
    tokens = ipa_tokenizer.tokenize(replaced, known_symbols)
    tones = tuple(_tone_of(deco) for symbol, deco in tokens if symbol in vowel_symbols and _tone_of(deco) is not None)
    return replaced, tones


def _remap_tone_sandhi(
    rules: tuple[ToneSandhiRule, ...], survivor: ToneLevel, absorbed: ToneLevel
) -> tuple[ToneSandhiRule, ...]:
    """A merger doesn't just rewrite lexicon entries -- any existing
    context-sandhi rule that mentions the now-gone ``absorbed`` category
    (in any of its own three tone-bearing fields) needs the same
    substitution, or it would keep referencing a tone this language no
    longer has. A rule that becomes degenerate after remapping is dropped
    rather than kept as a harmless no-op, the same "never map a tone to
    itself" discipline ``resolve_tone_sandhi``'s own invented-rule branch
    already holds itself to -- which field would actually be mapped to
    itself depends on the rule's own ``target`` (see
    ``core.phonology.ToneSandhiRule``'s own docstring): a ``"before"``
    rule (the common case) is degenerate when ``becomes == before`` (the
    field it actually rewrites); an ``"after"`` rule (real Meeussen's
    Rule) is degenerate when ``becomes == after`` instead, since that's
    the field *it* rewrites -- checking the wrong field here would either
    wrongly drop a genuinely fine ``"after"`` rule or wrongly keep one
    that's actually become a no-op."""
    remapped = []
    for rule in rules:
        before = survivor if rule.before == absorbed else rule.before
        after = survivor if rule.after == absorbed else rule.after
        becomes = survivor if rule.becomes == absorbed else rule.becomes
        rewritten = before if rule.target == "before" else after
        if becomes == rewritten:
            continue
        remapped.append(ToneSandhiRule(before=before, after=after, becomes=becomes, target=rule.target))
    return tuple(remapped)


def _remap_lexical_tone_sandhi(
    rules: tuple[LexicalToneSandhiRule, ...], survivor: ToneLevel, absorbed: ToneLevel
) -> tuple[LexicalToneSandhiRule, ...]:
    """The word-specific counterpart of ``_remap_tone_sandhi`` above, for
    ``ToneSystem.lexical_sandhi`` (real Mandarin 不/一 -- see
    ``LexicalToneSandhiRule``'s own docstring) -- same remap-or-drop
    logic, just across its own two tone-bearing fields instead of three."""
    remapped = []
    for rule in rules:
        before = survivor if rule.before == absorbed else rule.before
        becomes = survivor if rule.becomes == absorbed else rule.becomes
        if becomes == before:
            continue
        remapped.append(LexicalToneSandhiRule(gloss=rule.gloss, before=before, becomes=becomes))
    return tuple(remapped)


def _pick_lexicalizing_sandhi_rule(
    rng: random.Random, sandhi: tuple[ToneSandhiRule, ...]
) -> ToneSandhiRule | None:
    """Picks one of a tonal language's own live, general context-sandhi
    rules to freeze into affected words' own citation tones (see
    ``_lexicalize_sandhi_ipa`` below) -- ``None``, an honest "nothing to
    lexicalize" abstention, when the language has no such rule at all.
    ``ToneSystem.lexical_sandhi`` is deliberately not a candidate here --
    it's already word-specific data, not a general rule that could ever
    need to "become" lexical. A rule with ``before == becomes`` (never
    produced by this project's own ``resolve_tone_sandhi``, but not
    excluded by ``ToneSandhiRule`` itself) would freeze into a genuine
    no-op and is excluded from consideration, the same "never map a tone
    to itself" discipline this file's other tone-system mechanisms
    already hold themselves to. Only a ``target="before"`` rule is ever
    eligible: ``_has_qualifying_lexicalization_target``/
    ``_lexicalize_sandhi_ipa`` both freeze a *word's own last* tone-
    bearing syllable, which is exactly the syllable a ``"before"`` rule
    conditions and rewrites -- but for an ``"after"`` rule (real Bantu
    Meeussen's Rule) that position would be a *different* word's own
    *first* tone-bearing syllable instead, conditioned by what precedes
    it, which neither helper here is built to freeze. An honest, narrower
    scope rather than a silently-wrong freeze of the wrong syllable."""
    eligible = [rule for rule in sandhi if rule.before != rule.becomes and rule.target == "before"]
    if not eligible:
        return None
    return rng.choice(eligible)


def _has_qualifying_lexicalization_target(
    tokens: list[Token], vowel_symbols: frozenset[str], before: ToneLevel
) -> bool:
    """Whether this word's own *last* tone-bearing syllable -- the one
    position ``generation.tone_sandhi.apply_sandhi`` itself always
    conditions general sandhi on, tracking "the syllable immediately
    preceding whatever comes next" -- currently carries ``before``, the
    structural precondition for a rule fixed on that tone to have
    anything of this word's own to freeze onto. A tone-bearing syllable
    that isn't this word's own last one is never sandhi's own target
    position at all, so it's correctly ignored here even if it happens to
    carry ``before`` too."""
    last_tone: ToneLevel | None = None
    for symbol, deco in tokens:
        if symbol in vowel_symbols:
            tone = _tone_of(deco)
            if tone is not None:
                last_tone = tone
    return last_tone == before


def _lexicalize_sandhi_ipa(
    ipa: str, known_symbols: tuple[str, ...], vowel_symbols: frozenset[str], rule: ToneSandhiRule
) -> tuple[str, tuple]:
    """One word's own real sandhi-lexicalization: when this word's own
    last tone-bearing syllable (see ``_has_qualifying_lexicalization_target``
    above) currently carries ``rule.before``, it permanently becomes
    ``rule.becomes`` -- the same outcome a live application of ``rule``
    would already produce whenever this word happened to sit right before
    a ``rule.after``-toned neighbor, now baked in as this word's own new
    citation tone instead of staying conditioned on a following context
    this project's per-word storage has no way to remember happened. Every
    other word -- its own last tone bearing something other than
    ``rule.before``, or no tone at all -- is returned unchanged. Returns
    the new ``(ipa, tones)`` pair, the same shape every other tone-system
    transform in this file already returns, so this can be handed
    straight to ``_evolve_tone_system``'s own ``transform`` contract."""
    tokens = ipa_tokenizer.tokenize(ipa, known_symbols)
    tone_positions = [i for i, (symbol, deco) in enumerate(tokens) if symbol in vowel_symbols and _tone_of(deco) is not None]
    if tone_positions and _tone_of(tokens[tone_positions[-1]][1]) == rule.before:
        i = tone_positions[-1]
        symbol, deco = tokens[i]
        tokens[i] = (symbol, deco.replace(TONE_DIACRITICS[rule.before], TONE_DIACRITICS[rule.becomes]))
    tones = tuple(_tone_of(deco) for symbol, deco in tokens if symbol in vowel_symbols and _tone_of(deco) is not None)
    return "".join(symbol + deco for symbol, deco in tokens), tones


def _evolve_tone_system(
    rng: random.Random,
    base_tone_system: ToneSystem,
    years: int,
    contact_intensity: float,
    final_ipas: list[str],
    known_symbols: tuple[str, ...],
    vowel_symbols: frozenset[str],
    consonant_by_ipa: dict,
):
    """Whether this evolution run's own tone *system* itself changes --
    genuinely a different kind of change from the six gradient,
    per-position rules ``_evolve_ipa`` already applies (those adjust
    individual sounds; this decides whether/how the language's own tone
    *categories* (or its own sandhi rules) themselves change), so each of
    the five directions below is its own single whole-language roll, not
    a rate applied independently per eligible position the way e.g.
    lenition is. Real tone contrastiveness is a systemic property -- once
    a language has tone, every syllable carries one, not just the
    syllables that happen to sit in a marked environment -- so unlike
    lenition or palatalization, none of these five can sensibly leave the
    change half-applied across the lexicon; each either fires for the
    whole language this run, or it doesn't yet. Checked in a fixed order,
    at most one firing per run: detonalization, then (only if still
    tonal) merger, then (only if still tonal and no merger fired) split,
    then (only if still tonal and neither merger nor split fired) sandhi
    lexicalization; then (only if still non-tonal) tonogenesis -- a
    language's own tone system this run can only ever move in one of
    these five ways once, not compound multiple in the same call.

    Returns ``(new_tone_system, transform)``: ``transform`` is ``None``
    when nothing fired (the common case), or a pure
    ``list[str] -> (list[str], list[tuple])`` function when one did,
    applying that same real per-word transformation deterministically to
    *any* list of this language's own IPA strings -- the caller runs it
    over both ``final_ipas`` (a word's own new stored IPA) and
    ``spelling_ipas`` (the separate, sometimes-different basis
    ``evolve_language`` reconstructs a word's spelling from, e.g. a
    word-final-devoicing hint) so the two stay consistent with each
    other, without rolling this function's own random decisions twice.

    **Detonalization** (a currently tonal language loses tone): real
    Swahili's own well-documented loss of the reconstructed Bantu tone
    system under centuries of sustained contact is this project's own
    citable real case (see ``_HALF_LIVES["detonalization"]``'s own
    comment) -- accelerated by positive ``contact_intensity``, the same
    "contact drives simplification" link the three simplification-
    leaning segmental rules already use. Every entry's own tone marks
    are stripped from its IPA (``ipa_tokenizer.strip_tones``) and its own
    ``tones`` tuple collapses to ``()``, the same "genuinely toneless"
    shape a from-scratch non-tonal language already has.

    **Tone merger** (two of a currently tonal language's own real pitch
    categories collapse into one): see ``_tone_merger_pair``/
    ``_tone_merger_ipa``/``_remap_tone_sandhi``/``_remap_lexical_tone_sandhi``'s
    own docstrings -- `NEUTRAL` is never a merger participant, and any
    existing `sandhi`/`lexical_sandhi` rule mentioning the now-gone
    category is remapped or dropped, never left dangling.

    **Tone split** (a currently tonal language's own existing categories
    partly divide by register): the *already-tonal* counterpart of
    tonogenesis, via the same real onset-voicing-loss mechanism (see
    ``_YANG_TONE``/``_tone_split_ipa``/``_has_qualifying_voiced_onset``'s
    own docstrings) -- structurally gated the same way tonogenesis is
    below: no qualifying voiced-onset word, no split, regardless of
    ``years``. A split can *add* to ``levels`` (real `LOW`/`DIPPING`
    that weren't previously in use, if this language's own tone system
    didn't already include them) but never removes anything, unlike a
    merger.

    **Sandhi lexicalization** (a currently tonal language's own live,
    general context-sandhi rule loses its conditioning and freezes into
    affected words' own citation tones): see
    ``_pick_lexicalizing_sandhi_rule``/``_has_qualifying_lexicalization_target``/
    ``_lexicalize_sandhi_ipa``'s own docstrings -- only ``sandhi``, never
    ``lexical_sandhi`` (already word-specific, nothing to "become"
    lexical), is a candidate; the chosen rule is dropped from the
    returned system's own ``sandhi`` once it fires, since it no longer
    exists as a live process once every word it could ever have applied
    to already carries the outcome as its own citation tone. Structurally
    gated the same way tonogenesis/split are: no word whose own last
    tone-bearing syllable currently carries the chosen rule's ``before``,
    no raw material, regardless of ``years``.

    **Tonogenesis** (a currently non-tonal language gains tone): modeled
    via the one mechanism this project's own phoneme/coda machinery can
    actually detect -- real coda-glottal-stop loss, the same real
    pathway behind Vietnamese's own historical tone origin (Haudricourt
    1954) -- see ``_tonogenesis_ipa``'s own docstring for the actual
    per-word rule. Structurally gated, not just rate-gated: a language
    with no word anywhere in its own *current* lexicon that has a
    qualifying coda ``ʔ`` has no raw material for this specific pathway
    at all this run (an honest "the process has nothing to work from
    yet" abstention, the same discipline every other structurally-gated
    rule in this project already practices), regardless of how long
    ``years`` is."""
    detonalization_rate = _saturating_rate(years, _HALF_LIVES["detonalization"], contact_intensity)
    if base_tone_system.enabled and rng.random() < detonalization_rate:
        def detonalize(ipas: list[str]) -> tuple[list[str], list[tuple]]:
            return [ipa_tokenizer.strip_tones(ipa) for ipa in ipas], [() for _ in ipas]

        return ToneSystem(enabled=False), detonalize

    if base_tone_system.enabled:
        merger_rate = _saturating_rate(years, _HALF_LIVES["tone_merger"], 0.0)
        if rng.random() < merger_rate:
            pair = _tone_merger_pair(rng, base_tone_system.levels)
            if pair is not None:
                survivor, absorbed = pair

                def merge(ipas: list[str]) -> tuple[list[str], list[tuple]]:
                    converted = [_tone_merger_ipa(ipa, known_symbols, vowel_symbols, survivor, absorbed) for ipa in ipas]
                    return [ipa for ipa, _ in converted], [tones for _, tones in converted]

                new_levels = tuple(level for level in base_tone_system.levels if level != absorbed)
                new_system = ToneSystem(
                    enabled=True, levels=new_levels,
                    sandhi=_remap_tone_sandhi(base_tone_system.sandhi, survivor, absorbed),
                    lexical_sandhi=_remap_lexical_tone_sandhi(base_tone_system.lexical_sandhi, survivor, absorbed),
                )
                return new_system, merge

        split_rate = _saturating_rate(years, _HALF_LIVES["tone_split"], 0.0)
        if rng.random() < split_rate:
            has_raw_material = any(
                _has_qualifying_voiced_onset(ipa_tokenizer.tokenize(ipa, known_symbols), consonant_by_ipa, vowel_symbols)
                for ipa in final_ipas
            )
            if has_raw_material:
                def split(ipas: list[str]) -> tuple[list[str], list[tuple]]:
                    converted = [_tone_split_ipa(ipa, known_symbols, consonant_by_ipa, vowel_symbols) for ipa in ipas]
                    return [ipa for ipa, _ in converted], [tones for _, tones in converted]

                new_levels = tuple(dict.fromkeys((*base_tone_system.levels, *_YANG_TONE.values())))
                return ToneSystem(
                    enabled=True, levels=new_levels,
                    sandhi=base_tone_system.sandhi, lexical_sandhi=base_tone_system.lexical_sandhi,
                ), split

        lexicalizing_rule = _pick_lexicalizing_sandhi_rule(rng, base_tone_system.sandhi)
        if lexicalizing_rule is not None:
            lexicalization_rate = _saturating_rate(years, _HALF_LIVES["sandhi_lexicalization"], 0.0)
            if rng.random() < lexicalization_rate:
                has_raw_material = any(
                    _has_qualifying_lexicalization_target(
                        ipa_tokenizer.tokenize(ipa, known_symbols), vowel_symbols, lexicalizing_rule.before
                    )
                    for ipa in final_ipas
                )
                if has_raw_material:
                    def lexicalize(ipas: list[str]) -> tuple[list[str], list[tuple]]:
                        converted = [_lexicalize_sandhi_ipa(ipa, known_symbols, vowel_symbols, lexicalizing_rule) for ipa in ipas]
                        return [ipa for ipa, _ in converted], [tones for _, tones in converted]

                    new_sandhi = tuple(rule for rule in base_tone_system.sandhi if rule != lexicalizing_rule)
                    new_system = ToneSystem(
                        enabled=True, levels=base_tone_system.levels,
                        sandhi=new_sandhi, lexical_sandhi=base_tone_system.lexical_sandhi,
                    )
                    return new_system, lexicalize

    if not base_tone_system.enabled:
        has_raw_material = any(
            _has_qualifying_coda_glottal_stop(ipa_tokenizer.tokenize(ipa, known_symbols), vowel_symbols)
            for ipa in final_ipas
        )
        tonogenesis_rate = _saturating_rate(years, _HALF_LIVES["tonogenesis"], 0.0)
        if has_raw_material and rng.random() < tonogenesis_rate:
            def gain_tone(ipas: list[str]) -> tuple[list[str], list[tuple]]:
                converted = [_tonogenesis_ipa(ipa, known_symbols, vowel_symbols) for ipa in ipas]
                return [ipa for ipa, _ in converted], [tones for _, tones in converted]

            return ToneSystem(enabled=True, levels=(ToneLevel.HIGH, ToneLevel.LOW)), gain_tone

    return base_tone_system, None


def _inventory_and_structure(
    base_structure: SyllableStructure,
    ipas: list[str],
    known_symbols: tuple[str, ...],
    rng: random.Random,
    traits: TraitProfile,
    lineage_profiles: tuple[reference_languages.ReferenceLanguageProfile, ...],
) -> tuple[PhonemeInventory, SyllableStructure]:
    used_symbols: set[str] = set()
    for ipa in ipas:
        used_symbols.update(ipa_tokenizer.symbols_only(ipa, known_symbols))
    consonants = tuple(sorted((c for c in phonology_gen.ALL_CONSONANTS if c.ipa in used_symbols), key=lambda c: -c.prevalence))
    vowels = tuple(sorted((v for v in phonology_gen.ALL_VOWELS if v.ipa in used_symbols), key=lambda v: -v.prevalence))
    inventory = PhonemeInventory(consonants=consonants, vowels=vowels)
    return inventory, _recompute_syllable_structure(base_structure, consonants, rng, traits, lineage_profiles)


def _coin_native_word(
    rng: random.Random,
    entry: LexicalEntry,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    tone_system,
    word_accent_system,
    grammar,
    lineage_profiles: tuple[reference_languages.ReferenceLanguageProfile, ...] = (),
    strictness: float = 0.0,
) -> tuple[str, tuple[str, ...] | None, str | None]:
    """Native replacement (scenario 2b): an unrelated word for the same
    meaning, coined the same way fresh core-vocabulary generation coins any
    word (``lexicon_gen.py``/``root_pattern.py``), just targeting the
    evolved inventory/structure instead of a freshly generated one. For a
    root-and-pattern language's noun/verb/adjective entries, coins via the
    same template mechanism -- one root, no candidate-then-LLM-pick (unlike
    ``root_pattern.propose_templatic_word``), keeping evolution pure
    rule-based like every other path here. Returns ``(ipa, root,
    word_class)`` -- ``root`` is ``None`` for non-templatic coinage;
    ``word_class`` is this freshly-coined replacement's own new class
    assignment (via ``grammar.word_classes``/``word_class_deviation_rate``,
    the same as any other coinage path), never the old entry's.

    ``lineage_profiles`` is the evolving language's own heritage (``evolve_language``'s
    ``lineage_profiles``, not the current run's possibly-empty ``reference_profiles`` --
    this whole function is only ever called when ``reference_profiles`` is
    empty in the first place, i.e. no *new* contact this run), so a
    Dutch-lineage language replacing a word still stresses it the way
    Dutch would, not via the generic baseline."""
    stress_pattern, stress_deviation_rate = stress_gen.resolve_stress_pattern(lineage_profiles)
    word_accent_pattern = ""
    word_accent_deviation_rate: float | None = None
    word_accent_length_rate: float | None = None
    word_accent_window: int | None = None
    if word_accent_system.enabled:
        (
            _, word_accent_pattern, word_accent_deviation_rate, word_accent_length_rate, word_accent_window,
        ) = word_accent_gen.resolve_word_accent(lineage_profiles)

    if grammar.uses_root_and_pattern and entry.pos in root_pattern.TEMPLATIC_POS and grammar.templates:
        template = root_pattern.template_for_pos(rng, grammar.templates, entry.pos)
        root = root_pattern.generate_root(rng, inventory, structure, template.skeleton)
        root_iter = iter(root)
        filled_symbols = tuple(next(root_iter) if slot == "C" else slot for slot in template.skeleton)
        vowel_symbols = frozenset(v.ipa for v in inventory.vowels)
        stressed = word_accent_gen.mark_stress_and_word_accent(
            rng, filled_symbols, vowel_symbols, stress_pattern, stress_deviation_rate, strictness,
            word_accent_realization=word_accent_system.realization,
            word_accent_pattern=word_accent_pattern,
            word_accent_deviation_rate=word_accent_deviation_rate,
            word_accent_length_rate=word_accent_length_rate,
            word_accent_window=word_accent_window,
        )
        assigned_class = word_class_gen.assign_word_class(rng, grammar.word_classes, grammar.word_class_deviation_rate, entry.pos)
        stressed = word_class_gen.apply_word_class(
            rng, assigned_class, stressed, inventory,
            stress_pattern, stress_deviation_rate, strictness,
            word_accent_realization=word_accent_system.realization, word_accent_pattern=word_accent_pattern,
            word_accent_deviation_rate=word_accent_deviation_rate, word_accent_length_rate=word_accent_length_rate,
            word_accent_window=word_accent_window,
        )
        return stressed, root, (assigned_class.name if assigned_class is not None else None)

    num_syllables = lexicon_gen.choose_syllable_count(rng, entry.pos, favor_short=True)
    tone_marks: tuple[str, ...] = ()
    if tone_system.enabled:
        drawn_tones = tuple(rng.choice(tone_system.levels) for _ in range(num_syllables))
        if any(p.tone_shift_to_antepenult for p in lineage_profiles):
            drawn_tones = lexicon_gen.shift_high_tone_to_antepenult(drawn_tones)
        tone_marks = tuple(tone_system.mark("", tone) for tone in drawn_tones)
    word = word_builder.build_word(
        rng, inventory, structure, num_syllables, tone_marks,
        stress_pattern=stress_pattern, stress_deviation_rate=stress_deviation_rate, stress_strictness=strictness,
        word_accent_realization=word_accent_system.realization,
        word_accent_pattern=word_accent_pattern,
        word_accent_deviation_rate=word_accent_deviation_rate,
        word_accent_strictness=strictness,
        word_accent_length_rate=word_accent_length_rate,
        word_accent_window=word_accent_window,
    )
    assigned_class = word_class_gen.assign_word_class(rng, grammar.word_classes, grammar.word_class_deviation_rate, entry.pos)
    word = word_class_gen.apply_word_class(
        rng, assigned_class, word, inventory,
        stress_pattern, stress_deviation_rate, strictness,
        word_accent_realization=word_accent_system.realization, word_accent_pattern=word_accent_pattern,
        word_accent_deviation_rate=word_accent_deviation_rate, word_accent_length_rate=word_accent_length_rate,
        word_accent_window=word_accent_window,
    )
    return word, None, (assigned_class.name if assigned_class is not None else None)


def _coin_borrowed_word(
    rng: random.Random,
    entry: LexicalEntry,
    weighted_profiles: tuple,
    consonant_by_ipa: dict,
    vowel_by_ipa: dict,
) -> tuple[str, str]:
    """Wholesale borrowing (scenario 2a): coin a word from a matched
    reference language's own phoneme palette and romanize it with that
    language's own spelling conventions (Milestone A's reference-aware
    ``generate_romanization``) rather than this language's own systemic
    rules -- the borrowed word keeps its foreign spelling, it isn't
    respelled. Which language a given borrowed word comes from is a
    weighted choice, not a uniform one -- a 70%-weighted contact language
    should supply most borrowings, a 30%-weighted one a real but smaller
    minority, the same relative-influence reading `source_language_
    weights` has everywhere else."""
    profiles = [p for p, _ in weighted_profiles]
    weights = [w for _, w in weighted_profiles]
    profile = rng.choices(profiles, weights=weights)[0]
    consonants = tuple(c for s in profile.consonants if (c := consonant_by_ipa.get(s)) is not None)
    vowels = tuple(v for s in profile.vowels if (v := vowel_by_ipa.get(s)) is not None)
    inventory = PhonemeInventory(consonants=consonants, vowels=vowels)
    max_coda = 0 if profile.coda_profile == "none" else 1
    structure = SyllableStructure(max_onset=1, max_coda=max_coda)
    num_syllables = lexicon_gen.choose_syllable_count(
        rng, entry.pos, favor_short=True,
        average_syllables=profile.core_vocabulary_average_syllables, strictness=1.0,
    )
    ipa = word_builder.build_word(rng, inventory, structure, num_syllables)
    scheme = romanization_gen.generate_romanization(rng, inventory, (profile.name,))
    return ipa, scheme.apply(ipa)


def evolve_language(
    name: str,
    base: Language,
    years: int,
    traits: TraitProfile,
    seed: int,
    forced_orthography: OrthographyForce = OrthographyForce(),
) -> Language:
    rng = random.Random(seed)
    rates = _compute_rates(years, traits)
    orthography_rates = _compute_orthography_rates(years, traits)
    # A language's own reference-language *lineage* (Dutch's own curated
    # x->ch/au->ou/ɛi->ij rules, say) needs to stay available for
    # newly-reformed symbols even on a run that adds no *new* contact --
    # `traits.source_languages` alone is this run's active contact only,
    # and evolving with a neutral TraitProfile() would otherwise silently
    # lose every one of the base language's own curated spellings the
    # moment a symbol gets reformed. Merged (not replaced) so a run that
    # *does* add new contact still keeps the original lineage's rules
    # too, and persisted onto the returned language's own spec (below) so
    # a second evolution generation inherits the same lineage in turn.
    lineage_languages = tuple(dict.fromkeys((*base.spec.traits.source_languages, *traits.source_languages)))
    # Same union, for each name's own *weight*: the base language's own
    # prior weight persists unless this run's own `traits` re-states a
    # weight for that same name, in which case the fresh, current-run
    # value wins (this evolution's own contact intensity is presumably
    # what the caller actually means "now," not a stale weight from
    # however the base language was originally generated). A name with
    # no weight recorded anywhere defaults to 1.0, matching
    # `match_profiles_weighted`'s own "unweighted means equal" fallback.
    lineage_weight_by_name: dict[str, float] = {
        name: (base.spec.traits.source_language_weights[i] if i < len(base.spec.traits.source_language_weights) else 1.0)
        for i, name in enumerate(base.spec.traits.source_languages)
    }
    lineage_weight_by_name.update(
        {
            name: (traits.source_language_weights[i] if i < len(traits.source_language_weights) else 1.0)
            for i, name in enumerate(traits.source_languages)
        }
    )
    lineage_weights = tuple(lineage_weight_by_name.get(name, 1.0) for name in lineage_languages)
    # Same lineage, used for phonotactic constraints (e.g. Dutch's coda-
    # devoicing) rather than orthography this time -- a separate variable
    # from `reference_profiles` below (which is deliberately current-run-
    # only, for lexical borrowing) for the same reason lineage and active
    # contact stay distinct concepts for orthography.
    lineage_profiles = reference_languages.match_profiles(lineage_languages)

    consonant_by_ipa = {c.ipa: c for c in phonology_gen.ALL_CONSONANTS}
    vowel_by_ipa = {v.ipa: v for v in phonology_gen.ALL_VOWELS}
    # Tokenizing against the *full global* phoneme pool here (every symbol
    # this project can ever model, across every unrelated language
    # profile) is a correctness bug, not just an inefficiency:
    # `ipa_tokenizer`'s greedy-longest-match can mis-parse two real,
    # adjacent single-character phonemes (e.g. one syllable's coda "n"
    # immediately followed by the next syllable's onset "z") as a
    # *different*, unrelated multi-character phoneme that merely happens
    # to share that spelling in some *other* profile's own palette (e.g.
    # Swahili's prenasalized stop "nz", `phonology_gen.ALL_CONSONANTS`)
    # -- one this language never actually has. `known_symbols`/
    # `reconstruction_symbols` below run every multi-character candidate
    # through `_tokenizer_pool` -- restricted to what this language could
    # actually produce -- while every single-character candidate stays
    # global (see that function's own docstring for why: a grammatical
    # affix can inject a literal single-character symbol, e.g. a Dutch-
    # style plural suffix's own schwa, that never went through phoneme
    # selection at all, and narrowing single characters too would
    # silently drop those instead of just mis-tokenizing them).
    # `consonant_by_ipa`/`vowel_by_ipa` above stay global regardless --
    # those resolve a symbol's phonological *properties* (sonority,
    # voicing, place/manner) once a rule has already decided to
    # introduce it, an unrelated question from "what should the
    # tokenizer's own candidate set be."
    single_char_symbols = frozenset(s for s in (*consonant_by_ipa, *vowel_by_ipa) if len(s) == 1)
    base_symbols = frozenset(base.phonology.all_symbols())
    known_symbols = _tokenizer_pool(single_char_symbols, base_symbols)
    reconstruction_symbols = _tokenizer_pool(single_char_symbols, base_symbols | _reachable_sound_change_symbols(rates))

    evolved_pairs = [
        _evolve_ipa(entry.ipa, rng, rates, known_symbols, consonant_by_ipa, vowel_by_ipa)
        for entry in base.lexicon.entries
    ]
    evolved_ipas = [evolved for evolved, _ in evolved_pairs]
    spelling_ipas = [spelling for _, spelling in evolved_pairs]
    # Provisional inventory/structure from sound-changed IPA only -- the
    # coinage target for any native (non-borrowed) lexical replacements
    # below, before borrowed/replaced words can widen it further.
    provisional_inventory, provisional_structure = _inventory_and_structure(
        base.syllable_structure, evolved_ipas, reconstruction_symbols, rng, traits, lineage_profiles
    )
    reference_profiles = reference_languages.match_profiles(traits.source_languages)
    weighted_reference_profiles = reference_languages.match_profiles_weighted(
        traits.source_languages, traits.source_language_weights
    )
    # Borrowed replacements (pass 1 below) coin a word from a *reference*
    # profile's own palette, not this language's own -- widen the
    # reconstruction pool to match, same "only as tight as this run can
    # actually produce" discipline as `reconstruction_symbols` above, so
    # a borrowed word's own genuine phonemes don't trip the same
    # tokenizer ambiguity from the opposite direction (a real reference-
    # language multi-character phoneme wrongly split into single
    # characters because it wasn't a tokenizer candidate at all).
    final_reconstruction_symbols = reconstruction_symbols
    if reference_profiles:
        final_reconstruction_symbols = tuple(
            frozenset(reconstruction_symbols)
            | {symbol for profile, _ in weighted_reference_profiles for symbol in (*profile.consonants, *profile.vowels)}
        )

    # Pass 1: lexical replacement (scenarios 2a/2b) -- decide per entry
    # whether the whole word (not just its sound) gets replaced, at a rate
    # scaled by that entry's POS-based stability tier (pronouns/numerals
    # resist replacement far longer than nouns/verbs -- see
    # lexicon_gen.STABILITY_TIER). Borrowed words get their romanization
    # right here too, from the source language's own conventions; everything
    # else keeps its evolved IPA from above and gets its romanization from
    # the one evolved scheme built below.
    final_ipas: list[str] = []
    borrowed_romanizations: dict[int, str] = {}
    replaced_native: set[int] = set()
    replaced_roots: dict[int, tuple[str, ...]] = {}
    replaced_word_classes: dict[int, str | None] = {}
    for i, (entry, evolved_ipa) in enumerate(zip(base.lexicon.entries, evolved_ipas)):
        if rng.random() < _replacement_rate(years, traits, entry.pos):
            if reference_profiles:
                ipa, latin = _coin_borrowed_word(rng, entry, weighted_reference_profiles, consonant_by_ipa, vowel_by_ipa)
                final_ipas.append(ipa)
                borrowed_romanizations[i] = latin
            else:
                ipa, root, word_class = _coin_native_word(
                    rng, entry, provisional_inventory, provisional_structure, base.tone_system, base.word_accent, base.grammar,
                    lineage_profiles=lineage_profiles, strictness=traits.source_language_strictness,
                )
                final_ipas.append(ipa)
                replaced_native.add(i)
                if root is not None:
                    replaced_roots[i] = root
                replaced_word_classes[i] = word_class
        else:
            final_ipas.append(evolved_ipa)

    # Tone *system*-level change (detonalization/tonogenesis, see
    # `_evolve_tone_system`'s own docstring) -- after every word's own
    # sound change/replacement above (so it sees the words this run's
    # lexicon actually ends up with, borrowings included), before
    # inventory/structure reconstruction (so a tonogenesis run's own
    # removed coda ʔ and a detonalization run's own stripped tone marks
    # are both reflected in what gets reconstructed below, not the
    # pre-transition state). Applied identically to `spelling_ipas` too
    # (the separate, sometimes-different basis a word's own spelling is
    # reconstructed from below) via the same returned `transform`, not a
    # second call -- a second call would re-roll `rng` and could decide
    # differently, desyncing a word's own stored IPA from its own spelling.
    new_tone_system, tone_transform = _evolve_tone_system(
        rng, base.tone_system, years, traits.contact_intensity, final_ipas,
        final_reconstruction_symbols, frozenset(vowel_by_ipa), consonant_by_ipa,
    )
    tones_by_entry: list[tuple] | None = None
    if tone_transform is not None:
        final_ipas, tones_by_entry = tone_transform(final_ipas)
        spelling_ipas, _ = tone_transform(spelling_ipas)

    inventory, syllable_structure = _inventory_and_structure(
        base.syllable_structure, final_ipas, final_reconstruction_symbols, rng, traits, lineage_profiles
    )
    romanization = romanization_gen.evolve_romanization(
        base.romanization, inventory, rng, lineage_languages,
        reform_rate=orthography_rates.reform, drift_rate=orthography_rates.drift,
        forced_orthography=forced_orthography,
        strictness=traits.source_language_strictness,
        source_language_weights=lineage_weights,
    )

    # Pass 2: every non-replaced entry's spelling comes from the one
    # evolved scheme above -- decided per symbol, so words sharing a symbol
    # always agree, and so a reform is a language-wide convention change,
    # not a per-word one: it touches every word using the reformed symbol,
    # whether or not that particular word's own sound moved this run (real
    # spelling reforms work the same way -- they land on every word with
    # the affected pattern, not just ones whose pronunciation happened to
    # shift). Concretely: `latin` always comes from applying the *current*
    # (possibly-reformed) scheme to this entry's own (spelling-oriented)
    # IPA, compared against what the *unreformed* base scheme would have
    # produced for that same IPA -- isolates orthography evolution's own
    # effect from the sound change that already happened above. Only when
    # the two agree (no reform touched any symbol this word uses) *and*
    # the word's sound didn't move either does this fall back to the
    # word's own stored spelling verbatim rather than the reconstruction --
    # protects a real or curated spelling exception the general rule table
    # can't capture, the same "why real orthographies end up with silent
    # letters" freeze `evolve_romanization` already models per symbol.
    evolved_entries = []
    for i, (entry, final_ipa) in enumerate(zip(base.lexicon.entries, final_ipas)):
        root: tuple[str, ...] | None = entry.root
        word_class: str | None = entry.word_class
        if i in borrowed_romanizations:
            latin = apply_grammatical_spelling(romanization, borrowed_romanizations[i], entry.pos)
            path = "borrowed"
            root = None  # a foreign borrowing has no native root of its own
            word_class = None  # a foreign borrowing doesn't follow this language's own declension/conjugation classes either
        elif i in replaced_native:
            latin = apply_grammatical_spelling(romanization, romanization.apply(final_ipa), entry.pos)
            path = "replaced"
            root = replaced_roots.get(i)  # a new native root, or None if this wasn't templatic
            word_class = replaced_word_classes.get(i)  # this fresh replacement's own new class assignment, not the old word's
        else:
            # This branch is only reached for an entry pass 1 didn't
            # replace, so `final_ipa` is exactly `evolved_ipas[i]` by
            # construction -- `spelling_ipas[i]` is its matching
            # spelling-oriented counterpart (see `_evolve_ipa`'s own
            # docstring): identical to `final_ipa` unless a word-final
            # devoicing this run should still spell as its pre-devoicing
            # voiced form (Dutch "berg" [bɛrx], spelled "g").
            spelling_ipa = spelling_ipas[i]
            latin = apply_grammatical_spelling(romanization, romanization.apply(spelling_ipa), entry.pos)
            unreformed = apply_grammatical_spelling(base.romanization, base.romanization.apply(spelling_ipa), entry.pos)
            if latin != unreformed:
                path = "reformed"
            elif final_ipa == entry.ipa:
                latin = entry.romanization
                path = "unchanged"
            else:
                path = "conventional"
        update = {
            "ipa": final_ipa, "romanization": latin, "notes": f"orthography: {path}",
            "root": root, "word_class": word_class,
        }
        if tones_by_entry is not None:
            # A tone-system transition this run (see `_evolve_tone_system`)
            # replaces every entry's own `tones` too, regardless of which
            # of the three paths above it took -- once a language gains or
            # loses tone as a system, that applies uniformly, not just to
            # entries that also happened to change some other way this run.
            update["tones"] = tones_by_entry[i]
        evolved_entries.append(entry.model_copy(update=update))
    evolved_entries = tuple(evolved_entries)

    spec = GenerationSpec(
        prompt=f"evolved from '{base.name}' over {years} years",
        seed=seed,
        traits=traits.model_copy(update={"source_languages": lineage_languages, "source_language_weights": lineage_weights}),
    )

    return Language(
        name=name,
        spec=spec,
        phonology=inventory,
        syllable_structure=syllable_structure,
        tone_system=new_tone_system,
        word_accent=base.word_accent,
        romanization=romanization,
        grammar=base.grammar,
        lexicon=Lexicon(entries=evolved_entries, idioms=base.lexicon.idioms),
        history=base.history + (f"evolved {years} years (seed={seed})",),
    )
