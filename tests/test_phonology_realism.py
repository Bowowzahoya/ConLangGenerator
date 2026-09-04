"""Distributional checks for milestones 1-4 (inventory realism, in-word
frequency realism, real phonotactics, word-length realism). These call
``phonology_gen``/``word_builder`` directly (no LLM involved) except the
one word-length test, which needs ``lexicon_gen.propose_word``."""

import random

import pytest

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.phonology import VowelBackness
from conlang_generator.core.spec import GenerationSpec, SeedExample
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import ipa_tokenizer, lexicon_gen, phonology_gen, romanization_gen, sonority, word_builder
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
    inventory, structure, _ = phonology_gen.generate_phonology(rng, spec)
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
            inventory, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
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
            inventory, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
            hits += "ɛi" in inventory.vowel_symbols()
        return hits / len(_SEEDS)

    assert _hit_fraction(("Dutch",)) > _hit_fraction(())


def test_finnish_source_language_increases_geminate_consonant_presence():
    def _hit_fraction(source_languages: tuple[str, ...]) -> float:
        hits = 0
        for seed in _SEEDS:
            spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile(source_languages=source_languages))
            inventory, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
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
    inventory, structure, _ = phonology_gen.generate_phonology(rng, spec)
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
        inventory, structure, _ = phonology_gen.generate_phonology(random.Random(seed), GenerationSpec(prompt="p", seed=seed))
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
        inventory, structure, _ = phonology_gen.generate_phonology(random.Random(seed), GenerationSpec(prompt="p", seed=seed))
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
            _, structure, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
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
        inventory, structure, _ = phonology_gen.generate_phonology(rng, spec)
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
        inventory, structure, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
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
        inventory, structure, tone_system = phonology_gen.generate_phonology(random.Random(seed), spec)
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
        _, structure, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        assert structure.excluded_coda_consonants == ()


def test_vowel_harmony_words_mostly_share_backness():
    for seed in range(300):
        rng = random.Random(seed)
        spec = GenerationSpec(prompt="p", seed=seed)
        inventory, structure, _ = phonology_gen.generate_phonology(rng, spec)
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
    inventory, structure, tone_system = phonology_gen.generate_phonology(rng, spec)
    romanization = romanization_gen.generate_romanization(rng, inventory)
    vowel_symbols = set(inventory.vowel_symbols())

    def avg_syllable_count(favor_short: bool, seed: int) -> float:
        local_rng = random.Random(seed)
        total = 0
        n = 150
        for _ in range(n):
            entry = lexicon_gen.propose_word(
                local_rng, inventory, structure, tone_system, romanization,
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
    inventory, structure, tone_system = phonology_gen.generate_phonology(rng, spec)
    romanization = romanization_gen.generate_romanization(rng, inventory)
    vowel_symbols = set(inventory.vowel_symbols())

    def avg_syllable_count(pos: PartOfSpeech, seed: int) -> float:
        local_rng = random.Random(seed)
        total = 0
        n = 150
        for _ in range(n):
            entry = lexicon_gen.propose_word(
                local_rng, inventory, structure, tone_system, romanization,
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
        inventory, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
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
        _, structure, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        assert structure.max_onset <= _GERMAN.max_onset


def test_full_strictness_coda_profile_matches_the_source_languages_own_value():
    # Hawaiian's own coda_profile is "none" -- every generated structure
    # should land on the same effective shape (max_coda=0).
    for seed in range(30):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("Hawaiian",), source_language_strictness=1.0)
        )
        _, structure, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
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
    inventory, _, _ = phonology_gen.generate_phonology(random.Random(1), spec)
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
        inventory, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
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
            inventory, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
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
        _, structure, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        assert "ŋ" in structure.excluded_onset_consonants
        assert "ʒ" in structure.excluded_onset_consonants


def test_full_strictness_never_admits_a_restricted_coda_consonant():
    for seed in range(40):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("English",), source_language_strictness=1.0)
        )
        _, structure, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        assert not _coda_legal(structure, "j")
        assert not _coda_legal(structure, "w")

    for seed in range(40):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("German",), source_language_strictness=1.0)
        )
        _, structure, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        assert not _coda_legal(structure, "j")


def test_full_strictness_french_restricts_w_coda_but_not_j():
    # Real French genuinely has word-final /j/ (soleil, travail) -- the
    # restriction must be per-language, not a blanket glide ban.
    saw_j_allowed = False
    for seed in range(60):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("French",), source_language_strictness=1.0)
        )
        _, structure, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
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
        inventory, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
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
        inventory, structure, _ = phonology_gen.generate_phonology(rng, spec)
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
        _, structure, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        for pair in structure.allowed_onset_clusters:
            assert pair in _GERMAN.attested_onset_clusters, (seed, pair)


def test_full_strictness_english_onset_clusters_stay_within_the_curated_list():
    for seed in range(60):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("English",), source_language_strictness=1.0)
        )
        _, structure, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
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
        _, structure, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
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
        _, structure, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        for vowel in ("u", "o", "ʊ"):
            assert not _pair_legal(structure, "w", vowel)


def _synthetic_profile(name: str, **kwargs) -> ReferenceLanguageProfile:
    return ReferenceLanguageProfile(
        name=name, consonants=("p", "t", "w"), vowels=("a", "u"), coda_profile="unrestricted", max_onset=2, tonal=False, **kwargs
    )


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
        _, structure, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        assert set(structure.allowed_coda_clusters) <= set(_ENGLISH.attested_coda_clusters)


def test_zero_strictness_still_allows_an_unattested_coda_cluster():
    # Same gradient shape as the onset-cluster version: strictness=0.0
    # must not hard-restrict coda shape either.
    saw_unattested = False
    for seed in range(60):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("English",), source_language_strictness=0.0)
        )
        _, structure, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        if any(pair not in _ENGLISH.attested_coda_clusters for pair in structure.allowed_coda_clusters):
            saw_unattested = True
            break
    assert saw_unattested
