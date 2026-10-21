# Deferred work

Work identified during development that is **not done yet**. Finished items
have been removed (see `architecture/OVERVIEW.md` for history); things
consciously not implemented live in `LIMITATIONS.md`.

Rough effort tags: **S** = an hour or two, **M** = a session, **L** = a
multi-session feature.

---

## 1. LLM usage and cost

- **Trait-classifier call is expensive for what it does (S-M).** One
  `prompt.classify_traits` call costs about $0.005 on Haiku 4.5: ~3,250
  input tokens (~$0.0033) and ~320 output tokens (~$0.0016), from
  `generation/prompt_classifier.py`. Almost all input is the fixed
  `_SYSTEM_PROMPT` (~12k characters: rules, 15 dimension descriptions, ~11
  worked examples), identical on every call. Output is a JSON object with
  all 15 dimensions, most of them 0.0. Options, cheapest first:
  (a) ask for only non-zero fields, omitting the rest (output roughly
  halves); (b) trim/merge worked examples and the long strictness prose;
  (c) prompt caching does not apply as-is (Haiku 4.5 needs a >=4096-token
  prefix; the prompt is ~3.2k), so only worthwhile if the prompt grows.
  Quality risk is real: the prompt was calibrated on eight prompts, and the
  examples are what keep values calibrated (0.3 vs 0.9). Any cut should be
  re-checked with a fixed prompt set against the saved classifier outputs
  before adopting. The end result is ~$0.002-0.003; do not expect
  much lower.
- **Translation output is sometimes far too short (S-M, partly done).**
  Reported: "My friend, I think you are really dumb. Just piss off. You are
  a lkdjhr" into a Dutch-like language gave "sko kiszomongo holt stoehol".
  Done: input is now split into sentences and each is planned on its own
  (previously one prompt whose system text said "one sentence"). Still open:
  a "never drop meaningful words" check that compares plan glosses with the
  input's content words and warns or falls back per word; `max_tokens=500`
  on long sentences; "I think you are dumb" needs subordinate clauses (§10).
  Not yet re-tested against a real LLM.
- **Reset button for the cumulative cost display (S-M).** The top-right
  badge (`webui/app.py::_cost_snapshot`) shows the *all-time* total from
  `cost_ledger.jsonl`, an append-only real-spend record -- a destructive
  "clear" button would erase that history, which cuts against this
  project's own cost-awareness stance (`AGENTS.md`: "implement enough
  accounting to attribute token use"). Needs a design decision before
  implementing: archive-then-clear (rename the ledger to a timestamped
  backup, e.g. `cost_ledger.2026-10-16.jsonl`, and start a fresh one)
  preserves the real record while giving the user a fresh-looking total,
  vs. a lighter-weight "reset point" marker (store a timestamp or ledger
  line count that `summarize()` filters from, leaving the ledger itself
  untouched) that needs no file rotation. Either needs a new endpoint (e.g.
  `POST /api/cost/reset`); no existing mechanism does this today.

## 2. Web app

- **Voice picker within an engine (S).** No choice of SAPI or eSpeak voice
  -- see §9's multi-engine item, which subsumes this.
- **Reorganize the Generate/Inspect result view into labeled sections, and Advanced Options to match
  -- done.** `renderLanguageSummary` (the one function behind the Generate tab's own result, the
  Inspect tab, and Translate's "view details") now renders 7 bordered `.summary-section` blocks
  (Language Sources & Evolution, Grammar, Phonology (incl. Traits), Tones, Roman Orthography, Writing
  system, Generation Details -- Tones/Writing system omitted entirely when not applicable, same
  precedent as before). Advanced Options' own `fieldset.advanced-group`s were regrouped to the same
  6 names/boundaries (no "Grammar" fieldset there -- no Advanced Option today forces anything
  grammar-specific; add one if that ever changes). `_language_summary` gained `classifier_model`/
  `word_selection_model` (recorded at generation time, never surfaced to the web UI before). Pure
  markup reorganization otherwise -- every field/badge kept its own existing id, so no other JS
  needed to change. See `architecture/OVERVIEW.md` for the full mapping.
- **More intuitive script typing: key assignment by sound identity, not just position -- done.**
  `script.script_render.assign_keyboard_triggers` replaces the old purely-positional
  `keyboard_key_for_symbol_index`: identity first (a glyph whose own IPA symbol is already a plain key
  types with that exact key -- "p" -> /p/, "a" -> /a/), then this language's own actual romanization
  of whatever's left when that spelling happens to be a plain, free, 2+ character ASCII sequence (a
  digraph-style language's "sh" for /ʃ/, or just a diphthong that already romanizes plainly, like
  "ai"), then positional single-key fallback for whatever's still unplaced. Reuses
  `RomanizationScheme.apply` directly rather than a separate static table, so it adapts automatically
  to whichever exotic-symbol style a given language actually rolled. The real OS-keyboard/IME option
  was considered and set aside (install step outside the browser, breaks the zero-install web demo).
  See `architecture/OVERVIEW.md` for the implementation and verification notes.
- **Show a multi-section trait (e.g. `isolation`) in every section it actually affects, synced, with a
  per-section-relevant description (L) -- direct user request, not yet designed.** Several of the 15
  worldbuilding traits have documented effects landing in more than one section (`isolation` nudges both
  phonology, uvulars, and grammar, ergative alignment/morphology; `terrain_communication_distance` and
  several others affect evolution specifically, see §11's own item on this) but `TRAIT_SECTION`
  (`webui/static/index.html`) assigns each trait to exactly *one* section today, by its most prominent
  effect -- so a trait's other, real effects go unmentioned wherever it doesn't appear. The user's own
  request has three distinct parts, each with its own real cost: (1) **render the same trait's row in
  every section it affects** -- straightforward to loop over a trait-to-sections *list* instead of a
  single section, reusing the existing row-building code as-is; (2) **keep every copy's value in sync**
  -- needs either a single shared input moved via DOM reparenting (awkward with per-section layout) or
  duplicate inputs wired to mirror each other's value on every `input` event (simpler, the more likely
  approach); (3) **a different description per section, each explaining only that section's own
  relevant effect while still noting what changes elsewhere** -- this is a real content-authoring task,
  not a code change: `TRAIT_GLOSSARY` would need a *second* dimension (per trait, per section) rather
  than one summary/positive/negative triple, for every multi-section trait -- a non-trivial rewrite of
  `webui/glossary.py`'s own data shape, not just its text. Scope (3) realistically before starting, since
  it's the part most likely to balloon in practice (potentially a dozen-plus trait x section
  description pairs to write well).

## 3. Translation

- **Sentence-initial capitals treated as names (S, mostly done).** A
  capitalized sentence-initial word is now only treated as a name if it
  isn't an ordinary English word, and per-sentence (not whole-text)
  planning stops the fake planner from mistaking a later-sentence "Just"/
  "You" for a name. Still open: a real LLM still makes this mistake
  sometimes; only its worst consequence (silently discarding a
  misclassified word instead of reusing an existing entry) is fixed. See
  `architecture/OVERVIEW.md`.
- **A true multi-word proper name with no generic descriptor part (M).**
  "Lake Baikal"/"Mount Everest"-style names now split correctly (the
  descriptor becomes an ordinary word, the rest becomes the name), but a
  name like "New York" or "Los Angeles" has no generic part to split on
  and still isn't handled anywhere -- no mechanical way exists to know
  where such a name should split. Passes through as one literal unit
  under `"keep"`, or gets silently fused into one native-looking word
  under `"adapt"` (see `docs/LIMITATIONS.md`).
- **Unknown words are coined silently (M).** A word like "lkjejhrj" is
  looked up, not found, and `translation/expansion.coin_word` invents a
  word. The part of speech comes from the LLM plan (unknown or missing
  `pos` defaults to noun in `sentence_planner._parse`), not from any
  analysis of the word; a nonsense token therefore becomes a noun and is
  stored in the lexicon permanently. Decide: flag likely non-words (not in
  an English word list, low LLM confidence) and keep them as untranslated
  names with a warning; make coinage an explicit, reported action ("coined
  N new words"); allow undo; consider not persisting nonsense. Also
  decide error behaviour when the LLM returns a bad plan (today:
  word-for-word fallback with no message).
- **Sentence-final punctuation done (pass 52); quotation and comma
  punctuation still open (M-L).** Each rendered sentence now gets a
  period/question/exclamation mark derived from the plan's own mood (a
  per-language `punctuation_style` of `standard`/`none`), and decoding
  strips/recognizes it. Still open: quotation marks (direct speech isn't
  modeled at all) and comma placement (needs clause/list-boundary rules)
  -- both genuinely bigger, separate features. Also still open, each a
  deliberate scope boundary of this pass (see `docs/LIMITATIONS.md`): no
  `exclamatory` signal independent of mood; decode isn't re-split per
  sentence, so a multi-sentence decode still reports one whole-input
  question/imperative signal, not per-sentence.

## 4. Generation from the user's own words

- **Seed words drive the language (done, passes 47-51) -- part of
  speech, bulk input, phonotactic-mismatch warnings, syllable/
  orthography bias inference, and suppletive forms including pronoun
  case and verb tense.** See `architecture/OVERVIEW.md` for the full
  history.

  Still open, each its own well-bounded follow-up: `attested_onset_
  clusters`/`attested_coda_clusters` (literal cluster *identity*, not just
  size -- deferred from pass 48) (S); `vowel_harmony` inference (needs
  more data than a handful of seed words reliably gives) (S); digraph/
  multi-letter grapheme inference (deferred from pass 49 -- a genuinely
  harder alignment problem) (M); `syllable_boundary_marker`/`orthography_
  category`-style *coarse* convention inference, distinct from per-phoneme
  spelling rules (deferred from pass 49) (S); wiring orthography bias into
  `evolve_romanization`, not just fresh generation (deferred from pass 49
  -- evolution already doesn't use `weighted_profiles` for whole-scheme
  category, only narrower per-symbol fresh-rule generation during a
  reform event, a smaller, separate extension) (S).

## 5. Own script and font

- **Phase 1 (a simple alphabet) done -- see architecture/OVERVIEW.md.**
  One procedurally generated glyph per phoneme, 15 graded style dials
  (sharp/smooth, bold/thin, symmetric/asymmetric, ...) and a writing
  direction, rolled once per language and compiled into a real,
  installable `.ttf` via `fonttools` -- `conlang script`, `generate
  --own-script`, and a web UI toggle/download. Verified empirically
  against the real library before committing to the approach (built a
  toy font, round-tripped it, rendered it in a real browser via
  `@font-face`) rather than assumed from documentation.
- **Force individual `ScriptTraits` dials explicitly, from the CLI/web UI -- done.** `core/script.py`'s
  `ScriptTraitsForce` (15 `float | None` fields, same shape as `OrthographyForce`); `GenerationSpec.
  forced_script_traits`; `generate_script`/`roll_script_traits` apply each non-`None` override after
  rolling; CLI `--script-trait name=value` (repeatable, reuses `_parse_trait_overrides` against a
  second allowlist); web UI "+ script trait override" rows in the Script fieldset, mirroring the
  existing trait-override rows exactly.
- **Phase 2: harder writing-system types (L each).** Not implemented,
  but not precluded by Phase 1's own shape -- see `core/script.py`'s own
  module docstring for exactly how each would extend it:
  - **Abugida-style vowel modifiers (Hindi-like).** Every `Glyph`
    already carries named `anchors` (grid points), unused today -- a
    vowel modifier would be a second, smaller glyph attached to a base
    consonant's own anchor, no `Glyph` redesign needed.
  - **Syllable blocks (Hangul-like).** Several phoneme-glyphs composed
    into one bounding box via the same anchors (onset/nucleus/coda
    position rules) -- a composition function on top of the existing
    per-phoneme glyphs, not a new glyph representation.
  - **Logographic systems (Chinese-like).** Genuinely harder, not just
    unimplemented: one glyph per *gloss*, not per phoneme, needing
    semantic/phonetic component composition -- a real, separate design
    problem, not attempted or claimed solved by anything above. The same
    stroke-primitive technique is the likely right tool, but the
    gloss-to-glyph mapping and component system are undesigned.
