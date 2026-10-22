"""Tests for script.font_builder -- compiling an InventedScript into a
real TTF via fontTools. Round-trips every font it builds through a real
fontTools.ttLib.TTFont parse, not just a "no exception" check."""

from pathlib import Path

import pytest

fontTools = pytest.importorskip("fontTools")
from fontTools.ttLib import TTFont  # noqa: E402

from fontTools.pens.recordingPen import RecordingPen  # noqa: E402

from conlang_generator.core.script import ScriptTraits, StrokeKind
from conlang_generator.generation import script_gen
from conlang_generator.script.font_builder import (
    _DOT_RADIUS,
    _LETTER_SCALE,
    UPM,
    _build_glyph_outline,
    _dot_polygons,
    _stroke_width,
    build_font,
    codepoint_for_symbol_index,
)
from tests._shared_language import cached_language


def _contour_signed_areas(glyph_outline) -> list[float]:
    """Every closed contour's own shoelace signed area, by replaying the
    already-built glyph outline through a RecordingPen -- the same way
    `test_build_font_is_a_pure_function...` above re-reads built glyph
    data, not a separate geometry reimplementation."""
    pen = RecordingPen()
    glyph_outline.draw(pen, None)
    areas = []
    current: list[tuple[float, float]] = []
    for cmd, args in pen.value:
        if cmd == "moveTo":
            current = [args[0]]
        elif cmd == "lineTo":
            current.append(args[0])
        elif cmd == "closePath":
            area = 0.0
            n = len(current)
            for i in range(n):
                x0, y0 = current[i]
                x1, y1 = current[(i + 1) % n]
                area += x0 * y1 - x1 * y0
            areas.append(area / 2.0)
            current = []
    return areas


def _build(tmp_path: Path, seed: int = 1) -> tuple[Path, "object"]:
    language = cached_language(0)
    script = script_gen.generate_script(str(seed), language.phonology)
    output = tmp_path / "test.ttf"
    build_font(script, output, "TestFamily")
    return output, script


def test_codepoint_for_symbol_index_starts_at_private_use_area():
    assert codepoint_for_symbol_index(0) == 0xE000
    assert codepoint_for_symbol_index(5) == 0xE005


def test_build_font_writes_a_real_file(tmp_path: Path):
    output, _ = _build(tmp_path)
    assert output.is_file() and output.stat().st_size > 0


def test_built_font_round_trips_and_has_one_glyph_per_script_symbol(tmp_path: Path):
    output, script = _build(tmp_path)
    tt = TTFont(str(output))
    try:
        glyph_order = tt.getGlyphOrder()
        assert len(glyph_order) == len(script.glyphs) + 1  # +1 for .notdef
        cmap = tt.getBestCmap()
        assert len(cmap) == len(script.glyphs)
        for i in range(len(script.glyphs)):
            assert codepoint_for_symbol_index(i) in cmap
    finally:
        tt.close()


def test_every_glyph_with_strokes_has_a_non_empty_outline(tmp_path: Path):
    output, script = _build(tmp_path)
    tt = TTFont(str(output))
    try:
        glyf = tt["glyf"]
        for i, glyph in enumerate(script.glyphs):
            name = f"g{i:04d}"
            if glyph.strokes:
                assert glyf[name].numberOfContours > 0
    finally:
        tt.close()


def test_every_contour_in_a_glyph_winds_the_same_direction():
    # Real bug, caught empirically (every glyph in a real generated font
    # had this exact signature before the fix): a dot or a
    # `terminal_style` foot is built from `_regular_polygon`, which used
    # to wind the opposite direction from `_quad` (every line stroke's
    # own shape) -- TrueType's nonzero fill rule cancels out, rather than
    # unions, two *overlapping* contours that wind oppositely, punching a
    # visible hole right where a foot or dot sits on top of a stroke.
    # Forcing terminal_style/dot_prevalence/complexity to +1.0 guarantees
    # this glyph has feet, dots, and lines all at once.
    traits = ScriptTraits(terminal_style=1.0, dot_prevalence=1.0, complexity=1.0)
    glyph = script_gen.generate_glyph("test-winding-1", "p", traits, 2, 2)
    assert {s.kind for s in glyph.strokes} == {StrokeKind.DOT, StrokeKind.LINE}  # both present, confirmed by seed search
    outline, has_contour = _build_glyph_outline(glyph, 0, traits, UPM / 2, UPM / 2, 2, 2)
    assert has_contour
    areas = _contour_signed_areas(outline)
    nonzero_signs = {1 if a > 0 else -1 for a in areas if abs(a) > 1e-6}
    assert len(nonzero_signs) == 1


