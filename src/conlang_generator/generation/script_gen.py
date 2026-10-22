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
sequential stream position.** ``direction``/the grid shape/the 13 style
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
    SCRIPT_TRAIT_RANGE,
    Glyph,
    InventedScript,
    Point,
    ScriptTraits,
    ScriptTraitsForce,
    Stroke,
    StrokeKind,
    WritingDirection,
    lerp,
    lerp01,
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
    """Rolls all 13 dials, each within its own ``SCRIPT_TRAIT_RANGE`` (bipolar ``-1..1`` or unipolar
    ``0..1``), then applies any non-``None`` field of ``force`` on top (see ``ScriptTraitsForce``'s own
    docstring) -- every ``rng`` draw still happens even for a forced dial, so adding or removing an
    override never shifts any other dial's own value."""
    fields = ScriptTraits.model_fields
    rolled = {name: round(rng.uniform(*SCRIPT_TRAIT_RANGE[name]), 2) for name in fields}
    overrides = {name: value for name, value in force.model_dump().items() if value is not None}
    return ScriptTraits(**{**rolled, **overrides})


def _random_point(rng: random.Random, grid_max_x: int, grid_max_y: int) -> Point:
    return Point(x=rng.randint(0, grid_max_x), y=rng.randint(0, grid_max_y))


def _valid_line_partners(
    start: Point, grid_max_x: int, grid_max_y: int, exclude_direction: tuple[int, int] | None = None,
) -> list[Point]:
    """Every other grid point reachable from ``start`` by a cell-boundary or diagonal line --
    horizontal (``dy == 0``), vertical (``dx == 0``), or 45 degrees (``abs(dx) == abs(dy)``). Phase 1
    only ever draws a stroke along one of these three directions, not an arbitrary point-to-point
    slash -- real alphabets construct letters from a small set of simple, reused shapes, not
    disconnected noise.

    ``exclude_direction``, when given, drops any candidate whose own direction from ``start`` is
    *parallel* to it (same line, either continuing straight through or doubling back over it -- a
    zero cross product) -- direct user feedback: a chained stroke retracing part of the one that fed
    it "doesn't add anything... sometimes makes two letters look exactly the same." Returning to an
    *already-visited point* is not excluded here (that's how a triangle/circle closes) -- only a new
    segment running along the same line as the incoming one. Always falls back to the unfiltered list
    if filtering would leave nothing (a real possibility on the smallest 1x2/2x1 grids) -- never
    returns empty on any grid shape this module ever rolls (every grid has at least 2 points on some
    axis, so ``start`` always has at least one same-row or same-column partner before filtering)."""
    partners = []
    for x in range(grid_max_x + 1):
        for y in range(grid_max_y + 1):
            if x == start.x and y == start.y:
                continue
            dx, dy = x - start.x, y - start.y
            if dx == 0 or dy == 0 or abs(dx) == abs(dy):
                partners.append(Point(x=x, y=y))
    if exclude_direction is None:
        return partners
    edx, edy = exclude_direction
    filtered = [p for p in partners if (p.x - start.x) * edy - (p.y - start.y) * edx != 0]
    return filtered or partners


