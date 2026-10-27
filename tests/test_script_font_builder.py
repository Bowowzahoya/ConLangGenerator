"""Tests for script.font_builder -- compiling an InventedScript into a
real TTF via fontTools. Round-trips every font it builds through a real
fontTools.ttLib.TTFont parse, not just a "no exception" check."""

import math
from pathlib import Path

import pytest

fontTools = pytest.importorskip("fontTools")
from fontTools.ttLib import TTFont  # noqa: E402

from fontTools.pens.recordingPen import RecordingPen  # noqa: E402

from conlang_generator.core.script import Glyph, Point, ScriptTraits, Stroke, StrokeKind, WritingDirection
from conlang_generator.generation import script_gen
from conlang_generator.script.font_builder import (
    _DIACRITIC_GAP_FRACTION,
    _DIACRITIC_SCALE,
    _DOT_RADIUS,
    _LETTER_SCALE,
    _MIN_JOINT_ANGLE_DEGREES,
    _ROUNDING_SAFETY_CEILING,
    _TERMINAL_ORNAMENT_PRESETS,
    UPM,
    SerifRule,
    _build_connectivity,
    _build_glyph_outline,
    _bulge_through_point,
    _clamp_tilt_for_min_angle,
    _classify_orientation,
    _crooked_component_endpoints,
    _diacritic_offset,
    _dot_polygons,
    _ornament_main_points,
    _point_touch_counts,
    _render_scope,
    _round_endpoints,
    _roll_serif_rule,
    _roll_terminal_ornaments,
    _serif_polygons_for_stroke,
    _stroke_width,
    _terminal_ornament_polygons,
    _virtual_neighbor_direction,
    _weighted_dot_style,
    _weighted_ornament_preset,
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
    serif_rule = _roll_serif_rule(traits, "winding-test-fingerprint")
    outline, has_contour, _extent = _build_glyph_outline(
        glyph, 0, traits, UPM / 2, UPM / 2, 2, 2, WritingDirection.LTR, "winding-test-fingerprint", serif_rule,
    )
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


def test_weighted_dot_style_respects_the_low_ornateness_weight_boundaries():
    # At ornateness == 0.0, weights are square 0.38 / stroke 0.38 / circle 0.24 -- concentrated on
    # square/stroke, direct user phrasing ("low only one style of dots... more chance of stroke or
    # dot"), with circle raised from an original 0.16 for better default visibility (see
    # _DOT_STYLE_WEIGHTS_LOW's own docstring -- a whole-script single-roll mechanism meant the
    # original weight produced zero circles in ~84% of scripts, read as "I never see a circle").
    assert _weighted_dot_style(0.0, 0.0) == "square"
    assert _weighted_dot_style(0.37, 0.0) == "square"
    assert _weighted_dot_style(0.39, 0.0) == "stroke"
    assert _weighted_dot_style(0.75, 0.0) == "stroke"
    assert _weighted_dot_style(0.77, 0.0) == "circle"


def test_weighted_dot_style_respects_the_high_ornateness_weight_boundaries():
    # At ornateness == 1.0, weights are square 0.30 / stroke 0.30 / circle 0.40 -- flatter, slight
    # circle lean, direct user phrasing ("high randomly picking from all... slightly more chance of
    # circles").
    assert _weighted_dot_style(0.0, 1.0) == "square"
    assert _weighted_dot_style(0.29, 1.0) == "square"
    assert _weighted_dot_style(0.31, 1.0) == "stroke"
    assert _weighted_dot_style(0.59, 1.0) == "stroke"
    assert _weighted_dot_style(0.61, 1.0) == "circle"


def test_dot_polygons_is_deterministic_for_the_same_seed_and_fingerprint():
    a = _dot_polygons(100.0, 100.0, 50.0, 0.5, "dot-seed", "script-fp")
    b = _dot_polygons(100.0, 100.0, 50.0, 0.5, "dot-seed", "script-fp")
    assert a == b


def test_dot_polygons_at_zero_ornateness_always_reuses_the_script_wide_style():
    # use_per_dot = (stable_unit in [0,1]) < ornateness is never true at ornateness == 0.0, so every
    # dot sharing a script_fingerprint shares one style regardless of its own seed -- "low only one
    # style of dots," direct user phrasing.
    shapes = {
        len(_dot_polygons(100.0, 100.0, 50.0, 0.0, f"dot-seed-{i}", "shared-fingerprint")) for i in range(30)
    }
    assert len(shapes) == 1


def test_dot_polygons_at_full_ornateness_can_vary_per_dot():
    shapes = {
        len(_dot_polygons(100.0, 100.0, 50.0, 1.0, f"dot-seed-{i}", "shared-fingerprint")) for i in range(30)
    }
    assert len(shapes) > 1


def test_weighted_dot_style_can_reach_all_three_styles():
    styles = {_weighted_dot_style(roll / 100, 0.5) for roll in range(101)}
    assert styles == {"square", "stroke", "circle"}


# --- terminal ornaments (Part D) ----------------------------------------------------------------


def _line_glyph(points: list[tuple[int, int]]) -> Glyph:
    strokes = tuple(
        Stroke(kind=StrokeKind.LINE, start=Point(x=points[i][0], y=points[i][1]), end=Point(x=points[i + 1][0], y=points[i + 1][1]))
        for i in range(len(points) - 1)
    )
    return Glyph(ipa="x", strokes=strokes)


def test_roll_terminal_ornaments_is_empty_at_zero_terminal_style():
    glyph = _line_glyph([(0, 0), (2, 0), (2, 2)])
    traits = ScriptTraits(terminal_style=-1.0)
    for i in range(30):
        assert _roll_terminal_ornaments(glyph, f"ornament-none-{i}", traits, 2, 2) == []


def test_roll_terminal_ornaments_produces_some_at_full_terminal_style():
    glyph = _line_glyph([(0, 0), (2, 0), (2, 2)])
    traits = ScriptTraits(terminal_style=1.0)
    counts = [len(_roll_terminal_ornaments(glyph, f"ornament-some-{i}", traits, 2, 2)) for i in range(30)]
    assert any(c > 0 for c in counts)


def test_roll_terminal_ornaments_never_targets_a_glyph_with_no_line_strokes():
    glyph = Glyph(ipa="x", strokes=(Stroke(kind=StrokeKind.DOT, start=Point(x=0, y=0), end=Point(x=0, y=0)),))
    traits = ScriptTraits(terminal_style=1.0)
    assert _roll_terminal_ornaments(glyph, "ornament-dot-only", traits, 2, 2) == []


def test_weighted_ornament_preset_favors_plain_at_zero_ornateness_and_fancy_at_full():
    # A single roll's own index isn't meaningful on its own (the CDF always starts at index 0
    # regardless of ornateness) -- the actual shift is in the *distribution*, so compare the mean
    # picked index across many evenly spaced rolls instead.
    rolls = [i / 100 for i in range(100)]
    low_mean = sum(_weighted_ornament_preset(r, 0.0) for r in rolls) / len(rolls)
    high_mean = sum(_weighted_ornament_preset(r, 1.0) for r in rolls) / len(rolls)
    assert low_mean < high_mean


def test_terminal_ornament_polygons_produce_at_least_one_contour_for_every_preset():
    for preset in _TERMINAL_ORNAMENT_PRESETS:
        polygons = _terminal_ornament_polygons(
            100.0, 100.0, 1.0, 0.0, 40.0, preset, f"ornament-{preset.name}", 300.0,
        )
        assert polygons, preset.name


def test_terminal_ornament_centerline_length_scales_with_the_attached_strokes_own_length():
    # Direct user feedback: the ornament system reads as too tiny -- length_factor is now a fraction
    # of the attached stroke's own rendered length (see OrnamentPreset.length_factor's own docstring),
    # not a fixed UPM-absolute reference, so doubling the stroke length should double the centerline.
    preset = _TERMINAL_ORNAMENT_PRESETS[0]  # plain_foot -- a straight, unbent preset, easy to measure
    assert preset.bend_degrees == 0.0
    short = _ornament_main_points(0.0, 0.0, 1.0, 0.0, preset, 100.0)
    long = _ornament_main_points(0.0, 0.0, 1.0, 0.0, preset, 200.0)
    short_length = math.hypot(short[-1][0] - short[0][0], short[-1][1] - short[0][1])
    long_length = math.hypot(long[-1][0] - long[0][0], long[-1][1] - long[0][1])
    assert abs(long_length - 2 * short_length) < 1e-9
    # And most presets' own length_factor should land within the user's requested 0.2..0.6 band --
    # the two "extend beyond the normal letter size" presets are a deliberate, documented exception.
    exceptions = {"short_extension", "long_extension"}
    for p in _TERMINAL_ORNAMENT_PRESETS:
        if p.name not in exceptions:
            assert 0.2 <= p.length_factor <= 0.6, p.name


# --- serif (Part E) ------------------------------------------------------------------------------


def test_classify_orientation():
    assert _classify_orientation(0, 2) == "vertical"
    assert _classify_orientation(2, 0) == "horizontal"
    assert _classify_orientation(2, 2) == "diagonal"


def test_roll_serif_rule_is_a_no_op_at_zero_serif():
    traits = ScriptTraits(serif=0.0)
    rule = _roll_serif_rule(traits, "serif-fingerprint-zero")
    assert all(frac == 0.0 for frac in rule.coverage.values())


def test_roll_serif_rule_can_produce_nonzero_coverage_at_full_serif():
    # Each orientation class is independently rolled active-or-not, so a single fingerprint isn't
    # guaranteed every class fires -- check across several fingerprints that at least one class does.
    traits = ScriptTraits(serif=1.0)
    any_active = any(
        any(frac > 0.0 for frac in _roll_serif_rule(traits, f"serif-fingerprint-{i}").coverage.values())
        for i in range(20)
    )
    assert any_active


def test_roll_serif_rule_is_deterministic_for_the_same_fingerprint():
    traits = ScriptTraits(serif=1.0)
    a = _roll_serif_rule(traits, "serif-stable")
    b = _roll_serif_rule(traits, "serif-stable")
    assert a == b


def _first_nonempty_serif_polygons(stroke, width, key_prefix, rule):
    # `coverage == 1.0` still leaves a ~1/256 chance `_stable_unit`'s own include-roll lands exactly
    # on the boundary and excludes a given stroke_key (see `_serif_polygons_for_stroke`'s own
    # `include_roll >= coverage` check) -- try a handful of keys rather than risk a flaky one in a
    # test that isn't about that roll at all.
    for i in range(5):
        polygons = _serif_polygons_for_stroke(stroke, 0.0, 0.0, 0.0, 100.0, width, f"{key_prefix}-{i}", rule)
        if polygons:
            return polygons
    raise AssertionError("every candidate key was excluded by the include-roll")


def test_serif_polygons_for_stroke_radius_clearly_exceeds_the_strokes_own_half_width():
    # Direct user feedback: "serif doesn't seem to do anything" -- the un-floored radius used to be
    # only 0.96x..1.68x the stroke's own half-width across the whole weight range, so a "rounded"/
    # "triangle" foot centered right on the stroke's own tip mostly overlapped the stroke's own
    # existing silhouette. Checked across the whole weight range that the foot now clearly flares
    # well past it.
    for weight in (-1.0, 0.0, 1.0):
        traits = ScriptTraits(weight=weight, serif=1.0)
        width = _stroke_width(traits)
        rule = _roll_serif_rule(traits, f"serif-size-{weight}")._replace(
            coverage={"vertical": 1.0, "horizontal": 1.0, "diagonal": 1.0},
            sides_count={"vertical": 1, "horizontal": 1, "diagonal": 1},
            fixed_side={"vertical": "lower", "horizontal": "lower", "diagonal": "lower"},
            shape="rounded",
        )
        stroke = Stroke(kind=StrokeKind.LINE, start=Point(x=0, y=0), end=Point(x=0, y=2))
        polygons = _first_nonempty_serif_polygons(stroke, width, f"serif-size-key-{weight}", rule)
        assert len(polygons) == 1
        radius = max(math.hypot(px, py) for px, py in polygons[0])  # centered at (0, 0) -- the "lower" end
        assert radius > (width / 2) * 2.0


def test_serif_polygons_for_stroke_straight_shape_base_is_never_narrower_than_the_stroke():
    for weight in (-1.0, 0.0, 1.0):
        traits = ScriptTraits(weight=weight, serif=1.0)
        width = _stroke_width(traits)
        rule = _roll_serif_rule(traits, f"serif-straight-{weight}")._replace(
            coverage={"vertical": 1.0, "horizontal": 1.0, "diagonal": 1.0},
            sides_count={"vertical": 1, "horizontal": 1, "diagonal": 1},
            fixed_side={"vertical": "lower", "horizontal": "lower", "diagonal": "lower"},
            shape="straight",
        )
        stroke = Stroke(kind=StrokeKind.LINE, start=Point(x=0, y=0), end=Point(x=0, y=2))
        polygons = _first_nonempty_serif_polygons(stroke, width, f"serif-straight-key-{weight}", rule)
        assert len(polygons) == 1
        quad = polygons[0]  # `_quad`'s own point order: [0] and [-1] are both the base (near) edge
        base_span = math.hypot(quad[0][0] - quad[-1][0], quad[0][1] - quad[-1][1])
        assert base_span >= width


def test_serif_polygons_for_stroke_empty_when_its_own_class_has_zero_coverage():
    rule = SerifRule(
        coverage={"vertical": 0.0, "horizontal": 0.0, "diagonal": 0.0},
        sides_count={"vertical": 1, "horizontal": 1, "diagonal": 1},
        fixed_side={"vertical": "lower", "horizontal": "lower", "diagonal": "lower"},
        shape="rounded", thickness_factor=1.0,
    )
    stroke = Stroke(kind=StrokeKind.LINE, start=Point(x=0, y=0), end=Point(x=0, y=2))
    assert _serif_polygons_for_stroke(stroke, 0.0, 0.0, 0.0, 100.0, 40.0, "serif-stroke-key", rule) == []


def test_serif_polygons_for_stroke_draws_both_ends_when_sides_count_is_two():
    rule = SerifRule(
        coverage={"vertical": 1.0, "horizontal": 1.0, "diagonal": 1.0},
        sides_count={"vertical": 2, "horizontal": 2, "diagonal": 2},
        fixed_side={"vertical": "lower", "horizontal": "lower", "diagonal": "lower"},
        shape="triangle", thickness_factor=1.0,
    )
    stroke = Stroke(kind=StrokeKind.LINE, start=Point(x=0, y=0), end=Point(x=0, y=2))
    polygons = _serif_polygons_for_stroke(stroke, 0.0, 0.0, 0.0, 100.0, 40.0, "serif-stroke-key-both", rule)
    assert len(polygons) == 2


# --- diacritic placement (Part C) -----------------------------------------------------------------


def test_diacritic_offset_cross_axis_is_vertical_for_a_horizontal_direction():
    pos_x, pos_y = _diacritic_offset("cross_pos", WritingDirection.LTR, 2, 2, 100.0, 100.0)
    neg_x, neg_y = _diacritic_offset("cross_neg", WritingDirection.LTR, 2, 2, 100.0, 100.0)
    assert pos_x == neg_x  # horizontally centered either way
    assert pos_y != neg_y  # vertically, above vs. below


def test_diacritic_offset_cross_axis_is_horizontal_for_a_vertical_direction():
    pos_x, pos_y = _diacritic_offset("cross_pos", WritingDirection.TTB_LTR, 2, 2, 100.0, 100.0)
    neg_x, neg_y = _diacritic_offset("cross_neg", WritingDirection.TTB_LTR, 2, 2, 100.0, 100.0)
    assert pos_y == neg_y  # vertically centered either way
    assert pos_x != neg_x  # horizontally, left vs. right


def test_diacritic_offset_internal_slots_land_inside_the_main_glyphs_own_bounding_box():
    # The center of the diacritic's own box at the middle grid point (1,1) should land near the main
    # glyph's own center, not flush against an edge the way every external slot does.
    x, y = _diacritic_offset("internal:1,1", WritingDirection.LTR, 2, 2, 100.0, 100.0)
    width_diac = 200.0 * _DIACRITIC_SCALE
    height_diac = 200.0 * _DIACRITIC_SCALE
    assert abs((x + width_diac / 2) - 100.0) < 1e-9
    assert abs((y + height_diac / 2) - 100.0) < 1e-9


def test_diacritic_offset_external_slots_are_separated_from_the_main_glyphs_own_edge():
    # Direct user feedback: diacritics "mix up with the letter too much" -- an external slot must sit
    # a real gap past the main glyph's own edge now, not flush against it.
    _, top_y = _diacritic_offset("cross_pos", WritingDirection.LTR, 2, 2, 100.0, 100.0)
    assert top_y > 200.0  # height_main = 2*100 -- flush would be exactly 200.0
    _, bottom_y = _diacritic_offset("cross_neg", WritingDirection.LTR, 2, 2, 100.0, 100.0)
    height_diac = 200.0 * _DIACRITIC_SCALE
    assert bottom_y < -height_diac  # flush would be exactly -height_diac
    # Internal slots are deliberately unaffected -- nested by design, no edge to separate from.
    width_diac = height_diac = 200.0 * _DIACRITIC_SCALE
    x_internal, y_internal = _diacritic_offset("internal:0,0", WritingDirection.LTR, 2, 2, 100.0, 100.0)
    assert x_internal == -width_diac / 2.0
    assert y_internal == -height_diac / 2.0


def test_diacritic_offset_gap_is_twenty_percent_of_the_main_glyphs_own_size():
    # Direct user ask, round 8: the pass-55 gap ("mix up with the letter too much") still read as too
    # small -- "a blank space of 20% the size of the character."
    assert _DIACRITIC_GAP_FRACTION == pytest.approx(0.20)
    height_main = 200.0
    _, top_y = _diacritic_offset("cross_pos", WritingDirection.LTR, 2, 2, 100.0, 100.0)
    assert top_y == pytest.approx(height_main + height_main * 0.20)


# --- connectivity (Part A) --------------------------------------------------------------------------


def _line(sx: int, sy: int, ex: int, ey: int) -> Stroke:
    return Stroke(kind=StrokeKind.LINE, start=Point(x=sx, y=sy), end=Point(x=ex, y=ey))


def _dot_stroke(x: int, y: int) -> Stroke:
    return Stroke(kind=StrokeKind.DOT, start=Point(x=x, y=y), end=Point(x=x, y=y))


def test_build_connectivity_groups_connected_line_strokes():
    strokes = (_line(0, 0, 1, 0), _line(1, 0, 1, 1), _line(1, 1, 2, 2))
    components = _build_connectivity(strokes)
    assert len(components) == 1
    assert len(components[0].order) == 4  # 4 distinct points, 3 strokes, no closing edge
    assert components[0].closing_edges == []


def test_build_connectivity_a_dot_does_not_break_the_component():
    strokes = (_line(0, 0, 1, 0), _dot_stroke(2, 2), _line(1, 0, 1, 1))
    components = _build_connectivity(strokes)
    assert len(components) == 1  # the dot is ignored entirely; strokes 0 and 2 still connect


def test_build_connectivity_a_pen_lift_starts_a_new_component():
    strokes = (_line(0, 0, 1, 0), _line(2, 2, 2, 1))  # second doesn't touch the first anywhere
    assert len(_build_connectivity(strokes)) == 2


def test_build_connectivity_dot_only_strokes_produce_no_components():
    assert _build_connectivity((_dot_stroke(0, 0), _dot_stroke(1, 1))) == []


def test_build_connectivity_links_strokes_that_touch_by_chance_not_just_list_order():
    # Direct user feedback: "if they are connected by chance, they should count as actually
    # connected." Stroke 1 touches stroke 0's own point, but isn't list-consecutive with it (its own
    # `start` doesn't match stroke 0's `end`) -- the old `_find_chains` would have missed this.
    strokes = (_line(0, 0, 1, 0), _line(2, 2, 1, 0))
    components = _build_connectivity(strokes)
    assert len(components) == 1
    assert len(components[0].order) == 3


def test_build_connectivity_a_closed_loop_produces_exactly_one_closing_edge():
    # A square: 4 strokes, 4 points, back to the start -- a spanning tree over 4 points needs only 3
    # edges, so exactly one of the 4 strokes must be a closing edge.
    strokes = (_line(0, 0, 0, 2), _line(0, 2, 2, 2), _line(2, 2, 2, 0), _line(2, 0, 0, 0))
    components = _build_connectivity(strokes)
    assert len(components) == 1
    assert len(components[0].order) == 4
    assert len(components[0].closing_edges) == 1


# --- crookedness (Part B) ---------------------------------------------------------------------------


def _crooked(strokes: tuple[Stroke, ...], traits, key: str) -> dict[int, tuple[float, float, float, float]]:
    crooked: dict[int, tuple[float, float, float, float]] = {}
    for component in _build_connectivity(strokes):
        crooked.update(_crooked_component_endpoints(strokes, component, traits, key, 100.0, 100.0, 0.0, 0.0))
    return crooked


def test_crooked_component_endpoints_never_tilts_at_zero_crookedness():
    strokes = (_line(0, 0, 2, 0), _line(2, 0, 2, 2))
    traits = ScriptTraits(crookedness=0.0)
    endpoints = _crooked(strokes, traits, "g")
    x0, y0, x1, y1 = endpoints[0]
    assert abs(y1 - y0) < 1e-9  # stays horizontal (canonical angle 0)
    x0b, y0b, x1b, y1b = endpoints[1]
    assert abs(x1b - x0b) < 1e-9  # stays vertical


def test_crooked_component_endpoints_stays_connected_across_a_chain():
    # "The next stroke should move its start point along" -- every chain-interior joint must stay
    # exactly glued, even at full crookedness.
    strokes = (_line(0, 0, 2, 0), _line(2, 0, 2, 2), _line(2, 2, 0, 2))
    traits = ScriptTraits(crookedness=1.0)
    endpoints = _crooked(strokes, traits, "connectivity-check")
    for a, b in ((0, 1), (1, 2)):
        ax0, ay0, ax1, ay1 = endpoints[a]
        bx0, by0, bx1, by1 = endpoints[b]
        assert abs(ax1 - bx0) < 1e-9
        assert abs(ay1 - by0) < 1e-9


def test_crooked_component_endpoints_keeps_a_touch_by_chance_connected():
    # The round-7 fix itself: stroke 1 touches stroke 0's own endpoint without being its list
    # successor -- it must stay glued there even at full crookedness (direct user feedback: a P's own
    # loop plus an attached final stroke, turning it into an R, must not visibly disconnect).
    strokes = (_line(0, 0, 2, 0), _line(3, 2, 2, 0))
    traits = ScriptTraits(crookedness=1.0)
    for seed in range(20):
        endpoints = _crooked(strokes, traits, f"touch-check-{seed}")
        ax0, ay0, ax1, ay1 = endpoints[0]
        bx0, by0, bx1, by1 = endpoints[1]
        assert abs(ax1 - bx1) < 1e-6
        assert abs(ay1 - by1) < 1e-6


def test_crooked_component_endpoints_keeps_a_closed_loop_closed():
    # Direct user feedback: "a closed off square can turn into a circle, diamond or blob but not
    # disconnect" -- the loop's own closing edge is never independently tilted, so its two endpoints
    # always land exactly where the tree walk already placed them.
    strokes = (_line(0, 0, 0, 2), _line(0, 2, 2, 2), _line(2, 2, 2, 0), _line(2, 0, 0, 0))
    traits = ScriptTraits(crookedness=1.0)
    for seed in range(20):
        endpoints = _crooked(strokes, traits, f"loop-check-{seed}")
        # Walk the 4 strokes in their own stored order and confirm each one's end matches the next
        # one's start (wrapping around) -- a closed ring, regardless of which stroke the connectivity
        # builder happened to pick as the non-tilted closing edge.
        for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
            ax0, ay0, ax1, ay1 = endpoints[a]
            bx0, by0, bx1, by1 = endpoints[b]
            assert abs(ax1 - bx0) < 1e-6
            assert abs(ay1 - by0) < 1e-6


def test_crooked_component_endpoints_preserves_each_strokes_own_length():
    strokes = (_line(0, 0, 2, 0), _line(2, 0, 2, 2))
    traits = ScriptTraits(crookedness=1.0)
    endpoints = _crooked(strokes, traits, "length-check")
    for idx in (0, 1):
        x0, y0, x1, y1 = endpoints[idx]
        canonical_length = math.hypot(
            (strokes[idx].end.x - strokes[idx].start.x) * 100.0, (strokes[idx].end.y - strokes[idx].start.y) * 100.0,
        )
        assert abs(math.hypot(x1 - x0, y1 - y0) - canonical_length) < 1e-6


def test_crooked_component_endpoints_never_tilts_past_45_degrees_at_full_crookedness():
    strokes = (_line(0, 0, 2, 0),)
    traits = ScriptTraits(crookedness=1.0)
    for seed in range(40):
        endpoints = _crooked(strokes, traits, f"angle-bound-{seed}")
        x0, y0, x1, y1 = endpoints[0]
        angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
        assert abs(angle) <= 45.0 + 1e-6


def test_crooked_component_endpoints_is_deterministic():
    strokes = (_line(0, 0, 2, 0), _line(2, 0, 2, 2))
    traits = ScriptTraits(crookedness=0.7)
    a = _crooked(strokes, traits, "determinism-check")
    b = _crooked(strokes, traits, "determinism-check")
    assert a == b


def test_clamp_tilt_for_min_angle_passes_through_a_safe_tilt_unchanged():
    assert _clamp_tilt_for_min_angle(math.radians(0.0), 10.0, math.radians(90.0)) == 10.0


def test_clamp_tilt_for_min_angle_shrinks_a_tilt_that_would_fold_back():
    # canonical=250, arrival=90 -- "retrace" (the forbidden direction) is at 90+180=270 degrees. A
    # candidate tilt of 20 degrees lands the outgoing angle exactly on 270 (full fold-back).
    canonical, arrival, tilt = math.radians(250.0), math.radians(90.0), 20.0
    clamped = _clamp_tilt_for_min_angle(canonical, tilt, arrival)
    assert 0.0 <= clamped < tilt
    resulting_angle_deg = math.degrees(canonical) + clamped
    forbidden_deg = math.degrees(arrival) + 180.0
    interior = abs(((resulting_angle_deg - forbidden_deg + 180) % 360) - 180)
    assert interior >= _MIN_JOINT_ANGLE_DEGREES - 1e-6


def test_crooked_component_endpoints_never_produces_a_sub_minimum_interior_angle():
    # Direct user feedback: "extreme crookedness sometimes leads to really tiny angles" -- across many
    # seeds and a 3-stroke right-angle chain (each canonical turn 90 degrees, well within reach of a
    # +/-45-degree tilt on each side folding toward the other), no interior angle at either interior
    # joint should ever drop below the minimum.
    strokes = (_line(0, 0, 2, 0), _line(2, 0, 2, 2), _line(2, 2, 0, 2))
    traits = ScriptTraits(crookedness=1.0)
    for seed in range(60):
        endpoints = _crooked(strokes, traits, f"min-angle-{seed}")
        for a, b in ((0, 1), (1, 2)):
            ax0, ay0, ax1, ay1 = endpoints[a]
            bx0, by0, bx1, by1 = endpoints[b]
            incoming = math.atan2(ay1 - ay0, ax1 - ax0)
            outgoing = math.atan2(by1 - by0, bx1 - bx0)
            forbidden = incoming + math.pi
            interior = abs(((outgoing - forbidden + math.pi) % (2 * math.pi)) - math.pi)
            assert math.degrees(interior) >= _MIN_JOINT_ANGLE_DEGREES - 1e-3


# --- roundedness (Part C) ---------------------------------------------------------------------------


def test_bulge_through_point_is_zero_when_target_is_on_the_chord_itself():
    assert abs(_bulge_through_point(0.0, 0.0, 10.0, 0.0, 5.0, 0.0)) < 1e-9


def test_bulge_through_point_is_nonzero_for_a_target_off_the_chord():
    assert _bulge_through_point(0.0, 0.0, 10.0, 0.0, 5.0, 4.0) != 0.0


def test_virtual_neighbor_direction_continues_verbatim_when_not_isolated():
    # "Continue the bend of the bend after it" -- when the stroke's other end is shared with
    # something else, no perturbation at all.
    vdx, vdy = _virtual_neighbor_direction(1.0, 0.0, False, "any-key", 1.0)
    assert abs(vdx - 1.0) < 1e-9
    assert abs(vdy - 0.0) < 1e-9


def test_virtual_neighbor_direction_adds_a_bounded_random_offset_when_isolated():
    for seed in range(30):
        vdx, vdy = _virtual_neighbor_direction(1.0, 0.0, True, f"offset-{seed}", 1.0)
        delta = math.degrees(math.atan2(vdy, vdx))
        delta = (delta + 180) % 360 - 180
        assert abs(delta) <= 90.0 + 1e-6


def test_virtual_neighbor_direction_offset_is_zero_at_zero_roundedness():
    vdx, vdy = _virtual_neighbor_direction(1.0, 0.0, True, "any-key", 0.0)
    assert abs(vdx - 1.0) < 1e-9
    assert abs(vdy - 0.0) < 1e-9


def test_round_endpoints_is_a_no_op_at_zero_roundedness():
    strokes = (_line(0, 0, 2, 0), _line(2, 0, 2, 2))
    traits = ScriptTraits(crookedness=0.0, roundedness=0.0)
    crooked = _crooked(strokes, traits, "noop")
    segments, arcs, rounded_start, rounded_end = _round_endpoints(strokes, crooked, traits, "noop")
    assert arcs == []
    assert segments == crooked
    assert not any(rounded_start.values())
    assert not any(rounded_end.values())


def test_round_endpoints_truncates_by_the_described_linear_fraction():
    # "100% means from 50% along one stroke to 50% along the second" -- f = roundedness * 0.5. Uses
    # roundedness=0.6 (f=0.3, 2f=0.6) rather than 1.0 so the result is never ambiguous with the safety
    # clamp (which only ever engages above a 0.9 combined fraction) -- that's covered separately below.
    # Searches for a seed whose own joint roll actually selects (not every seed's own roll does at a
    # sub-1.0 roundedness), the same seed-search pattern this test module already uses elsewhere.
    strokes = (_line(0, 0, 2, 0), _line(2, 0, 2, 2))
    traits = ScriptTraits(crookedness=0.0, roundedness=0.6)
    f = 0.3
    for seed in range(50):
        key = f"midpoint-check-{seed}"
        crooked = _crooked(strokes, traits, key)
        segments, arcs, rounded_start, rounded_end = _round_endpoints(strokes, crooked, traits, key)
        if rounded_end[0] and rounded_start[1]:
            ax0, ay0, ax1, ay1 = crooked[0]
            seg_ax0, seg_ay0, seg_ax1, seg_ay1 = segments[0]
            assert abs(seg_ax1 - (ax0 + (ax1 - ax0) * (1 - f))) < 1e-6
            assert abs(seg_ay1 - (ay0 + (ay1 - ay0) * (1 - f))) < 1e-6
            assert len(arcs) >= 1
            return
    raise AssertionError("no seed produced a selected joint to test against")


def test_round_endpoints_loose_end_never_reaches_further_than_the_original_stroke():
    # Direct user feedback: "that was not my intention, I just meant it to turn away at an angle, but
    # not become longer" -- across many seeds, no point on any rounding arc should land further from
    # the stroke's own well-connected end than the stroke's own original length.
    strokes = (_line(0, 0, 2, 2),)
    traits = ScriptTraits(roundedness=1.0)
    for seed in range(40):
        key = f"no-overshoot-{seed}"
        crooked = _crooked(strokes, traits, key)
        x0, y0, x1, y1 = crooked[0]
        original_length = math.hypot(x1 - x0, y1 - y0)
        segments, arcs, rounded_start, rounded_end = _round_endpoints(strokes, crooked, traits, key)
        for ax0, ay0, ax1, ay1, bulge in arcs:
            assert math.hypot(ax0 - x0, ay0 - y0) <= original_length + 1e-6
            assert math.hypot(ax1 - x0, ay1 - y0) <= original_length + 1e-6


def test_round_endpoints_keeps_a_touch_by_chance_connected():
    # The round-7 fix: two strokes sharing a point they weren't list-chained through must round (or
    # not) as ONE joint decision, never disconnecting -- direct user feedback's own "outcrop" report.
    strokes = (_line(0, 0, 2, 0), _line(3, 2, 2, 0))
    traits = ScriptTraits(roundedness=1.0)
    for seed in range(20):
        key = f"touch-round-{seed}"
        crooked = _crooked(strokes, traits, key)
        segments, arcs, rounded_start, rounded_end = _round_endpoints(strokes, crooked, traits, key)
        # Both sides of the shared point must agree -- either both rounded or neither.
        assert rounded_end[0] == rounded_end[1]


def test_round_endpoints_leaves_a_degree_three_branch_point_untouched():
    # Three strokes meeting at one point -- a deliberate, flagged scope limit: no rounding there at
    # all, regardless of roundedness.
    strokes = (_line(0, 0, 1, 1), _line(1, 1, 2, 0), _line(2, 2, 1, 1))
    traits = ScriptTraits(roundedness=1.0)
    crooked = _crooked(strokes, traits, "branch-check")
    segments, arcs, rounded_start, rounded_end = _round_endpoints(strokes, crooked, traits, "branch-check")
    assert rounded_end[0] is False
    assert rounded_start[1] is False
    assert rounded_end[2] is False


def test_round_endpoints_safety_clamp_prevents_a_stroke_collapsing_to_zero_length():
    # An isolated stroke can have BOTH its own loose ends independently selected -- without the clamp,
    # f=0.5 on each side would consume the stroke's entire length (and then some).
    strokes = (_line(0, 0, 2, 0),)
    traits = ScriptTraits(crookedness=0.0, roundedness=1.0)
    crooked = _crooked(strokes, traits, "safety-clamp-check")
    segments, arcs, rounded_start, rounded_end = _round_endpoints(strokes, crooked, traits, "safety-clamp-check")
    assert rounded_start[0] and rounded_end[0]
    x0, y0, x1, y1 = segments[0]
    remaining = math.hypot(x1 - x0, y1 - y0)
    full = math.hypot(crooked[0][2] - crooked[0][0], crooked[0][3] - crooked[0][1])
    assert remaining >= full * (1.0 - _ROUNDING_SAFETY_CEILING) - 1e-6
    assert remaining >= -1e-9  # never negative


def test_round_endpoints_is_deterministic():
    strokes = (_line(0, 0, 2, 0), _line(2, 0, 2, 2))
    traits = ScriptTraits(crookedness=0.0, roundedness=0.6)
    crooked = _crooked(strokes, traits, "round-determinism")
    a = _round_endpoints(strokes, crooked, traits, "round-determinism")
    b = _round_endpoints(strokes, crooked, traits, "round-determinism")
    assert a == b


# --- serif/terminal-ornament skip a rounded endpoint (Part E) --------------------------------------


def test_serif_polygons_for_stroke_respects_availability_flags():
    rule = SerifRule(
        coverage={"vertical": 1.0, "horizontal": 1.0, "diagonal": 1.0},
        sides_count={"vertical": 2, "horizontal": 2, "diagonal": 2},
        fixed_side={"vertical": "lower", "horizontal": "lower", "diagonal": "lower"},
        shape="rounded", thickness_factor=1.0,
    )
    stroke = Stroke(kind=StrokeKind.LINE, start=Point(x=0, y=0), end=Point(x=0, y=2))
    both = _serif_polygons_for_stroke(stroke, 0.0, 0.0, 0.0, 100.0, 40.0, "avail-both", rule)
    start_only = _serif_polygons_for_stroke(
        stroke, 0.0, 0.0, 0.0, 100.0, 40.0, "avail-both", rule, start_available=True, end_available=False,
    )
    neither = _serif_polygons_for_stroke(
        stroke, 0.0, 0.0, 0.0, 100.0, 40.0, "avail-both", rule, start_available=False, end_available=False,
    )
    assert len(both) == 2
    assert len(start_only) == 1
    assert neither == []


def test_roll_terminal_ornaments_excludes_every_rounded_endpoint():
    glyph = _line_glyph([(0, 0), (2, 0), (2, 2)])
    traits = ScriptTraits(terminal_style=1.0, ornateness=0.5)
    rounded_start = {0: True, 1: True}
    rounded_end = {0: True, 1: True}
    for i in range(20):
        assert _roll_terminal_ornaments(glyph, f"excl-{i}", traits, 2, 2, rounded_start, rounded_end) == []


# --- _render_scope integration (Part E) -------------------------------------------------------------


def test_render_scope_produces_polygons_and_consistent_segments():
    strokes = (_line(0, 0, 2, 0), _line(2, 0, 2, 2))
    traits = ScriptTraits(crookedness=0.5, roundedness=0.5, weight=0.0)
    fingerprint = "render-scope-check"
    serif_rule = _roll_serif_rule(traits, fingerprint)
    polygons, xs, rounded_start, rounded_end, segments = _render_scope(
        strokes, traits, "g", 100.0, 100.0, 0.0, 0.0, fingerprint, serif_rule,
    )
    assert polygons
    assert set(segments) == {0, 1}
    assert xs


def test_render_scope_handles_a_dot_only_scope():
    strokes = (_dot_stroke(1, 1),)
    traits = ScriptTraits()
    fingerprint = "dot-only-check"
    serif_rule = _roll_serif_rule(traits, fingerprint)
    polygons, xs, rounded_start, rounded_end, segments = _render_scope(
        strokes, traits, "g", 100.0, 100.0, 0.0, 0.0, fingerprint, serif_rule,
    )
    assert polygons
    assert segments == {}


def test_point_touch_counts_classifies_degree_by_how_many_stroke_ends_share_a_point():
    strokes = (_line(0, 0, 2, 0), _line(3, 2, 2, 0))
    counts = _point_touch_counts(strokes)
    assert counts[Point(x=2, y=0)] == 2  # both strokes' own end
    assert counts[Point(x=0, y=0)] == 1  # stroke 0's own loose start
    assert counts[Point(x=3, y=2)] == 1  # stroke 1's own loose start


def test_render_scope_excludes_a_touch_by_chance_point_even_at_zero_roundedness():
    # Direct user feedback: a terminal ornament/serif should "only be added to genuine ends," e.g.
    # the stroke that turns a P into an R must not decorate the point where it touches the P -- this
    # must hold even when roundedness never fires at all (previously, eligibility was keyed only to
    # "did rounding claim this end," so an un-rounded touch stayed "available").
    strokes = (_line(0, 0, 2, 0), _line(3, 2, 2, 0))
    traits = ScriptTraits(roundedness=0.0)
    fingerprint = "genuine-end-fingerprint"
    serif_rule = _roll_serif_rule(traits, fingerprint)
    _polygons, _xs, rounded_start, rounded_end, _segments = _render_scope(
        strokes, traits, "g", 100.0, 100.0, 0.0, 0.0, fingerprint, serif_rule,
    )
    # Point (2, 0) -- stroke 0's own end and stroke 1's own end -- is a genuine joint, not available.
    assert rounded_end[0] is True
    assert rounded_end[1] is True
    # Each stroke's own OTHER end is a true, degree-1 loose end -- still available.
    assert rounded_start[0] is False
    assert rounded_start[1] is False
