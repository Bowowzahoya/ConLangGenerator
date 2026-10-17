"""Renders a word's own IPA as text in its language's invented script --
a string of Private Use Area codepoints, one per phoneme, ready to
display once ``font_builder.build_font``'s own compiled font is loaded.
"""

from __future__ import annotations

from conlang_generator.core.romanization import RomanizationScheme
from conlang_generator.core.script import Glyph, InventedScript, StrokeKind
from conlang_generator.generation import ipa_tokenizer
from conlang_generator.script.font_builder import codepoint_for_symbol_index

KEYBOARD_KEYS: tuple[str, ...] = (
    tuple("abcdefghijklmnopqrstuvwxyz") + tuple("0123456789") + ("-", "=", "[", "]", ";", "'", ",", ".", "/", "`")
)
"""The physical keys an invented script's glyphs are assigned to, in
order -- plain, unshifted keys on a standard US QWERTY layout (26
letters, 10 digits, 10 punctuation keys, 46 total), comfortable headroom
for every generated inventory seen in practice (~30-45 phonemes). A
language whose own inventory is larger than this runs out of keys --
its remaining phonemes simply have no keyboard binding at all (not
reachable some other way; not attempted here)."""


def keyboard_key_for_symbol_index(index: int) -> str | None:
    """The physical key ``script.glyphs[index]`` is typed with, by plain
    position -- the same "no separately stored mapping, derive it from
    the glyph's own index" approach ``font_builder.codepoint_for_symbol_
    index`` already uses for Private Use Area codepoints. ``None`` past
    the last available key."""
    return KEYBOARD_KEYS[index] if index < len(KEYBOARD_KEYS) else None


def render_word(script: InventedScript, ipa_word: str) -> str:
    """Tokenizes ``ipa_word`` into this script's own known symbols (the
    same ``ipa_tokenizer.symbols_only`` approach ``speech.articulation.
    word_inventory`` already uses) and maps each to its glyph's own
    codepoint, in order. A symbol with no matching glyph -- shouldn't
    happen for a word genuinely built from this language's own
    inventory, but a tone mark or a symbol added after this script was
    generated both reach this honestly -- is skipped rather than shown
    as a wrong or placeholder glyph."""
    index_by_ipa = {glyph.ipa: i for i, glyph in enumerate(script.glyphs)}
    symbols = ipa_tokenizer.symbols_only(ipa_word, tuple(index_by_ipa))
    codepoints = (
        codepoint_for_symbol_index(index_by_ipa[symbol]) for symbol in symbols if symbol in index_by_ipa
    )
    return "".join(chr(cp) for cp in codepoints)


def describe_glyph(glyph: Glyph) -> str:
    """A plain-language stroke-count summary, for `conlang script
    --sounds` -- the script-layer analogue of `speech.articulation.
    describe_consonant`/`describe_vowel`, though far less detailed: a
    glyph's own shape is already visible once the font is loaded, so
    this is only meant to orient a reader looking at raw terminal text,
    not to replace seeing it."""
    lines = sum(1 for s in glyph.strokes if s.kind is StrokeKind.LINE)
    arcs = sum(1 for s in glyph.strokes if s.kind is StrokeKind.ARC)
    dots = sum(1 for s in glyph.strokes if s.kind is StrokeKind.DOT)
    parts = []
    if lines:
        parts.append(f"{lines} straight line{'s' if lines != 1 else ''}")
    if arcs:
        parts.append(f"{arcs} curved stroke{'s' if arcs != 1 else ''}")
    if dots:
        parts.append(f"{dots} dot{'s' if dots != 1 else ''}")
    return ", ".join(parts) if parts else "no strokes"


def keyboard_layout(script: InventedScript, romanization: RomanizationScheme) -> list[dict]:
    """One row per glyph that got a key assignment (see ``KEYBOARD_KEYS``'s
    own docstring for why not every glyph necessarily does): the
    physical key that types it, its own IPA symbol, its default
    (context-free) romanization -- ``RomanizationScheme.apply`` on just
    that one symbol, the same real spelling machinery a whole word
    already goes through, not a separate lookup table -- and the
    codepoint the compiled font renders it at. The web UI's own Script
    tab builds both its reference legend and its live-typing
    transliteration from this one call, no per-keystroke round trip."""
    rows = []
    for i, glyph in enumerate(script.glyphs):
        key = keyboard_key_for_symbol_index(i)
        if key is None:
            continue
        rows.append(
            {
                "key": key,
                "ipa": glyph.ipa,
                "romanization": romanization.apply(glyph.ipa),
                "codepoint": codepoint_for_symbol_index(i),
            }
        )
    return rows


__all__ = ["render_word", "describe_glyph", "keyboard_layout", "keyboard_key_for_symbol_index", "KEYBOARD_KEYS"]
