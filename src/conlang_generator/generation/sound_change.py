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

Grammar and tone system are copied from the base language unchanged (word-
level focus only, per current project direction). The evolved
``PhonemeInventory``/``SyllableStructure`` are recomputed from what the
evolved lexicon actually uses.

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
from conlang_generator.core.phonology import Manner, PhonemeInventory, SyllableStructure, VowelBackness
from conlang_generator.core.romanization import OrthographyForce, apply_grammatical_spelling
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
    word_builder,
)

_VOICELESS_TO_VOICED: dict[str, str] = {
    "p": "b", "t": "d", "k": "g", "ʈ": "ɖ", "c": "ɟ", "tʃ": "dʒ",
    "s": "z", "f": "v", "ʃ": "ʒ", "ʂ": "ʐ", "θ": "ð", "ç": "ʝ", "χ": "ʁ", "x": "ɣ",
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


def _apply_lenition(tokens: list[Token], rng: random.Random, rate: float, vowel_by_ipa: dict) -> list[Token]:
    if rate <= 0:
        return tokens
    result = list(tokens)
    for i, (symbol, deco) in enumerate(result):
        if symbol not in _VOICELESS_TO_VOICED or i == 0 or i == len(result) - 1:
            continue
        if result[i - 1][0] in vowel_by_ipa and result[i + 1][0] in vowel_by_ipa and rng.random() < rate:
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
    the way real orthography does. ``None`` when nothing devoiced."""
    if rate <= 0 or not tokens:
        return tokens, None
    result = list(tokens)
    symbol, deco = result[-1]
    consonant = consonant_by_ipa.get(symbol)
    if consonant is not None and consonant.voiced and symbol in _VOICED_TO_VOICELESS and rng.random() < rate:
        result[-1] = (_VOICED_TO_VOICELESS[symbol], deco)
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
    if rate <= 0:
        return tokens
    result = list(tokens)
    seen_first_vowel = False
    for i, (symbol, deco) in enumerate(result):
        if symbol not in vowel_by_ipa:
            continue
        if not seen_first_vowel:
            seen_first_vowel = True
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
    onset_pairs = sonority.legal_onset_pairs(consonants)
    allowed_onset_clusters = (
        sonority.thin_cluster_pairs(rng, onset_pairs, traits.contact_intensity) if base.max_onset >= 2 else ()
    )
    if base.max_coda == 0:
        max_coda, allowed_coda_consonants, allowed_coda_clusters, excluded_coda_consonants = 0, None, (), ()
    elif base.allowed_coda_consonants is not None:
        sonorants = tuple(c.ipa for c in consonants if c.ipa == "ʔ" or sonority.sonority(c) >= 3)
        max_coda, allowed_coda_consonants, allowed_coda_clusters, excluded_coda_consonants = (
            (1, sonorants, (), ()) if sonorants else (0, None, (), ())
        )
    else:
        excluded_coda_consonants = ()
        if any(p.coda_devoicing for p in lineage_profiles):
            excluded_coda_consonants = tuple(
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
        allowed_coda_consonants=allowed_coda_consonants,
        excluded_coda_consonants=excluded_coda_consonants,
        vowel_harmony=base.vowel_harmony,
    )


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
    grammar,
) -> tuple[str, tuple[str, ...] | None]:
    """Native replacement (scenario 2b): an unrelated word for the same
    meaning, coined the same way fresh core-vocabulary generation coins any
    word (``lexicon_gen.py``/``root_pattern.py``), just targeting the
    evolved inventory/structure instead of a freshly generated one. For a
    root-and-pattern language's noun/verb/adjective entries, coins via the
    same template mechanism -- one root, no candidate-then-LLM-pick (unlike
    ``root_pattern.propose_templatic_word``), keeping evolution pure
    rule-based like every other path here. Returns ``(ipa, root)`` --
    ``root`` is ``None`` for non-templatic coinage."""
    if grammar.uses_root_and_pattern and entry.pos in root_pattern.TEMPLATIC_POS and grammar.templates:
        template = root_pattern.template_for_pos(rng, grammar.templates, entry.pos)
        root = root_pattern.generate_root(rng, inventory)
        return root_pattern.fill_template(template, root), root

    num_syllables = lexicon_gen.choose_syllable_count(rng, entry.pos, favor_short=True)
    tone_marks: tuple[str, ...] = ()
    if tone_system.enabled:
        tone_marks = tuple(tone_system.mark("", rng.choice(tone_system.levels)) for _ in range(num_syllables))
    return word_builder.build_word(rng, inventory, structure, num_syllables, tone_marks), None


def _coin_borrowed_word(
    rng: random.Random,
    entry: LexicalEntry,
    reference_profiles: tuple,
    consonant_by_ipa: dict,
    vowel_by_ipa: dict,
) -> tuple[str, str]:
    """Wholesale borrowing (scenario 2a): coin a word from a matched
    reference language's own phoneme palette and romanize it with that
    language's own spelling conventions (Milestone A's reference-aware
    ``generate_romanization``) rather than this language's own systemic
    rules -- the borrowed word keeps its foreign spelling, it isn't
    respelled."""
    profile = rng.choice(reference_profiles)
    consonants = tuple(c for s in profile.consonants if (c := consonant_by_ipa.get(s)) is not None)
    vowels = tuple(v for s in profile.vowels if (v := vowel_by_ipa.get(s)) is not None)
    inventory = PhonemeInventory(consonants=consonants, vowels=vowels)
    max_coda = 0 if profile.coda_profile == "none" else 1
    structure = SyllableStructure(max_onset=1, max_coda=max_coda)
    num_syllables = lexicon_gen.choose_syllable_count(rng, entry.pos, favor_short=True)
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
    # `traits.contact_languages` alone is this run's active contact only,
    # and evolving with a neutral TraitProfile() would otherwise silently
    # lose every one of the base language's own curated spellings the
    # moment a symbol gets reformed. Merged (not replaced) so a run that
    # *does* add new contact still keeps the original lineage's rules
    # too, and persisted onto the returned language's own spec (below) so
    # a second evolution generation inherits the same lineage in turn.
    lineage_languages = tuple(dict.fromkeys((*base.spec.traits.contact_languages, *traits.contact_languages)))
    # Same lineage, used for phonotactic constraints (e.g. Dutch's coda-
    # devoicing) rather than orthography this time -- a separate variable
    # from `reference_profiles` below (which is deliberately current-run-
    # only, for lexical borrowing) for the same reason lineage and active
    # contact stay distinct concepts for orthography.
    lineage_profiles = reference_languages.match_profiles(lineage_languages)

    consonant_by_ipa = {c.ipa: c for c in phonology_gen.ALL_CONSONANTS}
    vowel_by_ipa = {v.ipa: v for v in phonology_gen.ALL_VOWELS}
    known_symbols = tuple(consonant_by_ipa) + tuple(vowel_by_ipa)

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
        base.syllable_structure, evolved_ipas, known_symbols, rng, traits, lineage_profiles
    )
    reference_profiles = reference_languages.match_profiles(traits.contact_languages)

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
    for i, (entry, evolved_ipa) in enumerate(zip(base.lexicon.entries, evolved_ipas)):
        if rng.random() < _replacement_rate(years, traits, entry.pos):
            if reference_profiles:
                ipa, latin = _coin_borrowed_word(rng, entry, reference_profiles, consonant_by_ipa, vowel_by_ipa)
                final_ipas.append(ipa)
                borrowed_romanizations[i] = latin
            else:
                ipa, root = _coin_native_word(
                    rng, entry, provisional_inventory, provisional_structure, base.tone_system, base.grammar
                )
                final_ipas.append(ipa)
                replaced_native.add(i)
                if root is not None:
                    replaced_roots[i] = root
        else:
            final_ipas.append(evolved_ipa)

    inventory, syllable_structure = _inventory_and_structure(
        base.syllable_structure, final_ipas, known_symbols, rng, traits, lineage_profiles
    )
    romanization = romanization_gen.evolve_romanization(
        base.romanization, inventory, rng, lineage_languages,
        reform_rate=orthography_rates.reform, drift_rate=orthography_rates.drift,
        forced_orthography=forced_orthography,
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
        if i in borrowed_romanizations:
            latin = apply_grammatical_spelling(romanization, borrowed_romanizations[i], entry.pos)
            path = "borrowed"
            root = None  # a foreign borrowing has no native root of its own
        elif i in replaced_native:
            latin = apply_grammatical_spelling(romanization, romanization.apply(final_ipa), entry.pos)
            path = "replaced"
            root = replaced_roots.get(i)  # a new native root, or None if this wasn't templatic
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
        evolved_entries.append(
            entry.model_copy(
                update={"ipa": final_ipa, "romanization": latin, "notes": f"orthography: {path}", "root": root}
            )
        )
    evolved_entries = tuple(evolved_entries)

    spec = GenerationSpec(
        prompt=f"evolved from '{base.name}' over {years} years",
        seed=seed,
        traits=traits.model_copy(update={"contact_languages": lineage_languages}),
    )

    return Language(
        name=name,
        spec=spec,
        phonology=inventory,
        syllable_structure=syllable_structure,
        tone_system=base.tone_system,
        romanization=romanization,
        grammar=base.grammar,
        lexicon=Lexicon(entries=evolved_entries, idioms=base.lexicon.idioms),
        history=base.history + (f"evolved {years} years (seed={seed})",),
    )
