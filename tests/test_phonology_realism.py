"""Distributional checks for milestones 1-4 (inventory realism, in-word
frequency realism, real phonotactics, word-length realism). These call
``phonology_gen``/``word_builder`` directly (no LLM involved) except the
one word-length test, which needs ``lexicon_gen.propose_word``."""

import random

import pytest

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.phonology import (
    Consonant,
    Manner,
    PhonemeInventory,
    Place,
    SyllableStructure,
    Vowel,
    VowelBackness,
    VowelHeight,
    WordAccentSystem,
)
from conlang_generator.core.romanization import STRESS_MARK
from conlang_generator.core.spec import GenerationSpec, SeedExample
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import ipa_tokenizer, lexicon_gen, phonology_gen, romanization_gen, sonority, word_builder
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.reference_languages import REFERENCE_LANGUAGES, ReferenceLanguageProfile
from conlang_generator.llm.fake_client import FakeLLMClient

_SEEDS = range(200)


def test_high_prevalence_consonants_are_more_common_in_inventories():
    common_hits = sum(
        "p" in phonology_gen.generate_phonology(random.Random(s), GenerationSpec(prompt="p", seed=s))[0].consonant_symbols()
        for s in _SEEDS
    )
    rare_hits = sum(
        "ǀ" in phonology_gen.generate_phonology(random.Random(s), GenerationSpec(prompt="p", seed=s))[0].consonant_symbols()
        for s in _SEEDS
    )
    assert common_hits > rare_hits
    assert common_hits > len(_SEEDS) * 0.5
    assert rare_hits < len(_SEEDS) * 0.1


def test_token_frequency_within_words_follows_prevalence():
    spec = GenerationSpec(prompt="p", seed=7)
    rng = random.Random(spec.seed)
    inventory, structure, _, _ = phonology_gen.generate_phonology(rng, spec)
    by_prevalence = sorted(inventory.consonants, key=lambda c: c.prevalence, reverse=True)
    common, rare = by_prevalence[0], by_prevalence[-1]
    assert common.prevalence > rare.prevalence  # sanity: pool actually varies

    common_count = rare_count = 0
    for _ in range(500):
        word = word_builder.build_word(rng, inventory, structure, num_syllables=2)
        common_count += word.count(common.ipa)
        rare_count += word.count(rare.ipa)
    assert common_count > rare_count


def test_aspirated_consonants_appear_at_a_nonzero_base_rate():
    hits = sum(
        "pʰ" in phonology_gen.generate_phonology(random.Random(s), GenerationSpec(prompt="p", seed=s))[0].consonant_symbols()
        for s in _SEEDS
    )
    assert 0 < hits < len(_SEEDS)  # sometimes present, not forced, not absent


def test_arabic_source_language_increases_pharyngealized_consonant_presence():
    def _hit_fraction(source_languages: tuple[str, ...]) -> float:
        hits = 0
        for seed in _SEEDS:
            spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile(source_languages=source_languages))
            inventory, _, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
            hits += "tˤ" in inventory.consonant_symbols()
        return hits / len(_SEEDS)

    assert _hit_fraction(("Arabic",)) > _hit_fraction(())


def test_geminate_consonants_appear_at_a_nonzero_base_rate():
    hits = sum(
        "kː" in phonology_gen.generate_phonology(random.Random(s), GenerationSpec(prompt="p", seed=s))[0].consonant_symbols()
        for s in _SEEDS
    )
    assert 0 < hits < len(_SEEDS)


def test_palatalized_consonants_appear_at_a_nonzero_base_rate():
    hits = sum(
        "tʲ" in phonology_gen.generate_phonology(random.Random(s), GenerationSpec(prompt="p", seed=s))[0].consonant_symbols()
        for s in _SEEDS
    )
    assert 0 < hits < len(_SEEDS)


def test_diphthongs_appear_at_a_nonzero_base_rate():
    hits = sum(
        "ai" in phonology_gen.generate_phonology(random.Random(s), GenerationSpec(prompt="p", seed=s))[0].vowel_symbols()
        for s in _SEEDS
    )
    assert 0 < hits < len(_SEEDS)


def test_dutch_source_language_increases_ei_diphthong_presence():
    def _hit_fraction(source_languages: tuple[str, ...]) -> float:
        hits = 0
        for seed in _SEEDS:
            spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile(source_languages=source_languages))
            inventory, _, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
            hits += "ɛi" in inventory.vowel_symbols()
        return hits / len(_SEEDS)

    assert _hit_fraction(("Dutch",)) > _hit_fraction(())


def test_finnish_source_language_increases_geminate_consonant_presence():
    def _hit_fraction(source_languages: tuple[str, ...]) -> float:
        hits = 0
        for seed in _SEEDS:
            spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile(source_languages=source_languages))
            inventory, _, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
            hits += "kː" in inventory.consonant_symbols()
        return hits / len(_SEEDS)

    assert _hit_fraction(("Finnish",)) > _hit_fraction(())


def test_breathy_consonants_appear_at_a_nonzero_base_rate():
    hits = sum(
        "bʱ" in phonology_gen.generate_phonology(random.Random(s), GenerationSpec(prompt="p", seed=s))[0].consonant_symbols()
        for s in _SEEDS
    )
    assert 0 < hits < len(_SEEDS)


def test_pre_aspirated_consonants_appear_at_a_nonzero_base_rate():
    hits = sum(
        "ʰp" in phonology_gen.generate_phonology(random.Random(s), GenerationSpec(prompt="p", seed=s))[0].consonant_symbols()
        for s in _SEEDS
    )
    assert 0 < hits < len(_SEEDS)


def test_lateral_affricate_appears_at_a_nonzero_base_rate():
    hits = sum(
        "tɬ" in phonology_gen.generate_phonology(random.Random(s), GenerationSpec(prompt="p", seed=s))[0].consonant_symbols()
        for s in _SEEDS
    )
    assert 0 < hits < len(_SEEDS)


def test_nasalized_vowels_appear_at_a_nonzero_base_rate():
    hits = sum(
        "ã" in phonology_gen.generate_phonology(random.Random(s), GenerationSpec(prompt="p", seed=s))[0].vowel_symbols()
        for s in _SEEDS
    )
    assert 0 < hits < len(_SEEDS)


def test_close_back_unrounded_vowel_appears_at_a_nonzero_base_rate():
    hits = sum(
        "ɯ" in phonology_gen.generate_phonology(random.Random(s), GenerationSpec(prompt="p", seed=s))[0].vowel_symbols()
        for s in _SEEDS
    )
    assert 0 < hits < len(_SEEDS)


def test_new_phonemes_from_the_shared_pool_are_used_in_words():
    # A quick end-to-end smoke test: aspirated/pharyngealized/long-vowel
    # symbols, once included in an inventory, are actually sampled into
    # words (not just present in the inventory but never drawn).
    spec = GenerationSpec(prompt="p", seed=1, traits=TraitProfile(source_languages=("Arabic",)))
    rng = random.Random(spec.seed)
    inventory, structure, _, _ = phonology_gen.generate_phonology(rng, spec)
    marked_symbols = {
        c.ipa for c in inventory.consonants if c.aspirated or c.pharyngealized or c.long or c.palatalized or c.breathy
    }
    marked_symbols |= {v.ipa for v in inventory.vowels if v.long or v.diphthong or v.nasalized}
    if not marked_symbols:
        pytest.skip("this seed's inventory happened to roll no marked phonemes")
    found = False
    for _ in range(200):
        word = word_builder.build_word(rng, inventory, structure, num_syllables=3)
        if any(symbol in word for symbol in marked_symbols):
            found = True
            break
    assert found


