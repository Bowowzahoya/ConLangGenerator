"""Tests for webui.glossary -- the plain-language hover-tooltip content
for the Generate result's own grammar/trait badges."""

from conlang_generator.core.grammar import Alignment, MorphologicalType, WordOrder
from conlang_generator.core.traits import GRADED_TRAIT_FIELDS
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


def test_as_dict_has_the_three_top_level_sections():
    d = glossary.as_dict()
    assert set(d) == {"traits", "grammar", "simple"}
    assert d["traits"] is glossary.TRAIT_GLOSSARY
    assert d["grammar"] is glossary.GRAMMAR_GLOSSARY
    assert d["simple"] is glossary.SIMPLE_GLOSSARY
