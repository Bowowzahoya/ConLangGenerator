import unicodedata

from conlang_generator.core.romanization import RomanizationRule, RomanizationScheme

COMBINING_ACUTE = "́"


def _scheme() -> RomanizationScheme:
    return RomanizationScheme(
        rules=(
            RomanizationRule(ipa="tʃ", latin="ch"),
            RomanizationRule(ipa="t", latin="t"),
            RomanizationRule(ipa="a", latin="a"),
        )
    )


def test_longest_match_wins_over_prefix():
    # "tʃ" must be matched as a unit, not as "t" + unmapped "ʃ"
    assert _scheme().apply("tʃa") == "cha"


def test_unmapped_symbols_pass_through():
    assert _scheme().apply("ta!") == "ta!"


def test_output_is_nfc_normalized():
    # Identity mapping for a decomposed "e" + combining acute accent -- the
    # romanized output should come back precomposed (single 'é' codepoint),
    # matching what a human typing/pasting the word would produce.
    decomposed = "e" + COMBINING_ACUTE
    scheme = RomanizationScheme(rules=(RomanizationRule(ipa=decomposed, latin=decomposed),))
    result = scheme.apply(decomposed)
    assert result == unicodedata.normalize("NFC", result)
    assert result == "é"
    assert len(result) == 1
