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

Consumes 9 of ``ScriptTraits``' 13 dials (the rendering-time half; see
``generation.script_gen``'s own docstring for the stroke-topology half, and
``ornateness``'s own docstring for why it's read in *both* halves):
``weight``/``stroke_contrast`` (stroke width, and whether it tapers along
the stroke), ``slant`` (shear), ``proportion`` (horizontal scale),
``regularity`` (organic jitter, unipolar -- 0 = none, 1 = max), ``terminal_
style`` (frequency of a per-glyph terminal ornament -- a hook/swirl/foot/
extended stroke, one of 10 presets, at one stroke-end of some letters),
``serif`` (a separate, pervasive, script-wide stroke-end treatment -- see
its own docstring for how it differs from a terminal ornament), and
``ornateness`` (dot style, diacritic placement diversity, and which
terminal-ornament preset gets favored). ``angularity`` is currently dormant
everywhere -- see its own docstring in ``core.script.ScriptTraits``.
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

_ASCENT = 850
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
    dot style a low-``ornateness`` script reuses everywhere, and the whole serif rule in ``script.
    font_builder``'s own serif code) rather than per-glyph/per-stroke like every other ``_stable_unit``
    call here. Still a pure function of ``InventedScript`` data alone, same rule this module's own
    docstring already holds everything else to -- never RNG state, never the original generation seed
    (not present on this object at all)."""
    return f"{script.traits.model_dump()}:{script.direction}:{script.grid_max_x}:{script.grid_max_y}"


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


_DOT_STYLE_WEIGHTS_LOW = {"square": 0.42, "stroke": 0.42, "circle": 0.16}
_DOT_STYLE_WEIGHTS_HIGH = {"square": 0.30, "stroke": 0.30, "circle": 0.40}
"""The three dot styles' own selection weights at ``ornateness == 0`` vs. ``== 1`` -- low concentrates
on square/stroke ("more chance of stroke or dot," direct user phrasing), high is flatter with a slight
circle lean ("slightly more chance of circles"). ``_weighted_dot_style`` interpolates between them."""


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


class SerifRule(NamedTuple):
    """One script-wide serif rule, rolled once by ``_roll_serif_rule`` and reused for every stroke in
    every glyph -- a real typeface's serif treatment is visually consistent across its whole alphabet,
    not a fresh per-letter decision (contrast ``terminal_style``'s own per-*glyph* ornament roll)."""

    coverage: dict[str, float]
    """Per orientation class (``"vertical"``/``"horizontal"``/``"diagonal"``), the fraction of that
    class's own qualifying strokes that get a serif at all -- ``0.0`` if that class never does. One
    fraction-per-class model subsumes every named style the user described ("everywhere" = every class
    at `1.0`, "only for some vertical" = the vertical class active below `1.0`, "at random" = a shared
    middling fraction, any "combination" = whichever classes happened to roll active) without
    enumerating combinations by name."""
    sides_count: dict[str, int]
    """Per class, ``1`` or ``2`` -- whether a qualifying stroke gets a serif at one end or both."""
    fixed_side: dict[str, str]
    """Per class, which end when ``sides_count`` is ``1``: ``"lower"``/``"upper"`` (by the stroke's own
    two endpoints' em-space ``y`` -- well-defined for any orientation, including diagonal) or
    ``"random_per_stroke"``. Hebrew-style ("always the one side") is ``"lower"``/``"upper"`` on every
    class; Armenian-style ("always both sides on vertical") is ``sides_count["vertical"] == 2`` with
    whatever the other classes happened to roll -- both just different draws of this one model, not
    special-cased."""
    shape: str
    """``"triangle"``/``"rounded"``/``"straight"`` -- one roll for the whole script."""
    thickness_factor: float
    """Multiplies the stroke's own base width -- partly ``weight``-driven, partly random, per direct
    request ("thickness also partly determined by the thickness trait, but can still vary a bit")."""


_SERIF_ORIENTATION_CLASSES = ("vertical", "horizontal", "diagonal")


def _classify_orientation(dx: int, dy: int) -> str:
    """A grid-space stroke direction (not the jittered em-space one -- classification should reflect
    the stroke's own logical 0/90/45-degree direction, not a slightly-off rendered one) -> one of
    ``_SERIF_ORIENTATION_CLASSES``."""
    if dx == 0:
        return "vertical"
    if dy == 0:
        return "horizontal"
    return "diagonal"


def _roll_serif_rule(traits, fingerprint: str) -> SerifRule:
    """Rolls the four sub-decisions documented on ``SerifRule`` itself, each ``_stable_unit``-keyed off
    ``fingerprint`` (``_script_fingerprint``) so the whole rule -- and therefore every stroke's own
    serif-or-not -- stays identical for the same script, independent of a per-stroke draw."""
    coverage: dict[str, float] = {}
    sides_count: dict[str, int] = {}
    fixed_side: dict[str, str] = {}
    for cls in _SERIF_ORIENTATION_CLASSES:
        active_roll = (_stable_unit(f"{fingerprint}:serif:{cls}:active") + 1.0) / 2.0
        if active_roll < lerp01(traits.serif, 0.0, 0.9):
            coverage_roll = (_stable_unit(f"{fingerprint}:serif:{cls}:coverage") + 1.0) / 2.0
            coverage[cls] = lerp01(coverage_roll, 0.3, 1.0)
        else:
            coverage[cls] = 0.0
        sides_roll = (_stable_unit(f"{fingerprint}:serif:{cls}:sides") + 1.0) / 2.0
        sides_count[cls] = 2 if sides_roll < 0.4 else 1
        side_roll = (_stable_unit(f"{fingerprint}:serif:{cls}:side") + 1.0) / 2.0
        fixed_side[cls] = "lower" if side_roll < 0.4 else "upper" if side_roll < 0.8 else "random_per_stroke"
    shape_roll = (_stable_unit(f"{fingerprint}:serif:shape") + 1.0) / 2.0
    shape = "triangle" if shape_roll < 0.34 else "rounded" if shape_roll < 0.67 else "straight"
    thickness_wobble = 1.0 + _stable_unit(f"{fingerprint}:serif:thickness") * 0.15
    thickness_factor = lerp(traits.weight, 0.8, 1.4) * thickness_wobble
    return SerifRule(
        coverage=coverage, sides_count=sides_count, fixed_side=fixed_side, shape=shape,
        thickness_factor=thickness_factor,
    )


def _serif_polygons_for_stroke(
    stroke: Stroke, x0: float, y0: float, x1: float, y1: float, width: float, stroke_key: str, rule: SerifRule,
) -> list[list[tuple[float, float]]]:
    """Applies ``rule`` (the one script-wide ``SerifRule``) to a single already-placed ``LINE``
    stroke's own em-space endpoints -- a serif is a small polygon planted at a qualifying endpoint, no
    new sampling machinery needed (``"rounded"``/``"triangle"`` both reuse ``_regular_polygon`` at
    different side counts, ``"straight"`` a short ``_quad`` continuing the stroke's own direction)."""
    cls = _classify_orientation(stroke.end.x - stroke.start.x, stroke.end.y - stroke.start.y)
    coverage = rule.coverage[cls]
    if coverage <= 0.0:
        return []
    include_roll = (_stable_unit(f"{stroke_key}:serif-include") + 1.0) / 2.0
    if include_roll >= coverage:
        return []
    if rule.sides_count[cls] == 2:
        ends = [(x0, y0, x1, y1), (x1, y1, x0, y0)]
    else:
        fixed = rule.fixed_side[cls]
        if fixed == "random_per_stroke":
            fixed = "lower" if _stable_unit(f"{stroke_key}:serif-side") >= 0 else "upper"
        lower_first = y0 <= y1
        use_start = (fixed == "lower") == lower_first
        ends = [(x0, y0, x1, y1)] if use_start else [(x1, y1, x0, y0)]
    radius = width * rule.thickness_factor * 0.6
    polygons: list[list[tuple[float, float]]] = []
    for ex, ey, ox, oy in ends:
        if rule.shape == "rounded":
            polygons.append(_regular_polygon(ex, ey, radius))
        elif rule.shape == "triangle":
            polygons.append(_regular_polygon(ex, ey, radius, sides=3))
        else:  # "straight" -- a short nub continuing the stroke's own outward direction
            dx, dy = ex - ox, ey - oy
            length = math.hypot(dx, dy) or 1.0
            tip_x, tip_y = ex + dx / length * radius, ey + dy / length * radius
            polygons.append(_quad(ex, ey, tip_x, tip_y, width * rule.thickness_factor, width * 0.4))
    return polygons


def _stroke_polygons(
    stroke: Stroke, glyph_index: int | str, stroke_index: int, traits, grid_unit_x: float, grid_unit_y: float,
    script_fingerprint: str, serif_rule: SerifRule, offset_x: float = 0.0, offset_y: float = 0.0,
) -> list[list[tuple[float, float]]]:
    jitter_prefix = f"{glyph_index}:{stroke_index}"
    width = _stroke_width(traits)
    contrast = lerp01(traits.stroke_contrast, 0.0, 0.45)
    w_start, w_end = width * (1 + contrast), width * (1 - contrast)

    if stroke.kind is StrokeKind.DOT:
        cx, cy = _point_to_em(stroke.start, f"{jitter_prefix}:dot", traits, grid_unit_x, grid_unit_y, offset_x, offset_y)
        return _dot_polygons(cx, cy, width, traits.ornateness, f"{jitter_prefix}:dot", script_fingerprint)

    x0, y0 = _point_to_em(stroke.start, f"{jitter_prefix}:a", traits, grid_unit_x, grid_unit_y, offset_x, offset_y)
    x1, y1 = _point_to_em(stroke.end, f"{jitter_prefix}:b", traits, grid_unit_x, grid_unit_y, offset_x, offset_y)

    polygons: list[list[tuple[float, float]]] = []
    if stroke.kind is StrokeKind.LINE:
        polygons.append(_quad(x0, y0, x1, y1, w_start, w_end))
    else:  # ARC -- sample a quadratic curve bulging perpendicular to the chord
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        pdx, pdy = _perpendicular(x0, y0, x1, y1, 1.0)
        length = math.hypot(x1 - x0, y1 - y0)
        cx, cy = mx + pdx * stroke.bulge * length, my + pdy * stroke.bulge * length
        points = []
        for i in range(_ARC_SAMPLES + 1):
            t = i / _ARC_SAMPLES
            sx = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t**2 * x1
            sy = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t**2 * y1
            points.append((sx, sy))
        for i in range(len(points) - 1):
            segment_t0, segment_t1 = i / _ARC_SAMPLES, (i + 1) / _ARC_SAMPLES
            w0 = w_start + (w_end - w_start) * segment_t0
            w1 = w_start + (w_end - w_start) * segment_t1
            polygons.append(_quad(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1], w0, w1))

    if stroke.kind is StrokeKind.LINE:
        polygons.extend(
            _serif_polygons_for_stroke(stroke, x0, y0, x1, y1, width, jitter_prefix, serif_rule)
        )

    return polygons


