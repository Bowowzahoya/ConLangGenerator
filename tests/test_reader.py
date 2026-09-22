"""Tests for speech.reader.describe -- the CLI `conlang pronounce` command's
own text description of a looked-up word, including its Chao-letter/digit
tone-contour line for a tonal word."""

from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from conlang_generator.core.phonology import ToneLevel
from conlang_generator.speech import reader


def test_describe_a_toneless_word_is_unchanged():
    entry = LexicalEntry(ipa="kat", romanization="kat", glosses=("cat",), pos=PartOfSpeech.NOUN)
    assert reader.describe(entry) == "IPA: /kat/  Romanized: kat"
    assert "Tone" not in reader.describe(entry)


def test_describe_a_tonal_word_appends_its_own_chao_letter_and_digit_contour():
    entry = LexicalEntry(
        ipa="ma", romanization="ma", glosses=("mother",), pos=PartOfSpeech.NOUN, tones=(ToneLevel.HIGH,),
    )
    assert reader.describe(entry) == "IPA: /ma/  Romanized: ma  Tone contour: ˥˥ (55)"


def test_describe_a_multi_syllable_tonal_word_shows_one_contour_per_syllable_in_order():
    entry = LexicalEntry(
        ipa="mamə", romanization="mama", glosses=("mother",), pos=PartOfSpeech.NOUN,
        tones=(ToneLevel.HIGH, ToneLevel.NEUTRAL),
    )
    assert reader.describe(entry) == "IPA: /mamə/  Romanized: mama  Tone contour: ˥˥ (55) ˩˩ (11)"
