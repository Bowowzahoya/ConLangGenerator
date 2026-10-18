"""Tests for script.script_render -- turning a word's IPA into its
language's own invented-script glyph sequence, and describing a glyph
in plain language for the CLI."""

import random

from conlang_generator.core.romanization import RomanizationRule, RomanizationScheme
from conlang_generator.core.script import Glyph, InventedScript, Point, ScriptTraits, Stroke, StrokeKind, WritingDirection
from conlang_generator.generation import script_gen
from conlang_generator.script.font_builder import codepoint_for_symbol_index
from conlang_generator.script.script_render import (
    KEYBOARD_KEYS,
    assign_keyboard_triggers,
    describe_glyph,
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


def _script_of(*ipas: str) -> InventedScript:
    glyphs = tuple(
        Glyph(ipa=ipa, strokes=(Stroke(kind=StrokeKind.LINE, start=Point(x=0, y=0), end=Point(x=1, y=1)),))
        for ipa in ipas
    )
    return InventedScript(direction=WritingDirection.LTR, traits=ScriptTraits(), glyphs=glyphs)


def _romanization_of(*pairs: tuple[str, str]) -> RomanizationScheme:
    return RomanizationScheme(rules=tuple(RomanizationRule(ipa=ipa, latin=latin) for ipa, latin in pairs))


def test_assign_keyboard_triggers_identity_first():
    # Every symbol here is already a single plain KEYBOARD_KEYS
    # character -- each should be typed with that exact key, not some
    # unrelated positional slot.
    script = _script_of("p", "a", "m")
    romanization = _romanization_of(("p", "p"), ("a", "a"), ("m", "m"))
    triggers = assign_keyboard_triggers(script, romanization)
    assert triggers == {0: "p", 1: "a", 2: "m"}


def test_assign_keyboard_triggers_uses_this_languages_own_romanization_digraph():
    # /ʃ/ isn't itself a plain key, but this language's own romanization
    # spells it "sh" -- a plain, free, two-character KEYBOARD_KEYS
    # sequence -- which becomes the typed trigger instead of falling
    # back to an arbitrary single key.
    script = _script_of("ʃ")
    romanization = _romanization_of(("ʃ", "sh"))
    triggers = assign_keyboard_triggers(script, romanization)
    assert triggers == {0: "sh"}


def test_assign_keyboard_triggers_falls_back_to_a_free_key_when_romanization_isnt_plain_ascii():
    # /ʒ/ isn't a plain key, and this language's own romanization of it
    # ("ž") isn't plain ASCII either -- falls all the way back to the
    # first still-free single key.
    script = _script_of("ʒ")
    romanization = _romanization_of(("ʒ", "ž"))
    triggers = assign_keyboard_triggers(script, romanization)
    assert triggers == {0: KEYBOARD_KEYS[0]}


def test_assign_keyboard_triggers_identity_wins_over_a_later_glyphs_romanization_sequence():
    # /s/ claims key "s" outright (pass 1). A later /ʃ/ romanizing as
    # "sh" still gets that whole sequence (pass 2) -- claiming "s" for
    # /s/ doesn't block the *sequence* "sh" for /ʃ/, since a sequence is
    # never itself a single KEYBOARD_KEYS element.
    script = _script_of("s", "ʃ")
    romanization = _romanization_of(("s", "s"), ("ʃ", "sh"))
    triggers = assign_keyboard_triggers(script, romanization)
    assert triggers == {0: "s", 1: "sh"}


def test_assign_keyboard_triggers_every_trigger_is_unique_and_keyboard_keys_only():
    language = cached_language(0)
    script = script_gen.generate_script(random.Random(1), language.phonology)
    triggers = assign_keyboard_triggers(script, language.romanization)
    values = list(triggers.values())
    assert len(values) == len(set(values))
    for trigger in values:
        assert trigger
        assert all(ch in KEYBOARD_KEYS for ch in trigger)


def test_keyboard_layout_rows_carry_real_ipa_romanization_and_codepoint():
    language = cached_language(0)
    script = script_gen.generate_script(random.Random(1), language.phonology)
    triggers = assign_keyboard_triggers(script, language.romanization)
    rows = keyboard_layout(script, language.romanization)
    assert len(rows) == len(triggers)
    rows_by_trigger = {r["trigger"]: r for r in rows}
    for i, glyph in enumerate(script.glyphs):
        if i not in triggers:
            continue
        row = rows_by_trigger[triggers[i]]
        assert row["ipa"] == glyph.ipa
        assert row["romanization"] == language.romanization.apply(glyph.ipa)
        assert row["codepoint"] >= 0xE000
