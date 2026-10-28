"""Compiles an ``InventedScript`` into a real TTF via fontTools --
verified empirically against the real library (built a toy 3-glyph font,
round-tripped it with ``fontTools.ttLib.TTFont``, and rendered it in a
real browser through ``@font-face``) before writing this, not assumed
from documentation.

TrueType glyphs are *filled outlines*, not stroked paths -- there is no
native "draw a line of width W" primitive, so every ``Stroke`` gets
expanded into its own small filled polygon (a line becomes a rotated
rectangle/trapezoid, an arc a short chain of them following a sampled
curve, a dot a small regular polygon) before handing it to fontTools'
own glyph pen. Overlapping polygons within one glyph still render as a
single solid shape -- TrueType's default nonzero fill rule takes care of
that, no manual polygon-union step needed (confirmed in the same
experiment above).

Each phoneme's own glyph is assigned a Private Use Area codepoint
(U+E000 upward, by position in ``InventedScript.glyphs``) -- the
standard, collision-free way to ship an invented script as a real font;
see ``core.script.InventedScript.glyphs``'s own docstring.

Consumes 13 of ``ScriptTraits``' 18 dials (the rendering-time half; see
``generation.script_gen``'s own docstring for the stroke-topology half, and
``ornateness``'s own docstring for why it's read in *both* halves):
``weight``/``stroke_contrast`` (stroke width, and whether it tapers along
the stroke), ``slant`` (shear), ``proportion`` (horizontal scale),
``regularity`` (organic jitter, unipolar -- 0 = none, 1 = max), ``crookedness``
(a stroke tilts slightly off its own canonical angle, chain-propagated so
connected strokes never visibly disconnect), ``roundedness``/``roundedness_
extremity`` (corners -- both internal joints and a stroke sequence's own loose
ends -- smoothed into curves, applied *after* crookedness; ``roundedness`` is
occurrence, ``roundedness_extremity`` is how deep the cut goes; see
``_round_endpoints``'s own docstring), ``terminal_style`` (frequency of a
per-glyph terminal ornament -- a hook/swirl/foot/extended stroke, one of 10
presets, at one stroke-end of some letters), ``serif`` (a simple, fixed foot
shape attached to a genuine stroke terminal -- see its own docstring for how
it differs from a terminal ornament), ``ornateness`` (diacritic richness and
which terminal-ornament preset gets favored), and ``dot_ornateness`` (a dot's
own render style, split from ``ornateness`` above).
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import NamedTuple

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from conlang_generator.core.script import (
    Glyph,
    InventedScript,
    Point,
    Stroke,
    StrokeKind,
    WritingDirection,
    lerp,
    lerp01,
)

UPM = 1000
"""Units per em -- the standard TrueType working resolution."""

_LETTER_SCALE = 0.55
"""A glyph's own height/width fill this fraction of the em square, not the whole thing -- "regular
sized letters," per direct user feedback that the old full-em sizing looked oversized. Applied to both
grid axes, so a glyph's own height stays ``UPM * _LETTER_SCALE`` regardless of the rolled grid shape
(``grid_max_y`` only changes point *resolution* within that fixed height, never the height itself)."""

_ASCENT = 930
"""Raised from the old ``850`` alongside ``_DIACRITIC_GAP_FRACTION``'s own widening (round 8, direct
user feedback: "a blank space of 20% the size of the character") -- a "top"-slot diacritic's own
worst-case reach is now ``550 + 0.20*550 + 220 + 35 = 915`` em-units (see ``_DIACRITIC_GAP_FRACTION``'s
own docstring for that arithmetic in full), so ``_ASCENT`` keeps a comfortable margin above it. Purely
an ``hhea``/``OS2`` line-height metric (``build_font``'s own ``setupHorizontalHeader``/``setupOS2``
calls, confirmed the only two places this constant is read) -- never a hard clip bound on any
individual glyph's own outline, so raising it changes line-spacing hints only, not glyph geometry."""
_DESCENT = -250
_ARC_SAMPLES = 5
"""An arc stroke is polygon-approximated as this many straight segments
along a sampled quadratic curve, not a true smooth Bezier outline -- a
documented phase-1 simplification, not a claim of real curve rendering."""

_SIDE_BEARING = UPM * 0.1
"""Fixed left/right margin per glyph -- no longer derived from the removed ``density`` dial."""


def _stable_unit(seed_text: str) -> float:
    """A deterministic pseudo-random value in ``[-1.0, 1.0]``, derived
    from ``seed_text`` alone (never from RNG state) -- font-building is
    a pure function of the ``InventedScript`` data, so re-building the
    same script twice always produces byte-identical output."""
    digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
    return (digest[0] / 255.0) * 2.0 - 1.0


def _script_fingerprint(script: InventedScript) -> str:
    """A stable text fingerprint of the whole script's own data (traits, direction, grid shape) --
    used as the seed for decisions that must be consistent *across every glyph* (today: which single
    dot style a low-``ornateness`` script reuses everywhere) rather than per-glyph/per-stroke like
    every other ``_stable_unit`` call here. Still a pure function of ``InventedScript`` data alone, same
    rule this module's own docstring already holds everything else to -- never RNG state, never the
    original generation seed (not present on this object at all)."""
    return (
        f"{script.traits.model_dump()}:{script.direction}:{script.grid_max_x}:{script.grid_max_y}:"
        f"{script.diacritic_grid_max_x}:{script.diacritic_grid_max_y}"
    )


def _point_to_em(
    point: Point, jitter_seed: str, traits, grid_unit_x: float, grid_unit_y: float,
    offset_x: float = 0.0, offset_y: float = 0.0,
) -> tuple[float, float]:
    x = point.x * grid_unit_x
    y = point.y * grid_unit_y
    jitter_scale = lerp01(traits.regularity, 0.0, UPM * 0.035)
    x += _stable_unit(f"{jitter_seed}:x") * jitter_scale
    y += _stable_unit(f"{jitter_seed}:y") * jitter_scale
    x *= lerp(traits.proportion, 0.7, 1.3)
    x += y * lerp(traits.slant, -0.3, 0.3)
    return x + offset_x, y + offset_y


def _perpendicular(x0: float, y0: float, x1: float, y1: float, width: float) -> tuple[float, float]:
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length == 0:
        return 0.0, 0.0
    return -dy / length * (width / 2), dx / length * (width / 2)


def _quad(x0: float, y0: float, x1: float, y1: float, w0: float, w1: float) -> list[tuple[float, float]]:
    """A line segment of (possibly different) width at each end, expanded
    into its own filled quadrilateral -- the one shared primitive every
    stroke kind below is built from."""
    px0, py0 = _perpendicular(x0, y0, x1, y1, w0)
    px1, py1 = _perpendicular(x0, y0, x1, y1, w1)
    return [(x0 + px0, y0 + py0), (x1 + px1, y1 + py1), (x1 - px1, y1 - py1), (x0 - px0, y0 - py0)]


def _regular_polygon(cx: float, cy: float, radius: float, sides: int = 8) -> list[tuple[float, float]]:
    # The angle is negated (clockwise) to match `_quad`'s own winding --
    # TrueType's nonzero fill rule fills wherever contours' winding
    # numbers sum to nonzero, so two *overlapping* same-glyph contours
    # that wind in opposite directions cancel out in that overlap
    # instead of just unioning, punching a visible hole. A dot or a
    # `terminal_style` foot (both built from this function) sitting right
    # on top of a line/arc stroke's own `_quad` polygon is exactly that
    # overlap -- confirmed empirically (every glyph in a real generated
    # font had this exact mixed-winding signature) before fixing it here,
    # not assumed from reading the math alone.
    return [
        (cx + radius * math.cos(-2 * math.pi * i / sides), cy + radius * math.sin(-2 * math.pi * i / sides))
        for i in range(sides)
    ]


def _stroke_width(traits) -> float:
    return lerp(traits.weight, UPM * 0.025, UPM * 0.08)


_DOT_RADIUS = UPM * _LETTER_SCALE * 0.09
"""A fixed fraction of letter height, decoupled from stroke width -- direct user feedback that a
thin-weight script's dots were "currently very tiny," like a tittle should stay legible regardless of
how thin the rest of the script's strokes are."""


_DOT_STYLE_WEIGHTS_LOW = {"square": 0.38, "stroke": 0.38, "circle": 0.24}
_DOT_STYLE_WEIGHTS_HIGH = {"square": 0.30, "stroke": 0.30, "circle": 0.40}
"""The three dot styles' own selection weights at ``ornateness == 0`` vs. ``== 1`` -- low concentrates
on square/stroke ("more chance of stroke or dot," direct user phrasing), high is flatter with a slight
circle lean ("slightly more chance of circles"). ``_weighted_dot_style`` interpolates between them.
Circle's own low-``ornateness`` weight was raised from the original ``0.16`` -- not a bug fix (sampled
2000 times at ``ornateness=0.0``, the original weight reproduced almost exactly, ~15.25% circle), but
a usability one: at low ``ornateness`` a *whole script* shares one style roll (see ``_dot_polygons``'s
own ``use_per_dot``), so the original weight meant roughly 84% of scripts showed *zero* circles
anywhere, read by direct user feedback as "I never see a tiny circle" even though the mechanism was
working as specified."""


