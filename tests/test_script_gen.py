"""Tests for generation.script_gen -- rolling an InventedScript's own
direction/style and generating one glyph per phoneme. Every glyph's own
stroke content is addressably seeded (see script_gen's own module
docstring) -- several tests below exist specifically to pin that
property down, since it's what makes a script tweak (generator.
regenerate_script) able to redraw a stroke only when its own inputs
actually changed."""

import random

from conlang_generator.core.script import SCRIPT_TRAIT_RANGE, Point, ScriptTraits, ScriptTraitsForce, StrokeKind, WritingDirection
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
        lo, hi = SCRIPT_TRAIT_RANGE[name]
        value = getattr(traits, name)
        assert lo <= value <= hi


def test_roll_script_traits_rolls_unipolar_dials_within_0_to_1_over_many_draws():
    # A single roll could land anywhere in its own range by chance -- roll many to actually exercise
    # the unipolar dials' own [0.0, 1.0] bound (not the bipolar default [-1.0, 1.0]) across the board.
    unipolar = [name for name, (lo, hi) in SCRIPT_TRAIT_RANGE.items() if lo == 0.0]
    assert unipolar  # sanity: at least one unipolar dial exists (stroke_contrast/regularity/dot_ornateness)
    for seed in range(50):
        traits = script_gen.roll_script_traits(random.Random(seed))
        for name in unipolar:
            assert 0.0 <= getattr(traits, name) <= 1.0


def test_roll_script_traits_with_no_force_is_unaffected():
    traits = script_gen.roll_script_traits(random.Random(1), ScriptTraitsForce())
    assert traits == script_gen.roll_script_traits(random.Random(1))


def test_roll_script_traits_applies_a_forced_dial():
    traits = script_gen.roll_script_traits(random.Random(1), ScriptTraitsForce(dot_prevalence=1.0, weight=-1.0))
    assert traits.dot_prevalence == 1.0
    assert traits.weight == -1.0


def test_roll_script_traits_force_does_not_disturb_the_rng_stream():
    # The forced dial's own value replaces the roll's result -- it must
    # not skip or add an rng draw, or every *other* unforced dial would
    # silently shift too.
    unforced = script_gen.roll_script_traits(random.Random(1))
    forced = script_gen.roll_script_traits(random.Random(1), ScriptTraitsForce(dot_prevalence=0.99))
    for name in ScriptTraits.model_fields:
        if name == "dot_prevalence":
            continue
        assert getattr(forced, name) == getattr(unforced, name)


def test_generate_script_applies_forced_script_traits():
    language = cached_language(0)
    script = script_gen.generate_script("1", language.phonology, ScriptTraitsForce(complexity=1.0))
    assert script.traits.complexity == 1.0


def test_generate_script_is_reproducible_for_the_same_seed():
    language = cached_language(0)
    script_a = script_gen.generate_script("1", language.phonology)
    script_b = script_gen.generate_script("1", language.phonology)
    assert script_a == script_b


def test_generate_script_differs_for_a_different_seed():
    language = cached_language(0)
    script_a = script_gen.generate_script("1", language.phonology)
    script_b = script_gen.generate_script("2", language.phonology)
    assert script_a != script_b


def test_generate_script_covers_exactly_the_languages_own_inventory():
    language = cached_language(0)
    script = script_gen.generate_script("1", language.phonology)
    expected = language.phonology.consonant_symbols() + language.phonology.vowel_symbols()
    assert tuple(g.ipa for g in script.glyphs) == expected


def test_every_glyph_has_at_least_one_stroke():
    language = cached_language(0)
    script = script_gen.generate_script("1", language.phonology)
    for glyph in script.glyphs:
        assert len(glyph.strokes) >= 1


def test_generation_never_produces_an_arc_stroke():
    # Phase 1 drawing is lines (and dots) only -- roundedness (renamed from angularity) synthesizes
    # rounded corners entirely at render time (script.font_builder), never a generation-time line-vs-arc
    # choice (see ScriptTraits.roundedness's own docstring); forcing it to its own max must still never
    # produce a stored ARC stroke.
    language = cached_language(0)
    script = script_gen.generate_script("1", language.phonology, ScriptTraitsForce(roundedness=1.0))
    for glyph in script.glyphs:
        assert all(s.kind is not StrokeKind.ARC for s in glyph.strokes)


