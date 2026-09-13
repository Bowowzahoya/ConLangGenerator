"""Tests for cli.main's own non-typer helper logic (the parts worth unit
testing directly, as opposed to the typer command wiring itself)."""

import pytest
import typer

from conlang_generator.cli.main import _merge_source_languages


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
