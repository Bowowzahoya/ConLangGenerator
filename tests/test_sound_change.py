"""Tests for the diachronic sound-change engine (generation/sound_change.py).

Several comparisons below deliberately reuse the same ``seed`` across two
trait variants: since every rule always consumes exactly one rng draw per
eligible position regardless of outcome (same pattern used throughout
``phonology_gen.py``), the same seed means the *same underlying random
draws* get compared against a higher vs. lower rate -- so "low rate < high
rate" is guaranteed monotonic, not just statistically likely, and these
tests can't be flaky.
"""

import pytest
import random
from collections import Counter
from dataclasses import replace

from conlang_generator.core.grammar import Alignment, GrammarProfile, MorphologicalType, WordOrder, WordTemplate
from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import LexicalEntry, Lexicon, PartOfSpeech
from conlang_generator.core.phonology import TONE_DIACRITICS, Consonant, LexicalToneSandhiRule, Manner, Place, PhonemeInventory, SyllableStructure, ToneLevel, ToneSandhiRule, ToneSystem, Vowel, VowelBackness, VowelHeight, WordAccentSystem
from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK, RomanizationRule, RomanizationScheme, apply_grammatical_spelling
from conlang_generator.core.spec import GenerationSpec, SeedExample
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import ipa_tokenizer, lexicon_gen, phonology_gen, sonority, sound_change
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.reference_languages import REFERENCE_LANGUAGES, ReferenceLanguageProfile
from conlang_generator.generation.sound_change import evolve_language
from conlang_generator.llm.fake_client import FakeLLMClient

_KNOWN_SYMBOLS = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
_CONSONANT_BY_IPA = {c.ipa: c for c in phonology_gen.ALL_CONSONANTS}
_VOWEL_BY_IPA = {v.ipa: v for v in phonology_gen.ALL_VOWELS}
_ZERO_RATES = sound_change._Rates(
    lenition=0.0, final_devoicing=0.0, cluster_simplification=0.0,
    palatalization=0.0, vowel_reduction=0.0, ejective_drift=0.0,
)


def _base_language():
    return generate_language("Base", GenerationSpec(prompt="base", seed=16), FakeLLMClient())


def _changed_count(base, years, traits, seed) -> int:
    evolved = evolve_language("Evolved", base, years, traits, seed)
    return sum(1 for old, new in zip(base.lexicon.entries, evolved.lexicon.entries) if old.ipa != new.ipa)


def test_zero_years_produces_no_changes():
    base = _base_language()
    evolved = evolve_language("Evolved", base, 0, TraitProfile(), seed=1)
    assert [e.ipa for e in base.lexicon.entries] == [e.ipa for e in evolved.lexicon.entries]


def test_weighted_spelling_alternatives_dont_spuriously_reform_at_zero_years():
    # Regression guard for RomanizationRule.weight's reform-detection
    # hazard: evolve_romanization compares apply()'s output on the current
    # vs. pre-reform scheme to decide whether a symbol was reformed. If
    # that comparison rolled independent random alternatives each call
    # (rather than a stable, ipa_text-keyed pick), a tied symbol like
    # French /o/ ("o"/"au"/"eau") could show up as spuriously "reformed"
    # even with zero actual sound or orthography change. At years=0
    # nothing should move at all.
    # seed=3 -- empirically-found (see the seed-search convention noted
    # elsewhere in this file). Was briefly swapped to seed=0 while a
    # separate, unrelated tokenizer bug was diagnosed (this seed's base
    # word's raw IPA happens to contain the substring "nz" -- the
    # concatenation of two adjacent single-consonant syllable onsets --
    # which sound_change._inventory_and_structure's own symbol
    # reconstruction mis-tokenized as the *distinct* modeled "nz"
    # prenasalized-stop phoneme); restored to seed=3 now that
    # _tokenizer_pool fixes that root cause (see
    # test_reconstruction_never_lets_an_unrelated_multichar_phoneme_
    # swallow_two_adjacent_real_ones below for a direct regression test).
    base = generate_language(
        "Base", GenerationSpec(prompt="p", seed=3, traits=TraitProfile(source_languages=("French",), source_language_strictness=1.0)),
        FakeLLMClient(),
    )
    evolved = evolve_language("Evolved", base, 0, TraitProfile(source_languages=("French",), source_language_strictness=1.0), seed=1)
    assert [e.ipa for e in base.lexicon.entries] == [e.ipa for e in evolved.lexicon.entries]
    assert [e.romanization for e in base.lexicon.entries] == [e.romanization for e in evolved.lexicon.entries]


def test_reconstruction_never_lets_an_unrelated_multichar_phoneme_swallow_two_adjacent_real_ones():
    # Direct, synthetic reproduction of the tokenizer-ambiguity bug noted
    # above, rather than relying on stumbling onto the right seed:
    # `phonology_gen.ALL_CONSONANTS` models a genuine Swahili-style
    # prenasalized stop "nz" (a single, atomic multi-character phoneme in
    # *that* profile's own palette) purely as a distinct, unrelated global
    # entry -- it has nothing to do with this test's own hand-built
    # language, which has real, separate "n" and "z" consonants and no
    # "nz" phoneme of its own at all. A word whose coda "n" happens to
    # sit immediately before the next syllable's onset "z" (no vowel
    # between them) produces the literal substring "nz" in its raw IPA --
    # exactly the coincidental collision `_inventory_and_structure`'s own
    # symbol reconstruction used to mis-tokenize as the *global* "nz"
    # phoneme when it tokenized against the full global pool instead of
    # this language's own real, reconstructed inventory.
    consonants = (
        Consonant(ipa="n", place=Place.ALVEOLAR, manner=Manner.NASAL, voiced=True, prevalence=0.9),
        Consonant(ipa="z", place=Place.ALVEOLAR, manner=Manner.FRICATIVE, voiced=True, prevalence=0.9),
    )
    vowels = (Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=1.0),)
    phonology = PhonemeInventory(consonants=consonants, vowels=vowels)
    structure = SyllableStructure(max_onset=1, max_coda=1)
    romanization = RomanizationScheme(
        rules=(
            RomanizationRule(ipa="a", latin="a"),
            RomanizationRule(ipa="n", latin="n"),
            RomanizationRule(ipa="z", latin="z"),
        ),
        vowel_symbols=("a",),
    )
    grammar = GrammarProfile(
        word_order=WordOrder.SVO, morphological_type=MorphologicalType.ISOLATING, alignment=Alignment.NOMINATIVE_ACCUSATIVE,
        has_articles=False, adjective_after_noun=False, has_overt_copula=True,
    )
    # "an.za" -- coda "n" immediately followed by the next syllable's own
    # onset "z", the real structural source of a coincidental "nz" run.
    entry = LexicalEntry(ipa="anza", romanization="anza", glosses=("test",), pos=PartOfSpeech.NOUN)
    base = Language(
        name="Base", spec=GenerationSpec(prompt="p", seed=0), phonology=phonology, syllable_structure=structure,
        tone_system=ToneSystem(), romanization=romanization, grammar=grammar, lexicon=Lexicon(entries=(entry,)),
    )
    # years=0 -- no sound change should fire at all, isolating this to
    # reconstruction's own tokenization rather than any rule's behavior.
    evolved = evolve_language("Evolved", base, 0, TraitProfile(), seed=1)
    assert evolved.lexicon.entries[0].ipa == "anza"
    assert set(evolved.phonology.consonant_symbols()) == {"n", "z"}
    assert all(rule.ipa != "nz" for rule in evolved.romanization.rules)


def test_more_years_changes_more_words():
    base = _base_language()
    assert _changed_count(base, 20, TraitProfile(), seed=1) < _changed_count(base, 2000, TraitProfile(), seed=1)


def test_deterministic_for_same_inputs():
    base = _base_language()
    a = evolve_language("Evolved", base, 300, TraitProfile(contact_intensity=0.5), seed=7)
    b = evolve_language("Evolved", base, 300, TraitProfile(contact_intensity=0.5), seed=7)
    assert [e.ipa for e in a.lexicon.entries] == [e.ipa for e in b.lexicon.entries]


def test_evolving_with_no_new_contact_still_keeps_the_base_languages_own_lineage():
    # Regression for a real bug: evolve_language() used to pass only *this
    # run's* traits.source_languages into evolve_romanization(), so a
    # "no new influence" evolution (a bare TraitProfile()) silently lost
    # the base language's own reference-language identity (e.g. Dutch's
    # own curated x->ch/au->ou rules) the moment a symbol got reformed --
    # even though the base was generated with source_languages=("Dutch",).
    # The fix merges the base's own lineage forward; this checks it's
    # both used this run (see the end-to-end test below) and persisted
    # onto the returned language so a *second* evolution generation
    # inherits it too, without needing to re-specify it every time.
    base = generate_language(
        "Dutch", GenerationSpec(prompt="Dutch", seed=3, traits=TraitProfile(source_languages=("Dutch",))), FakeLLMClient()
    )
    evolved = evolve_language("Evolved", base, 100, TraitProfile(), seed=1)
    assert "Dutch" in evolved.spec.traits.source_languages

    # A new contact language this run is *added* to the lineage, not
    # substituted for it -- both should be reachable for future reforms.
    evolved_with_contact = evolve_language(
        "Evolved", base, 100, TraitProfile(source_languages=("Chinese",)), seed=1
    )
    assert "Dutch" in evolved_with_contact.spec.traits.source_languages
    assert "Chinese" in evolved_with_contact.spec.traits.source_languages