def _decide_stroke(
    seed_key: str,
    index: int,
    chain_from: Point | None,
    chain_direction: tuple[int, int] | None,
    traits: ScriptTraits,
    grid_max_x: int,
    grid_max_y: int,
    occupied: set[tuple[int, int]],
    is_diacritic: bool = False,
) -> Stroke:
    """One stroke slot's own decision, addressably seeded by ``f"{seed_key}:{index}"`` -- a pure
    function of the glyph's identity, this slot's index, and the current trait values, never of
    sequential stream position (see this module's own docstring for why that matters).

    First, ``dot_prevalence``: this slot may become a bare dot instead of a line, placed at a grid
    point not already used as any stroke's own start/end so far in this glyph (falls back to drawing
    a normal line instead if no such point remains, rather than erroring). ``is_diacritic`` raises the
    ceiling of this roll (still the same ``dot_prevalence`` scaling, just a higher one -- direct user
    request: "dots should also have a higher chance to be generated in diacritics, but still scale with
    dot prevalence"). A dot never advances ``chain_from`` -- the caller's own chain simply continues
    from wherever it last was, "picking up where left off" across a dot slot.

    Otherwise, a line: ``stroke_continuity`` decides whether it starts from ``chain_from`` (the
    previous line stroke's own end) or a fresh point, and ``end`` is always one of ``start``'s own
    valid cell-boundary/diagonal partners (``_valid_line_partners``) -- excluding ``chain_direction``
    itself when actually chaining, so this stroke never just retraces the one that fed it."""
    rng = random.Random(f"{seed_key}:{index}")
    dot_ceiling = 0.55 if is_diacritic else 0.33
    if rng.random() < lerp(traits.dot_prevalence, 0.0, dot_ceiling):
        free_points = [
            Point(x=x, y=y)
            for x in range(grid_max_x + 1)
            for y in range(grid_max_y + 1)
            if (x, y) not in occupied
        ]
        if free_points:
            return Stroke(kind=StrokeKind.DOT, start=rng.choice(free_points), end=rng.choice(free_points))
    is_chained = chain_from is not None and rng.random() < lerp(traits.stroke_continuity, 0.15, 0.95)
    start = chain_from if is_chained else _random_point(rng, grid_max_x, grid_max_y)
    exclude = chain_direction if is_chained else None
    end = rng.choice(_valid_line_partners(start, grid_max_x, grid_max_y, exclude))
    return Stroke(kind=StrokeKind.LINE, start=start, end=end)


def _touches_enough_corners(strokes: list[Stroke], traits: ScriptTraits, grid_max_x: int, grid_max_y: int) -> bool:
    """A small, connected grid risks a glyph too sparse to read clearly (e.g. two strokes confined to
    one corner) -- require the chain to actually reach a minimum number of the grid's 4 extreme
    corners before accepting it (see ``_build_stroke_chain``'s own bounded retry)."""
    corners = {(0, 0), (0, grid_max_y), (grid_max_x, 0), (grid_max_x, grid_max_y)}
    touched = {(s.start.x, s.start.y) for s in strokes} | {(s.end.x, s.end.y) for s in strokes}
    required = 3 if traits.complexity > 0 else 2
    return len(touched & corners) >= required


def _build_one_attempt(
    seed_key: str, traits: ScriptTraits, stroke_count: int, grid_max_x: int, grid_max_y: int,
    is_diacritic: bool = False,
) -> list[Stroke]:
    strokes: list[Stroke] = []
    occupied: set[tuple[int, int]] = set()
    chain_from: Point | None = None
    chain_direction: tuple[int, int] | None = None

    for i in range(stroke_count):
        s = _decide_stroke(
            seed_key, i, chain_from, chain_direction, traits, grid_max_x, grid_max_y, occupied, is_diacritic,
        )
        strokes.append(s)
        occupied.add((s.start.x, s.start.y))
        occupied.add((s.end.x, s.end.y))
        if s.kind is not StrokeKind.DOT:
            chain_from = s.end
            chain_direction = (s.end.x - s.start.x, s.end.y - s.start.y)
    return strokes


def _build_stroke_chain(
    seed_key: str, traits: ScriptTraits, stroke_count: int, grid_max_x: int, grid_max_y: int,
    is_diacritic: bool = False,
) -> list[Stroke]:
    """``stroke_count`` strokes, each addressably seeded (``_decide_stroke``), chained by default
    (``stroke_continuity``) and never retracing the stroke that fed it (see ``_valid_line_partners``'s
    own ``exclude_direction``), retried (bounded, each attempt its own addressable sub-key so a retry
    still produces a fresh draw) until enough of the grid's own corners are touched -- see
    ``_touches_enough_corners``. Regenerating the whole attempt on a retry, not patching just the
    offending stroke, keeps the connected-chain invariant intact (a single patched-in stroke could
    silently break the "starts where the last one ended" property). ``is_diacritic`` just threads
    through to every ``_decide_stroke`` call -- see that function's own docstring."""
    strokes: list[Stroke] = []
    for attempt in range(_CORNER_RETRY_LIMIT):
        strokes = _build_one_attempt(
            f"{seed_key}:attempt{attempt}", traits, stroke_count, grid_max_x, grid_max_y, is_diacritic,
        )
        if _touches_enough_corners(strokes, traits, grid_max_x, grid_max_y) or attempt == _CORNER_RETRY_LIMIT - 1:
            break
    return strokes


