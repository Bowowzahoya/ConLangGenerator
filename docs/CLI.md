# CLI

Three commands, per AGENTS.md's CLI discipline: `generate`, `translate`, `pronounce`.
New capabilities should extend one of these rather than add a new top-level
command.

Languages are saved under `./conlangs/<slug>/` (YAML files, gitignored --
regeneratable). LLM cache and cost ledger live under `./.cache/`.

## `conlang generate`

Generate a new language and save it.

```bash
conlang generate --prompt "isolated mountain language, tonal" --name test-lang \
  --seed 42 --isolated --high-altitude --tonal --llm fake
```

```
Generated 'test-lang' (test-lang) -- 47 core words.
Word order: SVO, morphology: agglutinative, alignment: ergative_absolutive, tonal: True
Saved to conlangs\test-lang
```

Flags: `--prompt` (free text, not yet parsed by an LLM -- see spec.py),
`--name`, `--seed` (reproducibility), `--llm` (`fake` default, or
`anthropic`), `--isolated`, `--high-altitude`, `--tonal`, `--fantasy`
(typological hints -- see `core/spec.py` for what each currently affects).

## `conlang translate`

Translate text to or from a generated language.

```bash
conlang translate "the mountain is high" --lang test-lang --to conlang --llm fake
```

```
klé' 'ỳbkỳlád
IPA: /klə́ʔ ʔɨ̀bkɨ̀lád/
(pattern: predicate-adjective)
```

```bash
conlang translate "klé' 'ỳbkỳlád" --lang test-lang --to english --llm fake
```

```
mountain is high
(pattern: predicate-adjective)
```

An English sentence with a word outside the core vocabulary triggers word
coinage, which is saved back to the language automatically:

```bash
conlang translate "I see the boat" --lang test-lang --to conlang --llm fake
```

```
'ích plét kápì
IPA: /ʔítʃ plə́t kápì/
Coined 1 new word(s): kápì
(pattern: subject-verb-object)
```

`--to` is `conlang` (default) or `english`. `(pattern: ...)` reports which of
the three recognized sentence shapes was used -- see
`translation/translator.py` for the explicit limitations.

## `conlang pronounce`

Show IPA and romanization for a known word (English gloss or conlang form).
No audio synthesis yet -- see `speech/reader.py`.

```bash
conlang pronounce "mountain" --lang test-lang
```

```
IPA: /klə́ʔ/  Romanized: klé'
```
