# Known limitations

Things this project **consciously does not do**: each was looked at, and
either declined for a stated reason or implemented as a deliberate
simplification. Not a backlog -- see `DEFERRED.md` for work that is simply
not done yet. Broader architecture notes live in `architecture/OVERVIEW.md`.

## Sounds and phonology

- **No positional allophones.** Spanish `β ð ɣ`, Arabic emphatic
  pharyngealization spreading onto neighbouring vowels, and any
  "intervocalic-only" sound are out of scope: the mechanism would need
  positional allophony, which the phoneme model does not have. Spanish
  lexicons are phonemic (`b d g`).
- **Vietnamese creaky/glottalized tones (ngã, nặng)** are approximated as
  plain pitch; phonation type is not a modeled dimension.
- **Reference-only symbols are never drawn at random** (`ɭ ɽ ʈʂ β ɸ ɕ …`):
  they appear only through seed/real words or a strict source profile.
  Drawing them would re-seed all existing output.
- **Russian `ʃʲ`/`ʒʲ` not added**: ш/ж are always hard, so there is no soft
  counterpart to model.
- **Portuguese diphthongal nasals (`ãw`, `õj`) and French `œ̃` vs `ɛ̃`** are
  not distinguished.
- **Sanskrit Vedic accent declined**: the profile targets accentless
  Classical Sanskrit; Vedic accent is a sentence-level rule, and its data
  sits in specialist dictionaries.
- **Rules that need live morphology are not modeled**: Finnish consonant
  gradation, Turkish/Icelandic morpheme-boundary alternations, Arabic/Hebrew
  article assimilation, Welsh mutation, Japanese rendaku, Korean
  palatalization (*같이*). Bengali's medial inherent-vowel pattern and
  Korean tense /s/ are left out because they are not documented confidently
  enough or not modeled. Mandarin neutral tone and Tibetan tone culmination
  are real but not rule-capturable.
- **Word-level phonology exists only for Hindi (schwa deletion), Bengali
  (word-final only) and Korean (nasalization, lateralization,
  tensification).**
- **Serbo-Croatian pitch accent is the least reliable data in the project**
  (233 words from hand recall). Expect real per-word errors.

## Real lexicons

- **Best-effort transcription, not linguist-verified**, written to the
  modeled phoneme set (simplified diphthongs, no unmodeled affricates).
- **One word per meaning**: no synonyms, register variants or polysemy.
  Verbs are in citation form, so a strict copy inherits infinitive endings.
- **No inflected forms from real data**: plurals, cases and conjugations of
  a copied word are invented affixes, not the source language's own.
- **Tibetan, Navajo and Zulu/Xhosa are written toneless** although their
  profiles are tonal.

## Tones

- **Sandhi is not reflected in the romanized output.** Declined: the
  English decoder matches citation-form spellings exactly, so respelling
  would break round-tripping, and Pinyin convention itself keeps citation
  tones. Sandhi is applied in pronunciation and TTS only.
- **Sandhi chains are simple citation-tone pairings**, not prosodic-phrase
  aware. Mandarin's sandhi before a neutral-tone syllable is not modeled.
- **Mandarin particles 的/了/吗 are not generated**: isolating languages have
  no analytic case/tense/aspect particles here (the only free particle is
  the yes/no question one, and it is a single invented syllable, not 吗
  specifically).
- **Other tone systems were surveyed and left without sandhi**, each for a
  stated reason: Thai (syllable-internal tone assignment), Vietnamese and
  Tibetan (no productive sandhi), Cantonese (unconditioned "changed tone"),
  Yoruba (downstep needs a register the 3-level system lacks).
- **Nguni High-tone shift is a simplification**: the rightmost High moves to
  the antepenult, without the penult conditioning or the verb tense/aspect
  interactions of the real system. Meeussen's Rule is modeled.
- **Tone evolution simplifications**: tone splits only cover `HIGH`→`LOW` and
  `RISING`→`DIPPING`; sandhi lexicalization ignores the actual neighbouring
  word and only applies to rules that rewrite the earlier syllable.
  Tonogenesis is only modeled through coda-`ʔ` loss.

## Grammar and translation

