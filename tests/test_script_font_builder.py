"""Tests for script.font_builder -- compiling an InventedScript into a
real TTF via fontTools. Round-trips every font it builds through a real
fontTools.ttLib.TTFont parse, not just a "no exception" check."""

import random
from pathlib import Path

import pytest

fontTools = pytest.importorskip("fontTools")
from fontTools.ttLib import TTFont  # noqa: E402

from conlang_generator.generation import script_gen
from conlang_generator.script.font_builder import build_font, codepoint_for_symbol_index
from tests._shared_language import cached_language


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
