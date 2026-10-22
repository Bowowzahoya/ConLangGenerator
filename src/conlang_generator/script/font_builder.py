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

Consumes 7 of ``ScriptTraits``' 12 dials (the rendering-time half; see
``generation.script_gen``'s own docstring for the stroke-topology half):
``weight``/``stroke_contrast`` (stroke width, and whether it
tapers along the stroke), ``slant`` (shear), ``proportion`` (horizontal
scale), ``regularity`` (organic jitter, unipolar -- 0 = none, 1 = max),
``terminal_style`` (small serif feet on line-stroke endpoints), and
``dot_ornateness`` (plain circle vs. a brief bent diagonal stroke for a
``DOT``). ``angularity`` is currently dormant everywhere -- see its own
docstring in ``core.script.ScriptTraits``.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from conlang_generator.core.script import Glyph, InventedScript, Point, Stroke, StrokeKind, lerp, lerp01

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


def _dot_polygons(cx: float, cy: float, width: float, ornateness: float, seed_text: str) -> list[list[tuple[float, float]]]:
    """A dot renders as a plain circle at ``dot_ornateness == 0``; as it rises toward ``1.0``, it
    increasingly renders instead as a brief, slightly bent diagonal stroke (Chinese-brush-dot style).
    The circle-vs-diagonal choice is deterministic (``_stable_unit``-keyed by the dot's own jitter
    seed, the same determinism convention every other font_builder randomness-lookalike already uses
    -- never a fresh ``random`` draw), with ``ornateness`` itself setting the probability."""
    choice = (_stable_unit(f"{seed_text}:ornate") + 1.0) / 2.0
    if choice > ornateness:
        return [_regular_polygon(cx, cy, _DOT_RADIUS)]
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


def _stroke_polygons(
    stroke: Stroke, glyph_index: int | str, stroke_index: int, traits, grid_unit_x: float, grid_unit_y: float,
    offset_x: float = 0.0, offset_y: float = 0.0,
) -> list[list[tuple[float, float]]]:
    jitter_prefix = f"{glyph_index}:{stroke_index}"
    width = _stroke_width(traits)
    contrast = lerp01(traits.stroke_contrast, 0.0, 0.45)
    w_start, w_end = width * (1 + contrast), width * (1 - contrast)

    if stroke.kind is StrokeKind.DOT:
        cx, cy = _point_to_em(stroke.start, f"{jitter_prefix}:dot", traits, grid_unit_x, grid_unit_y, offset_x, offset_y)
        return _dot_polygons(cx, cy, width, traits.dot_ornateness, f"{jitter_prefix}:dot")

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

    if stroke.kind is StrokeKind.LINE and traits.terminal_style > 0.2:
        foot_radius = lerp(traits.terminal_style, width * 0.6, width * 1.3)
        for ex, ey in ((x0, y0), (x1, y1)):
            polygons.append(_regular_polygon(ex, ey, foot_radius, sides=4))

    return polygons


_DIACRITIC_SCALE = 0.4
"""A diacritic renders at this fraction of the main glyph's own grid-cell size -- "no larger than 1
of the full letter cells," see `core.script.Glyph.diacritics`'s own docstring. Fixed for now, not its
own dial (would be a 13th dial before the fixed version is even verified to look right). Kept below
``0.5`` with real margin -- at the ``_LETTER_SCALE`` height, a "top" diacritic reaches
``letter_height * (1 + _DIACRITIC_SCALE)`` and a "bottom" one ``-letter_height * _DIACRITIC_SCALE``;
both need headroom within ``_ASCENT``/``_DESCENT`` for ``regularity``'s own jitter on top."""


