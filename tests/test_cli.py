"""Tests for cli.main's own non-typer helper logic (the parts worth unit
testing directly, as opposed to the typer command wiring itself)."""

import pytest
import typer

from conlang_generator.cli.main import _merge_source_languages, _parse_trait_overrides


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