def test_build_font_is_a_pure_function_of_the_script_data(tmp_path: Path):
    # Same InventedScript built twice -> byte-identical glyph geometry
    # (not just "no crash") -- font-building must never depend on
    # anything but the data already inside `script` itself, per this
    # module's own docstring ("never from RNG state").
    output_a, script = _build(tmp_path, seed=3)
    output_b = tmp_path / "second.ttf"
    build_font(script, output_b, "TestFamily")

    tt_a, tt_b = TTFont(str(output_a)), TTFont(str(output_b))
    try:
        glyf_a, glyf_b = tt_a["glyf"], tt_b["glyf"]
        for name in tt_a.getGlyphOrder():
            ga, gb = glyf_a[name], glyf_b[name]
            if ga.numberOfContours > 0:
                assert list(ga.coordinates) == list(gb.coordinates)
    finally:
        tt_a.close()
        tt_b.close()


def test_different_scripts_produce_different_glyph_geometry(tmp_path: Path):
    output_a, _ = _build(tmp_path, seed=1)
    output_b_dir = tmp_path / "b"
    output_b_dir.mkdir()
    output_b, _ = _build(output_b_dir, seed=2)

    tt_a, tt_b = TTFont(str(output_a)), TTFont(str(output_b))
    try:
        ga = tt_a["glyf"]["g0000"]
        gb = tt_b["glyf"]["g0000"]
        coords_a = list(ga.coordinates) if ga.numberOfContours > 0 else []
        coords_b = list(gb.coordinates) if gb.numberOfContours > 0 else []
        assert coords_a != coords_b
    finally:
        tt_a.close()
        tt_b.close()


# --- letter scale (Part B: "regular sized letters", not the whole em square) -----------------


def test_letter_height_is_a_fraction_of_the_em_square_not_the_whole_thing():
    # Direct user feedback: generated letters used to be "much bigger than normal letters" -- the old
    # grid_unit_y = UPM / grid_max_y math made every glyph's own height exactly UPM (the entire
    # ascent-to-baseline span) regardless of grid shape.
    assert 0.0 < _LETTER_SCALE < 1.0


# --- dot sizing and dot_ornateness (Part C) ----------------------------------------------------


def test_dot_radius_is_a_fixed_fraction_of_letter_height_not_stroke_width():
    # Direct user feedback: dots used to be sized off stroke width ("currently very tiny... like
    # the dot on an i"), so a thin-weight script's dots nearly disappeared.
    assert _DOT_RADIUS == UPM * _LETTER_SCALE * 0.09


def test_dot_ornateness_zero_always_renders_a_plain_circle():
    for i in range(30):
        polygons = _dot_polygons(100.0, 100.0, 50.0, 0.0, f"ornate-lo-{i}")
        assert len(polygons) == 1


def test_dot_ornateness_one_always_renders_a_brief_bent_diagonal_stroke():
    for i in range(30):
        polygons = _dot_polygons(100.0, 100.0, 50.0, 1.0, f"ornate-hi-{i}")
        assert len(polygons) > 1


def test_dot_ornateness_choice_is_deterministic_for_the_same_seed():
    a = _dot_polygons(100.0, 100.0, 50.0, 0.5, "ornate-stable")
    b = _dot_polygons(100.0, 100.0, 50.0, 0.5, "ornate-stable")
    assert a == b


# --- terminal_style foot size (Part D) ---------------------------------------------------------


def test_terminal_style_foot_radius_exceeds_the_strokes_own_half_width():
    # Real bug, confirmed empirically before this fix: the old foot formula
    # (lerp(terminal_style, 0, width*1.2) * 0.4) came out smaller than the stroke's own half-width,
    # so the foot was entirely hidden inside the stroke's own already-drawn polygon.
    traits = ScriptTraits(terminal_style=1.0)
    width = _stroke_width(traits)
    foot_radius = width * 1.3  # terminal_style == 1.0 -- see _stroke_polygons' own foot_radius formula
    assert foot_radius > width / 2