class OrnamentPreset(NamedTuple):
    name: str
    bend_degrees: float
    """Total turning angle of the ornament's own centerline, degrees -- ``0`` for a straight
    extension, up to ``540`` for `"swirl"`` (one and a half turns)."""
    length_factor: float
    """Multiplies ``_ORNAMENT_BASE_LENGTH`` for this preset's own total centerline length."""
    closed: bool
    """Whether the ornament's own far end gets a small solid cap (a plain stroke tapering to a point
    otherwise) -- "closed"/"open" per the user's own Thai-hook vs. Щ-hook distinction."""
    width_factor: float
    """Multiplies the glyph's own base stroke width."""


_TERMINAL_ORNAMENT_PRESETS: tuple[OrnamentPreset, ...] = (
    OrnamentPreset("plain_foot", 0.0, 0.5, True, 1.3),
    OrnamentPreset("short_serif", 0.0, 0.3, True, 1.0),
    OrnamentPreset("closed_hook", 200.0, 0.8, True, 0.9),
    OrnamentPreset("open_hook", 120.0, 0.9, False, 0.85),
    OrnamentPreset("small_flare", 40.0, 0.6, False, 1.1),
    OrnamentPreset("rounded_bulb", 360.0, 0.5, True, 1.0),
    OrnamentPreset("short_extension", 0.0, 1.3, False, 0.8),
    OrnamentPreset("long_extension", 0.0, 2.2, False, 0.7),
    OrnamentPreset("swirl", 540.0, 1.0, True, 0.6),
    OrnamentPreset("double_hook", 240.0, 1.1, True, 0.9),
)
"""10 fixed terminal-ornament presets, ordered plain -> fancy (``_weighted_ornament_preset`` favors the
tail as ``ornateness`` rises) -- the user's own 5 named examples (foot/open hook/closed hook/swirl/
extended stroke) plus 5 more filling out the "fancy" end, each just a parameter tuple for one shared
drawing function (``_terminal_ornament_polygons``) rather than 10 bespoke hand-authored shapes. A
reasonable first pass, not claimed final -- tuned against a real rendered check, same as every other
new visual mechanic in this project."""

