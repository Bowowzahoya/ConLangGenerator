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

Verbs also carry **aspect** and a **verbal mood**, each its own system
separate from tense. Every generated language rolls its own aspect system
(none, two-way perfective/imperfective, or four-way perfective/progressive/
perfect/habitual) and its own verbal moods (none, just irrealis, or
subjunctive/conditional/potential); the imperative is a separate sentence
mood (above). The planner maps the English wording to the closest label the
language has ("is seeing" -> progressive, or imperfective in a two-way
system; "has seen" -> perfect, or perfective; "would see" -> conditional, or
irrealis), and a language with no such label leaves the verb unmarked. Tense
and aspect are independent ("was seeing" is past + progressive). Verified
with `--llm fake` on a language generated with `--seed 12 --prompt "x"` (a
two-way aspect system, irrealis only):

```bash
conlang translate "I see the river." --lang t2 --to conlang --llm fake
conlang translate "I am seeing the river." --lang t2 --to conlang --llm fake
conlang translate "I would see the river." --lang t2 --to conlang --llm fake
```

```
mu1 tfi1niri knal3 mun3lu1min
mu1 tfi1noiri knal3 mun3lu1min
mu1 tfi1nira'i knal3 mun3lu1min
```

Translating the verb forms back gives `I is seeing river` and `I might see
river` (the plain, fake-LLM draft; a real LLM turns the annotations into
fluent English).

**Noun classes and agreement.** Every language rolls a noun-class system
(none, masculine/feminine, masculine/feminine/neuter, animate/inanimate, or
human/animal/plant/thing) and whether its verb also agrees with the object.
A noun's class is worked out from its English lemma (natural gender and
animacy first, otherwise a stable hash) and shows only through agreement:
the article agrees with the next noun, an adjective with its noun (or, as a
predicate, the sentence's subject), a verb with a noun subject (person
agreement stays for pronouns), and, where the language has object agreement,
with its object (by person for a pronoun, by class for a noun). Verified with
`--llm fake` on a language generated with `--seed 3 --prompt p` (SOV, an
animate/inanimate system, articles, and object agreement):

```bash
conlang translate "the dog sees the river" --lang t3 --to conlang --llm fake
conlang translate "I see the dog" --lang t3 --to conlang --llm fake
conlang translate "I see the river" --lang t3 --to conlang --llm fake
```

```
swisu:k pnait swisums lignasa skutusbusalach
mipap swisu:k pnaita skutusbusu-iwg
mipap swisums lignasa skutusbusu-ach
```

The article is `swisu:k` before the animate `dog` and `swisums` before the
inanimate `river`, and the last word is the verb: its ending changes with the
subject's class in the first sentence and with the object's class in the other
two (`-iwg` after an animate object, `-ach` after an inanimate one).
Translating back drops the articles and reads the verb.

**Noun-phrase features.** Every language also rolls: an optional **dual**
number beside the plural; whether a noun after a numeral above "one" keeps its
plural; whether demonstratives (this/that) come before or after their noun
(and agree with its class); an optional **indefinite article** ("a"); and how
**possession** is marked -- the genitive case when the language has one,
otherwise a free particle after the possessor, a suffix on the possessed noun,
or nothing at all. Adposition order follows the word order (postpositions in
object-before-verb languages) and is passed to the planner. Verified with
`--llm fake` on `--seed 7 --prompt p` (SOV, particle possession, a dual,
singular after numerals) and `--seed 11` (SVO, possessed-noun suffix):

```bash
conlang translate "I see my river." --lang t4 --to conlang --llm fake
conlang translate "I see two rivers." --lang t4 --to conlang --llm fake
conlang translate "I see my river." --lang t5 --to conlang --llm fake
```

```
skè skè nu phuzó nǐ-i-akhes
skè tà phuzó nǐ-i-akhes
ṅɔ̄̄ tʰīnaṅiroṅoň ṅɔ̄̄ nʲōni
```