def test_lineage_weights_persist_a_base_languages_own_weight_unless_restated():
    base = generate_language(
        "Base",
        GenerationSpec(
            prompt="p", seed=3,
            traits=TraitProfile(source_languages=("Dutch", "German"), source_language_weights=(0.8, 0.2)),
        ),
        FakeLLMClient(),
    )
    # No new contact this run -- the base's own weights should persist
    # unchanged, not silently reset to equal weighting.
    evolved = evolve_language("Evolved", base, 100, TraitProfile(), seed=1)
    weights_by_name = dict(zip(evolved.spec.traits.source_languages, evolved.spec.traits.source_language_weights))
    assert weights_by_name["Dutch"] == 0.8
    assert weights_by_name["German"] == 0.2

    # This run *does* restate Dutch's own weight -- the fresh value wins
    # for that name; German's own prior weight (not restated) persists.
    evolved_restated = evolve_language(
        "Evolved", base, 100, TraitProfile(source_languages=("Dutch",), source_language_weights=(0.3,)), seed=1
    )
    restated_weights = dict(
        zip(evolved_restated.spec.traits.source_languages, evolved_restated.spec.traits.source_language_weights)
    )
    assert restated_weights["Dutch"] == 0.3
    assert restated_weights["German"] == 0.2


def test_evolving_with_no_new_contact_still_uses_the_base_languages_curated_spelling_rules():
    # End-to-end version of the regression above: Dutch's own curated
    # x->ch rule (dutch.yaml) must still be reachable for a reformed "x"
    # even on a run that adds no new source_languages -- at a long
    # enough time depth that orthography reform is all but certain to
    # fire for it (years=3000 -> reform rate ~=1-e^-6, effectively 1.0),
    # so this seed isn't relying on a lucky roll. (Re-found against
    # seed=0 after word-stress assignment started consuming extra rng
    # draws during word building -- see stress_gen.py -- shifting this
    # fixed seed's downstream results; re-found again against that same
    # seed=0 after the ts/dz/alveolo-palatal-affricate/long-vowel pool
    # extension added new rng draws to consonant/vowel selection; re-found
    # again against evolve seed=0 after the Thai/Indonesian/Malay batch's
    # own new phoneme-pool content shifted downstream rng draws once more;
    # re-found again (twice, as the word-class-paradigm batch's own new
    # per-language rng draws shifted this repeatedly while that batch was
    # still in progress) back to evolve seed=0; re-found again (now
    # evolve seed=1) after generator.py started conditionally coining
    # "the"/"be" and rolling case/tense/agreement affixes for every
    # language; re-found again (back to evolve seed=0) after core-vocabulary
    # word selection became a seeded, LLM-free pick by default -- another
    # rng-stream reorder, plus the batched build-then-pick pass; re-found
    # again (now evolve seed=1) after the "Missing symbols still" batch's
    # own new _EXOTIC_POOL/_VOWEL_EXTRAS content shifted downstream rng
    # draws once more.)
    base = generate_language(
        "Dutch",
        GenerationSpec(
            prompt="Dutch",
            seed=3,
            traits=TraitProfile(source_languages=("Dutch",)),
            seed_examples=(SeedExample(gloss="bad", form="slecht", ipa="slɛxt"),),
        ),
        FakeLLMClient(),
    )
    evolved = evolve_language("Evolved", base, 3000, TraitProfile(), seed=1)
    x_rules = [r for r in evolved.romanization.rules if r.ipa == "x"]
    assert x_rules and all(r.latin == "ch" for r in x_rules)


def test_georgian_contact_gives_an_ejective_introduced_mid_evolution_a_real_spelling():
    # ejective_drift only ever introduces pʼ/tʼ/kʼ *during* evolution --
    # they're never present in the base language's own old romanization
    # scheme to inherit, so this exercises the full reference-profile
    # fallback path (romanization_gen's new source-language-anchor tier)
    # for a symbol that's brand new this run, not just reformed. A modest
    # years value with contact_intensity pulled negative (suppresses
    # orthography drift without suppressing ejective_drift itself, which
    # isn't contact-linked at zero-or-negative contact) keeps both "an
    # ejective actually appears" and "its mark survives drift" plausible
    # at the same time -- searched across seeds like this file's other
    # seed-dependent tests, rather than forced with an extreme years value
    # that would make orthography drift (shorter half-life than ejective
    # drift) erase the very mark this test is checking.
    base = generate_language(
        "Dutch",
        GenerationSpec(
            prompt="Dutch",
            seed=3,
            traits=TraitProfile(source_languages=("Dutch",)),
            seed_examples=(SeedExample(gloss="bad", form="slecht", ipa="slɛxt"),),
        ),
        FakeLLMClient(),
    )
    traits = TraitProfile(source_languages=("Georgian",), contact_intensity=-0.9)
    ejective_rules = next(
        rules
        for seed in range(100)
        if (rules := [
            r for r in evolve_language("Evolved", base, 300, traits, seed).romanization.rules
            if r.ipa in ("pʼ", "tʼ", "kʼ") and r.latin == r.ipa.replace("ʼ", "") + "'"
        ])
    )
    assert ejective_rules


def test_half_life_calibration_reflects_the_intended_relative_speed_ordering():
    # Locks in the calibration decision itself as a checked invariant, not
    # just a comment: final_devoicing/cluster_simplification are the two
    # fastest (most phonetically-natural/mechanical), lenition/vowel_reduction
    # the tied middle (gradient, multi-stage clines), palatalization/
    # ejective_drift the two slowest (gradual-to-phonologize / typologically
    # rare innovation, respectively). Trait-neutral so only the base
    # half-lives are being compared.
    rates = sound_change._compute_rates(250, TraitProfile())
    assert rates.final_devoicing > rates.lenition
    assert rates.cluster_simplification > rates.vowel_reduction
    assert rates.lenition > rates.palatalization
    assert rates.vowel_reduction > rates.palatalization
    assert rates.palatalization > rates.ejective_drift


@pytest.mark.slow
def test_evolved_onset_clusters_stay_a_thinned_subset_of_the_sonority_legal_closure():
    # Post-evolution recomputation must apply the same cluster thinning as
    # initial generation, not silently un-thin back to the full closure --
    # this is the exact consistency risk cluster-thinning could introduce
    # if phonology_gen.py and sound_change.py ever drifted apart. Seed 3
    # is picked because its base language actually rolls max_onset=2 (most
    # seeds don't, and evolution never re-rolls max_onset -- only its
    # cluster pool -- so a seed without it would make this test vacuous).
    # (Re-found against seed=3 after the Swahili/Zulu/Yoruba batch's own
    # new phoneme-pool content shifted downstream rng draws enough that
    # seed=1 stopped rolling max_onset=2 -- same "seed-shift from new
    # content" pattern documented elsewhere in this project's history.)
    base = generate_language("Base", GenerationSpec(prompt="base", seed=3), FakeLLMClient())
    assert base.syllable_structure.max_onset >= 2
    any_max_onset_2 = False
    for seed in range(30):
        evolved = evolve_language("Evolved", base, 300, TraitProfile(), seed)
        structure = evolved.syllable_structure
        if structure.max_onset >= 2:
            any_max_onset_2 = True
            legal = sonority.legal_onset_pairs(evolved.phonology.consonants)
            assert set(structure.allowed_onset_clusters) <= set(legal)
    assert any_max_onset_2


def test_evolved_dutch_lineage_keeps_coda_devoicing_with_no_new_contact():
    # Same consistency risk as cluster thinning, for the newer phonotactic
    # constraint: without threading lineage_profiles through
    # _recompute_syllable_structure, a Dutch-lineage language's
    # excluded_final_coda_consonants would silently reset to empty the moment
    # evolve_language recomputes SyllableStructure -- even on a run that
    # adds no *new* contact language, same failure mode as the romanization
    # lineage bug this mirrors.
    # seed=1 -- empirically-found (see the seed-search convention noted
    # elsewhere in this file); re-found after the ten-language batch's own
    # new phoneme-pool content shifted downstream rng draws enough that
    # seed=0 stopped rolling a non-empty excluded_final_coda_consonants.
    base = generate_language(
        "Dutch", GenerationSpec(prompt="Dutch", seed=1, traits=TraitProfile(source_languages=("Dutch",))), FakeLLMClient()
    )
    assert base.syllable_structure.excluded_final_coda_consonants  # sanity: the base actually has the constraint
    evolved = evolve_language("Evolved", base, 100, TraitProfile(), seed=1)
    assert evolved.syllable_structure.excluded_final_coda_consonants
    by_ipa = {c.ipa: c for c in evolved.phonology.consonants}
    for symbol in evolved.syllable_structure.excluded_final_coda_consonants:
        consonant = by_ipa[symbol]
        assert consonant.voiced
        assert consonant.manner.value in ("stop", "affricate", "fricative", "lateral_fricative")


def test_glosses_and_pos_preserved():
    base = _base_language()
    evolved = evolve_language("Evolved", base, 500, TraitProfile(), seed=3)
    for old, new in zip(base.lexicon.entries, evolved.lexicon.entries):
        assert old.glosses == new.glosses
        assert old.pos == new.pos


def test_evolved_ipa_round_trips_through_the_tokenizer():
    # Every character in the evolved IPA is accounted for as either a known
    # symbol or a combining-mark decoration on one -- nothing silently
    # mangled to unmodeled output.
    base = _base_language()
    evolved = evolve_language("Evolved", base, 800, TraitProfile(altitude=0.8, contact_intensity=0.8), seed=9)
    for entry in evolved.lexicon.entries:
        tokens = ipa_tokenizer.tokenize(entry.ipa, _KNOWN_SYMBOLS)
        assert "".join(symbol + deco for symbol, deco in tokens) == entry.ipa


def _total_token_count(language) -> int:
    # Excludes replaced/borrowed entries: their token count reflects fresh
    # random coinage length, not cluster simplification, and
    # contact_intensity also scales replacement's own rate -- without this
    # exclusion a replaced entry could coincidentally swing the total
    # either way, breaking the guaranteed (not just likely) monotonicity
    # this comparison relies on (see module docstring).
    return sum(
        len(ipa_tokenizer.symbols_only(e.ipa, _KNOWN_SYMBOLS))
        for e in language.lexicon.entries
        if e.notes not in ("orthography: replaced", "orthography: borrowed")
    )