def _weighted_dot_style(unit_roll: float, ornateness: float) -> str:
    """``unit_roll`` in ``[0, 1]`` -> one of ``"square"``/``"stroke"``/``"circle"``, via weights
    lerped between ``_DOT_STYLE_WEIGHTS_LOW``/``_DOT_STYLE_WEIGHTS_HIGH`` by ``ornateness``."""
    cumulative = 0.0
    for style in ("square", "stroke", "circle"):
        cumulative += lerp01(ornateness, _DOT_STYLE_WEIGHTS_LOW[style], _DOT_STYLE_WEIGHTS_HIGH[style])
        if unit_roll < cumulative:
            return style
    return "circle"


def _dot_polygons(
    cx: float, cy: float, width: float, ornateness: float, seed_text: str, script_fingerprint: str,
) -> list[list[tuple[float, float]]]:
    """A dot renders as one of three styles -- a tiny square/diamond, a plain circle, or a brief bent
    diagonal stroke (Chinese-brush-dot style) -- chosen by a blend of "the whole script reuses one
    style" (``ornateness == 0``, direct user request: "low only one style of dots") and "every dot
    rolls independently" (``ornateness == 1``, "high randomly picking from all, leading to high
    diversity"): ``use_per_dot`` is itself a per-dot coin flip weighted by ``ornateness``; the losing
    case reuses one roll keyed off ``script_fingerprint`` (``_script_fingerprint``) instead of this
    dot's own seed, so every dot in the script agrees on it. Either way the *style* choice itself
    (``_weighted_dot_style``) also shifts with ``ornateness`` -- see that function's own docstring."""
    use_per_dot = (_stable_unit(f"{seed_text}:diversity") + 1.0) / 2.0 < ornateness
    style_seed = seed_text if use_per_dot else script_fingerprint
    style_roll = (_stable_unit(f"{style_seed}:dot-style") + 1.0) / 2.0
    style = _weighted_dot_style(style_roll, ornateness)
    if style == "circle":
        return [_regular_polygon(cx, cy, _DOT_RADIUS)]
    if style == "square":
        return [_regular_polygon(cx, cy, _DOT_RADIUS, sides=4)]
    sign = 1.0 if _stable_unit(f"{seed_text}:dir") >= 0 else -1.0
    half = _DOT_RADIUS * 0.9
    x0, y0 = cx - half * sign, cy + half * sign
    x1, y1 = cx + half * sign, cy - half * sign
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    pdx, pdy = _perpendicular(x0, y0, x1, y1, 1.0)
    length = math.hypot(x1 - x0, y1 - y0)
    bend_cx, bend_cy = mx + pdx * 0.25 * sign * length, my + pdy * 0.25 * sign * length
    points = []
    for i in range(_ARC_SAMPLES + 1):
        t = i / _ARC_SAMPLES
        sx = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * bend_cx + t**2 * x1
        sy = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * bend_cy + t**2 * y1
        points.append((sx, sy))
    w0, w1 = width * 0.8, width * 1.1
    polygons = []
    for i in range(len(points) - 1):
        t0, t1 = i / _ARC_SAMPLES, (i + 1) / _ARC_SAMPLES
        ww0, ww1 = w0 + (w1 - w0) * t0, w0 + (w1 - w0) * t1
        polygons.append(_quad(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1], ww0, ww1))
    return polygons


_SERIF_FLARE_FACTOR = 1.0
"""How much wider than the stem's own half-width the foot's own flat base extends -- continuing round
8's own lesson that a serif has to visibly flare past its own stroke to read as one at all (the un-
floored shape that preceded this one was checked to barely exceed the stroke's own silhouette)."""
_SERIF_DEPTH_FACTOR = 1.6
"""How far the foot extends past the stroke's own loose end, as a multiple of stroke width."""
_SERIF_BOW_FACTOR = 0.35
"""How far each side edge pinches inward (toward the foot's own centerline) at its own midpoint, as a
fraction of the flare half-width -- the "concave sides" directly requested."""