def test_every_line_stroke_runs_along_a_cell_boundary_or_diagonal():
    language = cached_language(0)
    script = script_gen.generate_script("7", language.phonology, ScriptTraitsForce(complexity=1.0, dot_prevalence=0.3))
    for glyph in script.glyphs:
        for s in glyph.strokes:
            if s.kind is not StrokeKind.LINE:
                continue
            dx, dy = s.end.x - s.start.x, s.end.y - s.start.y
            assert (dx, dy) != (0, 0)
            assert dx == 0 or dy == 0 or abs(dx) == abs(dy)


def test_high_complexity_produces_more_strokes_than_low_complexity():
    minimal = script_gen.generate_glyph("complexity-test", "p", ScriptTraits(complexity=-1.0), 2, 2)
    ornate = script_gen.generate_glyph("complexity-test", "p", ScriptTraits(complexity=1.0), 2, 2)
    assert len(ornate.strokes) > len(minimal.strokes)


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
    script = script_gen.generate_script("1", language.phonology)
    assert (script.grid_max_x, script.grid_max_y) in {(2, 2), (1, 2), (2, 1)}
    for glyph in script.glyphs:
        for stroke in glyph.strokes:
            assert 0 <= stroke.start.x <= script.grid_max_x
            assert 0 <= stroke.start.y <= script.grid_max_y
            assert 0 <= stroke.end.x <= script.grid_max_x
            assert 0 <= stroke.end.y <= script.grid_max_y


# --- stroke continuity -----------------------------------------------------------------------


def test_high_stroke_continuity_chains_almost_every_stroke_to_the_last_ones_end():
    traits = ScriptTraits(stroke_continuity=1.0, complexity=1.0)
    glyph = script_gen.generate_glyph("continuity-test-3", "p", traits, 2, 2)
    chain = [s for s in glyph.strokes if s.kind is not StrokeKind.DOT]
    chained = sum(1 for prev, nxt in zip(chain, chain[1:]) if nxt.start == prev.end)
    assert chained >= len(chain) - 2  # almost every stroke continues from the last; a rare lift is fine


def test_low_stroke_continuity_rarely_chains_strokes():
    traits = ScriptTraits(stroke_continuity=-1.0, complexity=1.0)
    glyph = script_gen.generate_glyph("continuity-test-3", "p", traits, 2, 2)
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


def test_a_forced_dot_prevalence_does_not_disturb_other_dials_rng_draws():
    unforced = script_gen.roll_script_traits(random.Random(1))
    forced = script_gen.roll_script_traits(random.Random(1), ScriptTraitsForce(dot_prevalence=0.99))
    for name in ScriptTraits.model_fields:
        if name == "dot_prevalence":
            continue
        assert getattr(forced, name) == getattr(unforced, name)


# --- dot prevalence --------------------------------------------------------------------------


def test_high_dot_prevalence_produces_more_dots_than_low():
    traits_low = ScriptTraits(dot_prevalence=-1.0, complexity=1.0)
    traits_high = ScriptTraits(dot_prevalence=1.0, complexity=1.0)
    low_dots = sum(
        1
        for seed in range(1, 30)
        for s in script_gen.generate_glyph(f"dot-{seed}", "p", traits_low, 2, 2).strokes
        if s.kind is StrokeKind.DOT
    )
    high_dots = sum(
        1
        for seed in range(1, 30)
        for s in script_gen.generate_glyph(f"dot-{seed}", "p", traits_high, 2, 2).strokes
        if s.kind is StrokeKind.DOT
    )
    assert high_dots > low_dots


