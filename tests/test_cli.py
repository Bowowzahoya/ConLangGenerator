"""Tests for cli.main's own non-typer helper logic (the parts worth unit
testing directly, as opposed to the typer command wiring itself)."""

import pytest
import typer

from conlang_generator.cli.main import (
    SCRIPT_TRAIT_FIELDS,
    _merge_source_languages,
    _parse_seed_example,
    _parse_trait_overrides,
)
from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.script import SCRIPT_TRAIT_RANGE


def test_merge_source_languages_no_existing_defaults_new_entries_to_equal_weight():
    names, weights = _merge_source_languages((), (), ["French", "German"])
    assert names == ("French", "German")
    assert weights == (1.0, 1.0)


def test_merge_source_languages_applies_explicit_weight_suffix():
    names, weights = _merge_source_languages((), (), ["French:0.7", "German:0.3"])
    assert names == ("French", "German")
    assert weights == (0.7, 0.3)


def test_merge_source_languages_keeps_classifier_weight_for_a_bare_repeat():
    # The classifier already inferred French at weight 0.6 -- a bare CLI
    # repeat (no ":weight" suffix) must not silently reset it to 1.0.
    names, weights = _merge_source_languages(("French",), (0.6,), ["French"])
    assert names == ("French",)
    assert weights == (0.6,)


def test_merge_source_languages_explicit_cli_weight_overrides_classifier_weight():
    names, weights = _merge_source_languages(("French",), (0.6,), ["French:0.9"])
    assert names == ("French",)
    assert weights == (0.9,)


def test_merge_source_languages_appends_new_cli_names_after_existing():
    names, weights = _merge_source_languages(("Dutch",), (1.0,), ["German:0.4"])
    assert names == ("Dutch", "German")
    assert weights == (1.0, 0.4)


def test_merge_source_languages_rejects_a_non_numeric_weight():
    with pytest.raises(typer.Exit):
        _merge_source_languages((), (), ["French:not-a-number"])


def test_parse_trait_overrides_empty_list_is_a_no_op():
    assert _parse_trait_overrides([]) == {}


def test_parse_trait_overrides_parses_a_single_entry():
    assert _parse_trait_overrides(["altitude=-0.7"]) == {"altitude": -0.7}


def test_parse_trait_overrides_parses_multiple_entries():
    overrides = _parse_trait_overrides(["altitude=-0.7", "tone_sandhi=0.9"])
    assert overrides == {"altitude": -0.7, "tone_sandhi": 0.9}


def test_parse_trait_overrides_accepts_the_range_boundaries():
    assert _parse_trait_overrides(["altitude=-1.0", "tone_sandhi=1.0"]) == {"altitude": -1.0, "tone_sandhi": 1.0}


def test_parse_trait_overrides_last_entry_for_the_same_name_wins():
    assert _parse_trait_overrides(["altitude=0.5", "altitude=-0.9"]) == {"altitude": -0.9}


def test_parse_trait_overrides_rejects_an_unknown_trait_name():
    with pytest.raises(typer.Exit):
        _parse_trait_overrides(["not_a_trait=0.5"])


def test_parse_trait_overrides_rejects_a_value_outside_the_bipolar_range():
    with pytest.raises(typer.Exit):
        _parse_trait_overrides(["altitude=2.0"])
    with pytest.raises(typer.Exit):
        _parse_trait_overrides(["altitude=-2.0"])


def test_parse_trait_overrides_rejects_a_non_numeric_value():
    with pytest.raises(typer.Exit):
        _parse_trait_overrides(["altitude=abc"])


def test_parse_trait_overrides_rejects_an_entry_with_no_equals_sign():
    with pytest.raises(typer.Exit):
        _parse_trait_overrides(["altitude"])


def test_parse_trait_overrides_rejects_the_dedicated_strictness_flags_own_fields():
    # source_language_strictness/source_word_strictness already have their
    # own --strictness/--word-strictness flags -- one way to set each,
    # not two.
    with pytest.raises(typer.Exit):
        _parse_trait_overrides(["source_language_strictness=0.5"])
    with pytest.raises(typer.Exit):
        _parse_trait_overrides(["source_word_strictness=0.5"])


# --script-trait reuses _parse_trait_overrides against a second allowlist (SCRIPT_TRAIT_FIELDS,
# ScriptTraits' own 14 dials) and a different flag name for its own error messages -- these mirror
# the --trait tests above, against that allowlist instead. The real CLI call site also passes
# range_of=SCRIPT_TRAIT_RANGE.__getitem__ (most dials bipolar -1..1, a few unipolar 0..1) -- passed
# here too so these tests exercise the actual validation `--script-trait` uses, not the function's
# own bipolar-only default (which only `--trait`'s worldbuilding fields rely on).