def test_contact_intensity_increases_cluster_simplification():
    # Token count only shrinks via cluster simplification (the other rules are
    # substitutions, not deletions), so this isolates that one rule -- unlike an
    # aggregate "any change" count, which is no longer reliably monotonic in
    # contact_intensity now that it also *suppresses* ejective_drift (see
    # test_contact_intensity_suppresses_ejective_drift below): the two effects
    # can offset each other in an aggregate count.
    base = _base_language()
    high_contact = evolve_language("Evolved", base, 200, TraitProfile(contact_intensity=0.9), seed=5)
    low_contact = evolve_language("Evolved", base, 200, TraitProfile(contact_intensity=-0.9), seed=5)
    assert _total_token_count(high_contact) < _total_token_count(low_contact)


def _ejective_occurrences(base, years, altitude, seed) -> int:
    evolved = evolve_language("Evolved", base, years, TraitProfile(altitude=altitude), seed=seed)
    count = 0
    for entry in evolved.lexicon.entries:
        tokens = ipa_tokenizer.symbols_only(entry.ipa, _KNOWN_SYMBOLS)
        count += sum(1 for t in tokens if t in ("pʼ", "tʼ", "kʼ"))
    return count


def test_altitude_increases_ejective_drift():
    base = _base_language()
    assert _ejective_occurrences(base, 200, -0.9, seed=5) < _ejective_occurrences(base, 200, 0.9, seed=5)


def test_contact_intensity_suppresses_ejective_drift():
    # Same altitude, same years, same seed -- only contact_intensity differs -- so
    # this is a genuine causal comparison, not noise (see module docstring).
    # (Re-found against seed=0 after the Swahili/Zulu/Yoruba batch's own
    # new phoneme-pool content shifted downstream rng draws enough that
    # seed=5 stopped showing the effect -- same "seed-shift from new
    # content" pattern documented elsewhere in this project's history.)
    base = _base_language()
    high_contact = evolve_language(
        "Evolved", base, 1600, TraitProfile(altitude=0.0, contact_intensity=0.9), seed=0
    )
    no_contact = evolve_language(
        "Evolved", base, 1600, TraitProfile(altitude=0.0, contact_intensity=0.0), seed=0
    )

    def _count(language) -> int:
        count = 0
        for entry in language.lexicon.entries:
            tokens = ipa_tokenizer.symbols_only(entry.ipa, _KNOWN_SYMBOLS)
            count += sum(1 for t in tokens if t in ("pʼ", "tʼ", "kʼ"))
        return count

    assert _count(high_contact) < _count(no_contact)


def test_short_time_depth_keeps_orthography_mostly_conventional():
    # At a short `years` with default (0) orality_literacy, reform should
    # still be rare (its half-life is long specifically so freeze
    # dominates by default) -- most entries should be "unchanged" (sound
    # never moved) or "conventional" (sound moved but the unreformed scheme
    # still matches), not "reformed". A reform is a per-*symbol* roll, but
    # its word-level footprint scales with how many core-vocabulary words
    # happen to share that symbol -- a single reformed high-frequency vowel
    # can flip a sizeable minority of words "reformed" even though only one
    # (rare) reform actually fired, so this checks a simple majority rather
    # than a fixed multiplier (which a lucky/unlucky symbol pick could blow
    # past in either direction).
    base = _base_language()
    evolved = evolve_language("Evolved", base, 20, TraitProfile(), seed=0)
    counts = Counter(e.notes for e in evolved.lexicon.entries)
    not_reformed = counts["orthography: unchanged"] + counts["orthography: conventional"]
    reformed = counts["orthography: reformed"]
    assert not_reformed > reformed


def test_high_orality_literacy_lowers_reform_rate():
    # A word's *rendered* spelling only visibly shows a reform when
    # regeneration happens to land on a different grapheme than the
    # inherited one -- without a contact language active that's frequently
    # a no-op (regenerating via the same inferred style reproduces the same
    # value), so this tests the rate computation directly rather than
    # chasing string-level output through the full pipeline.
    low = sound_change._compute_orthography_rates(300, TraitProfile(orality_literacy=-0.9))
    high = sound_change._compute_orthography_rates(300, TraitProfile(orality_literacy=0.9))
    assert high.reform < low.reform


def test_non_replaced_entries_all_use_the_one_evolved_scheme():
    # Every entry not borrowed/replaced this run -- "unchanged" entries
    # included, now that a reform propagates to a word even when its own
    # sound didn't move -- must have its stored romanization equal applying
    # the language's *single* evolved scheme (plus grammatical spelling) to
    # its own evolved IPA -- confirms evolve_language never derives such a
    # word's spelling any other way, so two words sharing a symbol are
    # always consistent by construction. One deliberate exception: a word
    # whose final symbol was devoiced *this run* (Dutch "berg" [bɛrx],
    # still spelled "g") -- its spelling deliberately follows the
    # pre-devoicing voiced form, not the bare surface IPA (see
    # sound_change.py's own docstring), so re-applying the scheme to
    # `entry.ipa` directly won't reproduce it -- excluded here.
    base = _base_language()
    evolved = evolve_language("Evolved", base, 800, TraitProfile(contact_intensity=-0.9), seed=5)
    for old, entry in zip(base.lexicon.entries, evolved.lexicon.entries):
        if entry.notes not in ("orthography: unchanged", "orthography: conventional", "orthography: reformed"):
            continue
        old_tokens = ipa_tokenizer.tokenize(old.ipa, _KNOWN_SYMBOLS)
        new_tokens = ipa_tokenizer.tokenize(entry.ipa, _KNOWN_SYMBOLS)
        if old_tokens and new_tokens:
            old_final, new_final = old_tokens[-1][0], new_tokens[-1][0]
            if old_final in sound_change._VOICED_TO_VOICELESS and new_final == sound_change._VOICED_TO_VOICELESS[old_final]:
                continue  # final devoicing this run -- see the docstring above
        expected = apply_grammatical_spelling(evolved.romanization, evolved.romanization.apply(entry.ipa), entry.pos)
        assert entry.romanization == expected


def test_final_devoicing_preserves_the_pre_devoicing_voiced_spelling():
    # The "berg" case: a word-final /ɣ/ devoices to [x] this run -- the
    # spelling-oriented IPA `_evolve_ipa` returns alongside the real
    # (surface) one should keep the pre-devoicing voiced form (real Dutch
    # spells "berg" with g despite pronouncing it [bɛrx]), not whatever a
    # genuine /x/ would spell as.
    rates = replace(_ZERO_RATES, final_devoicing=1.0)
    evolved, spelling = sound_change._evolve_ipa("bɛrɣ", random.Random(1), rates, _KNOWN_SYMBOLS, _CONSONANT_BY_IPA, _VOWEL_BY_IPA)
    assert evolved == "bɛrx"  # real surface pronunciation: devoiced
    assert spelling == "bɛrɣ"  # spelling-oriented IPA: keeps the voiced form


def test_final_devoicing_hint_is_dropped_when_a_later_rule_touches_the_same_position():
    # A word-final voiced /d/ devoices to /t/, then ejective drift (also
    # rolled at rate 1.0) turns that same /t/ into /tʼ/ -- the "spell as
    # voiced" hint must be dropped, since the actual final sound is now
    # ejective, not a plain devoiced stop, and there's no real convention
    # for spelling that as its original voiced form.
    rates = replace(_ZERO_RATES, final_devoicing=1.0, ejective_drift=1.0)
    evolved, spelling = sound_change._evolve_ipa("bad", random.Random(1), rates, _KNOWN_SYMBOLS, _CONSONANT_BY_IPA, _VOWEL_BY_IPA)
    assert evolved == "batʼ"
    assert spelling == evolved  # hint dropped -- no stale voiced spelling


def test_unchanged_ipa_reuses_old_spelling_verbatim():
    # An entry whose evolved IPA is byte-identical to its original keeps its
    # exact old romanization, even if the scheme's reconstruction would give
    # something else for that symbol -- preserves any spelling exception a
    # word carries instead of silently "correcting" it via the rule table.
    # Only true when no reform touched it though -- see the next test for
    # the complementary case.
    base = _base_language()
    evolved = evolve_language("Evolved", base, 20, TraitProfile(), seed=5)
    for old, new in zip(base.lexicon.entries, evolved.lexicon.entries):
        if new.notes == "orthography: unchanged":
            assert old.ipa == new.ipa
            assert old.romanization == new.romanization


def test_a_reformed_symbol_still_changes_a_word_whose_own_sound_never_moved():
    # A spelling reform is a language-wide convention change, not a
    # per-word one -- it must touch every word using the reformed symbol,
    # even one whose own pronunciation didn't shift this run at all. Fixed
    # seed known to reform at least one word while its IPA stays
    # byte-identical to the base. (Re-found repeatedly as downstream rng
    # draws shift -- most recently against seed=0 after generator.py
    # started conditionally coining "the"/"be" for every language,
    # shifting this once more, and again against seed=2 after
    # sonority.legal_*_pairs began excluding tokenizer-ambiguous clusters
    # -- and again against seed=8 (valid with or without that sonority
    # change) after the default vocabulary grew to 400 words -- same
    # "seed-shift from new content" pattern documented elsewhere in this
    # project's history.)
    base = _base_language()
    evolved = evolve_language("Evolved", base, 20, TraitProfile(), seed=8)
    touched = [
        (old, new)
        for old, new in zip(base.lexicon.entries, evolved.lexicon.entries)
        if old.ipa == new.ipa and new.notes == "orthography: reformed"
    ]
    assert touched  # regression guard: this seed is known to produce at least one
    for old, new in touched:
        assert old.romanization != new.romanization


def test_source_language_replacement_borrows_from_its_own_phoneme_pool():
    base = _base_language()
    dutch = next(p for p in REFERENCE_LANGUAGES if p.name == "Dutch")
    traits = TraitProfile(contact_intensity=0.95, source_languages=("Dutch",))
    evolved = evolve_language("Evolved", base, 3000, traits, seed=5)

    within_dutch_pool = 0
    for entry in evolved.lexicon.entries:
        symbols = set(ipa_tokenizer.symbols_only(entry.ipa, _KNOWN_SYMBOLS))
        within_dutch_pool += bool(symbols) and symbols <= dutch.symbols()
    # Heavy contact + a long time depth pushes replacement near-certain, and
    # every borrowed word is built solely from Dutch's own phoneme pool by
    # construction -- most of the lexicon should land inside it. Not a tight
    # bound: legitimate changes to reference_languages/profiles/dutch.yaml (its
    # rule count) shift this fixed seed's downstream rng draws incidentally.
    assert within_dutch_pool >= 35