In the first, `nu` is the possessive particle after the possessor `skè`; in the
second, `phuzó` stays singular after the numeral `tà` because this language
does not pluralize after numerals; in the third, the possessed noun `nʲōn`
takes the suffix `-i`. Translating back marks a particle as `of` and a suffixed
noun as possessed. A demonstrative or article that has no matching word in
the language is coined on first use, like any word.

**Voice.** Every language rolls a voice system beyond the active: none, or a
passive (optionally with a causative) in a nominative-accusative language; or
an antipassive (optionally with a causative or a passive) in an
ergative-absolutive one. A voice is a verb suffix; the planner also
reassigns the arguments -- in a passive the patient is the subject with no
object case and the agent, if stated, follows or precedes "by" (per the
language's adposition order); in an antipassive the agent is a plain
absolutive subject; in a causative the causee becomes the object. A
language lacking the needed voice gets an ordinary active rewording. Verified
with `--llm fake` on `--seed 6 --prompt p` (SVO, passive and causative):

```bash
conlang translate "The dog sees the river." --lang t6 --to conlang --llm fake
conlang translate "The river is seen by the dog." --lang t6 --to conlang --llm fake
conlang translate "I made the dog see the river." --lang t6 --to conlang --llm fake
```

```
fan fusevo yutu
yut fuseevo taw' fan
da'a fusovepid fanu yut
```

In the passive the verb takes its voice suffix (`fusevo` -> `fuseevo`), the
patient `yut` moves to subject position without the object marker `-u`, and
`taw'` is "by". Translating the passive back gives `river is seen by dog`.
(`--llm fake` recognizes a passive only with an irregular participle or a
"by" phrase, and a causative only as "make X do Y"; a real LLM handles the
rest, including antipassives, which the fake planner never produces.)

**Existentials and possession clauses.** Every language chooses how to say
"there is X" -- X plus the copula (or just X where there is no overt copula),
or X plus a dedicated verb "exist" -- and how to say "A has B" -- the
transitive verb "have", or, with no verb "have", A first (in the dative if the
language has one, otherwise possessor-marked) followed by the existential
construction with B as its subject. The planner is told the language's own
strategy and writes the plan accordingly (never a slot for "there"), and the
English direction is told how to read the pattern back. Verified with
`--llm fake`: `--seed 2` is a copula + "have" language (SVO), `--seed 8` an
"exist" verb + dative-possessor language (SVO, dative case):

```bash
conlang translate "There is a dog." --lang t8 --to conlang --llm fake
conlang translate "I have a dog." --lang t8 --to conlang --llm fake
conlang translate "There is a dog." --lang t7 --to conlang --llm fake
conlang translate "I have a dog." --lang t7 --to conlang --llm fake
```

```
ts'sēi fyaě kỉkngẻeaa
gaì khîee ts'sēi fyaěu
na2pzu5zai te'3 ha2xo5goet
mi4ha na2pzu5zai te'3 ha2xo5goet
```

In `t8` the noun `fyaě` takes the copula `kỉkngẻeaa` for "there is", and "I
have a dog" uses the verb `khîee` with an object-marked `fyaěu`. In `t7`
"there is" is the verb `ha2xo5goet` ("exist"), and "I have a dog" is the same
construction with the possessor `mi4ha` (dative "I") in front and no verb
"have" at all. A question ("Is there a river?") gets the language's question
particle as usual. (`--llm fake` recognizes "there is/are/was X", "is there
X?", "there is no X" and, in dative-possessor languages, "A has/had B".)

**Comparatives and superlatives.** Every language decides how to mark the
comparative ("bigger") and the superlative ("biggest") -- each independently a
suffix on the adjective or a separate word ("more"/"most") -- and how to mark
the standard of comparison ("than Y"): a word "than" beside the standard (in
the language's adposition order), the standard in an oblique case (no extra
word), or a verb "exceed" with the standard as its object. The planner is told
the language's own choices; the English direction is given them too. Verified
with `--llm fake`: `--seed 2` (comparative and superlative suffixes, standard in
the dative case) and `--seed 6` (words "more"/"most" and a particle "than", no
overt copula):

```bash
conlang translate "The dog is bigger than the cat." --lang t9 --to conlang --llm fake
conlang translate "The dog is the biggest." --lang t9 --to conlang --llm fake
conlang translate "The dog is bigger than the cat." --lang t10 --to conlang --llm fake
conlang translate "The dog is the biggest." --lang t10 --to conlang --llm fake
```

```
sīi fyaě kỉkngẻeaa mbnaèaai sīoi knaỉa
sīi fyaě kỉkngẻeaa mbnaèii
fan hanv dudatyaum nuw la
fan 'us dudatyaum
```

In `t9` the adjective `mbnaè-` takes `-aai` (comparative) or `-ii` (superlative)
and the cat `knaỉa` is in the dative with its own agreeing article; in `t10`
the same sentence is `dog more big than cat` (`hanv` = "more", `nuw` = "than")
and the superlative is `dog most big` (`'us` = "most"). Translating
`t9`'s superlative back gives `dog is most big` (the plain draft; a real LLM
smooths it into "the dog is the biggest"). `--llm fake` plans only the
"X is [more/-er/most/-est] Adj [than Y]" shape from a small list of known
adjectives; a real LLM handles the rest.

**Classifiers.** A language may use numeral classifiers (12% of the time, 45%
when it is isolating): a classifier word, chosen by the noun's meaning (human,
animal, long, flat, round, general), follows a numeral or demonstrative before
its noun, and the noun stays singular after a numeral. The renderer adds the
classifier itself (the planner is told not to); each category's classifier is an
ordinary lexicon word coined on first use, and it is dropped when translating
back to English. Verified with `--llm fake` on `--seed 4 --prompt p` (SVO,
isolating, classifiers):

