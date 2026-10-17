"""Builds an ``InventedScript`` for a language: a writing direction, a
rolled ``ScriptTraits`` style, and one procedurally generated ``Glyph``
per phoneme in the language's own inventory.

Two separate decisions, kept deliberately separate:

- *whether* a language gets a script at all (``should_generate_script``)
  -- the two-channel "explicit override beats inferred beats default"
  pattern every other optional feature in this project already follows
  (see ``core.spec.GenerationSpec.force_own_script``/``core.traits.
  TraitProfile.requested_own_script``).
- *what it looks like* (everything else in this module) -- rolled from
  the language's own seed, not (yet) inferred from the free-text prompt.
  Wiring a script's own visual style to prompt wording would mean
  extracting several new graded dimensions through ``prompt_classifier.
  py``'s already-large, already-costly system prompt (see docs/
  DEFERRED.md's own "Trait-classifier call is expensive" item) -- a
  separate, bigger piece of work than this phase, not attempted here.

Only phase 1 (a simple alphabet: one atomic glyph per phoneme, no
composition) is implemented. See ``core.script``'s own module docstring
for how a later abugida/syllable-block system would extend this without
a redesign.
"""

from __future__ import annotations

import random

from conlang_generator.core.phonology import PhonemeInventory
from conlang_generator.core.script import (
    Glyph,
    InventedScript,
    Point,
    ScriptTraits,
    ScriptTraitsForce,
    Stroke,
    StrokeKind,
    WritingDirection,
    lerp,
)
from conlang_generator.core.spec import GenerationSpec

_DIRECTION_WEIGHTS: tuple[tuple[WritingDirection, float], ...] = (
    (WritingDirection.LTR, 0.5),
    (WritingDirection.RTL, 0.2),
    (WritingDirection.TTB_LTR, 0.15),
    (WritingDirection.TTB_RTL, 0.1),
    (WritingDirection.BOUSTROPHEDON, 0.05),
)
"""Illustrative, not a sourced real-world script-direction census -- just
weighted toward the broadly more common patterns (most living scripts
are LTR; RTL and top-to-bottom each have real, smaller families; true
boustrophedon is historical/rare today)."""

_MIN_STROKES = 2
_MAX_STROKES = 6
_GRID_MAX = 3  # Point.x/y range 0..3, see core.script.Point


def should_generate_script(spec: GenerationSpec) -> bool:
    """Explicit ``force_own_script`` wins outright, either direction;
    otherwise ``traits.requested_own_script`` ("yes"/"no"/""); otherwise
    ``False`` -- generating a script is a heavier, optional artifact
    (eventually a real compiled font), so an *absence* of any signal
    means skip it, the same "nothing happens unless asked" precedent
    `--pregenerate-audio`/`"auto"` TTS already follow elsewhere in this
    project, not a 50/50 roll."""
    if spec.force_own_script is not None:
        return spec.force_own_script
    return spec.traits.requested_own_script == "yes"


def roll_direction(rng: random.Random) -> WritingDirection:
    directions, weights = zip(*_DIRECTION_WEIGHTS)
    return rng.choices(directions, weights=weights, k=1)[0]


def roll_script_traits(rng: random.Random, force: ScriptTraitsForce = ScriptTraitsForce()) -> ScriptTraits:
    """Rolls all 15 dials, then applies any non-``None`` field of
    ``force`` on top (see ``ScriptTraitsForce``'s own docstring) --
    every ``rng`` draw still happens even for a forced dial, so adding or
    removing an override never shifts any other dial's own value."""
    fields = ScriptTraits.model_fields
    rolled = {name: round(rng.uniform(-1.0, 1.0), 2) for name in fields}
    overrides = {name: value for name, value in force.model_dump().items() if value is not None}
    return ScriptTraits(**{**rolled, **overrides})


def _random_point(rng: random.Random, y_max: int) -> Point:
    return Point(x=rng.randint(0, _GRID_MAX), y=rng.randint(0, y_max))


