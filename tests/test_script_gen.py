"""Tests for generation.script_gen -- rolling an InventedScript's own
direction/style and generating one glyph per phoneme."""

import random

from conlang_generator.core.script import ScriptTraits, StrokeKind, WritingDirection
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
    glyph = script_gen.generate_glyph(rng, "p", traits)
    assert all(s.kind is StrokeKind.LINE for s in glyph.strokes if s.kind is not StrokeKind.DOT)


def test_low_angularity_produces_mostly_arc_strokes():
    rng = random.Random(1)
    traits = ScriptTraits(angularity=-1.0, complexity=1.0)
    glyph = script_gen.generate_glyph(rng, "p", traits)
    assert all(s.kind is StrokeKind.ARC for s in glyph.strokes if s.kind is not StrokeKind.DOT)


def test_high_complexity_produces_more_strokes_than_low_complexity():
    rng_a = random.Random(1)
    rng_b = random.Random(1)
    minimal = script_gen.generate_glyph(rng_a, "p", ScriptTraits(complexity=-1.0))
    ornate = script_gen.generate_glyph(rng_b, "p", ScriptTraits(complexity=1.0))
    assert len(ornate.strokes) > len(minimal.strokes)


def test_high_symmetry_glyph_strokes_mirror_across_the_vertical_center():
    rng = random.Random(1)
    traits = ScriptTraits(symmetry=1.0, complexity=1.0)
    glyph = script_gen.generate_glyph(rng, "p", traits)
    lines_and_arcs = [s for s in glyph.strokes if s.kind is not StrokeKind.DOT]
    mirrored_xs = {3 - s.start.x for s in lines_and_arcs} | {3 - s.end.x for s in lines_and_arcs}
    actual_xs = {s.start.x for s in lines_and_arcs} | {s.end.x for s in lines_and_arcs}
    # Every mirrored x should itself appear somewhere in the actual set --
    # a necessary (not sufficient, given random pairing) signature of
    # genuine left-right symmetry.
    assert mirrored_xs <= actual_xs or not lines_and_arcs
