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

_GRID_SHAPE_WEIGHTS: tuple[tuple[tuple[int, int], float], ...] = (
    ((2, 2), 0.70),  # "square" -- the common case
    ((1, 2), 0.15),  # "tall"
    ((2, 1), 0.15),  # "wide"
)
"""(grid_max_x, grid_max_y) pairs, weighted -- a 2x2-cell grid (3x3 points) is the common case a
stocky, simple-alphabet letterform can be built from; the rarer tall/wide variants bias one axis down
to a single cell for scripts styled more vertical or horizontal. All three fit well inside `Point`'s
own `ge=0, le=3` bound -- smaller than the old fixed grid, not bigger, so that bound never needed to
change."""


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


def roll_grid_shape(rng: random.Random) -> tuple[int, int]:
    """One ``(grid_max_x, grid_max_y)`` pair -- see ``_GRID_SHAPE_WEIGHTS``."""
    shapes, weights = zip(*_GRID_SHAPE_WEIGHTS)
    return rng.choices(shapes, weights=weights, k=1)[0]


def roll_script_traits(rng: random.Random, force: ScriptTraitsForce = ScriptTraitsForce()) -> ScriptTraits:
    """Rolls all 16 dials, then applies any non-``None`` field of
    ``force`` on top (see ``ScriptTraitsForce``'s own docstring) --
    every ``rng`` draw still happens even for a forced dial, so adding or
    removing an override never shifts any other dial's own value."""
    fields = ScriptTraits.model_fields
    rolled = {name: round(rng.uniform(-1.0, 1.0), 2) for name in fields}
    overrides = {name: value for name, value in force.model_dump().items() if value is not None}
    return ScriptTraits(**{**rolled, **overrides})


def _random_point(rng: random.Random, grid_max_x: int, grid_max_y: int) -> Point:
    return Point(x=rng.randint(0, grid_max_x), y=rng.randint(0, grid_max_y))


def _random_line_or_arc(
    rng: random.Random, traits: ScriptTraits, grid_max_x: int, grid_max_y: int, chain_from: Point | None,
) -> Stroke:
    # angularity +1 -> never an arc; -1 -> always an arc.
    is_arc = rng.random() < lerp(-traits.angularity, 0.0, 1.0)
    # stroke_continuity +1 -> almost always continue from the last stroke's own end point (never
    # quite 100%, so even a near-fully-connected script still gets the rare multi-component letter);
    # -1 -> mostly lift and start fresh elsewhere (never quite 0%, so strokes can still coincidentally
    # chain). `chain_from` is `None` for a glyph's first stroke, which always starts fresh.
    if chain_from is not None and rng.random() < lerp(traits.stroke_continuity, 0.15, 0.95):
        start = chain_from
    else:
        start = _random_point(rng, grid_max_x, grid_max_y)
    end = _random_point(rng, grid_max_x, grid_max_y)
    tries = 0
    while end == start and tries < 5:  # a zero-length stroke draws nothing
        end = _random_point(rng, grid_max_x, grid_max_y)
        tries += 1
    if not is_arc:
        return Stroke(kind=StrokeKind.LINE, start=start, end=end)
    # Smoother (more negative angularity) -> a bigger bulge; sign is
    # independent of angularity, just which side the curve bends to.
    magnitude = lerp(-traits.angularity, 0.1, 0.6)
    bulge = magnitude if rng.random() < 0.5 else -magnitude
    return Stroke(kind=StrokeKind.ARC, start=start, end=end, bulge=round(bulge, 2))


def _mirror_point(p: Point, grid_max_x: int) -> Point:
    return Point(x=grid_max_x - p.x, y=p.y)


def _mirror_stroke(s: Stroke, grid_max_x: int) -> Stroke:
    return Stroke(
        kind=s.kind, start=_mirror_point(s.start, grid_max_x), end=_mirror_point(s.end, grid_max_x), bulge=-s.bulge,
    )


_CORNER_RETRY_LIMIT = 8


def _touches_enough_corners(strokes: list[Stroke], traits: ScriptTraits, grid_max_x: int, grid_max_y: int) -> bool:
    """A small, connected grid risks a glyph too sparse to read clearly (e.g. two strokes confined to
    one corner) -- require the chain to actually reach a minimum number of the grid's 4 extreme
    corners before accepting it (see ``_build_stroke_chain``'s own bounded retry)."""
    corners = {(0, 0), (0, grid_max_y), (grid_max_x, 0), (grid_max_x, grid_max_y)}
    touched = {(s.start.x, s.start.y) for s in strokes} | {(s.end.x, s.end.y) for s in strokes}
    required = 3 if traits.complexity > 0 else 2
    return len(touched & corners) >= required


