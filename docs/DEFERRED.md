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

## 2. Web app

- **Voice picker within an engine (S).** No choice of SAPI or eSpeak voice
  -- see §9's multi-engine item, which subsumes this.

## 3. Translation

- **Sentence-initial capitals treated as names (S, mostly done).** The
  planner prompt now says a capitalized sentence-initial word is a name only
  if it is not an ordinary English word, and the fake planner already
  ignores sentence-initial position; since text is now planned one sentence
  at a time, "Just"/"You" in a later sentence are no longer mistaken for
  names by the fake. Still open: check with a real LLM -- confirmed to
  still happen there, though its worst consequence (silently discarding
  a misclassified word, including a user's own manual edit, instead of
  reusing the existing ordinary entry) is now fixed; see
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
  punctuation still open (M-L).** Done: a per-language ``RomanizationScheme.
  punctuation_style`` (``standard``/``none``, independently rolled, ~12%
  ``none``) and ``core.romanization.terminal_mark(mood, style)`` give each
  rendered sentence a period/question mark/exclamation mark derived purely
  from the already-existing ``SentencePlan.mood`` (no new plan field --
  `"!"` only ever means `mood == "imperative"`, by construction, same as
  today's fake-planner detection); `translate_to_english` strips a mark
  before any lookup, also treats a bare `?`/`!` anywhere in the input as a
  question/imperative signal (so a language with no question particle can
  still decode correctly), and its fallback text is now always terminated
  (previously a declarative got no mark at all; deliberately still not
  capitalized -- see `docs/LIMITATIONS.md`). Still open:
  quotation marks (direct speech isn't modeled at all -- `quotative_
  particle` is reported/indirect speech only, confirmed in its own
  docstring) and comma placement (would need clause/list-boundary rules) --
  both genuinely bigger, separate features, not a continuation of this
  pass's own scope. Also still open, each a deliberate scope boundary of
  this pass (see `docs/LIMITATIONS.md`): no `exclamatory` signal
  independent of mood (a plain exclamatory statement still reads as
  declarative); decode is not re-split per sentence, so a multi-sentence
  decode input still reports one whole-input question/imperative signal,
  not per-sentence.
- **Coined words ignore word strictness -- done (pass 53).** On-the-fly
  coinage (`translation/expansion.py::coin_word`) now tries a real word
  first, reusing generation-time word strictness's own machinery: a
  deterministic per-gloss roll against `source_word_strictness`, a
  curated-lexicon lookup, else one single-gloss LLM call (`real_words_
  llm.fetch_real_words`, API-shape-compatible with a 1-item request
  unmodified), the same systematic deviation-shift table reconstructed
  from `(seed, strictness, inventory)` rather than persisted (it's fully
  derivable, so no schema change was needed) -- and only *falls back* to
  this project's existing invented-word coinage when none of that
  produces a usable word. This actually fires in practice specifically
  for a core-vocabulary gloss the generated `--vocabulary-size` left out
  (curated lexicons cover ~496 glosses; the default vocabulary is 400),
  not a coincidence -- every gloss `coin_word` could otherwise reach is,
  by construction, already in the lexicon by the time translation runs.
  Root-and-pattern (templatic) languages are excluded (adapting a
  borrowed word into an existing template is a different problem, left
  open); a real-word-based on-the-fly coinage never checks for a spelling
  collision against the rest of the lexicon, the same non-guarantee
  generation-time real words already have.

## 4. Generation from the user's own words

- **Seed words drive the language (part of speech, bulk input,
  phonotactic-mismatch warning, structural bias, orthography bias, and
  multi-form/inflected grammatical forms -- including pronoun case and
  verb tense beyond past -- done, passes 47-51 -- this entry is now
  closed).** "I think it should sound like this, and I already
  thought up some words -- fill in the rest consistently." Done:
  `SeedExample.pos` (optional; `--example
  gloss=form|ipa|pos` on the CLI, a per-row select in the web UI,
  defaults to NOUN exactly as before when omitted); bulk input
  (`--examples-file` on the CLI, a paste-many textarea in the web UI, both
  through a shared `generation.seed_examples.parse_bulk_seed_examples`);
  a warning (never a silent repair, since the given words must still
  appear verbatim) when a seed word's IPA isn't a legal syllable shape
  under the language's own generated `SyllableStructure`; deriving
  syllable-shape bias (pass 48) -- `generation/phonology_gen.py::_seed_
  structural_profile` reads each seed word's own onset/coda cluster sizes
  and whether it carries a tone mark; and deriving spelling-convention
  bias (pass 49) -- `generation/romanization_gen.py::_seed_orthography_
  profile` reads each seed word's own spelling against its IPA for the
  symbols where the letter count exactly matches the sound count (no
  digraph guessing -- a wrong split, e.g. misreading "qu" as independent
  q->k/u->w rules, is worse than abstaining). Both passes build a pseudo
  `ReferenceLanguageProfile` from the inferred signal and fold it into the
  *existing* reference-profile weighting machinery in their own module
  (confirmed in both to pull unconditionally, not gated behind `source_
  language_strictness`) -- no new mechanism, no new CLI/web flag,
  automatic whenever seed words are given. Also done (pass 50):
  `SeedExample.forms` -- a user-given irregular (suppletive) form for one
  of the four cells the existing suppletion mechanism already models
  (`plural`/noun, `past`/verb, `comparative`+`superlative`/adjective; a
  cell not matching its own word's POS is rejected, not guessed). A
  pre-created `LexicalEntry` keyed by `voice_np_gen.suppletive_gloss(base,
  cell)` is found directly by `translator._lookup_or_coin` at render time
  with no further render-side code; `voice_np_gen.suppletive_split`/
  `translator._class_gloss` gained an optional `grammar` parameter so
  decode and noun-class assignment also recognize a seeded lemma (not just
  the hardcoded English-irregular dicts). `--example gloss=form|ipa|pos|
  forms`/a 5th bulk-CSV column/a web-UI forms field, all sharing
  `generation.seed_examples.parse_seed_forms`'s `;`-separated
  `cell:form[:ipa]` syntax. Known scope limits: giving only one of
  comparative/superlative still makes the *other* cell suppletive too
  (since `grammar.suppletive_degrees` doesn't distinguish which), falling
  through to an unrelated freshly-coined word rather than the regular
  affixed form; a rendered suppletive form can still take regular,
  non-tense marking (e.g. subject agreement) on top of the user's own
  stem, same as the pre-existing hardcoded mechanism.

  **Also done (pass 51), closing both items the prior pass had left out of
  scope**: pronoun-case suppletion (a seeded word's own irregular "I"->
  "me"-style case form) and verb-tense suppletion beyond plain past
  (irregular `non_past`/`present`/`future`, not just `past`). Both
  generalize the pass-50 architecture rather than inventing a new one:
  `voice_np_gen.SUPPLETIVE_SUFFIXES` grew from 4 to 7 labels via a
  `suppletive_field(kind)` dict-dispatch (replacing an if/elif chain);
  `translator.py`'s render/decode "past"-only checks widened to any label
  in the new `voice_np_gen.TENSE_SUFFIXES`, byte-identical for `"past"` by
  construction. Pronoun cells (`accusative`/`ergative`/`genitive`/
  `dative`/`locative` -- never `nominative`/`absolutive`) reuse `pronoun_
  gen`'s own separate, pre-existing suppletion mechanism unmodified,
  folding a seeded person+case into `grammar.suppletive_pronoun_persons`/
  `_case_limits` once `grammar.cases` is final. A seeded pronoun-case or
  extra-tense cell the generated language doesn't end up having is kept
  in the lexicon but flagged by a new `seed_examples.unused_suppletive_
  form_warnings` (whether it's live can't be known until generation
  completes, unlike a cell/POS mismatch). Known quirk: seeding e.g.
  "she"'s accusative makes person "he" suppletive too (they share one
  agreement person label), so a separate, unseeded "he" entry for that
  same case falls through to ordinary coining -- same flavor as the
  pass-50 comparative/superlative quirk, not fixed, documented.

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

- **Generate an original script and package it as a font (L).** A huge
  item, kept on the agenda: design glyphs per phoneme/syllable, output a
  font (TTF/OTF/WOFF), and use it in the web UI.

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
- **Deviation is random, not systematic (done, pass 46).** Below word
  strictness 1.0, a real word's sounds now shift through a fixed,
  per-language `symbol -> symbol` table (`phoneme_fit.build_deviation_
  shift`/`apply_shift`) -- the same source phoneme always becomes the same
  target everywhere in a language, like a real daughter language's own
  sound laws, rather than an independent per-occurrence coin flip (the
  old `deviate_ipa`). Still a flat, unconditioned table (not context-
  sensitive) and feature-distance-nearest-neighbor, not lineage-aware --
  see docs/LIMITATIONS.md.
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

- **eSpeak tonal voice is Mandarin-only (M).** Tones work by switching to the
  `cmn` voice, so other sounds are approximated by Mandarin's inventory.
  The better fix is likely native per-engine pitch control (eSpeak's own
  SSML `<prosody>` contour, applied to whichever voice a word is actually
  using, not a voice switch) rather than a cross-engine PSOLA overlay.
  Not addressed by the per-word engine selection below -- that picks
  *between* eSpeak and SAPI per word, it doesn't change how eSpeak itself
  voices a tone once chosen.
- **Long, fixed pauses between words when a sentence is voiced -- done.**
  `webui/app.py::_synthesize_sentence`'s own inter-word silence shortened
  from 0.15s to 0.05s (`_INTER_WORD_SILENCE_SECONDS`). Real sentence-level
  intonation/stress/coarticulation stays explicitly out of scope by the
  same decision as before (word-level correctness and naturalness is the
  priority) -- sentence assembly otherwise stays as today's per-word
  concatenation; this was only ever the one small pacing fix in scope.
- **Multi-engine per-word selection (was one L item, split into
  right-sized pieces after planning surfaced just how much it bundled).
  Pieces 1-2 done.** Engine choice is per *word*, never per sound within
  a word, by explicit decision across every piece -- splicing different
  engines' audio together inside one word would need to solve matching
  pitch/timbre/volume at the seam, a separate, harder problem not taken
  on anywhere in this split. Done: a real per-phoneme coverage model
  (`speech.phoneme_coverage`, exact/approximate/poor per symbol, derived
  from `ipa_to_kirshenbaum.convert_symbol`'s own fidelity for eSpeak, a
  small curated table for SAPI) and the per-word selection built on it
  (`speech.engine_selection`), reachable as a new `"auto"` engine value
  on `pronounce --tts`/the web UI's Translate tab (not the default for
  either -- see the next sub-item).
  - **Surface engine choice and coverage more fully in the CLI/web UI
    (S-M).** `translate` still has no `--tts` path at all; `"auto"` is
    available but not the default anywhere, and there's no user-facing
    override (e.g. "prefer engine X when it covers the word") beyond
    picking a fixed single engine or `"auto"` -- decide whether `"auto"`
    should become the default, and what an override would even mean once
    selection is automatic per word.
  - **Add Piper as a new free, local, more natural-sounding neural engine
    (L, independent, slots into the roster once added).** The
    engine-vs-phoneme-set mismatch for a genuinely invented phonology
    (explored in chat) needs a concrete decision: approximate-only (map
    invented phonemes to the nearest sound Piper's pretrained voice
    already knows, no training) versus actually extending/fine-tuning a
    model (a much bigger, separate research effort) -- approximate-only
    is the realistic scope for this item.
  - **Add a paid cloud engine, e.g. Azure or Google SSML, with its own
    cost on/off toggle (L, independent).** Lowest priority -- needs the
    same per-task on/off-switch treatment this project already gives
    `llm=fake|anthropic`, off by default, before it's safe to even offer
    in the roster.
- **A per-sound pronunciation guide for people who aren't linguists (L).**
  Two tiers: (a) a full sound inventory for a given generated language --
  every phoneme it actually uses, each with a plain-language articulation
  description (tongue/lips position, not IPA jargon) and a soundclip; (b) a
  summarized version scoped to one specific word, showing only the sounds
  in that word, so pronouncing/translating doesn't require leaving the
  result to go look each sound up separately. Soundclips are synthesized
  (via the engine-selection item above -- whichever engine voices that one
  isolated sound most naturally), not sourced from real recordings.
- **Pronunciation is slow every time, not just the first time -- done,
  including the SAPI-specific latency this surfaced.** Repeated
  pronunciation used to re-synthesize every word from scratch.
  `speech/tts_cache.py::CachingTTSClient` wraps any real `TTSClient`,
  keyed on `(client.cache_identity(), ipa_text)` -- `cache_identity()`
  (new on the `TTSClient` protocol) fully captures what the engine/
  voice/tones state is, so eSpeak's own Mandarin-voice switch never
  collides with its default voice in the cache; stored as one `.wav`
  file per entry under `CACHE_DIR / "tts_cache"`, not a JSON blob
  (unlike the LLM cache -- audio is binary, a flat file store is the
  natural fit). Wired into both `cli/main.py`'s `pronounce` command and
  `webui/app.py`'s `/api/pronounce`, for every `--tts` value including
  `"auto"`. Pre-generation (eagerly warming the cache for a freshly
  generated language's whole lexicon) is also done: `speech/pregenerate.
  py::pregenerate_audio`, wired as a new explicit, not-automatic
  `--pregenerate-audio {none,espeak,sapi,auto}` CLI flag on `generate`
  (default `none`) and a matching `pregenerate_audio` field on `POST
  /api/generate`.

  **Follow-up, same item: the SAPI-specific ~3.7s/word cost itself,
  not just repeated-word caching, is now fixed too.** The user asked
  directly whether SAPI's latency could be improved, and it could: the
  cost was almost entirely a fresh PowerShell-process-startup + .NET-
  assembly-load on *every one-shot call*, not the actual synthesis.
  `speech/sapi_worker.py::SapiWorker` keeps one persistent process alive
  and reused across many words instead -- confirmed directly: a full
  400-word vocabulary via `--pregenerate-audio sapi` now takes ~2.7s
  total, not tens of minutes, so the web endpoint's `pregenerate_audio`
  now accepts `"sapi"`/`"auto"` too, not just `"none"`/`"espeak"`.
  `webui/app.py` also gained a module-level, lazily-started singleton
  worker (`_get_sapi_worker`) shared across *every* `/api/pronounce`
  request for that server's whole lifetime -- fixing the broader "auto
  is slow even for ordinary pronunciation" concern this same item had
  flagged, for every case except one: a single, standalone CLI
  `pronounce --tts sapi`/`auto` call still pays the full ~3.7s every
  time, since each CLI invocation is a fresh OS process with no second
  word for a worker to amortize against and no way to survive between
  invocations -- fixing that would need a cross-invocation background
  daemon, a materially bigger, separate feature, explicitly not
  attempted here. Confirmed byte-identical audio output to the original
  one-shot path for the same (including exotic, non-ASCII) IPA input --
  zero regression risk on SAPI's own direct-IPA-passthrough behavior,
  the reason it's worth having over eSpeak at all.
- **Untested by ear (S).** eSpeak tone numbers for mid/low/neutral
  (33/21/11) were only length-checked.

## 10. Grammar

Each feature has three parts, and all three must land together: (1) the
grammar generator invents the option (`grammar_gen.py`/`inflection_gen.py`),
(2) the planner and renderer use it (`sentence_planner.py`/`translator.py`),
(3) the English decoder reads it back (`translate_to_english`). Sizes:
S/M/L as above.

**Done:** plural number, imperative, yes/no and wh-questions, vocatives (as
plain sentence-initial nouns), per-sentence planning (pass 1); nested plan
structure with complement, relative and adverbial clauses (pass 2); aspect and
verbal mood as systems separate from tense (pass 3); noun classes with article,
adjective and verb (subject and object) agreement (pass 4); dual number,
demonstratives, numerals, an indefinite article and possession marking (pass 5); voice -- passive, antipassive, causative (pass 6); existentials and possession clauses (pass 7); comparatives and superlatives (pass 8); classifiers and the pronoun system (pass 9); reflexives, reciprocals, possessive pronoun paradigms, verb number and politeness, object pro-drop and richer classifiers (pass 10); suppletive pronoun case forms, reflexive possessives and possessive classifiers (pass 11); classifiers with quantifiers and per-noun classifiers (lexical pool, repeaters) (pass 12); subordination -- linker position, relativization strategies and position, non-finite verb forms, subordinate mood (pass 13); subordination follow-ups -- relativization reach, declining relative pronouns, agreeing infinitives, case-marked nominalizations, conditional sequencing, correlative adverbials, clause coordination, complementizers by verb class (pass 14); agreement follow-ups -- class assignment by semantic field or final sound, class marked on the noun (prefix/suffix), number and case agreement, numeral agreement, agreement inferred from position (pass 15); aspect/mood follow-ups -- auxiliary tenses, aspects and moods, evidentials, negation strategies and a prohibitive, distinct inflectional suffixes, affixes that evolve (pass 16); voice and noun-phrase follow-ups -- middle, applicative and impersonal voices, passive agent and agreement, trial and collective number, locative/instrumental case, adposition placement and case government, irregular plurals and comparatives, inalienable possession (pass 17); partial pronoun suppletion, adjective placement and stacking order, a specific article and a demonstrative-derived definite article (pass 18); the rest of the noun-phrase list -- suppletive pasts, partial possessive words, more classifier constructions, ablative/allative/comitative cases and a wider adposition table, adjectives across "and", agreeing specific article, deictic and doubled articles, tonal derived articles (pass 19); decoding speed-ups (pass 20); comparison follow-ups -- equatives, excessives, elatives, degrees on adverbs, "more" of a noun, ablative/locative standards, "the more..., the more..." in the fake planner (pass 21); real inflection paradigms -- declensions, conjugations and irregular lexemes (pass 22); paradigm follow-ups -- more cells, patterned syncretism, stem changes, adjective classes (pass 23); prefix, circumfix and infix inflection (pass 24); morphophonology -- vowel harmony, hiatus resolution and initial-consonant mutation (pass 25); derivation and compounding (pass 26); reduplication as grammar and root-and-pattern inflection and derivation (pass 27);
subordination follow-ups -- prepositional (pied-piped/stranded) relative clauses, stacked
relatives, raising and passivized-control infinitives, a nominalized clause as the subject,
reported-speech tense backshift, chained clause coordination, gapping, right-node raising and
two more complementizer classes (pass 28); agreement follow-ups, second round -- a plain
subject-plus-intransitive-verb sentence now gets verb agreement (the fake planner's plainest
sentence shape had never carried one before), a classifier repeater carries its noun's own class
marker and decodes back once, and semantic-field class assignment now covers animals, people and
materials (pass 29); aspect/mood follow-ups, second round -- a periphrastic auxiliary word can now
agree with the subject like a real auxiliary "have"/"has" instead of being an invariant particle;
the ordinary negative suffix can now mark a non-finite verb form, not only a finite one; "there is
no X" (and "A has no B") can use one dedicated negative-existential word instead of the ordinary
negation particle; a second collision-resolution pass now also catches a suffix *concatenation*
spelling like some other single affix, not just single affixes one by one; and evolving a language
can now grammaticalize a periphrastic auxiliary into a bound suffix, and grow its suppletive-past
list, the longer the time depth (pass 30); voice follow-ups, second round -- an impersonal verb now
plans (and, defensively, renders) with no subject at all, not just no subject agreement; an
applicative verb's promoted beneficiary now triggers the verb's own object agreement, a real
valency-changing effect (and a matching decode-search gap -- a voice and object agreement
combination together, never tried before -- fixed along the way); and the fake planner's closed
middle/antipassive verb lists are a bit wider (pass 31); comparison follow-ups, second round -- a
negative degree ("less big [than Y]", "least big") and a sufficiency degree ("big enough", the one
degree word that follows the adjective rather than precedes it); an equative's own standard case,
rolled independently of the comparative's; and a wider fake-planner adjective list (pass 32); a
topicalized sentence ("as for the cat, it sleeps") fronts the topic and marks it with a dedicated
particle where the language has one, dropping the main clause's resumptive subject (pass 33); a
subject-referent honorific ("the professor sleeps") reuses the addressee-politeness verb affix for a
closed list of titled subjects (pass 34); a quotative particle marks a speech-verb's complement
clause as reported speech, and tense backshift is now gated to speech verbs specifically (pass 35).
See `architecture/OVERVIEW.md`.

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

- **Strictness does not reach evolution -- done (pass 38/39).**
  `sound_change`'s inventory recompute could drift a strict language back
  toward the generic -- not because evolution gaining new sounds is wrong
  (real languages do that constantly), but because the mechanism used to
  be completely lineage-blind, so a strictness promise silently stopped
  applying the moment evolution ran, by any degree. Fixed in three stages:
  Stage 1 (pass 38) stopped `_recompute_syllable_structure` from silently
  *dropping* (not just freezing) most of a language's own phonological
  richness on every evolution regardless of strictness -- quads, both
  onset-exclusion fields, every onset/nucleus/coda boundary pair field,
  and the three per-position frequency-multiplier fields now survive
  (filtered to the evolved inventory, not blindly copied). Stage 2 (pass
  39) evolves the phonology *specification* itself as its own object,
  mirroring how fresh generation already builds one, instead of deriving
  it backward from whatever survived in already-mutated words:
  `_evolve_phonology_membership` gives every phoneme a small,
  time-scaled, strictness-independent chance of merging away (ordinary
  lineage-internal drift), and gives every sound-change-introduced
  phoneme an acceptance roll biased by `source_language_strictness`
  against the matched lineage's own palette -- heavily suppressed at high
  strictness when foreign to the lineage, but floored at 10% so it is
  never literally impossible (a dial, not a wall; empirically verified:
  Dutch-lineage ejective-drift acceptance dropped from 40/40 seeds at
  strictness 0 to 9/40 at strictness 1.0, damped rather than blocked). Its
  own per-position frequency multipliers also take a small bounded random
  walk each evolution call instead of staying frozen forever. Stage 3
  (pass 39) repairs any word whose own evolved IPA still contains a
  symbol Stage 2 rejected, refitting it to the final inventory via the
  same nearest-neighbour machinery (`phoneme_fit.fit_ipa`) `translation/
  names.py`/`generation/real_words.py` already share -- functions as a
  real merger, consistently wherever that symbol occurs, closing the
  inventory/wordlist mismatch class of bug Stage 1's own testing twice
  surfaced. Gated on `strictness > 0.0` (and on a matched lineage): at the
  default strictness 0, Stage 2/3 are a byte-identical no-op, confirmed by
  construction, not just by testing.
- **Rules are generic, not language-specific -- done (pass 40, stages 1-3).**
  "Dutch evolved forward 200 years" used to apply the general rule set
  only -- now each of the six rules' own *rate* (not its mechanics: the
  sound laws themselves are still generic) is additively biased by up to
  three independent sources, any or all absent (no-op) on a given run:
  - **Stage 1 -- real-lineage curated tendencies.** Six new
    `historical_*_affinity` fields on `ReferenceLanguageProfile`
    (`lenition`/`cluster_simplification`/`final_devoicing`/
    `palatalization`/`vowel_reduction`/`ejective_drift`), curated for a
    first batch of 14 of 51 profiles anchored directly to real, citable
    cases (several already this module's own docstring anchors): Dutch/
    German/Russian/Turkish/Polish (final devoicing -- Auslautverhärtung);
    Dutch/German (ejective drift, negative -- never developed ejectives);
    English (cluster simplification, vowel reduction); Latin/Spanish/
    French/Portuguese (lenition -- Western Romance intervocalic p/t/k >
    b/d/g; Italian deliberately excluded, see below); Russian/Polish/
    Serbo-Croatian (palatalization -- Slavic); Quechua/Georgian (ejective
    drift -- real ejective-bearing languages); Mandarin (vowel reduction,
    negative -- tonal, resists it). Unweighted mean across multiple
    matched lineages; combined additively with the evolution's own
    generic traits via a shared `_biased_strength` clamp, never
    overriding them.
  - **Stage 2 -- structural self-derived tendencies.** Applies to *any*
    evolving language, fictional included, with no curation and no
    lineage match needed: `_derive_structural_bias` reads the language's
    own *current* phonology/syllable structure (existing cluster
    richness -> cluster simplification; voicing-readiness -> lenition;
    voiced-obstruent coda material -> final devoicing; an existing
    palatal output + front vowels -> palatalization; vowel inventory size
    -> vowel reduction; an existing ejective -> ejective drift).
  - **Stage 3 -- richer use of already-extracted traits.** `orality_literacy`
    (already consumed for orthography-reform rate) extended to all six
    rules uniformly (a written norm anchors pronunciation against drift
    the same way it anchors spelling); `tonal_friendliness`/
    `terrain_communication_distance` both resist vowel reduction (tone
    carries contrastive load; loud/long-distance speech needs distinct
    vowel quality -- `terrain_communication_distance`'s own real
    mechanism, previously missing per the "Wiring existing traits" item
    above); `aesthetic_harshness` biases ejective drift (mirrors the
    existing fresh-generation fricative-harshness precedent).
  Reshaped from a one-stage into this three-stage plan by direct user
  feedback: stay flexible to what the *prompt* says about the evolution
  period's own circumstances (never overridden -- everything above is
  additive), and cover *fictional* languages too, not just real-sourced
  ones (Stage 2's whole reason to exist). Deferred: curating the
  remaining 36 profiles (Stage 1); extracting genuinely *new* free-text
  evolution-period concepts in the prompt classifier, rather than reusing
  today's fixed trait set (a bigger, riskier follow-up, not attempted
  here); `isolation`/`community_scale`/`social_hierarchy`/
  `spatial_reference`/`evidentiality_culture`/`ritual_register`/
  `taboo_register` for Stage 3 (no individually crisp, sound-change-rate-
  specific motivation found).
- **Evolved real words -- done (pass 41).** A new `RealWordOrigin` (`core/lexicon.py`:
  `language`/`form`/`ipa`) on `LexicalEntry.real_word`, set once at coinage by
  `generation/real_words.py` (both exact and deviated real-based words -- the deviated
  case keeps the *true* original, not its own already-looser starting form) and never
  touched again by anything downstream: `evolve_language`'s entry-rebuild loop only
  updates `ipa`/`romanization`/`notes`/`root`/`word_class` via `model_copy`, which leaves
  every other field (`real_word` included) exactly as it was -- so it survives any number
  of evolution steps unchanged, reaching all the way back to the real source word even
  after a *second* evolution run, which the CLI's own existing "old -> new" print couldn't
  do on its own (it only ever compares to the *immediately preceding* saved language).
  Cleared to `None` when a word is borrowed or natively replaced (a genuinely different
  word filling the same meaning's slot, not the same word sound-changing). `cli/main.py`'s
  evolve print now appends `(real Dutch water [ˈvatər])` alongside the old -> new
  comparison when set; the web UI's lexicon table and its `real_words` count switched from
  the old `notes`-prefix check (which evolution already overwrote, silently undercounting
  after one evolution step) to this new, evolution-proof field.
- **Orthography reform is partial -- done (pass 42, +follow-up).** `evolve_romanization`
  already modeled reform (drop + regenerate a symbol's own spelling rule) and
  freeze (keep it verbatim, why real orthographies get silent letters); now adds
  the third real force, *reading drift*: a letter's own written form stays
  exactly the same while its conventional reading quietly reassigns to a nearby
  symbol, with no formal reform event (real Latin "c" originally /k/, later read
  /s/ before front vowels; English "gh" drifting from a real consonant to
  silence). New `reading_drift_rate` (own `_ORTHOGRAPHY_HALF_LIVES["reading_drift"]`
  half-life, same `-orality_literacy` link `reform` already uses): a symbol that
  would otherwise freeze gets one further roll; if it fires, its own rule(s)
  keep their spelling but move to a same-class nearest neighbor
  (`phoneme_fit.neighbours`, promoted public, the same nearby-sound machinery
  `deviate_ipa` already used); the vacated original symbol gets a freshly
  generated rule of its own (same helper reform already calls), so the scheme
  stays total -- confirmed never dropping a symbol across 200+ seeds, including
  chained reassignments. Honestly scoped: this is a flat symbol reassignment,
  not phonetically context-conditioned (real Latin c/s is conditioned on a
  following front vowel).

  **Follow-up, same pass**: the original version re-spelled every *existing*
  word still pronouncing a drift-affected symbol this same run -- fine for a
  genuine reform (real deliberate reforms really do apply retroactively), wrong
  for mere reading drift (nobody is actively enforcing anything, so an
  already-written word has no reason to suddenly look different). Fixed:
  `evolve_romanization` now returns `(scheme, reading_drifted)` -- every symbol
  touched by drift this call, from either side of a reassignment (the symbol
  that lost its own grapheme, *and* the symbol that received a donated one).
  `evolve_language`'s entry-rebuild loop checks this first: a word whose own
  sound didn't change this run *and* uses a drift-touched symbol keeps its
  exact old spelling (`notes: "orthography: pre-drift"`) rather than being
  re-rendered through the new scheme -- only a newly-coined/replaced word, or
  one whose own sound genuinely moved, follows the new convention. This project
  still tracks no word's own spelling independent of its current `ipa` + the
  current scheme for any *other* kind of change (true of ordinary reform
  today, unchanged) -- reading drift specifically is now the one exception
  that respects an existing, unaffected word's own history.

  **Second follow-up -- phonetic-context conditioning, done.** Direct user
  follow-up to the "not phonetically context-conditioned" limit above.
  Working through a concrete design surfaced a correction: real Latin "c" ->
  /s/ before front vowels wasn't pure orthography drift (no underlying sound
  change) -- it was a genuine *conditioned sound change* (/k/ phonetically
  shifted, specifically before front vowels) combined with ordinary spelling
  *freeze* (the letter was never updated to reflect it). Landed as two
  separate, independently useful mechanisms:
  - `_apply_palatalization` (`sound_change.py`, already conditioned on a
    following front vowel) gained a second real outcome per source
    consonant -- `_PALATALIZATION_VARIANTS = {"k": ("tʃ", "s"), "g": ("dʒ",
    "z")}`, weighted 0.65 toward the affricate (most lineages stop there;
    French/Latin-American-Spanish-like lineages go one step further, to the
    plain sibilant) -- a new `rng.choices`-style draw strictly after the
    existing trigger roll, same RNG-stream convention as every other
    extension this session.
  - `evolve_romanization`'s own `reading_drift_rate` (`romanization_gen.py`)
    can now produce a *conditioned split* instead of always a flat
    reassignment, for a drifting *consonant* only (a vowel can't condition
    on its own frontness -- its identity already fixes that): the old
    grapheme keeps meaning the original symbol everywhere, but *also* means
    the drift target specifically before a front vowel, via the
    already-existing `RomanizationRule.following=("front_vowel",)` class tag
    -- zero new conditioning infrastructure needed, `apply()`'s own
    specificity ordering already does the rest. Both sides still feed the
    prior follow-up's own `reading_drifted` set, so an unaffected existing
    word keeps its own old spelling either way.
  Deferred: lineage-biasing *which* palatalization variant a matched real
  profile prefers; the intermediate `ts`/`dz` stage; a conditioning tag
  other than front/back vowel.
