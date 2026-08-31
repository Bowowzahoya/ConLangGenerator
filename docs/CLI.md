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
Word order: SOV, morphology: fusional, alignment: ergative_absolutive, tonal: True
Traits from prompt: isolation=0.39, altitude=0.88, community_scale=0.45, contact_intensity=0.72, aesthetic_harshness=0.44, tonal_friendliness=0.66, social_hierarchy=0.61, orality_literacy=0.35, evidentiality_culture=0.18, spatial_reference=0.51, ritual_register=0.61, taboo_register=0.86, terrain_communication_distance=0.89
Forced (guaranteed): isolated, high_altitude, tonal
Saved to conlangs\test-lang
```

`--prompt` is read by an LLM classification stage
(`generation/prompt_classifier.py`) into a graded `TraitProfile` --
"Traits from prompt" reports every dimension the classifier found any
evidence for (0.0 = no evidence and is omitted from the line). These only
*bias* generation probabilities; they never guarantee an outcome.
`--isolated`/`--high-altitude`/`--tonal` are a separate, absolute channel --
"Forced (guaranteed)" -- that bypasses the probability entirely (e.g.
`--high-altitude` always produces ejectives, regardless of what the prompt
says or doesn't say). `--fantasy` is recorded as metadata and passed as
context to the classifier and to word-coinage prompts. `--seed` controls
reproducibility; `--llm` selects `fake` (default) or `anthropic`.

## `conlang translate`

Translate text to or from a generated language.

```bash
conlang translate "the mountain is high" --lang test-lang --to conlang --llm fake
```

```
pètāzó tì
IPA: /pɛ̀tāzɔ́ tì/
(pattern: predicate-adjective)
```

```bash
conlang translate "pètāzó tì" --lang test-lang --to english --llm fake
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
līgégó krēt'à vīzót'ī
IPA: /līgɛ́gɔ́ kɾɛ̄tʼà vīzɔ́tʼī/
Coined 1 new word(s): krēt'à
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
IPA: /tì/  Romanized: tì
```