def _parse_script_trait_overrides(entries):
    return _parse_trait_overrides(entries, SCRIPT_TRAIT_FIELDS, "--script-trait", range_of=SCRIPT_TRAIT_RANGE.__getitem__)


def test_parse_script_trait_overrides_empty_list_is_a_no_op():
    assert _parse_script_trait_overrides([]) == {}


def test_parse_script_trait_overrides_parses_a_single_entry():
    overrides = _parse_script_trait_overrides(["weight=0.7"])
    assert overrides == {"weight": 0.7}


def test_parse_script_trait_overrides_parses_multiple_entries():
    overrides = _parse_script_trait_overrides(["weight=0.7", "slant=-0.4"])
    assert overrides == {"weight": 0.7, "slant": -0.4}


def test_parse_script_trait_overrides_last_entry_for_the_same_name_wins():
    overrides = _parse_script_trait_overrides(["weight=0.5", "weight=-0.9"])
    assert overrides == {"weight": -0.9}


def test_parse_script_trait_overrides_rejects_an_unknown_name():
    with pytest.raises(typer.Exit):
        _parse_script_trait_overrides(["not_a_dial=0.5"])


def test_parse_script_trait_overrides_rejects_a_graded_trait_name_not_in_its_own_allowlist():
    # altitude is a GRADED_TRAIT_FIELDS name, not a ScriptTraits dial --
    # confirms the two allowlists are genuinely separate, not merged.
    with pytest.raises(typer.Exit):
        _parse_script_trait_overrides(["altitude=0.5"])


def test_parse_script_trait_overrides_rejects_a_value_outside_the_bipolar_range():
    with pytest.raises(typer.Exit):
        _parse_script_trait_overrides(["weight=2.0"])


def test_parse_script_trait_overrides_rejects_a_non_numeric_value():
    with pytest.raises(typer.Exit):
        _parse_script_trait_overrides(["weight=abc"])


def test_parse_script_trait_overrides_accepts_a_unipolar_dial_at_its_own_bounds():
    # stroke_contrast/regularity/dot_ornateness only run 0.0..1.0 -- both ends of their own range
    # must parse cleanly through the real range_of lookup.
    overrides = _parse_script_trait_overrides(["regularity=0.0", "stroke_contrast=1.0"])
    assert overrides == {"regularity": 0.0, "stroke_contrast": 1.0}


def test_parse_script_trait_overrides_rejects_a_negative_value_for_a_unipolar_dial():
    with pytest.raises(typer.Exit):
        _parse_script_trait_overrides(["regularity=-0.5"])


def test_parse_seed_example_gloss_form_only():
    example = _parse_seed_example("water=aqua")
    assert (example.gloss, example.form, example.ipa, example.pos) == ("water", "aqua", None, None)


def test_parse_seed_example_with_ipa():
    example = _parse_seed_example("water=aqua|akwa")
    assert (example.gloss, example.form, example.ipa, example.pos) == ("water", "aqua", "akwa", None)


def test_parse_seed_example_with_ipa_and_pos():
    example = _parse_seed_example("run=zim|zim|verb")
    assert (example.gloss, example.form, example.ipa, example.pos) == ("run", "zim", "zim", PartOfSpeech.VERB)


def test_parse_seed_example_with_pos_and_no_ipa():
    example = _parse_seed_example("run=zim||verb")
    assert (example.gloss, example.form, example.ipa, example.pos) == ("run", "zim", None, PartOfSpeech.VERB)


def test_parse_seed_example_rejects_an_unknown_pos():
    with pytest.raises(typer.Exit):
        _parse_seed_example("run=zim||notapos")


def test_parse_seed_example_rejects_missing_equals_sign():
    with pytest.raises(typer.Exit):
        _parse_seed_example("water")


def test_parse_seed_example_with_a_single_irregular_form():
    example = _parse_seed_example("run=zim|zim|verb|past:zanu")
    assert len(example.forms) == 1
    assert (example.forms[0].cell, example.forms[0].form, example.forms[0].ipa) == ("past", "zanu", None)


def test_parse_seed_example_with_an_irregular_forms_own_ipa():
    example = _parse_seed_example("run=zim|zim|verb|past:zanu:za.nu")
    assert example.forms[0].ipa == "za.nu"


def test_parse_seed_example_with_multiple_irregular_forms():
    example = _parse_seed_example("tall=bik|bik|adjective|comparative:biko;superlative:bikomo")
    assert [(f.cell, f.form) for f in example.forms] == [("comparative", "biko"), ("superlative", "bikomo")]


def test_parse_seed_example_rejects_a_form_cell_that_does_not_match_the_pos():
    with pytest.raises(typer.Exit):
        _parse_seed_example("run=zim|zim|verb|plural:zimu")
