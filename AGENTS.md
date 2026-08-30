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