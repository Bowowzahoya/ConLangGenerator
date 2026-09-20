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
- **Phonotactic audit of real words (M).** No report of which curated words
  violate their own profile's syllable structure (clusters, restricted
  onsets); useful for spotting transcription errors.

## 2. Real lexicons (data)

- **Batches still to write (L).** Curated to 494 words: Dutch, French,
  German, English, Spanish, Italian, Portuguese, Latin, Russian, Polish,
  Turkish, Indonesian, Korean, Japanese, Mandarin, Hindi, Persian, Arabic,
  Hebrew, Bengali, Tamil, Icelandic.
  **Partly curated (only words I was confident of; the rest is left to the
  LLM gap-fill):** Quechua (412), Tibetan (365), Mongolian (322), Nahuatl
  (246), Pama-Nyungan (61, Western Desert / Pitjantjatjara), Arawakan (49 --
  the original list only; no additions, I don't know Lokono well enough to
  transcribe hundreds of words). These need a native/linguist pass to
  finish; Tibetan is written toneless although its profile is tonal.
  Profiles with no lexicon yet: Ancient Greek, Basque, Cantonese, Danish,
  Finnish, Georgian, Hawaiian, Hungarian, Khmer, Malay, Nama, Navajo,
  Norwegian, Old Norse, Sanskrit, Serbo-Croatian, Sumerian, Swahili, Swedish,
  Thai, Vietnamese, Welsh, Xhosa, Yoruba, Zulu.
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
- **Full-suite runtime (S).** The suite takes 5–9 minutes; slow tests could be
  marked and split so a fast subset runs by default.

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

- **`tests/test_ipa_roundtrip.py` (other session).** Failing on a generator
  bug (stray length mark, e.g. `dʒ` + doubled) — owned by that session, not
  fixed here.
- **Uncommitted edits by another session** (`sonority.py`,
  `test_sentence_planner.py`, `test_translator.py`) were deliberately left
  alone.
- **Classifier calibration (S).** The new `tone_sandhi` dimension and the
  word-strictness field are prompt-engineered and only unit-tested against a
  stub; a manual pass with `--llm anthropic` is still needed.
- **Line endings (S).** Git warns about LF→CRLF on many files; a
  `.gitattributes` would settle it.
