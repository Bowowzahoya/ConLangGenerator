"""Shared minimal fixtures for tests that need a fully-formed ``Language``
without going through the (slower, LLM-touching) generation pipeline."""

from __future__ import annotations

from conlang_generator.core.grammar import Alignment, GrammarProfile, MorphologicalType, WordOrder
from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import LexicalEntry, Lexicon, PartOfSpeech
from conlang_generator.core.phonology import (
    Consonant,
    Manner,
    Place,
    PhonemeInventory,
    SyllableStructure,
    ToneSystem,
    Vowel,
    VowelBackness,
    VowelHeight,
)
from conlang_generator.core.romanization import RomanizationRule, RomanizationScheme
from conlang_generator.core.spec import GenerationSpec


def make_minimal_language(name: str = "Test Tongue", seed: int = 1) -> Language:
    inventory = PhonemeInventory(
        consonants=(
            Consonant(ipa="p", place=Place.BILABIAL, manner=Manner.STOP, voiced=False),
            Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False),
            Consonant(ipa="m", place=Place.BILABIAL, manner=Manner.NASAL, voiced=True),
        ),
        vowels=(
            Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False),
            Vowel(ipa="i", height=VowelHeight.CLOSE, backness=VowelBackness.FRONT, rounded=False),
        ),
    )
    romanization = RomanizationScheme(
        rules=tuple(RomanizationRule(ipa=s, latin=s) for s in inventory.all_symbols())
    )
    lexicon = Lexicon(
        entries=(
            LexicalEntry(ipa="pa", romanization="pa", glosses=("mountain",), pos=PartOfSpeech.NOUN),
            LexicalEntry(ipa="ti", romanization="ti", glosses=("high",), pos=PartOfSpeech.ADJECTIVE),
        )
    )
    return Language(
        name=name,
        spec=GenerationSpec(prompt="a minimal test language", seed=seed),
        phonology=inventory,
        syllable_structure=SyllableStructure(max_onset=1, max_coda=0),
        tone_system=ToneSystem(enabled=False),
        romanization=romanization,
        grammar=GrammarProfile(
            word_order=WordOrder.SVO,
            morphological_type=MorphologicalType.ISOLATING,
            alignment=Alignment.NOMINATIVE_ACCUSATIVE,
            has_articles=True,
            adjective_after_noun=True,
            has_overt_copula=True,
        ),
        lexicon=lexicon,
    )