def test_a_dot_slot_does_not_break_the_chain():
    # The next real line stroke after a dot slot continues from wherever the chain was *before*
    # the dot, not from the dot's own position.
    traits = ScriptTraits(dot_prevalence=1.0, stroke_continuity=1.0, complexity=1.0)
    for seed in range(1, 60):
        strokes = script_gen.generate_glyph(f"chain-{seed}", "p", traits, 2, 2).strokes
        for i in range(len(strokes) - 2):
            if strokes[i].kind is StrokeKind.DOT:
                continue
            if strokes[i + 1].kind is StrokeKind.DOT and strokes[i + 2].kind is not StrokeKind.DOT:
                assert strokes[i + 2].start == strokes[i].end
                return
    raise AssertionError("no seed produced a line-dot-line sequence to test against")


# --- addressable seeding (the property script tweaking relies on) --------------------------------


def test_decide_stroke_is_a_pure_function_of_its_own_inputs():
    traits = ScriptTraits(stroke_continuity=0.5, dot_prevalence=0.2)
    a = script_gen._decide_stroke("pure-fn", 7, Point(x=0, y=0), (1, 0), traits, 2, 2, set())
    b = script_gen._decide_stroke("pure-fn", 7, Point(x=0, y=0), (1, 0), traits, 2, 2, set())
    assert a == b


def test_build_one_attempt_keeps_earlier_indices_stable_when_stroke_count_increases():
    # The core "retrace" property: a longer chain's own first N strokes are byte-identical to the
    # shorter chain's full output, when nothing else about those indices' own inputs changed --
    # tested directly against `_build_one_attempt` (bypassing the corner-coverage retry wrapper,
    # which could legitimately pick a different attempt number for a different stroke count).
    key = "retrace-prefix"
    traits = ScriptTraits(stroke_continuity=0.0, dot_prevalence=-1.0)
    short = script_gen._build_one_attempt(key, traits, 3, 2, 2)
    long = script_gen._build_one_attempt(key, traits, 5, 2, 2)
    assert long[:3] == short


def test_build_one_attempt_truncates_cleanly_when_stroke_count_decreases():
    key = "retrace-truncate"
    traits = ScriptTraits(stroke_continuity=0.0, dot_prevalence=-1.0)
    long = script_gen._build_one_attempt(key, traits, 5, 2, 2)
    short = script_gen._build_one_attempt(key, traits, 3, 2, 2)
    assert short == long[:3]


# --- corner coverage -------------------------------------------------------------------------


def test_every_generated_glyph_touches_enough_grid_corners():
    language = cached_language(0)
    script = script_gen.generate_script("5", language.phonology, ScriptTraitsForce(complexity=1.0))
    corners = {
        (0, 0), (0, script.grid_max_y), (script.grid_max_x, 0), (script.grid_max_x, script.grid_max_y),
    }
    for glyph in script.glyphs:
        touched = {(s.start.x, s.start.y) for s in glyph.strokes} | {(s.end.x, s.end.y) for s in glyph.strokes}
        assert len(touched & corners) >= 2  # the gate's own lower bound (complexity<=0 case)


# --- no-retrace (a chained stroke never runs back along the stroke that fed it) --------------


def test_valid_line_partners_excludes_the_parallel_direction_when_chaining():
    start = Point(x=1, y=1)
    partners = script_gen._valid_line_partners(start, 2, 2, exclude_direction=(1, 0))
    for p in partners:
        dx, dy = p.x - start.x, p.y - start.y
        assert dx * 0 - dy * 1 != 0  # never collinear with (1, 0) -- the same cross-product check the function itself uses


def test_valid_line_partners_falls_back_to_unfiltered_when_exclusion_would_empty_it():
    # On the smallest grid, filtering out one direction can legitimately leave nothing -- must fall
    # back to the unfiltered list rather than ever returning empty.
    start = Point(x=0, y=0)
    unfiltered = script_gen._valid_line_partners(start, 1, 1)
    assert len(unfiltered) <= 3  # a 1x1 (2x2-point) grid has very few candidates to begin with
    # Excluding every one of unfiltered's own directions in turn must never produce an empty result.
    for p in unfiltered:
        direction = (p.x - start.x, p.y - start.y)
        filtered = script_gen._valid_line_partners(start, 1, 1, exclude_direction=direction)
        assert filtered  # falls back to the unfiltered list rather than ever being empty