def test_source_language_weights_bias_borrowing_toward_the_heavier_language():
    base = _base_language()
    dutch = next(p for p in REFERENCE_LANGUAGES if p.name == "Dutch")
    mandarin = next(p for p in REFERENCE_LANGUAGES if p.name == "Mandarin")
    traits = TraitProfile(
        contact_intensity=0.95, source_languages=("Dutch", "Mandarin"), source_language_weights=(0.95, 0.05)
    )
    evolved = evolve_language("Evolved", base, 3000, traits, seed=5)

    within_dutch_only = 0
    within_mandarin_only = 0
    for entry in evolved.lexicon.entries:
        symbols = set(ipa_tokenizer.symbols_only(entry.ipa, _KNOWN_SYMBOLS))
        if not symbols:
            continue
        within_dutch_only += symbols <= dutch.symbols() and not symbols <= mandarin.symbols()
        within_mandarin_only += symbols <= mandarin.symbols() and not symbols <= dutch.symbols()
    # A heavily Dutch-weighted mix should draw most (unambiguous) borrowed
    # words from Dutch's own pool, not Mandarin's -- mirrors the single-
    # language regression test above, now for a weighted two-language mix.
    assert within_dutch_only > within_mandarin_only


def test_replacement_without_source_language_still_round_trips():
    # Same heavy-replacement pressure, but no source_languages -- native
    # (2b) coinage instead of borrowing (2a). Just needs to not crash and to
    # still produce well-formed, tokenizable IPA.
    base = _base_language()
    traits = TraitProfile(contact_intensity=0.95)
    evolved = evolve_language("Evolved", base, 3000, traits, seed=5)
    for entry in evolved.lexicon.entries:
        tokens = ipa_tokenizer.tokenize(entry.ipa, _KNOWN_SYMBOLS)
        assert "".join(symbol + deco for symbol, deco in tokens) == entry.ipa


def test_stability_tier_scales_replacement_rate():
    assert lexicon_gen.STABILITY_TIER[PartOfSpeech.PRONOUN] > lexicon_gen.STABILITY_TIER[PartOfSpeech.VERB]

    def _rate(pos: PartOfSpeech) -> float:
        return sound_change._replacement_rate(3000, TraitProfile(contact_intensity=0.5), pos)

    assert _rate(PartOfSpeech.PRONOUN) < _rate(PartOfSpeech.VERB)


# --- Stress-aware vowel reduction ---


def test_vowel_reduction_spares_the_stressed_vowel_not_the_first_one():
    # "paˈtaka" -- stress on the *second* syllable -- must spare that
    # vowel specifically, not the word's first vowel the way the old,
    # position-blind heuristic did.
    tokens = [("p", ""), ("a", ""), (STRESS_MARK, ""), ("t", ""), ("a", ""), ("k", ""), ("a", "")]
    result = sound_change._apply_vowel_reduction(tokens, random.Random(0), rate=1.0, vowel_by_ipa=_VOWEL_BY_IPA)
    symbols = [s for s, _ in result]
    assert symbols == ["p", "ə", STRESS_MARK, "t", "a", "k", "ə"]


def test_vowel_reduction_falls_back_to_the_first_vowel_heuristic_with_no_stress_marker():
    tokens = [("p", ""), ("a", ""), ("t", ""), ("a", ""), ("k", ""), ("a", "")]
    result = sound_change._apply_vowel_reduction(tokens, random.Random(0), rate=1.0, vowel_by_ipa=_VOWEL_BY_IPA)
    symbols = [s for s, _ in result]
    assert symbols == ["p", "a", "t", "ə", "k", "ə"]


def test_stress_mark_survives_diachronic_evolution_at_zero_years():
    base = _base_language()
    evolved = evolve_language("Evolved", base, 0, TraitProfile(), seed=1)
    for old, new in zip(base.lexicon.entries, evolved.lexicon.entries):
        assert (STRESS_MARK in old.ipa) == (STRESS_MARK in new.ipa)
        if STRESS_MARK in old.ipa:
            assert old.ipa.count(STRESS_MARK) == new.ipa.count(STRESS_MARK) == 1


def test_coin_native_word_uses_the_lineage_profiles_own_stress_pattern():
    # Regression guard: root-and-pattern replacement during evolution used
    # to hardcode the generic baseline (pattern="", strictness=0.0) no
    # matter what -- this proves `lineage_profiles`/`strictness` actually
    # reach `stress_gen.mark_stress`, with a synthetic profile combining
    # `root_and_pattern` and a real curated `stress_pattern` (no single
    # real profile in this project currently has both, so this is the
    # only way to prove the wiring itself, independent of what happens to
    # be curated today).
    inventory = PhonemeInventory(
        consonants=(
            Consonant(ipa="k", place=Place.VELAR, manner=Manner.STOP, voiced=False, prevalence=0.9),
            Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, prevalence=0.9),
            Consonant(ipa="b", place=Place.BILABIAL, manner=Manner.STOP, voiced=True, prevalence=0.9),
        ),
        vowels=(Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=1.0),),
    )
    structure = SyllableStructure(max_onset=1, max_coda=0)
    template = WordTemplate(name="verb-basic", pos=PartOfSpeech.VERB, skeleton=("C", "a", "C", "a", "C"))
    grammar = GrammarProfile(
        word_order=WordOrder.SVO, morphological_type=MorphologicalType.FUSIONAL, alignment=Alignment.NOMINATIVE_ACCUSATIVE,
        has_articles=False, adjective_after_noun=False, has_overt_copula=True,
        uses_root_and_pattern=True, templates=(template,),
    )
    entry = LexicalEntry(ipa="kataba", romanization="kataba", glosses=("write",), pos=PartOfSpeech.VERB)
    lineage_profile = ReferenceLanguageProfile(
        name="TestLineage", consonants=("k", "t", "b"), vowels=("a",), coda_profile="none", max_onset=1, tonal=False,
        stress_pattern="final", stress_deviation_rate=0.0,
    )
    ipa, root, _ = sound_change._coin_native_word(
        random.Random(1), entry, inventory, structure, ToneSystem(), WordAccentSystem(), grammar,
        lineage_profiles=(lineage_profile,), strictness=1.0,
    )
    assert root is not None
    assert STRESS_MARK in ipa
    # 3-syllable CaCaC template, "final" pattern with zero deviation at
    # full strictness -> deterministically the third syllable.
    mark_index = ipa.index(STRESS_MARK)
    vowels_after_mark = sum(1 for ch in ipa[mark_index + 1 :] if ch == "a")
    assert vowels_after_mark == 1  # exactly the stressed syllable's own vowel, nothing beyond it


def test_apply_lenition_still_lenites_across_a_word_accent_mark():
    # Real, systematic interaction fixed alongside STRESS_MARK's own:
    # WORD_ACCENT_MARK sits exactly at a syllable boundary, which is
    # exactly where an intervocalic lenition check looks -- the real
    # neighboring vowels on either side must still be found through it.
    vowel_by_ipa = {"a": _VOWEL_BY_IPA["a"]}
    tokens = [("t", ""), ("a", ""), (WORD_ACCENT_MARK, ""), ("p", ""), ("a", "")]
    result = sound_change._apply_lenition(tokens, random.Random(0), 1.0, vowel_by_ipa)
    assert result == [("t", ""), ("a", ""), (WORD_ACCENT_MARK, ""), ("b", ""), ("a", "")]


def test_apply_final_devoicing_finds_the_real_final_consonant_past_a_trailing_word_accent_mark():
    # A trailing WORD_ACCENT_MARK (the common case: the accented syllable
    # is word-final) must not hide the true final consonant from a naive
    # `tokens[-1]` lookup.
    consonant_by_ipa = {"d": _CONSONANT_BY_IPA["d"], "t": _CONSONANT_BY_IPA["t"]}
    tokens = [("a", ""), ("d", ""), (WORD_ACCENT_MARK, "")]
    result, original = sound_change._apply_final_devoicing(tokens, random.Random(0), 1.0, consonant_by_ipa)
    assert result == [("a", ""), ("t", ""), (WORD_ACCENT_MARK, "")]
    assert original == "d"


def test_adjacent_real_symbol_skips_both_stress_and_word_accent_marks():
    tokens = [("t", ""), (STRESS_MARK, ""), ("a", ""), (WORD_ACCENT_MARK, ""), ("p", "")]
    # `STRESS_MARK` isn't a real token position in this list shape (it's
    # only ever produced as a genuine list entry by `ipa_tokenizer.py`,
    # which is exactly what this helper is meant to walk) -- constructed
    # directly here to exercise both skip cases in one token stream.
    assert sound_change._adjacent_real_symbol(tokens, 0, 1) == "a"
    assert sound_change._adjacent_real_symbol(tokens, 4, -1) == "a"


# --- Tonogenesis / detonalization ------------------------------------------


def _glottal_inventory() -> tuple[PhonemeInventory, SyllableStructure]:
    consonants = (
        Consonant(ipa="k", place=Place.VELAR, manner=Manner.STOP, voiced=False, prevalence=0.9),
        Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, prevalence=0.9),
        Consonant(ipa="ʔ", place=Place.GLOTTAL, manner=Manner.STOP, voiced=False, prevalence=0.9),
    )
    vowels = (Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=1.0),)
    phonology = PhonemeInventory(consonants=consonants, vowels=vowels)
    structure = SyllableStructure(max_onset=1, max_coda=1, allowed_coda_consonants=("ʔ", "t"))
    return phonology, structure


def _glottal_romanization() -> RomanizationScheme:
    return RomanizationScheme(
        rules=(
            RomanizationRule(ipa="a", latin="a"), RomanizationRule(ipa="k", latin="k"),
            RomanizationRule(ipa="t", latin="t"), RomanizationRule(ipa="ʔ", latin="'"),
        ),
        vowel_symbols=("a",),
    )