def test_onset_clusters_are_sonority_legal_or_the_s_stop_exception():
    checked_any_cluster = False
    for seed in range(50):
        inventory, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), GenerationSpec(prompt="p", seed=seed))
        by_ipa = {c.ipa: c for c in inventory.consonants}
        for c1_ipa, c2_ipa in structure.allowed_onset_clusters:
            checked_any_cluster = True
            assert sonority.is_legal_onset_cluster(by_ipa[c1_ipa], by_ipa[c2_ipa])
    assert checked_any_cluster


def test_allowed_onset_clusters_are_a_thinned_subset_of_the_full_sonority_legal_closure():
    # Real languages use a gappier subset of their sonority-legal cluster
    # space than the full combinatorial closure -- proves the thinning in
    # generate_phonology actually thins, in the real generation path (not
    # just in isolation against sonority.thin_cluster_pairs directly).
    checked_any = False
    total_allowed, total_legal = 0, 0
    for seed in _SEEDS:
        inventory, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), GenerationSpec(prompt="p", seed=seed))
        if structure.max_onset >= 2:
            checked_any = True
            legal = sonority.legal_onset_pairs(inventory.consonants)
            assert set(structure.allowed_onset_clusters) <= set(legal)
            total_allowed += len(structure.allowed_onset_clusters)
            total_legal += len(legal)
    assert checked_any
    assert total_allowed < total_legal


def test_contact_intensity_reduces_onset_cluster_count():
    def _avg_cluster_count(contact_intensity: float) -> float:
        total, hits = 0, 0
        for seed in _SEEDS:
            spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile(contact_intensity=contact_intensity))
            _, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
            if structure.max_onset >= 2:
                hits += 1
                total += len(structure.allowed_onset_clusters)
        return total / hits if hits else 0.0

    unbiased_avg = _avg_cluster_count(0.0)
    contact_avg = _avg_cluster_count(0.8)
    assert contact_avg < unbiased_avg


def test_sonorant_only_coda_profile_only_allows_sonorants_or_glottal_stop():
    checked_any = False
    for seed in range(100):
        rng = random.Random(seed)
        spec = GenerationSpec(prompt="p", seed=seed)
        inventory, structure, _, _ = phonology_gen.generate_phonology(rng, spec)
        if structure.allowed_coda_consonants is not None:
            checked_any = True
            by_ipa = {c.ipa: c for c in inventory.consonants}
            for symbol in structure.allowed_coda_consonants:
                assert symbol == "ʔ" or sonority.sonority(by_ipa[symbol]) >= 3
    assert checked_any


def test_dutch_biased_unrestricted_coda_excludes_voiced_obstruents():
    # Real Dutch/German-style final-obstruent devoicing as a static
    # phonotactic constraint, not just sound_change.py's diachronic rule.
    checked_any = False
    for seed in _SEEDS:
        spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile(source_languages=("Dutch",)))
        inventory, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        if structure.max_coda >= 1 and structure.allowed_coda_consonants is None:  # "unrestricted" coda profile
            checked_any = True
            by_ipa = {c.ipa: c for c in inventory.consonants}
            for symbol in structure.excluded_coda_consonants:
                consonant = by_ipa[symbol]
                assert consonant.voiced
                assert consonant.manner.value in ("stop", "affricate", "fricative", "lateral_fricative")
    assert checked_any


def test_dutch_biased_words_never_end_in_an_excluded_coda_consonant():
    for seed in range(100):
        spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile(source_languages=("Dutch",)))
        inventory, structure, tone_system, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        if not structure.excluded_coda_consonants:
            continue
        rng = random.Random(seed)
        known_symbols = inventory.consonant_symbols() + inventory.vowel_symbols()
        consonants = set(inventory.consonant_symbols())
        for _ in range(50):
            word = word_builder.build_word(rng, inventory, structure, num_syllables=2)
            tokens = ipa_tokenizer.symbols_only(word, known_symbols)
            if tokens and tokens[-1] in consonants:  # word actually ends in a coda consonant
                assert tokens[-1] not in structure.excluded_coda_consonants


def test_no_source_language_never_sets_excluded_coda_consonants():
    # coda_devoicing is opt-in per matched reference profile -- an
    # unbiased generation should never populate it.
    for seed in range(100):
        spec = GenerationSpec(prompt="p", seed=seed)
        _, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        assert structure.excluded_coda_consonants == ()


def test_vowel_harmony_words_mostly_share_backness():
    for seed in range(300):
        rng = random.Random(seed)
        spec = GenerationSpec(prompt="p", seed=seed)
        inventory, structure, _, _ = phonology_gen.generate_phonology(rng, spec)
        if not structure.vowel_harmony:
            continue

        backness_by_ipa = {v.ipa: v.backness for v in inventory.vowels}
        matches = total = 0
        for _ in range(40):
            word = word_builder.build_word(rng, inventory, structure, num_syllables=3)
            classes = [backness_by_ipa[ch] for ch in word if ch in backness_by_ipa]
            non_central = [c for c in classes if c != VowelBackness.CENTRAL]
            if len(non_central) >= 2:
                total += 1
                if len(set(non_central)) == 1:
                    matches += 1
        if total >= 5:
            assert matches / total > 0.6
            return
    pytest.fail("no seed produced a vowel-harmony language with enough multi-vowel words to test")


def test_favor_short_false_produces_longer_words_on_average():
    client = FakeLLMClient()
    spec = GenerationSpec(prompt="p", seed=3)
    rng = random.Random(spec.seed)
    inventory, structure, tone_system, _ = phonology_gen.generate_phonology(rng, spec)
    romanization = romanization_gen.generate_romanization(rng, inventory)
    vowel_symbols = set(inventory.vowel_symbols())

    def avg_syllable_count(favor_short: bool, seed: int) -> float:
        local_rng = random.Random(seed)
        total = 0
        n = 150
        for _ in range(n):
            entry = lexicon_gen.propose_word(
                local_rng, inventory, structure, tone_system, WordAccentSystem(), romanization,
                "thing", PartOfSpeech.NOUN, client, "Test", favor_short=favor_short,
            )
            total += sum(1 for ch in entry.ipa if ch in vowel_symbols)
        return total / n

    short_avg = avg_syllable_count(True, 100)
    long_avg = avg_syllable_count(False, 200)
    assert long_avg > short_avg


def test_function_words_skew_shorter_than_content_words():
    client = FakeLLMClient()
    spec = GenerationSpec(prompt="p", seed=9)
    rng = random.Random(spec.seed)
    inventory, structure, tone_system, _ = phonology_gen.generate_phonology(rng, spec)
    romanization = romanization_gen.generate_romanization(rng, inventory)
    vowel_symbols = set(inventory.vowel_symbols())

    def avg_syllable_count(pos: PartOfSpeech, seed: int) -> float:
        local_rng = random.Random(seed)
        total = 0
        n = 150
        for _ in range(n):
            entry = lexicon_gen.propose_word(
                local_rng, inventory, structure, tone_system, WordAccentSystem(), romanization,
                "x", pos, client, "Test",
            )
            total += sum(1 for ch in entry.ipa if ch in vowel_symbols)
        return total / n

    function_avg = avg_syllable_count(PartOfSpeech.PARTICLE, 300)
    content_avg = avg_syllable_count(PartOfSpeech.NOUN, 400)
    assert function_avg < content_avg


# --- source_language_strictness ---

