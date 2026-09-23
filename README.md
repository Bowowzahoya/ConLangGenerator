# ConLangGenerator

Generates constructed languages from a prompt or characteristics, and
translates to/from English -- deterministically where possible, with LLM
calls only where genuine creativity is needed. Comes with a CLI and an
optional local web UI over the same generate/translate/pronounce core.

See `AGENTS.md` for development philosophy, `architecture/OVERVIEW.md` for
the current class structure, and `docs/CLI.md` for the CLI's own full
reference.

## Quick start (CLI)

```bash
uv sync
uv run conlang generate --prompt "isolated mountain language, tonal" --name test-lang \
  --seed 42 --isolated --high-altitude --tonal --llm fake
uv run conlang translate "the mountain is high" --lang test-lang --to conlang --llm fake
uv run conlang pronounce "mountain" --lang test-lang
uv run pytest            # fast run (~3 min); skips tests marked slow
uv run pytest -m slow    # only the slow ones
uv run pytest -m ""      # everything
```

`--llm fake` (the default) uses a deterministic, zero-cost stand-in for a
real model -- no API key needed. Pass `--llm anthropic` to use a real model
(requires `ANTHROPIC_API_KEY`); usage is cached and cost-tracked under
`.cache/`. `conlang --help` (or `<command> --help`) lists every flag;
`docs/CLI.md` has verified examples for each command, including
`conlang audit-lexicons` (checks the curated real lexicons against their
own reference profiles) and `conlang serve` (below).

## Web app

A local browser UI over the same core -- generate a language, inspect its
grammar/tone system/lexicon, translate to and from it, and hear a word or
sentence spoken, without typing CLI flags. Optional (a separate dependency
group, not installed by `uv sync` alone):

```bash
uv sync --group web
uv run conlang serve --port 8000
```

Then open `http://localhost:8000`. **Generate** builds and saves a
language (the same options `conlang generate` takes, via a form --
prompt, seed, source languages with their own relative weights,
strictness, seed words, trait overrides, orthography overrides,
evolution, all under "Advanced options") and shows its grammar, tone
system (levels with real IPA tone-letter contours, sandhi rules), and
full lexicon -- searchable, each word with its own pronunciation button
and, for a word based on a real source-language word, a "real" badge;
edit a word's own spelling or pronunciation in place; download the
lexicon as CSV, or the whole language as one importable file. **Translate**
sends text to or from any saved language and can speak the result
(espeak-ng or, on Windows, built-in SAPI -- picked once, used for
pronunciation everywhere on the page); it also exports/imports a whole
saved language (a portable file for sharing or backup -- importing over
an existing name asks to confirm first). Languages persist under
`./conlangs/` either way, so a language made on the CLI shows up in the
web UI and vice versa. `--reload` auto-restarts the server on source
changes (development only); `uv run uvicorn
conlang_generator.webui.app:app --port 8000` runs the same app directly,
without going through the CLI wrapper.