def _glottal_grammar() -> GrammarProfile:
    return GrammarProfile(
        word_order=WordOrder.SVO, morphological_type=MorphologicalType.ISOLATING, alignment=Alignment.NOMINATIVE_ACCUSATIVE,
        has_articles=False, adjective_after_noun=False, has_overt_copula=True,
    )


def _tonogenesis_base(with_glottal_coda: bool = True, pos: PartOfSpeech = PartOfSpeech.NOUN) -> Language:
    # "kaʔta" (real qualifying coda ʔ, syllable 1) + "tata" (no ʔ at all)
    # -- a mixed lexicon, so a tonogenesis run's own uniform "every
    # syllable gets some tone" application is directly checkable against
    # both a converted and an unconverted-but-now-toned word.
    entries = (
        LexicalEntry(ipa="kaʔta" if with_glottal_coda else "kata", romanization="ka'ta" if with_glottal_coda else "kata", glosses=("one",), pos=pos),
        LexicalEntry(ipa="tata", romanization="tata", glosses=("two",), pos=pos),
    )
    phonology, structure = _glottal_inventory()
    return Language(
        name="Base", spec=GenerationSpec(prompt="p", seed=0), phonology=phonology, syllable_structure=structure,
        tone_system=ToneSystem(enabled=False), romanization=_glottal_romanization(), grammar=_glottal_grammar(),
        lexicon=Lexicon(entries=entries),
    )


def _detonalization_base() -> Language:
    entries = (
        LexicalEntry(
            ipa="k" + _tone("a", ToneLevel.HIGH) + "t" + _tone("a", ToneLevel.LOW), romanization="kata",
            glosses=("one",), pos=PartOfSpeech.NOUN, tones=(ToneLevel.HIGH, ToneLevel.LOW),
        ),
    )
    phonology, structure = _glottal_inventory()
    return Language(
        name="Base", spec=GenerationSpec(prompt="p", seed=0), phonology=phonology, syllable_structure=structure,
        tone_system=ToneSystem(enabled=True, levels=(ToneLevel.HIGH, ToneLevel.LOW)),
        romanization=_glottal_romanization(), grammar=_glottal_grammar(), lexicon=Lexicon(entries=entries),
    )


def _tone(vowel: str, level: ToneLevel) -> str:
    return vowel + TONE_DIACRITICS[level]


def test_has_qualifying_coda_glottal_stop():
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)

    def has(ipa: str) -> bool:
        return sound_change._has_qualifying_coda_glottal_stop(ipa_tokenizer.tokenize(ipa, known), vowel_symbols)

    assert has("kaʔ")  # word-final
    assert has("kaʔta")  # before a consonant
    assert not has("kaʔa")  # before a vowel -- belongs to the *next* syllable's onset
    assert not has("ka")  # no ʔ at all
    assert not has("ʔaka")  # word-initial ʔ is an onset, not a coda


def test_tonogenesis_ipa_assigns_low_to_glottal_coda_syllables_high_elsewhere():
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    ipa, tones = sound_change._tonogenesis_ipa("kaʔta", known, vowel_symbols)
    assert tones == (ToneLevel.LOW, ToneLevel.HIGH)
    assert ipa == "k" + _tone("a", ToneLevel.LOW) + "t" + _tone("a", ToneLevel.HIGH)
    assert "ʔ" not in ipa  # the coda that conditioned the tone is gone, same real diachronic outcome


def test_tonogenesis_fires_when_a_qualifying_word_exists_at_a_long_enough_time_depth():
    # Direct call to _evolve_tone_system, not the full evolve_language
    # pipeline -- at a time depth long enough to saturate tonogenesis's
    # own rate, lexical *replacement* is also live and could otherwise
    # coincidentally replace the one qualifying word before this check
    # ever runs, an unrelated confound this direct call sidesteps
    # entirely (the end-to-end wiring itself is covered separately below).
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    final_ipas = ["kaʔta", "tata"]
    new_tone_system, transform = sound_change._evolve_tone_system(
        random.Random(1), ToneSystem(enabled=False), 5000, 0.0, final_ipas, known, vowel_symbols, _CONSONANT_BY_IPA,
    )
    assert new_tone_system.enabled
    assert set(new_tone_system.levels) == {ToneLevel.HIGH, ToneLevel.LOW}
    new_ipas, tones = transform(final_ipas)
    assert "ʔ" not in new_ipas[0]
    assert tones[0] == (ToneLevel.LOW, ToneLevel.HIGH)  # its own real qualifying coda -> low, elsewhere -> high
    assert tones[1] == (ToneLevel.HIGH, ToneLevel.HIGH)  # never had a qualifying coda -> high throughout


def test_tonogenesis_never_fires_with_no_qualifying_word_in_the_lexicon():
    # Structural gating: no word anywhere in this language has a real
    # qualifying coda ʔ, so there's no raw material for this specific
    # pathway -- stays non-tonal even at a huge time depth.
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    new_tone_system, transform = sound_change._evolve_tone_system(
        random.Random(1), ToneSystem(enabled=False), 5000, 0.0, ["kata", "tata"], known, vowel_symbols, _CONSONANT_BY_IPA,
    )
    assert not new_tone_system.enabled
    assert transform is None


def test_tonogenesis_wires_correctly_through_the_full_evolve_language_pipeline(monkeypatch):
    # End-to-end confirmation that evolve_language actually calls the
    # mechanism above and applies its result. The 6 *segmental* rules
    # (_compute_rates) share the same years-based saturation curve as
    # tonogenesis's own rate, so a years value long enough to make
    # tonogenesis near-certain also makes lenition/cluster-simplification/
    # etc. near-certain -- which would mangle (or itself delete the
    # qualifying coda ʔ from) this test's own tiny hand-built word well
    # before tonogenesis ever got a chance to look at it, an unrelated
    # confound the direct tests above already avoid by calling
    # _evolve_tone_system in isolation. Silencing the 6 segmental rules
    # here (rather than picking some "safer" years value -- there isn't
    # one, their half-lives all overlap tonogenesis's own) isolates this
    # test to exactly what it's meant to check: the plumbing between
    # _evolve_tone_system and the rest of evolve_language, not whether
    # segmental change and tonogenesis compose (a real, separate question
    # this project doesn't yet have a rule ordering/interaction story for
    # -- see architecture/OVERVIEW.md).
    monkeypatch.setattr(sound_change, "_compute_rates", lambda years, traits: _ZERO_RATES)
    # Lexical *replacement* is tracked independently of _compute_rates
    # above (its own separate half-life table), so it's silenced the same
    # way -- otherwise this test's own single word could still coincide
    # with a replacement roll at this time depth.
    monkeypatch.setattr(sound_change, "_replacement_rate", lambda years, traits, pos: 0.0)
    base = _tonogenesis_base(with_glottal_coda=True, pos=PartOfSpeech.NUMERAL)
    evolved = evolve_language("Evolved", base, 5000, TraitProfile(), seed=1)
    one = next(e for e in evolved.lexicon.entries if "one" in e.glosses)
    assert evolved.tone_system.enabled
    assert "ʔ" not in one.ipa
    assert one.tones == (ToneLevel.LOW, ToneLevel.HIGH)


def test_detonalization_fires_under_long_time_depth_and_strips_every_tone_mark():
    base = _detonalization_base()
    traits = TraitProfile(contact_intensity=1.0)
    evolved = evolve_language("Evolved", base, 5000, traits, seed=1)
    assert not evolved.tone_system.enabled
    assert evolved.tone_system.levels == ()
    entry = evolved.lexicon.entries[0]
    assert entry.tones == ()
    for level, mark in TONE_DIACRITICS.items():
        assert mark not in entry.ipa


def test_zero_years_never_changes_the_tone_system_either_direction():
    for base in (_tonogenesis_base(with_glottal_coda=True), _detonalization_base(), _merger_base(), _split_base()):
        evolved = evolve_language("Evolved", base, 0, TraitProfile(contact_intensity=1.0), seed=1)
        assert evolved.tone_system == base.tone_system
        assert [e.tones for e in evolved.lexicon.entries] == [e.tones for e in base.lexicon.entries]


def test_a_tonogenesis_runs_own_spelling_stays_consistent_with_its_own_new_ipa(monkeypatch):
    # Regression guard: _evolve_tone_system's own transform must be
    # applied to spelling_ipas too, not just final_ipas -- otherwise a
    # word's stored IPA and its derived romanization could disagree about
    # whether this word even has a coda ʔ anymore. Same segmental-rules/
    # replacement silencing as the wiring test above, for the same reason.
    monkeypatch.setattr(sound_change, "_compute_rates", lambda years, traits: _ZERO_RATES)
    monkeypatch.setattr(sound_change, "_replacement_rate", lambda years, traits, pos: 0.0)
    base = _tonogenesis_base(with_glottal_coda=True, pos=PartOfSpeech.NUMERAL)
    evolved = evolve_language("Evolved", base, 5000, TraitProfile(), seed=1)
    one = next(e for e in evolved.lexicon.entries if "one" in e.glosses)
    assert evolved.tone_system.enabled  # confirms tonogenesis, not a no-op, actually happened
    assert "ʔ" not in one.ipa
    assert "'" not in one.romanization  # the apostrophe this profile's own scheme uses to spell ʔ


# --- Tone splits / mergers ---------------------------------------------


def _tonal_inventory_with_voicing() -> tuple[PhonemeInventory, SyllableStructure]:
    consonants = (
        Consonant(ipa="p", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, prevalence=0.9),
        Consonant(ipa="b", place=Place.BILABIAL, manner=Manner.STOP, voiced=True, prevalence=0.9),
        Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, prevalence=0.9),
    )
    vowels = (Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=1.0),)
    phonology = PhonemeInventory(consonants=consonants, vowels=vowels)
    structure = SyllableStructure(max_onset=1, max_coda=0)
    return phonology, structure