- **Styling the script from the free-text prompt (M-L).** Today the 15
  style dials and the direction are rolled from the language's own seed
  only, independent of what the prompt says (a sharp-looking script
  isn't more likely just because the prompt describes a "harsh" culture)
  -- seen as a separate, bigger piece of work (extracting several new
  graded dimensions through `prompt_classifier.py`'s already-large,
  already-costly system prompt; see this file's own "Trait-classifier
  call is expensive" item above), not attempted in Phase 1. Only
  *whether* a script gets generated at all is prompt-inferred
  (`TraitProfile.requested_own_script`), not what it looks like.
- **True cursive joining (M-L).** `ScriptTraits.connectivity` is rolled
  and stored but not yet consumed by the font builder -- real contextual
  joining (a different glyph form depending on word position, Arabic-
  style) needs OpenType contextual substitution (GSUB), a genuinely
  bigger feature than placing isolated glyphs, not attempted here. The
  same "extracted, not yet consumed" honesty `core.traits.TraitProfile`
  already applies to several of its own fields.
- **Smooth (not polygon-approximated) arc outlines (S).** `script.
  font_builder`'s own arc strokes are a short chain of straight-line
  segments sampling a curve, not a true smooth Bezier outline --
  documented as a phase-1 simplification in that module's own docstring,
  good enough at the sizes this renders at but a real limitation if a
  script is ever rendered very large.

## 6. Sounds and phonology

- **Russian vowel reduction in real words (M).** The profile's
  `stress_driven_vowel_reduction` governs generated words; auditing all 494
  curated real words for correct unstressed о/а → `ə` has not been done.
- **IPA U+0261 not normalized on input (S).** IPA typed with `ɡ` (U+0261)
  by a user or an LLM is not converted to ASCII `g`.
- **Diacritic style's `ts`→`ʦ`/`tɕ`→`ʨ`/`dz`→`ʣ`/`dʑ`→`ʥ` ligature
  spelling looks like raw IPA leaking through, and isn't good behavior
  (S-M).** Flagged by a user report on a language generated from "French
  evolved forward 1000 years with influence from Chinese." These are
  real, historically-attested single-character IPA ligatures (U+02A6/
  02A3/02A8/02A5), not invented, and the table's comment currently
  defends them on that basis -- but on reflection that defense doesn't
  hold up the way it does for this table's other identity choices (`ø`,
  `pʰ`, `bʱ`, the retroflex dot-under series, ...): none of these four
  ligature characters is actually used in any real, living orthography
  or standard transliteration convention, so a reader has no way to
  distinguish "deliberate exotic styling" from "the IPA transcription
  just wasn't romanized." This is a real shortcoming to fix, not a
  settled stylistic choice to defend. Candidate fix, not yet designed or
  implemented: give these four symbols an ordinary Latin-extended letter
  or digraph instead, the way the monoletter/digraph tables already do
  for the same four symbols (monoletter: `"c"` for `ts`/`tɕ`; digraph: a
  two-letter spelling) -- reusing one of those existing choices rather
  than inventing a third would keep the three exotic-symbol styles from
  needlessly diverging on exactly these four sounds. **Confirmed
  recurring in a second, independent user report** (a different language,
  "FutureMongotalian"): the same `ʣ`/`ʦʦ` ligatures, plus two
  previously-untracked entries of the exact same class -- `lʲ` (the
  palatalization-modifier identity choice) and `ǯ` (the `dʒ`-ligature
  identity choice) -- both read the same way to a user unfamiliar with
  either convention. This confirms the complaint is really about the
  diacritic style's general tendency to produce unfamiliar, IPA-looking
  letters, not only these specific four -- worth keeping in mind when
  this item is eventually picked up: a fix scoped to only `ts`/`tɕ`/`dz`/
  `dʑ` would leave the same class of complaint about `lʲ`/`ǯ`/etc.
  unaddressed.
- **Profile widening: what is still open (S-M).** (a) glide+vowel sequences
  written as onset clusters (French `bw`, Italian `pj`) are clusters, not
  diphthongs; (b) geminate affricates beyond Italian `tsː`, and geminates
  in languages with `coda_profile: none` (Japanese *kitte*); (c) Basque
  loan clusters (`tɾ`, `fɾ`) are tagged as loans, not admitted; (d)
  Sanskrit's pausa restriction; (e) lexicon slips: Swedish `ɧ`, Portuguese
  *carregar* rhotic.
- **Stress/pitch accent in real words (M).** (a) Verify the 233 Serbo-Croatian
  words against a real dictionary; (b) most Danish/Swedish/Norwegian
  polysyllables use only the shape default -- real lexical exceptions are
  unknown; (c) fixed-pattern languages ignore their real exceptions
  (loanwords, verbs); (d) secondary stress is not marked anywhere; (e) vowel
  harmony is absent from real words; (f) Indonesian/Malay diphthong-vs-hiatus
  facts and Persian's 2 low-confidence hits are open.
- **Show each sound's own prevalence and positional tendencies in the web
  UI's sound inventory (M).** Direct user request from a deep-dive review:
  "Inspect's sound inventory should show prevalence of each sound --
  overall prevalence, and positional tendencies (syllable-initial/final,
  disallowed in coda, etc.)." The raw data already exists but isn't
  surfaced anywhere in `articulation.full_inventory`/the `/api/languages/
  {slug}` response: every `Consonant`/`Vowel` already carries its own
  `prevalence: float` (an illustrative draw-weight, not a measured corpus
  frequency -- the "overall prevalence" half of the request would need to
  be explicit about this distinction rather than implying a real-language-
  style frequency count), and `SyllableStructure`'s own `max_onset`/
  `max_coda`/`allowed_onset_clusters`/`allowed_coda_clusters`/
  `allowed_coda_consonants`/`excluded_coda_consonants` already fully
  determine which consonants can appear onset-only, coda-only, both, or
  neither -- just never computed into a per-phoneme "can appear
  initial/final/not in coda" summary anywhere. Needs: (a) a new backend
  function deriving that per-phoneme positional summary from a language's
  own `SyllableStructure` (not a new data model -- it's already fully
  determined by the existing fields, just needs computing once per
  language); (b) a `prevalence` + positional-summary field added to each
  `PhonemeGuideEntry`/`as_dict()` entry; (c) UI work in the sound
  inventory's own popover (`toggleSoundBadge`/`renderSoundGuideList`) to
  show both, phrased plainly (e.g. "common" / "rare", "can start or end a
  syllable" / "never ends a syllable") rather than raw numbers, consistent
  with how every other sound-guide description in this project is already
  plain-language rather than technical.
- **Freshly-coined words can violate their own language's syllable structure -- done ("Tweaking Phase
  2").** Root-cause, confirmed directly: generating "frenchlike" (a saved language, `max_coda=1`,
  `allowed_coda_clusters=()`) produced "begin" as `chefr` /ʃəfʁ/ -- a word-final two-consonant coda its
  own structure explicitly forbids. Traced to the *actual* source with a monkeypatch trace, not guessed:
  `word_class_gen.generate_word_classes`'s own matched-reference-profile branch adopts a curated
  `WordClass` straight from a profile's own YAML data (`french.yaml`'s real "-re" verb class, `suffix:
  ["ʁ"]` -- modeling real French's own genuinely bare /ʁ/ ending, "e" silent) -- unlike an *invented*
  class's own suffix (`word_builder.build_class_suffix`, always nucleus-first by construction), a
  curated suffix is real morpheme data taken verbatim and assumes whatever stem shape its own real
  source language's stems usually have; an arbitrary invented stem doesn't always oblige. Confirmed in
  `frenchlike` specifically: 28 of 400 words (7%), all the same "-re"-class shape. Fixed with a new
  `word_builder.safe_affix_junction` (see its own docstring), called from `word_class_gen.
  apply_word_class` on both the prefix+stem and stem+suffix boundaries: when concatenating directly
  would exceed what the run's own rolled `SyllableStructure` allows at that boundary, inserts this
  language's own epenthetic vowel there instead of silently producing an illegal cluster. Handles the
  symmetric prefix-side case too (Swahili's own real bare "m-"/"n-" noun-class prefixes, same risk).
  Verified directly: the regenerated "frenchlike" has zero illegal word-final codas (was 17 before the
  fix, scanning all 400 words); full test suite run (hot-path change, touches `word_class_gen.py`/
  `word_builder.py`) confirmed no regressions. See `tests/test_word_builder.py`'s own
  `test_safe_affix_junction_*` tests.
- **"Weird"-looking combinations under a French-inspired sound palette are legally formed, not a bug
  (verified, not fixed) -- a deeper realism gap instead.** Reported: `pleijmãb`/`scrö̃t`/`plë̃m` (from
  `frenchlike`) look wrong. Checked directly against the language's own real `SyllableStructure`:
  `scrö̃t`'s `skʁ-` onset is explicitly present in its own `allowed_onset_triples` (`('s','k','ʁ')`) --
  a real, intentional French-cluster allowance, not an oversight -- and the other two have no coda-
  cluster violation either (the ch. 6 bug just above is a different, narrower issue). The actual gap:
  nothing in this project models *co-occurrence* plausibility between independently-legal choices --
  real French doesn't productively combine a word-final nasalized vowel with a *following* audible
  coda consonant the way `pleijmãb`'s `-ãb`/`scrö̃t`'s `-ɔ̃t` do (a real French nasal vowel is normally
  the syllable's own final sound, with no consonant after it) -- but nothing here currently represents
  "these two independently-legal features shouldn't co-occur" as a constraint; every phonotactic
  rule in this project is a single-axis structural check (onset/coda cluster legality, allowed onset-
  nucleus pairs), not a cross-feature plausibility model. A real fix needs a new kind of constraint this
  project doesn't have at all yet, not a tweak to an existing one -- related to, but a level more
  specific than, the "Profile widening" item already above in this chapter.
- **Word length doesn't correlate with a word's own "basicness," only its part of speech -- done,
  alongside a new `word_length_preference` trait (direct user request: "I wonder if there can be more
  phonology traits in generation... lengths of words etc.").** Originally reported: "simple or more
  difficult words seem equally likely to be long or short" for a generated language, unlike real
  languages (Zipf's law of abbreviation: frequent/basic concepts trend shorter). Confirmed at the time:
  `lexicon_gen.choose_syllable_count`'s own `favor_short` parameter only ever varies the syllable-count
  table by **part of speech**, never by per-*gloss* basicness. Fixed using the exact lever already
  identified: a new `_CORE_MEANING_GLOSSES` frozenset (`lexicon_gen.py`, lowercased `CORE_MEANINGS`
  glosses) feeds a new `is_core_meaning: bool` parameter on `choose_syllable_count`, contributing a flat
  `_CORE_MEANING_LENGTH_DELTA` (-0.4) into the function's own existing exponential-tilt math (`weights
  scaled by exp(theta * count)`) -- composed additively with the source-language-average tilt already
  there, not replacing it. `build_pending_word` passes `gloss_key in _CORE_MEANING_GLOSSES`, confirmed
  wired (not just correct in isolation) via a monkeypatch spy test. New `word_length_preference`
  `GRADED_TRAIT_FIELD` contributes its own delta (`_WORD_LENGTH_PREFERENCE_MAX_DELTA`, 0.9) into the same
  combined tilt -- one `theta`, not three separate rolls, so a basic gloss in a culture that also
  prefers long words nets out to whichever pull is stronger. Verified: core-meaning glosses measurably
  skew shorter (mean syllable count ~1.36 vs. ~2.51 neutral, 3000-draw average); `word_length_preference`
  gradient is monotonic (-1.0 -> ~1.04, 0.0 -> ~2.5, +1.0 -> ~3.96); composes additively rather than one
  silently overriding the other. Scope note: `sound_change._coin_native_word`'s own `choose_syllable_
  count` call (evolution's native-word replacement) was deliberately *not* threaded with either new
  parameter -- an easy, separate follow-up, not required for the trait itself to work during fresh
  generation.
- **Six more phonology traits -- done, same brainstorm/request as the word-length item above.**
  `fricative_density`, `nasality`, `vowel_richness`, `consonant_richness`, `vowel_length_affinity` each
  add one `biased_probability(rate, trait)` wrap at an already-identified rate-computation site in
  `phonology_gen.py`'s `_select_consonants`/`_select_vowels` (composed *before* the existing reference-
  bias step, same general-then-specific layering `altitude`->ejectives/`isolation`->uvulars already
  use): `fricative_density` wraps the `_FRICATIVE_POOL` loop's own per-symbol rate (composing with
  `aesthetic_harshness`'s own which-ones bias on the same pool -- density is *how many*, harshness is
  *which ones*); `nasality`/`vowel_length_affinity` wrap `_select_vowels`'s extras loop filtered to
  `extra.nasalized`/`extra.long` respectively; `vowel_richness`/`consonant_richness` wrap the *entire*
  optional extras tier uniformly (vowel extras; nasal/fricative/approximant/exotic consonant loops --
  deliberately excluding the ejective/uvular/aspirated/pharyngealized/breathy/pre-aspirated *group*
  gates, each already owned by a specific trait, and the stop/affricate pairs, which are core, not
  "extra"). `vowel_reduction_affinity` is the scoped-down implementation of a 7th idea, "rhythm type"
  (stress-timed vs. syllable-timed): investigated directly and confirmed no data-model field or
  downstream consumer represents timing class anywhere in the pipeline today -- a literal rhythm-class
  categorical would be pure unconsumed metadata, the same risk `ritual_register`/`taboo_register`
  already carry. Instead, it biases `lexicon_gen.py`'s own `reduce_unstressed_vowels` boolean (`any(p.
  stress_driven_vowel_reduction for p in reference_profiles)`, previously unconditionally `False` for
  any language with no matched source language) for exactly that no-source-language case -- a real
  curated profile (true *or* false) always wins outright. A second, less obvious fix was needed for this
  one to actually do anything: `word_builder.build_word`'s own reduction *rate* (not just whether it can
  fire at all) is separately scaled by `stress_strictness`, which is always `0.0` without a source
  language -- confirmed safe to override just for this trait-driven case, since `stress_gen.assign_
  stress`'s own use of that same parameter is unconditionally gated on a truthy `stress_pattern` (also
  always empty without a source language), so bumping it changes nothing about stress *position*, only
  the reduction rate. Also required a fix not originally scoped: `ReferenceLanguageProfile` (`generation/
  reference_languages/__init__.py`) needed all 7 new `typical_<field>` fields added too -- without them,
  `blend_toward_reference` crashed with `AttributeError` the moment *any* request named a source
  language, for every profile at once (found by running the broader test suite, not anticipated in the
  plan). None of the 7 are curated on any profile yet -- left uncurated, a separate future batch, same
  "abstain rather than guess" standard as the other curation rounds.

  All 7 added to `GRADED_TRAIT_FIELDS` (15 -> 22) and `PHONOLOGY_ONLY_TRAIT_FIELDS` (confirmed phonology-
  generation-only, never read by `grammar_gen.py` or any other grammar-adjacent module) -- immediately
  usable in Tweak with zero extra UI code, same precedent as the `tonal_friendliness`/`tone_sandhi`
  audit. Not added to `EVOLUTION_TRAIT_FIELDS`: the 5 inventory-shape traits are read only by
  `generate_phonology`, never called during evolution (`evolve_language` reconstructs its inventory via
  a structurally different mechanism, `_evolve_phonology_membership`).

  **Budgeted risk, materialized and resolved, not a surprise reacted to mid-pass**: adding 22 names to
  `GRADED_TRAIT_FIELDS` means the fake LLM now classifies all 7 new fields to a real, non-zero, hash-
  derived value for any test going through `classify_prompt`+fake LLM, and the word-length basicness fix
  above is *unconditionally* active for every `CORE_MEANINGS` gloss regardless of any trait value --
  both shift the shared lexicon/phonology rng stream's own draw sequence for nearly every generated
  language. A full-suite run surfaced exactly 7 fixture failures (not hundreds -- most of the suite
  checks structural properties, not byte-exact lexicon content, so stayed robust) across `test_webui.py`
  (2), `test_sound_change.py` (1), `test_translator.py` (1), and `test_subordination.py` (2, fixed
  properly rather than re-pinned -- `_clause_verb`'s own naive romanization-prefix string match was
  fragile to begin with, now rewritten to decode each candidate token via `_decode_verb_full` and match
  by gloss instead); all re-verified with a new seed/value where the fixture itself needed one. Verified:
  full suite green (2329 passed) after triage.

  Verified live through the real dev server, not just by test: a strongly-positive `fricative_density`/
  `nasality`/`consonant_richness`/`vowel_richness` override measurably shifts the resulting phoneme
  inventory's own fricative/nasal-vowel/long-vowel/consonant/vowel counts across several seeds (e.g.
  `consonant_richness=1.0` averaged 89 consonants vs. 21.6 neutral vs. 12.1 at `-1.0`, across 20 seeds).
- **Graded complexity-to-length gradient within non-core vocabulary (M) -- surfaced while scoping
  the word-formation plan, deliberately set aside from it.** The word-length basicness fix above
  (`is_core_meaning`) and the word-formation plan (see ch. 10's new entry) both explain length
  through two *binary* mechanisms -- "is this one of the 51 `CORE_MEANINGS`" and "is this word built
  from parts" -- but real word length also tracks rarity/specificity on a *continuum* even for
  monomorphemic words with neither property: "giraffe"/"umbrella"/"octopus" are longer than "dog"/
  "cat" despite being loanwords, not compounds, and not core vocabulary either (the modern,
  information-theoretic restatement of Zipf's law -- Piantadosi, Tily & Gibson 2011 -- length tracks
  predictability/surprisal, frequency is just a strong proxy for that). Nothing in `choose_syllable_
  count` currently distinguishes "giraffe"-tier rareness from "photosynthesis"-tier rareness within
  the non-core bucket -- it's one flat table. Needs a per-gloss rarity/specificity signal this
  project doesn't have (plausibly an LLM-classified or curated rank over `ALL_MEANINGS`/translation-
  time vocabulary), composed as one more additive delta into the same tilt
  `word_length_preference`/`is_core_meaning` already use -- not a new mechanism, just a third input
  to it, deliberately not attempted alongside the word-formation plan since the two explain length
  through genuinely different channels (composition vs. raw rarity) and conflating them risks double-
  counting the same words.
- **Serial verb constructions as their own typological axis (M) -- surfaced the same way, also set
  aside.** Verb-verb *compounding* (one lexical word, see ch. 10's new entry) is related to but
  distinct from serial verb constructions (Mandarin's resultative 打破 "hit-break" = to break;
  Japanese's 飛び出す "fly-out" = to jump out; robust across Niger-Congo and Austronesian) -- SVCs are
  a *syntactic* phenomenon (multiple verbs in one clause with no intervening conjunction/marking),
  not a single compound word, and this project has no existing clause-structure axis for it (`core.
  grammar.GrammarProfile`'s own fields are all either word-level or about a single clause's
  arguments). Worth keeping conceptually separate from the word-formation plan's own per-POS
  compound-likelihood multiplier (which only ever produces single lexical compound verbs, not
  multi-verb clauses) -- a real, scoped future addition to the grammar/syntax side, not the lexicon
  side, not attempted here.

## 7. Real lexicons

- **Finish the partly curated lexicons (L).** Curated to ~494 words for most
  languages. Partly curated, needing a native/linguist pass: Yoruba (102),
  Zulu (84), Xhosa (52), Sumerian (38), Navajo (24), Nama (4), Hawaiian
  (401), Georgian (169), Khmer (52), Thai (190), Quechua (412), Tibetan
  (365), Mongolian (322), Nahuatl (246), Pama-Nyungan (61), Arawakan (49).
  The LLM fills gaps until then.
- **Linguist verification (L).** No spot-check workflow (export a list, mark
  corrections, re-import) exists.
- **Vocabulary ceiling (M).** `ALL_MEANINGS` is ~496 meanings. Larger lists
  (Swadesh-207, Leipzig-Jakarta, a 1000-word core) and the unused
  `salient_vocabulary_domains` trait could drive domain vocabulary.
- **Deviation is now systematic, not random (done, pass 46) -- still a
  flat, unconditioned table (S-M).** A real word's sounds below word
  strictness 1.0 shift through a fixed, per-language `symbol -> symbol`
  table (`phoneme_fit.build_deviation_shift`), the same source phoneme
  always becoming the same target, like a real daughter language's own
  sound laws. Still not context-sensitive, and feature-distance-nearest-
  neighbor rather than lineage-aware -- see `docs/LIMITATIONS.md`.
- **Blending several sources (M).** Each word comes from one source
  language by weight; no cognate blending.
- **Proper-name lexicon (S).** Names are kept/adapted, but there is no
  gazetteer of common real names per language.
- **Tag more loanwords (S).** Only 32 entries carry the `loan` tag;
  heavy-loan languages (Swahili, Malay/Indonesian, Persian, Turkish, Hindi,
  Japanese) have many more untagged Arabic/Sanskrit/Chinese/English loans.

## 8. Tones

- **Sandhi chain grouping (M).** Three-tone chains are paired simply; real
  prosodic phrasing is not modeled.
- **Tone in real-based words (S).** A deviated word re-spells through the
  language's own orthography; tone-marking style interplay with pinyin-style
  spelling is only lightly tested.

## 9. Pronunciation (TTS)

- **eSpeak's tonal voice is Mandarin-only, and no better mechanism exists
  in eSpeak-ng 1.52.0 (investigated, closed as far as eSpeak itself
  goes).** Tones work by switching to the `cmn` voice, so other sounds
  are approximated by Mandarin's own inventory. Verified directly against
  the installed engine that there's no better option: SSML `<prosody
  contour="...">` is silently ignored (byte-identical audio with or
  without it); a flat `<prosody pitch="...">` shift does work but can
  only convey a crude high/low register, never a real Chao contour; and
  this project's own Kirshenbaum `[[...]]` bracket syntax breaks entirely
  under SSML mode anyway (even the closing `</speak>` tag gets spoken
  aloud). A genuine fix would need a different mechanism entirely --
  MBROLA's own per-phoneme pitch-envelope data via eSpeak's `--pho`
  output, or a different engine -- a materially bigger, separate
  investigation (L), not attempted here.
- **Multi-engine per-word selection (done, pieces 1-4) -- picks the
  best-fitting engine per word via a real per-phoneme coverage model
  (`speech.phoneme_coverage`), reachable as `--tts auto`.** See
  `architecture/OVERVIEW.md` for the full history (the coverage model
  itself, CLI/web UI surfacing, and adding Piper as a third engine).
  - **Add a paid cloud engine, e.g. Azure or Google SSML, with its own
    cost on/off toggle (L, independent).** Lowest priority -- needs the
    same per-task on/off-switch treatment this project already gives
    `llm=fake|anthropic`, off by default, before it's safe to even offer
    in the roster.
- **eSpeak's `en-us` voice approximates sounds outside English's own
  inventory more roughly than the Kirshenbaum-mapping fidelity rating
  implies (M).** Reported: `/ç/` (mapped to Kirshenbaum `"C"`, a direct
  unmodified `_BASE_BY_IPA` entry, rated `"exact"` fidelity) sounds like
  "f" rather than a recognizable "ch" as in "loch". Verified directly:
  synthesizing `[[C]]` and `[[f]]` through espeak-ng 1.52.0's `en-us`
  voice produces genuinely different audio (not a literal mapping
  collision), so the Kirshenbaum *letter* is correctly distinct -- but
  `speech.phoneme_coverage`'s fidelity rating only measures whether the
  IPA-to-Kirshenbaum translation step is a clean 1:1 mapping, not
  whether the chosen *voice* can actually realize that sound well;
  `en-us` has no native `/ç/`, so it falls back to whatever its own
  synthesis model approximates `"C"` as, and that approximation isn't
  rated anywhere. A real fix needs voice-specific fidelity data (which
  Kirshenbaum letters `en-us` actually renders recognizably, vs. only a
  native-phone voice like `de`/`is` would) across more than just this
  one symbol -- likely affects every sound English itself lacks (clicks,
  ejectives, pharyngeals, uvulars already flagged as "approximated" by
  the engine's own capabilities notes, but the `"exact"` tier may be
  over-promising more broadly than previously known). Not yet
  investigated beyond this one reported case.
- **Untested by ear (S).** eSpeak tone numbers for mid/low/neutral
  (33/21/11) were only length-checked.
- **Play a tone's own pitch contour from Inspect's Tones section (M).**
  Direct user request from a deep-dive review: clicking a tone badge
  (e.g. in a tonal language's own Tones section) should also offer an
  audio clip of a reference vowel (the request's own example: `/a/`)
  spoken with that tone's pitch contour, not just the textual contour
  description `toggleToneBadge`/`renderToneBadgeInfo` already show. The
  mechanism to synthesize a tone-marked vowel already exists end to end
  (`/api/pronounce`'s own `ipa` parameter already accepts a tone-marked
  syllable, and every TTS engine already handles tone marks via
  `apply_sandhi`/the engine's own tone mechanism -- eSpeak's numeric tone
  letters, SAPI's pitch contour, Piper's tone marks dropped outright per
  its own documented limitation) -- what's missing is purely a UI wiring
  job: a play button on the tone badge's own popover, synthesizing (the
  language's own default vowel, perhaps its most prevalent one once the
  prevalence item above lands) + that tone's own mark, reusing
  `playWordPronunciation`/`wirePronounceButton`'s existing pattern rather
  than inventing a new audio-playback mechanism.

## 10. Grammar

Each feature has three parts, and all three must land together: (1) the
grammar generator invents the option (`grammar_gen.py`/`inflection_gen.py`),
(2) the planner and renderer use it (`sentence_planner.py`/`translator.py`),
(3) the English decoder reads it back (`translate_to_english`). Sizes:
S/M/L as above.

**Done (passes 1-35):** the full grammar feature list -- plural/dual/trial
number, questions, classifiers, voice (passive/antipassive/causative/
middle/applicative/impersonal), tense/aspect/mood/evidentiality,
subordination (relative/complement/adverbial clauses), noun classes and
agreement, comparison, real inflection paradigms, derivation/compounding/
reduplication/root-and-pattern morphology, and discourse (topic/focus,
honorifics, reported speech). See `architecture/OVERVIEW.md` for the full
pass-by-pass history.

**Subordination follow-ups (done, pass 28); still missing (S-M):** an "oblique_pp" relative
clause has no resumptive-pronoun fallback (real-world "beyond reach" reach limiting only
covers the case-declined `oblique`/`possessor` functions); stacking is limited to exactly two
relative clauses and, in the fake planner, to a `who`/`which` marker (not `that`, to avoid
clashing with the complementizer); a raising verb is mechanically identical to a control verb
(no distinct treatment of weather/dummy subjects); a passivized-control matrix subject is
restricted to a pronoun (a name needs the ordinary noun-phrase handling, not attempted here);
backshift is a rendering-only default the planner's own tense still overrides (matching how
`conditional_clause_tense` already worked) -- a real LLM planner therefore needs telling to
*omit* the embedded tense for it to show, and the fake planner (which always infers an explicit
tense from the English) never demonstrates it through free text, only through direct plan
construction; a coordination chain beyond three conjuncts, and gapping/right-node raising beyond
two conjuncts, need their own fake-planner shape (the renderer itself has no depth limit); gapping
and right-node raising are detected in the fake planner only from the written convention with a
comma before the residual subject/object. The subordinator itself is still coined as an ordinary
particle word.

**Agreement follow-ups (done, pass 15 + pass 29); still missing (S):** the
planner still supplies each noun's own case/number -- a design choice, not a
gap: the planner already knows a slot's syntactic role (subject/object/
oblique), so there is nothing an agreement pass would add by re-deriving it.
Semantic-field class assignment now covers the great majority of noun glosses
(`noun_class_gen._SEMANTIC_FIELDS`) but is still a curated list, not a real
semantic ontology, so a gloss outside it falls back to the arbitrary `hash`
assignment.

**Aspect/mood follow-ups (done, pass 16 + pass 30); still missing (S-M):** a suffix concatenation
(tense+agreement, say) can still spell the same word as some other single suffix -- pass 30 added a
second, bounded collision-resolution pass that measurably reduces this (59 residual collisions
across 60 test seeds down to 26) but does not guarantee eliminating it, since only pairs from
different fields are checked and a very small phoneme inventory can run out of free shapes
(decoding then picks the plainest reading, which the fluent-English step may correct); evidential
marking is optional and taken from the planner (no obligatory evidential system, no evidential-tense
interaction -- deliberately not attempted in pass 30); a verb's past tense can now fuse into an
irregular lexeme over time, but only from the same small, fixed candidate list
(`voice_np_gen.IRREGULAR_PASTS`, ~13 verbs) ordinary generation already draws `suppletive_past`
from -- a genuinely arbitrary verb can't fuse, since the decode/prompt-generation side
(`voice_np_gen.suppletive_split`) gates on that same fixed list; grammaticalizing a periphrastic
auxiliary into a suffix only fires once that auxiliary has actually been coined by an earlier
translation (coined lazily, on first use) -- a language that has never needed it keeps it
periphrastic regardless of time depth.

**Voice follow-ups (done, pass 17 + pass 31); still missing (S-M):** the beneficiary an applicative
promotes still keeps whatever *case* the plan happens to give it (accusative/absolutive already falls
out of the ordinary transitive-object rules the fake planner already applies, so this rarely shows in
practice, but the renderer itself does nothing applicative-aware for case, only for object agreement
now); a middle/applicative/impersonal voice is still a single suffix (no further valency-changing
morphology beyond what pass 31 added); reciprocals stay a suffix or a word (no other strategy);
the fake planner's free-text detection is still short fixed shapes, now a bit wider ("The man eats.",
"The door boiled.", "I cook for him.", "Someone dances." -- English impersonal "one" itself can't be
used as a trigger, since the tokenizer's numeral-grouping pass always swallows "one X" into a
numeral-quantified noun phrase before voice detection ever runs, whether X is a noun or a verb).
Decoding an unknown token was sped up (pass 20: about 3x on
average, worst case from ~4.6 s to under 1 s in a 40-language sample) but is still a
generate-and-compare search: a feature-heavy language spends ~0.5 s on a token that is not one of
its words. A real fix would index inflected forms per language, or match suffixes right to left (M).

**Existence/possession follow-ups (S-M):** more strategies (locative
possession "at me is", topic-comment possession, a possessive verb that
agrees with the possessed noun, "have" as a light verb); a dedicated
existential particle; negative existentials with their own verb ("there
isn't"); habitual/experiential possession ("I have to"); the English
direction relies on the fluency prompt note rather than recognizing the
construction itself.

**Comparison follow-ups (done, pass 21 + pass 32); still missing (S):** no "not as big as" beyond a
plain negation, no "so big that ..." result clauses (a genuinely new subordinate-clause construction
-- the "that" linker would collide with the existing complementizer and correlative-relative uses of
that same surface word in the fake planner), no comparison of quantities beyond the word "more"
("three times as big" is left to the planner); an adverb only takes a degree suffix in the languages
that roll `adverb_degree`; "the more..., the more..." is the pass-14 correlative with a fake-planner
shape for exactly that sentence; the fake planner's adjective list is about 125 words.

**Noun phrase (passes 17-19 done; the list is cleared apart from these smaller gaps):**
suppletion covers only the irregular past of about a dozen verbs (no suppletive present/participle
forms) and possessive words differ only by *person* (no independent "mine", no declining
possessive words); the classifier constructions are adjectives, standalone numerals and quantifiers
(a mass noun after a numeral still takes its ordinary category classifier, and a measure noun's
"of" is simply dropped); the adposition table is a fixed English list of about 25 words, a case
that replaces its adposition is read back as one English preposition (in/with/from/to) with the
finer choice left to the fluent-English step, and a case-less language only gains spatial cases when
its adposition strategy uses them; the adjective classes are word lists; a deictic article is made
only for `this`/`that` (no article per person or distance beyond two) and exists only beside a noun.

**Verb phrase (auxiliaries/periphrastic tenses and evidentiality done, pass
16 + pass 29/30; deontic modality done, pass 44; negative verbs done, pass
45; serial verbs (resultative subtype pass 46, directional subtype pass
47) done; this bullet otherwise predates those passes and was stale --
narrowed to what's actually still missing):** valency-changing
morphology beyond pass 31 (L); a
state-vs-identity copula distinction (zero copula itself already exists,
`has_overt_copula`) (S); adverb placement
(S). Deontic modality itself (pass 44) covers obligation only, via a new
independent `"obligative"` mood label (glossed "must", reusing the entire
existing mood/periphrastic/decode pipeline) -- still missing within that:
a separate `permissive` label for permission (English already loosely
covers it via `potential`'s "can"/"may" gloss, so splitting it out cleanly
needs its own disambiguation work) and a weaker "advisable" shade distinct
from strong obligation ("should" vs "must" as two strengths sharing one
label today). Negative verbs itself (pass 45, a new `"negative_verb"`
negation strategy: a dedicated word carries subject agreement while the
main verb takes an invariant `connegative` stem) is scoped to finite verbs
only and a single tense-invariant connegative stem -- still missing within
that: a non-finite (infinitive/nominalized) clause's own negation under
this strategy (falls back to an ordinary particle, same as `"particle"`
strategy); a tense-sensitive connegative (real Finnish varies it by tense);
grammaticalization of the negative-verb word into a bound suffix over
evolution (`sound_change._grammaticalize_and_fuse` is the natural, already-
precedented place to extend this, not attempted here).

**Serial verbs -- done, both the resultative subtype (pass 46, Mandarin's own 打破 "hit-break" = to
break) and the directional subtype (pass 47, Japanese's own 飛び出す "fly-out" = to jump out).** See
`architecture/OVERVIEW.md` for the full mechanism of both -- the second pass needed no new render/
decode/safety machinery at all, only a second closed verb pool (`voice_np_gen.DIRECTIONAL_VERB_
POOL`, go/come/arrive/leave/return/climb/turn, disjoint from the resultative pool) and a second
fake-planner trigger shape, since `PlannedSlot.serial_result` was already fully subtype-agnostic.
Still deliberately not attempted, each a realistic later follow-up: a third SVC subtype (manner,
purposive/sequential "go buy"); distinguishing "toward speaker" (come-like) vs. "away from speaker"
(go-like) deixis within the directional pool itself (real languages often grammaticalize this
finely; all 7 pool members are treated as equivalent path markers here); chains of more than two
verbs (real languages do allow longer chains, but two is the clearest, most citable case, matching
this project's own "cap depth at two" precedent elsewhere, e.g. subordination's own relative-clause
stacking); richer argument-sharing patterns beyond the simple transitive-V1 + intransitive-result-V2
reading ("I hit it [and it] broke") -- same-subject-different-object chains exist in real SVC
languages, not modeled here; independently toggling "has resultative but not directional" or vice
versa -- both subtypes are gated by the single `has_serial_verbs` flag, not separately rollable;
negation/imperative interaction with a serial verb is narrowly made safe (the result/direction verb
is excluded from both `_finite_verb_indices`/`_negatable_verb_indices`, so neither ever targets it)
but not given its own real treatment (negating a serial sentence always lands on the finite verb
only, matching the real cross-linguistic default, not separately verified beyond that).
"Valency-changing morphology beyond pass 31" is a separate, already-distinct (L) item just above
this one, not touched by either pass.

**Morphology (the morphology list is done, passes 22-27):** what is left is depth, not breadth (S-M each).
Reduplication marks a cell *alongside* its ordinary affix (there is no pure reduplication that replaces the
affix), copies from a fixed menu (full, initial CV, initial syllable, final syllable), and marks six cells (plural, three
aspects, elative, superlative); it does not reduplicate the root of a templatic word or mark derivations. Root-and-pattern
inflection covers the verb tenses and aspects, the plural and the comparative, one vowel melody per cell; a stem is
rebuilt from the word's stored root, so a word whose consonants have since changed under sound change (its root no
longer matches) keeps its citation stem, tonal templatic words lose their tone marks in a patterned stem, a
class suffix a templatic word was built with is not carried into the patterned stem, and only three derivations (agent, abstract, adjectival) use
templates -- the citation templates themselves are still the five of `root_pattern.generate_templates`, and roots are
triliteral only. Templatic languages are rare (about 4% of generations, more with a Semitic source language). Also still open: five
derivational rules only, no verbalizers or instruments; compounds are noun + noun from a solid or hyphenated
English word; class assignment is by gender or a hash of the gloss; an infix goes after the first consonant or
before the last vowel only. Decoding an unknown token in a language with infixed verbs can still take a few seconds. The plural,
imperative and question-particle forms do not yet evolve with `sound_change` (S).

**Discourse (topic/focus done, pass 33; referent honorifics done, pass 34; reported speech done,
pass 35; optional, L otherwise):** a topicalized sentence ("as for the cat, it sleeps") fronts the
topic noun phrase, marks it with a dedicated particle in the languages that rolled one, and drops the
main clause's own resumptive subject pronoun -- subject-coreferent topics only, a bare topic noun
phrase only (no adjectives/numerals/possessors on it), no focus/cleft constructions ("it is X
that..."), no cross-sentence topic continuity (pass 33). A subject-referent honorific ("the professor
sleeps") marks deference toward whoever a sentence's subject is, independent of the already-existing
addressee-only `honorific_you`/verb-politeness, reusing the *same* verb affix rather than a second one
-- a closed title list only (professor, doctor, teacher, elder, king, queen, president, master), no
proper-name trigger, subject position only (pass 34). A quotative particle marks a complement clause
under a speech verb ("say", "tell", "claim", ...) as reported/quoted content, additional to (not
replacing) any complementizer-by-verb marking; `reported_speech_backshift` is now gated to speech
verbs specifically rather than any past-tense verb's complement (a bug fix -- "I knew that she was
late" was backshifting even though it isn't reported speech); indirect speech only, no direct
quotation (pass 35). See `architecture/OVERVIEW.md`. Still missing: pro-drop and ellipsis beyond
today's morphological (within-sentence, agreement-driven) kind -- no discourse-driven, cross-sentence
ellipsis; distinct honorific vocabulary (Japanese-style suppletive verb stems for a closed list of
common verbs) and object/addressee-humbling (kenjougo-style) marking; direct quotation and any
interaction between the quotative particle and the (separate) evidentiality system; idioms
(`Idiom`/`with_new_idiom` exist as types but nothing generates one).

**Wiring existing traits (`evidentiality_culture`/`spatial_reference`/`salient_vocabulary_domains` done;
`ritual_register`/`taboo_register`/`terrain_communication_distance` still M each):**
`evidentiality_culture` raises the chance of a richer `EVIDENTIAL_SYSTEMS` roll (less "no
evidentiality", the freed weight split proportionally across the three richer systems);
`spatial_reference` raises the roll rate specifically for the three truly spatial cases (locative,
ablative, allative) -- instrumental/comitative, about means/accompaniment rather than spatial
reference, stay at their flat rate; `salient_vocabulary_domains` folds into the same `salient_context`
free-text channel word-coining prompts already read (via `core.traits.coining_context`), rather than
getting its own separate plumbing. `ritual_register`, `taboo_register` remain genuinely unconsumed --
no register/formal-speech system, no euphemism/avoidance-vocabulary system exists anywhere yet to bias;
each needs a real new mechanism built first, not just a formula (`social_hierarchy` is consumed -- it
raises the probability a language rolls `honorific_you` at all, see `pronoun_gen.py`). **Correction,
found during a deep-dive review that asked "is terrain_communication_distance really the only trait
that affects evolution?" (it isn't -- see §11's new item on this):** `terrain_communication_distance`
and `orality_literacy` are NOT actually unconsumed the way this entry used to claim -- both are read by
`sound_change._compute_rates` (vowel-reduction resistance, and literacy anchoring pronunciation against
drift across all six segmental rules, respectively), just only at *evolution* time, never at fresh-
generation time -- this entry was stale, describing only the fresh-generation path where these two
traits genuinely have no effect. Word order is not trait-linked (S). Matched-language
grammar bias is partial: `real_word_order`, `real_alignment`, `real_has_articles`, ... exist for ~16
of ~50 profiles, and `morphological_type` has no matched-language bias -- it has no
`real_morphological_type` field on any profile at all, so this needs new per-profile data curated
across ~50 profiles, not a formula tweak (M, bigger than the three traits just wired).
- **Imitate a matched source language's own derivational/word-formation pattern as a graded trait
  (M-L).** Direct user request: a French-inspired language's verbs could plausibly all take a
  consistent shape (the user's own example: "jouler", "boller", "avrir", echoing real French's own
  heavily-dominant `-er` class) the way source-language sound/word sourcing already biases phonology
  and vocabulary. Today's word-class system (`word_class_gen.py`, `WordClass`/`Paradigm`) already
  assigns each lexeme to one of several inflection classes with its own prevalence weight -- the
  missing piece is biasing *that* weighting toward whichever class a matched real profile's own real
  grammar overwhelmingly favors (the same "weighted real-profile nudge, scaled by strictness" shape
  `morphological_type`/`uses_root_and_pattern` already use in `grammar_gen.py`), which needs each
  curated profile to record which of its own real inflection classes dominates and by how much -- new
  curated data, not just a formula change.
- **A trait for "appetite for exceptions," covering grammar, orthography, and/or script alike (M-L).**
  Direct user request, with real-language grounding already named by the user: French's verb system is
  overwhelmingly `-er` but keeps a real minority of `-ir`/`-re` verbs; Dutch's past participle is mostly
  `ge-...-t/d` but keeps irregulars like "gevlogen." This project already has *some* irregularity
  machinery (`_draw_irregulars` in `paradigm_gen.py`, `IRREGULAR_PASTS` in `voice_np_gen.py`) but no
  single graded dial controlling *how much* a language tolerates irregularity across the board, and
  critically -- per the user's own framing -- a real exception isn't random noise, it still follows
  "some sort of smaller rule" (a genuine minority sub-class, not an arbitrary one-off per word). Scoping
  this well means deciding whether "smaller rule" is modeled as literally more `Paradigm`-style minority
  classes (consistent with how paradigms already work) activated more often at a high trait value, which
  seems like the more natural fit than inventing a new per-word-exception mechanism; extending this same
  idea to orthography/script exceptions is a further, separate step once the grammar side exists.
- **Occasionally share a root between semantically related words -- done, "to die"/"death," the
  user's own example.** The "which glosses are related" signal this entry itself said was missing is
  now `generation/word_relations.WORD_RELATIONS` (a curated list) or the configured LLM
  (`GenerationSpec.word_formation`); relatedness is realized via a new non-concatenative (ablaut)
  `DerivationRule.stem_change`, reusing `paradigm_gen.build_stem_maps`/`change_stem` (inflection's own
  umlaut-plural machinery, found already built for an unrelated reason) rather than `LexicalEntry.
  root`/the templatic root-and-pattern path this entry originally pointed at -- `root_pattern.py`'s
  own mechanism turned out to need no changes at all, since it already reuses `root` through a
  different template whenever a `DerivationRule.pattern` applies. See `architecture/OVERVIEW.md`'s
  own "compounding/derivation/ablaut word formation" entry for the full mechanism.
- **A trait for compound-word likelihood -- done, Monday/understand (English) vs. Mandarin's own
  heavy compounding, the user's own examples.** `traits.compound_likelihood`, composed with a
  per-part-of-speech multiplier (noun > adjective > verb, cross-linguistically grounded) and a hard
  suppression for core/basic vocabulary -- the "graded dial controlling how often" this entry asked
  for, generalized to gate derivation/ablaut too, not just literal compounding. See `architecture/
  OVERVIEW.md`'s own "compounding/derivation/ablaut word formation" entry.
- **Dutch "ver-"-style recurring opaque formatives (S-M) -- direct user question ("can we enable
  very common patterns like ver- in Dutch: verhuizen, verlaten, vertragen, verplaatsen?").**
  Linguistically a different phenomenon from the derivation/compounding above: real "ver-" doesn't
  derive one word *from* an identifiable base with one clean meaning the way agent "-er" does --
  linguists describe it as having 8-plus loosely related senses (completive, directional,
  pejorative, privative...), closer to a recognizable recurring *texture* than a predictable rule.
  Confirmed by reading the code: this already exists almost as-is --
  `generation/word_class_gen.py`'s `WordClass` mechanism already assigns a chunk of words of a given
  POS an arbitrary, invented, baked-into-the-IPA prefix/suffix with its own prevalence weight, with
  no requirement for a semantic base at all. A Dutch-flavored language can already get a `ver-`-
  shaped verb class today; the gap is (a) the prevalence weight may need tuning so it reads as
  "common" the way real "ver-" does, and (b) it's invisible -- `word_class` is recorded on every
  `LexicalEntry` but never surfaced (same gap the "Show a word's own grammatical forms/paradigm in
  Inspect" entry right below already names). If a *semantically clustered* version is ever wanted
  (leaning toward change-of-state/motion senses the way real "ver-" loosely does, rather than purely
  arbitrary), that would need the relatedness machinery from the word-formation plan above -- but the
  base "recurring textural prefix" case needs no new architecture.
- **Show a word's own grammatical forms/paradigm in Inspect (M) -- direct user question, "are
  grammatical forms/cases already wired?" answered: yes internally, no visibly.** Confirmed by reading
  the code, not guessing: `generation/paradigm_gen.py`'s `roll_paradigms`/`Paradigm`/`InflectionAffix`
  machinery, and `inflection_gen.apply_affix`, already compute a specific word's own inflected form for
  any (case/tense/etc.) cell on demand -- this is exactly what the translator already calls internally
  for any sentence using a case-marked noun or tense-marked verb. Grepped `webui/app.py`/`static/
  index.html`/`cli/main.py` for "paradigm"/"declension"/"conjugation": zero matches -- none of this is
  exposed anywhere as a standalone, browsable table; the only way to ever see an inflected form today is
  indirectly, buried inside a translated sentence. A real addition needs: (a) a new function enumerating
  which cells are worth showing for a given POS (a verb's full tense x aspect x mood x voice x agreement
  cross-product can combinatorially explode -- a curated, representative subset like infinitive/present/
  past indicative, not literally every combination, is the realistic scope); (b) correctly resolving
  that lexeme's own `WordClass`-based `Paradigm` overrides/syncretisms/stem-change before calling
  `apply_affix`, not just the language's own base affixes; (c) a new endpoint and an Inspect UI section
  (e.g. a small table under each lexicon row, or a dedicated "declension/conjugation" popover). Not a
  quick fix -- the combinatorial-scope decision in (a) alone needs real judgment before implementation.

## 11. Language evolution

- **Rules are generic, not language-specific -- done (pass 40, stages
  1-3).** Each of the six sound-change rules' own *rate* (not the sound
  laws themselves) is now biased by: curated real-lineage tendencies for
  14 of 51 reference profiles (`historical_*_affinity` fields, e.g.
  Dutch/German/Russian/Turkish/Polish final devoicing); a structural
  self-derived bias from the language's own current phonology, applying
  to any evolving language including fictional ones; and three already-
  extracted traits (`orality_literacy`, `tonal_friendliness`/
  `terrain_communication_distance`, `aesthetic_harshness`) now feeding
  all six rules. See `architecture/OVERVIEW.md` for the full mechanism.
  Deferred: curating the remaining 36 profiles (Stage 1); extracting
  genuinely *new* free-text evolution-period concepts in the prompt
  classifier rather than reusing today's fixed trait set; `isolation`/
  `community_scale`/`social_hierarchy`/`spatial_reference`/
  `evidentiality_culture`/`ritual_register`/`taboo_register` for Stage 3
  (no individually crisp, sound-change-rate-specific motivation found).
- **Which traits actually feed evolution -- corrected/completed list, found
  answering a direct deep-dive question ("is terrain_communication_distance
  really the only trait that affects evolution?").** It isn't, and the
  question's own premise undersold how many already do, by only checking
  `sound_change._compute_rates` for one of them. The full, verified-by-
  reading-the-code picture: `contact_intensity` (lenition/cluster-
  simplification strength, the same direction it already nudges fresh-
  generation's own morphology-type roll); `orality_literacy` (a flat
  literacy-anchors-against-drift bias across all six segmental rules);
  `tonal_friendliness`/`terrain_communication_distance` (both resist vowel
  reduction, for two independent real reasons -- tone and loud/long-
  distance speech both need distinct vowel quality -- the same target
  rule); `altitude`/`aesthetic_harshness` (ejective-drift strength, mirroring
  fresh generation's own ejective-inclusion bias). `terrain_communication_
  distance` itself genuinely has *zero* fresh-generation effect of its own
  (unlike the other five, which are dual-purpose, affecting both fresh
  generation and evolution) -- it was excluded from `core.traits.
  PHONOLOGY_ONLY_TRAIT_FIELDS` specifically because it's a no-op in the
  Tweak feature's own fresh-regeneration path (see that constant's own
  docstring). There is therefore nothing to "split" about it the way the
  original question's own framing suggested (one trait doing double duty
  that should become two) -- it's already evolution-only; the actual gap is
  that today's Generate/Inspect UI shows it in the "Phonology" section
  alongside three traits that *do* have an immediate generation-time effect,
  which is genuinely misleading about when it does anything. The right fix
  is UI classification, not a new trait: once Evolution becomes its own
  tab/step (see the restructuring item just below), this trait -- and only
  this one -- should move there instead of staying under Phonology.
- **Separate Generation from Evolution more clearly across the whole app -- (a)+(b) done.** Direct
  user request, scoped down from the original six-part (a)-(f) sketch to the two parts confirmed as
  already-mostly-supported by existing mechanisms:
  - **(a) A separate Evolve tab**, `POST /api/languages/{slug}/evolve` (new `EvolveRequest`/
    `evolve_language_endpoint`, `webui/app.py`), mirroring `/api/languages/{slug}/tweak`'s own shape
    but with **no trait allowlist** -- confirmed by reading `_evolve_grammar_affixes`/`word_class_gen.
    apply_word_class` that `sound_change.evolve_language` never re-rolls grammar typology (word order,
    alignment, morphological_type, word classes) no matter which of the 15 `GRADED_TRAIT_FIELDS`
    change, unlike fresh generation's own shared-rng grammar roll -- so, unlike Tweak's own
    `PHONOLOGY_ONLY_TRAIT_FIELDS` restriction, every trait is safe here. Confirmed with a real test
    (`tests/test_evolve_webui.py::test_evolve_with_a_grammar_adjacent_trait_still_keeps_typology_
    identical`), not just by reading the code. `source_languages` merge *additively* with the base's
    own existing lineage (already `evolve_language`'s own behavior, just not previously reachable from
    the web UI); `years <= 0` is rejected outright (a dedicated evolve action with nothing to do isn't
    a meaningful request, unlike the combined path's own "0 = none" convenience default). The web UI's
    own Evolve tab (`index.html`, `panel-evolve`) copies the Tweak tab's proven preview/save shape
    directly -- `loadEvolveLanguage`/`runEvolve` mirror `loadTweakLanguage`/`runTweak`, and
    `renderTweakDiff`/`renderSoundInventoryDiff` are reused as-is (both already generic over any
    before/after lexicon + phoneme-inventory pair) -- plus a new `buildPrefilledTraitRows`/
    `collectPrefilledOverrides` pair generalizing what used to be Tweak-only logic, and a generalized
    `addSourceLangRow(containerId)`/`collectSourceLanguages(containerId)` shared with Generate's own
    source-language rows rather than duplicated.

    **Follow-up, direct user request after noticing the tab showed the same 15 trait rows/descriptions
    as Generate and asking whether they all really apply to both generation and evolution -- they
    don't.** New `core.traits.EVOLUTION_TRAIT_FIELDS`: of the 15 `GRADED_TRAIT_FIELDS`, only 6 are ever
    actually read anywhere in `sound_change.py`'s own evolution call path (confirmed by grep, tracing
    every helper `evolve_language` calls, not assumed) -- `altitude`/`aesthetic_harshness` (ejective
    drift), `contact_intensity` (cluster simplification, lexical replacement rate, orthography drift/
    reform, *and* tonal detonalization -- the real Swahili case), `orality_literacy` (literacy anchors
    pronunciation and spelling against drift), `tonal_friendliness`/`terrain_communication_distance`
    (both resist vowel reduction only -- a genuinely surprising finding: neither touches the tone
    *system* itself at all, despite `tonal_friendliness`'s own name; only `contact_intensity` can
    cause detonalization, and tonogenesis is a separate, purely structural coda-driven mechanism). The
    other 9 are real, still-consumed traits -- just never by anything evolution calls (7 are fresh-
    generation-only: `isolation`/`community_scale`/`social_hierarchy`/`evidentiality_culture`/
    `spatial_reference`/`phonotactic_restrictiveness`/`tone_sandhi`; 2, `ritual_register`/
    `taboo_register`, aren't consumed by *anything* yet, generation or evolution alike). The Evolve tab
    now shows only these 6 as trait-override rows (unlike `PHONOLOGY_ONLY_TRAIT_FIELDS`, this is
    display-only -- the endpoint's own `trait_overrides` validation still accepts any of the 15, since
    setting one of the other 9 during evolution is a harmless no-op, not a correctness risk), grouped
    by each trait's own *evolution*-time mechanism rather than Generate's own `TRAIT_SECTION` grouping
    (`tonal_friendliness`/`terrain_communication_distance` move into "Phonology" here, since neither has
    any tone-system effect during evolution; `contact_intensity` stays "Grammar", matching where
    Generate/Tweak already show it, even though its own evolution effects are broader) -- a group with
    nothing in it (today, only "Tones") is hidden outright. New `webui.glossary.EVOLUTION_TRAIT_GLOSSARY`
    gives each of the 6 its own info-popover description written purely in terms of the evolution
    effect, instead of reusing `TRAIT_GLOSSARY`'s generation-focused text.
  - **(b) Generate stays focused on a base language.** The "Years of evolution" input was removed from
    Generate's own Advanced Options (web UI only); `evolve_years`/`generate_evolved_language`/CLI's own
    `--years` are unchanged at the backend/CLI level -- a prompt that itself implies a time depth
    (e.g. "...evolved over 500 years") still triggers evolution during fresh generation exactly as
    before, only the manual override input is gone. `--evolve-from` was already the CLI's own dedicated
    entry point and needed no change; confirmed unaffected with a live smoke run of docs/CLI.md's own
    first `--evolve-from` example.
  - **(c)-(f)** (a "Design" tab for multi-source derived languages; richer structured `history`
    beyond Inspect's new flat list below; a CLI discussion, resolved as "no change needed"; the
    invented script evolving too) remain deferred, same reasoning as originally written: (c) implies a
    genuinely new blending-between-several-already-evolved-languages mechanism that doesn't exist in
    any form today; (f) depends on ch. 12 item 11 (tweaking a script) landing first.
  - **Inspect** now renders `Language.history` as a small ordered list under Generation Details
    (`_language_summary` gained a `"history"` key, `webui/app.py`; pure frontend surfacing in
    `renderLanguageSummary`, no new backend mechanism) -- previously recorded on every language but
    never shown anywhere in the web UI.
  - Verified live through the real dev server: evolving a saved language from the new tab with an
    added source language (Dutch) and a 300-year run previews a word/sound-inventory diff, saves as a
    new language, and Inspect shows both history steps (`"generated core language"`, `"evolved 300
    years (seed=0)"`); `--evolve-from`'s own CLI output is unaffected (smoke-tested above).
- **Grade every curated real language on all 15 worldbuilding traits, including the evolution-only
  ones, as an extra blending weight -- done, for a defensible curated subset (not all ~53 profiles).**
  New optional `typical_<field>` fields on `ReferenceLanguageProfile` (one per `GRADED_TRAIT_FIELDS`
  name, deliberately prefixed `typical_` rather than `real_`, since these are this project's own
  cultural/typological characterization rather than hard phonological facts the way `real_word_order`
  is), `None` meaning "not curated" -- the same "abstain rather than guess" convention every other
  optional profile field already follows. New `blend_toward_reference(traits, weighted_profiles,
  blend_weight) -> TraitProfile` (`generation/reference_languages/__init__.py`): per trait, averages
  only the matched profiles that actually curated that specific field (weighted, re-normalized across
  just that subset -- the same pattern `lexicon_gen._resolve_average_syllables` already uses for
  `core_vocabulary_average_syllables` -- an uncurated field is left completely untouched, never treated
  as a silent "0.0 vote"), then linearly interpolates the trait's current value toward that average by
  `blend_weight` (0 = true no-op, 1 = snaps to the reference average). Wired into both `/api/generate`
  and the new Evolve endpoint above, right after `source_languages`/strictness are merged in but
  *before* `trait_overrides` -- so an explicit override still wins outright, the same precedence every
  other explicit-vs-inferred channel in this project already has. **Deliberately reuses
  `source_language_strictness` as the blend weight** rather than adding a new Advanced Options dial, a
  documented v1 simplification. Curated 11 of ~53 profiles (17 trait values total), each with a real
  linguistic/historical citation in its own YAML comment, not a guessed number: `social_hierarchy` for
  Japanese (0.9)/Korean (0.9)/Thai (0.8) (well-documented honorific-register systems); `isolation`/
  `community_scale`/`contact_intensity` for Icelandic (0.9/0.6/-0.8), Hawaiian (0.95 isolation,
  -0.7 orality_literacy), Nahuatl (0.5 community_scale), Navajo (0.6/0.6); `evidentiality_culture` for
  Quechua (0.9)/Tibetan (0.85) (extensively documented grammaticalized evidential systems);
  `contact_intensity` for Swahili (0.85)/English (0.8, with -0.7 community_scale). `ritual_register`/
  `taboo_register`/`spatial_reference` (no confident real-world correlate found) and
  `tonal_friendliness` (would just duplicate the existing `tonal: bool` field) are left uncurated
  project-wide for v1, matching every other profile field's own "curate what's genuinely documented,
  abstain otherwise" standard rather than force-filling all 15 x 53 cells. Verified end to end, not
  just unit-tested: a Japanese-sourced generation at strictness 1.0 with no explicit trait override
  nudges `social_hierarchy` to 0.9 (confirmed live through the real dev server, and in
  `tests/test_reference_trait_blend.py`'s own end-to-end test), while an explicit `trait_overrides`
  still wins outright. Remaining curation (the other ~42 profiles, the three uncurated-for-now traits)
  is still a real, substantial future direction if picked back up later, just no longer unscoped.

  **Batch 2 -- 18 more profiles curated (24 new trait values), direct user request to keep working
  through the remaining ~42.** Same "abstain rather than guess" standard as batch 1, each with a real
  citation: `isolation` for Basque (0.9, Europe's own textbook surviving language isolate), Nama (0.35)
  and Pama-Nyungan (0.3) (traditional small-scale Khoisan/Western-Desert societies, more moderate than
  Basque's case); `community_scale` for Nama (0.5) and Pama-Nyungan (0.5) (the same real small-scale
  social organization); `altitude` for Georgian (0.4, the Caucasus) and, added to the two already-
  curated profiles above, Tibetan (0.9, the Tibetan Plateau) and Quechua (0.6, the Andes, more moderate
  since Quechua is also spoken in lowland valleys); `contact_intensity` for Ancient Greek (0.6, Koine's
  Hellenistic-era spread), Turkish (0.6, Ottoman-era Arabic/Persian loanword absorption), Old Norse
  (0.55, Viking Age trade/settlement -- English/Russian loanwords), Persian (0.55, the Persianate
  world's own literary lingua franca), Arabic (0.65, Islamic-era trade/conquest spread), and Zulu
  (0.5)/Xhosa (0.55) (click consonants adopted from well-documented Khoisan contact, one of
  linguistics' most-cited areal sound-borrowing cases); `orality_literacy` for Latin (0.8, Medieval
  Latin's centuries as a purely written/liturgical language), Hebrew (0.85, ~1,700 years as a written-
  and-liturgical-only language before its 19th/20th-century revival), and Sumerian (0.8, the literal
  origin of writing itself, cuneiform); `aesthetic_harshness` for Georgian (0.5, dense real consonant
  clusters/ejectives), Dutch (0.45, the real velar/uvular fricative), and Arabic (0.5, real pharyngeal/
  uvular/emphatic consonants); `tone_sandhi` for Mandarin (0.7, its own third-tone rule, already the
  trait's own canonical textbook example); `phonotactic_restrictiveness` for Finnish (0.5, native-
  vocabulary consonant-cluster restrictions); `terrain_communication_distance` for Mongolian (0.5,
  traditional steppe herding-call/long-song tradition). Verified: new blend-mechanism spot checks
  (Basque-sourced generation nudges `isolation` to 0.9, Zulu-sourced nudges `contact_intensity` to 0.5,
  both at blend weight 1.0) plus the full test suite.

  **Deliberately not curated this batch, for a specific reason each, not an oversight**: Sumerian's own
  city-states were major Bronze Age trade hubs, so `isolation` was *not* added there despite Sumerian
  also being a genealogical language isolate -- "no known relatives" and "a geographically/socially
  isolated speech community" are different facts, and only the first is true of Sumerian. Sanskrit was
  considered for `orality_literacy` but dropped: its own real tradition is just as famous for
  *precise oral* transmission (Vedic recitation, the Śikṣā phonetic tradition) as for writing, making a
  one-directional "written norm anchors it" framing genuinely ambiguous rather than well-grounded.
  Welsh was considered for `contact_intensity` but dropped: its own real history with English is
  substantially about suppression/displacement, not the trade/creolization-flavored contact this trait's
  own description centers on.

  **Batch 3 -- all remaining 20 reachable profiles curated, direct user request ("go ahead with
  those").** 22 new trait values, same "real, specific citation, not a guessed number" standard as
  batches 1/2: `contact_intensity` for Indonesian/Malay (0.6 each, the shared Malacca-Strait trade-
  lingua-franca and layered Sanskrit/Arabic/Dutch/Portuguese/Chinese loanword history), Khmer (0.45,
  Sanskrit/Pali via Indian Ocean trade and Theravada Buddhism), Arawakan (0.5, real Garifuna
  ethnogenesis -- Carib/Arawakan intermarriage with shipwrecked West Africans, a UNESCO-recognized
  contact story), Danish (0.4, Hanseatic Middle Low German trade contact), Tamil (0.4, Chola-era
  maritime trade network) alongside `orality_literacy` (0.65, one of the world's longest continuous
  literary traditions, Sangam-era poetry), Hindi (0.55, Mughal-era Persian/Arabic absorption, the same
  layer that produced Urdu) alongside `social_hierarchy` (0.5, the real tū/tum/āp three-tier pronoun
  system), Bengali (0.45, Bengal Sultanate/Mughal-era Persian/Arabic layer), Cantonese (0.4, British
  colonial-era English loanwords), Vietnamese (0.6, a millennium of Chinese contact plus French
  colonial contact), Yoruba (0.45, the transatlantic contact history behind Santería/Candomblé),
  French (0.55, its own centuries as Europe's diplomatic lingua franca), Portuguese (0.55, Age-of-
  Exploration maritime/colonial contact), Russian (0.35, Mongol-Tatar Golden Horde-era loanwords, kept
  modest as one specific historical layer), Spanish (0.6, ~800 years of Al-Andalus Arabic contact plus
  its own colonial spread), and Sanskrit (0.5, the well-documented "Sanskrit cosmopolis" spread across
  South/Southeast Asia -- a different, cleaner angle than the `orality_literacy` ambiguity that got it
  skipped in batch 2); `isolation` for Hungarian (0.5, a Uralic language surrounded by unrelated
  Indo-European languages in the Carpathian Basin for a millennium); `aesthetic_harshness` for Italian
  (-0.45, the real phonological grounding behind its "melodious" reputation -- high vowel-to-consonant
  ratio, no harsh series at all), German (0.4) and Polish (0.4, alongside `phonotactic_restrictiveness`
  at -0.45 for Polish's own famously permissive consonant clusters -- the opposite pole from Finnish's
  own restrictive case).

  **Still deliberately uncurated, same "no clean real-world correlate found" standard as the 4
  project-wide-excluded traits**: Welsh, Norwegian, Swedish, and Serbo-Croatian remain completely
  uncurated -- Welsh for the reason already stated above (its English contact is suppression, not
  trade); Norwegian/Swedish for lacking a distinctly *their own* well-documented fact beyond the shared
  Old Norse/Viking-era history already curated on that profile directly; Serbo-Croatian because its own
  real contact/history is bound up in politically sensitive questions about the underlying language's
  own unification/division that this project isn't equipped to adjudicate. 49 of 53 profiles now have
  at least one curated trait -- these 4 are the only ones left with none, and are being left that way
  deliberately rather than force-filled. Verified: all 53 YAML files still parse; direct
  `blend_toward_reference` spot checks (Spanish/Polish/Hindi/Hungarian) each resolve to their exact
  curated value at blend weight 1.0; full suite green.
- **Tweaking a saved language's own traits and regenerating -- plan written up as its own chapter.**
  See `## 12. Tweaking an existing language` below.
- **Orthography reform is partial -- done (pass 42 + two follow-ups).**
  `evolve_romanization` now models reform (drop + regenerate a spelling
  rule), freeze (keep it verbatim), and reading drift (the written form
  stays the same while its conventional reading quietly reassigns to a
  nearby symbol, confirmed never dropping a symbol across 200+ seeds); a
  drift-touched symbol no longer wrongly re-spells an *existing* word
  that didn't itself change sound this run; and reading drift can now
  condition on a following front vowel specifically for a drifting
  consonant (not just a flat reassignment), paired with a matching
  conditioned-palatalization sound change. See `architecture/
  OVERVIEW.md`. Deferred: lineage-biasing *which* palatalization variant
  a matched real profile prefers; the intermediate `ts`/`dz` stage; a
  conditioning tag other than front/back vowel.
- **Frequent words should change less during evolution (M) -- direct user request, scoping the
  word-formation plan.** Real, well-documented frequency effect (Bybee's usage-based phonology;
  frequent words are maintained by rote and resist regular sound change, hence English's own most
  irregular verbs are overwhelmingly its most frequent ones). Confirmed feasible, not attempted here:
  `evolve_language`'s own loop (`sound_change.py`, the `_evolve_ipa(entry.ipa, rng, rates, ...)` call
  over `base.lexicon.entries`) already has each full `LexicalEntry` -- including `.glosses` -- in
  scope at the exact point `rates` get applied; nothing currently reads it. The natural fix is a
  per-word rate dampener keyed on `lexicon_gen.CORE_MEANINGS`/`_CORE_MEANING_GLOSSES` membership
  (the same frequency proxy fresh generation's own word-length fix already uses), composed into
  `_compute_rates`'s existing rate-biasing shape as one more multiplicative factor rather than a new
  per-rule mechanism -- scoped and real, just not built in this pass.
- **Compound ossification during evolution (M) -- direct user request, same scoping conversation.**
  Real diachronic phenomenon: a compound's own internal boundary erodes under sound change until
  it's reclassified as a single opaque root (English "woman" < "wife-man", "window" < "wind-eye",
  "lord" < "hlāfweard" "loaf-ward" -- the user's own `_compound_entry` fallback case in the word-
  formation plan above is this exact process working forward instead of backward). This needs the
  word-formation plan's own structured compound-marking on `LexicalEntry` to exist first (today
  `_compound_entry`'s own compound-ness is recorded only as free-text `notes`, not structured) --
  once that lands, evolution could roll, per compound word per evolution run, whether its boundary
  survives recognizably or the word gets reclassified as a plain root (and its `root`/compound
  metadata cleared), biased by the same contact/drift-strength traits already feeding every other
  evolution rule. A direct, concrete follow-up once the word-formation plan ships, not before.

## 12. Tweaking an existing language

Direct user request: "I'd like to be able to tweak an existing language. E.g. change aesthetic
harshness. And then have the option to regenerate words, or use the old words, and then if reusing
words should be changed to accommodate the new sound inventory that comes out, but still be based on
the previous word," followed by "write a plan... in a separate tab in the app... split up in items."

A real, substantial new capability -- distinct from both a fresh `generate` (new seed, no inheritance
from the old language at all) and today's `--evolve-years` (`generate_evolved_language`/
`evolve_language`, which drifts an *existing* phonology through *time-based* sound-change rules, not
from a directly-dialed-in new trait value). Not started; broken into the items below, roughly in build
order -- each is independently schedulable, and later items depend on earlier ones.

- **1. Give phonology its own independent `rng` stream -- done.** `generate_language`'s phonology call
  now draws from its own `random.Random(f"{spec.seed}:phonology")` stream instead of the shared
  `rng = random.Random(spec.seed)` romanization/grammar/lexicon all still draw from afterward -- same
  "own independent stream" pattern `generator.py` already used for its punctuation-style and script
  rolls. Confirmed via a real full-suite run: every seed's exact phonology/romanization/grammar/lexicon
  output shifted as expected (32 tests failed on hardcoded-seed/fixture assumptions, none on a genuine
  logic break), each re-pinned to a newly-found seed with the same documented properties or hardened
  against a legitimate `None`-gloss case the new seed selection happened to newly exercise -- see
  `architecture/OVERVIEW.md` for the full account.
- **2. A scoped phonology-regeneration function -- done, simpler than originally sketched.** New
  `generator.regenerate_phonology(name, language, trait_overrides, llm_client) -> Language`. The
  original sketch above (hand-copy `language.grammar` across unchanged, manually re-derive only
  phonology/romanization/script) turned out to be unnecessary complexity: thanks to item 1, phonology's
  own draws no longer perturb the shared stream grammar/lexicon draw from, and a grep across every
  module under `generation/` confirmed none of the three allowed trait fields are read outside
  `phonology_gen.py` in the fresh-generation path -- so simply building an edited `GenerationSpec`
  (same seed, only `traits` updated) and calling `generate_language` on it again is enough:
  `generate_language`'s own grammar roll reproduces byte-identical typological choices (word order,
  alignment, cases, tenses, morphology type, ...) by construction, confirmed with a real test, not
  assumed. **v1 scope, corrected from the original sketch by the same grep**: only `altitude`/
  `aesthetic_harshness`/`phonotactic_restrictiveness` are accepted (`core.traits.
  PHONOLOGY_ONLY_TRAIT_FIELDS`) -- `isolation` was dropped (also read by `grammar_gen.py`, would have
  broken the "grammar stays identical" guarantee) and `terrain_communication_distance` was dropped
  (read only by `sound_change.py`/evolution, a silent no-op in a fresh regeneration). A disallowed key
  raises `ValueError` rather than being silently ignored.
- **3. "Regenerate words" mode -- done, for free, as a side effect of item 2.** Item 2's own
  implementation calls `generate_language` outright, which always recoins the lexicon fresh against the
  new phonology/romanization -- no separate mechanism was needed.
- **4. "Reuse old words, adapted" mode -- done.** New `generator.regenerate_phonology_adapt_words`,
  layered on item 2's own output: each of the base language's lexicon entries gets its `ipa` re-fit via
  `phoneme_fit.fit_ipa` against the newly rolled inventory/syllable structure, then its `romanization`
  re-derived via the new `RomanizationScheme.apply` + `apply_grammatical_spelling` (the same pairing
  fresh coinage itself uses) -- every other field (`glosses`/`pos`/`root`/`word_class`/`notes`/
  `real_word`) carries over unchanged. Verified live, not just by the mechanism's own description: the
  same base word came out as "Hya" (regenerate -- an unrelated new word) vs. "Ḫaya" (adapt -- the same
  word, consonant cluster intact) under the identical trait edit; "we" (Mu) came out completely
  unchanged under adapt, since its own sounds already all survived in the new inventory. **Known v1
  limitation, documented on the function itself**: `fit_ipa` only ever fits the *segmental* shape --
  stress/word-accent/tone marks are already stripped for its other two existing callers, not a new gap
  here -- so every adapted entry's own `tones` is cleared to `()` rather than left stale/inconsistent
  with a now-unmarked `ipa`; adapting a tonal language's own lexicon does not yet preserve its tones.
- **5. CLI entry point -- done.** `generate --tweak-from <name> --words {regenerate,adapt}`, mirroring
  `--evolve-from`'s own shape exactly (loads a saved language, always saves the result under `--name` as
  a new language, source never overwritten) and reusing the *already-existing* `--trait NAME=VALUE`
  flag/`_parse_trait_overrides` unchanged. `--prompt`/`--source-language`/`--seed`/etc. are all ignored
  outright in this mode (the base language's own already-resolved seed/spec is reused directly) --
  `--prompt` stays required syntactically (same as `--evolve-from`) but is never read. Verified with a
  real example (see `docs/CLI.md`'s own "Tweaking" section): `regenerate` and `adapt` run back to back
  on the same base + same trait edit visibly diverge in exactly the way item 4 describes, right in the
  CLI's own printed word-list.
- **6. A new, separate "Tweak" tab in the web UI -- done.** Its own top-level tab (`panel-tweak`,
  alongside Generate/Translate/Inspect/Script/Reference/Log in `nav`), not folded into Inspect. A
  language picker (same `fillLanguageSelect`/`refreshLanguages` pattern as Inspect's own); trait-override
  rows restricted to `PHONOLOGY_ONLY_TRAIT_FIELDS` (a new, separate field list from Advanced Options' own
  15-field `gradedTraitFields`, since the backend rejects anything outside the three phonology-only
  names) and pre-filled from the picked language's own current nonzero trait reading (`GET /api/
  languages/{slug}`'s own `traits` field) rather than starting blank; a "words" radio (regenerate/adapt);
  a save-name field (defaults to `{slug}-tweaked`, never overwrites the source, same precedent
  `--evolve-from`/`--tweak-from` already set). New `POST /api/languages/{slug}/tweak` endpoint (same
  response shape `/api/generate` already returns); the result renders through the *already-existing*
  `showInspectResult`/`renderLanguageSummary` completely unchanged, since a tweaked language is still
  just a `Language` like any other -- confirmed live: submitting switches to the Inspect tab showing the
  tweaked result, with grammar/glosses verified identical to the base language the same way the CLI/unit
  tests already confirm it.
- **7. Word-by-word diff/preview before saving -- done.** `TweakRequest.dry_run`: `/api/languages/
  {slug}/tweak` computes exactly as normal but skips `_repository().save(...)` when set, returning
  `"saved": false`. Since `regenerate_phonology`/`regenerate_phonology_adapt_words` are both
  deterministic, no server-side preview state is needed -- the web UI's own Tweak tab just POSTs the
  identical body again with `dry_run: false` to commit what it already showed. The Tweak tab's own
  "Preview Tweak" button renders a before/after table (gloss/pos/old spelling/new spelling, reusing the
  lexicon table's own column shape as planned) without leaving the tab or saving anything; a "Save
  Tweaked Language" button then appears to commit. Picking a different language (or anything that would
  make the preview stale) clears it. Verified live: a preview showed real before/after pairs ("ggauhk3
  -> ggauhk") with the language confirmed not yet on disk (404), then Save produced a saved language
  whose first word matched the preview exactly.
- **8. Extend tweaking to grammar-affecting traits (L), stretch goal, not needed for v1.** Once item 2's
  phonology-scoped mechanism is proven, the same pattern (own independent `rng` stream, a scoped
  regeneration function, reuse existing grammar_gen machinery) could extend to the traits item 2 v1
  explicitly excludes (`social_hierarchy`, `spatial_reference`, `evidentiality_culture`, ...), letting a
  user eventually tweak grammar without touching phonology, or both at once. Not attempted until item 2
  ships and is validated on the phonology-only slice first.
- **9. Extend tweaking to Roman Orthography -- done ("Tweaking Phase 2").** New
  `generator.regenerate_orthography(name, language, orthography_overrides: OrthographyForce,
  llm_client)`. Turned out NOT to be a simple "edit GenerationSpec.forced_orthography, call
  generate_language again" the way `regenerate_phonology` is: `romanization_gen.generate_romanization`
  draws from the *same* shared `rng` stream grammar/lexicon coining also draw from (confirmed by reading
  `generator.py`'s own flow -- no independent `":romanization"` stream exists the way phonology's own
  `":phonology"` stream does), so re-rolling it that way would also shift grammar/lexicon output, not
  just the spelling. Implemented instead as a direct, standalone re-derivation: a new independent
  `":orthography-tweak"` rng stream builds a fresh `RomanizationScheme` via `generate_romanization`
  directly (same inputs as fresh generation, just the new forced style), then every lexicon entry is
  re-spelled from its own *unchanged* `ipa` via `apply_grammatical_spelling` -- phonology/grammar/script
  and every word's own IPA stay byte-identical (verified in `tests/test_regenerate_orthography.py`), only
  spelling changes. No "regenerate vs. adapt" words mode exists for this axis (confirmed correct, not
  cut for time): since the IPA never changes, every word is always "re-spelled," never recoined -- there
  was never a real distinction to preserve. An exact real-word copy keeps its own real spelling verbatim,
  same guarantee item 4's `regenerate_phonology_adapt_words` already has for the phonology-tweak case,
  for the same underlying reason (a real word's own literal spelling was never derived from this
  language's own romanization scheme to begin with). Can't be combined with a phonology-trait tweak in
  the same request (the webui endpoint dispatches to one axis or the other, never both at once --
  documented on both the function and `TweakRequest` itself). Web UI: a new collapsible "Roman
  Orthography (separate axis)" section in the Tweak tab, reusing the exact same fixed selects Generate's
  own Roman Orthography fieldset already has. Verified live end-to-end through the real dev server: IPA
  identical before/after, spelling visibly changed under a forced Wade-Giles-style tweak.
- **10. Extend tweaking to language-source features (M-L), not attempted in "Tweaking Phase 2" --
  confirmed harder than items 9/11, not just "likely" as originally guessed below.** Direct user
  request: Tweak should also support changing a saved language's own `source_languages`/
  `source_language_strictness`/`source_word_strictness` after the fact. Investigated (not implemented)
  while building item 9's own `regenerate_orthography`, since the same "does this field draw from the
  shared `rng` stream grammar also reads from" question applies here too -- and the answer is yes, in a
  *third* place beyond phonology and the lexicon: `word_class_gen.generate_word_classes` *also* reads
  `traits.source_languages`/`source_language_strictness` directly, to decide whether a matched profile's
  own curated `WordClass`es (real French verb classes, real Swahili noun-class prefixes, ...) get
  adopted -- and `word_classes` lives on `GrammarProfile`, the exact thing `regenerate_phonology`'s own
  "grammar stays typologically identical" guarantee is built to protect. So changing the source-language
  axis risks perturbing grammar through a *third* channel beyond the two already known (phonology's own
  inventory roll; `real_words.plan_real_words`'s own lexicon planning, which already has its own
  independent `":real-words"` rng stream per the module's own docstring, so that one specific channel is
  actually fine) -- `word_class_gen.py` has no independent stream of its own at all, same gap
  orthography turned out to have. A real implementation needs to either give word-class generation the
  same independent-stream treatment item 1 gave phonology, or (more likely, since word classes are a
  *lexeme-level* choice re-resolved per word via `assign_word_class`, not a single whole-language roll
  the way morphological_type is) restructure this more like item 9's own direct-re-derivation shape
  rather than item 2's "edit spec, call generate_language again" shape. Scope this with that specific
  finding in hand, not from scratch.
- **11. Extend tweaking to the Writing System / invented script (L), deliberately scoped as its own
  larger investigation, not a quick extension.** Direct user request from a deep-dive review, with its
  own explicit framing: "tackle this one together with an overall deep dive into script" -- the user
  flagged this as needing bigger, separate treatment rather than a quick addition alongside items 9/10
  above. The core design constraint the user already specified: changing a script trait (e.g.
  `angularity`) during a tweak should only change the ANGLES of a glyph's EXISTING strokes, not add or
  remove strokes outright -- i.e. a tweaked script should still be visually recognizable as a variant of
  the original invented script, not an unrelated fresh one. This is a materially harder problem than
  items 9/10: today, `force_own_script`/`ScriptTraits` feed into `script_gen.py`'s glyph-generation
  pipeline as seed-time parameters that shape the WHOLE generative process per glyph (stroke count
  included), not as a post-hoc transform applied to an already-generated glyph's own stroke data -- so
  "only re-angle existing strokes" would need either (a) a genuinely different, constrained regeneration
  mode in `script_gen.py` that holds stroke *topology* fixed while re-rolling only angle-affecting
  parameters, or (b) a true post-processing transform applied directly to each glyph's own stored stroke
  geometry. Needs its own investigation into `core/script.py`/`generation/script_gen.py`/
  `speech/font_builder.py`'s actual internals (how a glyph's strokes are represented, whether angle and
  topology are already cleanly separable parameters or are entangled in the generative process) before
  any implementation plan can be written -- not attempted here, per the user's own explicit framing.
- **12. Tweak preview should show the sound *correspondence*, not just added/removed sets -- done
  ("Tweaking Phase 2").** New `phoneme_fit.sound_correspondence(old_inventory, new_inventory) ->
  dict[str, str]`, reusing `fit_ipa`'s own internal per-symbol `_nearest` match (no new matching logic),
  exposed via the tweak endpoint's own `sound_correspondence` response field and rendered directly in
  the "sounds lost" chip list (e.g. "ç → /x/") instead of a bare symbol with no indication of where it
  went. Originally written up below as a separate idea; kept for the historical record.
  which old sound now maps to which new one, not just two separate chip lists. There usually *is* a
  fixed, derivable correspondence available: in "adapt" mode, each old symbol's nearest-match target is
  already computable via `phoneme_fit._nearest(old_symbol, new_inventory)` -- the exact function
  `fit_ipa` itself calls per-symbol -- so a new small helper could compute, for every symbol in the
  *base* inventory, what it would be re-fit to in the *new* one, and the preview's own sound-diff
  section (added in the 19-point round, `renderSoundInventoryDiff`) could show `/f/ -> /f/` (unchanged),
  `/x/ -> /h/` (shifted), style arrows instead of (or alongside) the current separate added/removed
  chip lists. Not attempted here -- needs a new backend field (a per-symbol correspondence list) and a
  frontend rendering pass, a moderate but well-scoped addition building directly on existing machinery.

## 13. Trait realism

Two related "this doesn't feel realistic" reports from a round of hands-on use of the new Evolve tab,
both pointing at the same underlying theme (real-world rarity/magnitude isn't yet reflected in how
traits get picked or how fast they act) but requiring unrelated fixes with very different risk profiles.

- **The fake LLM's trait distribution is unrealistically uniform, not weighted toward real-world rarity
  (M-L, needs a full-suite re-pin).** Direct user report: "there are not that many languages with very
  high altitude, yet randomly it will be relatively high 25% of the time with a random pick." Confirmed
  the exact mechanism: `llm/fake_client.py::_fake_trait_profile` maps each trait name to
  `round((stable_hash(prompt + name) % 201 - 100) / 100.0, 2)` -- a flat, uniform draw over 201 values
  spanning `[-1.0, 1.0]`, so `P(value > 0.5)` really is exactly 25%, matching the report precisely. This
  is deliberate *for its original purpose* (the fake LLM's own module docstring: "just needs to vary
  deterministically by prompt... spanning both positive and negative," for exercising "different
  prompts -> different generated languages" in tests) -- but the free "Fake LLM" backend is also this
  project's primary *everyday* generation mode (the real LLM costs money), so its unrealistic shape
  leaks straight into ordinary use, not just tests. `core.traits.TraitProfile`'s own module docstring
  already states the intended real shape for the *real* classifier -- "calibrated to rarely report
  values near +-1.0" -- so the fake stand-in arguably should mimic that same statistical shape instead
  of diverging from it. Fix would be mechanical (reshape the hash-derived uniform draw toward 0 with a
  sign-preserving power curve, e.g. `sign(x) * abs(x) ** p` for some `p > 1`, still deterministic, still
  spanning both signs) and apply uniformly to all 15 `GRADED_TRAIT_FIELDS` as the user requested -- but
  the blast radius is large: nearly every test in this project's suite generates at least one language
  via the fake LLM (`AGENTS.md`'s own "fake-LLM-first rule"), and this project has *already* been
  through the exact shape of fallout a change like this causes -- the "give phonology its own
  independent rng stream" change (ch. 12 item 1's own history) reshaped far fewer draws and still broke
  32 fixed-seed tests needing individual re-pinning. Changing every trait's own magnitude for every
  fake-LLM-classified prompt would very plausibly affect an order of magnitude more tests than that (any
  test asserting a specific generated property that happens to sit near a probabilistic threshold a
  trait feeds into). Needs a dedicated pass budgeted for a full re-pin, not a quick edit alongside
  other work -- deferred for that reason alone, not because the fix itself is unclear.
- **Evolution's own contact mechanism redesigned around a capped per-source "contact intensity" instead
  of the flat `source_language_strictness` it used to read -- done.** Three of the user's own notes,
  interlocking, implemented together as one redesign:
  - *"Sound strictness should be removed from evolution... introduce words from the source languages
    slowly, as well as take over phonology, grammar etc., with a particular speed based on weight
    (better to rename to contact intensity). Contact intensity should have a limit in terms of total sum
    of 1.0..."* and *"Contact intensity should follow directly from the sum of intensities of source
    languages."*
  - *"When adding Thai with 0.5 influence... and 100 years of evolution, it quickly gained 15 sounds. Is
    this reasonable?"*
  - Two follow-up clarifications: the per-language intensity must be given **explicitly, with no
    default** ("the sum doesn't have to sum up to 1.0, that is merely the maximum of all influence...
    normally it would be quite far below 1.0"); the 1.0 ceiling is **not cumulative** across separate
    evolution runs ("a language's own prior contact history... does not count"), and `contact_intensity`
    itself becomes fully derived -- not separately configurable via `trait_overrides` -- the moment any
    source language is active this run ("it should not be configurable in evolution when there is a
    source language specified, but gets taken over by the source languages").

  Confirmed, not assumed, exactly why Thai at weight 0.5 still produced full-strength change:
  `sound_change._evolve_phonology_membership` read a single flat scalar, `strictness = traits.source_
  language_strictness if lineage_profiles else 0.0` -- every matched source language's own symbols were
  pooled into one `reference_symbols` set with **no per-language weight applied at all**, so a source
  language added at `weight=0.5` was treated identically to one at `weight=1.0` for this mechanism
  specifically (weight *did* matter for `_coin_borrowed_word`'s own lexical-replacement sourcing --
  the two mechanisms were already inconsistent about what "weight" meant). `source_language_strictness`
  is also explicitly a *generation-style* "how closely does this stick to a real source" dial, not a
  *rate-of-contact-over-time* one -- the user's own "that belongs in generating languages inspired by a
  language" framing was a real, correct architectural distinction this project hadn't drawn yet.

  **Mechanism** (`sound_change.py`): every evolution-path read of `source_language_strictness` now reads
  `contact_intensity` instead -- `_evolve_phonology_membership`'s own gain/loss roll (now gated on, and
  scaled by, `contact_intensity`), `_coin_native_word`'s stress/accent lineage-fidelity, and `romanization_
  gen.evolve_romanization`'s own reform/drift strictness. `contact_intensity` was already read by
  `_replacement_rate` (lexical-replacement speed) and `_evolve_tone_system` (tonal detonalization chance)
  from earlier work, so this unifies *every* contact-related evolution mechanism (phonology gain/loss,
  lexical replacement, orthography reform/drift, native-word accent fidelity, tonal detonalization) onto
  one dial, matching "take over phonology, grammar [orthography] etc. with a particular speed based on
  weight" directly. `generate_language`'s own fresh-generation use of `source_language_strictness` is
  completely unchanged, per the user's own "that belongs in generating languages inspired by a language"
  distinction -- only `evolve_language`'s own mechanics switched dials, and `evolve_language` itself
  doesn't derive anything -- it just reads whatever `contact_intensity` its caller resolved, same as any
  other trait, so this applies identically regardless of caller.

  **Web endpoint** (`webui/app.py`, scope deliberately limited to here -- see below): new
  `EvolveSourceLanguageEntry(name, intensity)` replaces `SourceLanguageEntry` for `EvolveRequest.
  source_languages` -- `intensity` is **required** (no default at all, not even for a single entry,
  per the user's own explicit correction) and semantically an *absolute* contact-pressure dial, unlike
  Generate's own `weight` (a *relative* blend proportion among sibling sources). `evolve_language_
  endpoint` validates each intensity is in `[0.0, 1.0]`, that their **sum** doesn't exceed `1.0` (400 if
  it does -- a ceiling "normally... quite far below," never a target), and rejects outright if `trait_
  overrides` also tries to set `contact_intensity` alongside a nonempty `source_languages` (ambiguous
  which should win) -- then derives `contact_intensity = sum(intensities)` directly and feeds that same
  value as `blend_toward_reference`'s own blend weight too (previously a separate `strictness` field on
  `EvolveRequest`, now removed -- one number now drives every contact-related effect for the run,
  including the reference-trait-grading blend). The cap is **per-run, not cumulative**: a language's own
  prior lineage (carried forward via `evolve_language`'s existing `lineage_languages` merge) does not
  count against a *later* run's own 1.0 ceiling, confirmed as the user's own explicit choice. When no
  `source_languages` are given this run, `contact_intensity` is untouched by any of this and `trait_
  overrides.contact_intensity` still works exactly as before (unchanged old behavior, verified with a
  test) -- the derivation/validation only activates when there's new contact to compute from.

  **Web UI** (`static/index.html`): Evolve's own source-language rows are a dedicated `addEvolveSource
  LangRow`/`collectEvolveSourceLanguages` pair (not a reuse of Generate's `addSourceLangRow` -- the two
  fields mean genuinely different things now, not worth forcing through one shared shape), each row
  showing a required "intensity" input instead of an optional "weight," plus a live running total against
  the 1.0 cap (`updateEvolveIntensityTotal`, turns red when exceeded). The `contact_intensity` row inside
  the Grammar trait-override group becomes disabled and shows the live derived total the moment any
  source-language row is active, and restores the language's own actual current value
  (`evolveBaseContactIntensity`) the moment every source-language row is removed again -- so the UI never
  lets a user set both at once, matching the backend's own rejection. The standalone "Sound strictness"
  input that used to sit next to "Years of evolution" is gone entirely (its only remaining role, the
  reference-trait-grading blend weight, is now the same derived `contact_intensity`).

  **Deliberately out of scope**: the CLI's own `--evolve-from` keeps its existing `--source-language
  NAME[:WEIGHT]`/`--strictness` flags with their existing *relative, auto-normalized* semantics --
  fundamentally different from the web endpoint's new *absolute, capped-sum* "intensity," so unifying
  them would be semantically wrong, not just more code. The underlying `sound_change.py` mechanism swap
  still applies to every `--evolve-from` run (no CLI code needed for that part), but a CLI user who wants
  the old "strict lineage-gain" effect must now use `--trait contact_intensity=X` explicitly instead of
  `--strictness X` -- `docs/CLI.md`'s own `dutch-evolved-strict`/`dutch-evolved-loose` example was
  updated and re-verified with real output to reflect this (`contact_intensity=1.0`: 19->19 consonants,
  no net gain; `contact_intensity=0.0`: 19->24, balloons with contact-driven gains -- same demonstrated
  direction as before, just via the new dial).

  **Item 2's own "15 sounds in 100 years" magnitude question**: not separately recalibrated. The Thai-
  at-0.5 report is now believed to have been largely explained by weight being silently ignored (fixed
  above) rather than the base rate itself being wrong -- recalibrating `_MERGER_HALF_LIFE`/`_MIN_GAIN_
  ACCEPTANCE`/`_compute_rates`'s own per-rule half-lives against real contact-linguistics history remains
  a real, legitimate future direction if the magnitude still feels off once contact intensity is actually
  driving the roll as intended, but doing so needs real comparative data to ground it, not a guessed
  number -- left for a future session to judge with the fix in place, not attempted blind here.

  Verified: `tests/test_sound_change.py`'s own membership/strictness-damping tests (4 of them) updated to
  construct `contact_intensity` instead of `source_language_strictness` where that field was literally
  the mechanism under test -- same assertions, same behavior, confirming this was a pure field-swap, not
  a formula change; `tests/test_evolve_webui.py` gained 6 new tests (intensity required, out-of-range
  rejected, sum-over-1.0 rejected, explicit `contact_intensity` override rejected alongside source
  languages, correct derivation as the sum, and unaffected behavior with no source languages); full
  suite green. Live-verified through the real dev server: adding a source language at intensity 0.25
  disables and live-updates the `contact_intensity` row to match, removing it restores the language's
  own actual value, and the saved result's own `traits.contact_intensity` matches the entered intensity
  exactly.
