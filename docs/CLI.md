# CLI

Five commands. `generate`, `translate`, `pronounce` are the core trio per
AGENTS.md's CLI discipline -- new capabilities should extend one of these
rather than add a new top-level command. `audit-lexicons` (curated-data QA)
and `serve` (the local web UI) are separate utility commands, not part of
that trio, and don't compete with it for scope.

Languages are saved under `./conlangs/<slug>/` (YAML files, gitignored --
regeneratable). LLM cache and cost ledger live under `./.cache/`.

## `conlang generate`

Generate a new language and save it.

```bash
conlang generate --prompt "isolated mountain language, tonal" --name test-lang \
  --seed 42 --isolated --high-altitude --tonal --llm fake
```

```
Generated 'test-lang' (test-lang) -- 400 core words.
Word order: SVO, morphology: isolating, alignment: ergative_absolutive, tonal: True
Orthography: digraph + macron + postposed_letter
Traits from prompt: isolation=-0.16, altitude=-0.56, community_scale=-0.43, contact_intensity=+0.23, aesthetic_harshness=-0.78, tonal_friendliness=-0.92, phonotactic_restrictiveness=-0.05, tone_sandhi=-0.85, social_hierarchy=-0.90, orality_literacy=-0.74, evidentiality_culture=-0.42, spatial_reference=-0.61, ritual_register=+0.77, taboo_register=+0.45, terrain_communication_distance=+0.21
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
guarantees an outcome on its own. `--trait NAME=VALUE` (repeatable, one
per trait) sets a specific dimension directly instead of relying on the
prompt to imply it -- `NAME` is one of the 15 fields the "Traits from
prompt" line above can show (`isolation`, `altitude`, `community_scale`,
`contact_intensity`, `aesthetic_harshness`, `tonal_friendliness`,
`phonotactic_restrictiveness`, `tone_sandhi`, `social_hierarchy`,
`orality_literacy`, `evidentiality_culture`, `spatial_reference`,
`ritual_register`, `taboo_register`, `terrain_communication_distance`),
`VALUE` the same -1.0..1.0 range, and it overrides that one trait's own
prompt-inferred value without touching any other:

```bash
conlang generate --prompt "a plain language" --name trait-test --seed 1 \
  --llm fake --trait tone_sandhi=0.9 --trait altitude=-0.7
```

```
Generated 'trait-test' (trait-test) -- 400 core words.
Word order: SOV, morphology: fusional, alignment: nominative_accusative, tonal: False
Orthography: digraph
Traits from prompt: isolation=-0.12, altitude=-0.70, community_scale=+0.71, ..., tone_sandhi=+0.90, ...
Saved to conlangs\trait-test
```

`source_language_strictness`/`source_word_strictness` -- also graded,
0.0-1.0 -- aren't among `--trait`'s own accepted names; they already have
their own dedicated `--strictness`/`--word-strictness` flags above, one
way to set each rather than two. `--isolated`/`--high-altitude`/`--tonal`
are a separate, absolute channel -- "Forced (guaranteed)" -- that bypasses
the probability entirely (e.g. `--high-altitude` always produces ejectives,
regardless of what the prompt says or the trait reading). `--fantasy` is
recorded as metadata and passed as context to the classifier and to
word-coinage prompts. `--seed` controls reproducibility; `--llm` selects
`fake` (default) or `anthropic`. `--vocabulary-size` (default 400, max
496) sets how many basic meanings get pregenerated up front -- anything
else is coined on demand during translation and reused after that.

`--source-language` (repeatable) and `--example` (repeatable) bias
generation toward a real language's sound, or its actual words, or insert
literal words:

```bash
conlang generate --prompt "a small trading language" --name island-tongue --seed 7 --llm fake \
  --source-language Japanese --example "water=aqua" --example "mountain=yama|jama"