```bash
conlang translate "I see two dogs." --lang t11 --to conlang --llm fake
conlang translate "I see two rivers." --lang t11 --to conlang --llm fake
```

```
mudz ngazkhejshiaash pngu'j fngux lizmij
mudz ngazkhejshiaash pngu'j pigx dejtslanz
```

The numeral `pngu'j` ("two") is followed by `fngux` (animal classifier) before
`lizmij` (dog), and by `pigx` (long-thing classifier) before `dejtslanz`
(river). Translating the second back gives `I see two river`.

Classifier languages vary: each has classifiers for its own subset of twelve
noun categories (human, animal, long, flat, round, plant, container,
building, vehicle, tool, food, plus a general one that takes any noun whose
category the language lacks); a quarter put the numeral and classifier after
the noun (noun-numeral-classifier, as in Thai) instead of before it; and most
(80%) also use a classifier after a demonstrative.

**Pronoun system.** Beyond the core I/you/he/we, every language always has
`you-plural` and `they`, and rolls: an inclusive/exclusive split of "we" (15%),
a separate `she` and `it` instead of one third person (35%), a polite
`you-polite` (15%, more likely with a high `social_hierarchy` trait), and
**pro-drop** (35%, only if the four person suffixes on the verb are distinct):
the subject pronoun is omitted when the verb's agreement names the person.
The planner is given the language's pronoun glosses and how to map English
pronouns onto them; plural and polite pronouns agree like their singular person
and `they` like `he`. New pronouns are coined on first use, read back as e.g.
`you (plural)`, and a dropped subject is read back from the verb's agreement.
Verified with `--llm fake` on `--seed 6 --prompt p` (separate `she`/`it`, pro-drop):

```bash
conlang translate "I see the river." --lang t12 --to conlang --llm fake
conlang translate "She sees the river." --lang t12 --to conlang --llm fake
conlang translate "You see the river." --lang t12 --to conlang --llm fake
```

```
fusevid yutu
fusevan yutu
fusevad yutu
```

No pronoun is written: the verb `fusev-` ends in `-id` (I), `-an` (she) or `-ad`
(you), and `yutu` is the object. Translating the last back gives `you see
river`. (The fake planner maps she/it/they/me/him/us/them and, with a language
that has one, `you-polite` after a cue word like "sir"; a real LLM decides
politeness and clusivity from context.)

