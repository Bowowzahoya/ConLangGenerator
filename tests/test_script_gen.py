"""Tests for generation.script_gen -- rolling an InventedScript's own
direction/style and generating one glyph per phoneme."""

import random

from conlang_generator.core.script import Glyph, Point, ScriptTraits, ScriptTraitsForce, StrokeKind, WritingDirection
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import script_gen
from tests._shared_language import cached_language


def test_should_generate_script_defaults_to_false():
    assert script_gen.should_generate_script(GenerationSpec(prompt="p", seed=1)) is False


def test_force_own_script_wins_either_direction_over_requested():
    spec_force_on = GenerationSpec(
        prompt="p", seed=1, force_own_script=True, traits=TraitProfile(requested_own_script="no")
    )
    assert script_gen.should_generate_script(spec_force_on) is True

    spec_force_off = GenerationSpec(
        prompt="p", seed=1, force_own_script=False, traits=TraitProfile(requested_own_script="yes")
    )
    assert script_gen.should_generate_script(spec_force_off) is False


def test_requested_own_script_is_used_when_not_forced():
    spec = GenerationSpec(prompt="p", seed=1, traits=TraitProfile(requested_own_script="yes"))
    assert script_gen.should_generate_script(spec) is True


def test_roll_direction_only_ever_returns_a_real_direction():
    rng = random.Random(1)
    for _ in range(50):
        assert script_gen.roll_direction(rng) in set(WritingDirection)


def test_roll_script_traits_covers_every_field_in_range():
    traits = script_gen.roll_script_traits(random.Random(1))
    for name in ScriptTraits.model_fields:
        value = getattr(traits, name)
        assert -1.0 <= value <= 1.0


def test_roll_script_traits_with_no_force_is_unaffected():
    traits = script_gen.roll_script_traits(random.Random(1), ScriptTraitsForce())
    assert traits == script_gen.roll_script_traits(random.Random(1))


def test_roll_script_traits_applies_a_forced_dial():
    traits = script_gen.roll_script_traits(random.Random(1), ScriptTraitsForce(angularity=1.0, weight=-1.0))
    assert traits.angularity == 1.0
    assert traits.weight == -1.0


def test_roll_script_traits_force_does_not_disturb_the_rng_stream():
    # The forced dial's own value replaces the roll's result -- it must
    # not skip or add an rng draw, or every *other* unforced dial would
    # silently shift too.
    unforced = script_gen.roll_script_traits(random.Random(1))
    forced = script_gen.roll_script_traits(random.Random(1), ScriptTraitsForce(angularity=0.99))
    for name in ScriptTraits.model_fields:
        if name == "angularity":
            continue
        assert getattr(forced, name) == getattr(unforced, name)


def test_generate_script_applies_forced_script_traits():
    language = cached_language(0)
    script = script_gen.generate_script(
        random.Random(1), language.phonology, ScriptTraitsForce(complexity=1.0)
    )
    assert script.traits.complexity == 1.0


def test_generate_script_is_reproducible_for_the_same_seed():
    language = cached_language(0)
    script_a = script_gen.generate_script(random.Random(1), language.phonology)
    script_b = script_gen.generate_script(random.Random(1), language.phonology)
    assert script_a == script_b


def test_generate_script_differs_for_a_different_seed():
    language = cached_language(0)
    script_a = script_gen.generate_script(random.Random(1), language.phonology)
    script_b = script_gen.generate_script(random.Random(2), language.phonology)
    assert script_a != script_b


def test_generate_script_covers_exactly_the_languages_own_inventory():
    language = cached_language(0)
    script = script_gen.generate_script(random.Random(1), language.phonology)
    expected = language.phonology.consonant_symbols() + language.phonology.vowel_symbols()
    assert tuple(g.ipa for g in script.glyphs) == expected


def test_every_glyph_has_at_least_one_stroke():
    language = cached_language(0)
    script = script_gen.generate_script(random.Random(1), language.phonology)
    for glyph in script.glyphs:
        assert len(glyph.strokes) >= 1