def _random_line_or_arc(rng: random.Random, traits: ScriptTraits, y_max: int) -> Stroke:
    # angularity +1 -> never an arc; -1 -> always an arc.
    is_arc = rng.random() < lerp(-traits.angularity, 0.0, 1.0)
    start = _random_point(rng, y_max)
    end = _random_point(rng, y_max)
    tries = 0
    while end == start and tries < 5:  # a zero-length stroke draws nothing
        end = _random_point(rng, y_max)
        tries += 1
    if not is_arc:
        return Stroke(kind=StrokeKind.LINE, start=start, end=end)
    # Smoother (more negative angularity) -> a bigger bulge; sign is
    # independent of angularity, just which side the curve bends to.
    magnitude = lerp(-traits.angularity, 0.1, 0.6)
    bulge = magnitude if rng.random() < 0.5 else -magnitude
    return Stroke(kind=StrokeKind.ARC, start=start, end=end, bulge=round(bulge, 2))


def _mirror_point(p: Point) -> Point:
    return Point(x=_GRID_MAX - p.x, y=p.y)


def _mirror_stroke(s: Stroke) -> Stroke:
    return Stroke(kind=s.kind, start=_mirror_point(s.start), end=_mirror_point(s.end), bulge=-s.bulge)


def generate_glyph(rng: random.Random, ipa: str, traits: ScriptTraits) -> Glyph:
    """One phoneme's own glyph -- a handful of stroke primitives placed
    on the fixed grid, styled by ``traits``. See this module's own
    docstring for which of ``ScriptTraits``' 15 dials this function
    itself consumes (stroke topology) versus ``script.font_builder``
    (rendering) versus not yet consumed at all (``connectivity`` --
    true cursive joining needs positional glyph variants, a genuinely
    bigger OpenType feature, the same "extracted, not yet consumed"
    honesty `core.traits.TraitProfile` already applies to several of its
    own fields)."""
    # height_variance: this one glyph, not the whole script, rolls
    # whether it's full-height or restricted to the lower rows (an
    # x-height-only look) -- the *rate* that happens at is what gives
    # the trait its visible effect across the whole glyph set.
    y_max = _GRID_MAX
    if rng.random() < lerp(traits.height_variance, 0.0, 0.5):
        y_max = _GRID_MAX - 1

    stroke_count = round(lerp(traits.complexity, _MIN_STROKES, _MAX_STROKES))
    strokes: list[Stroke] = []

    if traits.symmetry > 0.3:
        half = max(1, stroke_count // 2)
        for _ in range(half):
            s = _random_line_or_arc(rng, traits, y_max)
            strokes.append(s)
            strokes.append(_mirror_stroke(s))
        if stroke_count % 2 and len(strokes) < stroke_count:
            strokes.append(_random_line_or_arc(rng, traits, y_max))
    else:
        for _ in range(stroke_count):
            strokes.append(_random_line_or_arc(rng, traits, y_max))

    # diacritic_density: an extra floating dot or two, independent of
    # the main stroke count above.
    dot_chance = lerp(traits.diacritic_density, 0.0, 0.6)
    for _ in range(2):
        if rng.random() < dot_chance:
            p = _random_point(rng, y_max)
            strokes.append(Stroke(kind=StrokeKind.DOT, start=p, end=p))

    return Glyph(ipa=ipa, strokes=tuple(strokes))


def generate_script(
    rng: random.Random,
    inventory: PhonemeInventory,
    forced_script_traits: ScriptTraitsForce = ScriptTraitsForce(),
) -> InventedScript:
    """Every symbol in ``inventory``'s own consonants and vowels, each
    given one glyph, in that stable order -- drawing sequentially from
    one ``rng`` stream (the same convention every other per-symbol
    generation pass in this project already uses), so re-running with
    the same seed and the same inventory always reproduces the same
    script."""
    direction = roll_direction(rng)
    traits = roll_script_traits(rng, forced_script_traits)
    symbols = inventory.consonant_symbols() + inventory.vowel_symbols()
    glyphs = tuple(generate_glyph(rng, symbol, traits) for symbol in symbols)
    return InventedScript(direction=direction, traits=traits, glyphs=glyphs)


__all__ = [
    "should_generate_script",
    "roll_direction",
    "roll_script_traits",
    "generate_glyph",
    "generate_script",
]
