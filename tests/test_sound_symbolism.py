"""Distributional checks for meaning-specific sound symbolism: the
mama/papa kinship convergence (Jakobson 1960) and size sound symbolism for
big/small (Sapir 1929)."""

import random

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.phonology import VowelHeight
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import lexicon_gen, phonology_gen, romanization_gen
from conlang_generator.llm.fake_client import FakeLLMClient


def _fixed_language(seed: int = 42):
    spec = GenerationSpec(prompt="p", seed=seed)
    rng = random.Random(seed)
    inventory, structure, tone_system = phonology_gen.generate_phonology(rng, spec)
    romanization = romanization_gen.generate_romanization(rng, inventory)
    return inventory, structure, tone_system, romanization


def test_mother_skews_nasal_and_father_skews_stop_onsets():
    inventory, structure, tone_system, romanization = _fixed_language()
    client = FakeLLMClient()
    rng = random.Random(1)

    nasal_ipas = {c.ipa for c in inventory.consonants if c.manner.value == "nasal"}
    stop_ipas = {c.ipa for c in inventory.consonants if c.manner.value == "stop" and not c.ejective}

    mother_nasal_onsets = 0
    father_stop_onsets = 0
    n = 100
    for _ in range(n):
        mother = lexicon_gen.propose_word(
            rng, inventory, structure, tone_system, romanization, "mother", PartOfSpeech.NOUN, client, "Test"
        )
        if mother.ipa[0] in nasal_ipas:
            mother_nasal_onsets += 1
        father = lexicon_gen.propose_word(
            rng, inventory, structure, tone_system, romanization, "father", PartOfSpeech.NOUN, client, "Test"
        )
        if father.ipa[0] in stop_ipas:
            father_stop_onsets += 1

    # Baseline (unrelated gloss) onset-manner rate for comparison.
    baseline_nasal_onsets = sum(
        1
        for _ in range(n)
        if lexicon_gen.propose_word(
            rng, inventory, structure, tone_system, romanization, "tree", PartOfSpeech.NOUN, client, "Test"
        ).ipa[0]
        in nasal_ipas
    )

    assert mother_nasal_onsets > baseline_nasal_onsets
    assert father_stop_onsets > n * 0.5


def test_small_words_average_closer_vowels_than_big_words():
    inventory, structure, tone_system, romanization = _fixed_language()
    client = FakeLLMClient()
    rng = random.Random(2)

    height_rank = {
        VowelHeight.CLOSE: 0, VowelHeight.NEAR_CLOSE: 1, VowelHeight.CLOSE_MID: 2, VowelHeight.MID: 3,
        VowelHeight.OPEN_MID: 4, VowelHeight.NEAR_OPEN: 5, VowelHeight.OPEN: 6,
    }
    height_by_ipa = {v.ipa: height_rank[v.height] for v in inventory.vowels}

    def avg_first_vowel_height(gloss: str, pos, n: int = 100) -> float:
        total = 0
        for _ in range(n):
            entry = lexicon_gen.propose_word(rng, inventory, structure, tone_system, romanization, gloss, pos, client, "Test")
            first_vowel = next(ch for ch in entry.ipa if ch in height_by_ipa)
            total += height_by_ipa[first_vowel]
        return total / n

    small_avg = avg_first_vowel_height("small", PartOfSpeech.ADJECTIVE)
    big_avg = avg_first_vowel_height("big", PartOfSpeech.ADJECTIVE)
    assert small_avg < big_avg