def _simple_serif_foot_polygon(
    ex: float, ey: float, dx: float, dy: float, width: float, stroke_key: str, serif: float,
) -> list[list[tuple[float, float]]]:
    """A single, fixed serif-foot shape planted at a genuine stroke terminal ``(ex, ey)``, extending in
    direction ``(dx, dy)`` (the stroke's own outward direction, continuing past its own tip, so the
    foot naturally reads as sitting "below" a downward-pointing end or "above" an upward one -- "at the
    bottom or top... of all ends" falls out of geometry here, not a separate rule). Round 9's full
    replacement for the old per-script ``SerifRule`` system (coverage/sides/shape/thickness rolled per
    orientation class) -- direct user feedback that version was both invisible in practice and more
    elaborate than the look called for: "let's first make a simple version." One flat per-end roll
    (``include_roll < serif``) decides whether this terminal gets a foot at all; at ``serif=1.0`` every
    qualifying terminal does ("all ends of continuous lines"), at ``0.0`` none do.

    Shape, in the stroke's own local frame at this end: the top two corners sit flush with the
    stroke's own existing half-width (so the foot reads as a continuation of the stem, not a separate
    shape bolted on); the bottom two corners flare to ``_SERIF_FLARE_FACTOR`` wider, joined by a
    straight base edge ("a simple triangle... straight at the bottom"); the two side edges are each a
    quadratic-Bezier-sampled curve bowed *inward* toward the centerline (``_SERIF_BOW_FACTOR``) rather
    than running straight -- "concave sides left and right" -- the same sampling technique
    ``_arc_polygons``/``_dot_polygons``'s own bent stroke already use, not a new curve primitive."""
    if serif <= 0.0:
        return []
    include_roll = (_stable_unit(f"{stroke_key}:serif-include") + 1.0) / 2.0
    if include_roll >= serif:
        return []

    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    px, py = -uy, ux  # unit perpendicular, same rotational sense as `_perpendicular`'s own convention

    stem_half = width / 2.0
    flare_half = width * _SERIF_FLARE_FACTOR
    depth = width * _SERIF_DEPTH_FACTOR
    bow = flare_half * _SERIF_BOW_FACTOR

    top_left = (ex - px * stem_half, ey - py * stem_half)
    top_right = (ex + px * stem_half, ey + py * stem_half)
    base_x, base_y = ex + ux * depth, ey + uy * depth
    bottom_left = (base_x - px * flare_half, base_y - py * flare_half)
    bottom_right = (base_x + px * flare_half, base_y + py * flare_half)

    def bowed_side(start: tuple[float, float], end: tuple[float, float], sign: float) -> list[tuple[float, float]]:
        mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        cx, cy = mx + px * bow * sign, my + py * bow * sign
        points = []
        for i in range(_ARC_SAMPLES + 1):
            t = i / _ARC_SAMPLES
            sx = (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * cx + t**2 * end[0]
            sy = (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * cy + t**2 * end[1]
            points.append((sx, sy))
        return points

    left_side = bowed_side(top_left, bottom_left, sign=1.0)
    right_side = bowed_side(top_right, bottom_right, sign=-1.0)
    # This order (not `left_side + reversed(right_side)`) matches `_quad`/`_regular_polygon`'s own
    # winding direction (confirmed by shoelace signed area) -- two *overlapping* same-glyph contours
    # winding oppositely cancel out under TrueType's nonzero fill rule instead of unioning, the same
    # real bug `_regular_polygon`'s own winding comment already documents fixing once.
    polygon = right_side + list(reversed(left_side))
    return [polygon]


def _arc_polygons(
    x0: float, y0: float, x1: float, y1: float, bulge: float, w0: float, w1: float,
) -> list[list[tuple[float, float]]]:
    """A quadratic-Bezier-sampled curve from ``(x0,y0)`` to ``(x1,y1)``, bulging perpendicular to the
    chord by ``bulge`` (a signed fraction of chord length) -- tapering width linearly from ``w0`` to
    ``w1`` across the sampled segments. Shared by ``StrokeKind.ARC`` rendering (the generation-time
    primitive, never actually produced by ``generation.script_gen`` today but still rendered correctly
    for forward-compatibility) and ``roundedness``'s own synthesized corner-rounding curves."""
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    pdx, pdy = _perpendicular(x0, y0, x1, y1, 1.0)
    length = math.hypot(x1 - x0, y1 - y0)
    cx, cy = mx + pdx * bulge * length, my + pdy * bulge * length
    points = []
    for i in range(_ARC_SAMPLES + 1):
        t = i / _ARC_SAMPLES
        sx = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t**2 * x1
        sy = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t**2 * y1
        points.append((sx, sy))
    polygons = []
    for i in range(len(points) - 1):
        t0, t1 = i / _ARC_SAMPLES, (i + 1) / _ARC_SAMPLES
        polygons.append(
            _quad(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1], w0 + (w1 - w0) * t0, w0 + (w1 - w0) * t1)
        )
    return polygons


def _bulge_through_point(x0: float, y0: float, x1: float, y1: float, cx: float, cy: float) -> float:
    """The signed ``bulge`` fraction (see ``_arc_polygons``) that makes the quadratic control point
    land as close as possible to ``(cx, cy)`` -- used by ``roundedness`` to curve a corner through
    (approximately) its own original vertex. Only the component of ``(cx,cy)`` perpendicular to the
    ``(x0,y0)``-``(x1,y1)`` chord can be represented at all (the ``bulge`` model has exactly one degree
    of freedom); any along-chord component is simply dropped -- a reasonable approximation for the
    roughly-symmetric corners this produces, not claimed exact."""
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length == 0:
        return 0.0
    ux, uy = -dy / length, dx / length
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    projection = (cx - mx) * ux + (cy - my) * uy
    return 2.0 * projection / length


def _stroke_polygons(
    stroke: Stroke, glyph_index: int | str, stroke_index: int, traits, grid_unit_x: float, grid_unit_y: float,
    script_fingerprint: str, offset_x: float = 0.0, offset_y: float = 0.0,
) -> list[list[tuple[float, float]]]:
    """Renders a ``DOT`` or ``ARC`` stroke -- ``LINE`` strokes no longer go through this function at
    all (see ``_render_scope``'s own chain-based handling for ``crookedness``/``roundedness``/serif)."""
    jitter_prefix = f"{glyph_index}:{stroke_index}"
    width = _stroke_width(traits)

    if stroke.kind is StrokeKind.DOT:
        cx, cy = _point_to_em(stroke.start, f"{jitter_prefix}:dot", traits, grid_unit_x, grid_unit_y, offset_x, offset_y)
        return _dot_polygons(cx, cy, width, traits.dot_ornateness, f"{jitter_prefix}:dot", script_fingerprint)

    # ARC -- a generation-time primitive generation.script_gen never actually produces today, kept
    # correct for forward-compatibility (see core.script.ScriptTraits.roundedness's own docstring).
    contrast = lerp01(traits.stroke_contrast, 0.0, 0.45)
    w_start, w_end = width * (1 + contrast), width * (1 - contrast)
    x0, y0 = _point_to_em(stroke.start, f"{jitter_prefix}:a", traits, grid_unit_x, grid_unit_y, offset_x, offset_y)
    x1, y1 = _point_to_em(stroke.end, f"{jitter_prefix}:b", traits, grid_unit_x, grid_unit_y, offset_x, offset_y)
    return _arc_polygons(x0, y0, x1, y1, stroke.bulge, w_start, w_end)


class OrnamentPreset(NamedTuple):
    name: str
    bend_degrees: float
    """Total turning angle of the ornament's own centerline, degrees -- ``0`` for a straight
    extension, up to ``540`` for `"swirl"`` (one and a half turns)."""
    length_factor: float
    """The ornament's own total centerline length, as a fraction of the stroke it's attached to's own
    rendered length -- most presets land in ``0.2..0.6`` (direct user request); ``short_extension``/
    ``long_extension`` deliberately exceed that ("a longer stroke extending beyond the normal size of
    the letters (Javanese)," direct user request from an earlier round -- only means something if
    it's allowed to exceed "normal" ornament size)."""
    closed: bool
    """Whether the ornament's own far end gets a small solid cap (a plain stroke tapering to a point
    otherwise) -- "closed"/"open" per the user's own Thai-hook vs. Щ-hook distinction."""
    width_factor: float
    """Multiplies the glyph's own base stroke width."""


_TERMINAL_ORNAMENT_PRESETS: tuple[OrnamentPreset, ...] = (
    OrnamentPreset("plain_foot", 0.0, 0.35, True, 1.3),
    OrnamentPreset("short_serif", 0.0, 0.25, True, 1.0),
    OrnamentPreset("closed_hook", 200.0, 0.45, True, 0.9),
    OrnamentPreset("open_hook", 120.0, 0.5, False, 0.85),
    OrnamentPreset("small_flare", 40.0, 0.3, False, 1.1),
    OrnamentPreset("rounded_bulb", 360.0, 0.35, True, 1.0),
    OrnamentPreset("short_extension", 0.0, 0.9, False, 0.8),
    OrnamentPreset("long_extension", 0.0, 1.4, False, 0.7),
    OrnamentPreset("swirl", 540.0, 0.55, True, 0.6),
    OrnamentPreset("double_hook", 240.0, 0.55, True, 0.9),
)
"""10 fixed terminal-ornament presets, ordered plain -> fancy (``_weighted_ornament_preset`` favors the
tail as ``ornateness`` rises) -- the user's own 5 named examples (foot/open hook/closed hook/swirl/
extended stroke) plus 5 more filling out the "fancy" end, each just a parameter tuple for one shared
drawing function (``_terminal_ornament_polygons``) rather than 10 bespoke hand-authored shapes. A
reasonable first pass, not claimed final -- tuned against a real rendered check, same as every other
new visual mechanic in this project. ``length_factor`` values are each a fraction of the attached
stroke's own rendered length (see ``OrnamentPreset.length_factor``'s own docstring) -- direct user
feedback that the whole system read as too tiny when scaled from a fixed, UPM-absolute reference
length instead."""


def _weighted_ornament_preset(unit_roll: float, ornateness: float) -> int:
    """``unit_roll`` in ``[0, 1]`` -> an index into ``_TERMINAL_ORNAMENT_PRESETS``. Weight for index
    ``i`` interpolates between "decreasing in ``i``" (``ornateness == 0``, favors ``plain_foot``) and
    "increasing in ``i``" (``ornateness == 1``, favors ``swirl``/``double_hook``) -- "higher ornateness
    should favor the more fancy of those 10... as well as more diversity," direct user phrasing (a
    flatter weight spread at high ``ornateness`` is itself more diverse than a sharply peaked one)."""
    n = len(_TERMINAL_ORNAMENT_PRESETS)
    weights = [lerp01(ornateness, n - i, i + 1) for i in range(n)]
    total = sum(weights)
    cumulative = 0.0
    for i, w in enumerate(weights):
        cumulative += w
        if unit_roll < cumulative / total:
            return i
    return n - 1


_TERMINAL_ORNAMENT_BUCKET_WEIGHTS = {
    "bottom": 0.40, "top": 0.28, "middle_left": 0.12, "middle_right": 0.12, "middle_middle": 0.08,
}
"""Positional bias for which stroke-endpoint candidate gets a terminal ornament, by *absolute*
em-space bucket (not direction-relative -- an individual glyph's own shape doesn't rotate with writing
direction) -- "slightly more chance on the bottom, then top, then middle left or right, then middle
middle," direct user phrasing, in that order."""


def _ornament_bucket(point: Point, grid_max_x: int, grid_max_y: int) -> str:
    if point.y == 0:
        return "bottom"
    if point.y == grid_max_y:
        return "top"
    if point.x * 2 < grid_max_x:
        return "middle_left"
    if point.x * 2 > grid_max_x:
        return "middle_right"
    return "middle_middle"


def _roll_terminal_ornaments(
    glyph: Glyph, glyph_index: int, traits, grid_max_x: int, grid_max_y: int,
    rounded_start: dict[int, bool] | None = None, rounded_end: dict[int, bool] | None = None,
) -> list[tuple[int, bool, int]]:
    """Rolls 0, 1, or (rarely) 2 terminal ornaments for this glyph's own ``LINE`` strokes -- once per
    *glyph*, not per stroke (``terminal_style`` sets the frequency; see ``ScriptTraits.terminal_style``
    's own docstring for why this is a separate, per-letter-occasional mechanic, distinct from
    ``serif``'s own pervasive, per-script rule). Candidates are classified into ``_ornament_bucket``
    position buckets using *grid* coordinates (not the jittered em-space position -- a small jitter
    should never flip which bucket a point reads as). ``rounded_start``/``rounded_end`` (from
    ``_render_scope``, which merges ``roundedness``'s own corner-rounding claims with "isn't a genuine
    degree-1 loose end at all," see ``_render_scope``'s own docstring) exclude whichever stroke-ends
    rounding already claimed -- a smoothed corner has no sharp terminus left for an ornament to sit on
    either -- *and* any point where another stroke actually touches, regardless of whether rounding
    fired there (direct user feedback: an ornament should "only be added to genuine ends," not where
    one stroke merely meets another). Returns ``(stroke_index, is_start, preset_index)`` triples;
    ``is_start`` picks which of that ``Stroke``'s own two endpoints."""
    rounded_start = rounded_start or {}
    rounded_end = rounded_end or {}
    candidates = [
        (i, is_start)
        for i, s in enumerate(glyph.strokes)
        if s.kind is StrokeKind.LINE
        for is_start in (True, False)
        if not (rounded_start.get(i, False) if is_start else rounded_end.get(i, False))
    ]
    if not candidates:
        return []
    count_roll = (_stable_unit(f"{glyph_index}:ornament-count") + 1.0) / 2.0
    p_two = lerp01(traits.terminal_style, 0.0, 0.08)
    p_one = lerp01(traits.terminal_style, 0.0, 0.6)
    if count_roll < p_two:
        count = 2
    elif count_roll < p_two + p_one:
        count = 1
    else:
        return []
    count = min(count, len(candidates))

    weights = [
        _TERMINAL_ORNAMENT_BUCKET_WEIGHTS[
            _ornament_bucket(glyph.strokes[i].start if is_start else glyph.strokes[i].end, grid_max_x, grid_max_y)
        ]
        for i, is_start in candidates
    ]
    chosen: list[tuple[int, bool, int]] = []
    chosen_indices: set[int] = set()
    for n in range(count):
        remaining = [(idx, w) for idx, w in enumerate(weights) if idx not in chosen_indices]
        remaining_total = sum(w for _, w in remaining)
        roll = (_stable_unit(f"{glyph_index}:ornament-pos:{n}") + 1.0) / 2.0 * remaining_total
        cumulative = 0.0
        pick = remaining[-1][0]
        for idx, w in remaining:
            cumulative += w
            if roll < cumulative:
                pick = idx
                break
        chosen_indices.add(pick)
        preset_roll = (_stable_unit(f"{glyph_index}:ornament-shape:{n}") + 1.0) / 2.0
        preset_index = _weighted_ornament_preset(preset_roll, traits.ornateness)
        stroke_index, is_start = candidates[pick]
        chosen.append((stroke_index, is_start, preset_index))
    return chosen


def _arc_points(
    x0: float, y0: float, dx: float, dy: float, radius: float, bend_rad: float, samples: int,
) -> list[tuple[float, float]]:
    """``samples + 1`` points along a true circular arc starting at ``(x0, y0)`` tangent to unit
    direction ``(dx, dy)``, turning a signed total angle ``bend_rad`` (positive = curl left/CCW,
    negative = right/CW) -- used for a terminal ornament's own hook/swirl shapes, which (unlike the
    existing ``ARC`` stroke/dot-stroke code) can bend well past a quadratic Bezier's own practical
    range."""
    sign = 1.0 if bend_rad >= 0 else -1.0
    nx, ny = -dy, dx
    cx, cy = x0 + sign * radius * nx, y0 + sign * radius * ny
    theta0 = math.atan2(y0 - cy, x0 - cx)
    return [
        (cx + radius * math.cos(theta0 + sign * (i / samples) * abs(bend_rad)),
         cy + radius * math.sin(theta0 + sign * (i / samples) * abs(bend_rad)))
        for i in range(samples + 1)
    ]


def _ornament_main_points(
    x0: float, y0: float, dx: float, dy: float, preset: OrnamentPreset, stroke_length: float,
) -> list[tuple[float, float]]:
    """The sampled centerline for one ornament segment -- a straight 2-point line for
    ``bend_degrees == 0``, else an ``_arc_points`` sample. Shared by the main ornament and (for
    ``"double_hook"``) its own secondary branch. ``stroke_length`` is the attached stroke's own
    rendered length -- ``preset.length_factor`` is a fraction of it, not a fixed absolute (see that
    field's own docstring)."""
    base_length = stroke_length * preset.length_factor
    if preset.bend_degrees == 0:
        return [(x0, y0), (x0 + dx * base_length, y0 + dy * base_length)]
    bend_rad = math.radians(preset.bend_degrees)
    radius = base_length / abs(bend_rad)
    samples = max(_ARC_SAMPLES, round(abs(preset.bend_degrees) / 30))
    return _arc_points(x0, y0, dx, dy, radius, bend_rad, samples)


def _taper_polygons(
    points: list[tuple[float, float]], width: float, width_factor: float, closed: bool,
) -> list[list[tuple[float, float]]]:
    n = len(points) - 1
    polygons = []
    for i in range(n):
        t0, t1 = i / n, (i + 1) / n
        w0 = width * width_factor * (1 - 0.3 * t0)
        w1 = width * width_factor if closed else width * width_factor * (1 - 0.3 * t1)
        polygons.append(_quad(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1], w0, w1))
    if closed:
        polygons.append(_regular_polygon(points[-1][0], points[-1][1], width * width_factor * 0.5))
    return polygons


