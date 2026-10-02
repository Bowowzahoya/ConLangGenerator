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

**Verb phrase still missing:** auxiliaries and periphrastic tenses (M);
negation strategies (affix, double negation, negative verbs) (M);
evidentiality (M); serial verbs (L); valency-changing morphology (L); copula
strategies (zero, state vs identity) (S); adverb placement (S).

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

**Wiring existing traits (M each):** `evidentiality_culture`, `spatial_reference`, `ritual_register`,
`taboo_register`, `terrain_communication_distance`,
`salient_vocabulary_domains` are extracted and stored but consumed by
nothing (`orality_literacy` only affects evolution's orthography reform; `social_hierarchy` is
consumed -- it raises the probability a language rolls `honorific_you` at all, see `pronoun_gen.py`).
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
