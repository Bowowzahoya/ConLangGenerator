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
Generated 'test-lang' (test-lang) -- 49 core words.
Word order: SOV, morphology: fusional, alignment: ergative_absolutive, tonal: True
Traits from prompt: isolation=-0.16, altitude=-0.56, community_scale=-0.43, contact_intensity=+0.23, aesthetic_harshness=-0.78, tonal_friendliness=-0.92, social_hierarchy=-0.90, orality_literacy=-0.74, evidentiality_culture=-0.42, spatial_reference=-0.61, ritual_register=+0.77, taboo_register=+0.45, terrain_communication_distance=+0.21
Forced (guaranteed): isolated, high_altitude, tonal
Saved to conlangs\test-lang
```

`--prompt` is read by an LLM classification stage
(`generation/prompt_classifier.py`) into a graded, **bipolar**
`TraitProfile` -- "Traits from prompt" reports every dimension the
classifier found any evidence for (`0.0` = no evidence and is omitted).
Positive values are evidence *for* a dimension's named pole, negative
values are evidence for its *opposite* (e.g. `tonal_friendliness=-0.92`
above is strong evidence the language should specifically *not* be
tonal). Either direction only *biases* generation probability -- it never
guarantees an outcome on its own. `--isolated`/`--high-altitude`/`--tonal`
are a separate, absolute channel -- "Forced (guaranteed)" -- that bypasses
the probability entirely (e.g. `--high-altitude` always produces ejectives,
regardless of what the prompt says or the trait reading). `--fantasy` is
recorded as metadata and passed as context to the classifier and to
word-coinage prompts. `--seed` controls reproducibility; `--llm` selects
`fake` (default) or `anthropic`.

`--contact-language` (repeatable) and `--example` (repeatable) bias
generation toward a real language's sound or insert literal words:

```bash
conlang generate --prompt "a small trading language" --name island-tongue --seed 7 --llm fake \
  --contact-language Japanese --example "water=aqua" --example "mountain=yama|jama"
```

```
Generated 'island-tongue' (island-tongue) -- 49 core words.
Word order: VSO, morphology: agglutinative, alignment: nominative_accusative, tonal: False
Traits from prompt: ...
Contact languages: Japanese
Seed examples: water=aqua (/akwa/), mountain=yama (/jama/)
Saved to conlangs\island-tongue
```

`--contact-language` matches (case-insensitively, by name or alias) against
a small hand-curated set of real languages in `generation/reference_languages.py`
(Japanese, Finnish, Mandarin, Arabic, Hawaiian, Georgian, a click-language
stand-in, a Romance stand-in) and softly biases the phoneme palette, coda
typology, cluster tolerance, and tonality toward it -- a bias, not an
override; unmatched names are silently ignored. It's merged with whatever
`--prompt` itself implies (the classifier also extracts named languages from
free text, though `--llm fake` never does -- that part needs `--llm anthropic`
to see for real).

`--example` takes `gloss=form` (IPA guessed from the spelling) or
`gloss=form|ipa` (explicit pronunciation) and always inserts that literal
word under that gloss, replacing whatever core-vocabulary generation would
have produced -- its phonemes are also guaranteed to be in the generated
inventory. Word-level only; sentence-level examples aren't supported yet.

## `conlang translate`

Translate text to or from a generated language.

```bash
conlang translate "the mountain is high" --lang test-lang --to conlang --llm fake
```

```
yōk bȫtë̀bsā’
IPA: /jōk bɔ̄tɛ̀bsāʔ/
(pattern: predicate-adjective)
```

```bash
conlang translate "yōk bȫtë̀bsā’" --lang test-lang --to english --llm fake
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
móp vàǯʁíz yīp
IPA: /móp vàdʒʁíz jīp/
Coined 1 new word(s): vàǯʁíz
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
IPA: /jōk/  Romanized: yōk
```
