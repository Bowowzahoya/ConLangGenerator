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

- **Spanish spirantization (decided, S).** The lexicon is now phonemic (`b d g`);
  the surface allophones `β ð ɣ` stay out of the profile, since invented words
  would place them word-initially. Revisit only with a positional-allophone
  mechanism (intervocalic-only sounds).
- **Russian palatalization gaps (mostly done).** `gʲ` added, completing the
  velar palatalized series alongside the already-modeled `kʲ`/`xʲ`. The
  hard/soft `l` contrast is now real: plain л is modeled as `ɫ` (velarized
  "dark l", its true phonetic value), distinct from the already-modeled
  palatalized `lʲ`; every lexicon word's bare `l` was reclassified via the
  real IPA tokenizer, cross-checked word-by-word against real Russian
  pronunciation, not a blind substitution. щ is now `ɕː` (always long, no
  plain short counterpart, unlike the rest of the series), replacing plain
  `ɕ` in the 5 words that use it. `ʃʲ`/`ʒʲ` were **not** added -- checked
  against real Russian phonology first: ш/ж are canonically the language's
  own "always hard," unpaired fricatives, with no phonemic soft
  counterpart to model; the original note asserting this gap was wrong,
  not the pool, so it's corrected here instead of "fixed." Doing this pass
  also surfaced one pre-existing, unrelated lexicon bug (*сильный* "strong"
  stored with a hard л where the real word has a soft one -- `docs/LEXICON_AUDIT.md`
  has the full account) and two stale `attested_*_clusters` comments in
  the profile, both fixed alongside. **Still open:** vowel reduction
  (akan'e/ikan'e) is only partly reflected in the lexicon's own IPA
  transcriptions -- the profile's `stress_driven_vowel_reduction: true`
  flag governs *generated* words, but auditing all 494 curated real words
  for whether every unstressed о/а is correctly written `ə` would be a
  further pass of the same scale as the stress/pitch-accent lexicon audit
  above, not yet done.
- **Nasal vowels in French and Portuguese (done).** The lexicons use real nasal vowels (`vã`, `bɔ̃`,
  `mɛ̃`; `sĩku`, `kõ`), French gains `ã ɛ̃ ɔ̃`. `ɑ̃` is written `ã` and `œ̃` merged into `ɛ̃`. Portuguese
  diphthongal nasals (`ãw`, `õj`) and French `œ̃` vs `ɛ̃` are still not distinguished.
- **Geminates as doubled consonants (done).** Long twins exist for the common consonants (see
  `LEXICON_AUDIT.md`); lexicons and profiles use them.
- **Reference-only symbols are never drawn (design choice, S to change).**
  `ɭ ɽ ʈʂ β ɸ ɕ …` appear only via seed/real words or a strict source
  profile. A low-probability draw group would let exotic prompts pick them,
  at the cost of re-seeding existing output.
- **Missing symbols (mostly done).** `ɰ` (velar approximant) and `ɱ`
  (labiodental nasal) added as `_REFERENCE_ONLY_CONSONANTS`; rhotacized
  schwa `ɚ` and Mandarin's own syllabic `ɻ̩` (儿/二) added to the drawable
  vowel pool, both romanizing as real Pinyin's own "er" (a deliberate
  collision, not an oversight); click coverage completed with the 5th,
  rarest real place (bilabial `ʘ`, plus its own aspirated/breathy/
  nasalized accompaniments); implosive coverage completed with the 5th
  place (uvular `ʛ`); epiglottal fricatives `ʜ ʢ` added (reusing
  `Place.PHARYNGEAL`, the closest existing place -- no dedicated
  epiglottal place exists or is needed elsewhere). All wired through
  every downstream completeness-tested table (`romanization_gen.py`'s
  three exotic styles, `ipa_to_kirshenbaum.py`); verified drawable (400
  seeds at `isolation=1.0`) and force-includable via a seed example.
  Extending `_EXOTIC_POOL`/`_VOWEL_EXTRAS` (both *drawn* groups) shifted
  downstream rng draws broadly -- re-found working seeds for every
  affected fixed-seed test (`test_translator.py`/`test_sentence_planner.py`'s
  shared nom-acc/ergative/no-features fixtures, the Latin-declension
  seed, an untoned-seed tone-roll seed, the Dutch orthography-reform
  evolve seed), same "seed-shift from new content, not a functional
  regression" pattern as every prior phoneme-pool batch. **Still open:**
  Vietnamese's own creaky/glottalized ngã/nặng phonation (needs a new
  tone-adjacent phonation-marking dimension, not just a missing symbol --
  approximated as plain pitch for now) and Arabic's coarticulatory
  pharyngealization spreading onto *vowels* next to emphatic consonants
  (a positional-allophone question, the same kind of gap Spanish
  spirantization above is deliberately left for).
