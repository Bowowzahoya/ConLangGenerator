import pytest

from conlang_generator.core.lexicon import LexicalEntry, Lexicon, PartOfSpeech


def test_by_gloss_is_case_insensitive_against_stored_capitalization():
    # "I" is stored capitalized (natural English orthography for the
    # pronoun); a lowercase query token must still find it.
    lexicon = Lexicon(
        entries=(LexicalEntry(ipa="i", romanization="i", glosses=("I",), pos=PartOfSpeech.PRONOUN),)
    )
    assert lexicon.by_gloss("i") is not None
    assert lexicon.by_gloss("I") is not None


def test_with_replaced_entry_swaps_only_the_matching_entry_in_place():
    water = LexicalEntry(ipa="watər", romanization="water", glosses=("water",), pos=PartOfSpeech.NOUN)
    fire = LexicalEntry(ipa="faɪər", romanization="fire", glosses=("fire",), pos=PartOfSpeech.NOUN)
    lexicon = Lexicon(entries=(water, fire))
    edited_water = water.model_copy(update={"romanization": "aqua"})

    updated = lexicon.with_replaced_entry("water", edited_water)

    assert updated.entries == (edited_water, fire)  # position preserved, fire untouched
    assert lexicon.entries == (water, fire)  # original lexicon itself is unchanged (frozen model)


def test_with_replaced_entry_matches_case_insensitively():
    water = LexicalEntry(ipa="watər", romanization="water", glosses=("Water",), pos=PartOfSpeech.NOUN)
    lexicon = Lexicon(entries=(water,))
    edited = water.model_copy(update={"romanization": "aqua"})
    updated = lexicon.with_replaced_entry("water", edited)
    assert updated.entries == (edited,)


def test_with_replaced_entry_raises_for_an_unknown_gloss():
    lexicon = Lexicon(entries=())
    with pytest.raises(ValueError):
        lexicon.with_replaced_entry("nonexistent", LexicalEntry(ipa="x", romanization="x", glosses=("x",), pos=PartOfSpeech.NOUN))