_GERMAN = next(p for p in REFERENCE_LANGUAGES if p.name == "German")
_ENGLISH = next(p for p in REFERENCE_LANGUAGES if p.name == "English")
_HAWAIIAN = next(p for p in REFERENCE_LANGUAGES if p.name == "Hawaiian")


def test_full_strictness_inventory_is_a_subset_of_the_source_languages_own_symbols():
    allowed = _GERMAN.symbols()
    for seed in range(40):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("German",), source_language_strictness=1.0)
        )
        inventory, _, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        got = set(inventory.consonant_symbols()) | set(inventory.vowel_symbols())
        assert got <= allowed, (seed, got - allowed)


def test_full_strictness_onset_never_exceeds_the_source_languages_own_max_onset():
    # German's own max_onset is 2; every generated structure should honor
    # that ceiling (never higher, and the model only supports 1 or 2 to
    # begin with).
    for seed in range(40):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("German",), source_language_strictness=1.0)
        )
        _, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        assert structure.max_onset <= _GERMAN.max_onset


def test_full_strictness_coda_profile_matches_the_source_languages_own_value():
    # Hawaiian's own coda_profile is "none" -- every generated structure
    # should land on the same effective shape (max_coda=0).
    for seed in range(30):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("Hawaiian",), source_language_strictness=1.0)
        )
        _, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        assert structure.max_coda == 0


def test_full_strictness_still_force_includes_a_seed_example_symbol_outside_the_source_language():
    # Hawaiian's own consonants (p, k, ʔ, h, m, n, l, w) have no "d" -- a
    # literal seed_examples word using it must still surface "d" in the
    # inventory even under full strictness, since _force_include is
    # deliberately untouched by source_language_strictness.
    spec = GenerationSpec(
        prompt="p", seed=1,
        traits=TraitProfile(source_languages=("Hawaiian",), source_language_strictness=1.0),
        seed_examples=(SeedExample(gloss="x", form="kadu", ipa="kadu"),),
    )
    inventory, _, _, _ = phonology_gen.generate_phonology(random.Random(1), spec)
    assert "d" in inventory.consonant_symbols()


def test_full_strictness_with_two_source_languages_draws_from_their_combined_palette():
    # English has "r" but no "ʁ"; German has "ʁ" but no "r" -- at full
    # strictness with both named, every generated symbol must trace to
    # *either* profile, and across enough seeds both language-exclusive
    # symbols should surface (proving a true union, not one profile
    # dominating the other).
    allowed = _ENGLISH.symbols() | _GERMAN.symbols()
    saw_german_only = False
    saw_english_only = False
    for seed in range(60):
        spec = GenerationSpec(
            prompt="p", seed=seed,
            traits=TraitProfile(source_languages=("English", "German"), source_language_strictness=1.0),
        )
        inventory, _, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        got = set(inventory.consonant_symbols()) | set(inventory.vowel_symbols())
        assert got <= allowed, (seed, got - allowed)
        saw_german_only = saw_german_only or "ʁ" in got
        saw_english_only = saw_english_only or "r" in got
    assert saw_german_only
    assert saw_english_only


def test_source_language_strictness_gradient_is_monotonic():
    # Fraction of generated symbols falling outside German's own set
    # should strictly decrease as strictness rises from 0.0 (today's soft
    # bias) through 0.5 to 1.0 (hard restriction).
    def _off_reference_fraction(strictness: float) -> float:
        off = total = 0
        for seed in range(60):
            spec = GenerationSpec(
                prompt="p", seed=seed,
                traits=TraitProfile(source_languages=("German",), source_language_strictness=strictness),
            )
            inventory, _, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
            got = set(inventory.consonant_symbols()) | set(inventory.vowel_symbols())
            off += len(got - _GERMAN.symbols())
            total += len(got)
        return off / total

    loose = _off_reference_fraction(0.0)
    mid = _off_reference_fraction(0.5)
    strict = _off_reference_fraction(1.0)
    assert loose > mid > strict
    assert strict == 0.0


def _coda_legal(structure, symbol: str) -> bool:
    """Whether `symbol` could actually be chosen as a single-consonant
    coda by `word_builder._build_coda`, given `structure` -- mirrors that
    function's own candidate-filtering logic directly, rather than
    building many words to observe it indirectly."""
    if structure.max_coda == 0:
        return False
    if structure.allowed_coda_consonants is not None and symbol not in structure.allowed_coda_consonants:
        return False
    return symbol not in structure.excluded_coda_consonants


def test_full_strictness_never_admits_englishs_restricted_onset_consonants():
    for seed in range(40):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("English",), source_language_strictness=1.0)
        )
        _, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        assert "ŋ" in structure.excluded_onset_consonants
        assert "ʒ" in structure.excluded_onset_consonants


def test_full_strictness_never_admits_a_restricted_coda_consonant():
    for seed in range(40):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("English",), source_language_strictness=1.0)
        )
        _, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        assert not _coda_legal(structure, "j")
        assert not _coda_legal(structure, "w")

    for seed in range(40):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("German",), source_language_strictness=1.0)
        )
        _, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        assert not _coda_legal(structure, "j")


def test_full_strictness_french_restricts_w_coda_but_not_j():
    # Real French genuinely has word-final /j/ (soleil, travail) -- the
    # restriction must be per-language, not a blanket glide ban.
    saw_j_allowed = False
    for seed in range(60):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("French",), source_language_strictness=1.0)
        )
        _, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        assert not _coda_legal(structure, "w")
        saw_j_allowed = saw_j_allowed or _coda_legal(structure, "j")
    assert saw_j_allowed


def test_zero_strictness_still_allows_symbols_outside_the_source_language():
    # The no-op guarantee's other half: strictness=0.0 must NOT hard-
    # restrict -- today's existing soft, non-exclusive bias should still
    # let an off-profile symbol through sometimes.
    saw_off_reference = False
    for seed in range(60):
        spec = GenerationSpec(
            prompt="p", seed=seed,
            traits=TraitProfile(source_languages=("German",), source_language_strictness=0.0),
        )
        inventory, _, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        got = set(inventory.consonant_symbols()) | set(inventory.vowel_symbols())
        if got - _GERMAN.symbols():
            saw_off_reference = True
            break
    assert saw_off_reference


# --- restricted_onset_consonants / attested_onset_clusters ---


def test_full_strictness_never_lets_ŋ_open_a_syllable_in_german():
    # /ŋ/ is real in German (Zunge, singen) but coda/medial-only -- never
    # a plain syllable onset -- confirmed via real generated words, not
    # just the structural fields, since word_builder is what actually
    # consumes excluded_onset_consonants.
    for seed in range(30):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("German",), source_language_strictness=1.0)
        )
        rng = random.Random(seed)
        inventory, structure, _, _ = phonology_gen.generate_phonology(rng, spec)
        if "ŋ" not in inventory.consonant_symbols():
            continue
        for _ in range(30):
            word = word_builder.build_word(rng, inventory, structure, num_syllables=2)
            assert not word.startswith("ŋ"), (seed, word)


def test_full_strictness_german_onset_clusters_stay_within_the_curated_list():
    for seed in range(60):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("German",), source_language_strictness=1.0)
        )
        _, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        for pair in structure.allowed_onset_clusters:
            assert pair in _GERMAN.attested_onset_clusters, (seed, pair)


def test_full_strictness_english_onset_clusters_stay_within_the_curated_list():
    for seed in range(60):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("English",), source_language_strictness=1.0)
        )
        _, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        for pair in structure.allowed_onset_clusters:
            assert pair in _ENGLISH.attested_onset_clusters, (seed, pair)