def _build_stroke_chain(
    rng: random.Random, traits: ScriptTraits, stroke_count: int, grid_max_x: int, grid_max_y: int,
) -> list[Stroke]:
    """``stroke_count`` strokes, chained by default (``stroke_continuity``), mirrored across the
    vertical center if ``symmetry`` calls for it, retried (bounded) until enough of the grid's own
    corners are touched -- see ``_touches_enough_corners``. Regenerating the whole chain on a retry,
    not just the offending stroke, keeps the connected-chain invariant intact (a single patched-in
    stroke could silently break the "starts where the last one ended" property)."""
    strokes: list[Stroke] = []
    for attempt in range(_CORNER_RETRY_LIMIT):
        strokes = []
        chain_from: Point | None = None
        if traits.symmetry > 0.3:
            half = max(1, stroke_count // 2)
            for _ in range(half):
                s = _random_line_or_arc(rng, traits, grid_max_x, grid_max_y, chain_from)
                strokes.append(s)
                strokes.append(_mirror_stroke(s, grid_max_x))
                chain_from = s.end
            if stroke_count % 2 and len(strokes) < stroke_count:
                strokes.append(_random_line_or_arc(rng, traits, grid_max_x, grid_max_y, chain_from))
        else:
            for _ in range(stroke_count):
                s = _random_line_or_arc(rng, traits, grid_max_x, grid_max_y, chain_from)
                strokes.append(s)
                chain_from = s.end
        if _touches_enough_corners(strokes, traits, grid_max_x, grid_max_y) or attempt == _CORNER_RETRY_LIMIT - 1:
            break
    return strokes


def generate_glyph(rng: random.Random, ipa: str, traits: ScriptTraits, grid_max_x: int, grid_max_y: int) -> Glyph:
    """One phoneme's own glyph -- a chain of connected stroke primitives
    (``stroke_continuity``) placed on this script's own grid, styled by
    ``traits``. See this module's own docstring for which of
    ``ScriptTraits``' 16 dials this function itself consumes (stroke
    topology) versus ``script.font_builder`` (rendering);
    ``connectivity`` is consumed by ``generate_script`` instead (cross-
    glyph baseline joining, not a per-glyph topology concern)."""
    # height_variance: this one glyph, not the whole script, rolls
    # whether it's full-height or restricted to the lower rows (an
    # x-height-only look) -- the *rate* that happens at is what gives
    # the trait its visible effect across the whole glyph set. Guarded
    # on grid_max_y >= 2 -- on a "wide" grid (grid_max_y == 1) this
    # reduction would flatten the glyph onto a single row.
    y_max = grid_max_y
    if grid_max_y >= 2 and rng.random() < lerp(traits.height_variance, 0.0, 0.5):
        y_max = grid_max_y - 1

    stroke_count = round(lerp(traits.complexity, _MIN_STROKES, _MAX_STROKES))
    strokes = _build_stroke_chain(rng, traits, stroke_count, grid_max_x, y_max)

    # diacritic_density: an extra floating dot or two, independent of
    # the main stroke count above -- added after the corner-coverage
    # gate accepts the main chain, since a dot was never meant to count
    # toward "the letter is big enough to read."
    dot_chance = lerp(traits.diacritic_density, 0.0, 0.6)
    for _ in range(2):
        if rng.random() < dot_chance:
            p = _random_point(rng, grid_max_x, y_max)
            strokes.append(Stroke(kind=StrokeKind.DOT, start=p, end=p))

    return Glyph(ipa=ipa, strokes=tuple(strokes))


def _apply_connectivity(glyph: Glyph, traits: ScriptTraits, direction: WritingDirection, grid_max_x: int) -> Glyph:
    """``connectivity``'s own cheap approximation of cross-letter joining: pin the glyph's overall
    first and last *non-dot* stroke to two fixed baseline anchor points, so adjacent glyphs' own
    shapes visually touch/align at the baseline when typeset in sequence -- "letters always begin and
    end in the same spot," per the user's own framing, not real OpenType contextual substitution (see
    ``docs/DEFERRED.md``'s "True cursive joining" item for what that would still need). Horizontal
    directions only (``LTR``/``RTL``) -- vertical joining for top-to-bottom scripts is a real
    follow-up, not attempted here. A no-op below ``connectivity``'s own 0.3 threshold, or for a glyph
    with no non-dot strokes at all (shouldn't happen -- ``generate_glyph`` always builds at least
    ``_MIN_STROKES`` -- but never crash a rare empty case either way)."""
    if traits.connectivity <= 0.3 or direction not in (WritingDirection.LTR, WritingDirection.RTL):
        return glyph
    non_dot_indices = [i for i, s in enumerate(glyph.strokes) if s.kind is not StrokeKind.DOT]
    if not non_dot_indices:
        return glyph
    entry, exit_ = (Point(x=0, y=0), Point(x=grid_max_x, y=0))
    if direction is WritingDirection.RTL:
        entry, exit_ = exit_, entry
    strokes = list(glyph.strokes)
    first_i, last_i = non_dot_indices[0], non_dot_indices[-1]
    strokes[first_i] = strokes[first_i].model_copy(update={"start": entry})
    strokes[last_i] = strokes[last_i].model_copy(update={"end": exit_})
    return glyph.model_copy(update={"strokes": tuple(strokes)})


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
    grid_max_x, grid_max_y = roll_grid_shape(rng)
    traits = roll_script_traits(rng, forced_script_traits)
    symbols = inventory.consonant_symbols() + inventory.vowel_symbols()
    glyphs = tuple(
        _apply_connectivity(generate_glyph(rng, symbol, traits, grid_max_x, grid_max_y), traits, direction, grid_max_x)
        for symbol in symbols
    )
    return InventedScript(
        direction=direction, traits=traits, grid_max_x=grid_max_x, grid_max_y=grid_max_y, glyphs=glyphs,
    )


__all__ = [
    "should_generate_script",
    "roll_direction",
    "roll_grid_shape",
    "roll_script_traits",
    "generate_glyph",
    "generate_script",
]
