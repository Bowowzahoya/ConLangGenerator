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

**Every glyph's own stroke content is addressably seeded, not drawn from
sequential stream position.** ``direction``/the grid shape/the 16 style
dials are rolled once, in order, from one shared sequential ``random.
Random`` stream (same convention every other per-symbol generation pass
in this project already uses -- reproducible by seed, nothing new here).
But each glyph's own strokes are each keyed by ``random.Random(f"{seed}:
{symbol}:...:{index}")`` -- the same string-keyed-determinism technique
``script.font_builder._stable_unit`` already uses for jitter, just
applied one level up. This is deliberate, not an incidental style
choice: it is the one property a script *tweak* (``generation.generator.
regenerate_script``) needs to "redraw stroke i only if stroke i's own
inputs actually changed" -- a stroke-count increase appends past the old
end, a decrease truncates, and a shifted pen-lift point only changes the
specific indices whose own roll crosses a different threshold, with no
diff/splice logic needed anywhere. Sequential stream consumption (this
module's own shape before this) cannot offer that: any upstream change
shifts every later draw's position in the stream, and therefore its
value, even when nothing about that specific stroke's own inputs
changed.
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
_CORNER_RETRY_LIMIT = 8

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
    """Rolls all 17 dials, then applies any non-``None`` field of
    ``force`` on top (see ``ScriptTraitsForce``'s own docstring) --
    every ``rng`` draw still happens even for a forced dial, so adding or
    removing an override never shifts any other dial's own value."""
    fields = ScriptTraits.model_fields
    rolled = {name: round(rng.uniform(-1.0, 1.0), 2) for name in fields}
    overrides = {name: value for name, value in force.model_dump().items() if value is not None}
    return ScriptTraits(**{**rolled, **overrides})


def _random_point(rng: random.Random, grid_max_x: int, grid_max_y: int) -> Point:
    return Point(x=rng.randint(0, grid_max_x), y=rng.randint(0, grid_max_y))


def _valid_line_partners(start: Point, grid_max_x: int, grid_max_y: int) -> list[Point]:
    """Every other grid point reachable from ``start`` by a cell-boundary or diagonal line --
    horizontal (``dy == 0``), vertical (``dx == 0``), or 45 degrees (``abs(dx) == abs(dy)``). Phase 1
    only ever draws a stroke along one of these three directions, not an arbitrary point-to-point
    slash -- real alphabets construct letters from a small set of simple, reused shapes, not
    disconnected noise. Always non-empty on any grid shape this module ever rolls (every grid has at
    least 2 points on some axis, so ``start`` always has at least one same-row or same-column
    partner)."""
    partners = []
    for x in range(grid_max_x + 1):
        for y in range(grid_max_y + 1):
            if x == start.x and y == start.y:
                continue
            dx, dy = x - start.x, y - start.y
            if dx == 0 or dy == 0 or abs(dx) == abs(dy):
                partners.append(Point(x=x, y=y))
    return partners


def _decide_stroke(
    seed_key: str,
    index: int,
    chain_from: Point | None,
    traits: ScriptTraits,
    grid_max_x: int,
    grid_max_y: int,
    occupied: set[tuple[int, int]],
) -> Stroke:
    """One stroke slot's own decision, addressably seeded by ``f"{seed_key}:{index}"`` -- a pure
    function of the glyph's identity, this slot's index, and the current trait values, never of
    sequential stream position (see this module's own docstring for why that matters).

    First, ``dot_prevalence``: this slot may become a bare dot instead of a line, placed at a grid
    point not already used as any stroke's own start/end so far in this glyph (falls back to drawing
    a normal line instead if no such point remains, rather than erroring). A dot never advances
    ``chain_from`` -- the caller's own chain simply continues from wherever it last was, "picking up
    where left off" across a dot slot.

    Otherwise, a line: ``stroke_continuity`` decides whether it starts from ``chain_from`` (the
    previous line stroke's own end) or a fresh point, and ``end`` is always one of ``start``'s own
    valid cell-boundary/diagonal partners (``_valid_line_partners``)."""
    rng = random.Random(f"{seed_key}:{index}")
    if rng.random() < lerp(traits.dot_prevalence, 0.0, 0.33):
        free_points = [
            Point(x=x, y=y)
            for x in range(grid_max_x + 1)
            for y in range(grid_max_y + 1)
            if (x, y) not in occupied
        ]
        if free_points:
            return Stroke(kind=StrokeKind.DOT, start=rng.choice(free_points), end=rng.choice(free_points))
    if chain_from is not None and rng.random() < lerp(traits.stroke_continuity, 0.15, 0.95):
        start = chain_from
    else:
        start = _random_point(rng, grid_max_x, grid_max_y)
    end = rng.choice(_valid_line_partners(start, grid_max_x, grid_max_y))
    return Stroke(kind=StrokeKind.LINE, start=start, end=end)


def _mirror_point(p: Point, grid_max_x: int) -> Point:
    return Point(x=grid_max_x - p.x, y=p.y)


def _mirror_stroke(s: Stroke, grid_max_x: int) -> Stroke:
    return Stroke(
        kind=s.kind, start=_mirror_point(s.start, grid_max_x), end=_mirror_point(s.end, grid_max_x), bulge=-s.bulge,
    )


def _touches_enough_corners(strokes: list[Stroke], traits: ScriptTraits, grid_max_x: int, grid_max_y: int) -> bool:
    """A small, connected grid risks a glyph too sparse to read clearly (e.g. two strokes confined to
    one corner) -- require the chain to actually reach a minimum number of the grid's 4 extreme
    corners before accepting it (see ``_build_stroke_chain``'s own bounded retry)."""
    corners = {(0, 0), (0, grid_max_y), (grid_max_x, 0), (grid_max_x, grid_max_y)}
    touched = {(s.start.x, s.start.y) for s in strokes} | {(s.end.x, s.end.y) for s in strokes}
    required = 3 if traits.complexity > 0 else 2
    return len(touched & corners) >= required


def _build_one_attempt(seed_key: str, traits: ScriptTraits, stroke_count: int, grid_max_x: int, grid_max_y: int) -> list[Stroke]:
    strokes: list[Stroke] = []
    occupied: set[tuple[int, int]] = set()
    chain_from: Point | None = None

    def place(index: int) -> Stroke:
        nonlocal chain_from
        s = _decide_stroke(seed_key, index, chain_from, traits, grid_max_x, grid_max_y, occupied)
        occupied.add((s.start.x, s.start.y))
        occupied.add((s.end.x, s.end.y))
        if s.kind is not StrokeKind.DOT:
            chain_from = s.end
        return s

    if traits.symmetry > 0.3:
        half = max(1, stroke_count // 2)
        for i in range(half):
            s = place(i)
            strokes.append(s)
            mirrored = _mirror_stroke(s, grid_max_x)
            strokes.append(mirrored)
            occupied.add((mirrored.start.x, mirrored.start.y))
            occupied.add((mirrored.end.x, mirrored.end.y))
        if stroke_count % 2 and len(strokes) < stroke_count:
            strokes.append(place(half))
    else:
        for i in range(stroke_count):
            strokes.append(place(i))
    return strokes


def _build_stroke_chain(seed_key: str, traits: ScriptTraits, stroke_count: int, grid_max_x: int, grid_max_y: int) -> list[Stroke]:
    """``stroke_count`` strokes, each addressably seeded (``_decide_stroke``), chained by default
    (``stroke_continuity``), mirrored across the vertical center if ``symmetry`` calls for it, retried
    (bounded, each attempt its own addressable sub-key so a retry still produces a fresh draw) until
    enough of the grid's own corners are touched -- see ``_touches_enough_corners``. Regenerating the
    whole attempt on a retry, not patching just the offending stroke, keeps the connected-chain
    invariant intact (a single patched-in stroke could silently break the "starts where the last one
    ended" property)."""
    strokes: list[Stroke] = []
    for attempt in range(_CORNER_RETRY_LIMIT):
        strokes = _build_one_attempt(f"{seed_key}:attempt{attempt}", traits, stroke_count, grid_max_x, grid_max_y)
        if _touches_enough_corners(strokes, traits, grid_max_x, grid_max_y) or attempt == _CORNER_RETRY_LIMIT - 1:
            break
    return strokes


_DIACRITIC_SLOTS = ("top", "bottom", "left", "right")
"""The same 4 names ``core.script.Glyph.anchors`` already uses as its own worked examples -- a small,
fixed set, per direct user request, not a freer offset."""
_DIACRITIC_MIN_STROKES = 1
_DIACRITIC_MAX_STROKES = 3
""""Generally less strokes" than a main letter's own ``_MIN_STROKES.._MAX_STROKES`` range."""


def _generate_diacritics(seed_key: str, traits: ScriptTraits, grid_max_x: int, grid_max_y: int) -> dict[str, Glyph]:
    """How many of ``_DIACRITIC_SLOTS`` get filled is ``diacritic_density``'s own roll (0..4); which
    ones, a seeded sample. Each filled slot's own diacritic is built by ``generate_glyph`` itself --
    the exact same stroke-generation process as any letter, just with fewer strokes
    (``_DIACRITIC_MIN_STROKES``/``_DIACRITIC_MAX_STROKES``) and ``with_diacritics=False`` (a diacritic
    never gets its own diacritics). Reuses the *main* glyph's own ``grid_max_x``/``grid_max_y`` rather
    than rolling an independent grid shape per diacritic -- `script.font_builder` renders it at
    `_DIACRITIC_SCALE` regardless, so the same grid shape at half size already gives the "small,
    confined" look without a second grid-shape data field to carry around."""
    count = round(lerp(traits.diacritic_density, 0.0, len(_DIACRITIC_SLOTS)))
    if count <= 0:
        return {}
    slots = random.Random(f"{seed_key}:diacritic-slots").sample(_DIACRITIC_SLOTS, count)
    return {
        slot: generate_glyph(
            f"{seed_key}:diacritic:{slot}", "", traits, grid_max_x, grid_max_y,
            min_strokes=_DIACRITIC_MIN_STROKES, max_strokes=_DIACRITIC_MAX_STROKES, with_diacritics=False,
        )
        for slot in slots
    }


def generate_glyph(
    seed_key: str, ipa: str, traits: ScriptTraits, grid_max_x: int, grid_max_y: int,
    min_strokes: int = _MIN_STROKES, max_strokes: int = _MAX_STROKES, with_diacritics: bool = True,
) -> Glyph:
    """One phoneme's own glyph -- a chain of connected, boundary/diagonal-only line (and occasional
    dot) strokes placed on this script's own grid, addressably seeded from ``seed_key`` (see this
    module's own docstring). ``seed_key`` is the glyph's own full identity (script seed + phoneme
    symbol) -- every stroke slot's own key is derived from it, never from a shared stream position.
    ``min_strokes``/``max_strokes``/``with_diacritics`` exist so ``_generate_diacritics`` can call this
    same function for a diacritic's own small glyph (fewer strokes, never itself diacritic-bearing)
    rather than duplicating the stroke-generation logic above."""
    # height_variance: this one glyph, not the whole script, rolls whether it's full-height or
    # restricted to the lower rows (an x-height-only look) -- the *rate* that happens at is what gives
    # the trait its visible effect across the whole glyph set. Guarded on grid_max_y >= 2 -- on a
    # "wide" grid (grid_max_y == 1) this reduction would flatten the glyph onto a single row. Its own
    # addressable key (not stroke-indexed) so regenerating with a different stroke count never shifts
    # this decision.
    y_max = grid_max_y
    if grid_max_y >= 2 and random.Random(f"{seed_key}:height_variance").random() < lerp(traits.height_variance, 0.0, 0.5):
        y_max = grid_max_y - 1

    stroke_count = round(lerp(traits.complexity, min_strokes, max_strokes))
    strokes = _build_stroke_chain(seed_key, traits, stroke_count, grid_max_x, y_max)
    diacritics = _generate_diacritics(seed_key, traits, grid_max_x, grid_max_y) if with_diacritics else {}
    return Glyph(ipa=ipa, strokes=tuple(strokes), diacritics=diacritics)


def _apply_connectivity(
    glyph: Glyph, traits: ScriptTraits, direction: WritingDirection, grid_max_x: int, grid_max_y: int,
) -> Glyph:
    """``connectivity``'s own cheap approximation of cross-letter joining: pin the glyph's overall
    first and last *non-dot* stroke to two fixed baseline anchor points, so adjacent glyphs' own
    shapes visually touch/align at the baseline when typeset in sequence -- "letters always begin and
    end in the same spot," per the user's own framing, not real OpenType contextual substitution (see
    ``docs/DEFERRED.md``'s "True cursive joining" item for what that would still need). Horizontal
    directions only (``LTR``/``RTL``) -- vertical joining for top-to-bottom scripts is a real
    follow-up, not attempted here. A no-op below ``connectivity``'s own 0.3 threshold, or for a glyph
    with no non-dot strokes at all (shouldn't happen -- ``generate_glyph`` always builds at least
    ``_MIN_STROKES`` -- but never crash a rare empty case either way).

    Forcing just one endpoint of a stroke could leave its *other* endpoint no longer a valid cell-
    boundary/diagonal partner of the new one (``_valid_line_partners``) -- checked and repaired here:
    if the existing other endpoint is no longer valid, it's replaced with that endpoint's own first
    valid partner (a stable, deterministic pick, not a fresh random draw -- this is a repair, not a
    new creative decision)."""
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

    def _valid(a: Point, b: Point) -> bool:
        dx, dy = b.x - a.x, b.y - a.y
        return (dx == 0 or dy == 0 or abs(dx) == abs(dy)) and (dx != 0 or dy != 0)

    first = strokes[first_i]
    new_end = first.end if _valid(entry, first.end) else _valid_line_partners(entry, grid_max_x, grid_max_y)[0]
    strokes[first_i] = first.model_copy(update={"start": entry, "end": new_end})

    last = strokes[last_i]
    new_start = last.start if _valid(last.start, exit_) else _valid_line_partners(exit_, grid_max_x, grid_max_y)[0]
    strokes[last_i] = last.model_copy(update={"start": new_start, "end": exit_})

    return glyph.model_copy(update={"strokes": tuple(strokes)})


def generate_script(
    seed: str,
    inventory: PhonemeInventory,
    forced_script_traits: ScriptTraitsForce = ScriptTraitsForce(),
) -> InventedScript:
    """Every symbol in ``inventory``'s own consonants and vowels, each given one glyph, in that stable
    order. ``direction``/the grid shape/the 17 style dials are rolled once, in order, from one shared
    sequential ``random.Random(seed)`` stream (the same convention every other per-symbol generation
    pass in this project already uses); each glyph's own stroke *content* is addressably keyed from
    ``seed`` directly instead (see this module's own docstring for why) -- so re-running with the same
    seed and the same inventory always reproduces the same script, exactly as before, just via two
    different mechanisms for two different kinds of decision."""
    rng = random.Random(seed)
    direction = roll_direction(rng)
    grid_max_x, grid_max_y = roll_grid_shape(rng)
    traits = roll_script_traits(rng, forced_script_traits)
    symbols = inventory.consonant_symbols() + inventory.vowel_symbols()
    glyphs = tuple(
        _apply_connectivity(
            generate_glyph(f"{seed}:{symbol}", symbol, traits, grid_max_x, grid_max_y),
            traits, direction, grid_max_x, grid_max_y,
        )
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