def test_zero_strictness_still_allows_an_unattested_onset_cluster_or_ŋ_onset():
    # The gradient's other end: strictness=0.0 must not hard-restrict
    # onset shape either -- today's generic sonority-only behavior should
    # still sometimes produce a cluster outside German's curated list.
    saw_unattested = False
    for seed in range(60):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("German",), source_language_strictness=0.0)
        )
        _, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        if any(pair not in _GERMAN.attested_onset_clusters for pair in structure.allowed_onset_clusters):
            saw_unattested = True
            break
    assert saw_unattested


# --- Onset+nucleus co-occurrence (blacklist/whitelist per language) ---


def _pair_legal(structure, onset_final: str, nucleus: str) -> bool:
    """Whether `(onset_final, nucleus)` could actually survive
    `word_builder._choose_nucleus`'s own filtering, given `structure` --
    mirrors that function's logic directly rather than building many
    words to observe it indirectly."""
    if structure.allowed_onset_nucleus_pairs is not None:
        return (onset_final, nucleus) in structure.allowed_onset_nucleus_pairs
    return (onset_final, nucleus) not in structure.excluded_onset_nucleus_pairs


def test_full_strictness_never_admits_englishs_w_plus_rounded_vowel():
    for seed in range(40):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("English",), source_language_strictness=1.0)
        )
        _, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        for vowel in ("u", "o", "ʊ"):
            assert not _pair_legal(structure, "w", vowel)


def test_full_strictness_never_admits_frenchs_w_plus_unattested_vowel():
    # Real French /w/ only ever precedes a/i/ɛ (moi, oui, ouest) -- the
    # concrete "oueauy"/"moia" bug came from /w/+/o/ being generated at
    # all with nothing to stop it.
    for seed in range(40):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("French",), source_language_strictness=1.0)
        )
        _, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        for vowel in ("o", "u", "y", "ø", "œ", "ɔ", "e", "ə", "ɑ"):
            assert not _pair_legal(structure, "w", vowel)


def _synthetic_profile(name: str, **kwargs) -> ReferenceLanguageProfile:
    return ReferenceLanguageProfile(
        name=name, consonants=("p", "t", "w"), vowels=("a", "u"), coda_profile="unrestricted", max_onset=2, tonal=False, **kwargs
    )


# --- The 6-level tone system and its reference-biased set selection ---


def test_tone_level_sets_richest_entry_covers_all_six_levels():
    from conlang_generator.core.phonology import ToneLevel

    richest = max(phonology_gen._TONE_LEVEL_SETS, key=len)
    assert set(richest) == set(ToneLevel)
    assert len(richest) == 6


def test_choose_tone_levels_with_no_reference_profiles_can_reach_every_set_length():
    # Unbiased baseline: over enough draws, every one of the existing
    # set lengths (2, 3, 4, 6) should turn up.
    rng = random.Random(0)
    lengths = {len(phonology_gen._choose_tone_levels(rng, (), 0.0)) for _ in range(500)}
    assert lengths == {len(levels) for levels in phonology_gen._TONE_LEVEL_SETS}


def test_choose_tone_levels_biases_toward_the_matched_profiles_own_tone_count():
    # A profile curating tone_level_count=6 (Cantonese/Vietnamese's own
    # real count) should make the 6-level set come up far more than a
    # 1-in-4 uniform pick would, at full strictness -- confirming the
    # reference-bias actually has an effect, not just that the set exists.
    cantonese_like = _synthetic_profile("C", tone_level_count=6)
    rng = random.Random(0)
    hits = sum(
        1
        for _ in range(500)
        if len(phonology_gen._choose_tone_levels(rng, (cantonese_like,), 1.0)) == 6
    )
    assert hits > 450


def test_choose_tone_levels_ignores_a_profile_with_no_tone_level_count_curated():
    # tonal=True alone (no tone_level_count) must not bias the set choice
    # at all -- same "abstain when uncurated" convention as every other
    # optional field.
    uncurated = _synthetic_profile("U")
    rng = random.Random(0)
    lengths = [len(phonology_gen._choose_tone_levels(rng, (uncurated,), 1.0)) for _ in range(500)]
    counts = {n: lengths.count(n) for n in {len(levels) for levels in phonology_gen._TONE_LEVEL_SETS}}
    # Roughly uniform -- no single length should dominate the way the
    # biased test above shows for a curated profile.
    assert max(counts.values()) < 300


def test_resolve_onset_nucleus_restriction_intersects_two_blacklists():
    # A pair only stays forbidden if *every* blacklist-mode source
    # forbids it -- what's legal in either becomes legal in the
    # combination (the user's own "blacklists get shortened" rule).
    a = _synthetic_profile("A", restricted_onset_nucleus_pairs=(("w", "u"), ("p", "a")))
    b = _synthetic_profile("B", restricted_onset_nucleus_pairs=(("w", "u"),))
    allowed, excluded = phonology_gen._resolve_onset_nucleus_restriction(
        random.Random(0), (a, b), 1.0, ("p", "t", "w"), ("a", "u"), 0.0
    )
    assert allowed is None
    assert set(excluded) == {("w", "u")}  # ("p", "a") only forbidden by A, so it's legal in the combination


def test_resolve_onset_nucleus_restriction_unions_two_whitelists():
    # A pair is legal if *either* whitelist-mode source attests it (the
    # user's own "whitelists get extended" rule).
    a = _synthetic_profile("A", attested_onset_nucleus_pairs=(("p", "a"),))
    b = _synthetic_profile("B", attested_onset_nucleus_pairs=(("t", "u"),))
    allowed, excluded = phonology_gen._resolve_onset_nucleus_restriction(
        random.Random(0), (a, b), 1.0, ("p", "t", "w"), ("a", "u"), 0.0
    )
    assert excluded == ()
    assert set(allowed) == {("p", "a"), ("t", "u")}


def test_resolve_onset_nucleus_restriction_mixed_subtracts_whitelist_exemptions():
    # A pair forbidden by a blacklist-mode source but explicitly attested
    # by a whitelist-mode source is exempted -- collapses to blacklist
    # semantics since a whitelist can't be represented once the legal set
    # has already been widened by something else.
    blacklist = _synthetic_profile("BL", restricted_onset_nucleus_pairs=(("w", "u"), ("p", "a")))
    whitelist = _synthetic_profile("WL", attested_onset_nucleus_pairs=(("w", "u"),))
    allowed, excluded = phonology_gen._resolve_onset_nucleus_restriction(
        random.Random(0), (blacklist, whitelist), 1.0, ("p", "t", "w"), ("a", "u"), 0.0
    )
    assert allowed is None
    assert set(excluded) == {("p", "a")}  # ("w", "u") exempted by the whitelist


def test_resolve_onset_nucleus_restriction_ignores_uncurated_profiles():
    # An uncurated profile (empty on both fields) must abstain from the
    # intersection entirely, not be treated as "verified permissive
    # everywhere" (which would zero out every other source's blacklist).
    curated = _synthetic_profile("Curated", restricted_onset_nucleus_pairs=(("w", "u"),))
    uncurated = _synthetic_profile("Uncurated")
    allowed, excluded = phonology_gen._resolve_onset_nucleus_restriction(
        random.Random(0), (curated, uncurated), 1.0, ("p", "t", "w"), ("a", "u"), 0.0
    )
    assert allowed is None
    assert set(excluded) == {("w", "u")}


