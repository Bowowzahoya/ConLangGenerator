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
- **Neutral tone as grammar (kinship half done).** Real Mandarin kinship
  reduplication (妈妈 māma, 爸爸 bàba, 哥哥 gēge) canonically carries its
  own real tone only on the *first* syllable, with the second surfacing
  neutral -- `word_builder.build_reduplicated_word` gained a
  `second_tone_mark` parameter (`None` keeps the original "both
  syllables share one tone" behavior for every other tonal language's
  own kinship words), and `lexicon_gen._propose_kinship_word` passes the
  language's own neutral-tone mark there whenever `ToneLevel.NEUTRAL` is
  actually in its own `tone_system.levels` (only Mandarin's own curated
  `neutral_tone: true` triggers this among currently-curated profiles).
  `LexicalEntry.tones` reflects the real pair too (`(dipping, neutral)`,
  not `(dipping, dipping)`), not just the stored IPA's own mark. No new
  rng draw added (the choice is derived, not rolled), so this needed no
  reseeding of any fixed-seed test.

  **Grammatical particles (的/了/吗) investigated, declined.** These are a
  possessive/attributive marker, an aspect/tense marker, and a sentence-
  final question particle respectively -- none of them map onto anything
  this project currently generates as its own word. Real Mandarin has no
  articles at all (`real_has_articles: false`, so "the" doesn't even
  correspond to 的, which isn't an article to begin with); this project's
  own case/tense-affix machinery is switched off entirely for isolating
  morphology (`grammar_gen.py`: `cases` stays empty when
  `morphological_type is ISOLATING`) rather than realized as separate
  analytic particle words the way real Mandarin's 了/着/过 actually are;
  and there's no modeled sentence-final question-particle mechanic at
  all. None of this project's own already-generated function words
  (`"the"`, `"not"`, `"and"`, `"be"`) are genuinely neutral-tone in real
  Mandarin either (不 and 一 specifically get their own real, non-neutral
  tone-sandhi behavior, already curated separately). Marking a particle
  neutral is the easy part; there's no particle to mark until this
  project has real isolating-language analytic grammar (a possessive
  marker, an aspect particle, a question particle) to generate in the
  first place -- a materially bigger feature than "add a tone rule,"
  closer in size to the still-open case/tense-affix architecture this
  project's own grammar generation already brackets off. Left open
  rather than forced onto an existing word that wouldn't actually be
  correct.
- **Other tone systems (surveyed and mostly resolved as not applicable;
  `tone_levels` pinned for Tibetan/Zulu/Xhosa; the one genuine
  architectural gap -- progressive tone sandhi -- fixed).** Re-examined
  all seven other tonal profiles for real, curatable
  `tone_sandhi`/`lexical_tone_sandhi` data mirroring Mandarin's own.
  Cantonese/Thai/Vietnamese/Yoruba already had real `tone_levels` curated
  (Tibetan/Zulu/Xhosa's own real High/Low register claim is now pinned
  explicitly too, rather than left to coincide with whichever stock
  2-level set `_TONE_LEVEL_SETS` happens to offer -- see each profile's
  own comment). Sandhi/lexical-sandhi stays empty for five of the seven,
  each for a real, specific, researched reason (documented in each
  profile's own comment, not silently skipped): Thai's own tone is
  syllable-internal assignment (consonant class x tone mark x syllable
  type), not inter-syllable alternation at all, outside what
  `ToneSandhiRule`/`LexicalToneSandhiRule` (both inter-syllable) can
  represent; Vietnamese and Tibetan have no productive context-
  conditioned sandhi (Vietnamese's one documented case is specific to
  *reduplication*, a different mechanism; Tibetan's tone is a historical
  reflex, not a live process); Cantonese's real "changed tone" (變調) is
  genuinely *unconditioned* by a following tone, so representing it via
  `LexicalToneSandhiRule` (which always requires a next-tone match) would
  misrepresent it -- fittingly, it's already this project's own real
  anchor case for `sound_change.py`'s sandhi-lexicalization direction,
  which models an unconditioned lexical tone fact correctly; and Yoruba's
  own downstep/local-assimilation stays uncurated, since it's either
  gradient/phonetic rather than a clean categorical `ToneLevel`-to-
  `ToneLevel` mapping, or needs a `!H` downstepped register this
  project's flat 3-level system has no category for.

  **Zulu/Xhosa's own Meeussen's Rule (the actual "tone-depression
  patterns" this bullet originally gestured at) surfaced a genuine,
  previously-undocumented architectural gap, now fixed.** Real Meeussen's
  Rule (a High tone immediately followed by another High lowers that
  *second* one to Low, H+H -> H+L, well-documented across Bantu) needs
  the *later* syllable to change based on what *precedes* it --
  `ToneSandhiRule`'s own `apply_sandhi` implementation used to only ever
  rewrite an *earlier* syllable's tone based on what *follows* it (the
  direction Mandarin's third-tone sandhi happens to need), the opposite
  direction, unable to express Meeussen's Rule at all. Fixed with a new
  `ToneSandhiRule.target: Literal["before", "after"] = "before"` field
  (the default preserves every existing rule's own exact behavior):
  `"before"` rewrites the earlier syllable (Mandarin's own shape),
  `"after"` the later one (Meeussen's Rule's own shape). `apply_sandhi`
  now branches on it; `ReferenceLanguageProfile.tone_sandhi` accepts an
  optional 4th `target` element (`[high, high, low, after]` is Zulu/
  Xhosa's own curated Meeussen's Rule, now real, reachable, curated data,
  not a disclosed gap); `resolve_tone_sandhi` parses it; `sound_change.py`'s
  own merger-remap and sandhi-lexicalization mechanisms were both updated
  to be target-aware (a merger's degenerate-rule check now looks at
  whichever field a rule's own `target` actually rewrites; lexicalization
  stays restricted to `target="before"` rules only, since freezing a
  `target="after"` rule would need freezing a *different* word's own
  *first* syllable, a materially different mechanism this batch didn't
  build). Real Nguni High-tone shift/spread -- a positional
  *displacement* of a tone onto a later syllable, not a same-position
  substitution at all -- stays uncurated: `target` alone doesn't solve
  it, an honest, still-open gap, a materially different mechanism from
  what this batch fixed.
- **Contour representation (done).** `ToneLevel`/`TONE_DIACRITICS` (one combining
  mark per category) stay this project's own *stored*, phonemic representation --
  unchanged, since that's what a word's IPA is actually built/read/romanized from
  everywhere else. New `core.phonology.TONE_CONTOURS` (`ToneLevel` -> real Chao
  (1930) pitch-level digits, 5=highest/1=lowest -- Standard Mandarin's own four
  tones are exactly 55/35/214/51 in this convention) and `chao_letters()` (converts
  those digits into the real IPA tone-letter bars, e.g. `"51"` -> `"˥˩"`) give a
  separate, phonetically fuller *display*/synthesis view derived from the same
  stored tone, not a replacement for it. This data already existed, just privately
  and only for eSpeak (`speech/tts.py`'s own `_ESPEAK_TONE_NUMBERS`, "verified by
  synthesizing each and comparing lengths/pitch against the pinyin voice") --
  refactored to source from the new canonical `TONE_CONTOURS` instead of
  duplicating it, so eSpeak's own real pitch targets and the new human-readable
  display share one real fact. `speech/reader.py`'s `describe()` (the CLI
  `conlang pronounce` command's own text output) now appends a
  `Tone contour: ˥˩ (51)`-shaped line, one pair per tone-bearing syllable, only
  when the word actually has tones. **Not done:** exposing per-language
  `tone_levels` with their own contour in the web UI (currently just a bare
  `tonal: true/false` badge) -- backend data is trivial to add
  (`TONE_CONTOURS`/`chao_letters` already do the work), but showing it needs new
  frontend surface, not just wiring existing data, so it's left as a natural,
  disclosed next step rather than built speculatively here.
- **Tone in evolution (done -- detonalization, tonogenesis, tone splits,
  tone mergers, sandhi lexicalization).** `sound_change.evolve_language`
  used to always copy a language's own `ToneSystem` forward unchanged; it
  now models five directions a language's own tone *system* can genuinely
  change during evolution, checked in a fixed order (detonalization, then
  merger, then split, then sandhi lexicalization, then -- only for an
  already-non-tonal language -- tonogenesis), each its own single
  whole-language roll (not a rate applied per position the way the six
  gradient segmental rules are -- tone contrastiveness is systemic, not
  gradient: once a language has tone, every syllable carries one).
  **Detonalization** (a tonal language loses
  tone): accelerated by positive `contact_intensity`, the same real
  mechanism behind this project's own already-curated Swahili fact
  (`tonal: false`, attributed to centuries of sustained Arabic/trade-
  contact pressure) -- now reachable as a genuine transition, not just a
  starting fact. **Tonogenesis** (a non-tonal language gains tone):
  modeled via the one mechanism this project's own phoneme/coda machinery
  can actually detect -- real coda-glottal-stop loss, the same pathway
  behind Vietnamese's own historical tone origin (Haudricourt 1954): a
  word's own coda `ʔ` (word-final, or before a consonant -- never
  intervocalic, which is an onset under maximal-onset, not a coda) is
  removed and its own vowel surfaces `LOW`; every other vowel surfaces
  the real cross-linguistic elsewhere case, `HIGH`. Structurally gated: a
  language with no word anywhere in its own current lexicon that has a
  qualifying coda `ʔ` has no raw material for this pathway at all,
  regardless of `years`. **Tone merger** (two of a tonal language's own
  real pitch categories collapse into one): real Middle Chinese's own
  "entering" tone category dispersing into modern Mandarin's other tones
  is this project's own citable case; `NEUTRAL` is never a merger participant, and any
  existing `ToneSandhiRule`/`LexicalToneSandhiRule` mentioning the
  now-gone category is remapped onto the survivor or, if that makes the
  rule map a tone to itself, dropped -- never left dangling. **Tone
  split** (a tonal language's own existing categories partly divide by
  register): the already-tonal counterpart of tonogenesis, via the same
  real onset-voicing-loss mechanism behind Middle Chinese's own 4-tone-
  to-8-tone register split -- a syllable-initial voiced obstruent onset
  devoices, and its own vowel's tone moves to the real lower-register
  partner this project's simplified `ToneLevel` enum actually has for it
  (`HIGH`->`LOW`, `RISING`->`DIPPING`, both already-documented category
  pairs, not invented ones); `FALLING`/`MID` have no defensible partner
  in this project's own simplified inventory and are left with their
  onset devoiced but their tone unchanged, an honest partial coverage
  rather than a fabricated pairing. Structurally gated the same way
  tonogenesis is: no word with a real qualifying voiced onset before a
  register-eligible tone, no raw material, regardless of `years`.
  **Sandhi lexicalization** (a live, general `ToneSandhiRule` loses its
  own conditioning and freezes into affected words' own citation tones,
  the rule itself dropping out): real Cantonese "changed tone" (變調) --
  a fossilized reflex of earlier, once-productive tone sandhi a modern
  speaker can no longer predict from any live rule, just memorizes per
  word -- is this project's own citable anchor, hence the slowest
  half-life of all five mechanisms. Only a general `sandhi` rule is ever
  a candidate (`lexical_sandhi` is already word-specific, nothing to
  "become" lexical); a word whose own *last* tone-bearing syllable (the
  same position `generation.tone_sandhi.apply_sandhi` itself already
  conditions general sandhi on) currently carries the chosen rule's
  `before` permanently becomes `becomes`, and the rule itself is dropped
  from the language's own `sandhi` once it fires. Deliberately
  unconditioned by what actually follows each word (this project's
  per-word storage has no memory of a word's own historical neighbors to
  check against) -- an honest simplification, not a claim that every
  affected word really did sit next to the trigger tone every time, but
  a fair telling of what "losing the conditioning environment" itself
  means for a rule that no longer exists to check it. Structurally gated
  the same way tonogenesis/split are: no word with a qualifying last
  tone, no raw material, regardless of `years`. Smoke-tested against real
  generation, all five directions (isolated, ʔ-coda-bearing base
  languages gaining a real high/low tone contrast; strict-Mandarin-sourced
  languages losing theirs under high contact, merging DIPPING into HIGH,
  or freezing a DIPPING+DIPPING sandhi rule into affected words' own
  citation tones; strict-Thai/Zulu/Yoruba-sourced languages splitting
  real voiced-onset syllables into a lower register while devoicing the
  onset that conditioned it; strict-Vietnamese- and strict-Cantonese-
  sourced languages -- Cantonese being this mechanism's own real anchor
  case -- each freezing one of their own real sandhi rules the same way).

  That closes out the original tones survey in full.
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
