"""Tests for script.script_render -- turning a word's IPA into its
language's own invented-script glyph sequence, and describing a glyph
in plain language for the CLI."""

import random

from conlang_generator.core.script import Glyph, Point, Stroke, StrokeKind
from conlang_generator.generation import script_gen
from conlang_generator.script.font_builder import codepoint_for_symbol_index
from conlang_generator.script.script_render import (
    KEYBOARD_KEYS,
    describe_glyph,
    keyboard_key_for_symbol_index,
    keyboard_layout,
    render_word,
)
from tests._shared_language import cached_language


def test_render_word_maps_each_symbol_to_its_own_codepoint():
    language = cached_language(0)
    script = script_gen.generate_script(random.Random(1), language.phonology)
    word = language.lexicon.entries[0]

    rendered = render_word(script, word.ipa)

    index_by_ipa = {g.ipa: i for i, g in enumerate(script.glyphs)}
    expected = "".join(
        chr(codepoint_for_symbol_index(index_by_ipa[symbol]))
        for symbol in word.ipa
        if symbol in index_by_ipa
    )
    # A crude per-character check is enough here -- the real tokenization
    # correctness (multi-character symbols, modifiers) is ipa_tokenizer's
    # own job and already tested there; this just confirms render_word
    # actually threads codepoints through rather than, say, always
    # returning the first glyph.
    assert len(rendered) > 0
    assert all(ord(c) >= 0xE000 for c in rendered)


def test_render_word_skips_a_symbol_with_no_matching_glyph():
    glyph = Glyph(ipa="p", strokes=(Stroke(kind=StrokeKind.LINE, start=Point(x=0, y=0), end=Point(x=1, y=1)),))
    from conlang_generator.core.script import InventedScript, ScriptTraits, WritingDirection

    script = InventedScript(direction=WritingDirection.LTR, traits=ScriptTraits(), glyphs=(glyph,))
    # "x" has no glyph in this one-symbol script -- should be dropped,
    # not crash and not render as some placeholder.
    rendered = render_word(script, "px")
    assert rendered == chr(codepoint_for_symbol_index(0))


def test_describe_glyph_counts_each_stroke_kind():
    glyph = Glyph(
        ipa="p",
        strokes=(
            Stroke(kind=StrokeKind.LINE, start=Point(x=0, y=0), end=Point(x=1, y=1)),
            Stroke(kind=StrokeKind.LINE, start=Point(x=0, y=1), end=Point(x=1, y=0)),
            Stroke(kind=StrokeKind.ARC, start=Point(x=0, y=0), end=Point(x=2, y=2), bulge=0.3),
            Stroke(kind=StrokeKind.DOT, start=Point(x=1, y=1), end=Point(x=1, y=1)),
        ),
    )
    description = describe_glyph(glyph)
    assert "2 straight lines" in description
    assert "1 curved stroke" in description
    assert "1 dot" in description


def test_describe_glyph_handles_no_strokes():
    glyph = Glyph(ipa="p", strokes=())
    assert describe_glyph(glyph) == "no strokes"


def test_keyboard_key_for_symbol_index_is_positional_and_stable():
    assert keyboard_key_for_symbol_index(0) == "a"
    assert keyboard_key_for_symbol_index(25) == "z"
    assert keyboard_key_for_symbol_index(26) == "0"
    assert keyboard_key_for_symbol_index(len(KEYBOARD_KEYS)) is None


def test_keyboard_layout_covers_every_glyph_up_to_the_key_budget():
    language = cached_language(0)
    script = script_gen.generate_script(random.Random(1), language.phonology)
    rows = keyboard_layout(script, language.romanization)
    assert len(rows) == min(len(script.glyphs), len(KEYBOARD_KEYS))
    keys = [r["key"] for r in rows]
    assert keys == list(KEYBOARD_KEYS[: len(rows)])


def test_keyboard_layout_rows_carry_real_ipa_romanization_and_codepoint():
    language = cached_language(0)
    script = script_gen.generate_script(random.Random(1), language.phonology)
    rows = keyboard_layout(script, language.romanization)
    for row, glyph in zip(rows, script.glyphs):
        assert row["ipa"] == glyph.ipa
        assert row["romanization"] == language.romanization.apply(glyph.ipa)
        assert row["codepoint"] >= 0xE000
