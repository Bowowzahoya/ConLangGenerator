# Deferred work

Things identified during development that would make the generator more
correct or more capable but are **not implemented**. Grouped by area; each
item says what is missing, why it matters and (where useful) where it would
go. Items marked *(known limitation)* are also described in
`architecture/OVERVIEW.md` ("Known v0 limitations" and the feature sections).

Rough effort tags: **S** = an hour or two, **M** = a session, **L** = a
multi-session feature.

---

## 1. Sounds and phonology

- **Spanish spirantization in the profile (S).** The lexicon writes `β ð ɣ`
  between vowels, but the Spanish profile lists only `b d g`. Adding them
  needs onset/coda tier entries and restrictions (they never open a word
  after a pause) plus orthography rules.
- **Russian palatalization gaps (M).** No `ʃʲ`/`ʒʲ`/`gʲ`, no hard/soft `l`
  contrast (`ɫ`), no long `ɕː` for щ (written `ɕ`), and vowel reduction
  (akan'e) is only partly reflected in the lexicon transcriptions.
- **Nasal vowels written as vowel + `n` (S).** French and Portuguese words
  approximate nasal vowels as `V+n` in the lexicons although `ɛ̃ ɔ̃ ã õ ĩ ũ`
  exist in the pool. A second pass could use the real symbols.
- **Geminates as doubled consonants (S).** Italian geminates are written
  `tt`, `ss` (a cluster) rather than the modeled long consonants; the pool has
  long forms only for `k t p s n l`. Extending the long-consonant set (`b d g
  m r ʃ …`) and re-transcribing Italian/Japanese/Arabic would be more faithful.
- **Reference-only symbols are never drawn (design choice, S to change).**
  `ɭ ɽ ʈʂ β ɸ ɕ …` appear only via seed/real words or a strict source
  profile. A low-probability draw group would let exotic prompts pick them,
  at the cost of re-seeding existing output.
- **Missing symbols still (M).** `ɰ`, rhotacized vowels (`ɚ`, Mandarin erhua),
  syllabic `ɻ̩`, `ʜ ʢ`, `ɱ`, `ɫ`, breathy/creaky vowels (Vietnamese ngã/nặng
  are approximated as plain pitch), implosive/click coverage beyond a few
  illustrative symbols, and the pharyngealization of *vowels* next to
  emphatics (Arabic).
- **Consistency of the script-g (S).** The pool mixes ASCII `g` and U+0261
  `ɡ` (only in `ɡʱ`, `ɡb`, click clusters). Real-lexicon authors must know
  which to write; normalizing would remove a trap.
- **Onset/coda clusters cap at 2 consonants (M)** *(known limitation)* — no
  English "str".
- **Vowel harmony, stress and word accent are not present in the real
  lexicons (M).** Real words carry no stress marks and no pitch-accent
  (Japanese) marks; `stress_pattern` only affects invented words.
- **Korean assimilation and Hindi schwa deletion (L)** *(known limitation)* —
  word-level algorithmic systems, not per-symbol rules.
- **Phonotactic audit of real words (done).** `conlang audit-lexicons`
  (see `docs/LEXICON_AUDIT.md`) flags words a profile cannot produce and
  aggregates the illegal consonant runs and missing sounds per language.
- **Profile widening from the audit, group 1 (done).** Baseline flagged
  32% of words, now 21%. Sanskrit visarga `h` and unrestricted medial codas;
  attested onset/coda clusters (`s`+stop, `ʃt`, `ts`, glide clusters, ...)
  for English, German, Polish, Italian, French, Dutch, Latin, Serbo-Croatian,
  Sanskrit, Swedish, Norwegian, Danish; coda `ʁ` no longer removed by coda
  devoicing; attested clusters now bypass the sonority check
  (`sonority.with_attested`); long/mid vowels for German, Danish, Swedish,
  Norwegian; `ʎ` for Italian; Polish `ɲ` onset; English's wrong
  "w never before a rounded vowel" restriction removed; Portuguese/Dutch
  lexicons' `r`/`ɾ` and `ʎ` aligned with their profiles.
- **Profile widening, still open (M).** Modeling limits the audit cannot
  fix with a cluster list: (a) *word-final devoicing is done* (final-only field,
  Turkish exemptions); the Sanskrit pausa restriction (only `k ʈ t p ṅ ṇ n m ḥ`
  word-finally) and other final-only coda sets could now use the same
  field via a profile setting, but no profile field exists for it yet; (b) *doubled consonants are done* (long twins for the common consonants,
  lexicons and profiles converted; still open: geminate affricates like Italian
  `tts`, geminates in `coda_profile: none` languages such as Japanese *kitte*,
  and word-initial geminates in the few languages that have them); (c) *three-consonant clusters are done* (curated triples, strict profiles only; Georgian, Hebrew,
  Hungarian and the other unreviewed languages have none yet, and 4-consonant runs like
  Polish *vzvʲ*+glide stay out of scope); (d) glide+vowel sequences written as onset clusters
  (French `bw`, Italian `pj`); (e) languages not yet reviewed (Old Norse and Icelandic done):
  Nahuatl, Mandarin, Welsh, Georgian, Korean, Ancient Greek,
  Zulu/Xhosa, Tibetan, Tamil, Hungarian, Persian, Spanish (`β ð ɣ`),
  Hindi; (f) lexicon-side slips: Danish `w`/`ɪ`, Swedish `ɧ`, Portuguese `carregar` rhotic.

## 2. Real lexicons (data)

- **Batches still to write (L).** Curated to 494 words: Dutch, French,
  German, English, Spanish, Italian, Portuguese, Latin, Russian, Polish,
  Turkish, Indonesian, Korean, Japanese, Mandarin, Hindi, Persian, Arabic,
  Hebrew, Bengali, Tamil, Icelandic, Swedish, Danish, Norwegian, Finnish, Hungarian, Serbo-Croatian,
  Malay, Swahili, Welsh, Ancient Greek, Sanskrit, Basque, Old Norse (490), Cantonese, Vietnamese (the last two generated from jyutping / Vietnamese
  spelling by rule, tones included).
  **Partly curated (only words I was confident of; the rest is left to the
  LLM gap-fill):** Yoruba (102, with its three tones), Zulu (84) and Xhosa (52)
  written toneless with click consonants, Sumerian (38), Navajo (24,
  toneless although the profile is tonal), Nama (4 -- I know too little of it
  to go further), Hawaiian (401), Georgian (169), Khmer (52, mostly numbers
  and basic nouns -- needs a native pass), Thai (190, tones written by hand -- only words whose tone
  I was sure of), Quechua (412), Tibetan (365), Mongolian (322), Nahuatl
  (246), Pama-Nyungan (61, Western Desert / Pitjantjatjara), Arawakan (49 --
  the original list only; no additions, I don't know Lokono well enough to
  transcribe hundreds of words). These need a native/linguist pass to
  finish; Tibetan is written toneless although its profile is tonal.
  Every reference profile now has at least a small curated lexicon.
  Until a language is curated the LLM fills the gaps.
- **Linguist verification (L).** Every list is a best-effort transcription to
  the modeled phoneme set, not verified. A spot-check workflow (export a
  language's list, mark corrections, re-import) does not exist.
- **One word per meaning (M).** No synonyms, register variants or polysemy;
  multi-word glosses were replaced with a single word (e.g. Turkish "get" is
  `edinmek`). Verbs are in citation form (Hindi `-naa`, Turkish `-mak`), so
  a strict copy inherits infinitive endings.
- **No inflected forms from real data (L).** Plurals, cases and conjugations
  of a copied word are invented affixes, not the source language's own
  (Dutch `-en`, Russian case endings). `word_classes` covers only citation
  shapes.
- **Vocabulary ceiling (M).** `ALL_MEANINGS` is ~496 meanings. Larger lists
  (Swadesh-207, Leipzig-Jakarta, a 1000-word core) and the unused
  `salient_vocabulary_domains` trait (seafaring, herding…) could drive domain
  vocabulary.
- **Coined words ignore word strictness (M).** On-the-fly coinage during
  translation (`translation/expansion.coin_word`) always invents; it could
  ask for the real word (curated, else LLM) when word strictness is high.
- **Deviation is random, not systematic (M).** Below strictness 1.0 a real
  word is loosened by random nearest-phoneme swaps. Regular correspondences
  (a fixed consonant-shift table per source language, applied consistently)
  would make the "different but related" vocabulary look like a real daughter
  language.
- **Blending several sources (M).** With multiple source languages each word
  is taken from one language by weight; there is no cognate blending.
- **Proper-name lexicon (S).** Names are recognized and kept/adapted, but no
  gazetteer of common real names per language.

## 3. Tones

- **Lexically specific sandhi (M)** — Mandarin 不 (bù→bú before falling) and
  一 (yī) change by word, not by tone context, so `ToneSandhiRule` cannot
  express them. Needs a per-word flag or a word-conditioned rule.
- **Sandhi scope (M).** Applied to a translation's IPA only. Not applied to
  the romanized output (pinyin would write *ní hǎo*), to `pronounce` of a
  single entry, to other output paths, or preserved through `sound_change`
  evolution. Chain grouping (3-3-3 within a prosodic phrase) is a simple
  citation-tone pairing, not phrase-structure aware.
- **Neutral tone as grammar (M).** Neutral tone is stored per word;
  nothing generates it for grammatical particles (的 了 吗) or reduplicated
  kinship terms by rule.
- **Other tone systems (M each).** No `tone_levels`/sandhi data for
  Cantonese (6 tones + sandhi), Thai (5 + tone rules), Vietnamese (6, with
  glottalized ngã/nặng), Tibetan, Yoruba, Zulu/Xhosa/Swahili (tone
  languages with their own tone-depression patterns). Only Mandarin is
  curated.
- **Contour representation (M).** Tones are single diacritics (level names).
  Chao tone letters (˥˩) / two-digit contours would represent register +
  contour properly and give TTS the actual pitch targets.
- **Tone in evolution (L).** Sound change does not model tonogenesis,
  tone splits/mergers, or sandhi becoming lexical.
- **Tone in real-based words (S).** A deviated word re-spells through the
  language's own orthography; tone-marking style interplay with pinyin-style
  spelling is only lightly tested.
- **Pitch accent (M).** Japanese pitch accent, Swedish/Norwegian tone
  accents exist as `word_accent`, but are not carried by real lexicons.

## 4. Pronunciation (TTS)

- **eSpeak tonal voice is Mandarin-only (M).** Tones work by switching to the
  `cmn` voice; the language's other sounds are approximated by Mandarin's
  inventory and the accent is Mandarin's. Alternatives: eSpeak SSML
  `<prosody>` pitch contours per vowel on the language's own (or an English)
  voice, or post-processing (PSOLA-style) an F0 contour onto any voice's
  output.
- **Per-word synthesis (M).** Sentences are voiced word by word with fixed
  silences: no sentence intonation, no stress, no coarticulation, and
  sandhi is not reflected in prosody beyond the changed tone marks.
- **Voice selection (S).** No choice of SAPI voice (only the default; the
  Chinese Huihui/Hanhan voices are installed but cannot take IPA tones) or of
  eSpeak voice; the source language's own voice (Spanish, German…) could be
  used for its real-word-heavy languages.
- **Capability model is tones-only (M).** Engines report which tones they
  voice, but not which *sounds* (clicks, ejectives, pharyngeals, breathy
  voice, word accent, length) are dropped or approximated, and warnings cover
  tones only. A per-symbol support table would let the UI flag those too.
- **Warnings are web-only (S).** The CLI `pronounce`/translate path does not
  print engine capabilities or unvoiceable-tone alerts.
- **Other engines (L).** Piper/Coqui (local neural), Azure/Google (SSML IPA
  with tone support for Mandarin/Cantonese/Thai). Kirshenbaum conversion for
  the newly added symbols (`ɸ β ɕ ʑ ɦ ɭ ɽ ʈʂ`) is approximate and unlistened.
- **Audio cache (S).** Repeated pronunciation re-synthesizes every word.
- **Untested by ear (S).** The eSpeak tone numbers were verified by output
  length and measured pitch; mid/low/neutral (33/21/11) were only length-checked.

## 5. Grammar and translation

- **Unused traits *(known limitation)* (M each).** `social_hierarchy`,
  `evidentiality_culture`, `spatial_reference`, `ritual_register`,
  `taboo_register`, `terrain_communication_distance`,
  `salient_vocabulary_domains` are extracted and stored but consumed by
  nothing; `orality_literacy` only affects evolution's orthography reform.
- **Word order not trait-linked *(known limitation)* (S).**
- **Matched-language grammar bias is partial (M).** `real_word_order`,
  `real_alignment`, `real_has_articles`, … exist for ~16 of ~50 profiles;
  `morphological_type` has no matched-language bias.
- **Translation understands three sentence shapes (L)** *(known limitation)*
  — no real parser; no agreement, no relative clauses, questions, tenses
  beyond the simple planner; no idiom generation/matching although
  `Lexicon.idioms` exists.
- **Seed examples (S)** default to NOUN and are not checked against the
  generated syllable structure; sentence-level seeds don't exist.
- **Sentence-context spelling (M).** Agreement-driven capitalization/mute
  letters and specific-word capitalization are out of scope.

## 6. Language evolution

- **Strictness does not reach evolution *(known limitation)* (M).**
  `sound_change`'s inventory recompute can drift a strict language back
  toward the generic.
- **Only sound change (L).** No grammar evolution (case loss, grammaticalization),
  lexical replacement, borrowing, semantic shift, or family-tree/dialect
  branching; history is a flat list.
- **Rules are generic, not language-specific (L).** "Dutch evolved forward
  200 years" applies the general rule set (final devoicing, cluster
  simplification, …), not Dutch's actual likely developments.
- **Evolved real words (S).** Provenance notes survive, but the original real
  word is not kept alongside the evolved form for display ("water > waːter").
- **Orthography reform is partial (M).** Only rate-driven; no
  spelling-pronunciation drift.

## 7. CLI

- **No `--tone-sandhi` (or other graded-trait) flags (S).** The trait is set
  only through the prompt classifier.
- **Lexicon coverage report (S).** A command listing, per reference language,
  whether a lexicon exists, its size and how many entries violate the
  profile.
- **Strictness/pronunciation warnings (S).** Word-vs-sound strictness
  warnings print; tone/engine warnings do not (see §4).
- **Test runtime (done).** The default `pytest` run skips the 4 tests marked
  `slow` and takes about 3 minutes (it was 13); `pytest -m slow` runs just
  those, `pytest -m ""` everything. The three trait tests call
  `generate_phonology` directly, and `test_phonology_realism.py` shares its
  default-spec inventories through a memoized `_phonology(seed)` helper, uses
  100 seeds for the "A is more common than B" comparisons and small
  vocabularies where only stress marks are checked (file: ~80 s -> ~45 s).
  What is left is spread thin (about 850 tests averaging 0.2 s, most of it
  generating 400-word languages); a smaller test-only default vocabulary would
  cut it further but reshuffles every seed-dependent fixture.


## 8. Web app

- **Untested in a browser this round (S).** The capability/warning UI was
  syntax-checked (`node --check`) and its endpoints tested, but the page was
  not exercised in a browser.
- **Missing controls (S).** No tone-sandhi trait control, no display of the
  language's tone levels/sandhi rules, no per-word audio, no engine voice
  picker, no real-based/real provenance badge per word beyond notes.
- **Lexicon browsing/editing (M).** No view, search, edit or export of a
  generated language's lexicon or of a reference language's real words.
- **Source-language weights UI (S).** Weights exist in the traits but not in
  the form.
- **Persistence and sharing (M).** Languages live in local storage files; no
  import/export of a whole language from the UI.

## 9. Engineering and data hygiene

*(All of the earlier items here are resolved; this section now records what
was done.)*

- **IPA round trip (fixed).** Generated words could contain a cluster whose
  concatenation the greedy tokenizer reads as something else (`t` + `sː` as
  `ts` + a stray `ː`; `n` + `dʒ` as `nd` + `ʒ`). `sonority.legal_onset_pairs`/
  `legal_coda_pairs` now drop within-syllable pairs that don't read back, and
  `sonority.unreadable_boundary_pairs` adds the cross-syllable ones to
  `SyllableStructure.excluded_coda_onset_boundary_pairs`.
  `tests/test_ipa_roundtrip.py` covers both and every generated lexicon.
- **Other session's edits (adopted).** `sonority.py`, `test_sentence_planner.py`
  and `test_translator.py` (seed changes forced by the pair filtering) are
  committed together with the boundary fix; the full suite passes.
- **Classifier calibration (checked).** A manual pass with `--llm anthropic`
  over eight prompts: the `tone_sandhi` trait comes out strongly positive when
  sandhi is asked for (0.8-0.9), strongly negative when it is ruled out (-0.9)
  and absent otherwise; `source_word_strictness` is high for "actual Dutch
  words" (0.9-0.95), low (0.1) for "a few invented words", and 0 when words
  are not mentioned. One remaining quirk, not new: a purely atmospheric
  prompt ("guttural desert language") makes the classifier volunteer a source
  language (Arabic, strictness 0.15).
- **Line endings (fixed).** `.gitattributes` (`* text=auto eol=lf`) keeps
  everything LF in the repository and in working copies, ending the
  LF -> CRLF warnings.
- **Suite runtime (done).** Split into a fast default run and `slow` tests;
  see section 7.
