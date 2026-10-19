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
- **Freshly-coined words can violate their own language's syllable structure (M), found investigating
  the Tweak no-op bug.** Root-cause, confirmed directly: generating "frenchlike" (a saved language,
  `max_coda=1`, `allowed_coda_clusters=()`) produced "begin" as `chefr` /ʃəfʁ/ -- a word-final two-
  consonant coda its own structure explicitly forbids, and the word has no real-word provenance
  (`notes`/`real_word` both empty, so it wasn't a real-word copy bypassing validation on purpose, see
  ch. 7's own "exact real word copy" precedent). Re-running `phoneme_fit.fit_ipa` against this exact
  same (byte-identical, unchanged) inventory/structure "fixes" it to `chefar` /ʃəfaʁ/, confirming
  `fit_ipa`'s own `SyllableStructure.is_valid_syllable` check disagrees with whatever check (if any)
  the original word-coining path (`word_builder.py`/`lexicon_gen.py`) used when this word was first
  built -- a real consistency bug between the two, not something this project's own phonotactics model
  is incapable of expressing (the structure itself is perfectly expressive; something just isn't
  enforcing it consistently at coining time). Confirmed in `frenchlike` specifically: 28 of 400 words
  (7%) have this shape. Not root-caused further or fixed here -- needs reading `word_builder.py`'s own
  cluster-construction/legality logic side-by-side with `SyllableStructure.is_valid_syllable` to find
  exactly where they diverge, a genuinely separate investigation from the stress-mark fix this same
  report led to (already fixed, see `generation/phoneme_fit.py`'s own `fit_ipa`).
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
- **Word length doesn't correlate with a word's own "basicness," only its part of speech (M) --
  confirmed, not yet fixed.** Reported: "simple or more difficult words seem equally likely to be long
  or short" for a generated language, unlike real languages (Zipf's law of abbreviation: frequent/basic
  concepts trend shorter). Traced directly: `lexicon_gen.choose_syllable_count`'s own `favor_short`
  parameter -- whose docstring explicitly invokes Zipf's law -- is passed `True` at literally every call
  site in the codebase (grepped; no caller ever passes `False`), and only ever varies the syllable-count
  table by **part of speech** (function-like words shortest, then a flat 1-4 syllable table identical
  for every other open-class word) -- there is no per-*gloss* basicness signal feeding it at all, so
  e.g. "water" and a far rarer/more specific noun draw from the exact same length distribution. This
  project already has the natural lever for a real fix: `lexicon_gen.CORE_MEANINGS` (referenced in
  `_GENERIC_AVERAGE_SYLLABLES`'s own docstring as a hand-counted-average source) is a real, identifiable
  basic-vocabulary subset of the full ~496-meaning list -- a gloss's own CORE_MEANINGS membership could
  bias `choose_syllable_count` toward shorter counts specifically, layered on top of (not replacing) the
  existing POS-based and source-language-average tilts. Not implemented here: this is a hot-path
  function (`generate_language` calls it for every coined word), so a change here needs the same full-
  suite-before-and-after discipline `AGENTS.md`'s own testing section already calls for on hot-path
  changes, not attempted inside an already-large batch of unrelated fixes.
- **No explicit "prefers long or short words" trait exists (S, once the item above lands) -- direct
  follow-up question, answered.** Confirmed: today's only word-length levers are the POS-based
  `favor_short` default (point above) and a matched source language's own curated
  `core_vocabulary_average_syllables` (`_resolve_average_syllables`, only applies with a source language
  and nonzero `source_language_strictness`) -- no standalone graded trait exists for "this culture's
  language favors long/elaborate words vs. short/economical ones" independent of any source language.
  Once the item above adds a real basicness-aware length mechanism, exposing a dedicated trait for it
  (rather than only a source-language-derived average) would be a small, natural follow-up -- but
  doing the trait first, before the underlying mechanism actually varies word length in a meaningful
  way per-gloss, would just add a dial with nothing real to turn.

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
45; this bullet otherwise predates those passes and was stale -- narrowed
to what's actually still missing):** serial verbs (L); valency-changing
morphology beyond pass 31 (L); a state-vs-identity copula distinction (zero
copula itself already exists, `has_overt_copula`) (S); adverb placement
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
- **Occasionally share a root between semantically related words (M) -- "to die"/"death," the user's
  own example.** Directly grounded in existing, intentionally-left-open infrastructure:
  `generation/root_pattern.py`'s own module docstring already says this exact thing is out of scope
  *for now*, not impossible -- "It does not attempt derivational relatedness between words... that needs
  semantic judgment between an English gloss and the existing lexicon, LLM territory, not attempted
  here, [but] `LexicalEntry.root` is recorded on every templatic word regardless, so that future work
  has the data already in place." This is exactly that future work: given two glosses the classifier (or
  a curated semantic-relatedness list, cheaper and more deterministic than an LLM call per word pair)
  judges related, reuse the earlier word's own `root` through a *different* template/affix rather than
  coining an unrelated new root -- a real, scoped feature, not a research problem, but one that needs a
  "which glosses are related" signal this project doesn't have yet (an LLM-classified list, most likely,
  given the docstring's own "LLM territory" framing).
- **A trait for compound-word likelihood (M) -- Monday/understand (English) vs. Mandarin's own heavy
  compounding, the user's own examples.** `generation/derivation_gen.py`'s own compounding mechanism
  already exists (see the pass-list at the top of this chapter: "derivation/compounding/reduplication/
  root-and-pattern morphology" is marked done) -- what's missing is a graded dial controlling *how
  often* compounding gets picked over a plain coined root or an affixed derivation, the same "weighted,
  trait-biased choice among existing options" shape several already-wired traits in this chapter use,
  not a new word-formation mechanism.
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
- **Separate Generation from Evolution more clearly across the whole app (XL, needs its own design
  pass before implementation) -- direct user request, raised as "help me think this out," not yet
  designed.** Today `generate --evolve-from`/the web UI's own single `--years`/`evolve_years` field
  bakes evolution into the *same* step as fresh generation (`generate_evolved_language` = generate,
  then immediately evolve) -- there is no separate moment to inspect, tweak, or branch from the freshly
  generated "base" before deciding how it should age. The user's own sketch, lightly organized:
  - **(a) A separate Evolve tab/step,** letting the user evolve *any* saved language (including one
    generated at 100% real-word/sound strictness from a single source profile -- today's only way to
    get a "real" starting point, since nothing in this project represents an actual historical language
    as a full `Language` object the way a generated one is; `evolve_language` itself already requires a
    full `Language`, not a bare reference profile, so "evolve a real language" is already possible
    today, just as a two-step "generate at strictness 1.0, then evolve" rather than one convenient
    action -- worth keeping, since the two-step shape is also how multi-source blending below would
    naturally work too). Conditions the user wants surfaced: current `terrain_communication_distance`
    (already modeled, see the item just above), influencing language(s) and their mix (`source_
    languages`/weights, already modeled for fresh generation -- `evolve_language` already merges a
    lineage's own curated rules in, but doesn't yet let a *new* set of contact languages bias an
    evolution run the way fresh generation's own `source_languages` can), whether re-evolving keeps old
    words vs. only their sounds (this project's existing "regenerate vs. adapt" distinction, already
    built for Tweak's own phonology-only case -- see ch. 12 -- generalizes directly here), and a more
    free-text, prompt-like channel for *how* languages influence each other during a contact period
    (the user's own example: "might expect more words in a particular area such as seafaring,"
    inferred from a prompt) -- this last piece is new and would need its own extraction work in
    `prompt_classifier.py`, not a reuse of an existing mechanism.
  - **(b) Generate stays focused on a "base language,"** with no evolution step of its own -- `--years`/
    `evolve_years` would move entirely to the new Evolve step; `source_languages` stays in Generate for
    the sound/word "feel" it already provides (unchanged).
  - **(c) A "Design" tab for a more complex, multi-source derived language** (evolution + several
    source languages + a description of what happened during the evolution period, possibly one prompt
    with sub-prompts for each base language it derives from) is the most novel, least-specified piece
    of this proposal -- it isn't just a UI reorganization of (a)/(b), it implies a genuinely new
    mechanism (blending/contact between *several* already-evolved or already-generated languages, not
    just one base plus one evolution period) that doesn't exist in any form today. Recommend treating
    this as a separate, later design pass once (a)/(b) are built and proven, not attempted in the same
    effort.
  - **(d) Inspect** would need to show a language's own generation-vs-evolution history more legibly
    (today's `history: list[str]` field is a flat log of free-text strings, e.g. `"evolved 400 years"`
    -- adequate for a human reading it, not structured enough to drive a UI distinguishing "base" from
    "evolved" state cleanly).
  - **(e) CLI:** per `AGENTS.md`'s own CLI discipline ("new capabilities do not automatically justify a
    new top-level command... consider whether the capability belongs under an existing command first"),
    recommend `generate --evolve-from` stays the CLI entry point rather than a new top-level `evolve`
    command, since the web UI's own tab-separation constraint (clarity for a casual user clicking
    through a form) doesn't apply the same way to a flag on an existing command a user already
    explicitly invokes by name.
  - **(f) The invented script evolving too, "grounded in reality"** -- deliberately bundled by the user
    with this same restructuring, but really depends on ch. 12 item 11 (tweaking a script, which is
    itself deferred as its own "deep dive into script" investigation) landing first: evolving a script
    is a repeated/gradual version of the same "change stroke style while staying recognizably the same
    glyph" problem, not a separate mechanism. Sequence this after that investigation, not in parallel
    with it.

  No part of (a)-(f) has been scoped into concrete functions/endpoints yet; this is a direction, not a
  plan. The recommended first slice, if picked up, is (a)+(b) together (a genuine, already-mostly-
  supported-by-existing-mechanisms separation), with (c) explicitly deferred further and (d)/(e)/(f)
  following once (a)/(b) exist to react to.
- **Grade every curated real language on all 15 worldbuilding traits, including the evolution-only
  ones, as an extra blending weight (L).** Direct user request: when generating a language "like"
  several real ones, the conlang could take on some of those reference languages' own typical
  worldbuilding-trait leanings (e.g. an isolated-community-typical language nudging toward the same
  grammar typology an isolated real language tends to have), weighted independently of -- not instead
  of -- the existing sound/word-strictness mechanism, which only ever governs the phonological/lexical
  palette. This is a real, coherent idea but a large one: it needs a documented, defensible trait
  reading for every one of ~53 curated `ReferenceLanguageProfile`s across all 15 dials (most of which
  have no agreed-on objective measure at all -- `social_hierarchy`/`ritual_register`/`taboo_register`
  in particular are cultural judgments, not phonological facts the way `core_vocabulary_average_
  syllables` is), a new blending formula distinct from today's sound/word strictness (itself already a
  two-strictness-dial system, see ch. 4), and a decision on how this new "cultural/typological" weight
  interacts with the classifier's own prompt-inferred trait reading when both apply to the same trait.
  Not attempted here; flagged as a real but substantial future direction, likely the single largest
  curation effort in this list.
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
- **9. Extend tweaking to Roman Orthography (M), not needed for v1.** Direct user request from a
  deep-dive review: Tweak should also support re-rolling a saved language's own romanization (its
  `orthography_style`/`exotic_symbol_style`/`vowel_length_style`/`syllable_boundary_marker`/
  `short_vowel_doubling`/`consonant_gemination` axes) independent of phonology -- e.g. keep the same
  sound inventory but try a different spelling convention. Genuinely simpler than item 2's own
  phonology-regeneration problem: orthography is already its own, separate roll
  (`romanization_gen.roll_romanization_scheme`/`force_romanization_scheme`), not entangled with
  phonology or grammar the way `PHONOLOGY_ONLY_TRAIT_FIELDS` had to be carefully scoped to avoid
  perturbing grammar -- re-rolling it doesn't touch the phoneme inventory, syllable structure, or any
  grammar-affecting trait at all. A new `regenerate_orthography(name, language, orthography_overrides,
  llm_client)` mirroring `regenerate_phonology`'s own shape (edited `GenerationSpec`, same seed, only
  the romanization-axis fields forced) would need a "words" mode too -- since every existing word's
  `romanization` is derived from its `ipa` via the orthography scheme, EVERY word's spelling changes by
  construction (there is no "adapt" vs. "regenerate" distinction the way phonology has one: the ipa
  itself never changes, only how it's spelled, so this is really just "re-spell the whole lexicon under
  the new convention" -- closer to item 3's "regenerate" mode, with no analogue to item 4's "adapt"
  mode at all). Web UI: a new orthography-axis section in the Tweak tab, likely reusing the Roman
  Orthography fieldset's own fixed selects (see item 13 of the 19-point review -- same selects Advanced
  Options' own Roman Orthography section already has, pre-filled from the picked language's current
  reading) rather than inventing a new control style.