**Reflexives, reciprocals, possessive pronouns, verb number and politeness,
object pro-drop.** Every language also chooses:

- how to say "himself" and "each other": a word (`self`, `each-other`, an
  object pronoun), a suffix on the verb (a `reflexive`/`reciprocal` voice, no
  object), or just an ordinary pronoun;
- how to say "my/your/his...": the personal pronoun plus the language's
  possession marking (as before), a possessive word per person
  (`possessive-I`, `possessive-you`... agreeing with the noun's class), or a
  person suffix on the possessed noun;
- whether the verb marks a plural subject (25%) and, in a language with a
  polite "you", a polite subject (60% of those) with a suffix of its own;
- whether an object pronoun is omitted when the verb's object agreement names
  it (only where the verb agrees with objects by person).

The planner is told each choice; the English direction reads them back
(`oneself`, `each other`, `my`, `possessed by: I`, `subject: plural`,
`polite`, and a dropped object such as `him`). Verified with `--llm fake`:
`--seed 7 --prompt p` (SVO; reflexive suffix, reciprocal word, possessive
words, verb number) and `--seed 3` (SVO; reflexive word, possessive person
suffix, object pro-drop):

```bash
conlang translate "He sees the dog." --lang t13 --to conlang --llm fake
conlang translate "He sees himself." --lang t13 --to conlang --llm fake
conlang translate "They see each other." --lang t13 --to conlang --llm fake
conlang translate "I see my dog." --lang t13 --to conlang --llm fake
conlang translate "They see the dog." --lang t13 --to conlang --llm fake
conlang translate "I see my dog." --lang t14 --to conlang --llm fake
conlang translate "He sees you." --lang t14 --to conlang --llm fake
```

```
tā ngûgo phutâ nǐ-i-u-udh
tā nǐ-ei-i-u
pủh nǎd nǐ-i-u-umbeny
skè bsēko phutâ nǐ-i-akhudh
pủh ngûgo phutâ nǐ-i-u-umbudh
mipap pnaitida skutusbusu-iwg
pyasdut skutusbusu-ask
```

In `t13`, "himself" is a verb suffix (`nǐ-ei-i-u`, no object); "each other" is
the word `nǎd`; "my" is the word `bsēko` before `phutâ` (dog); and the verb of
"They see the dog" ends in `-umbudh` where "He sees the dog" ends in `-udh`
(the `-umb` marks a plural subject). In `t14`, "my dog" is `pnaitida` (the dog
with a first-person suffix `-da`), and "He sees you" has no object pronoun: the
verb ending `-ask` names "you"; translating it back gives `he see you`.

**Suppletive pronoun forms, reflexive possessives, possessive classifiers.** Some
languages give a personal pronoun's non-nominative forms words of their own
(I/me/my: 35% of languages, for a random subset of I/you/he/we; the other
persons keep the ordinary case suffix), so "me" is a lexicon word
(`i-accusative`) rather than "I" plus a suffix. A language may also have a
reflexive possessive ("his own dog"): a word (`possessive-self`), a suffix on the
noun, or nothing special. And a classifier language may put a possessive
classifier between a possessor word and the possessed noun (30% of classifier
languages; chosen by the possessed noun's category). The planner is told all of
these; the English direction reads them back (`me`, `his`, `one's own`, and drops
the possessive classifier). Verified with `--llm fake` on `--seed 15 --prompt p`
(SOV, suppletive I/he/we, reflexive-possessive suffix) and `--seed 74`
(SVO, possessive words, possessive classifiers):

```bash
conlang translate "He sees me." --lang t19 --to conlang --llm fake
conlang translate "I see him." --lang t19 --to conlang --llm fake
conlang translate "He sees his dog." --lang t19 --to conlang --llm fake
conlang translate "He sees his own dog." --lang t19 --to conlang --llm fake
conlang translate "I see my dog." --lang t18 --to conlang --llm fake
conlang translate "I see my river." --lang t18 --to conlang --llm fake
```

```
rok2 snaw5 ski3nãkaim
kav4 tłi5 ski3nãkaa
rok2 sin2 smãms4nu2la ski3nãkaim
rok2 smãms4nu2lowa ski3nãkaim
ku2 pawi2ura pu1ko1mim kiy3 da3
ku2 pawi2ura pu1ko1mar ngiy3 taung3
```

In `t19`, `rok2` is "he" and `kav4` "I", but the object forms are their own words:
`snaw5` is "me" and `tłi5` is "him"; the genitive "his" is `sin2` (a word, not
a suffix on `rok2`), while "his own" has no separate word -- the noun takes the
reflexive-possessive suffix (`smãms4nu2lowa`, against plain `smãms4nu2la`). In
`t18`, "my" is the possessive word `pu1ko1m-` (agreeing with the noun) followed by
a possessive classifier: `kiy3` (the general one) before "dog" and `ngiy3` (the
long-thing one) before "river"; translating the last back gives `I see my river`
(the classifier is dropped).

**Classifiers with quantifiers, and per-noun classifiers.** In a classifier
language, a quantifier ("many", "few", "some", "several", "all", "every", "each",
"both", "how many") takes a classifier like a numeral does -- but each language
picks a random half of these quantifiers that do (the rest stand bare, and their
noun keeps its plural). And a noun's classifier need not follow its meaning: 30%
of classifier languages assign each noun one of a pool of 12-40 classifiers
(arbitrary but stable, `classifier-lex14`), and 60% have *repeaters* -- 10-50% of
nouns are their own classifier ("two river river"), the repeated noun being
dropped again when translating back to English. Verified with `--llm fake` on
`--seed 85 --prompt p` (SVO; a pool of 35 classifiers, about half the nouns
repeaters, "many"/"few" classified, "all" not):

```bash
conlang translate "I see two dogs." --lang t20 --to conlang --llm fake
conlang translate "I see two rivers." --lang t20 --to conlang --llm fake
conlang translate "I see two boats." --lang t20 --to conlang --llm fake
conlang translate "I see many dogs." --lang t20 --to conlang --llm fake
conlang translate "I see all dogs." --lang t20 --to conlang --llm fake
```

```
nek maman'ung kin tig penat
nek maman'ung kin nguleng nguleng
nek maman'ung kin 'u kuwon
nek maman'ung ye' tig penat
nek maman'ung yik penata
```

After the numeral `kin` ("two") comes a classifier: `tig` for dog, `'u` for boat --
words from the language's pool -- but for "river" the noun repeats itself
(`nguleng nguleng`). "Many" (`ye'`) takes the same classifier as a numeral
(`ye' tig penat`), while "all" (`yik`) does not, and its noun stays plural
(`penata`). The planner is told which quantifiers take a classifier (and to write
them as `"pos":"quantifier"`); it never writes a classifier itself.

**Subordination.** Clauses inside clauses are no longer laid out by a rule of
thumb; each language rolls how it does them:

- **Where the subordinator goes** ("that", "because", "if"): before or after its
  clause (after in about 70% of verb-final languages, before in about 85% of the
  rest).
- **Relative clauses**: a relative *pronoun* (who/which), one invariant *particle*,
  a *gap* (no linking word, the relativized noun simply left out, as in
  Japanese), a *resumptive* pronoun kept in the clause, or a *correlative* (the
  relative clause comes first and the main clause points back with "that"); and the
  clause goes before or after its noun (mostly before in object-before-verb
  languages).
- **Non-finite verbs**: an *infinitive* ("I want to see"), a *nominalized* form and
  a *participle* ("the man sleeping"), each a suffix that replaces tense and
  agreement (a language without one uses a finite clause with a repeated subject).
- **Subjunctive in subordinate clauses**: about half the languages put the verb of
  an "if"/"unless"/"so that"/"although" clause in the subjunctive or irrealis (if
  they have one).

The renderer enforces the relative-clause strategy and position itself, whatever
linking word the planner wrote. Verified with `--llm fake` on `--seed 26`
(SVO; a relative particle, clause before its noun; an infinitive; irrealis in "if"
clauses), `--seed 6` (a correlative) and `--seed 13` (a gap):

```bash
conlang translate "I see the dog who sleeps." --lang t22 --to conlang --llm fake
conlang translate "I want to see the river." --lang t22 --to conlang --llm fake
conlang translate "I see the river if you see the dog." --lang t22 --to conlang --llm fake
conlang translate "I see the dog who sleeps." --lang t23 --to conlang --llm fake
conlang translate "I see the dog who sleeps." --lang t24 --to conlang --llm fake
```

```
sey3 gʱi1yunʲineṅ bʱa3unʲiṅ xʲẽ3 ṅɔ̃ṅ1mʲem3
sey3 po1da3unʲin gʱi1yow ǯʱi3muy
sey3 gʱi1yunʲinaṅ ǯʱi3muy ǯʱu1say1đew3 pa3du3 gʱi1yunʲiwireṅ ṅɔ̃ṅ1mʲem3
mun kapdihevo fusevid yuw fanu
lāt mùnê'o'o nuwōkáhū'e mì'o'u
```

In `t22` the relative clause is `bʱa3unʲiṅ` ("sleeps") plus the relative particle
`xʲẽ3`, and both come *before* the noun `ṅɔ̃ṅ1mʲem3` ("dog"); "want to see" is the
plain infinitive `gʱi1yow` with no subject or tense; and the verb after "if" (`…wireṅ`,
irrealis) differs from the main verb (`…naṅ`); translating that sentence back gives
`I see river if you might see dog`. In `t23` the relative clause (`mun kapdihevo`)
opens the sentence and the main clause points back with `yuw` ("that") before the
noun (the subject "I" is dropped, this language being pro-drop). In `t24` the
relative clause is just the verb `mì'o'u` after the noun, with no linking word.

**Subordination follow-ups.** Eight more choices per language:

- **Relativization reach.** A gap or particle relative clause reaches only up to a
  rolled position on the hierarchy subject > object > oblique > possessor; a clause
  beyond it ("the man whose dog...") takes the invariant word `rel` plus a resumptive
  pronoun. The planner marks each relative clause's `rel_function`.
- **Declining relative pronouns.** Where a language uses relative pronouns they may
  take the case of their function (who/whom/whose) and a plural, as separate lexicon
  words (`who-accusative`, `who-genitive-plural`).
- **Infinitives that agree with their controller** ("I told him to go": the
  infinitive takes "him"'s person), and **nominalized clauses** ("seeing the river")
  that take the case of their function.
- **Conditionals**: the main clause of an "if" sentence takes the conditional mood,
  and the "if" clause a fixed tense, in about half the languages.
- **Correlatives beyond relatives**: "if"/"when"/"the more" clauses come first, with a
  correlate ("then") opening the main clause.
- **Clause coordination**: a conjunction word, a *converb* (the first verb takes a
  medial suffix, no conjunction) or plain juxtaposition; a shared subject pronoun
  can be dropped from the second clause.
- **Complementizers by verb class**: separate "that" words after speech/thought,
  desire, perception and factive verbs.

The renderer enforces all of these whatever the planner wrote, except where noted; the
English direction reads them back (`whom`, `whose`, `that`, `see and`, `to go`).
Verified with `--llm fake` on `--seed 54 --prompt p` (SVO; a gap relative reaching only
to objects, verb-class complementizers, correlatives, agreeing infinitives) and
`--seed 62` (a converb coordination):

```bash
conlang translate "I see the dog which I hear." --lang t25 --to conlang --llm fake
conlang translate "I see the man whose dog sleeps." --lang t25 --to conlang --llm fake
conlang translate "I told him to go." --lang t25 --to conlang --llm fake
conlang translate "I want to go." --lang t25 --to conlang --llm fake
conlang translate "I think that you see the river." --lang t25 --to conlang --llm fake
conlang translate "I know that you see the river." --lang t25 --to conlang --llm fake
conlang translate "I see the river if you sleep." --lang t25 --to conlang --llm fake
conlang translate "I see the dog and I hear the cat." --lang t26 --to conlang --llm fake
```

```
gin riwtahuggidip tuctut gin pwipidi
gin riwtahuggidip buh kic gnold tuctuttan hi-idi
gin qalpri-itipo gnold tmido-oso
gin ze-idip tmido-osip
gin dobinidi clo me riwtahuggidip pmip
gin spirbosdidi we me riwtahuggidip pmip
peso me hi sna gin riwtahuggidatip pmip
nảw fa2aimt lan3ça4ṅa nảw tim1ĵi2ṅumimt guṅ5mɛ̄5ma
```

In `t25`, "the dog which I hear" is a bare gap (an object relative is within its reach),
but "the man whose dog sleeps" -- a possessor, beyond the reach -- takes `kic` (`rel`) and
keeps a resumptive pronoun `gnold` ("he", possessive) before "dog". The infinitive of
"go" is `tmido-oso` after "told him" and `tmido-osip` after "want" (it agrees with its
controller, "he" and "I"). The complementizer is `clo` after "think" (speech), `we`
after "know" (factive) and `yan` after "see" (perception). In the "if" sentence the
clause `me hi` ("you sleep") leads, "then" (`sna`) opens the main clause, and the main
verb (`…datip`) is in the conditional mood. In `t26` there is no "and": the first verb
"see" takes the converb suffix (`fa2aimt`); translating back gives `I see and dog I hear cat`.

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

**Agreement follow-ups.** Per language: how nouns without natural gender get a class
(arbitrarily, by semantic field, or by final sound), whether the noun itself carries
its class as a prefix or suffix, and which of article, adjective, demonstrative,
possessive and numeral agree in class, number and case. The renderer works out the
agreeing noun from word position. Verified with `--llm fake` on `--seed 7 --prompt p`
(three classes, class suffix on the noun):

```bash
conlang translate "I see the dog." --lang t26 --to conlang --llm fake
conlang translate "I see the river." --lang t26 --to conlang --llm fake
conlang translate "The river is big." --lang t26 --to conlang --llm fake
```

Gives `skè ngûgo phutâ-al nǐ-i-akhudh` and `skè ngûgang phuzó-i nǐ-i-akhip`: the nouns
`phutâ-` (dog) and `phuzó-` (river) end in different class markers (`-al`, `-i`).

**Aspect/mood follow-ups.** Per language: which tenses, aspects and moods are spelled with an
auxiliary word (before or after the verb) instead of a suffix; an evidential system
(`reported`/`inferred`/`witnessed`); whether negation is a word, a verb suffix or both; and a
prohibitive for negated commands. Inflectional suffixes no longer repeat within a paradigm, and
they change when a language evolves. Verified with `--llm fake` on `--seed 27 --prompt p`
(negation as a verb suffix, a prohibitive, all three evidentials, periphrastic future/perfect
before the verb):

```bash
conlang translate "I did not see the river." --lang t27 --to conlang --llm fake
conlang translate "I will see the river." --lang t27 --to conlang --llm fake
conlang translate "I reportedly see the river." --lang t27 --to conlang --llm fake
conlang translate "Do not see the river!" --lang t27 --to conlang --llm fake
```

The negated verb `ksinàaaokan` carries past and the negative suffix (read back as `not saw`); the
future is the auxiliary `nīfprúkǎ` before the plain verb `ksinà` (read back as `will see`);
`ksinàaiyokan` adds the reported evidential (`reportedly`); and the negated command is the single
prohibitive form `ksinàap` (`do not see!`).

**Voice and noun-phrase follow-ups.** Per language: extra voices (middle, applicative,
impersonal); whether the passive agrees and whether its agent is "by" or an instrumental case;
trial and collective number; locative and instrumental case, with adpositions either kept
(governing a case) or replaced by it; irregular plurals (`child` -> `children`) and
comparatives (`good` -> `better`) as words of their own; and inalienable possession. Verified
with `--llm fake`: `--seed 6 --prompt p` (middle voice, trial) as `t28`, `--seed 5` (applicative
voice) as `t29`, `--seed 2` (irregular plurals) as `t30`:

```bash
conlang translate "The door opens." --lang t28 --to conlang --llm fake
conlang translate "I cook for him." --lang t29 --to conlang --llm fake
conlang translate "I see the children." --lang t30 --to conlang --llm fake
conlang translate "I see the child." --lang t30 --to conlang --llm fake
```

The middle verb `fukilnevo` reads back as `gets opened`; the applicative verb `za3memiwy'` as `I cook for` (with `khir4` = `him`);
and `t30`'s irregular plural (`kèkhuẻi`) is a different word from the singular (`fyǐi`) and reads
back as `children`.

**Noun-phrase follow-ups, round two.** Per language: a suppletive pronoun may be suppletive in only some of
its cases; adjectives keep to a language-wide order when stacked (and may be joined by "and" or split
around the noun by class); and a third article ("a certain") or a definite article reduced from "that" may
exist. Verified with `--llm fake`: `--seed 2 --prompt p` as `t31` (specific article; the pronoun `I`
suppletive only in accusative and dative) and `--seed 4` as `t32` (adjectives ordered quality, colour, size
and joined by "and"):

```bash
conlang translate "I see a certain dog." --lang t31 --to conlang --llm fake
conlang translate "I see a dog." --lang t31 --to conlang --llm fake
conlang translate "I see the big red dog." --lang t32 --to conlang --llm fake
conlang translate "I see the red big dog." --lang t32 --to conlang --llm fake
```

`t31` gives `fnaīnyê` for "a certain" (read back as `a certain`) against `ts'sēi` for plain "a"; `t32`
gives the same six words for both adjective orders, with the joining word `shiz` between the two
adjectives (read back as `red and big`).

**Noun-phrase follow-ups, round three.** Per language: irregular pasts as words of their own (`go` ->
`went`), a reduced clitic form of "this/that" beside a noun, and more spatial cases (ablative, allative,
comitative) with a wider list of adpositions; also classifiers beside adjectives, "of" dropped in "a cup of
water", possessive words for only some persons, and a doubled definite article. Verified with `--llm fake`:
`--seed 3 --prompt p` as `t34` (irregular pasts, ablative/allative/comitative) and `--seed 1` as `t35`
(a reduced demonstrative):

```bash
conlang translate "I see the river." --lang t34 --to conlang --llm fake
conlang translate "I saw the river." --lang t34 --to conlang --llm fake
conlang translate "I see this dog." --lang t35 --to conlang --llm fake
```

In `t34` the verb of "I saw the river" is `saisasu-ach`, a word of its own for the past of "see", against
`skutusbusu-ach` for the present, and it reads back as `saw`. In `t35` "this" is `toh` on its own but the
reduced `oh` beside a noun.

**Comparison follow-ups.** Per language: the equative ("as big as"), excessive ("too big") and elative
("very big") are each a suffix or an adverb; the standard of a comparison may take an ablative or locative (or
dative/genitive) case instead of "than"; some languages also put a degree suffix on adverbs; and "the more...,
the more..." is written as two parallel parts. Verified with `--llm fake`: `--seed 2 --prompt p` as `t36` (all
five degrees are suffixes; dative standard) and `--seed 3` as `t37` (adverbs for every degree; locative standard):

```bash
conlang translate "The dog is as big as the cat." --lang t36 --to conlang --llm fake
conlang translate "The dog is too big." --lang t36 --to conlang --llm fake
conlang translate "The dog is very big." --lang t36 --to conlang --llm fake
conlang translate "The dog is bigger than the cat." --lang t37 --to conlang --llm fake
conlang translate "The more you read, the more you learn." --lang t37 --to conlang --llm fake
```

In `t36` "big" is `mbnaèi` and becomes `mbnaèeia` (as big as), `mbnaèeui` (too big) and `mbnaèaii` (very big);
the equative's standard is `sīoi knaỉa`, "the cat" in the dative. In `t37` the standard `chami-ue` carries the
locative and reads back as `than cat`.
