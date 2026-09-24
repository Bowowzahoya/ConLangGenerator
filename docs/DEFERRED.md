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
- **Model choice per task (M).** `DEFAULT_MODEL` (Haiku 4.5) is hard-wired
  into every request. Add a selectable model for language generation
  (classifier), for word selection, and for translation, in the CLI
  (`--model`, `--word-model`, `--translate-model`) and the web UI, with the
  expected price shown next to each choice. `llm/pricing.py` already holds
  $/1M-token prices for Haiku 4.5, Sonnet 5, Opus 5.5 and Fable 5 and
  `estimate_cost`; an estimate needs typical token counts per purpose
  (taken from the cost ledger: classify ~3.3k in / 0.3k out, translate plan
  ~1.5k in / 0.05-0.3k out; word selection scales with lexicon size).
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

- **Advanced options (S).** Move the checkboxes for fantasy, force isolated,
  force high altitude, force tonal, allow all-caps POS and foreign names
  into the collapsed "Advanced options" block. Also let the LLM choose
  foreign-name handling: today `foreign_names` is `"keep"`/`"adapt"` when
  explicit, else a vote of the source-language profiles' curated
  `foreign_name_handling` (`translation/names.py:resolve_foreign_names`);
  the classifier is never asked, so it cannot pick it. Add it to the
  classifier output.
- **Model picker (M).** UI counterpart of the model-choice item in §1,
  with expected price per call shown.
- **Hover/click gloss in the translation result (M).** Show what every word
  in a translation means (English gloss, part of speech, case/tense
  marking) by hovering or clicking, and align it with the source words.
  `TranslationResult` would need to carry per-token gloss data (the plan
  slots plus the resolved entry) alongside `text`.
- **Voice picker within an engine (S).** No choice of SAPI or eSpeak voice.

## 3. Translation

- **Sentence-initial capitals treated as names (S, mostly done).** The
  planner prompt now says a capitalized sentence-initial word is a name only
  if it is not an ordinary English word, and the fake planner already
  ignores sentence-initial position; since text is now planned one sentence
  at a time, "Just"/"You" in a later sentence are no longer mistaken for
  names by the fake. Still open: check with a real LLM.
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
- **Punctuation (M).** Punctuation disappears in translation. Decide punctuation
  rules per orthography (which marks, spacing, question/exclamation
  marks, quotes) and carry them through the plan and the romanization;
  keep the round trip back to English working.
- **Coined words ignore word strictness (M).** On-the-fly coinage always
  invents; it could use the real word (curated, else LLM) when word
  strictness is high.

## 4. Generation from the user's own words

- **Seed words drive the language (M-L).** "I think it should sound like
  this, and I already thought up some words -- fill in the rest
  consistently." Take a set of user words (spelling, optional IPA, gloss,
  optional part of speech and grammatical forms), derive a subset of
  rules/sounds from them (inventory, syllable shapes, orthography,
  frequent clusters), then generate the rest of the lexicon to fit. The
  given words must appear verbatim in the language; a prompt can still be
  added. Belongs under Advanced options in the web UI and a file or flag
  in the CLI. Extends the existing seed examples, which today default to
  NOUN, are not checked against the generated syllable structure, and
  have no sentence-level form. Grammatical forms could be passed in the
  prompt or as columns.

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
- **Deviation is random, not systematic (M).** Below word strictness 1.0 a
  real word is loosened by random nearest-phoneme swaps; a fixed per-language
  consonant-shift table would look like a real daughter language.
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
  Alternatives: eSpeak SSML `<prosody>` pitch contours, or PSOLA-style F0
  post-processing.
- **Per-word synthesis (M).** Sentences are voiced word by word with fixed
  silences: no sentence intonation, stress or coarticulation.
- **Voice selection (S).** See §2.
- **Capability model is tones-only (M).** Engines report which tones they
  voice, not which sounds (clicks, ejectives, pharyngeals, breathy voice,
  length) are dropped; warnings cover tones only. `translate` has no
  `--tts` path to warn about.
- **Other engines (L).** Piper/Coqui, Azure/Google SSML. Kirshenbaum
  conversion for `ɸ β ɕ ʑ ɦ ɭ ɽ ʈʂ` is approximate and unlistened.
- **Audio cache (S).** Repeated pronunciation re-synthesizes every word.
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
demonstratives, numerals, an indefinite article and possession marking (pass 5); voice -- passive, antipassive, causative (pass 6); existentials and possession clauses (pass 7). See
`architecture/OVERVIEW.md`.

