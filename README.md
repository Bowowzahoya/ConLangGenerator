# ConLangGenerator

Generates constructed languages from a prompt or characteristics, and
translates to/from English -- deterministically where possible, with LLM
calls only where genuine creativity is needed.

See `AGENTS.md` for development philosophy, `architecture/OVERVIEW.md` for
the current class structure, and `docs/CLI.md` for usage.

## Quick start

```bash
uv sync
uv run conlang generate --prompt "isolated mountain language, tonal" --name test-lang \
  --seed 42 --isolated --high-altitude --tonal --llm fake
uv run conlang translate "the mountain is high" --lang test-lang --to conlang --llm fake
uv run conlang pronounce "mountain" --lang test-lang
uv run pytest
```

`--llm fake` (the default) uses a deterministic, zero-cost stand-in for a
real model -- no API key needed. Pass `--llm anthropic` to use a real model
(requires `ANTHROPIC_API_KEY`); usage is cached and cost-tracked under
`.cache/`.