def test_valid_line_partners_without_exclusion_is_unaffected():
    start = Point(x=1, y=1)
    assert script_gen._valid_line_partners(start, 2, 2, exclude_direction=None) == script_gen._valid_line_partners(
        start, 2, 2,
    )


def test_build_one_attempt_rarely_retraces_the_incoming_strokes_own_direction():
    # Direct user feedback: a chained stroke running back along the same line as the one that fed it
    # "doesn't add anything... sometimes makes two letters look exactly the same." Full continuity
    # forces chaining on every slot, maximizing the chance to catch a retrace if the exclusion logic
    # were missing; occasional retraces from the documented small-grid fallback are expected, routine
    # retracing is not.
    traits = ScriptTraits(stroke_continuity=1.0, complexity=1.0)
    chained_pairs = 0
    retraces = 0
    for seed in range(300):
        strokes = script_gen._build_one_attempt(f"no-retrace-{seed}", traits, 6, 2, 2)
        lines = [s for s in strokes if s.kind is StrokeKind.LINE]
        for prev, nxt in zip(lines, lines[1:]):
            if nxt.start != prev.end:
                continue
            chained_pairs += 1
            dx0, dy0 = prev.end.x - prev.start.x, prev.end.y - prev.start.y
            dx1, dy1 = nxt.end.x - nxt.start.x, nxt.end.y - nxt.start.y
            if dx0 * dy1 - dy0 * dx1 == 0:
                retraces += 1
    assert chained_pairs > 0
    assert retraces / chained_pairs < 0.05  # rare fallback cases only, not routine


# --- duplicate-glyph detection ----------------------------------------------------------------


def test_generate_script_never_produces_two_glyphs_with_the_same_signature():
    # A tiny grid with low complexity has few genuinely distinct possible shapes -- the stress case
    # most likely to produce an accidental collision without the duplicate-retry logic.
    language = cached_language(0)
    script = script_gen.generate_script(
        "dup-stress", language.phonology, ScriptTraitsForce(complexity=-1.0, dot_prevalence=-1.0),
    )
    signatures = [script_gen._glyph_signature(g) for g in script.glyphs]
    assert len(signatures) == len(set(signatures))


def test_glyph_signature_differs_for_different_strokes_but_matches_for_identical_ones():
    a = script_gen.generate_glyph("sig-a", "p", ScriptTraits(complexity=1.0), 2, 2)
    b = script_gen.generate_glyph("sig-a", "p", ScriptTraits(complexity=1.0), 2, 2)
    c = script_gen.generate_glyph("sig-c", "t", ScriptTraits(complexity=-1.0), 2, 2)
    assert script_gen._glyph_signature(a) == script_gen._glyph_signature(b)
    assert script_gen._glyph_signature(a) != script_gen._glyph_signature(c)


# --- diacritic dot-prevalence boost ------------------------------------------------------------


def test_is_diacritic_raises_the_dot_prevalence_ceiling():
    # Same dot_prevalence value, only is_diacritic differs -- direct user request: "dots should also
    # have a higher chance to be generated in diacritics, but still scale with dot prevalence."
    traits = ScriptTraits(dot_prevalence=1.0)
    main_dots = sum(
        1
        for seed in range(200)
        if script_gen._decide_stroke(f"dot-boost-{seed}", 0, None, None, traits, 2, 2, set(), False).kind
        is StrokeKind.DOT
    )
    diacritic_dots = sum(
        1
        for seed in range(200)
        if script_gen._decide_stroke(f"dot-boost-{seed}", 0, None, None, traits, 2, 2, set(), True).kind
        is StrokeKind.DOT
    )
    assert diacritic_dots > main_dots


