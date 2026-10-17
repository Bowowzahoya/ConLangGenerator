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
- **Reorganize the Generate/Inspect result view into labeled sections (M-L).** Direct user request.
  `renderLanguageSummary` (`webui/static/index.html`) is the one function behind the Generate tab's
  own result, the Inspect tab, and Translate's "view details" -- today it's one flat info dump, a
  single `.badges` div mixing grammar/orthography/own-script/bookkeeping badges together, traits in a
  second ad hoc div right below it, and no structure beyond that. Requested grouping, mirroring
  Advanced Options' own `fieldset.advanced-group` divisions, applied identically everywhere this one
  function renders:
  1. **Language Sources & Evolution** -- the `source_languages` badge, `source_language_strictness`,
     the `real_words` badge, `foreign_names`, `evolved_years`.
  2. **Grammar** -- `word_order`, `alignment`, `morphological_type`, `has_articles`,
     `has_overt_copula`, `adjective_after_noun`, `cases`, `tenses`.
  3. **Phonology (incl. Traits)** -- the existing trait badges (today a second ad hoc `.badges` div)
     folded in here, with the existing Sound Inventory section (`renderSoundInventorySection`) right
     underneath.
  4. **Tones** -- the existing `renderToneSection`, content unchanged, just given the same section
     wrapper as everything else instead of sitting at the same visual level as the sound-inventory
     `<h2>` with no further grouping.
  5. **Roman Orthography** -- the existing `orthography_category` badge.
  6. **Own-script orthography** -- the existing script toggle/font-download/glyph-count badge. Name
     still a placeholder (the user flagged this themselves) -- "Writing system" and "Invented script"
     are the two better candidates to pick between when this is implemented.
  7. **Generation Details** -- the cost badge, `pregenerated_audio` badge, `word_selection`, and two
     fields `_language_summary` doesn't expose to the web UI at all yet:
     `language.spec.classifier_model`/`word_selection_model` (recorded at generation time, never
     surfaced here before).

  Concrete plan, not yet started:
  - `webui/app.py`'s `_language_summary`: add `classifier_model`/`word_selection_model` to the
    returned dict (plain strings, same shape as `orthography_category`) -- the only backend gap;
    every other value this reorg needs already rides along on the existing summary dict.
  - `webui/static/index.html`'s `renderLanguageSummary`: split the one big template literal into one
    function per section (e.g. `renderSourcesSection`/`renderGrammarSection`/`renderPhonologySection`
    folding in today's trait-badge rendering/`renderOrthographySection`/`renderScriptSection` extracted
    from today's inline toggle+download block/`renderGenerationDetailsSection`), each returning its own
    heading plus a shared new CSS class (e.g. `.summary-section`, visually matching
    `fieldset.advanced-group` rather than inventing a second look), called in sequence from
    `renderLanguageSummary`. Generate/Inspect/Translate's "view details" all pick this up for free,
    since all three already funnel through this one function.
  - No other backend schema changes -- every other value already exists in the summary dict today;
    this is a template reorganization plus the two added model fields above.
  - Tests: a new `tests/test_webui.py` assertion that `classifier_model`/`word_selection_model`
    round-trip through `/api/generate`'s response. No other backend test changes expected (no field
    moves or is removed, only grouped differently in the rendered HTML); the HTML reorganization itself
    gets verified by hand in a real browser, the same standard the preceding `advanced-group` fieldset
    split already followed.

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
getting its own separate plumbing. `ritual_register`, `taboo_register` and
`terrain_communication_distance` remain genuinely unconsumed -- no register/formal-speech system, no
euphemism/avoidance-vocabulary system, and no long-range-communication proxy exists anywhere yet to
bias; each needs a real new mechanism built first, not just a formula (`orality_literacy` only affects
evolution's orthography reform; `social_hierarchy` is consumed -- it raises the probability a language
rolls `honorific_you` at all, see `pronoun_gen.py`). Word order is not trait-linked (S). Matched-language
grammar bias is partial: `real_word_order`, `real_alignment`, `real_has_articles`, ... exist for ~16
of ~50 profiles, and `morphological_type` has no matched-language bias -- it has no
`real_morphological_type` field on any profile at all, so this needs new per-profile data curated
across ~50 profiles, not a formula tweak (M, bigger than the three traits just wired).

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
