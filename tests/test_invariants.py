"""Architecture-invariant tests: mutation-shaped methods must return a new
instance rather than mutate in place (copy-on-transition state semantics,
per AGENTS.md)."""

import pytest

from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from tests.factories import make_minimal_language


def test_language_with_new_words_returns_new_instance():
    language = make_minimal_language()
    new_entry = LexicalEntry(ipa="ma", romanization="ma", glosses=("water",), pos=PartOfSpeech.NOUN)

    updated = language.with_new_words((new_entry,), reason="test")

    assert updated is not language
    assert new_entry not in language.lexicon.entries
    assert new_entry in updated.lexicon.entries
    assert language.history == ()
    assert updated.history == ("test",)


def test_lexicon_with_entries_returns_new_instance():
    language = make_minimal_language()
    lexicon = language.lexicon
    new_entry = LexicalEntry(ipa="ma", romanization="ma", glosses=("water",), pos=PartOfSpeech.NOUN)

    updated = lexicon.with_entries((new_entry,))

    assert updated is not lexicon
    assert new_entry not in lexicon.entries


def test_models_are_frozen():
    language = make_minimal_language()
    with pytest.raises((TypeError, ValueError)):
        language.name = "Something Else"  # type: ignore[misc]