def _tonal_romanization() -> RomanizationScheme:
    return RomanizationScheme(
        rules=(
            RomanizationRule(ipa="a", latin="a"), RomanizationRule(ipa="p", latin="p"),
            RomanizationRule(ipa="b", latin="b"), RomanizationRule(ipa="t", latin="t"),
        ),
        vowel_symbols=("a",),
    )


def _merger_base() -> Language:
    # Three real tone categories (HIGH/LOW/RISING) -- a merger needs at
    # least two eligible (non-NEUTRAL) categories to have anything to pick
    # from. One ToneSandhiRule and one LexicalToneSandhiRule each mention
    # RISING, so a merger that happens to absorb it must be seen to remap
    # or drop them, never leave them dangling.
    entries = (
        LexicalEntry(
            ipa="p" + _tone("a", ToneLevel.HIGH), romanization="pa", glosses=("one",),
            pos=PartOfSpeech.NOUN, tones=(ToneLevel.HIGH,),
        ),
        LexicalEntry(
            ipa="t" + _tone("a", ToneLevel.RISING), romanization="ta", glosses=("two",),
            pos=PartOfSpeech.NOUN, tones=(ToneLevel.RISING,),
        ),
    )
    phonology, structure = _tonal_inventory_with_voicing()
    tone_system = ToneSystem(
        enabled=True, levels=(ToneLevel.HIGH, ToneLevel.LOW, ToneLevel.RISING),
        sandhi=(ToneSandhiRule(before=ToneLevel.RISING, after=ToneLevel.LOW, becomes=ToneLevel.RISING),),
        lexical_sandhi=(LexicalToneSandhiRule(gloss="two", before=ToneLevel.RISING, becomes=ToneLevel.HIGH),),
    )
    return Language(
        name="Base", spec=GenerationSpec(prompt="p", seed=0), phonology=phonology, syllable_structure=structure,
        tone_system=tone_system, romanization=_tonal_romanization(), grammar=_glottal_grammar(),
        lexicon=Lexicon(entries=entries),
    )


def _split_base() -> Language:
    # "ba" -- syllable-initial *voiced* onset before a HIGH-toned vowel (a
    # real yin/yang split candidate); "pa" -- voiceless onset, never a
    # split candidate -- keeps both its own onset and its own tone, so a
    # split's real per-word selectivity is directly checkable against it.
    entries = (
        LexicalEntry(
            ipa="b" + _tone("a", ToneLevel.HIGH), romanization="ba", glosses=("one",),
            pos=PartOfSpeech.NOUN, tones=(ToneLevel.HIGH,),
        ),
        LexicalEntry(
            ipa="p" + _tone("a", ToneLevel.HIGH), romanization="pa", glosses=("two",),
            pos=PartOfSpeech.NOUN, tones=(ToneLevel.HIGH,),
        ),
    )
    phonology, structure = _tonal_inventory_with_voicing()
    tone_system = ToneSystem(enabled=True, levels=(ToneLevel.HIGH, ToneLevel.LOW))
    return Language(
        name="Base", spec=GenerationSpec(prompt="p", seed=0), phonology=phonology, syllable_structure=structure,
        tone_system=tone_system, romanization=_tonal_romanization(), grammar=_glottal_grammar(),
        lexicon=Lexicon(entries=entries),
    )


def test_is_syllable_initial_true_for_word_initial_and_after_a_vowel():
    vowel_symbols = frozenset({"a"})
    tokens = [("p", ""), ("a", ""), ("t", ""), ("a", "")]
    assert sound_change._is_syllable_initial(tokens, 0, vowel_symbols)  # word-initial
    assert sound_change._is_syllable_initial(tokens, 2, vowel_symbols)  # follows a vowel


def test_is_syllable_initial_false_for_the_second_member_of_an_onset_cluster():
    vowel_symbols = frozenset({"a"})
    tokens = [("p", ""), ("t", ""), ("a", "")]
    assert sound_change._is_syllable_initial(tokens, 0, vowel_symbols)
    assert not sound_change._is_syllable_initial(tokens, 1, vowel_symbols)


def test_is_syllable_initial_skips_past_stress_and_word_accent_marks():
    vowel_symbols = frozenset({"a"})
    tokens = [("p", ""), ("a", ""), (STRESS_MARK, ""), ("t", ""), ("a", "")]
    assert sound_change._is_syllable_initial(tokens, 3, vowel_symbols)


def test_has_qualifying_voiced_onset_true_for_a_syllable_initial_voiced_obstruent_before_a_yang_eligible_tone():
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    tokens = ipa_tokenizer.tokenize("b" + _tone("a", ToneLevel.HIGH), known)
    assert sound_change._has_qualifying_voiced_onset(tokens, _CONSONANT_BY_IPA, vowel_symbols)


def test_has_qualifying_voiced_onset_false_for_a_voiceless_onset():
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    tokens = ipa_tokenizer.tokenize("p" + _tone("a", ToneLevel.HIGH), known)
    assert not sound_change._has_qualifying_voiced_onset(tokens, _CONSONANT_BY_IPA, vowel_symbols)


def test_has_qualifying_voiced_onset_false_when_the_tone_has_no_yang_partner():
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    tokens = ipa_tokenizer.tokenize("b" + _tone("a", ToneLevel.FALLING), known)
    assert not sound_change._has_qualifying_voiced_onset(tokens, _CONSONANT_BY_IPA, vowel_symbols)


def test_tone_split_ipa_devoices_a_qualifying_onset_and_lowers_its_register():
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    ipa, tones = sound_change._tone_split_ipa("b" + _tone("a", ToneLevel.HIGH), known, _CONSONANT_BY_IPA, vowel_symbols)
    assert ipa == "p" + _tone("a", ToneLevel.LOW)
    assert tones == (ToneLevel.LOW,)


def test_tone_split_ipa_leaves_a_voiceless_onset_and_its_tone_unchanged():
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    ipa, tones = sound_change._tone_split_ipa("p" + _tone("a", ToneLevel.HIGH), known, _CONSONANT_BY_IPA, vowel_symbols)
    assert ipa == "p" + _tone("a", ToneLevel.HIGH)
    assert tones == (ToneLevel.HIGH,)


def test_tone_split_ipa_devoices_a_falling_tone_onset_but_keeps_its_tone():
    # FALLING has no defensible entry in _YANG_TONE -- the onset still
    # devoices (the conditioning contrast is still lost), but the tone
    # itself is left alone rather than forced into a fabricated pairing.
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    ipa, tones = sound_change._tone_split_ipa("b" + _tone("a", ToneLevel.FALLING), known, _CONSONANT_BY_IPA, vowel_symbols)
    assert ipa == "p" + _tone("a", ToneLevel.FALLING)
    assert tones == (ToneLevel.FALLING,)


def test_tone_merger_pair_picks_two_distinct_eligible_levels():
    pair = sound_change._tone_merger_pair(random.Random(1), (ToneLevel.HIGH, ToneLevel.LOW, ToneLevel.RISING))
    assert pair is not None
    survivor, absorbed = pair
    assert survivor != absorbed
    assert {survivor, absorbed} <= {ToneLevel.HIGH, ToneLevel.LOW, ToneLevel.RISING}


def test_tone_merger_pair_never_picks_neutral():
    for seed in range(20):
        pair = sound_change._tone_merger_pair(random.Random(seed), (ToneLevel.HIGH, ToneLevel.NEUTRAL, ToneLevel.LOW))
        assert pair is not None
        assert ToneLevel.NEUTRAL not in pair


def test_tone_merger_pair_abstains_with_fewer_than_two_eligible_levels():
    assert sound_change._tone_merger_pair(random.Random(1), (ToneLevel.HIGH,)) is None
    assert sound_change._tone_merger_pair(random.Random(1), (ToneLevel.HIGH, ToneLevel.NEUTRAL)) is None


def test_tone_merger_ipa_replaces_every_occurrence_of_the_absorbed_mark():
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    ipa = "p" + _tone("a", ToneLevel.RISING) + "t" + _tone("a", ToneLevel.HIGH)
    new_ipa, tones = sound_change._tone_merger_ipa(ipa, known, vowel_symbols, ToneLevel.LOW, ToneLevel.RISING)
    assert new_ipa == "p" + _tone("a", ToneLevel.LOW) + "t" + _tone("a", ToneLevel.HIGH)
    assert tones == (ToneLevel.LOW, ToneLevel.HIGH)


def test_remap_tone_sandhi_substitutes_and_drops_degenerate_rules():
    rules = (
        ToneSandhiRule(before=ToneLevel.RISING, after=ToneLevel.HIGH, becomes=ToneLevel.MID),
        # before == becomes == RISING -- after remapping both become LOW,
        # a rule that would map a tone to itself, so it must be dropped.
        ToneSandhiRule(before=ToneLevel.RISING, after=ToneLevel.LOW, becomes=ToneLevel.RISING),
    )
    remapped = sound_change._remap_tone_sandhi(rules, survivor=ToneLevel.LOW, absorbed=ToneLevel.RISING)
    assert remapped == (ToneSandhiRule(before=ToneLevel.LOW, after=ToneLevel.HIGH, becomes=ToneLevel.MID),)


def test_remap_tone_sandhi_checks_the_after_field_for_a_target_after_rule():
    # A target="after" rule (real Meeussen's Rule) rewrites its own
    # `after` field at runtime, not `before` -- the degenerate check must
    # follow that, not the target="before" default's own convention.
    rules = (
        # after == becomes == RISING -- for a target="after" rule this is
        # the one that's actually degenerate once RISING is absorbed,
        # even though before(HIGH) stays untouched and != becomes.
        ToneSandhiRule(before=ToneLevel.HIGH, after=ToneLevel.RISING, becomes=ToneLevel.RISING, target="after"),
        ToneSandhiRule(before=ToneLevel.RISING, after=ToneLevel.HIGH, becomes=ToneLevel.MID, target="after"),
    )
    remapped = sound_change._remap_tone_sandhi(rules, survivor=ToneLevel.LOW, absorbed=ToneLevel.RISING)
    assert remapped == (
        ToneSandhiRule(before=ToneLevel.LOW, after=ToneLevel.HIGH, becomes=ToneLevel.MID, target="after"),
    )
    assert remapped[0].target == "after"


