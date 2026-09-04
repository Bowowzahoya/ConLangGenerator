"""Tests for the diachronic sound-change engine (generation/sound_change.py).

Several comparisons below deliberately reuse the same ``seed`` across two
trait variants: since every rule always consumes exactly one rng draw per
eligible position regardless of outcome (same pattern used throughout
``phonology_gen.py``), the same seed means the *same underlying random
draws* get compared against a higher vs. lower rate -- so "low rate < high
rate" is guaranteed monotonic, not just statistically likely, and these
tests can't be flaky.
"""

import random
from collections import Counter
from dataclasses import replace

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.romanization import apply_grammatical_spelling
from conlang_generator.core.spec import GenerationSpec, SeedExample
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import ipa_tokenizer, lexicon_gen, phonology_gen, sonority, sound_change
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.reference_languages import REFERENCE_LANGUAGES
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
    return generate_language("Base", GenerationSpec(prompt="base", seed=13), FakeLLMClient())


def _changed_count(base, years, traits, seed) -> int:
    evolved = evolve_language("Evolved", base, years, traits, seed)
    return sum(1 for old, new in zip(base.lexicon.entries, evolved.lexicon.entries) if old.ipa != new.ipa)


def test_zero_years_produces_no_changes():
    base = _base_language()
    evolved = evolve_language("Evolved", base, 0, TraitProfile(), seed=1)
    assert [e.ipa for e in base.lexicon.entries] == [e.ipa for e in evolved.lexicon.entries]


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


def test_evolving_with_no_new_contact_still_uses_the_base_languages_curated_spelling_rules():
    # End-to-end version of the regression above: Dutch's own curated
    # x->ch rule (dutch.yaml) must still be reachable for a reformed "x"
    # even on a run that adds no new source_languages -- at a long
    # enough time depth that orthography reform is all but certain to
    # fire for it (years=3000 -> reform rate ~=1-e^-6, effectively 1.0),
    # so this seed isn't relying on a lucky roll.
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


def test_evolved_onset_clusters_stay_a_thinned_subset_of_the_sonority_legal_closure():
    # Post-evolution recomputation must apply the same cluster thinning as
    # initial generation, not silently un-thin back to the full closure --
    # this is the exact consistency risk cluster-thinning could introduce
    # if phonology_gen.py and sound_change.py ever drifted apart. Seed 2
    # is picked because its base language actually rolls max_onset=2 (most
    # seeds don't, and evolution never re-rolls max_onset -- only its
    # cluster pool -- so a seed without it would make this test vacuous).
    base = generate_language("Base", GenerationSpec(prompt="base", seed=2), FakeLLMClient())
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
    # excluded_coda_consonants would silently reset to empty the moment
    # evolve_language recomputes SyllableStructure -- even on a run that
    # adds no *new* contact language, same failure mode as the romanization
    # lineage bug this mirrors.
    base = generate_language(
        "Dutch", GenerationSpec(prompt="Dutch", seed=0, traits=TraitProfile(source_languages=("Dutch",))), FakeLLMClient()
    )
    assert base.syllable_structure.excluded_coda_consonants  # sanity: the base actually has the constraint
    evolved = evolve_language("Evolved", base, 100, TraitProfile(), seed=1)
    assert evolved.syllable_structure.excluded_coda_consonants
    by_ipa = {c.ipa: c for c in evolved.phonology.consonants}
    for symbol in evolved.syllable_structure.excluded_coda_consonants:
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
    base = _base_language()
    high_contact = evolve_language(
        "Evolved", base, 1600, TraitProfile(altitude=0.0, contact_intensity=0.9), seed=5
    )
    no_contact = evolve_language(
        "Evolved", base, 1600, TraitProfile(altitude=0.0, contact_intensity=0.0), seed=5
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
    # seed known to reform several words (e.g. "mountain", "animal",
    # "fish") -- here via orthography drift dropping the ejective
    # apostrophe mark -- while their IPA stays byte-identical to the base.
    base = _base_language()
    evolved = evolve_language("Evolved", base, 20, TraitProfile(), seed=12)
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