_DIACRITIC_MIN_STROKES = 1
_DIACRITIC_MAX_STROKES = 3
""""Generally less strokes" than a main letter's own ``_MIN_STROKES.._MAX_STROKES`` range -- the lower
bound of ``ornateness``'s own widened ceiling, see ``_generate_diacritics``."""

_MAX_DUPLICATE_RETRIES = 5
"""Shared bound for every addressable-retry-on-collision loop in this module (a duplicate whole-glyph
signature in ``generate_script``, a duplicate diacritic slot in ``_generate_diacritics``) -- past this
many attempts, accept the last result unconditionally rather than looping forever on a tiny grid with
genuinely few distinct possible shapes/slots."""


def _script_wide_seed(traits: ScriptTraits, direction: WritingDirection) -> str:
    """A fingerprint of script-wide (not per-glyph) data -- traits plus direction -- for a decision
    that must come out identical for every glyph in the same script (today: the single fixed cross-axis
    sign a low-``ornateness`` script reuses for every diacritic, "always in the same location," direct
    user phrasing). Mirrors ``script.font_builder``'s own ``_script_fingerprint`` -- built from data
    already available at every call site here, rather than threading the original generation seed down
    an extra parameter just for this."""
    return f"{traits.model_dump()}:{direction}"


def _roll_diacritic_slot(seed_key: str, traits: ScriptTraits, direction: WritingDirection) -> str:
    """One diacritic instance's own placement slot -- see ``core.script.Glyph.diacritics``'s own
    docstring for the full vocabulary. Three independent, ``ornateness``-driven rolls: which broad
    category (external cross-axis -- no adjacent neighbor in this ``direction``, the frequent default;
    external along-axis -- where a neighboring glyph sits, "only sometimes... if there is no
    connectedness between letters"; or internal, one of 9 fractional positions nested inside the main
    glyph's own grid, "appearing... inside one of the 9 grid points"); which sign on the cross axis (a
    *script-wide* fixed one -- ``_script_wide_seed`` -- reused at low ``ornateness``, "always in the
    same location," with a rising per-instance chance of flipping to the other one, "start appearing
    both high and low," as it increases); and (for ``internal``) which of the 9 positions."""
    category_roll = random.Random(f"{seed_key}:diacritic-category").random()
    p_internal = lerp01(traits.ornateness, 0.0, 0.3)
    p_along = lerp01(traits.ornateness, 0.0, 0.25)
    if category_roll < p_internal:
        rng = random.Random(f"{seed_key}:diacritic-internal")
        return f"internal:{rng.randint(0, 2)},{rng.randint(0, 2)}"
    if category_roll < p_internal + p_along:
        sign = "pos" if random.Random(f"{seed_key}:diacritic-along-sign").random() < 0.5 else "neg"
        return f"along_{sign}"
    fixed_sign = "pos" if random.Random(f"{_script_wide_seed(traits, direction)}:diacritic-fixed-side").random() < 0.5 else "neg"
    flip_roll = random.Random(f"{seed_key}:diacritic-cross-flip").random()
    if flip_roll < lerp01(traits.ornateness, 0.0, 0.5):
        fixed_sign = "neg" if fixed_sign == "pos" else "pos"
    return f"cross_{fixed_sign}"


