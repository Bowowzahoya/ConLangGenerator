"""Tests for webui.glossary -- the plain-language click-to-popover
content for the Generate tab's own grammar/trait badges and Advanced
options."""

from conlang_generator.core.grammar import Alignment, MorphologicalType, WordOrder
from conlang_generator.core.romanization import (
    ExoticSymbolStyle,
    SyllableBoundaryMarker,
    ToneMarkingStrategy,
    VowelLengthStrategy,
)
from conlang_generator.core.script import ScriptTraits
from conlang_generator.core.traits import GRADED_TRAIT_FIELDS
from conlang_generator.generation.romanization_gen import ORTHOGRAPHY_STYLE_NAMES
from conlang_generator.webui import glossary


def test_every_graded_trait_field_has_a_bipolar_glossary_entry():
    for field in GRADED_TRAIT_FIELDS:
        entry = glossary.TRAIT_GLOSSARY[field]
        assert entry["kind"] == "bipolar"
        assert entry["summary"] and entry["positive"] and entry["negative"]


def test_the_two_strictness_dials_have_unipolar_glossary_entries():
    for field in ("source_language_strictness", "source_word_strictness"):
        entry = glossary.TRAIT_GLOSSARY[field]
        assert entry["kind"] == "unipolar"
        assert entry["summary"] and entry["low"] and entry["high"]


def test_trait_glossary_has_exactly_the_graded_fields_plus_the_two_dials():
    assert set(glossary.TRAIT_GLOSSARY) == set(GRADED_TRAIT_FIELDS) | {
        "source_language_strictness",
        "source_word_strictness",
    }


def test_every_script_trait_field_has_a_bipolar_glossary_entry():
    for field in ScriptTraits.model_fields:
        entry = glossary.SCRIPT_TRAIT_GLOSSARY[field]
        assert entry["kind"] == "bipolar"
        assert entry["summary"] and entry["positive"] and entry["negative"]


def test_script_trait_glossary_has_exactly_the_scripttraits_fields():
    assert set(glossary.SCRIPT_TRAIT_GLOSSARY) == set(ScriptTraits.model_fields)


def test_every_word_order_value_is_explained():
    gloss = glossary.GRAMMAR_GLOSSARY["word_order"]
    for order in WordOrder:
        assert order.value in gloss["values"] and gloss["values"][order.value]


def test_every_alignment_value_is_explained():
    gloss = glossary.GRAMMAR_GLOSSARY["alignment"]
    for alignment in Alignment:
        assert alignment.value in gloss["values"] and gloss["values"][alignment.value]


def test_every_morphological_type_value_is_explained():
    gloss = glossary.GRAMMAR_GLOSSARY["morphological_type"]
    for kind in MorphologicalType:
        assert kind.value in gloss["values"] and gloss["values"][kind.value]


def test_boolean_grammar_fields_explain_both_true_and_false():
    for field in ("has_articles", "has_overt_copula", "adjective_after_noun", "tonal"):
        gloss = glossary.GRAMMAR_GLOSSARY[field]
        assert gloss["values"]["true"] and gloss["values"]["false"]


def test_word_selection_and_foreign_names_explain_their_real_values():
    assert set(glossary.GRAMMAR_GLOSSARY["word_selection"]["values"]) == {"algorithmic", "llm"}
    assert set(glossary.GRAMMAR_GLOSSARY["foreign_names"]["values"]) == {"keep", "adapt"}


def test_as_dict_has_the_five_top_level_sections():
    d = glossary.as_dict()
    assert set(d) == {"traits", "script_traits", "grammar", "simple", "advanced_options"}
    assert d["traits"] is glossary.TRAIT_GLOSSARY
    assert d["script_traits"] is glossary.SCRIPT_TRAIT_GLOSSARY
    assert d["grammar"] is glossary.GRAMMAR_GLOSSARY
    assert d["simple"] is glossary.SIMPLE_GLOSSARY
    assert d["advanced_options"] is glossary.ADVANCED_OPTIONS_GLOSSARY


def test_every_advanced_option_checkbox_has_a_summary():
    for key in ("force_tonal", "allow_all_caps"):
        assert glossary.ADVANCED_OPTIONS_GLOSSARY[key]["summary"]
        assert "values" not in glossary.ADVANCED_OPTIONS_GLOSSARY[key]


def test_advanced_options_foreign_names_explains_all_three_real_values():
    # The Generate tab's own forward-looking select (including "auto"),
    # a distinct entry from GRAMMAR_GLOSSARY's own two-way resolved
    # "foreign_names" grammar badge.
    assert set(glossary.ADVANCED_OPTIONS_GLOSSARY["foreign_names"]["values"]) == {"auto", "keep", "adapt"}


def test_advanced_options_orthography_style_covers_every_named_preset():
    values = glossary.ADVANCED_OPTIONS_GLOSSARY["orthography_style"]["values"]
    assert set(values) == set(ORTHOGRAPHY_STYLE_NAMES)
    assert all(values.values())


def test_advanced_options_exotic_symbol_style_covers_every_enum_value():
    values = glossary.ADVANCED_OPTIONS_GLOSSARY["exotic_symbol_style"]["values"]
    assert set(values) == {m.value for m in ExoticSymbolStyle}


def test_advanced_options_vowel_length_style_covers_every_enum_value():
    values = glossary.ADVANCED_OPTIONS_GLOSSARY["vowel_length_style"]["values"]
    assert set(values) == {m.value for m in VowelLengthStrategy}


def test_advanced_options_tone_style_covers_every_enum_value():
    values = glossary.ADVANCED_OPTIONS_GLOSSARY["tone_style"]["values"]
    assert set(values) == {m.value for m in ToneMarkingStrategy}


def test_advanced_options_syllable_boundary_marker_covers_every_option_the_frontend_actually_sends():
    # /api/options sends `m.name.lower()`, not `m.value` -- they differ
    # for NONE/APOSTROPHE/HYPHEN (empty string/punctuation aren't usable
    # <option value> text), so the glossary must be keyed the same way
    # the frontend's own <select> options actually are.
    values = glossary.ADVANCED_OPTIONS_GLOSSARY["syllable_boundary_marker"]["values"]
    assert set(values) == {m.name.lower() for m in SyllableBoundaryMarker}


def test_advanced_options_short_vowel_doubling_and_gemination_have_no_values():
    # Plain booleans (true/false/unforced in the <select>) -- the select
    # itself already names the options, so only a summary is needed.
    for key in ("short_vowel_doubling", "consonant_gemination"):
        assert glossary.ADVANCED_OPTIONS_GLOSSARY[key]["summary"]
        assert "values" not in glossary.ADVANCED_OPTIONS_GLOSSARY[key]