def test_high_angularity_produces_mostly_line_strokes():
    rng = random.Random(1)
    traits = ScriptTraits(angularity=1.0, complexity=1.0)
    glyph = script_gen.generate_glyph(rng, "p", traits, 2, 2)
    assert all(s.kind is StrokeKind.LINE for s in glyph.strokes if s.kind is not StrokeKind.DOT)


def test_low_angularity_produces_mostly_arc_strokes():
    rng = random.Random(1)
    traits = ScriptTraits(angularity=-1.0, complexity=1.0)
    glyph = script_gen.generate_glyph(rng, "p", traits, 2, 2)
    assert all(s.kind is StrokeKind.ARC for s in glyph.strokes if s.kind is not StrokeKind.DOT)


def test_high_complexity_produces_more_strokes_than_low_complexity():
    rng_a = random.Random(1)
    rng_b = random.Random(1)
    minimal = script_gen.generate_glyph(rng_a, "p", ScriptTraits(complexity=-1.0), 2, 2)
    ornate = script_gen.generate_glyph(rng_b, "p", ScriptTraits(complexity=1.0), 2, 2)
    assert len(ornate.strokes) > len(minimal.strokes)


def test_high_symmetry_glyph_strokes_mirror_across_the_vertical_center():
    rng = random.Random(1)
    traits = ScriptTraits(symmetry=1.0, complexity=1.0)
    grid_max_x = 2
    glyph = script_gen.generate_glyph(rng, "p", traits, grid_max_x, 2)
    lines_and_arcs = [s for s in glyph.strokes if s.kind is not StrokeKind.DOT]
    mirrored_xs = {grid_max_x - s.start.x for s in lines_and_arcs} | {grid_max_x - s.end.x for s in lines_and_arcs}
    actual_xs = {s.start.x for s in lines_and_arcs} | {s.end.x for s in lines_and_arcs}
    # Every mirrored x should itself appear somewhere in the actual set --
    # a necessary (not sufficient, given random pairing) signature of
    # genuine left-right symmetry.
    assert mirrored_xs <= actual_xs or not lines_and_arcs


# --- grid shape ----------------------------------------------------------------------------------


def test_roll_grid_shape_only_ever_returns_one_of_the_three_weighted_shapes():
    rng = random.Random(1)
    seen = set()
    for _ in range(100):
        shape = script_gen.roll_grid_shape(rng)
        assert shape in {(2, 2), (1, 2), (2, 1)}
        seen.add(shape)
    assert seen == {(2, 2), (1, 2), (2, 1)}  # all three reachable over enough draws


def test_generate_script_persists_the_rolled_grid_shape():
    language = cached_language(0)
    script = script_gen.generate_script(random.Random(1), language.phonology)
    assert (script.grid_max_x, script.grid_max_y) in {(2, 2), (1, 2), (2, 1)}
    for glyph in script.glyphs:
        for stroke in glyph.strokes:
            assert 0 <= stroke.start.x <= script.grid_max_x
            assert 0 <= stroke.start.y <= script.grid_max_y
            assert 0 <= stroke.end.x <= script.grid_max_x
            assert 0 <= stroke.end.y <= script.grid_max_y


# --- stroke continuity -----------------------------------------------------------------------


def test_high_stroke_continuity_chains_almost_every_stroke_to_the_last_ones_end():
    rng = random.Random(3)
    traits = ScriptTraits(stroke_continuity=1.0, complexity=1.0, symmetry=-1.0)
    glyph = script_gen.generate_glyph(rng, "p", traits, 2, 2)
    chain = [s for s in glyph.strokes if s.kind is not StrokeKind.DOT]
    chained = sum(1 for prev, nxt in zip(chain, chain[1:]) if nxt.start == prev.end)
    assert chained >= len(chain) - 2  # almost every stroke continues from the last; a rare lift is fine


def test_low_stroke_continuity_rarely_chains_strokes():
    rng = random.Random(3)
    traits = ScriptTraits(stroke_continuity=-1.0, complexity=1.0, symmetry=-1.0)
    glyph = script_gen.generate_glyph(rng, "p", traits, 2, 2)
    chain = [s for s in glyph.strokes if s.kind is not StrokeKind.DOT]
    chained = sum(1 for prev, nxt in zip(chain, chain[1:]) if nxt.start == prev.end)
    assert chained <= 2  # occasional coincidental chaining is fine, routine chaining is not