def _generate_diacritics(
    seed_key: str, traits: ScriptTraits, grid_max_x: int, grid_max_y: int, direction: WritingDirection,
) -> dict[str, Glyph]:
    """How many diacritic instances attach is ``diacritic_density``'s own roll (0..4, unchanged
    mechanism); *where* each one sits is ``ornateness``-driven and direction-aware (see
    ``_roll_diacritic_slot``). Each instance is independently rolled (seeded ``f"{seed_key}:
    diacritic-slot:{i}"``); a collision falls back to cycling deterministically through the 9 internal
    grid positions by instance index -- not a bumped-sub-key retry (``generate_script``'s own
    duplicate-glyph pattern): near ``ornateness == 0`` every instance's own roll collapses onto the
    same single script-wide slot *by design*, so a retry would just recompute the identical answer
    rather than actually resolving the collision. Each filled slot's own diacritic is built by
    ``generate_glyph``
    itself -- the exact same stroke-generation process as any letter -- with fewer strokes
    (``_DIACRITIC_MIN_STROKES``, and an ``ornateness``-widened ceiling, "on average have more strokes,"
    direct user request), ``is_diacritic=True`` (a higher dot-prevalence ceiling, see
    ``_decide_stroke``), and ``with_diacritics=False`` (a diacritic never gets its own diacritics).
    Reuses the *main* glyph's own ``grid_max_x``/``grid_max_y`` rather than rolling an independent grid
    shape per diacritic -- `script.font_builder` renders it at a fraction of that size regardless, so
    the same grid shape at a smaller scale already gives the "small, confined" look without a second
    grid-shape data field to carry around."""
    count = round(lerp(traits.diacritic_density, 0.0, 4))
    if count <= 0:
        return {}
    effective_max_strokes = round(lerp01(traits.ornateness, _DIACRITIC_MAX_STROKES, _DIACRITIC_MAX_STROKES + 2))
    diacritics: dict[str, Glyph] = {}
    for i in range(count):
        slot = _roll_diacritic_slot(f"{seed_key}:diacritic-slot:{i}", traits, direction)
        if slot in diacritics:
            # At (or near) ornateness == 0 every instance's own "natural" roll collapses onto the
            # same single script-wide slot by design -- a bumped sub-key can't help there, since
            # _roll_diacritic_slot's own category/flip thresholds are also 0 at that same ornateness,
            # so a retry just recomputes the identical answer. Fall back to cycling deterministically
            # through the 9 internal grid positions by instance index instead -- guaranteed distinct
            # for any count up to 4 (this field's own max), never silently dropping an instance.
            for attempt in range(9):
                xi, yi = (i + attempt) % 3, ((i + attempt) // 3) % 3
                slot = f"internal:{xi},{yi}"
                if slot not in diacritics:
                    break
        diacritics[slot] = generate_glyph(
            f"{seed_key}:diacritic:{slot}", "", traits, grid_max_x, grid_max_y, direction,
            min_strokes=_DIACRITIC_MIN_STROKES, max_strokes=effective_max_strokes,
            with_diacritics=False, is_diacritic=True,
        )
    return diacritics


def generate_glyph(
    seed_key: str, ipa: str, traits: ScriptTraits, grid_max_x: int, grid_max_y: int,
    direction: WritingDirection = WritingDirection.LTR,
    min_strokes: int = _MIN_STROKES, max_strokes: int = _MAX_STROKES, with_diacritics: bool = True,
    is_diacritic: bool = False,
) -> Glyph:
    """One phoneme's own glyph -- a chain of connected, boundary/diagonal-only line (and occasional
    dot) strokes placed on this script's own grid, addressably seeded from ``seed_key`` (see this
    module's own docstring). ``seed_key`` is the glyph's own full identity (script seed + phoneme
    symbol) -- every stroke slot's own key is derived from it, never from a shared stream position.
    ``direction`` only matters to ``_generate_diacritics`` (a main letter's own strokes don't care about
    writing direction) -- defaults to ``LTR`` so a caller that never touches diacritic placement (most
    of this module's own tests) doesn't need to pass it. ``min_strokes``/``max_strokes``/
    ``with_diacritics``/``is_diacritic`` exist so ``_generate_diacritics`` can call this same function
    for a diacritic's own small glyph (fewer strokes, a higher dot-prevalence ceiling, never itself
    diacritic-bearing) rather than duplicating the stroke-generation logic above."""
    stroke_count = round(lerp(traits.complexity, min_strokes, max_strokes))
    strokes = _build_stroke_chain(seed_key, traits, stroke_count, grid_max_x, grid_max_y, is_diacritic)
    diacritics = _generate_diacritics(seed_key, traits, grid_max_x, grid_max_y, direction) if with_diacritics else {}
    return Glyph(ipa=ipa, strokes=tuple(strokes), diacritics=diacritics)


def _glyph_signature(glyph: Glyph) -> tuple:
    """A hashable stand-in for "this glyph looks exactly like that one" -- its own strokes plus every
    diacritic's own strokes, keyed by slot. ``Glyph.diacritics`` is a ``dict`` (unhashable), so it's
    flattened to a sorted tuple of ``(slot, strokes)`` pairs first."""
    return (glyph.strokes, tuple(sorted((slot, d.strokes) for slot, d in glyph.diacritics.items())))


def generate_script(
    seed: str,
    inventory: PhonemeInventory,
    forced_script_traits: ScriptTraitsForce = ScriptTraitsForce(),
) -> InventedScript:
    """Every symbol in ``inventory``'s own consonants and vowels, each given one glyph, in that stable
    order. ``direction``/the grid shape/the 12 style dials are rolled once, in order, from one shared
    sequential ``random.Random(seed)`` stream (the same convention every other per-symbol generation
    pass in this project already uses); each glyph's own stroke *content* is addressably keyed from
    ``seed`` directly instead (see this module's own docstring for why) -- so re-running with the same
    seed and the same inventory always reproduces the same script, exactly as before, just via two
    different mechanisms for two different kinds of decision.

    Each glyph is also checked against every earlier glyph in the same script (``_glyph_signature``,
    comparing strokes plus diacritics) -- direct user feedback that two letters could otherwise end up
    looking identical. On a collision, that one glyph is rebuilt with a bumped sub-key
    (``f"{seed}:{symbol}:dup{attempt}"``), the same addressable-retry pattern ``_build_stroke_chain``'s
    own corner-coverage retry already uses, bounded at ``_MAX_DUPLICATE_RETRIES`` attempts -- a tiny
    grid genuinely has few distinct possible shapes, so past the cap the last attempt is accepted
    unconditionally rather than looping forever."""
    rng = random.Random(seed)
    direction = roll_direction(rng)
    grid_max_x, grid_max_y = roll_grid_shape(rng)
    traits = roll_script_traits(rng, forced_script_traits)
    symbols = inventory.consonant_symbols() + inventory.vowel_symbols()
    glyphs: list[Glyph] = []
    seen_signatures: set[tuple] = set()
    for symbol in symbols:
        seed_key = f"{seed}:{symbol}"
        glyph = generate_glyph(seed_key, symbol, traits, grid_max_x, grid_max_y, direction)
        signature = _glyph_signature(glyph)
        attempt = 0
        while signature in seen_signatures and attempt < _MAX_DUPLICATE_RETRIES:
            attempt += 1
            glyph = generate_glyph(f"{seed_key}:dup{attempt}", symbol, traits, grid_max_x, grid_max_y, direction)
            signature = _glyph_signature(glyph)
        seen_signatures.add(signature)
        glyphs.append(glyph)
    return InventedScript(
        direction=direction, traits=traits, grid_max_x=grid_max_x, grid_max_y=grid_max_y, glyphs=tuple(glyphs),
    )


__all__ = [
    "should_generate_script",
    "roll_direction",
    "roll_grid_shape",
    "roll_script_traits",
    "generate_glyph",
    "generate_script",
]