def test_no_source_language_whitelist_mode_keeps_a_coverage_floor():
    # phonotactic_restrictiveness=1.0 (strong positive) makes whitelist
    # mode near-certain -- every consonant/vowel should keep at least one
    # legal partner, per "a whitelist should generally be large enough to
    # support a language."
    consonants = ("p", "t", "k", "m", "n")
    vowels = ("a", "i", "u")
    for seed in range(20):
        allowed, excluded = phonology_gen._resolve_onset_nucleus_restriction(
            random.Random(seed), (), 0.0, consonants, vowels, 1.0
        )
        if allowed is None:
            continue  # this seed happened to roll blacklist mode anyway
        covered_consonants = {pair[0] for pair in allowed}
        covered_vowels = {pair[1] for pair in allowed}
        assert covered_consonants == set(consonants)
        assert covered_vowels == set(vowels)


def test_no_source_language_blacklist_mode_leaves_most_pairs_legal():
    consonants = ("p", "t", "k", "m", "n")
    vowels = ("a", "i", "u")
    total = len(consonants) * len(vowels)
    for seed in range(20):
        allowed, excluded = phonology_gen._resolve_onset_nucleus_restriction(
            random.Random(seed), (), 0.0, consonants, vowels, -1.0
        )
        if allowed is not None:
            continue  # this seed happened to roll whitelist mode anyway
        assert len(excluded) < total / 2


def test_phonotactic_restrictiveness_pushes_toward_whitelist_mode():
    consonants = ("p", "t", "k", "m", "n")
    vowels = ("a", "i", "u")

    def _whitelist_fraction(restrictiveness: float) -> float:
        hits = 0
        for seed in range(80):
            allowed, _ = phonology_gen._resolve_onset_nucleus_restriction(
                random.Random(seed), (), 0.0, consonants, vowels, restrictiveness
            )
            hits += allowed is not None
        return hits / 80

    assert _whitelist_fraction(1.0) > _whitelist_fraction(0.0) > _whitelist_fraction(-1.0)


# --- Coda-cluster attested-data grading (the coda-side mirror of attested_onset_clusters) ---


def test_full_strictness_coda_clusters_stay_within_englishs_attested_list():
    for seed in range(60):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("English",), source_language_strictness=1.0)
        )
        _, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        assert set(structure.allowed_coda_clusters) <= set(_ENGLISH.attested_coda_clusters)


def test_zero_strictness_still_allows_an_unattested_coda_cluster():
    # Same gradient shape as the onset-cluster version: strictness=0.0
    # must not hard-restrict coda shape either.
    saw_unattested = False
    for seed in range(60):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("English",), source_language_strictness=0.0)
        )
        _, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        if any(pair not in _ENGLISH.attested_coda_clusters for pair in structure.allowed_coda_clusters):
            saw_unattested = True
            break
    assert saw_unattested


# --- Nucleus+coda co-occurrence (the coda-side mirror of onset+nucleus) ---


def _nucleus_coda_pair_legal(structure, nucleus: str, coda: str) -> bool:
    if structure.allowed_nucleus_coda_pairs is not None:
        return (nucleus, coda) in structure.allowed_nucleus_coda_pairs
    return (nucleus, coda) not in structure.excluded_nucleus_coda_pairs


def test_full_strictness_never_admits_englishs_tense_vowel_plus_ŋ():
    for seed in range(40):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("English",), source_language_strictness=1.0)
        )
        _, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        for vowel in ("i", "e", "u", "o", "ə", "ai", "au", "ɔi", "ei"):
            assert not _nucleus_coda_pair_legal(structure, vowel, "ŋ")


def test_full_strictness_english_words_never_have_a_tense_vowel_before_ŋ():
    tense_or_diphthong = {"i", "e", "u", "o", "ə", "ai", "au", "ɔi", "ei"}
    checked_any = False
    for seed in range(60):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("English",), source_language_strictness=1.0)
        )
        inventory, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        if "ŋ" not in inventory.consonant_symbols():
            continue
        rng = random.Random(seed)
        known_symbols = inventory.consonant_symbols() + inventory.vowel_symbols()
        for _ in range(50):
            word = word_builder.build_word(rng, inventory, structure, num_syllables=2)
            tokens = ipa_tokenizer.symbols_only(word, known_symbols)
            for i, token in enumerate(tokens[:-1]):
                if tokens[i + 1] == "ŋ":
                    checked_any = True
                    assert token not in tense_or_diphthong
    assert checked_any


def test_resolve_nucleus_coda_restriction_intersects_two_blacklists():
    a = _synthetic_profile("A", restricted_nucleus_coda_pairs=(("i", "ŋ"), ("u", "n")))
    b = _synthetic_profile("B", restricted_nucleus_coda_pairs=(("i", "ŋ"),))
    allowed, excluded = phonology_gen._resolve_nucleus_coda_restriction(
        random.Random(0), (a, b), 1.0, ("a", "i", "u"), ("ŋ", "n"), 0.0
    )
    assert allowed is None
    assert set(excluded) == {("i", "ŋ")}  # ("u", "n") only forbidden by A


def test_resolve_nucleus_coda_restriction_unions_two_whitelists():
    a = _synthetic_profile("A", attested_nucleus_coda_pairs=(("a", "n"),))
    b = _synthetic_profile("B", attested_nucleus_coda_pairs=(("u", "t"),))
    allowed, excluded = phonology_gen._resolve_nucleus_coda_restriction(
        random.Random(0), (a, b), 1.0, ("a", "u"), ("n", "t"), 0.0
    )
    assert excluded == ()
    assert set(allowed) == {("a", "n"), ("u", "t")}


def test_resolve_nucleus_coda_restriction_ignores_uncurated_profiles():
    curated = _synthetic_profile("Curated", restricted_nucleus_coda_pairs=(("i", "ŋ"),))
    uncurated = _synthetic_profile("Uncurated")
    allowed, excluded = phonology_gen._resolve_nucleus_coda_restriction(
        random.Random(0), (curated, uncurated), 1.0, ("a", "i"), ("ŋ", "n"), 0.0
    )
    assert allowed is None
    assert set(excluded) == {("i", "ŋ")}


def test_no_source_language_nucleus_coda_whitelist_mode_keeps_a_coverage_floor():
    vowels = ("a", "i", "u")
    consonants = ("p", "t", "k", "m", "n")
    for seed in range(20):
        allowed, excluded = phonology_gen._resolve_nucleus_coda_restriction(
            random.Random(seed), (), 0.0, vowels, consonants, 1.0
        )
        if allowed is None:
            continue  # this seed happened to roll blacklist mode anyway
        assert {pair[0] for pair in allowed} == set(vowels)
        assert {pair[1] for pair in allowed} == set(consonants)


# --- Coda-then-next-onset co-occurrence (cross-syllable boundary) ---


def test_resolve_coda_onset_boundary_restriction_intersects_two_blacklists():
    a = _synthetic_profile("A", restricted_coda_onset_pairs=(("t", "l"), ("n", "d")))
    b = _synthetic_profile("B", restricted_coda_onset_pairs=(("t", "l"),))
    allowed, excluded = phonology_gen._resolve_coda_onset_boundary_restriction(
        random.Random(0), (a, b), 1.0, ("t", "l", "n", "d"), 0.0
    )
    assert allowed is None
    assert set(excluded) == {("t", "l")}  # ("n", "d") only forbidden by A