def _diacritic_offset(
    slot: str, grid_max_x: int, grid_max_y: int, grid_unit_x: float, grid_unit_y: float,
) -> tuple[float, float]:
    """Where a diacritic's own (0,0) grid point lands in em-space, for the fixed anchor slot it was
    rolled into -- centered on the main glyph's own bounding box along the axis it doesn't extend past
    (so a "top" diacritic is horizontally centered, a "left" one vertically centered), sitting flush
    against the main glyph's own edge on the axis it does extend past. The same 4 names `Glyph.
    anchors` already uses as its own worked examples (`"top"`/`"bottom"`/`"left"`/`"right"`)."""
    width_main, height_main = grid_max_x * grid_unit_x, grid_max_y * grid_unit_y
    width_diac, height_diac = width_main * _DIACRITIC_SCALE, height_main * _DIACRITIC_SCALE
    if slot == "top":
        return (width_main - width_diac) / 2, height_main
    if slot == "bottom":
        return (width_main - width_diac) / 2, -height_diac
    if slot == "left":
        return -width_diac, (height_main - height_diac) / 2
    if slot == "right":
        return width_main, (height_main - height_diac) / 2
    raise ValueError(f"unknown diacritic anchor slot: {slot!r}")


def _iter_glyph_strokes(
    glyph: Glyph, glyph_index: int, grid_unit_x: float, grid_unit_y: float, grid_max_x: int, grid_max_y: int,
):
    """Yields ``(stroke, jitter_glyph_index, stroke_index, grid_unit_x, grid_unit_y, offset_x,
    offset_y)`` for every stroke this glyph is built from -- its own, plus each attached diacritic's
    own, rendered at `_DIACRITIC_SCALE` and translated to its own fixed anchor-slot offset
    (`_diacritic_offset`). Shared by `_build_glyph_outline` and `_glyph_extent` so a diacritic sticking
    out past the main glyph's own edge (a "left"/"right" one) is accounted for in both the compiled
    outline and the advance-width calculation."""
    for stroke_index, stroke in enumerate(glyph.strokes):
        yield stroke, glyph_index, stroke_index, grid_unit_x, grid_unit_y, 0.0, 0.0
    diac_unit_x, diac_unit_y = grid_unit_x * _DIACRITIC_SCALE, grid_unit_y * _DIACRITIC_SCALE
    for slot, diac in glyph.diacritics.items():
        offset_x, offset_y = _diacritic_offset(slot, grid_max_x, grid_max_y, grid_unit_x, grid_unit_y)
        for stroke_index, stroke in enumerate(diac.strokes):
            yield stroke, f"{glyph_index}:{slot}", stroke_index, diac_unit_x, diac_unit_y, offset_x, offset_y


def _build_glyph_outline(
    glyph: Glyph, glyph_index: int, traits, grid_unit_x: float, grid_unit_y: float, grid_max_x: int, grid_max_y: int,
):
    pen = TTGlyphPen(None)
    any_contour = False
    for stroke, idx, s_idx, unit_x, unit_y, ox, oy in _iter_glyph_strokes(
        glyph, glyph_index, grid_unit_x, grid_unit_y, grid_max_x, grid_max_y
    ):
        for polygon in _stroke_polygons(stroke, idx, s_idx, traits, unit_x, unit_y, ox, oy):
            pen.moveTo((round(polygon[0][0]), round(polygon[0][1])))
            for pt in polygon[1:]:
                pen.lineTo((round(pt[0]), round(pt[1])))
            pen.closePath()
            any_contour = True
    return pen.glyph(), any_contour


def _glyph_extent(
    glyph: Glyph, glyph_index: int, traits, grid_unit_x: float, grid_unit_y: float, grid_max_x: int, grid_max_y: int,
) -> tuple[float, float]:
    xs: list[float] = []
    for stroke, idx, s_idx, unit_x, unit_y, ox, oy in _iter_glyph_strokes(
        glyph, glyph_index, grid_unit_x, grid_unit_y, grid_max_x, grid_max_y
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
        )
        glyphs[name] = outline
        if not has_contour:
            width = empty_advance
        else:
            min_x, max_x = _glyph_extent(
                glyph, i, script.traits, grid_unit_x, grid_unit_y, script.grid_max_x, script.grid_max_y,
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
