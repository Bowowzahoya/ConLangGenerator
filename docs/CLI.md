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
a small hand-curated set of real languages, one YAML file per language
under `generation/reference_languages/profiles/` (Japanese, Finnish,
Mandarin, Arabic, Hawaiian, Georgian, a click-language stand-in, a Romance
stand-in, Dutch, French) and softly biases the phoneme palette, coda
typology, cluster tolerance, and tonality toward it -- a bias, not an
override; unmatched names are silently ignored. It's merged with whatever
`--prompt` itself implies (the classifier also extracts named languages from
free text, including ones only atmospherically evoked, not just named --
e.g. "lowlands among windmills and canals" -- though `--llm fake` never does
either kind -- that part needs `--llm anthropic` to see for real). Dutch and
Spanish also carry a few of their own real spelling conventions (Dutch
spells /u/ as "oe", for instance); when one of them matches, generated
words are somewhat more likely to use those conventions instead of the
generic fallback.

### Orthography style

A generated language's spelling conventions come from six independent
axes, all logged onto the saved language's `romanization.yaml`: how an
otherwise-exotic sound gets spelled (two ASCII letters, one Latin-Extended
letter, or a "shallow" one-ASCII-letter-per-sound system in the spirit of
Finnish/Swahili); whether/how vowel length is marked (doubling, a macron,
a colon, English-style trailing silent-e, or not at all) plus whether a
short vowel doubles the *following* onset consonant instead (Dutch/German
-- "zitten" vs. "zaten"); how tone (if any) surfaces (an inline diacritic,
a digit or letter after the syllable, or unmarked); whether/how a
vowel-initial syllable following a vowel-final one gets a separator (an
apostrophe, a hyphen, or none -- Pinyin's own real rule: "Xi'an" vs.
"Xian"); and whether a phonemically long/geminate consonant doubles its
own letter, independent of any neighboring vowel (Italian/Finnish/Japanese
-- "sono" vs. "sonno"). Because these are independent, nothing stops a
generated language from combining, say, Dutch/German-style doubling with
Wade-Giles-style postposed-digit tone marking -- a combination neither
real system has on its own. Ten named presets exist for real, attested
combinations (`digraph-style`, `diacritic-style`, `monoletter-style`,
`germanic-doubling-style`, `scholarly-macron-style`, `wade-giles-style`,
`zhuang-style`, `pinyin-style`, `silent-e-style`, `gemination-style`) --
`pinyin-style` and `wade-giles-style` are deliberately two different
presets, since real Pinyin and Wade-Giles are two different, both-real
romanizations of the same language, differing specifically on tone
marking. A matched `--contact-language` profile can lean the whole roll
toward its own declared preset (Dutch toward `germanic-doubling-style`,
Mandarin toward `wade-giles-style`, Japanese and Hawaiian toward
`scholarly-macron-style`, Finnish toward `gemination-style`), and the
prompt itself can too, when it explicitly asks for a specific convention
(e.g. "mark tone with a number after each syllable, Wade-Giles
style" -- same `--llm fake`-can't-see-wording caveat as
`--contact-language` above). Absent any of that, each axis is rolled
independently rather than picking one of the ten fixed bundles, so
combinations none of them have are freely reachable.

For an unconditional guarantee -- for testing, or when you want a
specific style and nothing else -- seven flags force it outright, the
same "guaranteed, not just likely" spirit as `--isolated`/`--high-altitude`/
`--tonal`:

- `--orthography-style NAME` forces one of the ten named presets exactly.
- `--exotic-symbol-style {digraph,diacritic,monoletter}`
- `--vowel-length-style {none,doubling,macron,colon,silent_e}`
- `--short-vowel-doubling` / `--no-short-vowel-doubling`
- `--tone-style {vowel_diacritic,postposed_digit,postposed_letter,unmarked}`
- `--syllable-boundary-marker {none,apostrophe,hyphen}`
- `--consonant-gemination-marked` / `--no-consonant-gemination-marked`

`--orthography-style` sets the whole starting point; any of the other six
then override just that one axis on top, so they compose across different
presets:

```bash
conlang generate --prompt "a trading language" --name doubling-with-digits \
  --llm fake --orthography-style germanic-doubling-style --tone-style postposed_digit
```

