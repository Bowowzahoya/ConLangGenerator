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
"""The plain, unshifted keys on a standard US QWERTY layout a trigger
(see ``assign_keyboard_triggers``) is ever built from -- 26 letters, 10
digits, 10 punctuation keys, 46 single keys total, comfortable headroom
for every generated inventory seen in practice (~30-45 phonemes) even
before a multi-key romanization-derived sequence stretches that further.
A glyph that still can't get a trigger (a genuinely huge inventory, with
every single key already spoken for and no usable plain-ASCII spelling
left) simply has no keyboard binding at all (not reachable some other
way; not attempted here)."""


def assign_keyboard_triggers(script: InventedScript, romanization: RomanizationScheme) -> dict[int, str]:
    """Maps each glyph's own index to the literal string a user types to
    produce it -- three passes, each only filling in glyphs the previous
    one left unassigned, so a more specific/intuitive assignment always
    wins over a more generic one:

    1. **Identity.** A glyph whose own IPA symbol already *is* a single
       plain key (``"p"`` -> /p/, ``"a"`` -> /a/) is typed with that exact
       key -- strictly more intuitive than the old purely-positional
       scheme (where key "a" could end up bound to any phoneme at all),
       and the common case for most consonants/vowels in practice.
    2. **This language's own romanization**, for whatever identity left
       unassigned. ``RomanizationScheme.apply`` on just that one symbol
       (the same real spelling machinery ``keyboard_layout`` already
       calls for its own "romanization" column, not a separate static
       digraph table) -- when that spelling happens to be a plain,
       already-free, 2+ character sequence of ``KEYBOARD_KEYS``
       characters (a digraph-style language's "sh" for /ʃ/, "ng" for
       /ŋ/, ...), typing it produces this glyph. Adapts automatically to
       whichever of the three exotic-symbol styles this particular
       language actually rolled -- a diacritic-style language's "š"
       isn't plain ASCII, so it falls through to the next pass instead.
    3. **Positional fallback**, among whatever single keys are still
       free, in glyph order -- the same "nothing left" honesty the old
       ``keyboard_key_for_symbol_index`` already had, just applied only
       to whatever a glyph's own identity/romanization couldn't place.

    Every assigned trigger is unique and built only from ``KEYBOARD_KEYS``
    characters, so the frontend's own greedy longest-match typing never
    needs to break a tie. A glyph with no free key or romanization-
    derived sequence left (a genuinely huge inventory) simply has no
    trigger -- not forced into something that would collide."""
    triggers: dict[int, str] = {}
    used: set[str] = set()

    def claim(index: int, trigger: str) -> None:
        triggers[index] = trigger
        used.add(trigger)

    for i, glyph in enumerate(script.glyphs):
        if len(glyph.ipa) == 1 and glyph.ipa in KEYBOARD_KEYS and glyph.ipa not in used:
            claim(i, glyph.ipa)

    for i, glyph in enumerate(script.glyphs):
        if i in triggers:
            continue
        spelling = romanization.apply(glyph.ipa)
        if len(spelling) >= 2 and spelling not in used and all(ch in KEYBOARD_KEYS for ch in spelling):
            claim(i, spelling)

    free_keys = (k for k in KEYBOARD_KEYS if k not in used)
    for i, glyph in enumerate(script.glyphs):
        if i in triggers:
            continue
        key = next(free_keys, None)
        if key is None:
            continue
        claim(i, key)

    return triggers


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
    """One row per glyph that got a typing trigger assigned (see
    ``assign_keyboard_triggers``'s own docstring for why not every glyph
    necessarily does): the literal string typed to produce it (one plain
    key, or a short multi-key sequence), its own IPA symbol, its default
    (context-free) romanization -- ``RomanizationScheme.apply`` on just
    that one symbol, the same real spelling machinery a whole word
    already goes through -- and the codepoint the compiled font renders
    it at. The web UI's own Script tab builds both its reference legend
    and its live-typing transliteration from this one call, no
    per-keystroke round trip."""
    triggers = assign_keyboard_triggers(script, romanization)
    rows = []
    for i, glyph in enumerate(script.glyphs):
        trigger = triggers.get(i)
        if trigger is None:
            continue
        rows.append(
            {
                "trigger": trigger,
                "ipa": glyph.ipa,
                "romanization": romanization.apply(glyph.ipa),
                "codepoint": codepoint_for_symbol_index(i),
            }
        )
    return rows


__all__ = ["render_word", "describe_glyph", "keyboard_layout", "assign_keyboard_triggers", "KEYBOARD_KEYS"]
