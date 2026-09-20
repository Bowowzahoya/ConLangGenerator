"""Data checks for the curated real-language vocabularies
(``generation/reference_languages/lexicons/*.yaml``): every entry must be
usable by generation and by the sound-change engine, both of which silently
drop symbols they can't tokenize."""

import pytest

from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK
from conlang_generator.generation import ipa_tokenizer, phonology_gen
from conlang_generator.generation.lexicon_gen import ALL_MEANINGS
from conlang_generator.generation.reference_languages import REFERENCE_LANGUAGES
from conlang_generator.generation.reference_languages.real_lexicon import curated_profiles, real_words

_KNOWN = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
_GLOSSES = {gloss for gloss, _ in ALL_MEANINGS}
_CURATED = [p.name for p in curated_profiles()]


def test_the_original_curated_languages_are_all_present():
    assert len(_CURATED) >= 36
    assert "Dutch" in _CURATED and "French" in _CURATED


@pytest.mark.parametrize("name", _CURATED)
def test_every_entry_is_a_real_gloss_with_a_fully_tokenizable_ipa(name):
    words = real_words(name)
    assert words
    for gloss, (spelling, ipa) in words.items():
        assert gloss in _GLOSSES, f"{name}: {gloss!r} is not an ALL_MEANINGS gloss"
        assert spelling.strip() and ipa.strip(), f"{name}: empty entry for {gloss!r}"
        tokens = ipa_tokenizer.tokenize(ipa, _KNOWN + (STRESS_MARK, WORD_ACCENT_MARK))
        assert "".join(symbol + deco for symbol, deco in tokens) == ipa, f"{name}: {gloss!r} /{ipa}/ has unmodeled symbols"


def test_a_language_without_a_curated_vocabulary_returns_nothing():
    assert real_words("Sumerian") == {} or real_words("Sumerian")  # either curated or empty, never an error
    assert real_words("Not A Language") == {}