```

```
Generated 'island-tongue' (island-tongue) -- 398 core words.
Word order: SOV, morphology: isolating, alignment: nominative_accusative, tonal: False
Orthography: scholarly-macron-gemination-style
Traits from prompt: ...
Source languages: Japanese
Seed examples: water=aqua (/akwa/), mountain=yama (/jama/)
Saved to conlangs\island-tongue
```

`--source-language` matches (case-insensitively, by name or alias)
against a hand-curated set of real languages, one YAML file per language
under `generation/reference_languages/profiles/` (53 as of this writing
-- run `conlang audit-lexicons` with no arguments to list every one
currently curated) and softly biases the phoneme palette, coda typology,
cluster tolerance, and tonality toward it -- a bias, not an override;
unmatched names are silently ignored. Repeat the flag to mix more than
one, optionally suffixing a relative weight (`--source-language
'French:0.7' --source-language 'German:0.3'`; weights need not sum to 1,
normalized automatically). It's merged with whatever `--prompt` itself
implies (the classifier also extracts named languages from free text,
including ones only atmospherically evoked, not just named -- e.g.
"lowlands among windmills and canals" -- though `--llm fake` never does
either kind -- that part needs `--llm anthropic` to see for real). Many
matched profiles also carry a few of their own real spelling conventions
(Dutch spells /u/ as "oe", for instance); when one of them matches,
generated words are somewhat more likely to use those conventions instead
of the generic fallback.

`--strictness` (0.0-1.0) controls how hard that bias is pulled: 0 is
today's soft, non-exclusive influence, 1.0 hard-restricts the generated
phonology/orthography/grammar to (the union of) the matched profile(s)'
own declared values. Separately, `--word-strictness` (0.0-1.0) controls
how much of the *vocabulary itself* is based on the source language's own
real curated words, rather than just its allowed sounds -- higher means
more core-vocabulary entries are real-based *and* closer to the real
word, with 1.0 making every one of them an exact copy:

```bash
conlang generate --prompt "Mandarin using actual real words" --name mandarin-real \
  --seed 5 --source-language Mandarin --strictness 0.2 --word-strictness 0.9 --llm fake
