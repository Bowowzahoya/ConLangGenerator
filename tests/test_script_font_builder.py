"""Tests for script.font_builder -- compiling an InventedScript into a
real TTF via fontTools. Round-trips every font it builds through a real
fontTools.ttLib.TTFont parse, not just a "no exception" check."""

import random
from pathlib import Path

import pytest

fontTools = pytest.importorskip("fontTools")
from fontTools.ttLib import TTFont  # noqa: E402

from fontTools.pens.recordingPen import RecordingPen  # noqa: E402

from conlang_generator.core.script import ScriptTraits
from conlang_generator.generation import script_gen
from conlang_generator.script.font_builder import UPM, _build_glyph_outline, build_font, codepoint_for_symbol_index
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
    script = script_gen.generate_script(random.Random(seed), language.phonology)
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
    # to wind the opposite direction from `_quad` (every line/arc stroke's
    # own shape) -- TrueType's nonzero fill rule cancels out, rather than
    # unions, two *overlapping* contours that wind oppositely, punching a
    # visible hole right where a foot or dot sits on top of a stroke.
    # Forcing terminal_style/diacritic_density/complexity/symmetry to +1.0
    # guarantees this glyph has feet, dots, lines, and arcs all at once.
    traits = ScriptTraits(terminal_style=1.0, diacritic_density=1.0, complexity=1.0, symmetry=1.0, angularity=0.0)
    glyph = script_gen.generate_glyph(random.Random(1), "p", traits, 2, 2)
    outline, has_contour = _build_glyph_outline(glyph, 0, traits, UPM / 2, UPM / 2)
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