_ORNAMENT_BASE_LENGTH = UPM * _LETTER_SCALE * 0.22
"""Reference length an ornament preset's own ``length_factor`` scales from -- roughly 40% of a grid
cell at the default 2x2 grid, a visible but not overwhelming flourish."""


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
) -> list[tuple[int, bool, int]]:
    """Rolls 0, 1, or (rarely) 2 terminal ornaments for this glyph's own ``LINE`` strokes -- once per
    *glyph*, not per stroke (``terminal_style`` sets the frequency; see ``ScriptTraits.terminal_style``
    's own docstring for why this is a separate, per-letter-occasional mechanic, distinct from
    ``serif``'s own pervasive, per-script rule). Candidates are classified into ``_ornament_bucket``
    position buckets using *grid* coordinates (not the jittered em-space position -- a small jitter
    should never flip which bucket a point reads as). Returns ``(stroke_index, is_start, preset_index)``
    triples; ``is_start`` picks which of that ``Stroke``'s own two endpoints."""
    candidates = [
        (i, is_start)
        for i, s in enumerate(glyph.strokes)
        if s.kind is StrokeKind.LINE
        for is_start in (True, False)
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


def _ornament_main_points(x0: float, y0: float, dx: float, dy: float, preset: OrnamentPreset) -> list[tuple[float, float]]:
    """The sampled centerline for one ornament segment -- a straight 2-point line for
    ``bend_degrees == 0``, else an ``_arc_points`` sample. Shared by the main ornament and (for
    ``"double_hook"``) its own secondary branch."""
    base_length = _ORNAMENT_BASE_LENGTH * preset.length_factor
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
) -> list[list[tuple[float, float]]]:
    """Draws ``preset`` starting at ``(x0, y0)``, continuing in unit direction ``(dx, dy)`` (the
    stroke's own direction at this endpoint, so the ornament reads as a natural continuation past the
    letter). The curl direction (left vs. right) is its own deterministic per-instance coin flip, not
    baked into the preset -- a hook should be able to face either way depending on which letter it
    lands on, not always identically."""
    curl_sign = 1.0 if _stable_unit(f"{seed_text}:curl") >= 0 else -1.0
    signed_preset = preset._replace(bend_degrees=preset.bend_degrees * curl_sign)
    points = _ornament_main_points(x0, y0, dx, dy, signed_preset)
    polygons = _taper_polygons(points, width, preset.width_factor, preset.closed)
    if preset.name == "double_hook" and len(points) >= 3:
        branch_start = points[len(points) // 2]
        prev = points[len(points) // 2 - 1]
        bdx, bdy = branch_start[0] - prev[0], branch_start[1] - prev[1]
        blength = math.hypot(bdx, bdy) or 1.0
        branch_preset = signed_preset._replace(
            bend_degrees=-signed_preset.bend_degrees * 0.7, length_factor=preset.length_factor * 0.5,
        )
        branch_points = _ornament_main_points(branch_start[0], branch_start[1], bdx / blength, bdy / blength, branch_preset)
        polygons.extend(_taper_polygons(branch_points, width, preset.width_factor * 0.8, preset.closed))
    return polygons


_DIACRITIC_SCALE = 0.4
"""A diacritic renders at this fraction of the main glyph's own grid-cell size -- "no larger than 1
of the full letter cells," see `core.script.Glyph.diacritics`'s own docstring. Fixed for now, not its
own dial (would be a 13th dial before the fixed version is even verified to look right). Kept below
``0.5`` with real margin -- at the ``_LETTER_SCALE`` height, a "top" diacritic reaches
``letter_height * (1 + _DIACRITIC_SCALE)`` and a "bottom" one ``-letter_height * _DIACRITIC_SCALE``;
both need headroom within ``_ASCENT``/``_DESCENT`` for ``regularity``'s own jitter on top."""


def _diacritic_offset(
    slot: str, direction: WritingDirection, grid_max_x: int, grid_max_y: int, grid_unit_x: float, grid_unit_y: float,
) -> tuple[float, float]:
    """Where a diacritic's own (0,0) grid point lands in em-space, for the slot it was rolled into --
    see ``Glyph.diacritics``'s own docstring for the slot vocabulary. External slots (``cross_pos``/
    ``cross_neg``/``along_pos``/``along_neg``) sit flush against the main glyph's own edge on the axis
    they extend past, centered on the other axis -- which axis is "cross" (no adjacent neighbor) vs.
    "along" (where the next glyph sits) depends on ``direction``: vertical scripts (``TTB_LTR``/
    ``TTB_RTL``) have cross=x/along=y, every other direction has cross=y/along=x. ``"pos"``/``"neg"``
    are just that axis's own positive/negative em-space direction, not direction-specific sides.
    Internal slots (``"internal:{xi},{yi}"``, each ``0``/``1``/``2``) center the diacritic *on* one of
    9 fractional positions of the main glyph's own bounding box -- deliberately not clamped to stay
    fully inside, so an edge/corner grid point still nests half-on-the-boundary the way a mark sitting
    right where two strokes cross would."""
    width_main, height_main = grid_max_x * grid_unit_x, grid_max_y * grid_unit_y
    width_diac, height_diac = width_main * _DIACRITIC_SCALE, height_main * _DIACRITIC_SCALE

    if slot.startswith("internal:"):
        xi, yi = (int(v) for v in slot[len("internal:"):].split(","))
        return (xi / 2.0) * width_main - width_diac / 2.0, (yi / 2.0) * height_main - height_diac / 2.0

    is_vertical_script = direction in (WritingDirection.TTB_LTR, WritingDirection.TTB_RTL)
    axis = "x" if (slot.startswith("cross") and is_vertical_script) or (
        slot.startswith("along") and not is_vertical_script
    ) else "y"
    positive = slot.endswith("_pos")
    if axis == "y":
        return (width_main - width_diac) / 2, height_main if positive else -height_diac
    return width_main if positive else -width_diac, (height_main - height_diac) / 2


def _iter_glyph_strokes(
    glyph: Glyph, glyph_index: int, grid_unit_x: float, grid_unit_y: float, grid_max_x: int, grid_max_y: int,
    direction: WritingDirection,
):
    """Yields ``(stroke, jitter_glyph_index, stroke_index, grid_unit_x, grid_unit_y, offset_x,
    offset_y)`` for every stroke this glyph is built from -- its own, plus each attached diacritic's
    own, rendered at `_DIACRITIC_SCALE` and translated to its own slot offset (`_diacritic_offset`,
    direction-aware -- see that function's own docstring). Shared by `_build_glyph_outline` and
    `_glyph_extent` so a diacritic sticking out past the main glyph's own edge is accounted for in both
    the compiled outline and the advance-width calculation."""
    for stroke_index, stroke in enumerate(glyph.strokes):
        yield stroke, glyph_index, stroke_index, grid_unit_x, grid_unit_y, 0.0, 0.0
    diac_unit_x, diac_unit_y = grid_unit_x * _DIACRITIC_SCALE, grid_unit_y * _DIACRITIC_SCALE
    for slot, diac in glyph.diacritics.items():
        offset_x, offset_y = _diacritic_offset(slot, direction, grid_max_x, grid_max_y, grid_unit_x, grid_unit_y)
        for stroke_index, stroke in enumerate(diac.strokes):
            yield stroke, f"{glyph_index}:{slot}", stroke_index, diac_unit_x, diac_unit_y, offset_x, offset_y


def _emit_polygons(pen: TTGlyphPen, polygons: list[list[tuple[float, float]]]) -> None:
    for polygon in polygons:
        pen.moveTo((round(polygon[0][0]), round(polygon[0][1])))
        for pt in polygon[1:]:
            pen.lineTo((round(pt[0]), round(pt[1])))
        pen.closePath()


def _glyph_terminal_ornament_polygons(
    glyph: Glyph, glyph_index: int, traits, grid_unit_x: float, grid_unit_y: float, grid_max_x: int, grid_max_y: int,
) -> list[list[tuple[float, float]]]:
    """The main glyph's own terminal ornaments (``_roll_terminal_ornaments``), each resolved to real
    em-space polygons -- never applied to a diacritic's own strokes (an ornament is a letter-scale
    flourish; a diacritic is already a small attached mark, not a "letter" in its own right)."""
    polygons: list[list[tuple[float, float]]] = []
    width = _stroke_width(traits)
    for stroke_index, is_start, preset_index in _roll_terminal_ornaments(glyph, glyph_index, traits, grid_max_x, grid_max_y):
        s = glyph.strokes[stroke_index]
        here, other = (s.start, s.end) if is_start else (s.end, s.start)
        jitter_prefix = f"{glyph_index}:{stroke_index}"
        here_tag, other_tag = ("a", "b") if is_start else ("b", "a")
        ex, ey = _point_to_em(here, f"{jitter_prefix}:{here_tag}", traits, grid_unit_x, grid_unit_y)
        ox, oy = _point_to_em(other, f"{jitter_prefix}:{other_tag}", traits, grid_unit_x, grid_unit_y)
        dx, dy = ex - ox, ey - oy
        length = math.hypot(dx, dy) or 1.0
        preset = _TERMINAL_ORNAMENT_PRESETS[preset_index]
        polygons.extend(
            _terminal_ornament_polygons(ex, ey, dx / length, dy / length, width, preset, f"{jitter_prefix}:ornament")
        )
    return polygons


def _build_glyph_outline(
    glyph: Glyph, glyph_index: int, traits, grid_unit_x: float, grid_unit_y: float, grid_max_x: int, grid_max_y: int,
    direction: WritingDirection, script_fingerprint: str, serif_rule: SerifRule,
):
    pen = TTGlyphPen(None)
    any_contour = False
    for stroke, idx, s_idx, unit_x, unit_y, ox, oy in _iter_glyph_strokes(
        glyph, glyph_index, grid_unit_x, grid_unit_y, grid_max_x, grid_max_y, direction,
    ):
        polygons = _stroke_polygons(stroke, idx, s_idx, traits, unit_x, unit_y, script_fingerprint, serif_rule, ox, oy)
        _emit_polygons(pen, polygons)
        any_contour = any_contour or bool(polygons)
    ornament_polygons = _glyph_terminal_ornament_polygons(
        glyph, glyph_index, traits, grid_unit_x, grid_unit_y, grid_max_x, grid_max_y,
    )
    _emit_polygons(pen, ornament_polygons)
    any_contour = any_contour or bool(ornament_polygons)
    return pen.glyph(), any_contour


def _glyph_extent(
    glyph: Glyph, glyph_index: int, traits, grid_unit_x: float, grid_unit_y: float, grid_max_x: int, grid_max_y: int,
    direction: WritingDirection,
) -> tuple[float, float]:
    xs: list[float] = []
    for stroke, idx, s_idx, unit_x, unit_y, ox, oy in _iter_glyph_strokes(
        glyph, glyph_index, grid_unit_x, grid_unit_y, grid_max_x, grid_max_y, direction,
    ):
        jitter_prefix = f"{idx}:{s_idx}"
        xs.append(_point_to_em(stroke.start, f"{jitter_prefix}:a", traits, unit_x, unit_y, ox, oy)[0])
        xs.append(_point_to_em(stroke.end, f"{jitter_prefix}:b", traits, unit_x, unit_y, ox, oy)[0])
    if not xs:
        return 0.0, UPM
    return min(xs), max(xs)


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
    serif_rule = _roll_serif_rule(script.traits, fingerprint)

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
        outline, has_contour = _build_glyph_outline(
            glyph, i, script.traits, grid_unit_x, grid_unit_y, script.grid_max_x, script.grid_max_y,
            script.direction, fingerprint, serif_rule,
        )
        glyphs[name] = outline
        if not has_contour:
            width = empty_advance
        else:
            min_x, max_x = _glyph_extent(
                glyph, i, script.traits, grid_unit_x, grid_unit_y, script.grid_max_x, script.grid_max_y,
                script.direction,
            )
            width = (max_x - min_x) + 2 * side_bearing
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
