import unicodedata

from conlang_generator.core.romanization import (
    RomanizationRule,
    RomanizationScheme,
    SyllableBoundaryMarker,
    ToneMarkingStrategy,
    VowelLengthStrategy,
)

COMBINING_ACUTE = "́"
COMBINING_GRAVE = "̀"


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


def _dutch_ish_scheme() -> RomanizationScheme:
    # A minimal "vuur"-shaped scheme: v/r consonants, y = the long vowel
    # that alternates, i = a filler vowel for building open syllables.
    return RomanizationScheme(
        rules=(
            RomanizationRule(ipa="v", latin="v"),
            RomanizationRule(ipa="r", latin="r"),
            RomanizationRule(ipa="i", latin="i"),
            RomanizationRule(ipa="y", latin="uu", syllable=("syllable_closed",)),
            RomanizationRule(ipa="y", latin="u", syllable=("syllable_open",)),
        ),
        vowel_symbols=("y", "i"),
        legal_onset_clusters=(),
    )


def test_closed_syllable_uses_the_closed_variant():
    # "vyr" -- y followed by a word-final consonant, no following vowel --
    # is a closed syllable (the "vuur" case).
    assert _dutch_ish_scheme().apply("vyr") == "vuur"


def test_open_syllable_uses_the_open_variant():
    # "vyri" -- y followed by a single consonant then a vowel -- is an open
    # syllable (the "vuren"-shaped case): that "r" belongs to the next
    # syllable's onset, not this one's coda.
    assert _dutch_ish_scheme().apply("vyri") == "vuri"


def test_word_final_vowel_is_open():
    assert _dutch_ish_scheme().apply("vy") == "vu"


def test_legal_onset_cluster_extends_the_open_syllable():
    # "y" followed by a legal 2-consonant onset cluster then a vowel --
    # both consonants belong to the next syllable, so this one is still
    # open.
    scheme = RomanizationScheme(
        rules=(
            RomanizationRule(ipa="p", latin="p"),
            RomanizationRule(ipa="l", latin="l"),
            RomanizationRule(ipa="i", latin="i"),
            RomanizationRule(ipa="y", latin="uu", syllable=("syllable_closed",)),
            RomanizationRule(ipa="y", latin="u", syllable=("syllable_open",)),
        ),
        vowel_symbols=("y", "i"),
        legal_onset_clusters=(("p", "l"),),
    )
    assert scheme.apply("yplipli") == "uplipli"


def _french_ish_scheme() -> RomanizationScheme:
    # A minimal "manger"/"mangeons"-shaped scheme: ʒ spelled "g" before a
    # front vowel, "ge" (silent e) before a back vowel, "j" elsewhere.
    return RomanizationScheme(
        rules=(
            RomanizationRule(ipa="m", latin="m"),
            RomanizationRule(ipa="ʒ", latin="g", following=("front_vowel",)),
            RomanizationRule(ipa="ʒ", latin="ge", following=("back_vowel",)),
            RomanizationRule(ipa="ʒ", latin="j"),
            RomanizationRule(ipa="e", latin="e"),
            RomanizationRule(ipa="ɔ", latin="o"),
        ),
        vowel_symbols=("e", "ɔ"),
        vowel_backness=(("e", "front"), ("ɔ", "back")),
    )


def test_class_conditioned_rule_selects_the_front_vowel_variant():
    assert _french_ish_scheme().apply("mʒe") == "mge"


def test_class_conditioned_rule_selects_the_back_vowel_variant_with_multiletter_grapheme():
    assert _french_ish_scheme().apply("mʒɔ") == "mgeo"


def test_unconditioned_rule_is_the_fallback_when_no_class_matches():
    assert _french_ish_scheme().apply("mʒm") == "mjm"


def _pinyin_ish_scheme() -> RomanizationScheme:
    # A minimal ü/u-shaped scheme: /y/ spelled "ü" by default, "u" after j.
    return RomanizationScheme(
        rules=(
            RomanizationRule(ipa="j", latin="j"),
            RomanizationRule(ipa="n", latin="n"),
            RomanizationRule(ipa="y", latin="ü"),
            RomanizationRule(ipa="y", latin="u", preceding=("j",)),
        ),
        vowel_symbols=("y",),
    )


def test_specific_segment_conditioning_selects_the_variant_after_the_named_symbol():
    assert _pinyin_ish_scheme().apply("jy") == "ju"


def test_specific_segment_conditioning_falls_back_when_the_named_symbol_is_absent():
    assert _pinyin_ish_scheme().apply("ny") == "nü"


def _toned_scheme(tone_strategy: ToneMarkingStrategy, tone_markers: tuple[tuple[str, str], ...]) -> RomanizationScheme:
    return RomanizationScheme(
        rules=(
            RomanizationRule(ipa="m", latin="m"),
            RomanizationRule(ipa="a", latin="a"),
            RomanizationRule(ipa="n", latin="n"),
        ),
        vowel_symbols=("a",),
        tone_strategy=tone_strategy,
        tone_markers=tone_markers,
    )


def test_vowel_diacritic_tone_strategy_is_the_unchanged_default():
    scheme = _toned_scheme(ToneMarkingStrategy.VOWEL_DIACRITIC, ((COMBINING_ACUTE, "1"),))
    assert scheme.apply("ma" + COMBINING_ACUTE + "n") == "mán"