def test_resolve_coda_onset_boundary_restriction_unions_two_whitelists():
    a = _synthetic_profile("A", attested_coda_onset_pairs=(("n", "d"),))
    b = _synthetic_profile("B", attested_coda_onset_pairs=(("t", "l"),))
    allowed, excluded = phonology_gen._resolve_coda_onset_boundary_restriction(
        random.Random(0), (a, b), 1.0, ("n", "d", "t", "l"), 0.0
    )
    assert excluded == ()
    assert set(allowed) == {("n", "d"), ("t", "l")}


def test_resolve_coda_onset_boundary_restriction_ignores_uncurated_profiles():
    curated = _synthetic_profile("Curated", restricted_coda_onset_pairs=(("t", "l"),))
    uncurated = _synthetic_profile("Uncurated")
    allowed, excluded = phonology_gen._resolve_coda_onset_boundary_restriction(
        random.Random(0), (curated, uncurated), 1.0, ("t", "l", "n"), 0.0
    )
    assert allowed is None
    assert set(excluded) == {("t", "l")}


def test_no_source_language_coda_onset_boundary_whitelist_mode_keeps_a_coverage_floor():
    consonants = ("p", "t", "k", "m", "n")
    for seed in range(20):
        allowed, excluded = phonology_gen._resolve_coda_onset_boundary_restriction(
            random.Random(seed), (), 0.0, consonants, 1.0
        )
        if allowed is None:
            continue  # this seed happened to roll blacklist mode anyway
        covered_first = {pair[0] for pair in allowed}
        covered_second = {pair[1] for pair in allowed}
        assert covered_first == set(consonants)
        assert covered_second == set(consonants)


def test_build_coda_never_returns_an_excluded_nucleus_coda_pair():
    from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure

    consonants = tuple(c for c in phonology_gen.ALL_CONSONANTS if c.ipa in ("m", "n", "ŋ", "t"))
    vowels = tuple(v for v in phonology_gen.ALL_VOWELS if v.ipa in ("a", "i"))
    inventory = PhonemeInventory(consonants=consonants, vowels=vowels)
    structure = SyllableStructure(max_onset=1, max_coda=1, excluded_nucleus_coda_pairs=(("i", "ŋ"),))
    rng = random.Random(1)
    for _ in range(300):
        coda = word_builder._build_coda(rng, inventory, structure, "i")
        assert coda != ("ŋ",)


def test_build_coda_returns_no_coda_when_every_candidate_is_illegal_for_this_nucleus():
    # Honest empty result preferred over fabricating an illegal coda --
    # a coda is always optional, unlike a mandatory onset.
    from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure

    consonants = tuple(c for c in phonology_gen.ALL_CONSONANTS if c.ipa in ("ŋ",))
    vowels = tuple(v for v in phonology_gen.ALL_VOWELS if v.ipa in ("i",))
    inventory = PhonemeInventory(consonants=consonants, vowels=vowels)
    structure = SyllableStructure(max_onset=0, max_coda=1, excluded_nucleus_coda_pairs=(("i", "ŋ"),))
    rng = random.Random(1)
    for _ in range(50):
        assert word_builder._build_coda(rng, inventory, structure, "i") == ()


def test_build_word_respects_a_coda_onset_boundary_restriction_across_syllables():
    from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure

    consonants = tuple(c for c in phonology_gen.ALL_CONSONANTS if c.ipa in ("t", "l", "n"))
    vowels = tuple(v for v in phonology_gen.ALL_VOWELS if v.ipa in ("a", "i"))
    inventory = PhonemeInventory(consonants=consonants, vowels=vowels)
    structure = SyllableStructure(
        max_onset=1, max_coda=1, allowed_coda_consonants=("t", "n"), excluded_coda_onset_boundary_pairs=(("t", "l"),)
    )
    rng = random.Random(1)
    for _ in range(100):
        word = word_builder.build_word(rng, inventory, structure, num_syllables=2)
        known_symbols = inventory.consonant_symbols() + inventory.vowel_symbols()
        tokens = ipa_tokenizer.symbols_only(word, known_symbols)
        # No "t" immediately followed by "l" anywhere a coda meets the
        # next syllable's onset (there's no vowel between them, since a
        # coda-onset boundary is precisely two consonants back to back).
        for i in range(len(tokens) - 1):
            if tokens[i] == "t" and tokens[i + 1] == "l":
                raise AssertionError(f"illegal boundary in {word!r}")


def test_word_builder_respects_a_maximally_tight_boundary_restriction_without_crashing():
    # A pathological structure where the only "legal" boundary consonant
    # doesn't actually exist in the inventory -- `_build_onset`'s
    # defensive "or candidates" fallback must still produce *something*
    # rather than leaving onset construction stuck, across many seeds.
    from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure

    consonants = tuple(c for c in phonology_gen.ALL_CONSONANTS if c.ipa in ("p", "t", "k"))
    vowels = tuple(v for v in phonology_gen.ALL_VOWELS if v.ipa in ("a", "i"))
    inventory = PhonemeInventory(consonants=consonants, vowels=vowels)
    structure = SyllableStructure(
        max_onset=1,
        max_coda=1,
        allowed_coda_consonants=("p", "t", "k"),
        allowed_coda_onset_boundary_pairs=(("p", "x"),),  # "x" isn't even in the inventory
    )
    for seed in range(20):
        rng = random.Random(seed)
        word = word_builder.build_word(rng, inventory, structure, num_syllables=3)
        assert word


# --- Per-language word-length realism (core_vocabulary_average_syllables) ---


def _mean_syllable_count(pos, favor_short: bool, average_syllables, strictness: float, seed: int, n: int = 400) -> float:
    rng = random.Random(seed)
    total = sum(
        lexicon_gen.choose_syllable_count(rng, pos, favor_short, average_syllables, strictness) for _ in range(n)
    )
    return total / n


def test_resolve_average_syllables_averages_curated_profiles_and_ignores_uncurated():
    curated_a = _synthetic_profile("A", core_vocabulary_average_syllables=1.0)
    curated_b = _synthetic_profile("B", core_vocabulary_average_syllables=2.0)
    uncurated = _synthetic_profile("Uncurated")
    assert lexicon_gen._resolve_average_syllables((curated_a, curated_b)) == 1.5
    assert lexicon_gen._resolve_average_syllables((curated_a, uncurated)) == 1.0
    assert lexicon_gen._resolve_average_syllables((uncurated,)) is None
    assert lexicon_gen._resolve_average_syllables(()) is None


def test_choose_syllable_count_is_a_no_op_without_a_curated_average_or_strictness():
    baseline = _mean_syllable_count(PartOfSpeech.NOUN, True, None, 0.0, seed=1)
    still_none = _mean_syllable_count(PartOfSpeech.NOUN, True, None, 1.0, seed=1)
    zero_strictness = _mean_syllable_count(PartOfSpeech.NOUN, True, 1.43, 0.0, seed=1)
    assert baseline == still_none == zero_strictness


def test_choose_syllable_count_gradient_is_monotonic_in_both_directions():
    # German (long-biased) pulls the mean up as strictness increases;
    # English (short-biased) pulls it down -- mirrors this session's
    # existing test_source_language_strictness_gradient_is_monotonic shape.
    def means(average_syllables: float) -> list[float]:
        return [
            _mean_syllable_count(PartOfSpeech.NOUN, True, average_syllables, s, seed=2)
            for s in (0.0, 0.5, 1.0)
        ]

    german_means = means(_GERMAN.core_vocabulary_average_syllables)
    assert german_means[0] < german_means[1] < german_means[2]

    english_means = means(_ENGLISH.core_vocabulary_average_syllables)
    assert english_means[0] > english_means[1] > english_means[2]