- **Translation is LLM-planned.** A sentence is turned
  into a plan (`SentencePlan`, order/case/tense/article/copula/negation/
  conjunction) by the LLM, then rendered deterministically. There is no
  real parser, and no agreement beyond
  what the plan states. Subordinate clauses (complement, relative, adverbial)
  nest to a depth of 3, deeper ones are flattened; the linking word is placed
  after the clause in verb-final (SOV/OSV) languages and before it otherwise,
  and subordinate verbs get no special form. Yes/no questions use one free particle, imperatives
  one suffix, plural one suffix (isolating languages get it as an attached
  clitic); there is no dual, gender or noun class, and vocatives are
  ordinary sentence-initial nouns. There is no idiom generation/matching (`Lexicon.idioms` exists
  but is unused).
- **Aspect and verbal mood are single suffixes** in a fixed order (aspect, tense,
  mood, agreement), chosen from illustrative label sets (two-way or four-way
  aspect; irrealis or subjunctive/conditional/potential). Auxiliaries ("have",
  "would", "is ...-ing") are never separate words. When several label
  combinations spell alike, decoding prefers the reading with the fewest
  aspect/mood labels.
- **Noun classes are illustrative**: one of five fixed systems, derived from
  the English gloss (natural gender/animacy, otherwise a hash), never stored
  on the lexicon entry and never marked on the noun. Classes reach only
  articles, adjectives and verbs (subject, and optionally object,
  agreement). A very small inventory can repeat a suffix across labels.
- **Noun-phrase features are illustrative**: the dual is one extra suffix; the
  possessive particle, possessed-noun suffix and genitive are the only
  possession strategies (no alienable/inalienable split, no agreement with the
  possessed noun); the indefinite article "a" and demonstratives are ordinary
  lexicon words coined on first use; numerals stand directly before their noun
  and there are no classifiers; adposition order is only told to the planner.
  In the fake planner a possessor name ("Bruno's") is not marked possessive.
- **Voice is a verb suffix plus planner-driven argument reassignment**: the
  agent of a passive is a "by" phrase, never an agent case; only passive,
  antipassive (ergative languages) and causative exist, one suffix each.
  Nothing checks that the planner reassigned the arguments correctly.
- **Existentials and possession clauses are planner-driven**: two strategies
  each (copula or "exist"; "have" or a dative-possessor construction). The
  renderer does not check that the planner really followed the strategy, and
  the English direction is told the strategy in the fluency prompt rather than
  parsing it.
- **Degree marking is one suffix or word per degree**, and the standard of
  comparison uses one of three strategies ("than" word, oblique case, "exceed"
  verb). Nothing checks the planner used the language's strategy; equatives and
  degree of adverbs/nouns are not modeled.
- **Classifiers and pronouns are illustrative**: six fixed classifier categories
  from small gloss lists, always directly after the numeral or demonstrative;
  pronoun number and politeness never reach the verb (agreement stays
  I/you/he/we, so `they` agrees like `he`); person suffixes can still collide
  (that is why pro-drop is switched off in such a language); the polite,
  inclusive and plural readings depend on the planner. Nothing checks that
  the planner used the language's own pronoun glosses.
- **Pronoun extras are illustrative**: a reflexive/reciprocal is a word, a voice
  suffix or an ordinary pronoun (no long-distance or emphatic reflexives);
  possessive pronouns are one word or suffix per person, not a full case
  paradigm; verb number and politeness are single suffixes triggered by the
  planner's `subject_number`/`polite` fields; object pro-drop only works with
  person object agreement. Classifier categories come from small gloss lists.
- **Sentence-context spelling** (agreement-driven capitalization, mute
  letters, capitalization of specific words) is out of scope.
- **Punctuation is dropped in translation** (see DEFERRED for the plan). Text is split into sentences on `.!?`, so an abbreviation like "Dr." splits wrongly.
- **No cost/latency guarantees for the LLM**: results depend on the model.

## Language evolution

- **Only sound change plus tone-system change and lexical replacement.** No
  grammar evolution (case loss, grammaticalization), semantic shift,
  borrowing or family-tree/dialect branching; history is a flat list.
- **Sound-change rules are generic**, not a language's own likely
  developments.

## Classifier

- **Atmospheric prompts can make the classifier volunteer a source
  language** (e.g. "guttural desert language" → Arabic, strictness 0.15).
  Known, harmless quirk.