def test_a_forced_stroke_continuity_does_not_disturb_other_dials_rng_draws():
    unforced = script_gen.roll_script_traits(random.Random(1))
    forced = script_gen.roll_script_traits(random.Random(1), ScriptTraitsForce(stroke_continuity=0.99))
    for name in ScriptTraits.model_fields:
        if name == "stroke_continuity":
            continue
        assert getattr(forced, name) == getattr(unforced, name)


# --- corner coverage -------------------------------------------------------------------------


def test_every_generated_glyph_touches_enough_grid_corners():
    language = cached_language(0)
    script = script_gen.generate_script(random.Random(5), language.phonology, ScriptTraitsForce(complexity=1.0))
    corners = {
        (0, 0), (0, script.grid_max_y), (script.grid_max_x, 0), (script.grid_max_x, script.grid_max_y),
    }
    for glyph in script.glyphs:
        touched = {(s.start.x, s.start.y) for s in glyph.strokes} | {(s.end.x, s.end.y) for s in glyph.strokes}
        assert len(touched & corners) >= 2  # the gate's own lower bound (complexity<=0 case)


# --- connectivity (cross-glyph baseline joining) ---------------------------------------------


def _sample_glyph(rng_seed: int) -> Glyph:
    rng = random.Random(rng_seed)
    traits = ScriptTraits(complexity=1.0)
    return script_gen.generate_glyph(rng, "p", traits, 2, 2)


def test_high_connectivity_pins_the_glyphs_entry_and_exit_to_the_ltr_baseline():
    glyph = _sample_glyph(4)
    traits = ScriptTraits(connectivity=1.0)
    joined = script_gen._apply_connectivity(glyph, traits, WritingDirection.LTR, grid_max_x=2)
    non_dot = [s for s in joined.strokes if s.kind is not StrokeKind.DOT]
    assert non_dot[0].start == Point(x=0, y=0)
    assert non_dot[-1].end == Point(x=2, y=0)


def test_high_connectivity_swaps_entry_and_exit_for_rtl():
    glyph = _sample_glyph(4)
    traits = ScriptTraits(connectivity=1.0)
    joined = script_gen._apply_connectivity(glyph, traits, WritingDirection.RTL, grid_max_x=2)
    non_dot = [s for s in joined.strokes if s.kind is not StrokeKind.DOT]
    assert non_dot[0].start == Point(x=2, y=0)
    assert non_dot[-1].end == Point(x=0, y=0)


def test_low_connectivity_is_a_no_op():
    glyph = _sample_glyph(4)
    traits = ScriptTraits(connectivity=0.3)
    assert script_gen._apply_connectivity(glyph, traits, WritingDirection.LTR, grid_max_x=2) == glyph


def test_connectivity_is_a_no_op_for_vertical_directions():
    glyph = _sample_glyph(4)
    traits = ScriptTraits(connectivity=1.0)
    assert script_gen._apply_connectivity(glyph, traits, WritingDirection.TTB_LTR, grid_max_x=2) == glyph


def test_connectivity_override_never_targets_a_diacritic_dot():
    traits = ScriptTraits(complexity=1.0, diacritic_density=1.0)
    glyph = None
    for seed in range(1, 50):
        candidate = script_gen.generate_glyph(random.Random(seed), "p", traits, 2, 2)
        if candidate.strokes and candidate.strokes[-1].kind is StrokeKind.DOT:
            glyph = candidate
            break
    assert glyph is not None, "no seed produced a trailing diacritic dot to test against"
    joined = script_gen._apply_connectivity(glyph, ScriptTraits(connectivity=1.0), WritingDirection.LTR, grid_max_x=2)
    assert joined.strokes[-1].kind is StrokeKind.DOT
    assert joined.strokes[-1] == glyph.strokes[-1]  # the dot itself is untouched by the override