def test_choose_syllable_count_never_zeroes_out_an_option_even_at_full_strictness():
    # A statistical tendency, not a hard rule -- unlike every pair-
    # restriction mechanism in this feature, every count must stay
    # reachable even at strictness=1.0.
    rng = random.Random(3)
    seen = set()
    for _ in range(2000):
        seen.add(lexicon_gen.choose_syllable_count(rng, PartOfSpeech.NOUN, True, 1.43, 1.0))
    assert seen == {1, 2, 3}


def test_recalibrated_generic_table_averages_well_under_the_old_1_7_figure():
    mean = _mean_syllable_count(PartOfSpeech.NOUN, True, None, 0.0, seed=4, n=1000)
    assert mean < 1.5


def test_full_strictness_german_words_average_more_syllables_than_english():
    client = FakeLLMClient()
    vowel_symbols_by_lang = {}
    means = {}
    for lang in ("English", "German"):
        spec = GenerationSpec(
            prompt="p", seed=6, traits=TraitProfile(source_languages=(lang,), source_language_strictness=1.0)
        )
        rng = random.Random(spec.seed)
        inventory, structure, tone_system, _ = phonology_gen.generate_phonology(rng, spec)
        romanization = romanization_gen.generate_romanization(rng, inventory)
        vowel_symbols = set(inventory.vowel_symbols())
        total = 0
        n = 150
        for _ in range(n):
            entry = lexicon_gen.propose_word(
                rng, inventory, structure, tone_system, WordAccentSystem(), romanization, "thing", PartOfSpeech.NOUN, client, "Test",
                source_languages=(lang,), strictness=1.0,
            )
            total += sum(1 for ch in entry.ipa if ch in vowel_symbols)
        means[lang] = total / n
    assert means["German"] > means["English"]


# --- Per-position in-word phoneme frequency realism ---


def test_resolve_position_multipliers_lerps_from_1_0_toward_the_tier_weight():
    profile = _synthetic_profile("A", onset_frequency_tiers={"very_common": ("s",), "rare": ("z",)})
    for strictness, expected_s, expected_z in ((0.0, 1.0, 1.0), (0.5, 1.5, 1.0 - 0.425), (1.0, 2.0, 0.15)):
        result = dict(
            phonology_gen._resolve_position_multipliers(("s", "z"), (profile,), strictness, "onset_frequency_tiers")
        )
        if strictness <= 0.0:
            assert result == {}
        else:
            assert result["s"] == pytest.approx(expected_s)
            assert result["z"] == pytest.approx(expected_z)


def test_resolve_position_multipliers_common_tier_is_always_exactly_1_0():
    profile = _synthetic_profile("A", onset_frequency_tiers={"common": ("p",)})
    for strictness in (0.25, 0.5, 1.0):
        result = dict(
            phonology_gen._resolve_position_multipliers(("p",), (profile,), strictness, "onset_frequency_tiers")
        )
        assert result["p"] == 1.0


def test_resolve_position_multipliers_unflagged_symbol_gets_no_entry():
    profile = _synthetic_profile("A", onset_frequency_tiers={"very_common": ("s",)})
    result = dict(
        phonology_gen._resolve_position_multipliers(("s", "t"), (profile,), 1.0, "onset_frequency_tiers")
    )
    assert "t" not in result
    assert result["s"] == 2.0


def test_resolve_position_multipliers_averages_disagreeing_profiles():
    a = _synthetic_profile("A", onset_frequency_tiers={"very_common": ("s",)})  # 2.0
    b = _synthetic_profile("B", onset_frequency_tiers={"rare": ("s",)})  # 0.15
    result = dict(
        phonology_gen._resolve_position_multipliers(("s",), (a, b), 1.0, "onset_frequency_tiers")
    )
    assert result["s"] == pytest.approx((2.0 + 0.15) / 2)


def test_resolve_position_multipliers_no_op_without_a_match_or_strictness():
    profile = _synthetic_profile("A", onset_frequency_tiers={"very_common": ("s",)})
    assert phonology_gen._resolve_position_multipliers(("s",), (), 1.0, "onset_frequency_tiers") == ()
    assert phonology_gen._resolve_position_multipliers(("s",), (profile,), 0.0, "onset_frequency_tiers") == ()


def _onset_token_share(rng: random.Random, inventory, structure, symbol: str, n: int = 200) -> float:
    hits = 0
    for _ in range(n):
        word = word_builder.build_word(rng, inventory, structure, num_syllables=2)
        if word and word[0] == symbol:
            hits += 1
    return hits / n


def test_full_strictness_english_boosts_frequent_onsets_and_suppresses_rare_ones():
    def onset_s_share(strictness: float, seed: int) -> float:
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("English",), source_language_strictness=strictness)
        )
        inventory, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        if "s" not in inventory.consonant_symbols():
            return None
        rng = random.Random(seed + 500)
        return _onset_token_share(rng, inventory, structure, "s", n=300)

    for seed in range(10):
        strict_share = onset_s_share(1.0, seed)
        loose_share = onset_s_share(0.0, seed)
        if strict_share is None or loose_share is None:
            continue
        assert strict_share >= loose_share
        break
    else:
        raise AssertionError("no seed in range had /s/ in both inventories")


def test_full_strictness_dutch_x_rises_in_coda_but_not_onset():
    # The concrete position-asymmetry case this feature targets: the same
    # symbol, opposite tiers, by position.
    found_case = False
    for seed in range(10):
        spec0 = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("Dutch",), source_language_strictness=0.0)
        )
        spec1 = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("Dutch",), source_language_strictness=1.0)
        )
        inv0, structure0, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec0)
        inv1, structure1, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec1)
        if "x" not in inv1.consonant_symbols():
            continue
        found_case = True
        onset_mult = dict(structure1.onset_symbol_multipliers).get("x", 1.0)
        coda_mult = dict(structure1.coda_symbol_multipliers).get("x", 1.0)
        assert onset_mult < 1.0  # rare onset
        assert coda_mult > 1.0  # very_common coda
    assert found_case


def test_zero_strictness_and_no_source_language_leave_multiplier_fields_empty():
    for spec in (
        GenerationSpec(prompt="p", seed=1),
        GenerationSpec(prompt="p", seed=1, traits=TraitProfile(source_languages=("English",), source_language_strictness=0.0)),
    ):
        _, structure, _, _ = phonology_gen.generate_phonology(random.Random(1), spec)
        assert structure.onset_symbol_multipliers == ()
        assert structure.nucleus_symbol_multipliers == ()
        assert structure.coda_symbol_multipliers == ()


# --- Word stress (milestone: primary lexical stress) ---


def test_full_strictness_french_words_are_overwhelmingly_stressed_on_the_last_syllable():
    # Real French: essentially always final-syllable stress -- French's
    # own curated stress_deviation_rate is illustratively tiny. French's
    # own vowel symbols are all single characters and this profile
    # doesn't model diphthongs, so "exactly one vowel character after
    # the stress mark" is a reliable proxy for "the stressed syllable is
    # the word's own last one."
    french = next(p for p in REFERENCE_LANGUAGES if p.name == "French")
    vowel_symbols = frozenset(french.vowels)
    total = 0
    final_stressed = 0
    for seed in range(15):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("French",), source_language_strictness=1.0)
        )
        language = generate_language("French", spec, FakeLLMClient())
        for entry in language.lexicon.entries:
            if STRESS_MARK not in entry.ipa:
                continue  # a monosyllable, or the reduplicated kinship path (no mark either way)
            total += 1
            mark_index = entry.ipa.index(STRESS_MARK)
            rest = entry.ipa[mark_index + 1 :]
            if sum(1 for ch in rest if ch in vowel_symbols) == 1:
                final_stressed += 1
    assert total > 0
    assert final_stressed / total > 0.85


