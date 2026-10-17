"""An invented writing system for a language -- one glyph per phoneme
(phase 1: a simple alphabet, consonants and vowels each getting their
own atomic glyph). Not every language gets one; it's an optional,
explicitly opt-in-or-inferred artifact (see ``core.traits.TraitProfile.
requested_own_script``/``core.spec.GenerationSpec.force_own_script``),
unlike ``romanization``, which every language always has.

Each ``Glyph`` is a small vector drawing -- a handful of ``Stroke``
primitives (straight lines, arcs, a dot) placed on a fixed grid --
deterministically generated from the language's own seed and biased by
``ScriptTraits``, the same "seeded procedural generation, not an ML
model" approach every other generator in this project already uses.
``generation/script_gen.py`` builds these; ``script/font_builder.py``
compiles a finished ``InventedScript`` into a real, installable font
file by expanding each stroke into a filled polygon (TrueType glyphs
are filled outlines, not stroked paths) via fontTools.

Forward-compatibility for later, harder writing-system types (not
implemented yet, but not precluded by this shape): every ``Glyph``
already carries named ``anchors`` (grid points) even though phase 1
never reads them -- a future abugida-style vowel modifier (Hindi-like)
attaches a second, smaller glyph to a base consonant's own anchor, and
a future syllable block (Hangul-like) composes several phoneme-glyphs
into one bounding box via the same anchors, neither needing a Glyph
redesign. A logographic system (Chinese-like, one glyph per *gloss*,
not per phoneme, with semantic/phonetic component composition) is
genuinely harder and not modeled here at all yet -- not claimed to be
solved, just not ruled out by this same stroke-primitive technique.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


def lerp(t: float, lo: float, hi: float) -> float:
    """``t`` in ``[-1.0, 1.0]`` (a ``ScriptTraits`` dial's own range) ->
    a value in ``[lo, hi]`` -- the shared reading both ``generation.
    script_gen`` (stroke topology) and ``script.font_builder``
    (rendering) use to turn a trait's bipolar float into a concrete
    generation/drawing parameter."""
    return lo + (t + 1.0) / 2.0 * (hi - lo)


class WritingDirection(str, Enum):
    LTR = "ltr"
    RTL = "rtl"
    TTB_LTR = "ttb_ltr"
    """Top-to-bottom, columns ordered left-to-right (Mongolian-style)."""
    TTB_RTL = "ttb_rtl"
    """Top-to-bottom, columns ordered right-to-left (classical Chinese/
    Japanese-style)."""
    BOUSTROPHEDON = "boustrophedon"
    """Alternating direction each line (early Greek-style) -- a display
    concern handled by the consumer (CLI text layout, the web UI's own
    CSS), not something a glyph's own shape needs to know about."""


class StrokeKind(str, Enum):
    LINE = "line"
    ARC = "arc"
    DOT = "dot"


class Point(BaseModel, frozen=True):
    """A coordinate on ``Glyph``'s own fixed grid (0-3 on each axis, an
    arbitrary but sufficient resolution for a handful of simple strokes
    -- not an em-square coordinate; ``script.font_builder`` does that
    scaling at build time)."""

    x: int = Field(ge=0, le=3)
    y: int = Field(ge=0, le=3)


class Stroke(BaseModel, frozen=True):
    ipa: str = ""
    """Unused by ``Stroke`` itself -- present only so a future per-stroke
    debug/description tool doesn't need a parallel structure. Left empty
    by every stroke ``generation.script_gen`` produces today."""
    kind: StrokeKind
    start: Point
    end: Point
    """For ``DOT``, equal to ``start`` (a single point, no extent)."""
    bulge: float = 0.0
    """How far an ``ARC`` stroke's own midpoint deviates from the
    straight line between ``start``/``end``, as a fraction of the
    stroke's own length (0.0 = a straight line, meaningless for
    ``LINE``/``DOT``). Signed: positive bulges to one side, negative to
    the other, so two arcs between the same two points can still look
    different."""


class Glyph(BaseModel, frozen=True):
    ipa: str
    strokes: tuple[Stroke, ...]
    anchors: dict[str, Point] = Field(default_factory=dict)
    """Named attachment points (``"top"``/``"bottom"``/``"left"``/
    ``"right"``, ...) for a later composite glyph (an abugida-style
    modifier, a syllable block) to hang a second glyph off of -- see this
    module's own docstring. Always empty in phase 1; a composer reading
    an empty dict should fall back to the glyph's own bounding box, not
    fail outright."""


class ScriptTraits(BaseModel, frozen=True):
    """Fifteen graded dials (bipolar, ``[-1.0, 1.0]``, same shape as
    ``core.traits.TraitProfile``) controlling the *style* the stroke
    generator draws every glyph in -- rolled once per language, seeded,
    by ``generation.script_gen.roll_script_traits``, not (yet) something
    the free-text prompt infers; see that function's own docstring for
    why. A positive value is the pole named first below, negative its
    opposite."""

    angularity: float = 0.0
    """+ sharp, straight lines, pointed corners; - smooth, curved, round joints."""
    stroke_contrast: float = 0.0
    """+ calligraphic, thick/thin width variation; - monoline, uniform width."""
    weight: float = 0.0
    """+ bold, heavy strokes; - thin, light strokes."""
    complexity: float = 0.0
    """+ ornate, many strokes per glyph; - minimal, 1-2 strokes per glyph."""
    connectivity: float = 0.0
    """+ cursive, glyphs join their neighbors; - disconnected, each glyph fully separate."""
    symmetry: float = 0.0
    """+ mirror-symmetric shapes; - asymmetric, irregular."""
    proportion: float = 0.0
    """+ wide, squat glyphs; - tall, narrow glyphs."""
    slant: float = 0.0
    """+ slanted, italic-like shear; - upright."""
    openness: float = 0.0
    """+ open, airy, lots of negative space; - closed, solid counters."""
    regularity: float = 0.0
    """+ geometric, ruler-and-compass precision; - organic, rustic, hand-drawn feel."""
    density: float = 0.0
    """+ tightly packed strokes; - loosely spaced strokes."""
    height_variance: float = 0.0
    """+ varied ascenders/descenders (like Latin lowercase); - uniform height (like Latin caps)."""
    diacritic_density: float = 0.0
    """+ many small attached marks (Arabic i'jam-dot-like); - few or none."""
    grid_alignment: float = 0.0
    """+ strict block/square alignment (Hangul-like); - freeform, variable-width letters."""
    terminal_style: float = 0.0
    """+ serif-like hooks/flourishes at stroke ends; - plain stroke ends."""


class InventedScript(BaseModel, frozen=True):
    direction: WritingDirection
    traits: ScriptTraits
    glyphs: tuple[Glyph, ...]
    """One per phoneme in the language's own ``phonology.consonants``/
    ``.vowels`` at the time this was generated -- see
    ``generation.script_gen.generate_script``. Glyph order is also this
    script's own codepoint-assignment order (``script.font_builder``
    assigns Private Use Area codepoints starting at U+E000 by position
    in this tuple, not from a separately persisted mapping)."""
