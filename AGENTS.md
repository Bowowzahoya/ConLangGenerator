# ConLangGenerator

## Purpose and development style

ConLangGenerator is primarily a project for exploration and fun.

I want to get interesting simulations running early, inspect what they do, intervene in them myself, and let implementation experience shape later architecture.

Prefer:

- real early examples over waiting for completeness;
- however, classes and architecture should be set up for scalability to other envisioned functionalities
- inspectability;
- simple replaceable implementations;
- explicit limitations rather than pretend completeness.

Implement enough of the architecture to support the current experiment cleanly, and to not make it difficult to implement more envisioned uses later.

## Architecture is a hypothesis

Treat uncertain architecture as something to test.

When implementation reveals a mismatch with `ARCHITECTURE.md`:

1. identify the concrete problem;
2. explain whether it is a domain-specific issue or a generic-core issue;
3. recommend the smallest architectural correction;
4. preserve existing working behavior where practical;
5. update the architecture only after the decision is made.

Do not silently change core concepts.

## Keep architecture visible

Keep an up to date text document under a folder `architecture` with a hierarchical overview of all classes, and for the most important ones what are their core characteristics, as currently implemented.

## CLI Discipline
 
Keep the CLI small and generic. New features do not automatically justify new top-level commands. To reach a goal, it is ok if it takes multiple commands. For example, generate, translate, pronounce should always remain separate. Before adding a command, consider whether the capability belongs under an existing command. Maintain docs/CLI.md as the complete overview of implemented commands. Every plan must show proposed CLI usage examples, and every completed implementation must show verified examples for all newly added or materially changed commands.

## Start using reality early

Move from toy examples to small real-world simulations relatively early, even when they are obviously incomplete.

## LLM don't have to be implemented right away

First build scaffolding and work with deterministic fake LLM answers.

## Cost awareness

This is a hobby project and should remain inexpensive.

Before real paid model calls become part of normal operation, implement enough accounting to attribute token use.

## Randomness should be meaningful and reproducible

Randomness could be useful for first-time generation.

However, it should always be reproducable with the same seed.

## Coding preferences

Prefer typed, explicit, small and composable code.

Prefer composition over deep inheritance.

Preserve immutable or copy-on-transition state semantics unless an experiment demonstrates a better alternative.

Keep randomness and external model calls explicit.

Add tests around architectural invariants.

Do not introduce a database, graph framework, distributed execution, elaborate plugin system or broad abstraction layer without an immediate need.

## Testing

The suite is large and `generate_language()` is expensive (phonology, a
several-hundred-word lexicon, ~30 grammar passes), so a full run used to take
20-50+ minutes. Two fixes landed to cut that down:
`inflection_gen._resolve_concatenation_collisions` had an O(n^3) hot loop
recomputing the same spelling on every (a, b) pair instead of once per entry
(fixed -- 3.17x faster `generate_language`, verified byte-identical output);
and `addopts` now runs the whole suite under `pytest-xdist` by default
(`-n auto --dist loadfile`, one worker
process per test *file*, not per individual test -- `tests/_shared_language.
py`'s `cached_language` cache is a plain process-wide dict, so splitting a
single file's tests across workers fragments that cache and erases the
parallelism gain; `--dist loadfile` keeps a whole file on one worker so it
survives). Measured on the full suite: 1687s serial (before either fix) ->
1273s serial (after the collision-loop fix) -> 799s with `--dist loadfile`
(after both) -- roughly 2.1x overall. A trivial one-file run now pays a few
seconds of xdist worker-startup overhead it didn't before; that's the
tradeoff for the full-suite win.

**Fixed: `--testmon`'s selective re-run was inert.** `pytest-testmon`
auto-disables selection whenever a `-m` marker expression is active anywhere
in the invocation ("testmon: selection automatically deactivated because -m
was used" -- visible with `-v`), and `addopts` used to carry `-m 'not slow'`
to skip the slow tripwire tests by default -- so `uv run pytest --testmon`
ran the *entire* suite (minus `slow`-marked tests) on every single
invocation, never a selective subset. Fixed by moving the slow-test skip
into `tests/conftest.py`'s `pytest_collection_modifyitems` hook instead,
which never puts `-m` on the command line. The hook detects whether the user
explicitly passed `-m` via `config.invocation_params.args` (not `config.
option.markexpr`, which can't tell "`-m ''` was typed" apart from "`-m` was
never typed" -- both parse to the same empty string) and steps aside when
they did, so the documented `pytest -m slow` (only slow tests) and
`pytest -m ''` (everything, slow included) escape hatches still work
unchanged. Verified concretely both directions: a second run with no code
changes now reports `testmon: changed files: 0` and runs nothing; editing
one test file selects exactly the test(s) whose coverage touches it, not the
whole suite.

Day to day (once the above is fixed), use `pytest-testmon` (a dev dependency)
for selective re-runs: `uv run pytest --testmon` runs only the tests whose
actual *covered code* changed since the last run (tracked via coverage, in
`.testmondata`, gitignored) -- real impact analysis, not a same-file guess,
so it also catches indirect effects (a shared rng stream, a generation-order
dependency) that touching an unrelated-looking file can still have.

- While iterating on a change confined to one module/feature: `uv run pytest
  --testmon` after each edit, and trust its answer -- don't re-verify with a
  manual full run afterward "to be safe." A change to a genuinely hot-path
  function (`_render_plan`, `generate_language`, `_decode_verb_full` --
  anything that runs on nearly every render/decode) makes testmon select
  nearly the whole suite anyway, since nearly every test's coverage profile
  includes it; in that case `--testmon` and a plain full run cost about the
  same wall-clock time (testmon usually a bit *slower*, from tracing
  overhead) -- pick one, don't run both in sequence.
- Run the full suite (`rm -rf .cache && uv run pytest -q -p no:cacheprovider`,
  no `--testmon`) every ~10 commits, whenever `.testmondata` doesn't exist yet
  or looks stale, or whenever asked. A clean full run is also the moment to
  note it (e.g. in the commit message) so the next session knows how fresh
  `--testmon`'s baseline is.
- `--testmon` needs its `.testmondata` baseline already built (one full run
  with `--testmon` first) to be selective; without it, it just runs
  everything once, slowly, while building the baseline -- effectively a
  slow full run, not a shortcut.
- Tests that generate many languages share one cache across files
  (`tests/_shared_language.py`'s `cached_language`, aliased as each file's
  own `_language`) instead of each file rebuilding the same seeds --
  reuse it (`_language = cached_language`) in any new test file that
  needs several generated languages, rather than writing a private
  per-file cache.
- A handful of tests are pure performance tripwires (decoding an unknown
  token stays fast across many languages), marked `@pytest.mark.slow`
  (skipped by default; run with `pytest -m slow`) and loosely thresholded
  on purpose -- they're guarding against a real regression recurring, not
  benchmarking exact speed, so don't tighten a threshold or lower a
  sample-size cap "to be precise": a shared, loaded machine routinely
  pushes single-digit-second decodes into the low tens of seconds with no
  code change at all, and re-running a flaky failure to check it costs
  more than the loose threshold ever would.