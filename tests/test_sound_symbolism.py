"""Distributional checks for meaning-specific sound symbolism: the
mama/papa kinship convergence (Jakobson 1960) and size sound symbolism for
big/small (Sapir 1929)."""

import random

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.phonology import Manner, Place, PhonemeInventory, Vowel, VowelBackness, VowelHeight, Consonant
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import lexicon_gen, phonology_gen, romanization_gen, word_builder
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


def test_build_reduplicated_word_excludes_marked_consonants():
    # A stop-manner inventory mixing a plain consonant with ejective/
    # aspirated/pharyngealized/geminate/palatalized variants -- the
    # mama/papa convergence is specifically about simple, unmarked
    # articulations, so only the plain one should ever be drawn.
    inventory = PhonemeInventory(
        consonants=(
            Consonant(ipa="p", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, prevalence=0.5),
            Consonant(ipa="pʼ", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, ejective=True, prevalence=0.5),
            Consonant(ipa="pʰ", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, aspirated=True, prevalence=0.5),
            Consonant(ipa="tˤ", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, pharyngealized=True, prevalence=0.5),
            Consonant(ipa="kː", place=Place.VELAR, manner=Manner.STOP, voiced=False, long=True, prevalence=0.5),
            Consonant(ipa="tʲ", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, palatalized=True, prevalence=0.5),
            Consonant(ipa="bʱ", place=Place.BILABIAL, manner=Manner.STOP, voiced=True, breathy=True, prevalence=0.5),
        ),
        vowels=(Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=1.0),),
    )
    rng = random.Random(1)
    for _ in range(50):
        word = word_builder.build_reduplicated_word(rng, inventory, (Manner.STOP,))
        assert word is not None
        assert word == "papa"


def test_build_reduplicated_word_respects_a_hard_onset_restriction():
    # Regression guard: /ŋ/ categorically can't open a syllable in real
    # Dutch (SyllableStructure.excluded_onset_consonants) -- unlike the
    # marked-articulation exclusions above (a style choice this function
    # otherwise deliberately skips), that's a hard phonotactic fact, so
    # it must still apply even to the reduplication special case. Before
    # this fix, a Dutch-shaped inventory could produce "ŋaŋa" for
    # "mother", which no real Dutch word could ever be.
    inventory = PhonemeInventory(
        consonants=(
            Consonant(ipa="m", place=Place.BILABIAL, manner=Manner.NASAL, voiced=True, prevalence=0.5),
            Consonant(ipa="ŋ", place=Place.VELAR, manner=Manner.NASAL, voiced=True, prevalence=0.9),
        ),
        vowels=(Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=1.0),),
    )
    rng = random.Random(1)
    for _ in range(50):
        word = word_builder.build_reduplicated_word(
            rng, inventory, (Manner.NASAL,), excluded_onset_consonants=("ŋ",)
        )
        assert word == "mama"  # never "ŋaŋa", even though /ŋ/ has higher prevalence


def test_build_reduplicated_word_excludes_diphthongs_but_still_returns_a_word():
    # Same "simple, unmarked sounds" reasoning applied to the vowel side --
    # a diphthong/nasalized-only inventory still falls back to a real
    # (non-open, since none is available) plain monophthong rather than
    # ever picking either marked vowel or returning None.
    inventory = PhonemeInventory(
        consonants=(Consonant(ipa="p", place=Place.BILABIAL, manner=Manner.STOP, voiced=False, prevalence=0.5),),
        vowels=(
            Vowel(ipa="e", height=VowelHeight.CLOSE_MID, backness=VowelBackness.FRONT, rounded=False, prevalence=1.0),
            Vowel(ipa="ai", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, diphthong=True, prevalence=1.0),
            Vowel(ipa="ã", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, nasalized=True, prevalence=1.0),
        ),
    )
    rng = random.Random(1)
    for _ in range(50):
        word = word_builder.build_reduplicated_word(rng, inventory, (Manner.STOP,))
        assert word is not None
        assert word == "pepe"  # the only non-diphthong vowel available


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