def test_unmarked_tone_strategy_drops_the_mark():
    scheme = _toned_scheme(ToneMarkingStrategy.UNMARKED, ())
    assert scheme.apply("ma" + COMBINING_ACUTE + "n") == "man"


def test_postposed_digit_tone_flushes_after_the_vowels_own_coda():
    scheme = _toned_scheme(ToneMarkingStrategy.POSTPOSED_DIGIT, ((COMBINING_ACUTE, "1"),))
    assert scheme.apply("ma" + COMBINING_ACUTE + "n") == "man1"


def test_postposed_digit_tone_flushes_at_a_word_final_open_syllable():
    scheme = _toned_scheme(ToneMarkingStrategy.POSTPOSED_DIGIT, ((COMBINING_ACUTE, "1"),))
    assert scheme.apply("ma" + COMBINING_ACUTE) == "ma1"


def test_postposed_letter_tone_lands_on_each_syllable_not_just_the_word_end():
    scheme = _toned_scheme(ToneMarkingStrategy.POSTPOSED_LETTER, ((COMBINING_ACUTE, "x"), (COMBINING_GRAVE, "z")))
    assert scheme.apply("ma" + COMBINING_ACUTE + "na" + COMBINING_GRAVE) == "maxnaz"


def test_short_vowel_neighbor_tag_selects_the_conditioned_rule():
    scheme = RomanizationScheme(
        rules=(
            RomanizationRule(ipa="t", latin="t"),
            RomanizationRule(ipa="t", latin="tt", preceding=("short_vowel",)),
            RomanizationRule(ipa="a", latin="a"),
        ),
        vowel_symbols=("a",),
        vowel_length=(("a", "short"),),
    )
    assert scheme.apply("at") == "att"


def test_long_vowel_neighbor_tag_does_not_trigger_the_short_conditioned_rule():
    scheme = RomanizationScheme(
        rules=(
            RomanizationRule(ipa="t", latin="t"),
            RomanizationRule(ipa="t", latin="tt", preceding=("short_vowel",)),
            RomanizationRule(ipa="a", latin="a"),
        ),
        vowel_symbols=("a",),
        vowel_length=(("a", "long"),),
    )
    assert scheme.apply("at") == "at"


def _silent_e_scheme() -> RomanizationScheme:
    # A minimal "mat"/"mate"-shaped scheme: "aː" is the long vowel tagged
    # "long" (its short counterpart "a" tagged "short"), both spelled with
    # the same plain letter -- SILENT_E's trailing "e" is the only thing
    # that distinguishes them.
    return RomanizationScheme(
        rules=(
            RomanizationRule(ipa="m", latin="m"),
            RomanizationRule(ipa="t", latin="t"),
            RomanizationRule(ipa="a", latin="a"),
            RomanizationRule(ipa="aː", latin="a"),
        ),
        vowel_symbols=("a", "aː"),
        vowel_length=(("aː", "long"), ("a", "short")),
        vowel_length_strategy=VowelLengthStrategy.SILENT_E,
    )


def test_silent_e_lands_after_the_coda_in_a_closed_syllable():
    assert _silent_e_scheme().apply("maːt") == "mate"


def test_silent_e_is_absent_in_a_word_final_open_syllable():
    assert _silent_e_scheme().apply("maː") == "ma"


def test_silent_e_is_absent_for_a_vowel_not_tagged_long():
    assert _silent_e_scheme().apply("at") == "at"


def _boundary_marker_scheme(marker: SyllableBoundaryMarker) -> RomanizationScheme:
    return RomanizationScheme(
        rules=(
            RomanizationRule(ipa="n", latin="n"),
            RomanizationRule(ipa="i", latin="i"),
            RomanizationRule(ipa="a", latin="a"),
        ),
        vowel_symbols=("i", "a"),
        syllable_boundary_marker=marker,
    )


def test_syllable_boundary_marker_separates_adjacent_vowels():
    # "nia" -- "a" immediately follows "i" with no consonant between them,
    # a hiatus (this project doesn't model diphthongs, so two adjacent
    # vowel symbols are always a genuine syllable boundary).
    assert _boundary_marker_scheme(SyllableBoundaryMarker.APOSTROPHE).apply("nia") == "ni'a"


def test_syllable_boundary_marker_is_absent_when_a_consonant_separates_the_vowels():
    assert _boundary_marker_scheme(SyllableBoundaryMarker.APOSTROPHE).apply("nina") == "nina"


def test_syllable_boundary_marker_is_absent_when_unset():
    assert _boundary_marker_scheme(SyllableBoundaryMarker.NONE).apply("nia") == "nia"


def test_specific_symbol_match_beats_a_class_match():
    # A scheme where both a class-conditioned and a symbol-conditioned rule
    # could apply (both key off "preceding") -- the symbol match should win
    # as the more specific one.
    scheme = RomanizationScheme(
        rules=(
            RomanizationRule(ipa="j", latin="j"),
            RomanizationRule(ipa="y", latin="Y_AFTER_CONSONANT", preceding=("consonant",)),
            RomanizationRule(ipa="y", latin="Y_AFTER_J", preceding=("j",)),
        ),
        vowel_symbols=("y",),
    )
    assert scheme.apply("jy") == "jY_AFTER_J"