- **10. Extend tweaking to language-source features (M), not needed for v1.** Direct user request from
  a deep-dive review: Tweak should also support changing a saved language's own `source_languages`/
  `source_language_strictness`/`source_word_strictness` after the fact -- e.g. take an already-generated
  language and re-roll it with a different (or no) real-language influence. Unlike orthography (item 9),
  this one is NOT obviously side-effect-free: `source_word_strictness` directly drives how many lexicon
  entries are real-word copies/real-word-based (`real_words.py`), so changing it necessarily means
  re-deriving a meaningfully different lexicon (not just a re-spelling), and `source_language_strictness`
  feeds into the actual phoneme-inventory roll in `phonology_gen.py`, meaning this would need the exact
  same "own independent rng stream + scoped regeneration" treatment item 2 already built for phonology
  -- changing source languages without the item-2-style care would risk the same grammar-perturbation
  problem item 2's own design had to solve for `isolation`. Likely the most involved of the three
  tweakable-axis extensions (8/9/10) precisely because it touches both phonology AND (via
  `source_word_strictness`) the lexicon at once; scope this one carefully against items 2/4's own
  machinery (quite possibly reusable close to as-is, given both already handle "re-derive phonology,
  then either recoin or adapt the lexicon") rather than building a third separate code path.
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
- **12. Tweak preview should show the sound *correspondence*, not just added/removed sets (M).**
  Direct user request from a deep-dive review: "if there is a fixed rule for that" -- prefer showing
  which old sound now maps to which new one, not just two separate chip lists. There usually *is* a
  fixed, derivable correspondence available: in "adapt" mode, each old symbol's nearest-match target is
  already computable via `phoneme_fit._nearest(old_symbol, new_inventory)` -- the exact function
  `fit_ipa` itself calls per-symbol -- so a new small helper could compute, for every symbol in the
  *base* inventory, what it would be re-fit to in the *new* one, and the preview's own sound-diff
  section (added in the 19-point round, `renderSoundInventoryDiff`) could show `/f/ -> /f/` (unchanged),
  `/x/ -> /h/` (shifted), style arrows instead of (or alongside) the current separate added/removed
  chip lists. Not attempted here -- needs a new backend field (a per-symbol correspondence list) and a
  frontend rendering pass, a moderate but well-scoped addition building directly on existing machinery.
