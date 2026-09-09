import unicodedata

from conlang_generator.core.romanization import (
    STRESS_MARK,
    JointSpelling,
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


def test_diaeresis_marker_rewrites_the_second_vowels_own_letter():
    # Real French tréma (Noël, naïve) -- not an inserted character like
    # APOSTROPHE/HYPHEN, a modification of the second vowel's own letter.
    # "nia": "a" is the *second* vowel (the one that triggers the hiatus
    # branch, adjacent to the preceding "i") -- confirm it's "a" that
    # gets rewritten to "ä", not "i".
    result = _boundary_marker_scheme(SyllableBoundaryMarker.DIAERESIS).apply("nia")
    assert result == "niä"


def test_diaeresis_marker_leaves_the_first_vowel_untouched():
    result = _boundary_marker_scheme(SyllableBoundaryMarker.DIAERESIS).apply("nia")
    assert result[1] == "i"  # the first vowel's own letter is unchanged


def test_diaeresis_marker_is_absent_when_a_consonant_separates_the_vowels():
    assert _boundary_marker_scheme(SyllableBoundaryMarker.DIAERESIS).apply("nina") == "nina"


def test_diaeresis_marker_leaves_latin_unchanged_when_not_a_plain_vowel_letter():
    # A symbol whose own latin spelling doesn't start with one of
    # a/e/i/o/u is left as-is rather than crashing or silently mangling
    # the first character.
    scheme = RomanizationScheme(
        rules=(
            RomanizationRule(ipa="n", latin="n"),
            RomanizationRule(ipa="i", latin="i"),
            RomanizationRule(ipa="o", latin="zh"),
        ),
        vowel_symbols=("i", "o"),
        syllable_boundary_marker=SyllableBoundaryMarker.DIAERESIS,
    )
    assert scheme.apply("nio") == "nizh"


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


def test_apply_collapses_an_accidental_triple_letter_to_a_double():
    # Two adjacent /p/ tokens, one preceded by a short vowel (doubles to
    # "pp") and one not (stays plain "p") -- each rule is independently
    # correct, but landing next to each other would spell "ppp", which no
    # real orthography ever writes. apply() collapses any 3+ run down to 2.
    scheme = RomanizationScheme(
        rules=(
            RomanizationRule(ipa="e", latin="e"),
            RomanizationRule(ipa="p", latin="pp", preceding=("short_vowel",)),
            RomanizationRule(ipa="p", latin="p"),
        ),
        vowel_symbols=("e",),
        vowel_length=(("e", "short"),),
    )
    assert scheme.apply("epp") == "epp"  # sanity: the underlying rules alone would give "epp" + "p" = "eppp"


def test_apply_never_produces_three_identical_consecutive_letters():
    scheme = RomanizationScheme(
        rules=(
            RomanizationRule(ipa="a", latin="a"),
            RomanizationRule(ipa="p", latin="ppp"),  # deliberately pathological, to isolate the collapse itself
        ),
    )
    assert scheme.apply("ap") == "app"


# --- Weighted spelling alternatives (RomanizationRule.weight) ---


def _tied_scheme() -> RomanizationScheme:
    return RomanizationScheme(
        rules=(
            RomanizationRule(ipa="o", latin="o", weight=0.45),
            RomanizationRule(ipa="o", latin="au", weight=0.30),
            RomanizationRule(ipa="o", latin="eau", weight=0.25),
            RomanizationRule(ipa="k", latin="k"),  # untouched by this feature -- no tie
        ),
    )


def test_a_single_matching_rule_is_unaffected_by_weight():
    # "k" has no alternatives at all -- never ties, so its rule's default
    # weight=1.0 is simply never consulted.
    assert _tied_scheme().apply("k") == "k"


def test_tied_rules_produce_more_than_one_spelling_across_many_words():
    scheme = _tied_scheme()
    spellings = {scheme.apply(f"o{i}") for i in range(30)}
    # Each "o{i}" is a distinct ipa_text, so each gets its own independent
    # pick -- across 30 of them, more than one of the three real
    # alternatives should show up (each "o{i}" leaves the digit itself
    # unmapped/passed through, so compare just the mapped prefix).
    prefixes = {scheme.apply(f"o{i}")[: -len(str(i))] for i in range(30)}
    assert prefixes <= {"o", "au", "eau"}
    assert len(prefixes) > 1


def test_tied_rule_choice_is_reproducible_for_the_same_ipa_text():
    scheme = _tied_scheme()
    assert scheme.apply("omanic") == scheme.apply("omanic")


def test_tied_rule_choice_is_resolved_independently_per_token_position():
    # Two occurrences of the same tied symbol within one word are keyed
    # on token index, not just the symbol -- across many two-"o" words,
    # the pair of picks isn't always identical (would be, if the choice
    # were keyed on symbol alone rather than per-occurrence).
    scheme = _tied_scheme()
    pairs = {scheme.apply(f"o{'x' * i}o") for i in range(20)}
    assert len(pairs) > 1


def test_weight_is_irrelevant_when_only_one_rule_matches_a_position():
    # A symbol with alternatives, but conditioned such that only one can
    # ever match a given context -- no tie, so `weight` never comes into
    # play and the result is fully deterministic.
    scheme = RomanizationScheme(
        rules=(
            RomanizationRule(ipa="s", latin="ss", preceding=("vowel",), following=("vowel",), weight=0.7),
            RomanizationRule(ipa="s", latin="s"),
            RomanizationRule(ipa="a", latin="a"),
        ),
        vowel_symbols=("a",),
    )
    assert scheme.apply("sa") == "sa"  # word-initial -- only the unconditioned rule matches


def test_reform_detection_style_comparison_matches_when_the_candidate_set_is_unchanged():
    # Mirrors sound_change.py's own reform-detection logic: apply() called
    # twice on the same ipa_text against two schemes whose rules for the
    # relevant symbol are identical must agree -- otherwise a spelling
    # reform could be spuriously detected from independent re-rolls alone.
    scheme_a = _tied_scheme()
    scheme_b = _tied_scheme()
    assert scheme_a.apply("otherwise") == scheme_b.apply("otherwise")


# --- Joint spelling (JointSpelling: onset+nucleus / nucleus+coda) ---


def _joint_scheme(**kwargs) -> RomanizationScheme:
    return RomanizationScheme(
        rules=(
            RomanizationRule(ipa="m", latin="m"),
            RomanizationRule(ipa="w", latin="ou"),
            RomanizationRule(ipa="a", latin="a"),
            RomanizationRule(ipa="t", latin="t"),
        ),
        vowel_symbols=("a",),
        **kwargs,
    )


def test_onset_nucleus_joint_spelling_consumes_both_tokens():
    # The real bug this feature fixes: real French /w/+/a/ ("moi", roi,
    # voix) is "oi" as one joint unit, not /w/'s own "oi" plus /a/'s own
    # separate "a" appended after (which would wrongly give "moia").
    scheme = _joint_scheme(onset_nucleus_spellings=(JointSpelling(first="w", second="a", latin="oi"),))
    assert scheme.apply("mwa") == "moi"


def test_onset_nucleus_joint_spelling_is_a_no_op_for_other_pairs():
    scheme = _joint_scheme(onset_nucleus_spellings=(JointSpelling(first="w", second="a", latin="oi"),))
    assert scheme.apply("ma") == "ma"  # no /w/ at all -- ordinary per-symbol spelling


def test_nucleus_coda_joint_spelling_consumes_both_tokens():
    # The coda-side mirror -- no real content curates this yet, but the
    # mechanism itself is symmetric.
    scheme = _joint_scheme(nucleus_coda_spellings=(JointSpelling(first="a", second="t", latin="augh"),))
    assert scheme.apply("mat") == "maugh"


def test_onset_nucleus_takes_precedence_over_nucleus_coda_for_the_same_vowel():
    # A vowel with both a winning onset+nucleus claim (on its preceding
    # consonant) and its own nucleus+coda rule for its following coda
    # defers to the onset+nucleus claim -- the coda then gets its own
    # ordinary, un-consumed spelling.
    scheme = _joint_scheme(
        onset_nucleus_spellings=(JointSpelling(first="w", second="a", latin="oi"),),
        nucleus_coda_spellings=(JointSpelling(first="a", second="t", latin="augh"),),
    )
    assert scheme.apply("mwat") == "moit"


def test_joint_spelling_ties_resolve_via_the_same_weighted_pick():
    scheme = _joint_scheme(
        onset_nucleus_spellings=(
            JointSpelling(first="w", second="a", latin="oi", weight=0.5),
            JointSpelling(first="w", second="a", latin="wa", weight=0.5),
        )
    )
    spellings = {scheme.apply(f"mwa{i}")[1:-len(str(i))] for i in range(20)}
    assert spellings <= {"oi", "wa"}
    assert len(spellings) > 1


def test_joint_spelling_choice_is_reproducible_for_the_same_ipa_text():
    scheme = _joint_scheme(
        onset_nucleus_spellings=(
            JointSpelling(first="w", second="a", latin="oi", weight=0.5),
            JointSpelling(first="w", second="a", latin="wa", weight=0.5),
        )
    )
    assert scheme.apply("mwatherton") == scheme.apply("mwatherton")


def test_consumed_position_still_runs_its_own_tone_and_hiatus_logic():
    # A vowel consumed by a preceding onset+nucleus rule still gets its
    # own tone-mark deco appended after the joint spelling, rather than
    # the deco silently vanishing along with its own `latin`.
    scheme = RomanizationScheme(
        rules=(
            RomanizationRule(ipa="w", latin="ou"),
            RomanizationRule(ipa="a", latin="a"),
        ),
        vowel_symbols=("a",),
        onset_nucleus_spellings=(JointSpelling(first="w", second="a", latin="oi"),),
    )
    result = scheme.apply("wa" + COMBINING_ACUTE)
    assert result == unicodedata.normalize("NFC", "oi" + COMBINING_ACUTE)  # "oí" -- the tone mark still landed on the "i"


def test_no_joint_spellings_is_byte_identical_to_before_this_feature():
    scheme = _joint_scheme()
    assert scheme.apply("mwat") == "mouat"  # every symbol spelled independently, as before


_STRESS_RULES = (
    RomanizationRule(ipa="k", latin="k"),
    RomanizationRule(ipa="f", latin="f"),
    RomanizationRule(ipa="a", latin="a"),
    RomanizationRule(ipa="e", latin="e"),
)


def test_irregular_only_marking_uses_the_words_own_final_nucleus_not_just_its_coda():
    # Real Portuguese default stress ("final_unless_unstressed_vowel") is
    # penultimate only if the word ends in an unstressed a/e/o, final
    # otherwise -- both "ends in a/e/o" and "ends in i/u" alike have an
    # *empty* coda, so this check must read the word's own actual final
    # vowel, not just its coda, to predict the right default and decide
    # whether "irregular_only" marking is warranted.
    scheme = RomanizationScheme(
        rules=_STRESS_RULES, vowel_symbols=("a", "e"),
        stress_accent_marking="irregular_only", stress_pattern="final_unless_unstressed_vowel",
    )
    # "kasa" ends in unstressed "a" -> predicted default is penultimate
    # (the first syllable) -- actual stress lands there too, so this is
    # the predictable case and gets no written accent.
    assert scheme.apply(STRESS_MARK + "kasa") == "kasa"
    # "kafe" also ends in "e" (predicted penultimate, the first syllable)
    # but is actually stressed on its own final syllable -- a genuine
    # deviation from the predicted default, so it does get marked
    # (café-shaped).
    assert scheme.apply("ka" + STRESS_MARK + "fe") == "kafé"
