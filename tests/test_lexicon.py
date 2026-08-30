from conlang_generator.core.lexicon import LexicalEntry, Lexicon, PartOfSpeech


def test_by_gloss_is_case_insensitive_against_stored_capitalization():
    # "I" is stored capitalized (natural English orthography for the
    # pronoun); a lowercase query token must still find it.
    lexicon = Lexicon(
        entries=(LexicalEntry(ipa="i", romanization="i", glosses=("I",), pos=PartOfSpeech.PRONOUN),)
    )
    assert lexicon.by_gloss("i") is not None
    assert lexicon.by_gloss("I") is not None