def _terminal_ornament_polygons(
    x0: float, y0: float, dx: float, dy: float, width: float, preset: OrnamentPreset, seed_text: str,
    stroke_length: float,
) -> list[list[tuple[float, float]]]:
    """Draws ``preset`` starting at ``(x0, y0)``, continuing in unit direction ``(dx, dy)`` (the
    stroke's own direction at this endpoint, so the ornament reads as a natural continuation past the
    letter). The curl direction (left vs. right) is its own deterministic per-instance coin flip, not
    baked into the preset -- a hook should be able to face either way depending on which letter it
    lands on, not always identically. ``stroke_length`` is that same attached stroke's own rendered
    length (see ``OrnamentPreset.length_factor``'s own docstring -- the ornament scales relative to
    it, not to a fixed absolute)."""
    curl_sign = 1.0 if _stable_unit(f"{seed_text}:curl") >= 0 else -1.0
    signed_preset = preset._replace(bend_degrees=preset.bend_degrees * curl_sign)
    points = _ornament_main_points(x0, y0, dx, dy, signed_preset, stroke_length)
    polygons = _taper_polygons(points, width, preset.width_factor, preset.closed)
    if preset.name == "double_hook" and len(points) >= 3:
        branch_start = points[len(points) // 2]
        prev = points[len(points) // 2 - 1]
        bdx, bdy = branch_start[0] - prev[0], branch_start[1] - prev[1]
        blength = math.hypot(bdx, bdy) or 1.0
        branch_preset = signed_preset._replace(
            bend_degrees=-signed_preset.bend_degrees * 0.7, length_factor=preset.length_factor * 0.5,
        )
        branch_points = _ornament_main_points(
            branch_start[0], branch_start[1], bdx / blength, bdy / blength, branch_preset, stroke_length,
        )
        polygons.extend(_taper_polygons(branch_points, width, preset.width_factor * 0.8, preset.closed))
    return polygons


class _Component(NamedTuple):
    """One connected group of ``LINE`` strokes, by shared grid ``Point`` -- not list adjacency. See
    ``_build_connectivity``'s own docstring."""

    order: list[Point]
    """BFS discovery order, the component's own root (entry point) first."""
    root_stroke_index: int
    """The ``LINE`` stroke index whose own ``start`` became this component's root -- used only to seed
    the root's own canonical position, the same ``jitter_glyph_index:{stroke_index}`` convention every
    other jitter seed in this module already uses."""
    parent_edge: dict[Point, tuple[int, bool]]
    """Every non-root point's own discovering stroke -- ``(stroke_index, arrived_via_own_start)``. The
    root has no entry here."""
    closing_edges: list[int]
    """``LINE`` stroke indices in this component that are *not* a spanning-tree edge -- both their own
    endpoints were already reached some other way (a stroke that closes a loop, or one that attaches to
    an already-drawn shape rather than extending it)."""


def _build_connectivity(strokes: tuple[Stroke, ...]) -> list[_Component]:
    """Groups ``LINE`` strokes into connected components by shared grid ``Point`` -- *any* two strokes
    touching the same point are connected, not just strokes that happen to be list-consecutive with
    ``stroke.start == previous.end`` (the old ``_find_chains``'s own, narrower rule). Direct user
    feedback: "if they are connected by chance, they should count as actually connected" --
    ``generation.script_gen``'s own ``_decide_stroke`` can start a fresh, unchained stroke at a point an
    *earlier* stroke already used (a coincidental touch, e.g. a final stroke attached to an
    already-drawn loop to turn a P into an R), and the old renderer treated that exactly like two
    strokes that never touch at all -- fine at ``crookedness=0``/``roundedness=0`` (same raw point,
    same baseline render), but a visible gap the instant either dial perturbs endpoints independently.

    For each not-yet-visited root (the first ``LINE`` stroke's own ``start``, in list order -- same
    determinism precedent ``_crooked_component_endpoints`` keeps for "the component's own entry point
    stays canonical"), a breadth-first walk discovers every reachable point via *some* stroke, and
    records that stroke as this point's own one ``parent_edge``. A spanning tree over ``n`` points needs
    exactly ``n-1`` edges -- so once the walk finishes, any ``LINE`` stroke in this component that was
    never used to discover a new point is, by construction, a *closing* edge: both its own endpoints
    were already reached another way (a loop's own final side, or an attached stroke touching an
    already-placed shape). ``_crooked_component_endpoints`` treats tree edges and closing edges very
    differently -- see that function's own docstring."""
    adjacency: dict[Point, list[tuple[int, Point]]] = {}
    for i, stroke in enumerate(strokes):
        if stroke.kind is not StrokeKind.LINE:
            continue
        adjacency.setdefault(stroke.start, []).append((i, stroke.end))
        adjacency.setdefault(stroke.end, []).append((i, stroke.start))

    visited: set[Point] = set()
    tree_edges: set[int] = set()
    components: list[_Component] = []
    for root_stroke_index, stroke in enumerate(strokes):
        if stroke.kind is not StrokeKind.LINE or stroke.start in visited:
            continue
        root = stroke.start
        order = [root]
        parent_edge: dict[Point, tuple[int, bool]] = {}
        visited.add(root)
        queue = [root]
        head = 0
        while head < len(queue):
            point = queue[head]
            head += 1
            for edge_idx, other in adjacency.get(point, []):
                if other in visited:
                    continue
                visited.add(other)
                tree_edges.add(edge_idx)
                parent_edge[other] = (edge_idx, strokes[edge_idx].start == point)
                order.append(other)
                queue.append(other)
        component_points = set(order)
        closing_edges = [
            j for j, s in enumerate(strokes)
            if s.kind is StrokeKind.LINE and j not in tree_edges
            and s.start in component_points and s.end in component_points
        ]
        components.append(_Component(
            order=order, root_stroke_index=root_stroke_index, parent_edge=parent_edge, closing_edges=closing_edges,
        ))
    return components


_MIN_JOINT_ANGLE_DEGREES = 15.0
"""Forbid a crookedness-tilted stroke from folding back near-parallel to the one that fed it -- direct
user feedback that extreme crookedness could produce "really tiny angles that look ugly random and not
like anything that would exist in a real language." Measured as the interior angle between "back the
way the walk arrived" and the candidate tilted direction leaving a point; ``generation.script_gen``'s
own ``exclude_direction`` already keeps the *untilted* canonical angle from ever exactly retracing (a
zero-degree interior angle), so clamping only ever has to walk partway back from a rolled tilt toward
that already-safe canonical baseline, never all the way to zero."""


def _clamp_tilt_for_min_angle(canonical_angle: float, tilt_deg: float, arrival_angle: float) -> float:
    """The largest-magnitude tilt (same sign as ``tilt_deg``, shrunk toward 0 if needed) that keeps the
    interior angle between the incoming direction (``arrival_angle``) and the resulting outgoing
    direction at or above ``_MIN_JOINT_ANGLE_DEGREES`` -- see that constant's own docstring. A plain
    bisection (25 iterations, far past the precision this ever needs): the interior-angle function isn't
    algebraically trivial to invert directly, but is well-behaved between the untilted canonical angle
    (always safe, per that constant's own docstring) and the full rolled tilt."""
    forbidden = arrival_angle + math.pi

    def interior_angle_degrees(t_deg: float) -> float:
        angle = canonical_angle + math.radians(t_deg)
        diff = abs(((angle - forbidden + math.pi) % (2 * math.pi)) - math.pi)
        return math.degrees(diff)

    if interior_angle_degrees(tilt_deg) >= _MIN_JOINT_ANGLE_DEGREES:
        return tilt_deg
    if interior_angle_degrees(0.0) < _MIN_JOINT_ANGLE_DEGREES:
        return 0.0
    lo, hi = 0.0, tilt_deg
    for _ in range(25):
        mid = (lo + hi) / 2.0
        if interior_angle_degrees(mid) >= _MIN_JOINT_ANGLE_DEGREES:
            lo = mid
        else:
            hi = mid
    return lo


def _crooked_component_endpoints(
    strokes: tuple[Stroke, ...], component: _Component, traits, jitter_glyph_index: int | str,
    grid_unit_x: float, grid_unit_y: float, offset_x: float, offset_y: float,
) -> dict[int, tuple[float, float, float, float]]:
    """``crookedness`` (Part B): walks ``_build_connectivity``'s own spanning tree instead of a simple
    ordered chain. The component's own root gets its plain canonical+jittered position (nothing
    precedes it to inherit from, same precedent the old per-chain walk already set). Walking
    ``component.order``, each further point's position is ``parent_position + length * angle`` --
    ``length``/the untilted ``canonical_angle`` both read from the two points' own canonical (jittered)
    positions, direction-symmetric (works whether this point was discovered via its own stroke's
    ``start`` or ``end``); the tilt itself is the same per-edge seeded roll as before (a selection roll,
    then a uniform draw scaled by ``crookedness * 45`` degrees), now passed through
    ``_clamp_tilt_for_min_angle`` whenever the point being placed has a parent that is itself not the
    root (an actual incoming direction to measure a corner against -- the root's own direct children
    have nothing to retrace, so aren't clamped).

    Once every point has a position, every stroke in the component -- tree edge or
    ``component.closing_edges`` alike -- is read off by one uniform ``(*positions[stroke.start],
    *positions[stroke.end])`` lookup. A closing edge's own two points are therefore *already* both
    resolved by the time this runs, so it never gets its own independent tilt at all: it renders as the
    plain straight connector between wherever its two ends landed -- the direct fix for "that final
    stroke should not be... skewed away by crookedness" (and, symmetrically, why a closed loop's own
    closing stroke keeps the loop closed, whatever shape ``roundedness`` then turns its corners into)."""
    positions: dict[Point, tuple[float, float]] = {}
    arrival_angle: dict[Point, float] = {}

    root = component.order[0]
    positions[root] = _point_to_em(
        root, f"{jitter_glyph_index}:{component.root_stroke_index}:a", traits, grid_unit_x, grid_unit_y,
        offset_x, offset_y,
    )

    for point in component.order[1:]:
        edge_idx, forward = component.parent_edge[point]
        stroke = strokes[edge_idx]
        jitter_prefix = f"{jitter_glyph_index}:{edge_idx}"
        orig_start = _point_to_em(stroke.start, f"{jitter_prefix}:a", traits, grid_unit_x, grid_unit_y, offset_x, offset_y)
        orig_end = _point_to_em(stroke.end, f"{jitter_prefix}:b", traits, grid_unit_x, grid_unit_y, offset_x, offset_y)
        orig_parent, orig_child = (orig_start, orig_end) if forward else (orig_end, orig_start)
        parent_point = stroke.start if forward else stroke.end

        length = math.hypot(orig_child[0] - orig_parent[0], orig_child[1] - orig_parent[1])
        canonical_angle = math.atan2(orig_child[1] - orig_parent[1], orig_child[0] - orig_parent[0])
        select_roll = (_stable_unit(f"{jitter_prefix}:crook-select") + 1.0) / 2.0
        if select_roll < traits.crookedness:
            tilt_deg = _stable_unit(f"{jitter_prefix}:crook-angle") * traits.crookedness * 45.0
            if parent_point in arrival_angle:
                tilt_deg = _clamp_tilt_for_min_angle(canonical_angle, tilt_deg, arrival_angle[parent_point])
            angle = canonical_angle + math.radians(tilt_deg)
        else:
            angle = canonical_angle

        parent_pos = positions[parent_point]
        positions[point] = (parent_pos[0] + length * math.cos(angle), parent_pos[1] + length * math.sin(angle))
        arrival_angle[point] = angle

    component_strokes = {edge_idx for edge_idx, _ in component.parent_edge.values()} | set(component.closing_edges)
    return {
        idx: (*positions[strokes[idx].start], *positions[strokes[idx].end])
        for idx in component_strokes
    }


_ROUNDING_SAFETY_CEILING = 0.9
"""Never let a single stroke's own two end-truncations (one from each side -- possible when both its
own loose end and its adjacent joint get rounded, or on an isolated 1-stroke component where both loose
ends do) sum past this fraction of its own length -- a plain, direct guard against a zero-or-negative-
length remnant. The user's own spec describes each side's rounding independently and doesn't need to
address this interaction, since it only ever arises from two *different* decisions both landing on one
stroke."""


def _virtual_neighbor_direction(
    dir_x: float, dir_y: float, is_isolated: bool, random_key: str, roundedness: float,
) -> tuple[float, float]:
    """The direction a loose end's own replacement tail bends from (see ``_round_endpoints``) --
    continuing the stroke's own forward direction verbatim when its other end is shared with something
    else ("continue the bend of the bend after it," read as: keep the directional flow the loose end's
    own neighbor is already committed to, rather than introducing an unrelated new heading), or that
    same direction plus a random offset when ``is_isolated`` (both of this stroke's own ends are
    unshared -- "if it is... a single straight stroke... random direction within the 2x2 frame, with
    1.0 meaning 90 degrees")."""
    angle = math.atan2(dir_y, dir_x)
    if is_isolated:
        offset_deg = _stable_unit(random_key) * roundedness * 90.0
        angle += math.radians(offset_deg)
    return math.cos(angle), math.sin(angle)


def _point_touch_counts(strokes: tuple[Stroke, ...]) -> dict[Point, int]:
    """How many ``LINE`` stroke-ends touch each grid ``Point`` -- degree 1 is a true loose end, 2 a
    normal joint, 3+ a branch point (see ``_round_endpoints``'s own docstring for the full
    classification). Used by ``_render_scope`` to gate serif/terminal-ornament attachment on "is this
    a genuine terminus" rather than only "did roundedness happen to claim it" -- a structural question,
    independent of ``traits.roundedness``'s own value or roll."""
    counts: dict[Point, int] = {}
    for stroke in strokes:
        if stroke.kind is not StrokeKind.LINE:
            continue
        counts[stroke.start] = counts.get(stroke.start, 0) + 1
        counts[stroke.end] = counts.get(stroke.end, 0) + 1
    return counts


def _triangle_long_side_corners(
    strokes: tuple[Stroke, ...], crooked: dict[int, tuple[float, float, float, float]],
    touches: dict[Point, list[tuple[int, bool]]],
) -> set[Point]:
    """Every point that is one of the two corners at the ends of a 3-stroke closed loop's own
    *longest* side -- direct user feedback: "triangles with high roundness become a weird egg shape...
    the angles on either side of the long side of a triangle should always stay sharp." Detected purely
    structurally: three degree-2 points, each pair directly joined by a ``LINE`` stroke (independent of
    ``_build_connectivity``'s own tree/closing-edge split, a different concern -- crookedness topology,
    not which corners round). The third ("apex") corner, opposite the longest side, is deliberately
    left out -- a triangle can still round at its own tip without losing its base and collapsing
    toward an ellipse."""
    def neighbors(point: Point) -> list[Point]:
        result = []
        for idx, is_start in touches.get(point, []):
            stroke = strokes[idx]
            result.append(stroke.end if is_start else stroke.start)
        return result

    def position(point: Point) -> tuple[float, float]:
        idx, is_start = touches[point][0]
        x0, y0, x1, y1 = crooked[idx]
        return (x0, y0) if is_start else (x1, y1)

    excluded: set[Point] = set()
    seen: set[frozenset] = set()
    for p, touch_list in touches.items():
        if len(touch_list) != 2:
            continue
        a, b = neighbors(p)
        if len(touches.get(a, [])) != 2 or len(touches.get(b, [])) != 2:
            continue
        if b not in neighbors(a):
            continue
        triangle = frozenset({p, a, b})
        if triangle in seen:
            continue
        seen.add(triangle)
        px, py = position(p)
        ax, ay = position(a)
        bx, by = position(b)
        side_pa = math.hypot(ax - px, ay - py)
        side_pb = math.hypot(bx - px, by - py)
        side_ab = math.hypot(bx - ax, by - ay)
        longest = max(side_pa, side_pb, side_ab)
        if longest == side_ab:
            excluded |= {a, b}
        elif longest == side_pa:
            excluded |= {p, a}
        else:
            excluded |= {p, b}
    return excluded


def _round_endpoints(
    strokes: tuple[Stroke, ...], crooked: dict[int, tuple[float, float, float, float]], traits,
    jitter_glyph_index: int | str,
) -> tuple[
    dict[int, tuple[float, float, float, float]], list[tuple[float, float, float, float, float]],
    dict[int, bool], dict[int, bool],
]:
    """``roundedness`` (Part C), keyed by grid-point *degree* (how many ``LINE`` stroke-ends touch it)
    instead of list adjacency -- a single pass over the whole scope's own strokes, not per-component
    (a point's degree already fully determines whether, and how, it rounds, and two different
    components can never share a point by definition).

    - **Degree 1** (a true loose end): the length-preserving bend described below.
    - **Degree 2** (a normal joint, however its two touching edges happen to meet): the existing
      two-sided joint math, generalized to whichever side of each edge actually meets this point --
      fires identically whether the two edges are simple chain-adjacent or a stroke attached to an
      already-drawn shape (a P's own loop plus the stroke that turns it into an R, or a closed loop's
      own final corner).
    - **Degree 3+** (a branch point): left alone entirely -- no truncation, no rounding, stays at its
      resolved (post-crookedness) position. A deliberate, flagged scope limit: three-or-more strokes
      meeting at one point is rare on this project's own tiny grids, and leaving it sharp is a safe
      default rather than a more elaborate multi-way corner model.

    Loose-end geometry, fixed per direct user feedback ("that was not my intention, I just meant it to
    turn away at an angle, but not become longer"): the old implementation placed the bend's own far
    point on a *virtual* stroke the same length as the real one, past the stroke's own original
    endpoint by up to half its own length. The new far point is the truncation point plus ``f *
    stroke_length`` along the chosen direction instead -- a replacement tail exactly as long as the
    straight portion it replaces, so turning away never reaches further than the original stroke did.

    Returns ``(segments, arcs, rounded_start, rounded_end)`` -- see the old ``_round_chain``'s own
    return-value shape (unchanged): ``segments`` is each stroke's own final (possibly truncated)
    ``(x0, y0, x1, y1)``; ``arcs`` is a list of ``(x0, y0, x1, y1, bulge)`` curves to additionally
    render; ``rounded_start``/``rounded_end`` flag which stroke-ends rounding claimed, for serif/
    terminal-ornament attachment to skip.

    ``roundedness``/``roundedness_extremity`` (round 9 split, direct user request: "a separate trait
    for extremeness of rounding, and for occurence of rounding") are deliberately read for two
    different things below -- ``roundedness`` alone decides *whether* a given point rounds at all
    (``selected()``), ``roundedness_extremity`` alone decides *how deep* the cut goes once it's
    selected (``f`` below, and the random bend-angle magnitude for an isolated loose end)."""
    f = traits.roundedness_extremity * 0.5

    touches: dict[Point, list[tuple[int, bool]]] = {}
    for idx, stroke in enumerate(strokes):
        if stroke.kind is not StrokeKind.LINE:
            continue
        touches.setdefault(stroke.start, []).append((idx, True))
        touches.setdefault(stroke.end, []).append((idx, False))

    def selected(key: str) -> bool:
        if traits.roundedness <= 0.0:
            return False
        roll = (_stable_unit(f"{key}:round-select") + 1.0) / 2.0
        return roll < traits.roundedness

    rounded_start: dict[int, bool] = {idx: False for idx, s in enumerate(strokes) if s.kind is StrokeKind.LINE}
    rounded_end: dict[int, bool] = {idx: False for idx, s in enumerate(strokes) if s.kind is StrokeKind.LINE}

    def point_key(p: Point) -> str:
        return f"{jitter_glyph_index}:point:{p.x},{p.y}"

    joints = [(p, t[0], t[1]) for p, t in touches.items() if len(t) == 2]
    loose_ends = [(p, t[0][0], t[0][1]) for p, t in touches.items() if len(t) == 1]
    joint_selected = {p: selected(f"{point_key(p)}:joint") for p, _, _ in joints}
    loose_selected = {p: selected(f"{point_key(p)}:loose") for p, _, _ in loose_ends}

    # Direct user feedback: a triangle's own longest side must always stay sharp at both its own
    # corners, however roundedness/roundedness_extremity would otherwise have rolled -- see
    # `_triangle_long_side_corners`'s own docstring.
    for point in _triangle_long_side_corners(strokes, crooked, touches):
        joint_selected[point] = False

    for point, (idx_a, start_a), (idx_b, start_b) in joints:
        if joint_selected[point]:
            rounded_start[idx_a] = rounded_start[idx_a] or start_a
            rounded_end[idx_a] = rounded_end[idx_a] or not start_a
            rounded_start[idx_b] = rounded_start[idx_b] or start_b
            rounded_end[idx_b] = rounded_end[idx_b] or not start_b
    for point, idx, is_start in loose_ends:
        if loose_selected[point]:
            if is_start:
                rounded_start[idx] = True
            else:
                rounded_end[idx] = True

    stroke_fraction: dict[int, float] = {}
    for idx, stroke in enumerate(strokes):
        if stroke.kind is not StrokeKind.LINE:
            continue
        both = rounded_start[idx] and rounded_end[idx]
        stroke_fraction[idx] = min(f, 0.45) if both and 2 * f > _ROUNDING_SAFETY_CEILING else f

    def side_point(idx: int, is_start_side: bool, fraction: float) -> tuple[float, float]:
        x0, y0, x1, y1 = crooked[idx]
        if is_start_side:
            return x0 + (x1 - x0) * fraction, y0 + (y1 - y0) * fraction
        return x0 + (x1 - x0) * (1 - fraction), y0 + (y1 - y0) * (1 - fraction)

    arcs: list[tuple[float, float, float, float, float]] = []

    for point, (idx_a, start_a), (idx_b, start_b) in joints:
        if not joint_selected[point]:
            continue
        fa, fb = stroke_fraction[idx_a], stroke_fraction[idx_b]
        p1x, p1y = side_point(idx_a, start_a, fa)
        p2x, p2y = side_point(idx_b, start_b, fb)
        cx0, cy0, cx1, cy1 = crooked[idx_a]
        corner_x, corner_y = (cx0, cy0) if start_a else (cx1, cy1)
        bulge = _bulge_through_point(p1x, p1y, p2x, p2y, corner_x, corner_y)
        arcs.append((p1x, p1y, p2x, p2y, bulge))

    for point, idx, is_start in loose_ends:
        if not loose_selected[point]:
            continue
        stroke = strokes[idx]
        other_point = stroke.end if is_start else stroke.start
        is_isolated = len(touches[other_point]) == 1
        fraction = stroke_fraction[idx]
        x0, y0, x1, y1 = crooked[idx]
        length = math.hypot(x1 - x0, y1 - y0) or 1.0
        tail_length = fraction * length
        truncation_x, truncation_y = side_point(idx, is_start, fraction)
        vdx, vdy = _virtual_neighbor_direction(
            x1 - x0, y1 - y0, is_isolated,
            f"{jitter_glyph_index}:{idx}:{'start' if is_start else 'end'}:end-angle",
            traits.roundedness_extremity,
        )
        sign = -1.0 if is_start else 1.0
        tip_x, tip_y = truncation_x + sign * tail_length * vdx, truncation_y + sign * tail_length * vdy
        loose_x, loose_y = (x0, y0) if is_start else (x1, y1)
        bulge = _bulge_through_point(truncation_x, truncation_y, tip_x, tip_y, loose_x, loose_y)
        arcs.append((truncation_x, truncation_y, tip_x, tip_y, bulge))

    segments: dict[int, tuple[float, float, float, float]] = {}
    for idx, stroke in enumerate(strokes):
        if stroke.kind is not StrokeKind.LINE:
            continue
        sx0, sy0, sx1, sy1 = crooked[idx]
        fa = stroke_fraction[idx] if rounded_start[idx] else 0.0
        fb = stroke_fraction[idx] if rounded_end[idx] else 0.0
        nx0, ny0 = sx0 + (sx1 - sx0) * fa, sy0 + (sy1 - sy0) * fa
        nx1, ny1 = sx1 - (sx1 - sx0) * fb, sy1 - (sy1 - sy0) * fb
        segments[idx] = (nx0, ny0, nx1, ny1)

    return segments, arcs, rounded_start, rounded_end


def _render_scope(
    strokes: tuple[Stroke, ...], traits, jitter_glyph_index: int | str, grid_unit_x: float, grid_unit_y: float,
    offset_x: float, offset_y: float, script_fingerprint: str,
) -> tuple[list[list[tuple[float, float]]], list[float], dict[int, bool], dict[int, bool], dict[int, tuple[float, float, float, float]]]:
    """All polygons for one glyph-or-diacritic *scope*'s own strokes (a main glyph's own ``glyph.
    strokes``, or one diacritic's own ``diac.strokes``) -- ``DOT``/``ARC`` via the unchanged per-stroke
    ``_stroke_polygons`` path, ``LINE`` strokes grouped into connected components (``_build_
    connectivity``) and run through ``crookedness`` (``_crooked_component_endpoints``) then
    ``roundedness`` (``_round_endpoints``, one global pass over every component's own output), with
    serif attachment skipping whichever stroke-end rounding claimed, *and* any point that isn't a
    genuine degree-1 loose end at all (``_point_touch_counts`` -- direct user feedback: a terminal
    ornament or serif was appearing where one stroke merely touched another, e.g. a P's own loop plus
    the stroke that turns it into an R, which is a structural joint regardless of whether
    ``roundedness`` happened to round it). Returns ``(polygons, xs, rounded_start, rounded_end,
    segments)`` -- ``xs`` is every x-coordinate touched (``_build_glyph_outline``'s own advance-width
    extent is computed from this directly); the last three are only meaningful for ``LINE`` strokes and
    are what the main glyph's own terminal-ornament roll needs. Despite the name (kept for the return
    shape's own continuity with ``_round_endpoints``), ``rounded_start``/``rounded_end`` here mean
    "not available for serif/terminal-ornament attachment" -- a strict superset of "rounding claimed
    this end"."""
    polygons: list[list[tuple[float, float]]] = []
    xs: list[float] = []
    width = _stroke_width(traits)
    contrast = lerp01(traits.stroke_contrast, 0.0, 0.45)
    w_start, w_end = width * (1 + contrast), width * (1 - contrast)

    crooked: dict[int, tuple[float, float, float, float]] = {}
    for component in _build_connectivity(strokes):
        crooked.update(
            _crooked_component_endpoints(
                strokes, component, traits, jitter_glyph_index, grid_unit_x, grid_unit_y, offset_x, offset_y,
            )
        )
    segments, arcs, rounded_start, rounded_end = _round_endpoints(strokes, crooked, traits, jitter_glyph_index)

    touch_counts = _point_touch_counts(strokes)
    for idx, stroke in enumerate(strokes):
        if stroke.kind is not StrokeKind.LINE:
            continue
        if touch_counts.get(stroke.start, 0) != 1:
            rounded_start[idx] = True
        if touch_counts.get(stroke.end, 0) != 1:
            rounded_end[idx] = True

    for idx, stroke in enumerate(strokes):
        if stroke.kind is not StrokeKind.LINE:
            continue
        x0, y0, x1, y1 = segments[idx]
        cx0, cy0, cx1, cy1 = crooked[idx]
        full_length = math.hypot(cx1 - cx0, cy1 - cy0) or 1.0
        t0 = math.hypot(x0 - cx0, y0 - cy0) / full_length
        t1 = 1.0 - math.hypot(cx1 - x1, cy1 - y1) / full_length
        sw0 = w_start + (w_end - w_start) * t0
        sw1 = w_start + (w_end - w_start) * t1
        polygons.append(_quad(x0, y0, x1, y1, sw0, sw1))
        xs.extend([x0, x1])
        if not rounded_start[idx]:
            polygons.extend(
                _simple_serif_foot_polygon(
                    x0, y0, x0 - x1, y0 - y1, width, f"{jitter_glyph_index}:{idx}:start", traits.serif,
                )
            )
        if not rounded_end[idx]:
            polygons.extend(
                _simple_serif_foot_polygon(
                    x1, y1, x1 - x0, y1 - y0, width, f"{jitter_glyph_index}:{idx}:end", traits.serif,
                )
            )
    for ax0, ay0, ax1, ay1, bulge in arcs:
        polygons.extend(_arc_polygons(ax0, ay0, ax1, ay1, bulge, width, width))
        xs.extend([ax0, ax1])

    for i, stroke in enumerate(strokes):
        if stroke.kind is StrokeKind.LINE:
            continue
        stroke_polygons = _stroke_polygons(
            stroke, jitter_glyph_index, i, traits, grid_unit_x, grid_unit_y, script_fingerprint,
            offset_x, offset_y,
        )
        polygons.extend(stroke_polygons)
        xs.extend(pt[0] for polygon in stroke_polygons for pt in polygon)

    return polygons, xs, rounded_start, rounded_end, segments


_DIACRITIC_SCALE = 0.4
"""A diacritic renders at this fraction of the main glyph's own grid-cell size -- "no larger than 1
of the full letter cells," see `core.script.Glyph.diacritics`'s own docstring. Fixed for now, not its
own dial (would be a 13th dial before the fixed version is even verified to look right). Kept below
``0.5`` with real margin -- at the ``_LETTER_SCALE`` height, a "top" diacritic reaches
``letter_height * (1 + _DIACRITIC_SCALE)`` and a "bottom" one ``-letter_height * _DIACRITIC_SCALE``;
both need headroom within ``_ASCENT``/``_DESCENT`` for ``regularity``'s own jitter on top."""

_DIACRITIC_GAP_FRACTION = 0.20
"""An external-slot diacritic's near edge sits this fraction of the main glyph's own width/height
further from the main glyph's own edge, instead of flush against it -- direct user feedback that
diacritics "mix up with the letter too much," then (round 8, this still read as too small at ``0.07``)
"a blank space of 20% the size of the character." Checked against headroom the same way
``_DIACRITIC_SCALE`` already documents: worst case (a "top" diacritic, maximum ``regularity``
jitter) reaches ``550 + 0.20*550 + 220 + 35 = 915`` em-units -- ``_ASCENT`` raised to ``930`` alongside
this change for exactly that margin, see its own docstring."""


def _diacritic_offset(
    slot: str, direction: WritingDirection, grid_max_x: int, grid_max_y: int, grid_unit_x: float, grid_unit_y: float,
) -> tuple[float, float]:
    """Where a diacritic's own (0,0) grid point lands in em-space, for the slot it was rolled into --
    see ``Glyph.diacritics``'s own docstring for the slot vocabulary. External slots (``cross_pos``/
    ``cross_neg``/``along_pos``/``along_neg``) sit ``_DIACRITIC_GAP_FRACTION`` past the main glyph's
    own edge on the axis they extend past (not flush against it), centered on the other axis -- which
    axis is "cross" (no adjacent neighbor) vs. "along" (where the next glyph sits) depends on
    ``direction``: vertical scripts (``TTB_LTR``/``TTB_RTL``) have cross=x/along=y, every other
    direction has cross=y/along=x. ``"pos"``/``"neg"`` are just that axis's own positive/negative
    em-space direction, not direction-specific sides. Internal slots (``"internal:{xi},{yi}"``, each
    ``0``/``1``/``2``) center the diacritic *on* one of 9 fractional positions of the main glyph's own
    bounding box -- deliberately not clamped to stay fully inside, so an edge/corner grid point still
    nests half-on-the-boundary the way a mark sitting right where two strokes cross would, and no gap
    applies here (nested by design, not separated from an edge)."""
    width_main, height_main = grid_max_x * grid_unit_x, grid_max_y * grid_unit_y
    width_diac, height_diac = width_main * _DIACRITIC_SCALE, height_main * _DIACRITIC_SCALE

    if slot.startswith("internal:"):
        xi, yi = (int(v) for v in slot[len("internal:"):].split(","))
        return (xi / 2.0) * width_main - width_diac / 2.0, (yi / 2.0) * height_main - height_diac / 2.0

    gap_x, gap_y = width_main * _DIACRITIC_GAP_FRACTION, height_main * _DIACRITIC_GAP_FRACTION

    is_vertical_script = direction in (WritingDirection.TTB_LTR, WritingDirection.TTB_RTL)
    axis = "x" if (slot.startswith("cross") and is_vertical_script) or (
        slot.startswith("along") and not is_vertical_script
    ) else "y"
    positive = slot.endswith("_pos")
    if axis == "y":
        return (width_main - width_diac) / 2, height_main + gap_y if positive else -height_diac - gap_y
    return width_main + gap_x if positive else -width_diac - gap_x, (height_main - height_diac) / 2


def _emit_polygons(pen: TTGlyphPen, polygons: list[list[tuple[float, float]]]) -> None:
    for polygon in polygons:
        pen.moveTo((round(polygon[0][0]), round(polygon[0][1])))
        for pt in polygon[1:]:
            pen.lineTo((round(pt[0]), round(pt[1])))
        pen.closePath()


def _glyph_terminal_ornament_polygons(
    glyph: Glyph, glyph_index: int, traits, grid_unit_x: float, grid_unit_y: float, grid_max_x: int, grid_max_y: int,
    segments: dict[int, tuple[float, float, float, float]], rounded_start: dict[int, bool], rounded_end: dict[int, bool],
) -> list[list[tuple[float, float]]]:
    """The main glyph's own terminal ornaments (``_roll_terminal_ornaments``), each resolved to real
    em-space polygons -- never applied to a diacritic's own strokes (an ornament is a letter-scale
    flourish; a diacritic is already a small attached mark, not a "letter" in its own right). Attaches
    to ``segments``' own *final* (post-crookedness, post-roundedness-truncation) stroke endpoint rather
    than recomputing a plain jittered one, and ``rounded_start``/``rounded_end`` keep rounding's own
    claimed endpoints out of the candidate pool in the first place (see ``_roll_terminal_ornaments``'s
    own docstring)."""
    polygons: list[list[tuple[float, float]]] = []
    width = _stroke_width(traits)
    ornaments = _roll_terminal_ornaments(glyph, glyph_index, traits, grid_max_x, grid_max_y, rounded_start, rounded_end)
    for stroke_index, is_start, preset_index in ornaments:
        x0, y0, x1, y1 = segments[stroke_index]
        ex, ey, ox, oy = (x0, y0, x1, y1) if is_start else (x1, y1, x0, y0)
        dx, dy = ex - ox, ey - oy
        length = math.hypot(dx, dy) or 1.0
        preset = _TERMINAL_ORNAMENT_PRESETS[preset_index]
        seed_text = f"{glyph_index}:{stroke_index}:ornament"
        polygons.extend(_terminal_ornament_polygons(ex, ey, dx / length, dy / length, width, preset, seed_text, length))
    return polygons


def _build_glyph_outline(
    glyph: Glyph, glyph_index: int, traits, grid_unit_x: float, grid_unit_y: float, grid_max_x: int, grid_max_y: int,
    diacritic_grid_max_x: int, diacritic_grid_max_y: int, direction: WritingDirection, script_fingerprint: str,
) -> tuple[object, bool, tuple[float, float]]:
    """Returns ``(ttf_glyph, has_contour, (min_x, max_x))`` -- the outline and its own advance-width
    extent computed together (one ``_render_scope`` pass per scope, not two), since both need the same
    ``crookedness``/``roundedness`` geometry."""
    pen = TTGlyphPen(None)
    any_contour = False
    xs: list[float] = []

    main_polygons, main_xs, rounded_start, rounded_end, segments = _render_scope(
        glyph.strokes, traits, glyph_index, grid_unit_x, grid_unit_y, 0.0, 0.0, script_fingerprint,
    )
    _emit_polygons(pen, main_polygons)
    any_contour = any_contour or bool(main_polygons)
    xs.extend(main_xs)

    # The diacritic's own overall footprint stays pinned to `_DIACRITIC_SCALE` of the main glyph's own
    # overall size regardless of the diacritic's own grid resolution (round 9: a diacritic can now have
    # a different grid shape than its main letter, `ScriptGridForce` -- this is a strict generalization
    # of the old `grid_unit_x * _DIACRITIC_SCALE` formula, which reduces to exactly that when the two
    # grids match, the common/default case).
    width_main, height_main = grid_max_x * grid_unit_x, grid_max_y * grid_unit_y
    diac_unit_x = (width_main * _DIACRITIC_SCALE) / diacritic_grid_max_x
    diac_unit_y = (height_main * _DIACRITIC_SCALE) / diacritic_grid_max_y
    for slot, diac in glyph.diacritics.items():
        offset_x, offset_y = _diacritic_offset(slot, direction, grid_max_x, grid_max_y, grid_unit_x, grid_unit_y)
        diac_polygons, diac_xs, _diac_rs, _diac_re, _diac_seg = _render_scope(
            diac.strokes, traits, f"{glyph_index}:{slot}", diac_unit_x, diac_unit_y, offset_x, offset_y,
            script_fingerprint,
        )
        _emit_polygons(pen, diac_polygons)
        any_contour = any_contour or bool(diac_polygons)
        xs.extend(diac_xs)

    ornament_polygons = _glyph_terminal_ornament_polygons(
        glyph, glyph_index, traits, grid_unit_x, grid_unit_y, grid_max_x, grid_max_y, segments, rounded_start, rounded_end,
    )
    _emit_polygons(pen, ornament_polygons)
    any_contour = any_contour or bool(ornament_polygons)

    extent = (min(xs), max(xs)) if xs else (0.0, UPM)
    return pen.glyph(), any_contour, extent


def build_font(script: InventedScript, output_path: Path, family_name: str) -> None:
    """Writes a real ``.ttf`` to ``output_path``. One glyph per
    ``script.glyphs`` entry, each mapped to a Private Use Area codepoint
    starting at U+E000 in that same order -- a word's own invented-
    script rendering (``script_render.py``, not yet written) must use
    this exact same order to stay in sync."""
    glyph_names = [".notdef"] + [f"g{i:04d}" for i in range(len(script.glyphs))]
    glyphs = {}
    advance: dict[str, tuple[int, int]] = {}
    cmap: dict[int, str] = {}

    grid_unit_x = (UPM * _LETTER_SCALE) / script.grid_max_x
    grid_unit_y = (UPM * _LETTER_SCALE) / script.grid_max_y
    side_bearing = _SIDE_BEARING
    empty_advance = UPM * _LETTER_SCALE * lerp(script.traits.proportion, 0.7, 1.3) + 2 * side_bearing
    fingerprint = _script_fingerprint(script)

    notdef_box = [(UPM * 0.1, 0), (UPM * 0.1, _ASCENT * 0.8), (UPM * 0.4, _ASCENT * 0.8), (UPM * 0.4, 0)]
    pen = TTGlyphPen(None)
    pen.moveTo((round(notdef_box[0][0]), round(notdef_box[0][1])))
    for pt in notdef_box[1:]:
        pen.lineTo((round(pt[0]), round(pt[1])))
    pen.closePath()
    glyphs[".notdef"] = pen.glyph()
    advance[".notdef"] = (round(empty_advance), round(side_bearing))

    for i, glyph in enumerate(script.glyphs):
        name = f"g{i:04d}"
        outline, has_contour, (min_x, max_x) = _build_glyph_outline(
            glyph, i, script.traits, grid_unit_x, grid_unit_y, script.grid_max_x, script.grid_max_y,
            script.diacritic_grid_max_x, script.diacritic_grid_max_y, script.direction, fingerprint,
        )
        glyphs[name] = outline
        width = empty_advance if not has_contour else (max_x - min_x) + 2 * side_bearing
        advance[name] = (round(width), round(side_bearing))
        cmap[0xE000 + i] = name

    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(glyph_names)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(advance)
    fb.setupHorizontalHeader(ascent=_ASCENT, descent=_DESCENT)
    fb.setupNameTable({"familyName": family_name, "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=_ASCENT, sTypoDescender=_DESCENT, usWinAscent=_ASCENT, usWinDescent=-_DESCENT)
    fb.setupPost()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fb.save(str(output_path))


def codepoint_for_symbol_index(index: int) -> int:
    """The Private Use Area codepoint ``build_font`` assigns to
    ``script.glyphs[index]`` -- the one piece of the mapping
    ``script_render.py`` needs without re-running the whole font build."""
    return 0xE000 + index


__all__ = ["build_font", "codepoint_for_symbol_index", "UPM"]