produces a language with Dutch/German-style vowel-length doubling *and*
Wade-Giles-style postposed-digit tone marking together -- `romanization.yaml`
shows `vowel_length_strategy: doubling`, `short_vowel_consonant_doubling:
true`, and `tone_strategy: postposed_digit` all at once. The same seven
flags work with `--evolve-from` too, as a deliberate, user-triggered
orthography reform mid-evolution (see below).

`--example` takes `gloss=form` (IPA guessed from the spelling) or
`gloss=form|ipa` (explicit pronunciation) and always inserts that literal
word under that gloss, replacing whatever core-vocabulary generation would
have produced -- its phonemes are also guaranteed to be in the generated
inventory. Word-level only; sentence-level examples aren't supported yet.

### Evolving an existing language (`--evolve-from` / `--years`)

Instead of generating fresh, evolve an *existing saved language* via
rule-based sound change -- this is how a real starting vocabulary (seeded
with `--example`, see above) becomes "Dutch after 200 years of English
contact":

```bash
conlang generate --name dutch-en200 --evolve-from dutch-base --years 200 \
  --prompt "two hundred years of heavy English contact" --llm fake
```

```
Evolved 'dutch-base' -> 'dutch-en200' (dutch-en200) over 200 years.
consonants: 18 -> 21, vowels: 13 -> 10
Evolution traits: isolation=+0.26, altitude=+0.01, community_scale=-0.94, aesthetic_harshness=+0.78, ...
  I: ɪk = ɪk
  you: yë = yë
  water: vatěr = vatěr
  mountain: bërḥ -> bër
  he: feḥi -> feḥě
  we: motramṅul -> morěmṅěl
Saved to conlangs\dutch-en200
```

`--prompt`/`--contact-language` are reinterpreted in this mode: they
describe the evolution period's own character (steering *how* the base
language changes), not a fresh language's. `--llm fake`'s prompt hashing
means the trait line above isn't actually reacting to "English contact" --
same caveat as always, worse here since two different prompt strings (base
vs. evolved) get unrelated hash noise; use `--llm anthropic`, or construct
a `TraitProfile` directly in Python, for a real side-by-side comparison at
a fixed trait profile across several `--years` values. Six sound-change
rules run (cluster simplification, lenition, final devoicing,
palatalization, vowel reduction, ejective drift), each scaling from the
world-typical base rate toward -- never reaching -- certainty as `years`
grows, so small `--years` stays close to the original and large `--years`
drifts further, never becoming unrecognizable instantly. `contact_intensity`
scales the simplification-leaning rules, and `altitude` scales ejective
drift's rate upward while positive `contact_intensity` additionally
suppresses it directly (heavy sustained contact keeps ejectives unlikely
regardless of time depth, not just slower to appear). Grammar and tone
system are carried over from the base language unchanged.

Orthography evolves through two independent mechanisms, not just re-derived
from the changed IPA. A word may be **replaced** outright -- borrowed from a
`--contact-language`'s own phoneme pool and spelling conventions if one is
set, otherwise coined natively -- at a rate that also depends on the word's
part of speech (pronouns/numerals resist replacement far longer than nouns,
which resist longer than verbs/adjectives -- a rough glottochronological
stability ranking, `lexicon_gen.STABILITY_TIER`). Every other word's
spelling comes from one evolved romanization scheme, decided per *symbol*
(not per word, so two words sharing a symbol always agree): each symbol is
either **frozen** (kept exactly as it was, even though the sound changed --
more likely the more literate/standardized the evolution period was
described as) or **reformed** (regenerated, inheriting the base scheme's
own rules for symbols that survive but a fresh style/reference lookup for
new ones) -- reform is deliberately rare by default (anchored to how
infrequent real spelling reforms are, e.g. Dutch's own 1804/1863/1946/1996/
2005), then **orthography-only drift** (dropped diacritics/ejective marks)
may simplify the result further, independent of any sound change. A word
whose sound didn't change at all this run keeps its *own* stored spelling
verbatim rather than being reconstructed through the scheme, preserving
any exception it carries.

A romanization rule can also be conditioned on syllable structure (open vs.
closed), for real orthographies that spell the same vowel differently
depending on it -- e.g. Dutch marks vowel length by doubling only in a
closed syllable ("vuur" /vy:r/ vs. "vuren" /'vy:rən/, `uu` vs. `u`); this
applies to both fresh generation's `--contact-language` bias and evolution.
See `core/romanization.py`, `generation/sound_change.py`, and
`generation/romanization_gen.py`'s module docstrings for the full rule
list, rate model, and rationale.

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