def test_full_strictness_spanish_and_italian_never_leak_the_stress_mark_into_romanization():
    for lang in ("Spanish", "Italian", "English", "German", "French", "Dutch"):
        for seed in range(5):
            spec = GenerationSpec(
                prompt="p", seed=seed, traits=TraitProfile(source_languages=(lang,), source_language_strictness=1.0)
            )
            language = generate_language(lang, spec, FakeLLMClient())
            for entry in language.lexicon.entries:
                assert STRESS_MARK not in entry.romanization, (lang, entry.ipa, entry.romanization)


def test_full_strictness_most_words_carry_an_embedded_stress_mark():
    # Not every word gets marked (a monosyllable's own single syllable is
    # trivially "the stressed one," conveying nothing to mark), but the
    # overwhelming majority of a real, mixed-syllable-count lexicon
    # should -- including reduplicated mama/papa kinship words, which
    # get real stress like any other word (see
    # word_builder.build_reduplicated_word).
    spec = GenerationSpec(
        prompt="p", seed=2, traits=TraitProfile(source_languages=("Italian",), source_language_strictness=1.0)
    )
    language = generate_language("Italian", spec, FakeLLMClient())
    marked = sum(STRESS_MARK in e.ipa for e in language.lexicon.entries)
    assert marked > len(language.lexicon.entries) * 0.5


# --- Synchronic stress-driven vowel reduction ---


def test_reduce_unstressed_vowels_swaps_non_stressed_nuclei_toward_schwa():
    # Isolated before/after comparison: schwa has near-zero prevalence
    # (0.01) against a dominant "e" (0.99), so almost no schwa should
    # appear via ordinary weighted selection alone -- the swap mechanism
    # itself, not schwa's own frequency, has to be doing the work.
    inventory = PhonemeInventory(
        consonants=(
            Consonant(ipa="p", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, prevalence=0.9),
            Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, prevalence=0.9),
        ),
        vowels=(
            Vowel(ipa="e", height=VowelHeight.CLOSE_MID, backness=VowelBackness.FRONT, rounded=False, prevalence=0.99),
            Vowel(ipa="ə", height=VowelHeight.MID, backness=VowelBackness.CENTRAL, rounded=False, prevalence=0.01),
        ),
    )
    structure = SyllableStructure(max_onset=1, max_coda=0)

    def _schwa_count(reduce: bool) -> int:
        total = 0
        for seed in range(150):
            word = word_builder.build_word(
                random.Random(seed), inventory, structure, 3,
                stress_pattern="final", stress_deviation_rate=0.0, stress_strictness=1.0,
                reduce_unstressed_vowels=reduce,
            )
            total += word.count("ə")
        return total

    assert _schwa_count(False) < 15  # near-baseline, matching schwa's tiny prevalence
    assert _schwa_count(True) > 150  # the swap mechanism visibly firing


def test_reduce_unstressed_vowels_rarely_touches_the_stressed_syllable():
    # `weighted_choice` floors every weight at 0.001 (see its own
    # docstring), so even at prevalence=0.0 ordinary selection retains a
    # tiny nonzero chance of picking schwa anywhere, including the
    # stressed syllable -- that's an existing, deliberate floor, not a
    # bug this test should fight. So this compares rates rather than
    # asserting an absolute "never": the swap should make schwa common
    # in *non*-stressed syllables while leaving the stressed one at
    # (close to) that same tiny floor-driven baseline.
    inventory = PhonemeInventory(
        consonants=(Consonant(ipa="p", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, prevalence=0.9),),
        vowels=(
            Vowel(ipa="e", height=VowelHeight.CLOSE_MID, backness=VowelBackness.FRONT, rounded=False, prevalence=0.99),
            Vowel(ipa="ə", height=VowelHeight.MID, backness=VowelBackness.CENTRAL, rounded=False, prevalence=0.0),
        ),
    )
    structure = SyllableStructure(max_onset=1, max_coda=0)
    stressed_schwa = 0
    unstressed_schwa = 0
    n = 500
    for seed in range(n):
        word = word_builder.build_word(
            random.Random(seed), inventory, structure, 3,
            stress_pattern="final", stress_deviation_rate=0.0, stress_strictness=1.0,
            reduce_unstressed_vowels=True,
        )
        # final stress -- the stressed syllable is everything from the
        # mark to the end of the word.
        mark_index = word.index(STRESS_MARK)
        if "ə" in word[mark_index:]:
            stressed_schwa += 1
        if "ə" in word[:mark_index]:
            unstressed_schwa += 1
    assert unstressed_schwa > n * 0.4  # the swap visibly firing
    assert stressed_schwa < n * 0.05  # only the residual weight-floor rate, not the swap


def test_reduce_unstressed_vowels_is_a_no_op_without_schwa_in_the_inventory():
    inventory = PhonemeInventory(
        consonants=(Consonant(ipa="p", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, prevalence=0.9),),
        vowels=(Vowel(ipa="e", height=VowelHeight.CLOSE_MID, backness=VowelBackness.FRONT, rounded=False, prevalence=1.0),),
    )
    structure = SyllableStructure(max_onset=1, max_coda=0)
    word = word_builder.build_word(
        random.Random(1), inventory, structure, 3,
        stress_pattern="final", stress_deviation_rate=0.0, stress_strictness=1.0,
        reduce_unstressed_vowels=True,
    )
    assert "ə" not in word  # nothing to swap toward -- abstains rather than fabricating one


def test_reduce_unstressed_vowels_skips_a_swap_that_would_violate_a_nucleus_coda_restriction():
    # Real English's own /ŋ/-only-after-a-checked-vowel restriction:
    # schwa doesn't license it, so a syllable's own (nucleus, coda) pair
    # must never end up being (ə, ŋ), even when the swap would otherwise
    # fire. max_onset=0 (no onset consonants at all) makes every
    # syllable exactly nucleus+optional-coda, so the flat string parses
    # back into syllables unambiguously (a vowel starts a new syllable; a
    # consonant right after one, with nothing to consume it as an onset,
    # can only be *that* vowel's own coda) -- with a real onset, "ə"
    # ending one syllable and "ŋ" opening the next would be a legal
    # cross-syllable adjacency, not the same restriction at all.
    inventory = PhonemeInventory(
        consonants=(Consonant(ipa="ŋ", place=Place.VELAR, manner=Manner.NASAL, voiced=True, prevalence=0.9),),
        vowels=(
            Vowel(ipa="i", height=VowelHeight.CLOSE, backness=VowelBackness.FRONT, rounded=False, prevalence=0.9),
            Vowel(ipa="ə", height=VowelHeight.MID, backness=VowelBackness.CENTRAL, rounded=False, prevalence=0.0),
        ),
    )
    structure = SyllableStructure(
        max_onset=0, max_coda=1, excluded_nucleus_coda_pairs=(("ə", "ŋ"),),
    )
    for seed in range(100):
        word = word_builder.build_word(
            random.Random(seed), inventory, structure, 3,
            stress_pattern="final", stress_deviation_rate=0.0, stress_strictness=1.0,
            reduce_unstressed_vowels=True,
        )
        bare = word.replace(STRESS_MARK, "")
        vowels = "iə"
        for i, ch in enumerate(bare):
            if ch == "ŋ" and i > 0 and bare[i - 1] in vowels:
                assert bare[i - 1] != "ə"