- **Consistency of the script-g (done).** Every /g/ is ASCII `g` now, including `gʱ`, `gb` and the
  click clusters (`tests/test_pool_uses_ascii_g.py` guards it). The tokenizer no longer lets the
  prenasalized `ŋg` eat the start of `ŋ` + `gʱ`. IPA typed with U+0261 by a user or an LLM is not
  normalized on input yet.
- **Onset/coda clusters cap at 2 consonants (done).** Curated triples and quads for strict profiles.
- **Stress and pitch accent in real words (mostly done).** 40 lexicons carry stress marks, pitch accent or stød
  (see `LEXICON_AUDIT.md`): Japanese and Ancient Greek carry H/L pitch accent, Serbo-Croatian the full
  four-way accent on every polysyllable (151 words from a rule-consistent first pass, 233 from hand recall --
  **this second batch is this project's least reliable data**; BCMS pitch accent is lexical, not derivable
  from shape, and I could not reach an automatable source for it -- expect real per-word errors, more than the
  project's usual best-effort caveat implies). Arabic, Basque, Georgian, Hawaiian and Hindi use best-effort
  position/weight rules. Danish/Swedish/Norwegian additionally get one further real rule beyond each profile's
  shape default: a reduced unstressed final syllable (bare vowel + `l`/`n`/`r`, no vowel of its own: *vatten*,
  *fågel*, *vinter*, Danish *gammel*, *himmel*) is accent 1/stød, a genuine Common Scandinavian class, not a
  guess -- fixing this also caught a real Danish syllabification bug (coda /r/ written as a vowel symbol made
  *mor*-type words wrongly two syllables; 44 words corrected). Still open: (a) verifying the 233 Serbo-Croatian
  words against a real dictionary; (b) most Danish/Swedish/Norwegian polysyllables still use only the shape
  default -- real lexical exceptions (Swedish *anden* "duck" vs "spirit", other -el/-en/-er words that are recent
  formations, compounds, stød on polysyllabic inflected forms) are unknown; (c) fixed-pattern languages ignore
  their real exceptions (loanwords, verbs) -- an `exceptions` pass per language would refine them; (d) secondary
  stress is not marked anywhere; (e) vowel harmony is absent from the real words. Japanese and Ancient Greek's
  own remaining gaps are now closed (see `LEXICON_AUDIT.md`): Greek is 452/453 (only the phrase *dia ti* left),
  Japanese 424/454 (93%; the rest are phrases, particles, homographs and a few verbs/adjectives I don't
  confidently know). Fixing them surfaced two real bugs in `real_stress.py`, both now covered by regression
  tests: `with_greek_accent` marked a fused diphthong's offglide instead of its real nucleus (8 spellings,
  *poieō* and similar, already counted among "unmarked" so nothing previously-reported was wrong); and the
  generic offglide-fusion rule was wrongly applied to Japanese, which has none (every written vowel is its own
  mora) -- this only broke *reading* the already-correct stored marks, so the coverage number didn't move, but
  `syllable_count`/`pitch_pattern` were silently wrong for any word containing a fusable vowel sequence.
  A systematic follow-up check across every other curated language found the same fusion-rule bug applied to
  three more families that have no phonemic diphthongs at all -- Slavic (Polish, Russian, Serbo-Croatian:
  *pauk* "spider" is *pa-uk*, two syllables), Bantu (Swahili: strict open-CV structure, *kusahau* is
  *ku-sa-ha-u*, four syllables, 14 words affected), Nahuatl (a plain 4-vowel system, *maitl* "hand" is
  *ma-itl*, two syllables) -- plus two individual named exceptions where the language's general fusion rule
  is otherwise correct: Spanish *oír*/*reír*/*raíz* (a written tilde marks real hiatus, not a diphthong) and
  Swedish *nio*/*tio* "nine"/"ten" (a genuine *ni-o*/*ti-o* hiatus). All six fixed with regression tests; see
  `LEXICON_AUDIT.md` for the full list of languages checked and the ones left open (Indonesian/Malay's mixed
  diphthong-vs-hiatus facts, Persian's 2 low-confidence hits) because a blanket rule would trade one error for
  another.
- **Sanskrit's Vedic accent (declined).** Considered and rejected, not just left open: the profile already
  deliberately targets accentless Classical Sanskrit (see its own comment); the lexicon's 129 verbs are cited
  as bare roots, and real Vedic finite-verb accent is a sentence-level syntactic rule, not a property of the
  citation form, so there is no single correct mark to add. The ~365 nominal entries could in principle carry
  a real per-word Vedic accent, but that data lives in specialist dictionaries no available tool can query at
  this scale, and it belongs to a different historical layer (Vedic, not the modeled Classical register) than
  the rest of the profile -- adding it piecemeal for the handful of Rigveda-famous words I could verify (agni,
  deva, ...) would misrepresent coverage, so none was added.
- **Word-level algorithmic phonology (done for Hindi/Bengali/Korean)** *(narrowed further)* — a
  survey of every curated profile for the same shape of gap Hindi schwa deletion already
  named (a word's own real pronunciation depends on scanning its *whole* syllable sequence,
  not just one adjacent symbol, so it can't be a per-symbol romanization rule) turned up one
  close sibling, Bengali's own inherent-vowel deletion, and confirmed several other real
  candidates (Finnish consonant gradation, Turkish/Icelandic morpheme-boundary alternations,
  Arabic/Hebrew definite-article assimilation, Welsh initial mutation, Japanese rendaku) are a
  *different* kind of gap -- each needs live inflection or a cross-word/morpheme trigger this
  project's citation-form-only, no-live-morphology architecture has nowhere to hang, not a
  missing algorithm. Mandarin's neutral tone and Tibetan's diachronic coda-reduction/tone
  culmination were already in the same "real but not rule-capturable" bucket as Hindi's own
  schwa deletion (see `LEXICON_AUDIT.md`'s Ancient Greek/Danish sections' own neighbors);
  nothing new needed there.

  **Hindi schwa deletion and Bengali's own word-final counterpart are now built** (new
  `ReferenceLanguageProfile.word_level_phonology`, dispatched in `generation/word_phonology.py`,
  applied inside `word_builder.build_word` to a freshly built word's own syllable sequence,
  before stress is assigned and before any word-class affix attaches). Hindi uses the
  standard, widely-cited computational formulation (Ohala 1983; Narasimhan, Sproat & Kiraz
  2004's own "ə -> ∅ / VC_CV" rule): a word-final inherent vowel always deletes (unless it's
  the word's only vowel), and an internal one deletes when the syllable to its own left is
  itself closed. Bengali gets only the word-final half -- its own real medial pattern targets
  a genuinely different inherent vowel (/ɔ/, not schwa) and isn't documented confidently
  enough for this project's own honesty standard to assert a specific medial rule, so it stays
  open rather than guessed at. Every deletion is checked against the language's own legal
  cluster set first and skipped, not forced through, when illegal -- smoke-tested via
  `conlang generate --source-language Hindi/Bengali --strictness 1.0`: word-final schwa/ɔ
  survives almost exclusively on monosyllables (correctly never deleted, a word needs at
  least one vowel) or where the merge would be an illegal cluster.

  **Korean's own cross-syllable consonant assimilation is now built too**, reusing the same
  `word_level_phonology` dispatch with a genuinely different algorithm shape (consonant
  rewriting conditioned on a full coda/onset neighbor pair, not vowel deletion scanning for
  syllable weight): nasalization (an obstruent-stop coda before a nasal onset takes that
  nasal's own place of articulation -- real *국물* gungmul "soup" /k/+/m/ -> [ŋ]+[m]),
  lateralization (/n/+/l/ or /l/+/n/ both converge on [l]+[l] -- real *신라* Silla), and
  tensification (an obstruent-stop coda before a plain obstruent onset makes that onset tense
  -- real *학교* hakgyo "school" /k/+/k/ -> [k]+[kʼ]; real Korean also tensifies a following /s/,
  but this project's own Korean profile doesn't model a distinct tense /s/, so that one member
  of the real series stays out of reach). All three are purely phonetically conditioned (no
  morpheme-boundary tracking needed), unlike real Korean **palatalization** (*같이* gachi
  "together", from an underlying /t/+/i/ across a root+suffix boundary) -- that one is
  deliberately left unmodeled, the same "needs live morphology this project doesn't have" gap
  the wider survey above already declined for Welsh mutation/Japanese rendaku/Arabic-Hebrew
  article assimilation, not a new instance of Korean's own already-closed gap. Every rewrite is
  checked against the language's own legal onset/coda set first and skipped when illegal, same
  discipline as Hindi/Bengali's own deletion rules. Smoke-tested via real `conlang generate
  --source-language Korean --strictness 1.0`: generated lexicons visibly show all three
  patterns (tense onsets, "ŋ" codas, doubled "ll").
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
- **Profile widening: what is still open (S-M).** The audit is at ~0% (loans excluded); what remains:
  (a) glide+vowel sequences written as onset clusters (French `bw`, Italian `pj`) are modeled as
  clusters, not diphthongs; (b) geminate affricates beyond Italian `tsː`, and geminates in languages with
  `coda_profile: none` (Japanese *kitte*); (c) Basque loan clusters (`tɾ`, `fɾ`) are tagged as loans, not
  admitted; (d) Portuguese diphthongal nasals (`ãw`, `õj`) and French `œ̃` vs `ɛ̃`; (e) Sanskrit's pausa
  restriction (its lexicon holds bare stems); (f) Spanish surface allophones `β ð ɣ` are not in the profile
  (the lexicon is phonemic) -- they need an intervocalic-only mechanism; (g) lexicon slips: Swedish `ɧ`,
  Portuguese *carregar* rhotic.
- **Word-position restrictions (done).** `restricted_onset_consonants` / `restricted_initial_consonants` /
  `restricted_final_coda_consonants` / `medial_only_consonants` cover onset-anywhere, word-initial,
  word-final and both; devoicing is final-only. Not covered: an *intervocalic*-only sound.

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

- **Tag more loanwords (S).** Only 32 lexicon entries carry the `loan` tag (the flagged, obviously
  borrowed ones). Heavy-loan languages (Swahili, Malay/Indonesian, Persian, Turkish, Hindi, Japanese)
  have many more untagged Arabic/Sanskrit/Chinese/English loans; tagging them would let the audit
  hold the rest to the native phonotactics more strictly.

## 3. Tones

- **Lexically specific sandhi (done).** New `core.phonology.LexicalToneSandhiRule`
  (`gloss`, `before`, `becomes`) and `ToneSystem.lexical_sandhi`, dispatched in
  `tone_sandhi.apply_sandhi` (now takes an optional `glosses` list, one per
  `ipa_words` entry) as a second pass after the general context-sandhi one, since
  it needs to read each word's own *already* general-sandhi'd neighbor tone (the
  real, as-spoken tone a listener actually hears next). Bound by gloss identity
  ("not"/"one", this project's own invented Mandarin-sourced words have no
  Chinese characters to key on) rather than tone content, so it fires only for
  that one specific lexicon entry, never any other syllable that happens to
  share its tone. Curated on Mandarin's own profile via a new
  `lexical_tone_sandhi: [[gloss, before, becomes], ...]` field (real 不 needs one
  rule, falling->rising; real 一 needs three, covering high/rising/dipping ->
  falling), resolved the same reference-weighted, strictness-scaled "kept, not
  invented" way `tone_sandhi` is (`generation.phonology_gen.resolve_lexical_tone_sandhi`,
  its own independent rng stream so it changes no other draw sequence). Wired
  into both existing sandhi consumers: `translate_to_conlang` (a new parallel
  `gloss_parts` list, one per rendered slot) and `conlang pronounce` (though a
  single looked-up word has no following syllable to trigger it on, so this only
  matters if/when a future multi-word `pronounce` path exists). Not modeled: the
  real rule's own edge case before a *neutral*-tone syllable (genuinely
  contested/simplified differently across pedagogical sources) -- both tracked
  words keep their own unmarked citation tone there, an honest abstention, not a
  guess. Verified with unit tests (the tracked-word-only scope, citation-tone
  fallback when word-final/unmatched, all four real 一 contexts, and that the
  lexical pass really does read the post-general-sandhi tone) plus one real
  end-to-end `translate_to_conlang` test (a real strict-Mandarin-sourced
  language, seed hand-found so "not" naturally sits before a real falling-tone
  word).
- **Sandhi scope (mostly done).** `conlang pronounce` now applies
  `tone_sandhi.apply_sandhi` to a single looked-up entry's own IPA (a
  multi-syllable citation form is just an "utterance" of one word to the
  same function that already handled cross-word sandhi, so no new sandhi
  logic was needed) -- printed as its own "Pronounced (tone sandhi):"
  line only when it actually differs from the citation form, and used
  (not the bare citation IPA) for TTS synthesis, so audio reflects real
  pronunciation. Preservation through `sound_change` evolution turned out
  to already work correctly with no code change -- evolution copies a
  language's own `ToneSystem` (levels *and* sandhi rules) forward
  unchanged, and `apply_sandhi` is a pure function of whatever
  `ToneSystem` it's handed; verified with a regression test rather than
  just asserted. The web UI has no per-word "hear this entry" affordance
  at all yet (only whole-translation playback, which already gets sandhi
  via the existing `translate_to_conlang` path) -- nothing to fix there
  until that feature exists, but it should reuse the same
  `apply_sandhi([entry.ipa], tone_system)[0]` wrapping when it does.
  **Declined, not fixed:** reflecting sandhi in the *romanized*
  translation output (`TranslationResult.text`). Investigated and
  rejected for two reasons: `translate_to_english`'s own decoder does
  exact-string matching against each entry's stored citation-form
  `romanization` (`_decode_noun`/`_decode_verb`), so a sandhi-respelled
  token would silently fail to round-trip back to English -- a real
  regression, not a cosmetic one; and real published Pinyin convention is
  genuinely split on this in practice (many dictionaries keep citation
  tones in writing precisely because sandhi is a spoken-only phenomenon),
  so "fixing" it isn't even an uncontroversial correctness improvement.
  Chain grouping (3-3-3 within a prosodic phrase) remains a simple
  citation-tone pairing, not phrase-structure aware -- a genuinely
  separate, harder problem (real prosodic phrasing) left for its own pass.
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


- **Initial-only restriction for geminates (done).** Every profile that barred geminates from all onsets
  now bars them from word-initial position only (`restricted_initial_consonants`); Tamil, Nahuatl, Sumerian,
  Swahili and Hawaiian, which never barred them, still allow word-initial geminates.