def test_remap_lexical_tone_sandhi_substitutes_and_drops_degenerate_rules():
    rules = (
        LexicalToneSandhiRule(gloss="one", before=ToneLevel.RISING, becomes=ToneLevel.HIGH),
        LexicalToneSandhiRule(gloss="two", before=ToneLevel.RISING, becomes=ToneLevel.RISING),
    )
    remapped = sound_change._remap_lexical_tone_sandhi(rules, survivor=ToneLevel.LOW, absorbed=ToneLevel.RISING)
    assert remapped == (LexicalToneSandhiRule(gloss="one", before=ToneLevel.LOW, becomes=ToneLevel.HIGH),)


def test_tone_merger_fires_at_a_long_enough_time_depth_and_shrinks_the_level_set():
    # Direct _evolve_tone_system call, same rationale as the tonogenesis
    # tests above -- isolates this to the mechanism itself, not lexical
    # replacement/segmental change at the same saturated time depth.
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    base = _merger_base()
    final_ipas = [e.ipa for e in base.lexicon.entries]
    new_tone_system = None
    transform = None
    # Detonalization and split are also live at this same time depth (all
    # three of a tonal language's own directions share the same
    # `if base_tone_system.enabled` branch, checked in that fixed order)
    # -- deliberately a *moderate* years value, not an extreme one: at a
    # huge years value detonalization's own rate saturates near 1.0 and,
    # being checked first, would dominate every seed, leaving no room for
    # merger to ever be reached at all. Seed-search for one that
    # specifically lands on merger, the same convention this file's other
    # seed-dependent tests already use for a specific-branch outcome.
    for seed in range(300):
        candidate_system, candidate_transform = sound_change._evolve_tone_system(
            random.Random(seed), base.tone_system, 200, 0.0, final_ipas, known, vowel_symbols, _CONSONANT_BY_IPA,
        )
        if candidate_system.enabled and len(candidate_system.levels) < len(base.tone_system.levels):
            new_tone_system, transform = candidate_system, candidate_transform
            break
    assert new_tone_system is not None, "no seed in range produced a tone merger"
    assert len(new_tone_system.levels) == len(base.tone_system.levels) - 1
    absorbed = next(iter(set(base.tone_system.levels) - set(new_tone_system.levels)))
    assert all(absorbed not in (r.before, r.after, r.becomes) for r in new_tone_system.sandhi)
    assert all(absorbed not in (r.before, r.becomes) for r in new_tone_system.lexical_sandhi)
    new_ipas, tones = transform(final_ipas)
    for ipa in new_ipas:
        assert TONE_DIACRITICS[absorbed] not in ipa


def test_tone_split_fires_at_a_long_enough_time_depth_when_raw_material_exists():
    # A split (unlike a merger, which only ever shrinks the level set, or
    # detonalization, which disables tone outright) is the only one of the
    # three tonal-branch outcomes that ever *grows* `levels` -- see
    # `_evolve_tone_system`'s own docstring -- so that's enough to identify
    # it uniquely among this fixture's own three possible outcomes.
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    base = _split_base()
    final_ipas = [e.ipa for e in base.lexicon.entries]
    new_tone_system = None
    transform = None
    # Same moderate-years reasoning as the merger test above -- and this
    # fixture's own tone system also has 2 eligible (non-NEUTRAL) levels,
    # so merger competes for the very same seeds here too (checked first);
    # the search just needs enough seeds where merger's own roll fails but
    # split's own succeeds.
    for seed in range(300):
        candidate_system, candidate_transform = sound_change._evolve_tone_system(
            random.Random(seed), base.tone_system, 200, 0.0, final_ipas, known, vowel_symbols, _CONSONANT_BY_IPA,
        )
        if candidate_system.enabled and len(candidate_system.levels) > len(base.tone_system.levels):
            new_tone_system, transform = candidate_system, candidate_transform
            break
    assert new_tone_system is not None, "no seed in range produced a tone split"
    assert ToneLevel.DIPPING in new_tone_system.levels
    new_ipas, tones = transform(final_ipas)
    assert new_ipas[0] == "p" + _tone("a", ToneLevel.LOW)  # devoiced onset, register-lowered tone
    assert new_ipas[1] == final_ipas[1]  # already-voiceless onset -- untouched
    assert tones[0] == (ToneLevel.LOW,)
    assert tones[1] == (ToneLevel.HIGH,)


def test_tone_split_never_fires_with_no_qualifying_voiced_onset_in_the_lexicon():
    # Structural gating, the same discipline tonogenesis's own gating
    # test above already checks: no word anywhere in this language has a
    # real qualifying voiced onset before a YANG-eligible tone, so there's
    # no raw material for a split at all this run, regardless of years.
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    tone_system = ToneSystem(enabled=True, levels=(ToneLevel.HIGH, ToneLevel.LOW))
    final_ipas = ["p" + _tone("a", ToneLevel.HIGH), "t" + _tone("a", ToneLevel.LOW)]
    for seed in range(50):
        candidate_system, _ = sound_change._evolve_tone_system(
            random.Random(seed), tone_system, 5000, 0.0, final_ipas, known, vowel_symbols, _CONSONANT_BY_IPA,
        )
        assert ToneLevel.DIPPING not in candidate_system.levels


def test_tone_merger_wires_correctly_through_the_full_evolve_language_pipeline(monkeypatch):
    # Same segmental-rules/replacement silencing as the tonogenesis wiring
    # test above, for the same reason: isolates this to the plumbing
    # between _evolve_tone_system and the rest of evolve_language.
    monkeypatch.setattr(sound_change, "_compute_rates", lambda years, traits: _ZERO_RATES)
    monkeypatch.setattr(sound_change, "_replacement_rate", lambda years, traits, pos: 0.0)
    base = _merger_base()
    evolved = None
    for seed in range(300):
        candidate = evolve_language("Evolved", base, 200, TraitProfile(), seed)
        if candidate.tone_system.enabled and len(candidate.tone_system.levels) < len(base.tone_system.levels):
            evolved = candidate
            break
    assert evolved is not None, "no seed in range produced a tone merger through the full pipeline"
    absorbed = next(iter(set(base.tone_system.levels) - set(evolved.tone_system.levels)))
    for entry in evolved.lexicon.entries:
        assert TONE_DIACRITICS[absorbed] not in entry.ipa
        assert absorbed not in entry.tones


def test_tone_split_wires_correctly_through_the_full_evolve_language_pipeline(monkeypatch):
    monkeypatch.setattr(sound_change, "_compute_rates", lambda years, traits: _ZERO_RATES)
    monkeypatch.setattr(sound_change, "_replacement_rate", lambda years, traits, pos: 0.0)
    base = _split_base()
    evolved = None
    for seed in range(300):
        candidate = evolve_language("Evolved", base, 200, TraitProfile(), seed)
        if candidate.tone_system.enabled and len(candidate.tone_system.levels) > len(base.tone_system.levels):
            evolved = candidate
            break
    assert evolved is not None, "no seed in range produced a tone split through the full pipeline"
    one = next(e for e in evolved.lexicon.entries if "one" in e.glosses)
    two = next(e for e in evolved.lexicon.entries if "two" in e.glosses)
    assert "b" not in ipa_tokenizer.symbols_only(one.ipa, _KNOWN_SYMBOLS)  # its own voiced onset devoiced
    assert one.tones == (ToneLevel.LOW,)
    assert two.ipa == "p" + _tone("a", ToneLevel.HIGH)  # never had a voiced onset -- untouched


# --- Sandhi lexicalization -----------------------------------------------


def _lexicalization_base() -> Language:
    # "ta"+RISING -- its own last (and only) tone-bearing syllable carries
    # RISING, the sandhi rule's own `before` -- real raw material for the
    # mechanism to freeze onto. "ka"+HIGH -- carries a different tone,
    # never a candidate, directly checkable as staying untouched. Only
    # voiceless onsets (k/t) in this fixture's own inventory -- no real
    # voiced obstruent anywhere in either word -- so tone *split* has no
    # raw material here and can never compete with lexicalization for the
    # same seed.
    entries = (
        LexicalEntry(
            ipa="t" + _tone("a", ToneLevel.RISING), romanization="ta", glosses=("one",),
            pos=PartOfSpeech.NOUN, tones=(ToneLevel.RISING,),
        ),
        LexicalEntry(
            ipa="k" + _tone("a", ToneLevel.HIGH), romanization="ka", glosses=("two",),
            pos=PartOfSpeech.NOUN, tones=(ToneLevel.HIGH,),
        ),
    )
    consonants = (
        Consonant(ipa="k", place=Place.VELAR, manner=Manner.STOP, voiced=False, prevalence=0.9),
        Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, prevalence=0.9),
    )
    vowels = (Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=1.0),)
    phonology = PhonemeInventory(consonants=consonants, vowels=vowels)
    structure = SyllableStructure(max_onset=1, max_coda=0)
    romanization = RomanizationScheme(
        rules=(
            RomanizationRule(ipa="a", latin="a"), RomanizationRule(ipa="k", latin="k"), RomanizationRule(ipa="t", latin="t"),
        ),
        vowel_symbols=("a",),
    )
    tone_system = ToneSystem(
        enabled=True, levels=(ToneLevel.HIGH, ToneLevel.LOW, ToneLevel.RISING),
        sandhi=(ToneSandhiRule(before=ToneLevel.RISING, after=ToneLevel.HIGH, becomes=ToneLevel.LOW),),
    )
    return Language(
        name="Base", spec=GenerationSpec(prompt="p", seed=0), phonology=phonology, syllable_structure=structure,
        tone_system=tone_system, romanization=romanization, grammar=_glottal_grammar(),
        lexicon=Lexicon(entries=entries),
    )


def test_pick_lexicalizing_sandhi_rule_picks_from_the_available_rules():
    rules = (
        ToneSandhiRule(before=ToneLevel.RISING, after=ToneLevel.HIGH, becomes=ToneLevel.LOW),
        ToneSandhiRule(before=ToneLevel.HIGH, after=ToneLevel.LOW, becomes=ToneLevel.RISING),
    )
    picked = sound_change._pick_lexicalizing_sandhi_rule(random.Random(1), rules)
    assert picked in rules


