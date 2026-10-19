"""Tests for phoneme_fit.py's own public, standalone helpers --
``sound_correspondence`` (the Tweak preview's own "what sound maps to
what" display, "Tweaking an existing language" item 12 in docs/
DEFERRED.md's own numbering) and ``epenthetic_vowel`` (shared with
``word_builder.safe_affix_junction``). ``fit_ipa`` itself is covered
indirectly via ``test_names.py``/``test_real_words.py``/
``test_regenerate_phonology.py``."""

from conlang_generator.core.phonology import Consonant, Manner, Place, PhonemeInventory, Vowel, VowelBackness, VowelHeight
from conlang_generator.generation import phoneme_fit


def _inventory(*consonant_ipas: str) -> PhonemeInventory:
    by_ipa = {
        "ç": Consonant(ipa="ç", place=Place.PALATAL, manner=Manner.FRICATIVE, voiced=False, prevalence=1.0),
        "x": Consonant(ipa="x", place=Place.VELAR, manner=Manner.FRICATIVE, voiced=False, prevalence=1.0),
        "f": Consonant(ipa="f", place=Place.LABIODENTAL, manner=Manner.FRICATIVE, voiced=False, prevalence=1.0),
    }
    vowels = (Vowel(ipa="ə", height=VowelHeight.MID, backness=VowelBackness.CENTRAL, rounded=False, prevalence=1.0),)
    return PhonemeInventory(consonants=tuple(by_ipa[s] for s in consonant_ipas), vowels=vowels)


def test_sound_correspondence_maps_a_removed_symbol_to_its_nearest_surviving_one():
    old_inventory = _inventory("ç", "f")
    new_inventory = _inventory("x", "f")
    correspondence = phoneme_fit.sound_correspondence(old_inventory, new_inventory)
    assert correspondence["ç"] == "x"  # nearest surviving fricative
    assert correspondence["f"] == "f"  # unchanged symbol maps to itself


def test_sound_correspondence_covers_every_old_symbol():
    old_inventory = _inventory("ç", "f")
    new_inventory = _inventory("x", "f")
    correspondence = phoneme_fit.sound_correspondence(old_inventory, new_inventory)
    assert set(correspondence) == set(old_inventory.all_symbols())


def test_epenthetic_vowel_prefers_a_central_vowel():
    inventory = PhonemeInventory(
        consonants=(),
        vowels=(
            Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.FRONT, rounded=False, prevalence=0.9),
            Vowel(ipa="ə", height=VowelHeight.MID, backness=VowelBackness.CENTRAL, rounded=False, prevalence=0.1),
        ),
    )
    assert phoneme_fit.epenthetic_vowel(inventory) == "ə"