**Next, in order:**
1. **Subordination refinements (M).** Clause-internal word order and
   linker placement are LLM- and heuristic-driven, not grammar-generated:
   no per-language choice of relativization strategy (relative pronoun vs
   gap vs particle), no infinitival/nominalized complements, no verb-form
   changes in subordinate clauses (subjunctive, non-finite), no
   correlatives. The subordinator ("that", "because") is coined as an
   ordinary particle word.
2. **Agreement follow-ups (M).** See below.

**Agreement follow-ups (M):** number agreement (plural verbs/adjectives); a
noun's class is not marked on the noun itself (no Bantu-style prefixes or
Romance-style endings), only through agreement; class assignment for
non-gendered nouns is a hash, not real lexical gender; adjective agreement
depends on the planner naming the noun (`agrees_with`); no agreement of
possessives, numerals or demonstratives; case agreement on adjectives.

**Aspect/mood follow-ups (M):** tense, case and agreement suffixes can still
collide with one another (only aspect and mood suffixes are made distinct);
no periphrastic (auxiliary) tenses or moods; no evidentiality or negative
mood; aspect/mood affixes do not yet evolve in `sound_change`.

**Voice follow-ups (M):** the middle/reflexive voice, reciprocals, applicatives
and impersonal passives; an agent case (instrumental/ergative-as-agent)
instead of a "by" word; voice-sensitive agreement (the verb agrees with the
patient in a passive only if the planner says so); the fake planner never
produces antipassives. Decoding a token in a language that rolled many
features (object agreement, aspects, moods, voices, classes) can take a few
seconds when the token is not a word of the language, because it searches
suffix combinations (staged and prefix-filtered); a cache or smarter suffix
matching would fix it (S-M).

**Existence/possession follow-ups (S-M):** more strategies (locative
possession "at me is", topic-comment possession, a possessive verb that
agrees with the possessed noun, "have" as a light verb); a dedicated
existential particle; negative existentials with their own verb ("there
isn't"); habitual/experiential possession ("I have to"); the English
direction relies on the fluency prompt note rather than recognizing the
construction itself.

**Clause types still missing:** comparatives and superlatives (M).

**Noun phrase still missing:** collective number and trial (S); classifiers
("two [piece] dogs") (M); a real pronoun system (person, number, clusivity,
honorifics, pro-drop, reflexives; today only I/you/he/we, others are coined as
ordinary words) (M); adjective stacking and adjective-noun order beyond
`adjective_after_noun` (S-M); adposition *placement* is left to the planner
(the renderer does not reorder) and no adposition has case government (S-M);
possessor agreement with the possessed noun's class, possessive pronoun
paradigms, and inalienable vs alienable possession (M); further cases
(locative, instrumental) (S); definiteness beyond the two articles, e.g.
specificity or demonstrative-derived articles (S).

**Verb phrase still missing:** auxiliaries and periphrastic tenses (M);
negation strategies (affix, double negation, negative verbs) (M);
evidentiality (M); serial verbs (L); valency-changing morphology (L); copula
strategies (zero, state vs identity) (S); adverb placement (S).

**Morphology:** real inflection paradigms (declensions, conjugations,
irregulars) instead of one invented affix per feature (L); prefix/infix/
circumfix positions (M); morphophonology at affix boundaries (vowel harmony,
mutation) (L); derivation and compounding (L); reduplication as grammar (M);
root-and-pattern beyond citation shapes (L). The new plural, imperative and
question-particle forms do not yet evolve with `sound_change` (S).

**Discourse (optional, L):** topic/focus and information structure, pro-drop
and ellipsis, politeness/honorific registers (uses `social_hierarchy`),
reported speech, idioms.

**Wiring existing traits (M each):** `social_hierarchy`,
`evidentiality_culture`, `spatial_reference`, `ritual_register`,
`taboo_register`, `terrain_communication_distance`,
`salient_vocabulary_domains` are extracted and stored but consumed by
nothing (`orality_literacy` only affects evolution's orthography reform).
Word order is not trait-linked (S). Matched-language grammar bias is partial:
`real_word_order`, `real_alignment`, `real_has_articles`, ... exist for ~16
of ~50 profiles, and `morphological_type` has no matched-language bias (M).

## 11. Language evolution

- **Strictness does not reach evolution (M).** `sound_change`'s inventory
  recompute can drift a strict language back toward the generic.
- **Rules are generic, not language-specific (L).** "Dutch evolved forward
  200 years" applies the general rule set, not Dutch's likely developments.
- **Evolved real words (S).** The original real word is not kept alongside
  the evolved form for display ("water > waːter").
- **Orthography reform is partial (M).** Only rate-driven; no
  spelling-pronunciation drift.