def test_pick_lexicalizing_sandhi_rule_abstains_with_no_sandhi_rules():
    assert sound_change._pick_lexicalizing_sandhi_rule(random.Random(1), ()) is None


def test_pick_lexicalizing_sandhi_rule_excludes_a_degenerate_rule():
    # before == becomes -- never produced by resolve_tone_sandhi's own
    # invention logic, but not excluded by the model itself -- would
    # freeze into a genuine no-op, so it's never eligible here.
    degenerate = (ToneSandhiRule(before=ToneLevel.RISING, after=ToneLevel.HIGH, becomes=ToneLevel.RISING),)
    for seed in range(20):
        assert sound_change._pick_lexicalizing_sandhi_rule(random.Random(seed), degenerate) is None


def test_pick_lexicalizing_sandhi_rule_excludes_a_target_after_rule():
    # Real Meeussen's Rule (Zulu/Xhosa's own curated target="after" shape)
    # is never eligible here -- _has_qualifying_lexicalization_target/
    # _lexicalize_sandhi_ipa both freeze a word's own *last* tone-bearing
    # syllable, which is only the position a target="before" rule
    # actually conditions and rewrites.
    progressive = (ToneSandhiRule(before=ToneLevel.HIGH, after=ToneLevel.HIGH, becomes=ToneLevel.LOW, target="after"),)
    for seed in range(20):
        assert sound_change._pick_lexicalizing_sandhi_rule(random.Random(seed), progressive) is None


def test_pick_lexicalizing_sandhi_rule_still_picks_a_target_before_rule_from_a_mixed_set():
    rules = (
        ToneSandhiRule(before=ToneLevel.HIGH, after=ToneLevel.HIGH, becomes=ToneLevel.LOW, target="after"),
        ToneSandhiRule(before=ToneLevel.RISING, after=ToneLevel.HIGH, becomes=ToneLevel.LOW),
    )
    for seed in range(20):
        picked = sound_change._pick_lexicalizing_sandhi_rule(random.Random(seed), rules)
        assert picked == rules[1]


def test_has_qualifying_lexicalization_target_true_for_a_matching_final_tone():
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    tokens = ipa_tokenizer.tokenize("t" + _tone("a", ToneLevel.RISING), known)
    assert sound_change._has_qualifying_lexicalization_target(tokens, vowel_symbols, ToneLevel.RISING)


def test_has_qualifying_lexicalization_target_false_for_a_different_final_tone():
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    tokens = ipa_tokenizer.tokenize("k" + _tone("a", ToneLevel.HIGH), known)
    assert not sound_change._has_qualifying_lexicalization_target(tokens, vowel_symbols, ToneLevel.RISING)


def test_has_qualifying_lexicalization_target_checks_the_words_own_last_tone_only():
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    # RISING appears earlier in the word, but the word's own *last*
    # tone-bearing syllable is HIGH -- only that position counts, the
    # same "last tone-bearing syllable" convention apply_sandhi itself
    # already uses (generation.tone_sandhi).
    ipa = "t" + _tone("a", ToneLevel.RISING) + "k" + _tone("a", ToneLevel.HIGH)
    tokens = ipa_tokenizer.tokenize(ipa, known)
    assert not sound_change._has_qualifying_lexicalization_target(tokens, vowel_symbols, ToneLevel.RISING)
    assert sound_change._has_qualifying_lexicalization_target(tokens, vowel_symbols, ToneLevel.HIGH)


def test_lexicalize_sandhi_ipa_freezes_a_matching_final_tone():
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    rule = ToneSandhiRule(before=ToneLevel.RISING, after=ToneLevel.HIGH, becomes=ToneLevel.LOW)
    ipa, tones = sound_change._lexicalize_sandhi_ipa("t" + _tone("a", ToneLevel.RISING), known, vowel_symbols, rule)
    assert ipa == "t" + _tone("a", ToneLevel.LOW)
    assert tones == (ToneLevel.LOW,)


def test_lexicalize_sandhi_ipa_leaves_a_non_matching_word_unchanged():
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    rule = ToneSandhiRule(before=ToneLevel.RISING, after=ToneLevel.HIGH, becomes=ToneLevel.LOW)
    ipa, tones = sound_change._lexicalize_sandhi_ipa("k" + _tone("a", ToneLevel.HIGH), known, vowel_symbols, rule)
    assert ipa == "k" + _tone("a", ToneLevel.HIGH)
    assert tones == (ToneLevel.HIGH,)


def test_lexicalize_sandhi_ipa_only_touches_the_words_own_last_tone_bearing_syllable():
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    rule = ToneSandhiRule(before=ToneLevel.RISING, after=ToneLevel.HIGH, becomes=ToneLevel.LOW)
    ipa_in = "t" + _tone("a", ToneLevel.RISING) + "t" + _tone("a", ToneLevel.RISING)
    ipa, tones = sound_change._lexicalize_sandhi_ipa(ipa_in, known, vowel_symbols, rule)
    assert ipa == "t" + _tone("a", ToneLevel.RISING) + "t" + _tone("a", ToneLevel.LOW)
    assert tones == (ToneLevel.RISING, ToneLevel.LOW)


def test_sandhi_lexicalization_fires_at_a_long_enough_time_depth_and_drops_the_frozen_rule():
    # Same moderate-years/seed-search rationale as the merger and split
    # tests above -- detonalization/merger are also live for this
    # fixture's own 3-level tonal system at the same time depth (split
    # never is -- see _lexicalization_base's own docstring), so this
    # searches for a seed landing specifically on lexicalization:
    # `levels` unchanged (unlike merger/split, neither of which leaves it
    # alone) but `sandhi` shorter than the base's own.
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    base = _lexicalization_base()
    final_ipas = [e.ipa for e in base.lexicon.entries]
    new_tone_system = None
    transform = None
    for seed in range(300):
        candidate_system, candidate_transform = sound_change._evolve_tone_system(
            random.Random(seed), base.tone_system, 200, 0.0, final_ipas, known, vowel_symbols, _CONSONANT_BY_IPA,
        )
        if (
            candidate_system.enabled and candidate_system.levels == base.tone_system.levels
            and len(candidate_system.sandhi) < len(base.tone_system.sandhi)
        ):
            new_tone_system, transform = candidate_system, candidate_transform
            break
    assert new_tone_system is not None, "no seed in range produced a sandhi lexicalization"
    assert new_tone_system.sandhi == ()  # the fixture's own single rule, now frozen and dropped
    assert new_tone_system.lexical_sandhi == base.tone_system.lexical_sandhi  # untouched by this mechanism
    new_ipas, tones = transform(final_ipas)
    assert new_ipas[0] == "t" + _tone("a", ToneLevel.LOW)  # its own qualifying last tone, frozen
    assert new_ipas[1] == final_ipas[1]  # never qualified -- untouched
    assert tones[0] == (ToneLevel.LOW,)
    assert tones[1] == (ToneLevel.HIGH,)


def test_sandhi_lexicalization_never_fires_with_no_qualifying_word_in_the_lexicon():
    # Structural gating, the same discipline tonogenesis/split's own
    # gating tests above already check: no word anywhere in this language
    # has its own last tone-bearing syllable carrying the rule's `before`,
    # so there's no raw material to freeze at all this run, regardless of
    # `years`.
    known = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
    vowel_symbols = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
    sandhi = (ToneSandhiRule(before=ToneLevel.RISING, after=ToneLevel.HIGH, becomes=ToneLevel.LOW),)
    tone_system = ToneSystem(enabled=True, levels=(ToneLevel.HIGH, ToneLevel.LOW, ToneLevel.RISING), sandhi=sandhi)
    final_ipas = ["k" + _tone("a", ToneLevel.HIGH), "k" + _tone("a", ToneLevel.LOW)]  # neither ends in RISING
    for seed in range(300):
        candidate_system, _ = sound_change._evolve_tone_system(
            random.Random(seed), tone_system, 5000, 0.0, final_ipas, known, vowel_symbols, _CONSONANT_BY_IPA,
        )
        if candidate_system.enabled and candidate_system.levels == tone_system.levels:
            # `sandhi` only ever changes alongside `levels` too (a merger
            # remapping it) -- with `levels` unchanged here, the only other
            # way `sandhi` could differ is lexicalization, which this
            # fixture has no raw material for at all.
            assert candidate_system.sandhi == sandhi


def test_sandhi_lexicalization_wires_correctly_through_the_full_evolve_language_pipeline(monkeypatch):
    monkeypatch.setattr(sound_change, "_compute_rates", lambda years, traits: _ZERO_RATES)
    monkeypatch.setattr(sound_change, "_replacement_rate", lambda years, traits, pos: 0.0)
    base = _lexicalization_base()
    evolved = None
    for seed in range(300):
        candidate = evolve_language("Evolved", base, 200, TraitProfile(), seed)
        if (
            candidate.tone_system.enabled and candidate.tone_system.levels == base.tone_system.levels
            and len(candidate.tone_system.sandhi) < len(base.tone_system.sandhi)
        ):
            evolved = candidate
            break
    assert evolved is not None, "no seed in range produced a sandhi lexicalization through the full pipeline"
    assert evolved.tone_system.sandhi == ()
    one = next(e for e in evolved.lexicon.entries if "one" in e.glosses)
    two = next(e for e in evolved.lexicon.entries if "two" in e.glosses)
    assert one.ipa == "t" + _tone("a", ToneLevel.LOW)
    assert one.tones == (ToneLevel.LOW,)
    assert two.ipa == base.lexicon.entries[1].ipa  # never qualified -- untouched


def test_zero_years_never_changes_a_sandhi_bearing_tone_system_either():
    base = _lexicalization_base()
    evolved = evolve_language("Evolved", base, 0, TraitProfile(contact_intensity=1.0), seed=1)
    assert evolved.tone_system == base.tone_system
    assert [e.tones for e in evolved.lexicon.entries] == [e.tones for e in base.lexicon.entries]