def test_is_diacritic_still_scales_with_dot_prevalence():
    traits_low = ScriptTraits(dot_prevalence=-1.0)
    traits_high = ScriptTraits(dot_prevalence=1.0)
    low_dots = sum(
        1
        for seed in range(200)
        if script_gen._decide_stroke(f"dot-scale-{seed}", 0, None, None, traits_low, 2, 2, set(), True).kind
        is StrokeKind.DOT
    )
    high_dots = sum(
        1
        for seed in range(200)
        if script_gen._decide_stroke(f"dot-scale-{seed}", 0, None, None, traits_high, 2, 2, set(), True).kind
        is StrokeKind.DOT
    )
    assert high_dots > low_dots


# --- diacritic placement (direction-aware, ornateness-driven) -----------------------------------


def test_roll_diacritic_slot_is_always_cross_axis_at_zero_ornateness():
    traits = ScriptTraits(ornateness=0.0)
    slots = {
        script_gen._roll_diacritic_slot(f"slot-lo-{i}", traits, WritingDirection.LTR) for i in range(100)
    }
    assert slots <= {"cross_pos", "cross_neg"}


def test_roll_diacritic_slot_reaches_every_category_at_full_ornateness():
    traits = ScriptTraits(ornateness=1.0)
    slots = {
        script_gen._roll_diacritic_slot(f"slot-hi-{i}", traits, WritingDirection.LTR) for i in range(300)
    }
    assert any(s.startswith("cross") for s in slots)
    assert any(s.startswith("along") for s in slots)
    assert any(s.startswith("internal:") for s in slots)


def test_roll_diacritic_slot_fixed_sign_is_script_wide_not_per_instance():
    # At zero ornateness, _roll_diacritic_slot's own flip chance is also zero -- every instance across
    # the whole script must agree on the same single fixed sign ("always in the same location").
    traits = ScriptTraits(ornateness=0.0)
    slots = {
        script_gen._roll_diacritic_slot(f"slot-fixed-{i}", traits, WritingDirection.LTR) for i in range(50)
    }
    assert len(slots) == 1


def test_script_wide_seed_is_unaffected_by_a_non_topology_dial():
    # Real bug, caught by direct testing (regenerate_script with only weight/slant forced changed a
    # diacritic's own stored slot, violating "non-topology dials never touch stroke data"): the old
    # implementation hashed the *entire* traits blob, so any render-only field change -- even one
    # SCRIPT_TRAIT_GROUP classifies as non-topology -- could flip the script-wide fixed sign. Only the
    # topology-group dials (plus ornateness, the documented exception) may ever change it.
    base = ScriptTraits(weight=-0.8, slant=0.3, serif=0.9, terminal_style=-0.5, stroke_contrast=0.7)
    tweaked = base.model_copy(update={"weight": 0.9, "slant": -0.7, "serif": 0.0, "terminal_style": 1.0})
    assert script_gen._script_wide_seed(base, WritingDirection.LTR) == script_gen._script_wide_seed(
        tweaked, WritingDirection.LTR
    )


def test_script_wide_seed_changes_with_a_topology_relevant_dial():
    base = ScriptTraits(complexity=0.0)
    tweaked = base.model_copy(update={"complexity": 0.9})
    assert script_gen._script_wide_seed(base, WritingDirection.LTR) != script_gen._script_wide_seed(
        tweaked, WritingDirection.LTR
    )


def test_build_diacritic_pool_size_scales_with_diacritic_density():
    traits = ScriptTraits(diacritic_density=0.0)
    assert script_gen._build_diacritic_pool("pool-size", traits, 2, 2, WritingDirection.LTR) == ()

    traits = ScriptTraits(diacritic_density=1.0)
    pool = script_gen._build_diacritic_pool("pool-size", traits, 2, 2, WritingDirection.LTR)
    assert len(pool) == script_gen._DIACRITIC_POOL_MAX


def test_build_diacritic_pool_never_rounds_a_positive_density_down_to_empty():
    # round(lerp01(0.1, 0, 5)) == round(0.5) == 0 in plain Python rounding -- without the floor, a
    # letter that *does* roll a diacritic (a real possibility at density=0.1) would have nothing to
    # draw from.
    traits = ScriptTraits(diacritic_density=0.1)
    pool = script_gen._build_diacritic_pool("pool-floor", traits, 2, 2, WritingDirection.LTR)
    assert len(pool) >= 1