```

```
warning: word strictness (0.90) is well above sound strictness (0.20): words based on real
source-language words will keep their own sounds while the rest of the vocabulary may sound very
different (a split vocabulary). Raise the sound strictness to keep the two consistent.
Generated 'mandarin-real' (mandarin-real) -- 398 core words.
Word order: SVO, morphology: fusional, alignment: nominative_accusative, tonal: True
Orthography: wade-giles-style
Traits from prompt: ...
Source languages: Mandarin (strictness=0.20)
Saved to conlangs\mandarin-real
```

Word strictness set well above sound strictness prints that warning (to
stderr) rather than blocking -- a real-word-heavy vocabulary sitting on
top of a looser, more invented sound system is a legitimate choice (a
deliberately "split" aesthetic), just one worth flagging. The reverse
(low word strictness, high sound strictness) is normal and silent.

`--example` takes `gloss=form` (IPA guessed from the spelling) or
`gloss=form|ipa` (explicit pronunciation) and always inserts that literal
word under that gloss, replacing whatever core-vocabulary generation
would have produced -- its phonemes are also guaranteed to be in the
generated inventory. Word-level only; sentence-level examples aren't
supported yet.

Two smaller flags round out word generation: `--word-selection` picks
between the default `algorithmic` (a seeded, no-LLM choice among each
word's own already-built candidate spellings) and `llm`
(sound-symbolism-informed, one batched request for the whole core
vocabulary); `--allow-all-caps` permits (doesn't guarantee) a rare roll
rendering a whole part-of-speech category in ALL CAPS, off by default.
`--foreign-names` sets how the language treats a foreign proper name met
in translation -- `keep` (as written, Dutch-style) or `adapt` (re-fitted
to its own sounds, Chinese-style); defaults to whatever the matched
`--source-language` implies, else `keep`.

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
marking. A matched `--source-language` profile can lean the whole roll
toward its own declared preset (Dutch toward `germanic-doubling-style`,
Mandarin toward `wade-giles-style`, Japanese and Hawaiian toward
`scholarly-macron-style`, Finnish toward `gemination-style`), and the
prompt itself can too, when it explicitly asks for a specific convention
(e.g. "mark tone with a number after each syllable, Wade-Giles
style" -- same `--llm fake`-can't-see-wording caveat as
`--source-language` above). Absent any of that, each axis is rolled
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

### Evolution (`--years`, with or without `--evolve-from`)

`--years` triggers rule-based diachronic sound change, in either of two
modes:

- **With `--evolve-from NAME`**: evolve an *existing saved language*
  instead of generating fresh -- this is how a real starting vocabulary
  (seeded with `--example`, see above) becomes "Dutch after 200 years of
  English contact":

  ```bash
  conlang generate --name dutch-en200 --evolve-from dutch-base --years 200 \
    --prompt "two hundred years of heavy English contact" --llm fake
  ```

  ```
  Evolved 'dutch-base' -> 'dutch-en200' (dutch-en200) over 200 years.
  consonants: 19 -> 24, vowels: 16 -> 15
  Evolution traits: isolation=+0.26, altitude=+0.01, community_scale=-0.94, ...
    I: noel = noel
    you: paaw = paaw
    he: smaap = smaap
    we: ja = ja
    this: grook -> rook
    that: ho = ho
  Saved to conlangs\dutch-en200
  ```

  `--prompt`/`--source-language` are reinterpreted in this mode: they
  describe the evolution period's own character (steering *how* the base
  language changes), not a fresh language's.

- **Without `--evolve-from`**: generate a fresh language exactly as
  `--prompt`/`--source-language`/etc. describe, then immediately evolve
  *that* language forward `--years` years before saving -- one step, not
  two separate `generate` calls:

  ```bash
  conlang generate --prompt "a language evolved forward 300 years under heavy contact" \
    --name evolved-fresh --seed 11 --years 300 --llm fake
  ```

  ```
  Generated 'evolved-fresh' (evolved-fresh) -- 399 core words.
  Evolved 300 years after generation.
  Word order: SOV, morphology: isolating, alignment: nominative_accusative, tonal: False
  Orthography: monoletter + short-vowel-doubling
  Traits from prompt: ...
  Saved to conlangs\evolved-fresh
  ```

  Here `--prompt` still classifies the fresh language's own traits as
  usual; the same reading also drives the evolution period's character,
  since there's only one prompt to read from.

Leaving `--years` blank uses the time depth the prompt itself implies
(e.g. "evolved forward 200 years"); `--years 0` with `--evolve-from`
evolves nothing (a no-op round trip, useful for testing).

`--llm fake`'s prompt hashing means the trait line in either mode isn't
actually reacting to the prompt's own wording -- same caveat as always,
worse in `--evolve-from` mode since two different prompt strings (base vs.
evolved) get unrelated hash noise; use `--llm anthropic`, or construct a
`TraitProfile` directly in Python, for a real side-by-side comparison at a
fixed trait profile across several `--years` values.

Two kinds of change run, independently gated: six gradient, per-position
**segmental** rules (cluster simplification, lenition, final devoicing,
palatalization, vowel reduction, ejective drift), each scaling from the
world-typical base rate toward -- never reaching -- certainty as `years`
grows, so small `--years` stays close to the original and large `--years`
drifts further, never becoming unrecognizable instantly; and, for a
tonal language, up to one **tone-system-level** change per run
(detonalization, a tone merger, a tone split, sandhi lexicalization, or --
for a currently non-tonal language -- tonogenesis), each its own
whole-language roll rather than a per-position rate, since tone
contrastiveness is systemic (see `generation/sound_change.py`'s own
`_evolve_tone_system` docstring for the real linguistic anchor behind
each). `contact_intensity` scales the simplification-leaning segmental
rules and accelerates detonalization; `altitude` scales ejective drift's
rate upward while positive `contact_intensity` additionally suppresses it
directly (heavy sustained contact keeps ejectives unlikely regardless of
time depth, not just slower to appear). Grammar is carried over from the
base language unchanged; the tone *system* is not, and may end up
enabled, disabled, or with a different level/sandhi inventory than it
started with.

Orthography evolves through two independent mechanisms, not just re-derived
from the changed IPA. A word may be **replaced** outright -- borrowed from a
`--source-language`'s own phoneme pool and spelling conventions if one is
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
applies to both fresh generation's `--source-language` bias and evolution.
See `core/romanization.py`, `generation/sound_change.py`, and
`generation/romanization_gen.py`'s module docstrings for the full rule
list, rate model, and rationale.

## `conlang translate`

Translate text to or from a generated language.

```bash
conlang translate "the mountain is high" --lang test-lang --to conlang --llm fake
```

```
twiz kiggx chmixp'afe dkheht
IPA: /twì kɪ́ɢ tʃmípʼaˈfe dχə̂/
(pattern: llm-plan)
```

```bash
conlang translate "twiz kiggx chmixp'afe dkheht" --lang test-lang --to english --llm fake
```

```
mountain is high
(pattern: llm-plan)
```

An English sentence with a word outside the core vocabulary triggers word
coinage, which is saved back to the language automatically:

```bash
conlang translate "I see the boat" --lang test-lang --to conlang --llm fake
```

```
nimtz lizmafak twiz lil'jhah
IPA: /nɪ̀mt ˈlìmafak twì ˈlīlʔhâ/
Coined 1 new word(s): lil'jhah
(pattern: llm-plan)
```

`--to` is `conlang` (default) or `english`. An LLM call
(`translation/sentence_planner.py`) drafts the sentence's own
*structure* first -- word order, which arguments get case-marked,
whether an article/copula/negation/conjunction appears, what tense/
agreement a finite verb takes -- never a word's actual spelling or
phonology; that structural plan is then rendered entirely through this
project's own existing, deterministic word-lookup/coinage and
inflection machinery. `(pattern: llm-plan)` always prints that label
now (translation used to recognize a small fixed set of sentence
shapes; it doesn't anymore -- the LLM-drafted plan can produce
genuinely arbitrary structure). `--llm fake` still produces a real,
grammar-shaped plan deterministically (not just a word-for-word
fallback), but -- same caveat as `generate`'s own prompt handling --
isn't actually reacting to the English wording itself; use `--llm
anthropic` for that.

Text is split into sentences (on `.`, `!`, `?`) and each is planned and
rendered on its own. The sentence's mood comes from the planner (with a
real LLM it reads the wording; `--llm fake` goes by the final punctuation and
a few heuristics): a plural noun takes the language's own plural suffix, an
imperative verb takes its own imperative suffix (no tense/agreement), a yes/no
question gets the language's free question particle (sentence-final, or
sentence-initial in verb-initial languages), and a wh-question keeps its
own question word and takes no particle. Every generated language now has a
plural suffix, an imperative suffix and a question particle (older saved
languages lack them and leave nouns/verbs unmarked). Subordinate clauses ("I see that you see the river", "... because ...",
relative clauses with a real LLM) are nested in the plan and rendered in
place, with the linking word ("that", "because", ...) coined like any
particle and placed after its clause in verb-final languages and before it
elsewhere. Punctuation itself is
still not written in the output. Verified with `--llm fake` on a language
generated with `--seed 3 --prompt "a plain language"`:

```bash
conlang translate "I see the mountains." --lang t1 --to conlang --llm fake
conlang translate "Do you see the mountain?" --lang t1 --to conlang --llm fake
conlang translate "Go home!" --lang t1 --to conlang --llm fake
```

```
bsaw gam gyaiwa vasauminay
ma gam gyaa vasauminan pvi
tnaplup'ua payuy
```

(Here `pvi` is the question particle, and the `-ay`-style ending on
`vasauminay` is plural on top of the object case.) Translating back marks
them: `conlang translate "ma gam gyaa vasauminan pvi" --lang t1 --to english`
gives `you mountain see?`, and `"tnaplup'ua payuy"` gives `home go!`.

```bash
conlang translate "I see that you see the river." --lang t1 --to conlang --llm fake
```

```
bsaw vasaum ma gam dia vasauminan tu
```

(`tu` is the coined `that`, sentence-final because `t1` is SOV. The `--llm fake`
planner nests a clause after `that`/`because`/`if`/`when`/`although`/`while`
only, and treats the main clause simply; a real LLM handles relative clauses
too.)

## `conlang pronounce`

Show IPA and romanization for a known word (English gloss or conlang
form), optionally synthesizing real audio.

```bash
conlang pronounce "mountain" --lang test-lang
```

```
IPA: /kɪ́ɢ/  Romanized: kiggx  Tone contour: ˥˥ (55)
```

`Tone contour:` (Chao pitch-letter/digit pairs, one per tone-bearing
syllable) only appears for a tonal language's own word. A word whose
sandhi rules change its actual spoken form gets a second line showing
that real pronunciation, distinct from its stored citation form:

```bash
conlang pronounce "on" --lang zulu-doc
```

```
IPA: /njáˈsí/  Romanized: nyásí  Tone contour: ˥˥ (55) ˥˥ (55)
Pronounced (tone sandhi): /njáˈsì/
```

`--tts {none,espeak,sapi}` (default `none`) synthesizes the word's own
*spoken* pronunciation (the post-sandhi form above, when sandhi applies)
to a `.wav` file under `./.cache/audio/`. Before attempting synthesis, it
also prints a warning (to stderr) for any tone in the word the chosen
engine genuinely can't voice -- the same check the web UI's own
`/api/pronunciation-check` makes, so a CLI user gets the same heads-up:

```bash
conlang pronounce "on" --lang zulu-doc --tts sapi
```

```
IPA: /njáˈsí/  Romanized: nyásí  Tone contour: ˥˥ (55) ˥˥ (55)
Pronounced (tone sandhi): /njáˈsì/
warning: Windows SAPI cannot voice tones: the low, high tone marks in this text will be spoken without them.
Audio saved to .cache\audio\zulu-doc-on.wav
```

`espeak` needs `espeak-ng` installed separately; `sapi` is Windows-only
(the built-in Speech API) and can't voice any tone at all (SAPI itself
rejects IPA tone marks); eSpeak voices every tone through its own
Mandarin voice instead, so the same word under `--tts espeak` prints no
warning. The warning only fires when a synthesis backend is actually
selected -- `--tts none` (the default) never checks or prints it, since
nothing gets synthesized to warn about.

## `conlang audit-lexicons`

Check the curated real lexicons (`generation/reference_languages/lexicons/`)
against their own reference profiles -- a transcription slip, or a
profile missing something the language really has.

```bash
conlang audit-lexicons Dutch Zulu
```

```
language         words  loans  off-profile  structure  flagged
Dutch              494      0            0          2      0%
Zulu                84      0            0          0      0%
all                578      0                              0%
```

With no language names given, audits every curated profile (53 as of
this writing). `off-profile` counts words using a sound the profile
doesn't list; `structure` counts words whose syllables the profile's own
phonotactics wouldn't allow. `--examples N` also prints up to N flagged
words per language; `--fail-above RATE` exits with an error if any
language's own flagged fraction exceeds it (for CI); `--include-loans`
also audits words tagged as loanwords (excluded by default, since a
loanword legitimately doesn't have to follow its host language's own
native phonotactics).

## `conlang serve`

Run the local browser UI (generate + translate).

```bash
conlang serve --port 8000
```

Requires the optional `web` dependency group: `uv sync --group web`.
`--reload` auto-restarts on source changes (development only). See
the README's Web app section for what the UI covers, and
`docs/DEFERRED.md` §2 for what is still planned.