def test_build_diacritic_pool_caps_strokes_at_four_even_at_full_ornateness():
    traits = ScriptTraits(diacritic_density=1.0, ornateness=1.0, complexity=1.0)
    for seed in range(30):
        pool = script_gen._build_diacritic_pool(f"stroke-cap-{seed}", traits, 2, 2, WritingDirection.LTR)
        assert all(len(d.strokes) <= script_gen._DIACRITIC_MAX_STROKES_CAP for d in pool)


def test_build_diacritic_pool_widens_stroke_count_ceiling_with_ornateness():
    traits_lo = ScriptTraits(diacritic_density=1.0, ornateness=0.0, complexity=1.0)
    traits_hi = ScriptTraits(diacritic_density=1.0, ornateness=1.0, complexity=1.0)
    lo_strokes = max(
        len(d.strokes)
        for seed in range(30)
        for d in script_gen._build_diacritic_pool(f"stroke-ceiling-{seed}", traits_lo, 2, 2, WritingDirection.LTR)
    )
    hi_strokes = max(
        len(d.strokes)
        for seed in range(30)
        for d in script_gen._build_diacritic_pool(f"stroke-ceiling-{seed}", traits_hi, 2, 2, WritingDirection.LTR)
    )
    assert hi_strokes > lo_strokes


def test_pool_diacritics_never_carry_their_own_diacritics():
    traits = ScriptTraits(diacritic_density=1.0, complexity=1.0)
    pool = script_gen._build_diacritic_pool("no-nesting", traits, 2, 2, WritingDirection.LTR)
    assert pool
    assert all(d.diacritics == {} for d in pool)


def test_attach_diacritics_attaches_roughly_half_of_letters_at_density_one_half():
    traits = ScriptTraits(diacritic_density=0.5, ornateness=0.3)
    pool = script_gen._build_diacritic_pool("attach-rate", traits, 2, 2, WritingDirection.LTR)
    attached = sum(
        1 for i in range(2000)
        if script_gen._attach_diacritics(f"letter-{i}", traits, WritingDirection.LTR, pool)
    )
    assert 850 < attached < 1150  # ~50% of 2000, loose statistical band


def test_attach_diacritics_never_attaches_a_second_one_at_low_density():
    traits = ScriptTraits(diacritic_density=0.5, ornateness=0.3)
    pool = script_gen._build_diacritic_pool("second-rate-low", traits, 2, 2, WritingDirection.LTR)
    counts = [
        len(script_gen._attach_diacritics(f"letter-{i}", traits, WritingDirection.LTR, pool))
        for i in range(2000)
    ]
    assert counts.count(2) / len(counts) < 0.05


def test_attach_diacritics_can_attach_a_second_one_close_to_full_density():
    traits = ScriptTraits(diacritic_density=1.0, ornateness=0.3)
    pool = script_gen._build_diacritic_pool("second-rate-high", traits, 2, 2, WritingDirection.LTR)
    counts = [
        len(script_gen._attach_diacritics(f"letter-{i}", traits, WritingDirection.LTR, pool))
        for i in range(2000)
    ]
    assert counts.count(2) / len(counts) > 0.2
    assert max(counts) == 2


def test_attach_diacritics_reuses_pool_entries_by_identity():
    traits = ScriptTraits(diacritic_density=1.0, ornateness=0.3, complexity=0.5)
    pool = script_gen._build_diacritic_pool("reuse-check", traits, 2, 2, WritingDirection.LTR)
    seen_strokes = set()
    for i in range(50):
        for d in script_gen._attach_diacritics(f"letter-{i}", traits, WritingDirection.LTR, pool).values():
            seen_strokes.add(d.strokes)
    pool_strokes = {d.strokes for d in pool}
    assert seen_strokes <= pool_strokes  # every attached diacritic came from the pool, nothing fresh
    assert len(seen_strokes) <= len(pool)
