# Architecture overview

Reflects the code as it exists after the first generation/translation slice.
Update this alongside future structural changes (per AGENTS.md).

## `core/` -- immutable domain models (pydantic, `frozen=True`)

All mutation-shaped operations return a new instance (`model_copy` /
`with_*` methods); nothing here is mutated in place.

- **`phonology.py`**: `Consonant` (place/manner/voicing, plus `ejective`/
  `aspirated`/`pharyngealized`/`long`/`palatalized`/`breathy`
  secondary-articulation and length flags -- `breathy` models
  Hindi/Bengali-style murmured voice, e.g. `"bʱ"`, the 4th member of a
  voiceless/voiceless-aspirated/plain-voiced/breathy-voiced stop series),
  `Manner` including `LATERAL_AFFRICATE` (Nahuatl's own `/tɬ/`, its one
  symbol living in `phonology_gen.py`'s `_EXOTIC_POOL` alongside
  implosives/clicks -- treated as a normal obstruent everywhere sonority/
  onset-legality/coda-devoicing already special-case `AFFRICATE`).
  `Vowel` (height/backness/rounding, plus `long`, `diphthong`, and
  `nasalized` -- Portuguese/French/Hindi-style, e.g. `"ã"`; a diphthong
  or nasalized vowel is its own atomic, multi-character `ipa` symbol,
  classified by its *onset* quality's (for diphthongs) or plain
  height/backness/roundedness (for nasalized vowels) values, the same
  pattern already used for affricates/long vowels/geminate consonants;
  both are excluded from `word_builder.py`'s kinship-reduplication filter
  as "marked, not simple" sounds, same treatment as every other secondary
  articulation) -> `PhonemeInventory`. Pre-aspiration (Icelandic-style
  `/ʰp ʰt ʰk/`) reuses the existing `aspirated` flag rather than adding a
  direction-specific one -- a deliberate simplification, since the flag's
  one behavioral consumer (reduplication's marked-sound exclusion) treats
  it direction-agnostically, and gets its own independently-gated
  `_PRE_ASPIRATED_GROUP` in `phonology_gen.py` (post- and pre-aspiration
  are different typological choices a language makes, not variants of
  one feature, so a language can roll either, both, or neither).
  `ToneSystem` (enabled levels + combining diacritics). `SyllableStructure`:
  onset/coda size limits, onset/coda-cluster allowlists, a coda-consonant
  allowlist (`allowed_coda_consonants`, `None` = unrestricted), an
  *independent* coda-consonant blocklist on the final position only
  (`excluded_coda_consonants` -- e.g. voiced obstruents for a
  final-devoicing language; orthogonal to the allowlist rather than
  reusing it, so a "sonorant-only coda" language and an "unrestricted but
  devoicing-constrained" one stay distinguishable), and
  `is_valid_syllable()` -- the one phonotactics check used everywhere a
  word is validated.
- **`romanization.py`**: `RomanizationRule` (IPA fragment -> Latin) can be
  conditioned two different, non-interchangeable ways: `following`/
  `preceding` -- a tuple of tags that must intersect the immediate
  neighbor's own tag set, either an exact ipa symbol (Mandarin pinyin
  drops the umlaut on /y/, spelling it "u" instead of "ü", specifically
  after j/q/x/y) or a computed class (`vowel`/`consonant`/`boundary`/
  `front_vowel`/`back_vowel`/`long_vowel`/`short_vowel` -- French/Italian/
  Spanish spell a consonant differently before a front vs. back vowel,
  e.g. "g" before "e"/"i" but "ge" before "a"/"o"/"u" to keep it soft;
  Dutch/German double a following onset consonant specifically after a
  short vowel, "zitten" vs. "zaten"); or `syllable` -- a tuple of
  `syllable_open`/`syllable_closed`, this symbol's own structural position
  (not a neighbor's), for languages that mark vowel length by syllable
  weight (Dutch: "vuur" /vy:r/ closed vs. "vuren" /'vy:rən/ open, doubled
  letter vs. single). `RomanizationScheme.apply()` greedily rewrites
  longest-ipa-fragment first (so multi-symbol sequences like affricates
  match before their parts), resolves whichever condition each rule
  specifies against a scheme's `vowel_symbols`/`legal_onset_clusters`/
  `vowel_backness`/`vowel_length` (plain string/tuple data, supplied by
  whoever builds the scheme -- `core/` has no phonological knowledge of
  its own; syllable openness itself is computed via the maximal-onset
  principle: a single following consonant, or a legal onset cluster,
  before the next vowel means *this* syllable is open, anything else
  closed), and NFC-normalizes the result so accented output matches what
  a human would type or paste. When several of a symbol's rules match a
  position, the more specific one wins (an exact-symbol match beats a
  class match; matching on more conditions beats fewer); when multiple
  rules *tie* at the winning specificity, `RomanizationRule.weight`
  breaks the tie via a reproducible weighted pick, keyed on a stable
  `hashlib`-derived seed from `(ipa_text, token index)` rather than an
  externally threaded `rng` -- real French `/o/` genuinely is "o"/"au"/
  "eau" depending on the specific word, with no phonological rule to
  predict which, so this models genuine spelling alternatives, not just
  a tie-break of last resort. Reusing `translation/expansion.py`'s own
  `_derived_seed` pattern (not Python's own randomized-per-process
  `hash()`) keeps `apply()` a pure function of `ipa_text` for a given
  scheme, which `sound_change.py`'s reform-detection logic depends on
  (it calls `apply()` twice -- current vs. pre-reform scheme -- and
  compares the results). `SyllableBoundaryMarker.DIAERESIS` is the one
  exception to "the marker's own value is the literal inserted text" --
  real French tréma (Noël, naïve) modifies the *second* vowel's own
  letter instead of inserting a character between the two, so `apply()`
  special-cases it. See its own module docstring for the full reasoning,
  and `reference_languages/`'s French/Mandarin profiles for worked,
  non-Dutch examples of each condition type -- French's own profile is
  also the most thoroughly curated example of weighted alternatives (its
  real `/o/`/`/ɛ/`/`/s/`/word-final-`/e/` alternations) alongside
  English's schwa (`/ə/`, spelled with almost any vowel letter depending
  on the word: about/item/lemon/focus/pencil). `JointSpelling`
  (`onset_nucleus_spellings`/`nucleus_coda_spellings` on both
  `RomanizationScheme` and `ReferenceLanguageProfile`) is a separate,
  narrower mechanism for the cases `following`/`preceding` conditioning
  *can't* reach: a real convention that consumes two adjacent phonemes'
  letters at once because *neither* phoneme's own independent spelling
  survives in the result (real French `/w/`+`/a/` -> "oi" -- French's own
  earlier `following=("a",)`-conditioned rule on `/w/` alone was actually
  a bug, since it only overrode `/w/`'s own slot while the following
  `/a/` still appended its own separate "a", wrongly producing "moia"
  instead of real "moi"). `apply()` resolves which positions emit a
  joint spelling and which are consumed by a preceding one in a single
  left-to-right pass, checking onset+nucleus before nucleus+coda at each
  position -- a vowel already claimed by its preceding onset therefore
  never also tries to claim its own following coda, which is the whole
  precedence rule, no separate conflict check needed. Deliberately
  pairwise, not a combined onset+nucleus+coda mechanism (same reasoning
  as the phonotactic restrictions below): real conventions that *look*
  three-way -- English "-ight" -- usually decompose into one symbol's
  own conditioning (`/aɪ/` before `/t/`), and there's no verified
  non-decomposable three-way case motivating a genuinely fused
  mechanism.

  `OrthographyCategory` (same module) names a reusable orthography
  *typology*, not a full per-language rule set: how an otherwise-exotic
  sound gets spelled (`ExoticSymbolStyle` -- digraph, single Latin-
  Extended letter, or a "monoletter" shallow/phonemic system in the
  spirit of Finnish/Swahili); whether/how vowel length is marked
  (`VowelLengthStrategy` -- doubling, macron, colon, English-style
  trailing silent-e, or none) plus the independent
  `short_vowel_consonant_doubling` flag; how tone (if any) surfaces
  (`ToneMarkingStrategy` -- inline diacritic, a postposed digit or
  letter, or unmarked); whether/how a vowel-initial syllable
  following a vowel-final one gets a separator (`SyllableBoundaryMarker`
  -- none, apostrophe, or hyphen; Pinyin's own real "Xi'an" vs. "Xian"
  rule); and whether a phonemically long/geminate consonant
  (`core.phonology.Consonant.long`) doubles its own letter
  (`consonant_gemination_marked`, a bare bool -- unlike vowel length
  there's no real cross-linguistic variety in *how* gemination is
  spelled, doubling is the near-universal convention across
  Italian/Finnish/Japanese/Hungarian/Estonian alike; distinct from
  `short_vowel_consonant_doubling`, which *derives* doubling from a
  neighboring short *vowel* rather than the consonant's own length).
  These six axes are genuinely independent -- `romanization_gen.py`'s
  `_CATEGORIES` holds ten named *anchor* instances for real, attested
  combinations (`germanic-doubling-style`, `wade-giles-style`,
  `pinyin-style`, `silent-e-style`, `gemination-style`, etc. --
  `pinyin-style` and `wade-giles-style` are deliberately two different
  anchors, since real Pinyin and Wade-Giles are two different, both-real
  romanizations of the *same* language, differing specifically on tone
  marking), useful as exact, keyword-forceable targets and as what a
  `ReferenceLanguageProfile` can point at, but nothing restricts a
  *generated* language to one of those fixed bundles: absent a force or a
  reference/prompt match, each axis is rolled on its own
  (`_roll_independent_axes`), so e.g. Dutch/German-style vowel-length
  doubling and Wade-Giles-style postposed-digit tone marking -- two
  different anchors' axes -- can and do co-occur. `apply()` branches
  directly on three of the six: `tone_strategy` (a tone mark riding a
  vowel's decoration is buffered and flushed once that vowel's own
  syllable coda ends, when the strategy is postposed -- reuses the same
  maximal-onset coda-run split `syllable_open`/`syllable_closed` is
  computed from); `vowel_length_strategy == SILENT_E` (the same
  deferred-buffer mechanism as postposed tone, scheduling a literal "e"
  for a vowel tagged `"long"` in `vowel_length` that lands in a closed
  syllable); and `syllable_boundary_marker` (immediate, not deferred --
  emitted whenever a vowel token's immediately preceding token was also a
  vowel, a hiatus specifically for schemes that don't have that sequence
  registered as one of their own diphthongs -- `core.romanization.SyllableBoundaryMarker`'s
  own docstring explains why a registered diphthong, itself an atomic
  multi-character symbol, never gets mistaken for one). The remaining three axes
  (including `consonant_gemination_marked`) are realized purely as
  generated `RomanizationRule`s (`romanization_gen.py`'s
  `_generate_length_rules`/`_generate_doubling_rules`/
  `_generate_gemination_rules`), so `apply()`'s matching logic itself
  never needs to know about them -- `_generate_gemination_rules` in
  particular needs no syllable-conditioning at all (unlike vowel-length
  doubling), since a geminate consonant is its own distinct `ipa` symbol
  and is long everywhere, not just in a closed syllable. Deliberately
  decoupled from `phonology.py`'s tone vocabulary: `tone_markers` is
  keyed by the literal combining-mark character, not `ToneLevel`, so this
  module never imports tone semantics -- see its own docstring.

  `RomanizationScheme` stores every one of a category's axes directly
  (`vowel_length_strategy`/`short_vowel_consonant_doubling`/
  `exotic_symbol_style`/`syllable_boundary_marker`/
  `consonant_gemination_marked`, alongside `tone_strategy`/
  `tone_markers`), not just the cosmetic `category_name` label -- so
  `evolve_romanization` can reconstruct the *exact* category that built a
  scheme (`_category_from_scheme`) rather than inferring an approximation
  from which symbol happens to have which letter, the way an earlier
  version of this design did.

  `OrthographyForce` (same module) is the explicit, deterministic
  override channel -- same spirit as `core.spec.GenerationSpec`'s
  `force_isolated`/`force_high_altitude`/`force_tonal`. `style` picks one
  of `_CATEGORIES`' named anchors outright (no `rng` involved, a
  `ValueError` if misspelled); any other field on it overrides just that
  one axis on top, so forced axes compose freely across different named
  anchors (the CLI's `--orthography-style`/`--exotic-symbol-style`/
  `--vowel-length-style`/`--short-vowel-doubling`/`--tone-style`/
  `--syllable-boundary-marker`/`--consonant-gemination-marked` flags,
  see `docs/CLI.md`). Two softer, probabilistic signals can also steer the
  roll, in order: a matched `ReferenceLanguageProfile`'s own declared
  `orthography_category`, then `TraitProfile.requested_orthography_style`
  -- a style name the prompt classifier extracts directly from wording
  like "mark tone with a number after each syllable, Wade-Giles style".
  Neither is a guarantee; only `OrthographyForce` is.
- **`grammar.py`**: `GrammarProfile` -- word order, morphological type,
  alignment, articles/copula/adjective-position flags, case labels, plural
  suffix. `uses_root_and_pattern: bool` + `templates: tuple[WordTemplate, ...]`
  for Semitic-style templatic morphology -- deliberately **orthogonal** to
  `morphological_type`, not a 5th value on that enum: synthesis (morphemes
  per word) and concatenative-vs-non-concatenative combination are
  different typological axes (Arabic is fusional *and* root-and-pattern at
  once; see `generation/root_pattern.py`). `WordTemplate.skeleton` is a
  sequence where `"C"` consumes the next root consonant in order and
  anything else is a literal ipa symbol (that template's own fixed vowel/
  affix). `word_classes: tuple[WordClass, ...]` + `word_class_deviation_rate`
  -- real, *phonologically live* citation-form paradigms (Latin's noun
  declensions, French's verb conjugations, Swahili's noun-class prefixes),
  see `generation/word_class_gen.py`'s own section below for the mechanism
  -- unlike `cases`/`plural_suffix` just above, this pair has a real
  consumer. Typed value objects only, no rule engine.
- **`lexicon.py`**: `LexicalEntry` (form + glosses + POS + tones + `root`
  -- the consonantal root a templatic word was derived from, `None`
  otherwise -- + `word_class`, the name of the `WordClass` a word was
  assigned at coinage, or `None`), `Lexicon` (entries + idioms, with
  case-insensitive `by_gloss`/`by_form` lookup, both NFC-normalized on the
  form side).
- **`traits.py`**: `TraitProfile` -- an LLM-classified, graded, *bipolar*
  (`-1.0 to 1.0`) reading of a free-text prompt against a broad set of
  factors that shape real languages (terrain, community structure, contact
  history, culture, aesthetics; non-human/anatomy factors excluded by
  design). `0.0` means "no textual evidence either way -> use the
  world-typical base rate," never a separate randomization step. A
  positive value *is* the probability of the named pole (up to
  near-certainty at `1.0`); a negative value is evidence for its
  *opposite* (down to near-impossibility at `-1.0`) -- see
  `generation/trait_bias.py`. Neither direction is capped short of its
  extreme; the safety valve is the classifier's calibration (rarely
  reporting values near +-1.0), not a mathematical ceiling -- see
  `generation/prompt_classifier.py`. `GRADED_TRAIT_FIELDS` lists the float
  fields; a handful are consumed by generation today (see `generation/`
  below), the rest are extracted and stored for future use.
  `source_languages` feeds `generation/reference_languages/` (milestone
  5). `salient_context` is a free-text catch-all for anything the
  classifier notices that doesn't map to a named field -- consumed today
  only as extra flavor context in word-coinage prompts.
- **`spec.py`**: `GenerationSpec` -- the resolved generation request:
  `prompt`, `seed`, `traits: TraitProfile` (LLM-inferred; a confident
  reading behaves close to a guarantee in either direction, but it's still
  inference from prose), `force_isolated`/`force_high_altitude`/
  `force_tonal` (explicit CLI flags only, default `False`) -- a
  structurally separate, unconditional channel that bypasses the
  probabilistic path entirely regardless of the prompt or the classifier's
  assessment -- and `seed_examples: tuple[SeedExample, ...]` (milestone 5,
  also CLI-only/explicit): literal user-supplied words that must appear
  verbatim in the lexicon, always fully resolved (IPA filled in) by the
  time this reaches `generate_language`. These channels are deliberately
  kept apart in code and naming.
- **`language.py`**: `Language` -- the aggregate root (phonology + syllable
  structure + tone system + romanization + grammar + lexicon + spec +
  history log). `with_new_words()` / `with_new_idiom()` are the only
  mutation-shaped operations, both append to `history`.

## `llm/` -- provider-agnostic LLM access

- **`base.py`**: `LLMClient` protocol, `LLMRequest`/`LLMResponse`. Nothing
  outside this package imports a specific SDK.
- **`fake_client.py`**: `FakeLLMClient`, the default everywhere. Reads
  `request.metadata["fake_strategy"]` (`choose_index`, `passthrough`,
  `trait_profile`, `guess_ipa`, or generic) to fabricate a deterministic
  response without guessing at prompt semantics -- `guess_ipa` is a crude
  letter-by-letter respelling used by `generation/seed_examples.py`.
- **`anthropic_client.py`**: `AnthropicClient`, a thin wrapper -- only
  touched when `--llm anthropic` is selected.
- **`cache.py`**: `CachingLLMClient` -- content-addressed cache (hash of
  model/system/prompt/params) persisted as one flat JSON file.
- **`cost_tracker.py`**: `CostTracker` (appends usage to a JSONL ledger,
  `summarize()`) and `CostTrackingLLMClient`, a decorator.
- **`pricing.py`**: hardcoded $/token table, `DEFAULT_MODEL` (cheapest
  current model).
- **`factory.py`**: `build_llm_client()` assembles
  `cache(cost_tracker(real_client))` -- cache outermost so a cache hit is
  never billed.

## `storage/` -- persistence abstraction

- **`base.py`**: `LanguageRepository` protocol -- whole-`Language`
  `save`/`load`/`list`/`exists` only, deliberately no fine-grained CRUD.
- **`yaml_backend.py`**: `YamlLanguageRepository` -- one directory per
  language slug, split into `meta.yaml`, `phonology.yaml`, `romanization.yaml`,
  `grammar.yaml`, `lexicon.yaml` for hand-inspection/diffing. The only
  backend today; a future `sql_backend.py` would implement the same
  protocol.

## `generation/` -- seeded, deterministic-first pipeline

Everything here is a pure function of a `random.Random` seeded from
`spec.seed` plus the `GenerationSpec`, except the one LLM call per word
(picking among pre-built candidates).

- **`word_builder.py`**: `build_syllable()`/`build_word()` -- the only code
  that assembles IPA strings, always obeying `SyllableStructure` by
  construction (never generates then validates). Phoneme selection is
  weighted by each candidate's `prevalence` rather than uniform, so common
  phonemes show up more often *within* words, not just more often in
  inventories (the schwa-in-English effect). On top of that generic
  weight, `SyllableStructure.onset_symbol_multipliers`/
  `nucleus_symbol_multipliers`/`coda_symbol_multipliers` -- resolved once
  per language in `phonology_gen.py`'s `_resolve_position_multipliers`
  from a matched profile's own `{onset,nucleus,coda}_frequency_tiers` --
  let `weighted_choice()` (and `_cluster_weight()`) apply a *per-position*
  strictness-graded multiplier on top: the same symbol can be common in
  one position and rare in another for a given language (real Dutch `/x/`
  is a rare onset -- chaos, chemie -- but one of the most productive codas
  via "-cht"/"-acht"), which a single flat `prevalence` value can't
  express. Curated by word-*type* productivity, not token/corpus
  frequency, since this project generates one word per meaning rather
  than running text -- those two measures diverge sharply for closed
  function-word classes (real English `/ð/` is everywhere in running text
  purely via "the/this/that/..." but is one of the smallest onset classes
  by word-type count). `build_word` picks one
  front/back harmony class per word up front when `vowel_harmony` is set
  and threads it into every syllable, with a small leak probability
  (central vowels stay harmony-neutral); an optional `size_bias`
  ("small"/"big") layers a further soft preference for close/open vowel
  height on top (Sapir 1929 size sound symbolism). `build_reduplicated_word()`
  is a separate, simpler path for the mama/papa kinship pattern (Jakobson
  1960) -- one onset restricted to a manner class, repeated twice,
  deliberately bypassing `SyllableStructure` since it isn't a phonotactic
  rule; candidates exclude every marked-articulation flag
  (`ejective`/`aspirated`/`pharyngealized`/`long`/`palatalized`), since
  the convergence is specifically about simple, unmarked sounds.
- **`sonority.py`**: `sonority(consonant) -> int`, derived from
  `Consonant.manner` (stops/affricates < fricatives < nasals < liquids <
  glides) rather than stored per-phoneme. `is_legal_onset_cluster()`/
  `is_legal_coda_cluster()` implement the sonority sequencing principle
  (rising toward the nucleus, falling away from it), plus the documented
  cross-linguistic exception for word-initial /s/ + voiceless stop.
  Onset legality additionally requires the first member be an obstruent
  (stop/affricate/fricative) -- a bare rising-sonority check would also
  accept nasal+liquid (e.g. `nr-`), cross-linguistically rare/marked as a
  word-initial cluster and not attested in any of `reference_languages`'s
  profiles -- and excludes a coronal stop followed by a coronal lateral
  (`tl-`/`dl-`), the well-documented cross-linguistic gap despite
  satisfying rising sonority (narrower than a blanket same-place rule,
  which would wrongly exclude real clusters like `sn-`/`sl-`).
  `legal_onset_pairs()`/`legal_coda_pairs(consonants) -> tuple[(str,
  str), ...]` compute every legal pair within a consonant set once -- the
  single shared source for this, called by `phonology_gen.generate_phonology`
  (initial generation), `sound_change._recompute_syllable_structure()`
  (post-evolution recomputation), and (onset side only) `romanization_gen.py`
  (which pairs let `RomanizationScheme` treat a whole cluster as the
  *next* syllable's onset when resolving vowel-length context).
  `thin_cluster_pairs(rng, pairs, contact_intensity) -> tuple[(str,
  str), ...]` then thins that full sonority-legal closure down to a
  sparser, gappier subset via an independent per-pair draw -- real
  languages don't use every combinatorially-legal cluster their inventory
  could produce -- always keeping at least one pair so a language that
  rolled cluster support at all never silently ends up clusterless.
  `contact_intensity` lowers the survival rate (heavy contact/creolization
  favors simpler phonotactics, the same mechanism `sound_change.py`'s
  cluster-simplification rule already models on the evolution side), via
  the shared `biased_probability` helper. Both `phonology_gen.py` and
  `sound_change.py` apply this thinning identically, so a language's
  cluster inventory can't inconsistently "un-thin" back to the full
  closure whenever sound change recomputes structure.
- **`ipa_tokenizer.py`**: `tokenize(text, known_symbols) -> list[(symbol,
  decoration)]` -- greedy longest-match against a known symbol set (like
  `RomanizationScheme.apply`), decoration-aware: trailing combining marks
  (tone diacritics) stay attached to the symbol they modify instead of
  being dropped, so a word can be pulled apart and reassembled without
  losing information. `symbols_only()` is the simpler "which phonemes
  appear" variant. Shared between `phonology_gen.py` (seed-example
  phoneme floor) and `sound_change.py` (full word rewriting).
- **`trait_bias.py`**: `biased_probability(base_rate, strength) -> float` --
  the single place "graded trait -> probability" logic lives. Bipolar:
  `strength=0` returns `base_rate` unchanged; `strength=1` reaches
  certainty (`1.0`); `strength=-1` reaches impossibility (`0.0`), via a
  steeper negative slope than positive (a rare event has little room to
  get rarer, a lot of room to get more common -- the correct way to bound
  a bipolar interpolation into `[0, 1]`, not an inconsistency). The
  strength *is* the intended probability -- there is no mathematical
  ceiling in either direction; the classifier is what's expected to keep
  reported strengths near +-1 rare (see `prompt_classifier.py`). A
  `force_*` flag guarantees an outcome unconditionally, independent of this
  function entirely.
- **`prompt_classifier.py`**: `classify_prompt()` -- one LLM call that reads
  the free-text prompt and returns a `TraitProfile`. The system prompt is
  calibrated specifically against over-eager/cascading inference: rate each
  dimension independently from direct evidence only (in either direction),
  default to 0.0, names both poles per dimension, and three worked
  examples anchor "incidental mention" vs. "explicit and central" vs.
  "explicit negative evidence." Parsing is lenient (malformed/missing
  fields degrade to "no evidence," never a crash) since LLM JSON isn't a
  reliable typed API.
- **`phonology_gen.py`**: `generate_phonology()`. One uniform mechanism
  drives inventory membership: every candidate consonant/vowel (a pool of
  ~60 consonants / ~22 vowels spanning the major IPA categories, including
  a few very-low-prevalence "exotic" extras like clicks/implosives, and the
  aspirated (pʰ/tʰ/kʰ), pharyngealized/"emphatic" (tˤ/dˤ/sˤ/ðˤ),
  same-quality-length-pair vowel (aː/iː/uː/eː/oː), geminate consonant
  (kː/tː/pː/sː/nː/lː -- a phonemic length distinction the consonant has
  on its own, Italian "sono" vs. "sonno"; each paired with a high-
  prevalence plain counterpart already in the pool so
  `romanization_gen.py`'s pairing usually resolves), palatalized
  consonant (tʲ/dʲ/nʲ/lʲ, Russian-style), and diphthong (ai/au/ɔi/ei/ɛi/œy
  -- each its own atomic, multi-character `Vowel` symbol classified by
  its *onset* quality; drawn independently per symbol like every other
  `_VOWEL_EXTRAS` member, not gated as one all-or-nothing group the way
  the consonant secondary-articulation groups are) groups -- illustrative
  coverage, not exhaustive IPA) gets an independent `rng.random() <
  prevalence` draw, except trait-linked symbols (ejectives, the uvular
  series, harshness-tagged fricatives/affricate/velar nasal), which use
  `biased_probability` (or `1.0` under the matching `force_*` flag)
  instead: ejectives from `traits.altitude` (Everett 2013), uvulars from
  `traits.isolation`, harsh-vs-soft fricative/affricate/nasal selection
  from `traits.aesthetic_harshness`. Aspirated/pharyngealized/long-vowel/
  geminate/palatalized/diphthong groups have no graded-trait link (no
  obvious existing trait fits any of them) -- pure base-rate + reference-
  bias, same treatment as the exotic click/implosive pool. Voiced stops/affricates are
  only added alongside their voiceless counterpart (near-universal
  implicational rule, guaranteed by construction). A floor tops up from the
  highest-prevalence unused symbols if the probabilistic draw produces a
  degenerate inventory. Onset/coda cluster legality comes from
  `sonority.py`, not a hardcoded list; each generated language also gets a
  coda profile (none / sonorant-only / unrestricted, illustrative-weighted)
  and a vowel-harmony flag (modestly boosted by `traits.isolation`).
  Tone-system-enabled uses `traits.tonal_friendliness` the same way.
  Milestone 5 adds two more inputs, both soft biases layered on the same
  probabilistic mechanism (never a hard override by default): `traits.source_languages`
  matched against `reference_languages` boosts symbols/coda-profile/
  onset-tolerance/tonality toward the matched real language(s)' profile and
  suppresses the rest (`_reference_biased_rate`/`_group_reference_bias`/
  `_reference_clamp`); `spec.seed_examples`' IPA (tokenized against the full
  known symbol pool, greedy longest-match like `RomanizationScheme.apply`)
  is a hard floor -- those specific phonemes are unconditionally forced into
  the inventory (`_force_include`), since a seed word's sounds must actually
  be available for the word to make sense as part of the language.
  `traits.source_language_strictness` (`[0, 1]`, `--strictness` on the CLI,
  or LLM-inferred from wording like "basically German" vs. merely
  atmospheric evocation) is the gradient dial on top of that soft bias --
  `0.0` (the default) reproduces the soft bias exactly; `1.0` pushes every
  one of those same formulas to its certainty/impossibility limit via
  `generation.trait_bias.biased_probability` (reused directly, since
  strictness is already a zero-to-one "positive strength"), hard-
  restricting the inventory to (the union of, when multiple languages are
  named) the matched profile(s)' own declared symbols, capping onset/coda
  shape to their own values, and making tonal/vowel-harmony deterministic.
  The same dial extends to `romanization_gen.py` (whole-scheme category
  selection, per-symbol curated spelling adoption, and the
  `GrammaticalSpelling` rolls -- German nouns reliably capitalize, French
  verbs reliably get their silent "-r") and to `grammar_gen.py`'s
  reference-bias axes -- originally just `uses_root_and_pattern`/the
  `FUSIONAL` weight boost, later extended to `word_order`/`alignment`/
  `has_articles`/`has_overt_copula`/`adjective_after_noun`/`cases` too
  once `real_word_order`/etc. existed to bias toward (see "Real
  inflection" below) -- for the specific profiles curated for those newer
  fields; an unmatched or not-yet-curated-for-this-axis profile still
  falls back to the unbiased trait-only roll exactly as before.
  `_force_include`'s seed-example floor stays completely unrestricted
  regardless of strictness, for the same correctness reason as above.
  Strictness also fixes two gaps a restricted *inventory* alone doesn't:
  `sonority.py`'s onset-cluster legality is a generic Sonority Sequencing
  Principle check, not real per-language data, so an SSP-legal but
  never-attested pair (f+m, g+v, d+n...) used to pass freely even at full
  strictness. `ReferenceLanguageProfile.attested_onset_clusters`
  (curated for German/English/French so far, empty -- unaffected --
  elsewhere) narrows the generic sonority-legal space to real attested
  pairs via `sonority.grade_against_attested`, the same
  `biased_probability`-graded pull as everywhere else in this feature.
  Separately, `restricted_onset_consonants` (e.g. `ŋ`, coda/medial-only
  in real German/English, never a plain syllable onset) plugs a second
  gap: unlike coda position (`excluded_coda_consonants`), *onset*
  position had no restriction mechanism of any kind before this --
  `SyllableStructure.excluded_onset_consonants` is its mirror, strictness-
  graded the same way, consumed by `word_builder._build_onset`.
- **`reference_languages/`** (a package, not a single module):
  `ReferenceLanguageProfile` and `REFERENCE_LANGUAGES` -- one hand-curated,
  typologically-spread profile per language (Japanese, Finnish, Mandarin,
  Arabic, Hawaiian, Georgian, a click-language stand-in, a Romance
  stand-in, Dutch, French), symbol sets restricted to what
  `phonology_gen.py` already models. `match_profiles()` case-insensitively
  matches names/aliases; unknown names are silently ignored. Illustrative
  sketches for flavor, not authoritative descriptions. Each profile lives
  in its own file under `reference_languages/profiles/*.yaml` -- adding a
  language is "add a YAML file that matches `ReferenceLanguageProfile`'s
  shape," no code change; `__init__.py`'s module docstring documents the
  exact YAML shape with an annotated example. `REFERENCE_LANGUAGES` is
  built by loading and `model_validate()`-ing every file in that directory
  at import time (same `model_dump()`/`model_validate()` round-trip
  `storage/yaml_backend.py` already uses for saved languages). Arabic's
  profile sets `root_and_pattern: true` (see `grammar_gen.py` below) and
  includes the emphatic consonants/long vowels, with real scholarly
  transliteration `orthography` rules for them (dot-under ṭ/ṣ/ḍ/ẓ, macron
  ā/ī/ū). Dutch's profile sets `coda_devoicing: true` -- real Dutch/German-
  style final-obstruent devoicing modeled as a *static* phonotactic
  constraint on fresh generation (not just `sound_change.py`'s diachronic
  `final_devoicing` rule): when a matched profile declares it and the
  generated `coda_profile` resolves to `"unrestricted"`,
  `generate_phonology()` populates `SyllableStructure.excluded_coda_consonants`
  with every voiced obstruent in that language's own inventory, and
  filters the coda-cluster pool to match (`sonority.exclude_final()`) so
  a cluster can never end in one either; `sound_change.py`'s
  `_recompute_syllable_structure` reapplies the same logic post-evolution
  (using the same lineage-merged source-language set the orthography fix
  already threads through) so the constraint doesn't silently reset on a
  run that adds no new contact language. Dutch, German, Russian, and
  Turkish are the four real final-devoicing languages among the current
  profiles; the rest don't categorically neutralize final obstruent
  voicing. A profile can optionally set `orthography_category` (a name
  into `romanization_gen.py`'s `_CATEGORIES` registry) as a coarse
  "which family" signal, separate from and layered under its own
  specific `orthography` deviations -- every profile now sets one,
  picked to match that language's own real orthographic tradition where
  one exists (Finnish's `"gemination-style"` matching kukka/kuka, whose
  own `consonants` list also includes `"kː"` so a Finnish contact bias
  raises geminate-consonant *selection* itself via the existing
  `_group_reference_bias` mechanism, not just the orthography roll;
  Turkish's `"diacritic-style"` is unusually literal, since Turkish's
  *own native* Latin alphabet already uses exactly those diacritics
  natively) or the closest reasonable fit otherwise. This is why an
  uncurated symbol under a source-language bias still tends to feel
  like that language's own family, not an unrelated generic default --
  see
  `romanization_gen.py`'s per-symbol priority tiers below.
- **`seed_examples.py`**: `resolve_seed_examples()` -- fills in
  `SeedExample.ipa` from `.form` via one LLM call per unresolved example
  when the user didn't supply IPA directly. An explicit guess (stated as
  such in the prompt), not phonetic analysis -- there's no reliable way to
  recover pronunciation from arbitrary spelling without knowing the
  intended convention.
- **`romanization_gen.py`**: `generate_romanization()` -- resolves an
  `OrthographyCategory` via `_resolve_category()`, in order of certainty:
  `forced_orthography.style` (an exact named anchor from `_CATEGORIES`,
  `ValueError` if misspelled) wins outright; otherwise a matched
  reference profile's own declared `orthography_category`, then
  `traits.requested_orthography_style` (the prompt-classifier hint), each
  get one probabilistic (70%) shot at winning; nothing winning rolls each
  axis independently (`_roll_independent_axes` -- see the `core/romanization.py`
  section above for why this isn't restricted to the ten named anchors);
  any other field set on `forced_orthography` then overrides just that
  one axis on top, always. The resulting category's `exotic_style` table
  covers every symbol in `phonology_gen.py`'s shared pool (no symbol
  falls through to a raw IPA glyph), and every one of its axes is logged
  onto the built `RomanizationScheme` so a saved language's
  `romanization.yaml` records what produced it. Independently of the
  category roll, when `traits.source_languages` matches a
  `reference_languages` profile, its own hand-curated `orthography` rules
  blend in probabilistically per symbol too (e.g. Dutch spelling /u/ as
  "oe" -- "feels like Dutch" without literal evolution from it). A
  reference profile can define more than one
  rule for the same symbol (Dutch's open/closed vowel-length pairs,
  Mandarin's ü/u-after-j/q/x/y pair, French's front/back-vowel consonant-
  softness pairs); when the reference roll succeeds for that symbol, every
  variant is carried over together, never split. Per-symbol priority
  (`_rules_for_symbol`) is four tiers: a matched reference deviation, then
  a category's own *generated* structural rule (`_generate_length_rules`/
  `_generate_doubling_rules`, built against the actual inventory --
  syllable-conditioned doubling or an unconditioned macron/colon rule for
  every long vowel with a same-quality short counterpart; a
  `preceding=("short_vowel",)` doubled-consonant rule paired with its
  plain fallback, when the category doubles consonants after short
  vowels), then -- for a symbol no matched profile curates a specific rule
  for -- a matched reference profile's own *named-anchor* `exotic_style`
  table (picked among the matched profiles' anchors if more than one
  applies), so an uncurated exotic symbol still leans on its contact
  language's own family of conventions rather than whatever the whole
  scheme's own independently-resolved category happens to use; only when
  no active contact language has any anchor at all does it fall through
  to the scheme's own flat `exotic_style` fallback letter. The
  long/short vowel pairing (and the `vowel_length` context tags
  themselves) only ever considers a vowel genuinely paired with a same-
  quality counterpart via `Vowel.long` -- deliberately *not* every vowel's
  bare `.long` flag, since some reference languages (Dutch's own "y") mark
  length purely through spelling convention, unrelated to that flag, and
  tagging every such vowel "short" would spuriously trigger consonant
  doubling after all of them. Every scheme this module builds also carries
  `vowel_symbols`/`legal_onset_clusters`/`vowel_backness` derived from the
  actual `PhonemeInventory` (via `sonority.legal_onset_pairs()` and
  `Vowel.backness`), so `RomanizationScheme.apply()` can resolve that
  context. `evolve_romanization()` is the equivalent for an evolving
  language (`sound_change.py`): reconstructs and carries forward the base
  scheme's own category exactly (`_category_from_scheme`, reading its
  stored axis fields directly -- reference-profile/prompt bias is
  deliberately *not* re-consulted for the *whole-scheme category* here)
  rather than rolling a fresh one. The per-symbol fallback tiers above
  still apply for any newly-reformed or newly-introduced symbol, though,
  using the base language's own original source-language lineage merged
  with any new contact this run adds (`sound_change.evolve_language`'s
  `lineage_languages` -- not just this run's own `traits.source_languages`
  alone, which would otherwise silently lose a language's own reference
  identity, e.g. Dutch's curated `x`->`ch`, the moment a symbol got
  reformed on a run that added no *new* contact),
  then decides, per *symbol* rather than per word, whether an inherited
  spelling rule is kept (**freeze**) or dropped and regenerated via the
  same four-tier priority (**reform** -- rare by default), then
  independently rolls per-rule **orthography-only drift**
  (diacritic/ejective-mark dropping) on the result -- see its own
  docstring for the full rate model and rationale. Deciding this per
  symbol (not per word) is what guarantees two words sharing a symbol
  always render it the same way. `forced_orthography` is still honored
  during evolution, though -- a deliberate, user-triggered whole-scheme
  reform; the *automatic* probabilistic kind (a Wade-Giles -> Pinyin-style
  historical swap happening on its own) isn't modeled -- see "Known v0
  limitations" below.
- **`grammar_gen.py`**: `generate_grammar()` -- weighted picks reflecting
  rough cross-linguistic frequency (SOV/SVO dominate; nominative-accusative
  dominates), nudged via `biased_probability`/weight shifts by
  `traits.isolation` and `traits.community_scale` (toward
  polysynthetic/agglutinative and ergative alignment -- Trudgill) and
  opposed by `traits.contact_intensity` (toward isolating/analytic --
  creolization tendency). `uses_root_and_pattern` is a separate low-base-
  rate roll (real templatic morphology is a narrow typological category),
  boosted -- along with `morphological_type`'s weights toward `FUSIONAL`
  specifically, empirically the right classification for Arabic's
  inflectional system -- when `traits.source_languages` matches a
  reference profile with `root_and_pattern=True`. `templates` is left
  empty here; `generator.py` fills it in afterward once the phoneme
  inventory exists (same relationship `plural_suffix` already has to it).
- **`word_class_gen.py`**: `generate_word_classes()` -- step one of a
  staged grammar roadmap (part-of-speech labeling + per-POS citation-form
  word shape here; real inflection -- case/conjugation/agreement -- and
  LLM-driven sentence construction are later, separate steps). Rolls,
  independently per `PartOfSpeech`, whether this language has a real
  multi-class citation-form paradigm for it (real Latin noun declensions
  `-us`/`-a`/`-um`, French verb conjugations `-er`/`-ir`/`-re`, Swahili
  noun-class prefixes `m-`/`ki-`/...) -- reused verbatim from a matched
  `ReferenceLanguageProfile.word_classes` when one curates them (a
  `strictness`-graded adoption roll, same "usually, not always, adopt the
  real convention" shape `romanization_gen.py`'s own reference-adoption
  rolls already use), or invented otherwise via a real, well-documented
  cross-linguistic asymmetry (nouns/verbs/adjectives get a meaningfully
  higher base rate than pronouns/particles/numerals, which mostly don't
  vary in citation shape by class at all). An invented class's own
  prefix/suffix is built via two new `word_builder.py` helpers,
  `build_class_suffix`/`build_class_prefix` -- a nucleus(+coda)-only
  suffix or onset+nucleus-only prefix, deliberately never including the
  "outer" onset/coda, so the join with any stem is phonotactically safe
  by construction (vowel-adjacent, never an arbitrary cluster) without
  needing a general phonotactic-repair mechanism. Root-and-pattern
  languages never get *invented* classes (real Semitic case/gender
  morphology interacts with root-and-pattern derivation in ways well
  beyond this step's own scope, an explicit boundary, not solved here) --
  a matched reference profile's own curated classes are still honored
  regardless.

  Unlike `core.romanization.MuteSuffixRule` (a cosmetic, silent spelling
  addition with zero IPA effect -- real French's own infinitive silent
  "-r"), a `WordClass`'s own prefix/suffix is genuine phonological
  content: `word_class_gen.assign_word_class()` picks a word's own class
  at coinage time (weighted by `WordClass.prevalence`, with a
  `word_class_deviation_rate` roll modeling real irregular/suppletive
  exceptions -- the same per-language "usually X, sometimes not" shape
  `stress_deviation_rate` already has), and `apply_word_class()`
  concatenates it directly onto the word's own IPA -- real content from
  that point on, riding through `RomanizationScheme.apply()` and every
  later `sound_change.py` rule exactly like any other phoneme, needing
  **no** special evolution-time handling (a class suffix undergoes the
  same historical sound change as the rest of the word, e.g. real Latin
  `-us` -> Italian `-o`, the linguistically correct behavior, not a
  re-derivation step). Critically, `apply_word_class()` also *re-derives*
  stress (and word accent) on the full, now-longer word via
  `word_accent_gen.mark_stress_and_word_accent` -- the same flat-symbol-
  sequence marking mechanism `root_pattern.py`/`sound_change.py`'s own
  templatic coining already use -- rather than trusting the stem's own
  already-baked-in mark: a position-dependent pattern (real French's own
  final-syllable stress is the clearest case) would otherwise still land
  on the *stem's* former final syllable once a vowel-bearing suffix
  syllable follows it, a real bug caught and fixed by generating French's
  own validation data during this feature's own first batch. Re-
  tokenizes the stem against the *full global* phoneme pool
  (`phonology_gen.ALL_CONSONANTS`/`ALL_VOWELS`, module constant
  `_ALL_SYMBOLS`), not just this run's own generated `PhonemeInventory`:
  a root-and-pattern template's own literal characters (real Arabic's
  "m-" place-noun prefix, hardcoded in `root_pattern.generate_
  templates()` regardless of what a given run's own inventory happens to
  contain) aren't guaranteed to already be inventory members, and
  tokenizing against too narrow a symbol set silently drops them
  (`ipa_tokenizer.tokenize`'s own documented behavior for an
  unrecognized character) -- a real bug found and fixed curating
  Arabic's own second-batch validation data (a missing root consonant
  only surfaced once a `WordClass` was actually applied to a templatic
  word). Called from all four word-coining sites
  (`lexicon_gen.propose_word` and its own `_propose_kinship_word`
  helper, `root_pattern.propose_templatic_word`, `sound_change.py`'s two
  coining functions) -- a borrowed word (`_coin_borrowed_word`)
  deliberately gets no class marking at all (real loanwords don't follow
  the borrowing language's own declension/conjugation system, at least
  not immediately). Known, documented gap: a tone mark stays on
  whichever base vowel it was already on in the stem, but a *new* vowel
  the suffix/prefix itself contributes gets no tone mark of its own --
  confirmed harmless in practice for Zulu/Xhosa's own second-batch
  noun-class prefixes (e.g. Zulu `umu-` + stem): the prefix's own vowels
  simply surface untoned while the stem's original tones ride through
  unchanged, a real but cosmetically minor gap, not a crash or a
  mismarked stem.

  First validation batch curated real data for 5 profiles chosen to
  exercise the mechanism's full range: Latin (suffixing noun declension),
  French (suffixing verb conjugation -- retiring its own former
  `mute_suffix_by_pos` entry, now modeled more accurately as real
  phonological content), German (a mix of an unmarked class -- real
  German masculine/neuter nouns take no citation-form ending at all,
  a legal, honest "both prefix and suffix empty" `WordClass` -- and a
  real `-e` feminine-leaning class, plus a single dominant `-en` verb
  class), Swahili (the first profile to exercise `WordClass.prefix`, a
  real Bantu noun-class-prefix system -- the direct payoff of a gap this
  project's own Swahili profile had already flagged in passing, as a
  word-length-counting note only, until now), and Mandarin (the "real
  isolating language has no such system" control case -- though note an
  empty `word_classes` doesn't *suppress* the generic invented-class
  roll for an unmatched/uncurated POS, the same "optional-field default
  can't distinguish unconsidered from actively false" limitation
  `root_and_pattern`'s own default already has elsewhere in this
  project; a Mandarin-biased run can still roll invented classes like
  any other unmatched language).

  A second batch curated 12 more profiles, broadening real
  cross-linguistic coverage past the first batch's Romance/Bantu/
  isolating spread: Spanish and Portuguese (the same real Iberian
  masc-`-o`/fem-`-a` noun split and `-ar`/`-er`/`-ir` verb classes as
  French/Latin's own Romance family, but with a phonemic tap `"ɾ"` in
  the verb suffix rather than a trill, matching each profile's own
  already-curated `restricted_coda_consonants: [r]`), Italian (a genuine
  3-way `-o`/`-a`/`-e` noun split, the first profile where the third
  class is real gender-ambiguity itself, not a third gender), Russian
  (masc-unmarked/fem-`-a`/neut-`-o` noun gender plus a single dominant
  `-t'` verb class -- deliberately *not* modeling Russian's real
  conjugation-class I/II distinction, since that split is present-
  tense-only, not a citation-form fact, so a false multi-class
  infinitive split was avoided), Arabic and Hebrew (real Semitic
  feminine tāʾ marbūṭa/`-a` marking curated *despite*
  `root_and_pattern: true` -- safe because `word_classes` applies
  orthogonally on top of whatever stem the templatic system already
  built; only *invented* classes are excluded from root-and-pattern
  languages, reference-curated ones are always honored), Ancient Greek
  (real 1st declension `-ē` / 2nd declension `-os`(masc./fem.)/
  `-on`(neut.) nouns, thematic `-ō` / athematic `-mi` verbs -- modeling
  2 of Greek's real 3 declensions, reflected in a higher
  `word_class_deviation_rate` than the more-regular profiles), Sanskrit
  (real a-stem/ā-stem nouns, cited by *stem* form rather than the
  visarga-marked nominative `-aḥ`, since "h" isn't a legal coda in this
  profile's own already-curated restrictions -- no verb classes, since
  Sanskrit verbs are conventionally cited by root), Old Norse and
  Icelandic (real masc-`-r`(Old Norse)/`-ur`(Icelandic, the modern
  reflex) vs. unmarked fem./neut. nouns, plus a real `-a` infinitive
  verb class -- Turkish's own real vowel-harmony-conditioned `-mak`/
  `-mek` infinitive split was deliberately *not* curated, since
  `assign_word_class`'s flat weighted pick has no mechanism to
  condition a class choice on a stem's own harmony class, and forcing a
  random split could silently violate a profile's own already-curated
  `vowel_harmony: true` fact), and Zulu/Xhosa (real Bantu noun-class
  prefix systems, a 5-class representative subset each of class 1/2,
  5/6, 7/8, 9/10, 11 -- Xhosa's own class 1/2 `um-` is genuinely,
  dialectally shorter than Zulu's own `umu-`, the first two profiles to
  combine a curated `WordClass.prefix` system with tone, see the
  tone-gap note above).

  A third batch curated 8 more profiles: Danish, Swedish, and Norwegian
  (a real Mainland Scandinavian fact quite different from Old Norse/
  Icelandic's own real declension -- the modern common/neuter gender
  split is *not* citation-form-marked on the noun itself at all, unlike
  Old Norse's real `-r`, so no noun classes are curated for any of the
  three; verbs instead get a real dominant infinitive marker each
  (Danish/Norwegian `-e`, Swedish `-a`, both realized as this project's
  own schwa/`a` nucleus) plus a small real "unmarked" class for the
  closed set of already vowel-final monosyllabic verbs -- gå/stå/se/
  bo-class exceptions), Dutch (a near-exceptionless single `-en`
  infinitive class, the strongest single-class case curated yet --
  "zijn" ("to be") is close to the only real exception, folded into
  `word_class_deviation_rate` rather than a second class), English (a
  second real control case alongside Mandarin's -- modern English has
  no citation-form noun or verb class marking at all, the most
  thoroughly analytic profile in this project's own Germanic family),
  Polish and Serbo-Croatian (the same real Slavic masc-unmarked/
  fem-`-a`/neut-`-o` gender split already curated for Russian, plus each
  language's own real dominant verb-infinitive marker -- Polish's
  single `-ć` (phonemically `"tɕ"`, the same alveolo-palatal affricate
  this profile already curates for real Polish spelled "ć"), Serbo-
  Croatian's dominant `-ti` alongside a real smaller `-ći` class for a
  closed set of velar-stem verbs), and Hungarian (a real single `-ni`
  infinitive class, no noun classes at all -- Hungarian has no
  grammatical gender -- and deliberately safe to curate despite this
  profile's own `vowel_harmony: true`: unlike Turkish's real `-mak`/
  `-mek` split, Hungarian's own real `-ni` is one of the few Hungarian
  suffixes that does *not* itself alternate by vowel harmony, so a flat
  suffix choice here can't violate the harmony fact the way a
  harmony-conditioned suffix would). Finnish was considered and
  deliberately skipped alongside Turkish: its own real 1st-infinitive
  marker is *both* harmony-conditioned (`-a`/`-ä`) *and* stem-type-
  conditioned (`-da`/`-dä`/`-ta`/`-tä`), a compounding of exactly the
  problem that ruled out Turkish, not a simpler case.

  A fourth batch curated 8 more profiles, deliberately mixing a few more
  positive declension/conjugation curations with several honest
  "isolating, no citation-form class system" control cases (broadening
  that control-case set past just Mandarin/English into several more
  real language families): Hindi (a real, genuinely messier noun-gender
  fact than a clean single-suffix system -- only the real "declinable"
  masculine `-ā` subtype (laṛkā, ghoṛā) takes a marked citation ending
  at all, with everything else, non-`-ā` masculine *and* feminine,
  honestly modeled as a single "unmarked" class rather than overclaiming
  a full gender system this project's own flat per-word mechanism can't
  condition correctly; verbs get the real, near-universal `-nā`
  infinitive), Welsh (real gender exists but, like Mainland Scandinavian,
  isn't citation-form-suffix-marked on the noun -- it surfaces instead
  via a following word's own initial-consonant mutation, well outside
  this project's own per-word mechanism, so no noun classes; verbs get a
  real dominant `-u` "verb-noun" citation class, the productive default
  new/borrowed Welsh verbs take, plus a real unmarked minority for short
  irregular verb-nouns like mynd/dod/cael), Bengali (no grammatical
  gender at all, a real fact -- and a real single dominant `-a` "verbal
  noun" citation class for verbs, distinct from the separate `-te`
  conjunctive-participle form used in running speech), and five real
  isolating-language control cases spanning distinct families --
  Vietnamese and Khmer (Austroasiatic), Thai (Kra-Dai), Indonesian
  (Austronesian -- its own real derivational/voice-marking affixes
  attach in running speech, not obligatorily on the citation form
  itself, the key real distinction from Swahili's own obligatory noun-
  class prefixes), and Yoruba (Niger-Congo, but one that genuinely lost
  the wider family's own Bantu-style noun-class-prefix system) -- each
  with no citation-form noun/verb class marking at all, the same real
  fact already curated for Mandarin/English.

  Persian, Basque, Georgian, and Mongolian were each considered for this
  batch and deliberately left uncurated: each has a real verb-citation-
  form fact that isn't safely flattenable by this mechanism's own flat,
  unconditioned per-word roll. Persian's real `-tan`/`-dan` infinitive
  split is conditioned by the preceding stem's own consonant voicing --
  the same category of problem (a conditioned suffix choice, just with a
  different conditioning environment) that already ruled out Turkish's
  and Finnish's own vowel-harmony-conditioned suffixes. Mongolian's real
  citation-form suffix (traditionally romanized "-x") carries its own
  harmony-alternating linking vowel as part of the morpheme itself
  (`yavax` vs. `irex`), the same underlying problem again. Basque's own
  real citation-form verb endings are genuinely mixed/irregular across
  its core vocabulary (no single dominant pattern the way Welsh's own
  `-u` is). Georgian's own real verbal-noun (masdar) formation depends
  on a richer verb-class system this project doesn't model. Left for a
  future batch rather than curated dishonestly.

  A fifth batch addressed the last 14 uncurated reference profiles,
  bringing every profile in `reference_languages/profiles/` to one of
  three explicit, documented states: really curated, honestly empty (a
  real "no citation-form class system" control case), or deliberately
  skipped (a real system this mechanism can't safely flatten). Five
  more profiles got real positive data: Japanese (no noun classes --
  genuinely genderless -- but a real, essentially exceptionless single
  verb class: the dictionary/"plain non-past" citation form always ends
  in a u-row syllable, modeled as the bare vowel suffix `u` so it
  composes correctly regardless of the stem's own final consonant),
  Korean (no noun classes; verbs *and* adjectives -- real Korean
  adjectives are morphologically "descriptive verbs," not a separate
  word-shape category -- share the same real, essentially exceptionless
  `-다`/`-da` citation-form suffix, curated with IPA `t` rather than `d`
  since Korean has one plain stop phoneme `/t/`, not a separate `/d/`,
  and this profile's own pre-existing orthography rule already spells
  it "d" after a vowel), Nahuatl (the real, obligatory absolutive noun
  suffix already flagged in this profile's own `core_vocabulary_
  average_syllables` comment -- simplified from its real three-way
  phonologically-conditioned allomorphy (`-tl`/`-tli`/`-in`) to a single
  dominant "-tli" elsewhere-form, the same "naturalism, not full
  accuracy, at the phonotactic boundary" simplification this project's
  own Russian `-t'` already accepts, plus a real unmarked class for
  Nahuatl's own obligatorily-possessed nouns -- confirmed working
  exactly as intended when kinship terms like "mother"/"father" landed
  in that unmarked class during validation), Quechua (no noun classes --
  genuinely genderless -- but a real, near-universal `-y` infinitive,
  curated as the glide `/j/` consonant this profile already models, not
  the vowel its own Latin spelling suggests), and Nama (a real,
  typologically unusual *suffixing* gender-number system -- but curated
  only partially, honestly: the real feminine `-s` is directly
  curatable, while the real masculine `-b` genuinely isn't, since this
  profile's own consonant inventory deliberately has no voiced stop
  series at all, so masculine and common gender are folded into a
  single honest "unmarked" class rather than introducing a phoneme this
  language's own profile says doesn't exist).

  The other nine got an explicit "no word_classes, deliberately"
  control-case or skip note: Malay (mirrors Indonesian's own real bare-
  root-citation fact exactly), Cantonese and Hawaiian (isolating/
  analytic control cases, Sinitic and Polynesian respectively, joining
  Mandarin/Vietnamese/Thai/Khmer/Yoruba's own), Tibetan (no noun
  declension at all; real verb stem-alternation exists but the
  dictionary citation form is conventionally just the bare present
  stem), Sumerian (a real animate/inanimate noun class exists, but it's
  semantic/agreement-triggering, not a citation-form suffix -- and this
  whole profile's own documented uncertainty as a reconstructed-only
  sketch makes inventing a paradigm here a bigger overclaim than
  elsewhere), Tamil (a real rational/irrational noun class, same
  semantic/agreement-triggering shape as Sumerian's; real verb
  infinitive formation is conditioned by one of three traditional
  conjugation classes, each with its own sandhi rule -- the same
  category of conditioned-suffix problem already ruling out Persian/
  Basque/Georgian/Mongolian), Navajo (real verb morphology is
  polysynthetic and template-based -- a whole ordered sequence of
  prefix slots around the root, not a root-plus-citation-suffix -- far
  beyond a single flat per-word roll), and Arawakan/Pama-Nyungan (both
  composite family sketches whose own already-documented thinner
  attestation makes this project's specific knowledge of a real
  citation-form system too uncertain to curate with the same confidence
  as its better-attested profiles).

  Every reference profile now has an explicit, reasoned answer to "does
  this language get word_classes" -- curated, honestly empty, or
  deliberately skipped -- rather than an unconsidered gap. Should new
  reference profiles be added in the future, they'd need this same
  explicit consideration to stay consistent with that standard.

  **Stem-conditioned class selection**, added afterward, lifts exactly
  the limitation that kept Turkish/Finnish/Mongolian/Persian in the
  "deliberately skipped" list above: `WordClass` gained `condition`
  (`""` | `"vowel_harmony"` | `"final_voicing"`) and `suffix_alt`, and
  `word_class_gen.apply_word_class` gained `_resolve_conditioned_suffix`
  (plus its own `_resolve_harmony_backness`/`_resolve_final_voiced`
  helpers). This is a genuinely different mechanism from
  `assign_word_class`'s own unconditioned weighted roll *among* classes
  (appropriate for real lexical/arbitrary variation, e.g. Basque's own
  still-uncurated irregular verb endings) -- a conditioned suffix is
  real allomorphy *within one* grammatical class, where an unconditioned
  50/50 pick between two literal forms would routinely contradict the
  stem it's attaching to. Deliberately resolved late, not early: *which*
  class a word belongs to (`assign_word_class`) is still a per-word roll
  wholly unrelated to the stem's own phonology, decided (as before)
  before the stem's IPA is even final; *which surface allomorph* a
  conditioned class's suffix takes is resolved only inside
  `apply_word_class`, the one point in the whole coinage pipeline where
  the real, finished stem already exists -- so no call site needed
  reordering, and no new argument needed threading through
  `lexicon_gen.propose_word`/`root_pattern.propose_templatic_word`/
  `sound_change`'s own coining functions at all.

  Both conditions reuse phonological trait data `core.phonology` already
  carries for every phoneme in the global pool -- `Vowel.backness`
  (`word_builder.build_word`'s own harmony generation already keys off
  this exact field, so a class's own condition resolution and the stem's
  own harmony generation are provably reading the same fact) and
  `Consonant.voiced` -- rather than inventing new per-language phonology
  data. `"vowel_harmony"` resolves the stem's own harmony class from its
  *last* non-`CENTRAL` vowel, scanning from the end (the vowel nearest
  the suffix boundary, the one real harmony actually conditions on),
  falling back to back-harmony when the stem has no such vowel at all --
  a real, non-hypothetical case: this project's own global vowel pool
  classifies a fully-open "a" as `CENTRAL` rather than a harmony-
  participating `BACK`, even though real Turkic/Mongolic "a" behaves as
  a back vowel for harmony purposes, and "a" is also that pool's single
  most common vowel, so defaulting the "no clear signal" case to back
  gets the single most frequent real case right rather than by
  accident. `"final_voicing"` resolves the stem's own final segment's
  voicing directly, falling back to the primary (voiceless-context)
  form for a vowel-final stem.

  Turkish (`-mek`/`-mak` infinitive, `condition: vowel_harmony`) and
  Mongolian (`-эх`/`-ах`, i.e. `[e,x]`/`[a,x]` -- the real consonant
  unchanged either way, only the harmony vowel alternates) are both now
  curated exactly as their own real grammar works. Persian (`-tan`/
  `-dan`, `condition: final_voicing`) is curated the same way for its
  own real final-consonant-voicing agreement, a different conditioning
  feature but the identical "genuine stem-conditioned allomorphy, not an
  unconditioned choice" shape. Finnish (`condition: vowel_harmony`,
  `-ä`/`-a`) is curated for its own real harmony axis only -- its own
  further real stem-type/consonant-gradation conditioning (a second,
  independent axis this mechanism doesn't attempt to compose with the
  first) stays a known, explicitly documented gap in finnish.yaml's own
  comment, not silently dropped. Verified by hand across 3 seeds each
  for all four profiles: every single generated verb's suffix agreed
  correctly with its own stem (harmony backness for Turkish/Finnish/
  Mongolian, final-consonant voicing for Persian), including the
  documented central-vowel-only and vowel-final fallback cases actually
  firing and resolving as specified -- zero mismatches.

  Basque, Georgian, Tamil's own verb-conjugation-class system, Sumerian/
  Tamil's own noun agreement classes, and Arawakan/Pama-Nyungan remain
  genuinely out of this mechanism's reach for the *other* reasons
  already given above (lexical irregularity with no confidently-known
  real proportions, an unmodeled richer class system, agreement rather
  than citation-form marking, and thin attestation, respectively) --
  none of those are the "needs stem-lookahead conditioning" problem this
  extension solves, so this extension doesn't newly unblock any of them.
  Navajo, listed above as blocked by *polysynthetic template morphology*
  specifically, is addressed by a second, different extension instead --
  see immediately below.

  **Polysynthetic position-class prefixes**, added after that, lifts the
  polysynthetic-morphology limitation that kept Navajo on the
  "deliberately skipped" list: `WordClass` gained `position_classes`
  (`tuple[PositionClass, ...]`), and two new small frozen models,
  `PositionClass` (a named slot: `name` + `options`) and
  `PositionClassOption` (`name` + `symbols` + `prevalence`) -- real
  Athabaskanist terminology (Young & Morgan; Rice; Hardy) for exactly
  this concept: a polysynthetic word's own verb-prefix structure is
  conventionally described as an ordered sequence of "position classes,"
  each a real, independent grammatical category (subject agreement,
  classifier, ...) that contributes its own morpheme to *every* word of
  that class simultaneously -- categorically different from an ordinary
  `WordClass` (one alternative paradigm chosen *among* several by
  `assign_word_class`'s own roll) or from `condition`'s own stem-
  conditioned *binary* choice. `word_class_gen.apply_word_class` gained
  `_resolve_position_classes`: for each slot, an independent weighted
  roll among its own options (the same `rng.choices`-by-`prevalence`
  shape `assign_word_class`'s own class selection already uses, just
  repeated once per slot), concatenated in order into a composite prefix
  prepended ahead of `prefix` and the stem. `symbols=()` is a real,
  legitimate option, not a placeholder -- a slot's own "null/zero
  morpheme" choice (Navajo's own zero classifier, by far its most common
  real one).

  Reuses the *exact* same integration points as `condition`/`suffix_alt`
  did, and for the identical underlying reason: `apply_word_class`
  already runs at the one point in every coinage path where the real
  stem exists, so composing a further prefix there needed no new
  argument threaded through any of the 5 existing call sites
  (`lexicon_gen.py` x2, `root_pattern.py` x1, `sound_change.py` x2), no
  new `GrammarProfile` field, and no new generator function --
  `generate_word_classes`'s existing reference-adoption logic already
  copies a matched profile's whole `WordClass` object (new field
  included) verbatim, confirmed during design research rather than
  assumed. Like `condition`, this only ever reaches a generated language
  through explicit reference-profile matching (`source_languages` naming
  "Navajo" by exact name/alias) -- the invented-class path never sets
  `position_classes`, so an unrelated/fictional language can't roll a
  polysynthetic prefix on its own, the same answer already given for
  harmony/voicing conditioning.

  Navajo itself is curated *partially and explicitly*: only the real
  classifier slot, and only 2 of its own real 4 members -- the real
  zero/null classifier (prevalence 0.7, the most common by far) and the
  real "ł-classifier" (prevalence 0.3, a simple, segmentally clean
  voiceless-lateral prefix, `"ɬ"`, already romanizing correctly via this
  profile's own pre-existing `{ipa: "ɬ", latin: "ł"}` rule). The other 2
  real classifiers (the "d-classifier," which often surfaces as
  consonant mutation on the stem's own initial segment rather than a
  clean independent segment, and the "ł'-classifier," glottalization
  interacting with the stem) are real but segmentally too complex for
  this project's flat concatenation model to honestly represent --
  left uncurated, the same "confident partial coverage" standard already
  used for Ancient Greek's 2-of-3 declensions and Zulu/Xhosa's
  5-of-~15 noun classes. The real subject-agreement prefix system (a
  further, more outward position class) stays entirely unmodeled too,
  for the same reason Tamil's own conjugation classes and Finnish's own
  stem-type conditioning stayed unmodeled: it's genuinely complicated by
  Navajo's own real "Mode I"/"Mode II" conjugation-class allomorphy and
  the yi-/bi- referential alternation, material advanced enough that
  guessing specific forms would overclaim confidence this project
  doesn't have. Verified by hand across 5 seeds: every generated verb
  carries the classifier (deterministically -- `word_class_deviation_
  rate` unset, since a real Navajo verb always has *some* classifier,
  including the audibly-silent zero one, so "no marking at all" isn't a
  coherent state the way it is for an ordinary optional class), the
  `ł`-classifier's own real romanization fires correctly every time it's
  rolled, and the zero/`ł` split across 45 sampled verbs (34/11, ~76%/
  24%) lands close to the curated 70%/30% target within normal sampling
  variance for that sample size.
- **`root_pattern.py`** (milestone 9): Semitic-style root-and-pattern
  (templatic) word formation -- a consonantal root (k-t-b "write"-related)
  fills a template to derive related words (kataba "he wrote", kitāb
  "book", kātib "writer", maktaba "library"). Models word *shape* only, not
  derivational *relatedness* between words (coining "writer" by reusing
  the root behind an existing "write" needs semantic judgment between an
  English gloss and the existing lexicon -- LLM territory, not attempted;
  `LexicalEntry.root` is recorded on every templatic word regardless, so
  that future work has the data already in place). `generate_templates()`
  builds a small illustrative set (one verb, three noun -- for real variety
  across different nouns, one preferring a *long* vowel when the inventory
  has one -- one adjective template) once per language, each template's
  vowel slots chosen from the actual generated inventory and then fixed
  (a real template's vowel pattern doesn't vary by root). `generate_root()`
  draws `size=3` (triliteral, the dominant real pattern) consonants
  weighted by prevalence with a simple OCP-style constraint: no two
  *adjacent* root consonants identical. `propose_templatic_word()` builds
  several root candidates and lets the LLM pick the best-sounding one --
  reuses `lexicon_gen.choose_best_candidate()` (extracted from
  `propose_word()` so the LLM-request shape lives in one place) rather than
  duplicating it. Applies to `PartOfSpeech.NOUN`/`VERB`/`ADJECTIVE` only
  (`TEMPLATIC_POS`) -- pronouns/particles/numerals stay non-templatic, real
  Semitic function words aren't derived this way either.
- **Real words and evolution** (two strictness dials, one step): the
  existing `source_language_strictness` is the **sound** strictness -- it
  only limits which sounds/syllables/orthography a language may use. The new
  `TraitProfile.source_word_strictness` (CLI `--word-strictness`, "Word
  strictness" in the web UI, classifier-extracted from wording like "actual
  Dutch words"; default 0 = none) is the **word** strictness
  (`generation/real_words.py`): each pregenerated meaning follows a real
  source-language word with that probability, and a real word is loosened by
  swapping each sound for a near neighbour with probability
  `(1 - strictness) * 0.6`, restricted to the sounds the sound strictness
  allows and re-spelled through the language's orthography -- so **1.0 makes
  every word an exact copy** (spelling verbatim, its phonemes forced into the
  inventory). Real words come from `reference_languages/lexicons/<name>.yaml`
  (`real_lexicon.py`; hand-transcribed to the modeled phoneme set, best
  effort and not linguist-verified; validated by `tests/test_real_
  lexicons.py`), and any meaning a matched language lacks curated is filled
  by one batched LLM request per 100 meanings (`real_words_llm.py`; answers
  whose IPA doesn't tokenize are dropped, the fake backend fills nothing).
  Word strictness far above sound strictness (margin 0.25) allows a *split
  vocabulary* and is **warned about, never blocked**. Real-derived entries
  carry `notes="real word: X"` / `"real-based word: X"`.
  **Reference-only symbols and tones:** real words need sounds the random
  draw would rarely (or never) pick, so `phonology_gen._REFERENCE_ONLY_
  CONSONANTS`/`_REFERENCE_ONLY_VOWELS` model them (β ɸ ɕ ʑ ɦ ʋ ɥ ɴ; the
  retroflex ɭ ɽ ɽʱ ʈʂ ʈʂʰ ɖʐ; emphatic zˤ lˤ; the diphthong ou) but keep
  them **out of every draw loop and out of `_ensure_floor` padding** -- they
  enter an inventory only when a seed/real word forces them in, so every
  existing seeded generation is unchanged. Tone marks in seed/real words
  (`TONE_DIACRITICS` combining marks, e.g. Mandarin 1-4 as high/rising/
  dipping/falling) make the language tonal with exactly those tones
  (`_levels_covering`; the tonal roll still runs first, so other draws are
  unchanged); `LexicalEntry.tones` records them, deviated words get their
  tones re-attached vowel by vowel and mapped to the language's own tone
  levels (none when it is not tonal). Profiles can carry `tone_levels`,
  `neutral_tone` and `tone_sandhi` (Mandarin: high/rising/dipping/falling +
  `ToneLevel.NEUTRAL`, the combining dot above, never on a word's first
  syllable; third-tone sandhi dipping+dipping -> rising): a run with source
  strictness >= 0.5 takes those levels. Sandhi is **probabilistic**
  (`phonology_gen.resolve_tone_sandhi`, its own rng seeded from `spec.seed`, so
  no other draw moves): each profile rule is kept with probability = the
  weighted source strictness (certain at 1.0), otherwise it may be replaced by
  a different invented rule (0.35 x (1 - strictness)), and a tonal language
  with no source rule may invent one (0.15, rarely two); the graded
  `TraitProfile.tone_sandhi` (-1..1, classifier-extracted) shifts all of those
  chances, except that full strictness always keeps the real rules. Sandhi is an
  utterance-level surface rule (`generation/tone_sandhi.py`, applied to the
  translation's IPA); lexicon entries keep citation tones. Profiles also
  list the reference-only symbols their language really has (Mandarin
  ʈʂ ʈʂʰ ɕ, Tamil ɭ, Hindi ɽ ɦ, Japanese ɸ ɕ ɴ, Polish ɕ ʑ, Russian ɫ ɕː,
  Arabic zˤ lˤ, Bengali ɽ); those join a strict inventory deterministically
  (weight x strictness >= 0.5, no rng). Not modeled: lexically specific
  sandhi (Mandarin 不/一) and Spanish β/ð/ɣ allophony in the profile.
  **Pronunciation engines** each report `TTSCapabilities` (which tones they
  voice + notes; `/api/options` `tts_capabilities`, shown under the engine
  select) and `tts.pronunciation_warnings` alerts for tones a translation
  carries that the chosen engine can't voice (`/api/pronunciation-check`, a
  banner in the UI). eSpeak voices tonal IPA through its Mandarin (`cmn`)
  voice: each tone becomes contour digits after its vowel (55/35/214/51, mid
  33, low 21, neutral 11) and a tonal sentence uses that one voice for every
  word, so the language's other sounds are approximated by Mandarin's
  inventory. SAPI cannot voice tones (its IPA input rejects tone marks); it
  strips them so the word is still spoken, toneless.
  Fitting a pronunciation to a language (nearest inventory phoneme +
  syllable-rule repair) lives in `generation/phoneme_fit.py`, shared with
  foreign-name adaptation. `generator.generate_evolved_language` then runs
  `GenerationSpec.evolve_years` (else the prompt-inferred
  `traits.time_depth_years`) years of `sound_change.evolve_language` on the
  fresh language -- so "Dutch evolved forward 200 years" is real Dutch words
  under real sound change; the CLI `--years` (without `--evolve-from`) and the
  web "Years of evolution" box drive it too.
- **Vocabulary size**: `lexicon_gen.CORE_MEANINGS` (the original 51,
  unchanged -- `experiments/` scripts index real-language lexicons against
  its order) plus `extended_meanings.EXTENDED_MEANINGS` (~445 more basic
  meanings, grouped and ordered by how basic they are: function words,
  verbs, adjectives, then body/nature/animals/people/food/objects/abstract
  nouns) make up `lexicon_gen.ALL_MEANINGS` (~496).
  `GenerationSpec.vocabulary_size` (default **400**; `--vocabulary-size` on
  the CLI, "Pregenerated words" in the web UI) pregenerates a prefix of it
  via `lexicon_gen.select_meanings()`, which always adds
  `ESSENTIAL_GLOSSES` (pronouns/not/and/the/be) so translation keeps
  working at small sizes. Anything not pregenerated is **coined on demand**
  when translation needs it (`translation/expansion.coin_word`), saved
  with the language, and found again on later requests: lookups also try
  simple base forms (`translator._gloss_variants`: plural `-s`/`-es`/`-ies`)
  so "canoes" reuses the "canoe" entry instead of coining a second word.
  Batched LLM word selection sends 100 words per request
  (`BATCH_CHUNK_SIZE`), so a 400-word language is 4 requests; collision
  retries are always algorithmic (up to 20 rounds), never an LLM call.
- **`lexicon_gen.py`**: `CORE_MEANINGS` (the original 51-word core vocabulary) and
  `propose_word()` -- builds candidate forms deterministically
  (`build_pending_word()`, returning a `PendingWord` whose `finish` callback
  completes it once a candidate is chosen), then picks one via
  `resolve_candidate()`, governed by `GenerationSpec.word_selection`:
  `"algorithmic"` (the default) is a uniform seeded-rng pick with **no LLM
  call at all**; `"llm"` delegates to `choose_best_candidate()` (one call,
  sound-symbolism-informed; shared with `root_pattern.py`, whose
  `build_pending_templatic_word()` has the same build/finish split). The
  initial core-vocabulary pass in `generator.py` builds every word's pool
  first and resolves all picks together -- one batched request
  (`choose_best_candidates_batch()`, a `WORD_NUMBER:CANDIDATE_NUMBER`
  reply parsed leniently, any malformed answer falling back to candidate 1)
  instead of one per word; romanization-collision retries re-pick their
  colliding words together per round (at most 5 rounds), so a whole
  language costs roughly 1-3 word-selection requests rather than ~51.
  `translation/expansion.py`'s later coinage honors the language's own
  `spec.word_selection` too. Sound symbolism itself (mother/father via
  `_propose_kinship_word`'s reduplication, big/small via
  `_SIZE_BIAS_GLOSSES`) lives in candidate *building*, not in this final
  pick, so making the pick algorithmic changes none of it. Prompt
  classification (`classify_prompt`) always uses the configured LLM
  regardless of `word_selection`.
  Shared by both initial generation and later expansion.
  Syllable count is weighted by part of speech and a `favor_short` flag
  (pronouns/particles skew short regardless; core generation defaults
  `favor_short=True`, `translation/expansion.py`'s coinage passes `False`)
  -- Zipf's law of abbreviation, using core-vs-coined as the one frequency
  proxy the system has. Both base weight tables were recalibrated against
  a hand-count of this project's own `CORE_MEANINGS` glosses translated
  into English/Dutch/French/German (the generic content-word mean was
  ~1.7 syllables, higher than even German's real ~1.43). On top of that,
  `ReferenceLanguageProfile.core_vocabulary_average_syllables` (curated
  for English 1.14, Dutch 1.27, French 1.35, German 1.43, Spanish 1.90,
  Italian 2.15 -- the last two carrying more counting uncertainty than
  the first four, given genuinely ambiguous diphthong-vs-hiatus
  syllabification in both) lets a matched `source_languages` bias graded by
  `source_language_strictness` exponentially tilt whichever base table
  got picked, via `choose_syllable_count`'s own `math.exp(theta * count)`
  reweighting -- deliberately the one mechanism in this whole feature that
  never zeroes out an option even at `strictness=1.0`, since average word
  length is a statistical tendency, not a categorical restriction the way
  every phonotactic axis above is. Two meaning-specific sound-symbolism
  effects layer on top: `"mother"`/`"father"` try `word_builder.build_reduplicated_word()`
  first (nasal vs. stop onset, ~80% of the time, falling back to normal
  generation if the inventory has neither or the roll misses) -- the
  mama/papa convergence; `"small"`/`"big"` thread `size_bias` into the
  normal candidate-build loop instead of replacing it.
- **`stress_gen.py`**: primary lexical word-stress -- which syllable of a
  word is stressed, stored as the standard IPA mark `ˈ` (U+02C8) directly
  before the stressed syllable's onset (e.g. Italian `parˈlare`), not as
  a separate structured field (unlike tone, the embedded mark is the
  single source of truth -- every consumer re-tokenizes the IPA string
  when it needs the position, rather than risking two representations
  drifting apart). `STRESS_MARK`/`predict_default_stress` live in
  `core/romanization.py`, not here -- `core.romanization.apply()`'s own
  stress-accent rendering (see below) needs them directly, and `core`
  can't depend on `generation`. `predict_default_stress(num_syllables,
  pattern, final_coda)` is pure and deterministic: `"final"` (French,
  ~always the last syllable), `"initial"` (German/Dutch, ~the root's
  first), `"penultimate_or_final_by_coda"` (real Spanish: penultimate if
  the word ends in a vowel/n/s, final otherwise), or `"lexical"`
  (English/Italian -- majority-penultimate for Italian, genuinely
  unpredictable for English; a further real refinement, English's own
  noun/verb stress alternation like ˈrecord/reˈcord, isn't modeled).
  `assign_stress()` picks the actual syllable per word: a bernoulli gate
  on `strictness` decides per word whether *this* word uses the matched
  profile's own pattern+deviation-rate pairing at all, or the generic
  penultimate-leaning baseline -- deliberately not a continuous blend of
  the two (there's no coherent "70% initial-stress" middle ground for a
  single word the way a numeric rate can interpolate); deterministic at
  `strictness=1.0`, pure baseline at `0.0`. `word_builder.build_word`
  can't decide stress until *after* every syllable is built (real
  Spanish's own rule depends on the actual final coda, which doesn't
  exist yet when syllable count alone is known) -- it collects each
  syllable's `(onset, nucleus, coda)` first, then calls `assign_stress`
  with the real final syllable's coda. `root_pattern.py`'s templatic path
  has no per-syllable build loop to hook into -- `mark_stress()` is a
  post-processing step on the chosen candidate's already-filled skeleton,
  syllabifying it via `syllable_onset_starts()` (the maximal-onset
  principle, the phoneme-symbol-level equivalent of
  `core.romanization`'s own `_coda_run_length`). Monosyllables are never
  marked at all (nothing to contrast against, the same reason real
  dictionary transcription omits it there). `_tokenize` in
  `core/romanization.py` extracts `STRESS_MARK` into a side-channel index
  (`stress_before`) rather than a real token -- it precedes its syllable
  and isn't a Unicode combining mark, so it can't ride the existing
  trailing-decoration slurp, and keeping it out of the token list
  entirely means zero risk to any existing following/preceding-conditioned
  rule. `apply()` then either drops it silently (`stress_accent_marking
  == ""`, most languages) or rewrites the stressed vowel's own letter in
  place via `_STRESS_ACCENT_MAP` -- `"final_only"` (real Italian: città,
  perché) when it's the word's last syllable, `"irregular_only"` (real
  Spanish: corazón, está) when the actual syllable differs from what
  `predict_default_stress` would have predicted -- the same "rewrite this
  vowel's own letter" shape `SyllableBoundaryMarker.DIAERESIS` already
  uses for French tréma, resolved in `romanization_gen.py` via
  `_resolve_stress_accent_marking`, following `_resolve_syllable_boundary_marker`'s
  own precedent exactly (a per-profile override on top of whatever
  `OrthographyCategory` resolved, carried forward unchanged -- not
  re-rolled -- by `evolve_romanization`). `sound_change.py`'s
  `ipa_tokenizer.tokenize()` keeps `STRESS_MARK` as a genuine token
  (unlike `core.romanization`'s side-channel approach) so it survives
  the six sound-change rules' own token-list mutations without separate
  index bookkeeping; `_apply_lenition`'s intervocalic check needed an
  explicit "skip past a stress marker" fix (stress systematically sits
  exactly where that check looks -- right before a syllable's onset --
  so leaving it unfixed would have silently suppressed lenition for
  every stressed-syllable onset). One payoff: `_apply_vowel_reduction`
  -- previously a position-blind "reduce every vowel except the word's
  first" approximation of unstressed-vowel-to-schwa reduction (English/
  Russian/Portuguese) -- now protects the vowel that actually follows the
  stress marker, falling back to the old first-vowel heuristic only when
  a word has no stress data at all. Root-and-pattern replacement during
  evolution (`_coin_native_word`'s templatic branch) resolves stress from
  `evolve_language`'s own `lineage_profiles` (the evolving language's
  heritage, not the current run's -- by construction always empty --
  `reference_profiles`), not a hardcoded generic baseline, so a
  Dutch-lineage language replacing a templatic word still stresses it
  the Dutch way. `word_builder.build_reduplicated_word` (the mama/papa
  path) assigns real stress too, via the same `stress_gen.assign_stress`
  -- a reduplicated word's two syllables are segmentally identical but
  audibly distinct in real stress placement (English "mama" is
  genuinely MA-ma).

  The other payoff, and the reason stress modeling extends past
  `sound_change.py`: `build_word` also takes a `reduce_unstressed_vowels`
  flag (from `ReferenceLanguageProfile.stress_driven_vowel_reduction`,
  curated true for English/German/Dutch, false -- the default -- for
  French/Spanish/Italian, which keep full vowel quality regardless of
  stress) modeling real *synchronic* reduction -- a freshly generated
  English/German/Dutch word's own citation form already has its
  unstressed vowels reduced (real "banana"/"Wasser" aren't three full
  vowels each), not something that only emerges after centuries of
  `sound_change.py`'s own separate diachronic drift. Implemented as a
  direct post-hoc swap of an already-built, already-valid syllable's
  nucleus to "ə" (never a re-draw through the normal weighted
  machinery), gated through `structure.is_valid_syllable` before
  committing so it can never manufacture an illegal nucleus-coda pairing
  (real English's own /ŋ/-only-after-a-checked-vowel restriction, e.g.
  -- schwa doesn't license it) -- skipped, not forced through, same
  "honest empty result over a fabricated illegal one" discipline
  `_build_coda` already practices elsewhere in this file.
- **`generator.py`**: `generate_language()` -- orchestrates the above into
  one `Language`. Builds a `LexicalEntry` directly from each
  `spec.seed_examples` entry (skipping `CORE_MEANINGS` generation for any
  gloss a seed example already covers) before generating the rest, so
  seeded words land in the lexicon like any other entry and translation
  picks them up with no special-casing. A seed entry's `romanization` is
  `example.form` itself (NFC-normalized), not the scheme applied to
  `example.ipa` -- a seed word's IPA is often already an approximation of
  the real word (six common diphthongs are modeled -- see
  `phonology_gen.py` below -- but a seed word using a real diphthong
  outside that small illustrative set still collapses to its nearest
  monophthong), so reconstructing the spelling from it can never recover
  the real one even in principle. When `grammar.uses_root_and_pattern`,
  every `NOUN`/`VERB`/`ADJECTIVE` core-meaning entry routes through
  `root_pattern.propose_templatic_word()` instead of `propose_word()`; same
  branch in `translation/expansion.py`'s `coin_word()` and
  `sound_change.py`'s `_coin_native_word()` (lexical replacement), so a
  root-and-pattern language stays templatic for every word it ever gets,
  not just its initial core vocabulary.
- **`sound_change.py`** (milestones 6-7): `evolve_language(name, base, years,
  traits, seed) -> Language` -- takes an *existing* saved language and
  evolves its lexicon via six rule-based sound changes (cluster
  simplification, lenition, final devoicing, palatalization, vowel
  reduction, ejective drift), instead of generating fresh. Pure rule-based,
  no LLM. Each rule's rate follows a saturating curve, `1 -
  exp(-years/effective_half_life)`, so small `years` changes little and
  large `years` approaches but never reaches total replacement;
  `contact_intensity` (simplification-leaning rules) and `altitude`
  (ejective drift, same Everett 2013 link as fresh generation) scale the
  half-life, shortening it at positive trait strength; `contact_intensity`
  additionally applies a direct multiplicative *suppression* to
  `ejective_drift` specifically (a half-life stretch alone can't keep a rate
  low indefinitely as `years` grows, which heavy sustained contact should
  do). `grammar` and `tone_system` are copied from the base unchanged
  (word-level feature only); `PhonemeInventory`/`SyllableStructure` are
  recomputed from what the evolved lexicon actually uses.

  Orthography evolves via two independent mechanisms. **Lexical
  replacement** (the whole entry, IPA and spelling, swapped for a different
  word) is decided per entry: borrowed from a matched contact language's
  own phoneme pool *and* spelled with that language's own conventions when
  `source_languages` is set, otherwise a native coinage via the same
  `lexicon_gen`/`word_builder` machinery fresh generation uses. Its rate is
  anchored to glottochronology's basic-vocabulary-replacement premise
  (~80-86% retention per 1000 years for stable core vocabulary), boosted by
  `contact_intensity` and scaled per entry by `lexicon_gen.STABILITY_TIER`
  (pronouns/numerals ~4x more resistant than nouns, nouns ~1.5x more than
  verbs/adjectives -- POS reused as the stability proxy, since it already
  captures the dominant real effect for a vocabulary this basic). Every
  non-replaced entry's spelling comes from the *one* evolved
  `RomanizationScheme` returned by `romanization_gen.evolve_romanization()`
  (freeze/reform + drift, decided per symbol -- see above) -- a reform is a
  language-wide convention change, not a per-word one, so it touches every
  word using the reformed symbol, whether or not that particular word's
  own sound moved this run (real spelling reforms work the same way: they
  land on every word with the affected pattern, not just ones whose
  pronunciation happened to shift). Only when the evolved scheme's
  rendering of a word's IPA agrees with what the *unreformed* base scheme
  would have produced (no reform touched any symbol it uses) *and* its
  sound is byte-identical to its original does an entry fall back to its
  stored spelling *verbatim* instead of the reconstruction -- preserves
  any real or curated exception a word's own spelling carries (e.g. a
  seed-example word's literal spelling) instead of silently "correcting"
  it, the same "why real orthographies end up with silent letters" freeze
  `evolve_romanization` already models per symbol. `notes` records
  `"unchanged"` (sound and spelling both untouched), `"conventional"`
  (spelling still matches the unreformed scheme -- whether or not the
  word's own sound moved), or `"reformed"` (some symbol the word uses was
  actually reformed -- again regardless of whether its own sound moved),
  for diagnostics (`experiments/evolution.py`'s report column). Replacement
  is decided first and, when it fires, bypasses all of this for that entry
  (a freshly coined/borrowed word has no old spelling to freeze to). One
  outcome per entry per call, not a fuller multi-stage history -- see
  limitations below. Reproducible: the whole pass is one
  seeded `random.Random`, consumed in lexicon order.

- **Per-language weighting (`traits.source_language_weights`)**: everything
  above describing multiple `source_languages` combining assumed they
  combine *unweighted* -- an equal-influence union/intersection/mean/
  first-match-wins/uniform choice, with no way to ask for "mostly French,
  somewhat German." `source_language_weights` (a parallel tuple to
  `source_languages`, empty meaning equal weight, not required to sum to
  1.0 -- normalized at the point of use by
  `reference_languages.match_profiles_weighted`) fixes that, threaded
  through every combination point in `romanization_gen.py`,
  `phonology_gen.py`, `grammar_gen.py`, and `word_class_gen.py`, plus
  `sound_change.py`'s own `lineage_weights` (mirrors `lineage_languages`'
  union-and-persist behavior, so a language's own historical weighting
  survives an evolution run that names no new contact language). The CLI's
  `--source-language` flag accepts an optional `NAME:WEIGHT` suffix
  (`--source-language "French:0.7" --source-language "German:0.3"`);
  `prompt_classifier.py` extracts an uneven split from wording like
  "mostly a French base, but with a noticeable German influence" the same
  way it extracts everything else, staying equal for a plain "mix of X
  and Y." Each *kind* of combination needed its own reasoned treatment,
  not one mechanical multiply-by-weight shortcut, since two genuinely
  different families exist: an **independent-roll** family (most of
  `romanization_gen.py`'s first-match-wins-with-its-own-roll functions,
  `word_class_gen.py`'s per-profile class-adoption roll) scales each
  candidate's own strength by its weight but iterates in *descending*-
  weight order and, critically, rescales every weight *relative to the
  heaviest matched profile* (`romanization_gen._by_descending_weight`) --
  not the raw sum-normalized weight -- so that two *equally*-weighted
  languages (today's default multi-language case) still reproduce a
  single named language's full roll strength, not a weaker one. A
  **union/pooling** family (`_resolve_joint_spellings`, `phonology_gen.py`'s
  boolean-any-to-weighted-fraction conversions, `_resolve_position_
  multipliers`' frequency-tier averaging) instead uses the raw
  sum-normalized weight directly, summing each *distinct contributing
  profile's* weight once (never once per matching entry -- a profile that
  curates multiple qualifying entries/symbols for the same combination
  point is deduped by `id(profile)`, not by weight value, since two
  different profiles can coincidentally share a weight) -- here a real,
  *intentional* behavior change is accepted even at equal weight, since a
  convention only part of the total named influence backs really is less
  certain than one every matched profile agrees on. One deliberate
  semantic generalization is called out explicitly where it lives:
  `phonology_gen._resolve_pair_restriction`'s onset/nucleus/coda-boundary
  blacklist combination is now **weighted-majority** (a pair stays
  forbidden only if the summed weight of blacklist-mode profiles
  forbidding it strictly exceeds the summed weight of those allowing it)
  rather than unanimous intersection -- identical to intersection for two
  equally-weighted disagreeing profiles (a tie resolves to "allowed"), but
  can diverge from it with three or more equally-weighted profiles that
  only partially agree (majority no longer requires unanimity). Whitelist
  combination stays a plain union regardless of weight in every case
  (onset-cluster/coda-cluster attested-data, pair-restriction whitelists,
  `word_class_gen`'s adopted-class pooling per profile) -- a permissive
  floor's whole purpose is inclusion, so weighting it down has no
  coherent reading the way weighting a restriction down does.
- **Invented harmony-conditioned classes and polysynthetic position
  classes**: `WordClass.condition`/`suffix_alt` (harmony/voicing-
  conditioned suffix allomorphy) and `WordClass.position_classes`
  (Navajo-style polysynthetic prefix slots) used to be reachable *only*
  through reference-profile adoption -- a language with no
  `source_languages` at all could never roll either mechanism, even when
  its own independently-rolled `SyllableStructure.vowel_harmony` or
  `GrammarProfile.morphological_type is POLYSYNTHETIC` said it plausibly
  should. `word_class_gen.generate_word_classes`'s *invented* path now
  gives an eligible POS's (NOUN/VERB/ADJECTIVE) class-marking roll a real
  chance, gated on `vowel_harmony`, to collapse into one real
  `condition="vowel_harmony"` class with front/back suffix allomorphs
  (via two `word_builder.build_class_suffix` calls, which gained an
  optional `harmony_class` parameter threaded straight into its existing
  `_choose_nucleus` call) instead of several independent flat classes; VERB
  specifically also gets a chance, gated on `morphological_type is
  POLYSYNTHETIC`, to collapse into a `position_classes`-bearing class via
  a new `_invent_position_classes` helper (1-2 slots, each a real null/
  zero-morpheme option -- mirroring Navajo's own real, most-common zero
  classifier -- plus 2-3 further options built via the existing
  `word_builder.build_class_prefix`). Neither collapse marks the POS as
  `any_multi_class` -- every word of that POS unconditionally takes the
  one resulting class, the same as a reference-adopted single class
  (Turkish's own real curated infinitive) never does either. `final_
  voicing` conditioning is deliberately *not* extended to the invented
  path: `build_class_suffix` is deliberately always vowel-initial (no
  onset, for its own phonotactic-safety guarantee), but `final_voicing`
  (real Persian `-tan`/`-dan`) needs a consonant-initial suffix --
  extending it would mean inventing a materially riskier new suffix
  shape, not exposing an existing one, and is left out rather than
  half-solved.
- Two smaller fixes rounding out the same batch: `word_class_gen.py`'s
  invented-class base rate for a part of speech a matched reference
  profile curates *nothing* for is now suppressed toward zero as
  `source_language_strictness` rises (`biased_probability(base_rate,
  -strictness)`) -- the same "matched but doesn't have it" treatment
  `grammar_gen.py` already gave `uses_root_and_pattern`, but previously
  missing here, so a strict single-language request could still invent a
  paradigm the named language shows no sign of having. And
  `prompt_classifier.py`'s system prompt gained an explicit instruction
  (plus a worked example: devout desert nomads/prayer/austere
  sun-scoured settlements -> `source_languages: ["Arabic"]`) generalizing
  the existing Dutch/windmills "atmospherically evoked" pattern: strong
  cultural, religious, or geographic imagery that real-world evokes a
  specific language or family justifies naming it even with no language,
  region, or ethnicity named outright, kept at low strictness (0.0-0.2)
  since the text isn't asking the conlang to *resemble* that language,
  only evoking its culture.

## Real inflection: case, tense, agreement, articles/copula, and grammar-level reference bias ("step 2")

The word/lexicon-level weighting batch above deliberately deferred one
gap: `GrammarProfile.word_order`/`has_articles`/`has_overt_copula`/
`adjective_after_noun` never consulted `source_languages` at all, and
`cases` was rolled but had **no consumer anywhere** -- the translator
only ever reordered bare citation-form words, never actually marking a
noun for case or inserting an article/copula even when the rolled
`GrammarProfile` said the language had the feature. This batch closes
both gaps.

- **Reference-profile curation + weighted bias (`grammar_gen.py`,
  `reference_languages/__init__.py`)**: six new optional fields
  (`real_word_order`/`real_alignment`/`real_has_articles`/`real_has_
  overt_copula`/`real_adjective_after_noun`/`real_case_count`, each
  `None`/abstains when uncurated) curated for a first representative
  batch of 16 profiles (French, German, Dutch, English, Japanese,
  Mandarin, Arabic, Turkish, Latin, Swahili, Korean, Thai, Russian,
  Polish, Hawaiian, Georgian) -- the rest stay uncurated, same "separate
  batches over time" precedent this project's own curation history
  already has. `grammar_gen.generate_grammar` now consults `match_
  profiles_weighted` for every one of these axes, built weighted from the
  start: `word_order`/`alignment` get the same "boost the matched value's
  own weight within the categorical roll" shape `morphological_type`
  already uses for `FUSIONAL`; `has_articles`/`has_overt_copula`/
  `adjective_after_noun` share a new local `_boolean_reference_bias`
  helper (boost toward the matched value, suppress toward its opposite at
  high strictness); `cases`' own *count* is nudged toward the weighted
  average of matched profiles' `real_case_count`, converging exactly to
  it (including a real, curated 0) at full weight/strictness. An
  ergative-absolutive language now draws its case labels from a separate
  `_ERGATIVE_CASE_LABELS` pool (ergative/absolutive/...) instead of the
  nominative/accusative-style labels, which never made sense for it -- a
  gap only surfaced while wiring the translator's own case marking.
- **`InflectionAffix` (`core/grammar.py`)**: a new value type for
  sentence-role-driven inflection (case, tense, subject agreement),
  deliberately distinct from `WordClass` -- see its own docstring for why
  (lexeme-fixed, chosen-once-at-coinage paradigm membership vs. a value
  applied fresh per sentence based on syntactic role; the two share only
  the low-level "attach a prefix/suffix, re-derive stress" mechanism,
  extracted into `word_builder.attach_affix_and_restress` so both
  `word_class_gen.apply_word_class` and the new `inflection_gen.apply_
  affix` can call it without `inflection_gen.py` needing to depend on
  `WordClass` at all). `GrammarProfile` gains `tenses` (an illustrative,
  source-language-independent 2-way `("past", "non_past")` vs. 3-way
  `("past", "present", "future")` coin flip) plus `case_affixes`/`tense_
  affixes`/`agreement_affixes` (`generation/inflection_gen.py`'s own
  `generate_*_affixes` functions, filled in by `generator.py` once the
  phoneme inventory exists -- the same two-phase relationship `plural_
  suffix`/`templates` already have). Agreement is keyed by this project's
  own 4 core pronoun glosses (`"I"`/`"you"`/`"he"`/`"we"`) plus
  `"default"` for any noun subject, not an abstract person/number grid
  this project's pronoun set doesn't otherwise use.
- **Conditional core vocabulary**: `lexicon_gen.CORE_MEANINGS` gained
  `("the", PARTICLE)`/`("be", VERB)`, coined only when `has_articles`/
  `has_overt_copula` is true (`lexicon_gen.CONDITIONAL_MEANINGS` maps the
  gloss to the gating `GrammarProfile` attribute) -- a language without
  the feature has no such lexeme at all.
- **`translator.py`'s own rendering primitives apply the inflection**:
  `_apply_case`/`_apply_verb_inflection` case-mark a noun/pronoun or
  tense+agreement-mark a verb/copula (the latter via one combined
  `InflectionAffix`, agreement keyed by this project's own 4 core pronoun
  glosses or `"default"`) whenever the caller names a label this
  language's own `GrammarProfile` actually has -- an unavailable/invalid
  label degrades to the bare citation form rather than raising. Each
  affix application seeds its own `random.Random` from a stable hash of
  `(language.spec.seed, a per-call salt)`, the same "hash the payload
  into a local seed" precedent `core.romanization._stable_local_choice`
  already uses, so translation stays reproducible without a public rng
  parameter. As of the LLM-drafted-plan rewrite below, *which* label (if
  any) to apply to a given word is decided by the sentence plan, not by
  scanning the English input for an article/copula/case cue.
- **Decoding it back out (`translate_to_english`) is generate-and-compare,
  not a parse** -- spelling isn't a clean invertible function in general
  (the same reason `sound_change.py`'s own reform-detection compares via
  `apply()` rather than string surgery). `_decode_noun`/`_decode_verb`
  render each candidate lexicon entry's own bare form and, if that
  doesn't match, each of its case/tense+agreement-marked forms via the
  identical `inflection_gen.apply_affix` path encoding used, comparing
  against the observed token.
- **Explicit scope limits, same "illustrative, not exhaustive" honesty as
  everywhere else in this project**: only one argument is ever
  case-marked per sentence; `genitive`/`dative`/`locative` labels exist in
  the case pool but stay unexercised (no possessive/oblique sentence
  pattern exists to attach them to); tense detection never recognizes a
  periphrastic English future ("will go").

## `translation/` -- bidirectional translation

- **`sentence_planner.py`**: an LLM drafts one sentence's own *structure*
  before any word is rendered -- word order, which arguments (if any) get
  case-marked, whether an article/copula/negation/conjunction appears,
  and a finite verb's tense/agreement -- as an ordered `SentencePlan` of
  `PlannedSlot`s (`kind="content"` names an English lemma/pos plus
  optional case/tense/agreement; `"article"`/`"copula"`/`"negation"`/
  `"conjunction"` are function-word slots). This replaces the two
  hand-written sentence shapes (predicate-adjective, subject-verb-object)
  `translate_to_conlang` used to pattern-match against. The LLM never
  invents a word's actual spelling -- see the module's own docstring for
  the LLM/deterministic-rendering boundary, the same "LLM picks among/
  describes deterministically-built material" principle `lexicon_gen.py`
  already established. Parsing is lenient (`generation/prompt_
  classifier.py`'s own "extract JSON, coerce field-by-field, degrade to a
  safe default" style); a totally unparseable response falls back to a
  trivial one-slot-per-content-word plan, the same word-for-word safety
  net `translator.py` always had. `llm/fake_client.py`'s
  `fake_strategy="sentence_plan"` deterministically reproduces the old
  two-pattern heuristic (plus a 3rd, always-available "one content slot
  per word" fallback) for tests and dry runs.
- **`translator.py`**: `translate_to_conlang()` calls `sentence_planner.
  plan_sentence()` then walks the plan's slots, rendering each via the
  existing `_lookup_or_coin`/`_apply_case`/`_apply_verb_inflection`
  primitives -- no sentence-shape branching left in this function at all.
  `translate_to_english()`'s decode is now per-token and
  structure-agnostic to match: an exact `by_form` match, else `_decode_
  noun` then `_decode_verb`, no positional assumption about which pool a
  given token belongs to. The decoded sequence is handed to the *same*
  pre-existing fluency-polish LLM call, its prompt generalized to
  describe `"(case: X)"`/`"(tense: X)"` annotations so a real model can
  reconstruct natural English word order/tense from them; the fake
  passthrough backend, having no real language understanding, doesn't
  attempt that reordering -- see the module docstring for the remaining
  explicit scope limits (single-clause only; noun-phrase-level
  coordination but no multi-clause/relative-clause/subordinate structure;
  no question formation; negation is one particle slot with no
  per-language position typology).
- **`names.py` (foreign proper names)**: the sentence plan has a `"name"`
  slot kind (the LLM planner identifies people/place names and never
  respells them; the fake planner treats a non-initial capitalized word as
  one), so "Bruno" is never coined as an ordinary word. How a language
  treats a name is the `GenerationSpec.foreign_names` trait (`"keep"` /
  `"adapt"`; CLI `--foreign-names`, "Foreign names" in the web UI); unset
  it derives from the matched `source_languages` via each reference
  profile's curated `foreign_name_handling` (Mandarin/Cantonese/Japanese/
  Korean/Thai/Vietnamese/Hawaiian adapt; Dutch/German/French/English/
  Spanish/Italian/Portuguese/Polish/Russian/Latin/Swahili/Turkish/
  Danish/Swedish/Norwegian keep), else keeps. **keep** uses the name as
  written (its guessed IPA is stored for pronunciation; no case affix, since
  its sounds may lie outside the inventory). **adapt** maps each guessed
  sound to the nearest inventory phoneme by feature distance and repairs
  the result to the language's syllable rules with an epenthetic vowel
  (dropping a consonant only as a last resort) -- deterministic, so the same
  name always gives the same form; it inflects like a noun. A name is stored
  as a `LexicalEntry` (`notes="proper name"`), so it is made once, reused
  after save/reload, decodes back through `by_form`, and is invisible to
  ordinary word lookups (the name "Rose" never stands in for the word
  "rose"). Known limits: possessive `'s` is dropped (no genitive marking
  yet), and the fake planner misses a sentence-initial name.
- **`expansion.py`**: `coin_word()` -- reuses `lexicon_gen.propose_word()`
  with a per-gloss RNG seed derived from `sha256(spec.seed, gloss)`, so
  coinage is reproducible independent of translation order.

## `speech/`

- **`reader.py`**: `lookup_pronunciation()` / `describe()` -- IPA and
  romanization lookup only.
- **`tts.py`**: real audio synthesis, mirroring `llm/base.py`/`llm/
  factory.py`'s own provider-agnostic-seam shape exactly (`TTSClient`
  `Protocol`, `build_tts_client(kind)` factory) -- `cli/main.py`'s own
  `pronounce --tts <kind>` never imports a specific backend directly.
  `"none"` (the default, same "cheap and dependency-free by default"
  precedent `build_llm_client(kind="fake")` already sets) reproduces the
  original text-only behavior. Two real backends, since they sound
  genuinely different and neither is a clear universal winner:
  `"espeak"` (espeak-ng, cross-platform once installed -- has no direct
  IPA input, so `ipa_to_kirshenbaum.py` converts to its own Kirshenbaum
  ASCII-IPA notation first, wrapped in its `[[...]]` bracket phonetic-
  input syntax) and `"sapi"` (Windows' own built-in `System.Speech`,
  invoked via a short PowerShell script rather than a new Python
  dependency -- no install at all, and it accepts literal IPA directly
  through SSML's `<phoneme alphabet="ipa">`, so no approximation step is
  needed; Windows-only, `synthesize()` returns `False` cleanly
  elsewhere).
- **`ipa_to_kirshenbaum.py`**: converts this project's own IPA notation
  (all ~195 symbols in `phonology_gen.ALL_CONSONANTS`/`ALL_VOWELS`) into
  Kirshenbaum, a real, documented ASCII-IPA scheme (not espeak-ng's own
  arbitrary notation). `_BASE_BY_IPA` covers every *plain* symbol
  directly; a genuinely exotic one (click clusters, pharyngealized/
  breathy/pre-aspirated consonants, apical-vs-laminal distinctions) falls
  back through a systematic modifier-stripping approximation (ejective/
  aspirated/palatalized/pharyngealized/breathy/length/nasalization/
  apical/laminal stripped one at a time, re-checking the base table each
  time, with length and nasalization *appended* via Kirshenbaum's own
  notation rather than silently dropped) toward the nearest representable
  phoneme -- illustrative, not exhaustive, the same honesty standard
  every other curated table in this project already holds itself to. A
  nasalized vowel (e.g. `"ã"`) is stored as one precomposed Unicode
  codepoint in this project's own pool, unlike every other modifier here
  (which is already its own standalone character) -- NFD-normalized
  before the fallback check so both cases share one code path. Tone and
  word-accent marks have no real espeak-ng equivalent at all (no lexical-
  tone input mechanism) and are dropped entirely, a known, permanent
  limitation, not something faked.

## `cli/main.py`

Typer app. `generate`/`translate`/`pronounce` are the core trio per AGENTS.md's
CLI discipline; `audit-lexicons` (curated-lexicon QA) and `serve` (the local
web UI) are separate utility commands that don't compete with that trio for
scope. `generate`'s `--source-language` (repeatable) and `--example`
(repeatable, `gloss=form` or `gloss=form|ipa`) are milestone-5 inputs;
`--evolve-from <name>` + `--years N` switch `generate` into evolving an
existing saved language instead of generating fresh, and `--years` alone
(no `--evolve-from`) evolves the freshly generated language itself before
saving -- `--prompt`/`--source-language` are reinterpreted as the evolution
period's own characteristics in the former mode (classified the same way,
just describing something different). `--word-strictness` is the separate,
real-*words* dial alongside `--strictness`'s own sounds-only one (see
`generation/real_words.py`); `--trait NAME=VALUE` (repeatable) sets one of
the 15 bipolar worldbuilding traits directly instead of relying on the
prompt to imply it (`_parse_trait_overrides`, validated against
`core.traits.GRADED_TRAIT_FIELDS`) -- a generic flag rather than 15
dedicated ones, the same repeatable `NAME=VALUE`/`Name:weight` shape
`--source-language` already established, keeping the CLI's own flag count
from scaling 1:1 with `TraitProfile`'s own field count. None of this adds a
new command. See `docs/CLI.md` for verified examples of all five commands.

## `experiments/`

Dev/evaluation tooling, not part of the CLI or the installed package -- the
way to actually look at what a generation-pipeline change did, instead of
reading code or one-off ad hoc scripts.

- **`showcase.py`**: `uv run python experiments/showcase.py` regenerates a
  local, standalone `experiments/output/showcase.html` (gitignored) with
  phonology + full lexicon tables for a fixed set of fresh-generation
  scenarios (defined at the top of the file -- add more there, nothing
  else needs to change). Word-level only; no grammar/translation shown.
- **`evolution.py`**: same idea for `sound_change.py` -- regenerates
  `experiments/output/evolution.html`, a real language's core vocabulary
  (`lexicons.py`; currently Dutch, hand-transcribed, covering every
  `CORE_MEANINGS` gloss) shown next to its evolved form across a range of
  `years`/direction scenarios, changed words highlighted. The calibration
  check for "close in time stays recognizable, far in time drifts a lot."
- **`lexicons.py`**: real seed vocabularies for `evolution.py`, one tuple
  of `(gloss, spelling, ipa)` per language -- add more languages here to
  extend the report.

## Known v0 limitations (intentional, not oversights)

- Several `TraitProfile` fields are extracted and stored but not yet
  consumed by generation: `social_hierarchy`, `evidentiality_culture`,
  `spatial_reference`, `ritual_register`, `taboo_register`,
  `terrain_communication_distance`, `salient_vocabulary_domains`.
  `orality_literacy` is consumed only by evolution's orthography-reform
  rate, not by fresh generation. The
  classifier-extracted `time_depth_years` is now the default for
  `GenerationSpec.evolve_years` (see "Real words and evolution" below).
- `source_language_strictness` reaches every reference-bias mechanism
  that exists (phonology's inventory/syllable-shape/tonal/vowel-harmony
  axes; `romanization_gen.py`'s category/per-symbol/grammatical-spelling
  rolls; `grammar_gen.py`'s `uses_root_and_pattern`/`FUSIONAL` boost, and
  now `word_order`/`alignment`/`has_articles`/`has_overt_copula`/
  `adjective_after_noun`/`cases` too -- see "Real inflection" above) --
  but only for the specific `ReferenceLanguageProfile`s actually curated
  for a given axis. The newer `real_word_order`/`real_alignment`/`real_
  has_articles`/`real_has_overt_copula`/`real_adjective_after_noun`/
  `real_case_count` fields exist for a first batch of 16 profiles, not
  all ~50 -- an uncurated-for-that-axis or entirely unmatched profile
  still falls back to the unbiased trait-only roll, same "abstain when
  uncurated" convention as every other optional field. An explicit
  `morphological_type` still has no matched-language bias at all (only
  `FUSIONAL`'s own boost, gated on `root_and_pattern` specifically, not a
  general `real_morphological_type` field). `source_language_strictness`
  also doesn't reach `sound_change.py`'s own, separate inventory-recompute
  path during multi-century evolution -- a strict language's phonology
  can still drift back toward looser/generic over a long evolution run,
  same as any other language's.
- `restricted_onset_consonants`/`attested_onset_clusters` are curated for
  German, English, French, Dutch, Italian, and Spanish -- every other
  profile leaves both empty (falls back to the generic sonority-only
  check, same "not yet curated" honesty `orthography` already
  practices). Italian's `coda_profile` is `"sonorant"`, which hardcodes
  `max_coda=1`/`allowed_coda_clusters=()` in `phonology_gen.py`
  regardless of any curated cluster list -- so `attested_coda_clusters`
  is deliberately left empty for Italian specifically (would be dead
  data), unlike the other five. The full local-
  adjacency family now covers all three positions in `(onset) nucleus
  (coda)`: onset+nucleus (`allowed_onset_nucleus_pairs`/
  `excluded_onset_nucleus_pairs`, e.g. real English "dw-"/"tw-" never
  preceding a rounded vowel; French's own `/w/` is blacklisted before
  every vowel except its three real attested ones, a/i/ɛ -- real French
  "wagon" is actually `/v/`, not `/w/`), nucleus+coda (`allowed_nucleus_coda_pairs`/
  `excluded_nucleus_coda_pairs`, e.g. real English `/ŋ/` only closing a
  syllable after a lax/checked vowel), and the cross-syllable
  `SyllableStructure.is_valid_boundary` (coda-then-next-onset, e.g. a
  word's own coda "p" immediately followed by the next syllable's own
  onset "d") -- all three resolved by the one generic
  `phonology_gen._resolve_pair_restriction`, all three consumed by
  `word_builder.py`. All three are deliberately pairwise (one adjacent
  pair at a time), never a combined onset+nucleus+coda check -- real
  phonotactic co-occurrence constraints are almost always local, and
  there's no verified English/German/French/Dutch example of a genuine
  non-decomposable three-way restriction (every pair fine on its own,
  the triple together not) to justify a fused mechanism. The
  cross-syllable-boundary field is empty for every profile -- real,
  solidly-verifiable, purely *combinatorial* (non-assimilation) facts of
  this shape are genuinely sparse for the four perfected languages (most
  real syllable-boundary phenomena in German/French/Dutch are
  assimilation/liaison processes, not a flat "this coda never precedes
  that onset," and this project's word-builder
  still has no morpheme/compound structure to distinguish a genuine
  cross-morpheme sequence like English "handbag"/German "Erdbeere" from
  ordinary syllable adjacency) -- so the cross-syllable mechanism mostly
  stands ready for a future language with a more clearly documented
  boundary restriction (e.g. a closed-syllabary language) rather than
  changing these four languages' own output today.
- `sound_change.py`'s six sound-change rules are illustrative, not
  exhaustive (none of them has diphthong-specific behavior -- a real
  diphthong monophthongizing over time, e.g., isn't modeled, though
  diphthongs *are* modeled at the phonology level now -- see
  `phonology_gen.py` above; lenition is single-step voiceless->voiced,
  not a fuller stop->fricative->zero chain).
  `force_isolated`/`force_high_altitude`/`force_tonal` aren't read during
  evolution (fresh-generation-specific concepts) -- only graded trait
  strength affects evolution rates. Orthography evolution (milestones 7-8)
  treats each lexicon entry/symbol independently for one `evolve_language`
  call -- a word can't be (e.g.) borrowed in one call and then drift
  further in a later one, since no per-word evolution history is tracked,
  only the current snapshot. Lexical replacement's "does the LLM judge this
  coinage plausible, or could an existing word's meaning plausibly drift to
  cover this sense" (the `brak`/`lam`-style reuse case) is deliberately not
  modeled yet -- current replacement coinage is purely rule-based
  (`word_builder`/sonority-constrained), not LLM-judged; that's the natural
  next step once `llm/cost_tracker.py`'s summary is actually surfaced
  somewhere and `AnthropicClient` uses native prompt caching for repeated
  system prompts, so adding more per-entry LLM calls here doesn't quietly
  balloon cost. Multiple languages influencing each other's vocabulary
  through ongoing contact (beyond one evolution period's one-way borrowing
  from a reference profile) isn't modeled -- it would need a way to
  represent an active relationship between two already-generated
  `Language` objects, a materially bigger piece of architecture than
  anything here.
- The typological tendency nudges and phoneme-pool prevalence values in
  `phonology_gen.py`/`grammar_gen.py`, and the reference-language sketches
  in `reference_languages/profiles/`, are illustrative approximations, not
  a typological database (e.g. PHOIBLE) or authoritative descriptions.
- `reference_languages/profiles/` covers 35 languages (Arabic, Arawakan,
  Bengali, Danish, Dutch, English, Finnish, French, Georgian, German,
  Hawaiian, Hebrew, Hindi, Hungarian, Icelandic, Indonesian, Italian,
  Japanese, Korean, Mandarin, Mongolian, Nahuatl, Norwegian, Pama-Nyungan,
  Persian, Polish, Portuguese, Quechua, Russian, Spanish, Swedish, Tamil,
  Tibetan, Turkish, Xhosa), chosen for
  typological/cultural spread (several -- Icelandic, Nahuatl, Tibetan,
  Mongolian, Arawakan, Pama-Nyungan, Quechua, Hebrew -- picked as much
  for real-world "vibe" association with popular fantasy settings as
  typological interest; Arawakan and Pama-Nyungan are families rather
  than single languages, and lean on looser illustrative sketches given
  thinner available attested-vocabulary knowledge), not a general "any
  named language" capability -- an
  unmatched name is silently ignored. External-file storage makes adding
  one mechanical, but the actual linguistic curation (what a real
  language's phonology and orthography look like) is still entirely
  manual -- the format change doesn't by itself scale that part up.
  Word-level algorithmic romanization systems (Korean revised
  romanization's cross-syllable consonant assimilation; Hindi/Devanagari
  schwa deletion) are also out of reach of this project's per-symbol
  adjacency-conditioned rules -- not attempted, not silently assumed
  covered.
- **The North Germanic batch** (Danish/Swedish/Norwegian/Icelandic) is
  curated to the same depth as English/German/French/Dutch/Italian/
  Spanish: phonotactic restrictions/clusters, per-position frequency
  tiers, a hand-counted `core_vocabulary_average_syllables`, curated
  orthography, and full stress data. Danish/Swedish/Norwegian didn't
  exist as profiles before this batch (created from scratch); Icelandic
  already had a real phoneme inventory and orthography rules and got the
  missing axes layered on. All four restrict `/ŋ/` and `/h/` from onset/
  coda respectively (the shared Germanic facts English/German/Dutch/
  Icelandic already modeled); Swedish/Norwegian additionally model a
  real retroflex series (`ʈ/ɖ/ɳ/ʂ`, the surface outcome of real `/r/` +
  dental sandhi -- "kort" -> `[kɔʈ]`) as independent phonemes restricted
  from onset but not coda, spelled "r"+letter (never marked as its own
  articulation in real spelling) -- a deliberate simplification over
  modeling the sandhi as a derivation rule. Swedish's real "sj-sound" has
  no exact symbol in this project's pool (the closest is `/x/`, flagged
  as an approximation the same way Italian's `/lʲ/` approximates `/ʎ/`)
  and gets a real, genuinely irregular multi-way weighted spelling
  (sj-/sk-/skj-/stj-/sch-); Norwegian's own less-extreme realization uses
  plain `/ʃ/` with a narrower real spelling spread instead. Icelandic
  additionally restricts its pre-aspirated series and `/h/` from coda,
  and its aspirated stops from coda too (aspiration is onset-conditioned
  in real Icelandic) -- and its own onset frequency tiers rank the
  aspirated stops *above* their plain counterparts, the reverse of every
  other profile's stop tiers, because real Icelandic's default
  word-initial realization of `/p,t,k/` is aspirated (plain stops mainly
  surface onset-medially after `/s/`). All four get `stress_pattern:
  "initial"` (the shared Germanic default); Icelandic's own
  `stress_deviation_rate` is notably lower than the mainland three's
  (its own stress is more rigidly initial than even German/Dutch's), and
  it deliberately gets `stress_driven_vowel_reduction: false` where
  Danish/Swedish/Norwegian get `true` -- a real typological split
  (Icelandic's own inflectional endings keep distinct full vowel
  qualities; mainland Scandinavian genuinely reduces toward schwa, Danish
  especially). Danish's stød and Swedish/Norwegian's pitch accent are now
  modeled -- see `WordAccentSystem` below (this bullet originally said
  they were deliberately left unmodeled; that's stale).
- **Word accent** (`core/phonology.py`'s `WordAccentCategory`/
  `WordAccentSystem`, `generation/word_accent_gen.py`) models real Danish
  stød and Swedish/Norwegian pitch accent as *one* mechanism, not two --
  historical Scandinavian linguistics treats them as different surface
  realizations of the same Common Scandinavian binary accent-1/accent-2
  contrast (accent 1 from originally-monosyllabic Old Norse forms, accent
  2 from originally-polysyllabic ones; Danish kept only the glottalization
  component, Swedish/Norwegian kept only the pitch contour), so one
  `realization` axis (`"glottalization"` | `"pitch"`) covers both rather
  than two unrelated features. Deliberately *not* built as an extension of
  `ToneSystem`: a tone language assigns pitch per syllable independent of
  stress, while word accent is exactly one contrast tied to the stressed
  syllable -- typologically distinct, so a language never rolls both
  (`generate_phonology` resolves `tonal` first and skips the word-accent
  roll entirely once it's won, and vice versa).
  - Architecturally closer to stress than to tone: tone is fixed *before*
    syllables are built (`word_builder.build_word`'s own long-standing
    docstring), but word accent -- like stress -- can't be decided until
    the accented syllable's own shape is known (Danish's default rule
    needs the real nucleus length/coda sonority), so it's computed right
    after `stress_index` in `build_word`, reusing the same collected
    `syllables` list. One genuinely easy-to-get-wrong detail: stress
    marking skips monosyllables (nothing to contrast against), but real
    Danish stød is *canonically* a monosyllable phenomenon ("hund"
    [hunˀ]) -- so the accented-syllable index defaults to `0` for a
    monosyllable even though `stress_index` itself is `None` there.
  - `core/romanization.py` owns `WORD_ACCENT_MARK` (U+02C0, non-combining,
    same "own token, not a combining decoration" status as `STRESS_MARK`)
    and `predict_default_word_accent` (same "lives in `core` because
    `apply()` needs it directly" reasoning as `predict_default_stress`),
    with two named patterns: `"monosyllabic_heavy"` (Danish) and
    `"underived_monosyllable"` (Swedish/Norwegian). Unlike stress, there's
    no generic cross-linguistic fallback -- most languages don't have
    this feature, so an uncurated profile just never enables
    `WordAccentSystem` at all, rather than falling back to some default
    typology.
  - The `"pitch"` realization reuses `core.phonology.TONE_DIACRITICS`'
    two combining characters (acute/grave) directly for its own two
    accent marks -- a practical reuse of already-proven-safe characters,
    *not* a coupling to `ToneSystem` (mutual exclusivity is what makes
    reusing the literal characters safe: within one scheme they can only
    ever mean tone or word accent, never both). `"glottalization"` marks
    only `ACCENT_1` (stød's real presence/absence shape); `"pitch"` marks
    both categories (a genuine two-way contrast).
  - Real Danish/Swedish/Norwegian orthography writes neither feature, so
    `RomanizationScheme.word_accent_marking` (mirroring
    `stress_accent_marking`) stays `""` for all three curated profiles --
    `apply()`'s job is purely to keep the IPA-internal marks from leaking
    into Latin output: `WORD_ACCENT_MARK` is consumed via a
    `word_accent_after` side channel in `_tokenize` (mirroring
    `stress_before`, so it's never emitted as a token in the first
    place), and the two pitch-realization diacritics are stripped from a
    vowel's `deco` before the existing tone-decoration logic could
    mistake them for real tone. An `"irregular_only"`/`"final_only"`-style
    rendering block (via `word_accent_marking == "marked"`) is a real,
    designed-for hook -- `RomanizationScheme`/`ReferenceLanguageProfile`
    both carry the field -- but not built, since no curated profile needs
    it yet.
  - `sound_change.py`: `word_accent` is copied through unchanged during
    evolution, same "grammar and tone system are copied from the base
    language unchanged" treatment `tone_system` already gets.
    `_coin_native_word` re-derives word accent from `lineage_profiles`
    (not the current run's `reference_profiles`, same reasoning as its
    own stress handling) via a new `word_accent_gen.mark_stress_and_word_accent`
    -- root_pattern.py's own templatic path uses the same function
    (replacing its earlier `stress_gen.mark_stress`-only call), since
    computing word accent for a flat, already-filled skeleton needs the
    actual stress *index* that `mark_stress` computed internally but
    never exposed. Two of the six sound-change rules needed a real fix
    for `WORD_ACCENT_MARK`, found by the same systematic audit
    `STRESS_MARK` got: `_apply_lenition` (via `_adjacent_real_symbol`,
    now skipping past `WORD_ACCENT_MARK` the same way it already skipped
    `STRESS_MARK`) and `_apply_final_devoicing` (a trailing
    `WORD_ACCENT_MARK` was hiding the real final consonant from a plain
    `tokens[-1]` lookup whenever the accented syllable was word-final --
    the common case). `_simplify_clusters`/`_apply_palatalization`'s own
    narrower interactions were judged benign (a word-accent mark sitting
    exactly at a syllable boundary resisting cluster simplification or
    blocking a coda-position palatalization check across that boundary),
    same judgment call `STRESS_MARK` got for the same two rules.
    `_apply_vowel_reduction`/`_apply_ejective_drift` are structurally
    immune (neither ever inspects a non-vowel, non-consonant token).
  - Curated for Danish (`glottalization`/`monosyllabic_heavy`), Swedish
    and Norwegian (`pitch`/`underived_monosyllable`) -- Icelandic
    untouched (no stød/pitch accent in real Icelandic).
- **The Finnish/Hungarian/Polish batch** brought a third trio to the same
  curation depth as the perfected profiles -- Finnish already had a real
  (if bare) profile (`kː` gemination, `vowel_harmony: true`); Hungarian
  and Polish were created from scratch. Researching their real phoneme
  inventories surfaced a genuine, shared gap in `phonology_gen.py`'s
  pool -- fixed there directly (not worked around), so every future
  language benefits:
  - A plain alveolar affricate pair `ts`/`dz` (real Hungarian/Polish
    "c"/"dz") joined `_STOP_AND_AFFRICATE_PAIRS` unconditionally (common
    enough cross-linguistically, same status as `tʃ`/`dʒ`); a new gated
    `_ALVEOLO_PALATAL_GROUP` (`tɕ`/`dʑ`, real Polish "ć"/"dź", genuinely
    distinct from "cz"/"dż") mirrors `_PALATALIZED_GROUP`'s own shape --
    typologically rarer, so it keeps its own base rate rather than
    joining the unconditional list. Three new long vowels `æː`/`øː`/`yː`
    (real Hungarian "ő"/"ű", Finnish's own long "ä"/"ö"/"y") joined
    `_VOWEL_EXTRAS`, each sharing its short counterpart's exact
    height/backness/rounded so `romanization_gen._short_counterpart`'s
    existing matching pairs them up with zero new code. All four
    consonants + three vowels needed entries added to `romanization_gen.py`'s
    three exhaustive fallback tables (`_DIGRAPH_TABLE`/`_DIACRITIC_TABLE`/
    `_MONOLETTER_TABLE`) -- every symbol in the shared pool must have one
    or it leaks as a raw IPA glyph; the diacritic table's entries reuse
    real, historically-attested single-Unicode-character IPA ligatures
    (ʦ/ʣ/ʨ/ʥ) for the four affricates. `sound_change.py`'s
    `_VOICELESS_TO_VOICED` gained `ts`->`dz` (and, via its own reverse-
    construction, `tɕ`->`dʑ`) so intervocalic lenition reaches them the
    same way it already reaches `tʃ`->`dʒ`.
  - A real bug surfaced while curating Finnish: the `gemination-style`
    `OrthographyCategory` only ever set `consonant_gemination_marked`,
    never `vowel_length_strategy` -- so Finnish's own long vowels fell
    through to the generic diacritic-style macron fallback (`aː`->`ā`)
    instead of real Finnish's own doubling convention (`aː`->`aa`).
    Setting the category's `vowel_length_strategy` to the existing
    `DOUBLING` value turned out to be a *different* real bug, not a fix:
    `VowelLengthStrategy.DOUBLING`'s actual implementation
    (`_generate_length_rules`) is syllable-conditioned, the same way
    real Dutch/German doubling genuinely is (single letter in an open
    syllable, doubled only in a closed one) -- but real Finnish doubles
    a long vowel *unconditionally* regardless of syllable shape ("maa"
    is a single open monosyllable, still doubled). No unconditioned-
    doubling strategy exists in this project yet, so the category was
    reverted to leaving `vowel_length_strategy` unset, and Finnish's own
    profile hand-curates each long vowel's real doubled spelling
    directly (`orthography: [{ipa: aː, latin: aa}, ...]`) instead --
    lower-risk than adding a new shared strategy variant for a single
    profile's real need.
  - Real, specific spelling facts curated: Hungarian's famous "reversed"
    convention (the letter "s" spells /ʃ/, plain /s/ is spelled "sz");
    real "ty"/"gy" mapped to the pool's own genuine palatal stops `c`/`ɟ`
    (not just palatalized alveolars); a real "j"/"ly" weighted spelling
    alternative for the same, historically-merged /j/ sound. Polish's
    real "w" letter (pronounced /v/) vs. the real *sound* /w/ (spelled
    "ł", not a dark l); a real "rz"/"ż" weighted alternative for the
    same, etymologically-split /ʒ/ sound; `coda_devoicing: true` (real,
    well-documented Polish word-final obstruent devoicing, same fact
    already modeled for Dutch/German) -- its own coda frequency tiers
    keep the devoiced-excluded voiced obstruents as harmless dead data,
    matching an existing precedent already in Dutch's own tiers rather
    than introducing a new pattern. Polish is also the first profile to
    curate `stress_pattern: "penultimate"` outright (real, robust fixed-
    penultimate Polish stress) -- already `predict_default_stress`'s own
    generic fallback, so this needed zero new logic, only a data
    addition.
- **The Arabic/Hebrew/Turkish batch** brought a fourth trio to the same
  curation depth -- unlike the prior three batches, all three already had
  real (non-bare) profiles (Arabic/Hebrew both `root_and_pattern: true`
  with a curated scholarly transliteration; Turkish already
  `vowel_harmony`/`coda_devoicing`), so this batch only extended the
  missing axes -- no new shared-pool symbols were needed.
  - Two real phoneme corrections surfaced while researching, fixed
    directly: Arabic's ج (jīm) was modeled as voiceless `tʃ`, but real
    Modern Standard Arabic jīm is voiced `/dʒ/`; Hebrew's rhotic was
    modeled as alveolar `r`, but real *Modern Israeli* Hebrew (what the
    profile's own `"ivrit"` alias targets) canonically has a uvular
    rhotic `/ʁ/`, the same real fact already curated for Danish/Swedish/
    French. Two more gaps surfaced while building Arabic's own frequency
    tiers: native `/b/` and the interdental fricatives `/θ/ð/` (ب ث ذ)
    were both missing from a profile that's supposed to model MSA's real
    consonant inventory -- added directly rather than silently working
    around a partition mismatch.
  - Real Arabic shadda (gemination) is now modeled, reusing the existing
    `_GEMINATE_GROUP` pool symbols (no new architecture) -- but this
    surfaced a genuine, separate bug in `root_pattern.py::generate_root`:
    a geminate consonant could be drawn as one of a word's own three
    *root* letters, which no real Semitic language does (gemination is a
    property the *template* imposes on an ordinary radical -- Form II
    verbs double the middle one -- never an inherent property of the
    root itself). Fixed generally in `generate_root` (excludes any
    `.long` consonant from the root-candidate pool, with a fallback to
    the unfiltered pool if that would empty it) rather than special-cased
    for Arabic, since the same real fact holds for any root-and-pattern
    language. Real Arabic transliteration also conventionally marks
    *both* vowel length (macron) and gemination (doubling) in the same
    system -- no existing `OrthographyCategory` did both (the existing
    `scholarly-macron-style` category Hindi/Bengali/Tamil also use has
    macron only, correctly, since none of those have productive
    gemination), so a new `scholarly-macron-gemination-style` category
    was added for Arabic specifically to point at.
  - Real Arabic diphthongs `/aj/`/`/aw/` (bayt "house", yawm "day") are
    now modeled too, with `/j/`/`/w/` restricted from true coda position
    (they're diphthong components there, not true consonant codas) --
    the same real fact and same fix shape English's own
    `restricted_coda_consonants` already uses.
  - Stress needed three genuinely different real treatments: Arabic's is
    quantity-sensitive (heavy-syllable-attracting), not a flat position
    -- modeled as `"lexical"`, the same "genuinely complex, no simple
    flat rule" catch-all English's own real stress system already uses.
    Hebrew and Turkish are both real, robustly word-**final** languages
    -- distinctive since most European languages aren't -- with Hebrew's
    own genuine penultimate ("milel") minority curated as a
    substantially higher `stress_deviation_rate` than Turkish's own
    narrower, more systematic exceptions (place names, "stress-neutral"
    suffixes).
- **The Russian/Serbo-Croatian/Portuguese batch** brought a fifth trio to
  the same curation depth. Russian and Portuguese already had real
  (non-bare) profiles; Serbo-Croatian didn't exist at all and was built
  from scratch. Two genuinely new architecture extensions were needed
  (both explicitly approved before implementation), plus non-major data
  additions reusing existing mechanisms.
  - **Word accent's tone+length axis** (`core/phonology.py`'s
    `WordAccentSystem.realization` gains `"pitch_and_length"`;
    `generation/word_accent_gen.py`): real Serbo-Croatian/BCMS has a
    genuine 4-way pitch accent (short/long x rising/falling on the
    accented syllable) -- more complex than the binary `WordAccentCategory`
    contrast built for Danish/Swedish/Norwegian, whose own code comment
    explicitly named this as the deferred case. Reuses the existing
    binary `WordAccentCategory` for the *tone* dimension only (`ACCENT_1`
    = falling, the historically older/conservative pattern; `ACCENT_2` =
    rising, the Neo-Štokavian retraction/innovation -- a genuine, if
    loose, historical-linguistic parallel to the Scandinavian older/newer
    framing already used, not just a convenient reuse) -- no new enum.
    *Length* is a new, orthogonal `bool` dimension, handled via wholly
    separate functions (`assign_word_accent_with_length`,
    `mark_word_accent_with_length`, `_TONE_LENGTH_DIACRITICS`) rather
    than overloading the existing binary `assign_word_accent`/
    `mark_word_accent`, so the proven Danish/Swedish/Norwegian path is
    untouched by construction. The four real, standard Slavistic
    accentuation marks: long rising = acute (U+0301, already reused from
    the binary system's own `ACCENT_1` mark -- note the *character*
    carries over, not the category pairing, since rising is `ACCENT_2`
    here), short rising = grave (U+0300, likewise reused), long falling =
    circumflex (U+0302, new), short falling = double grave (U+030F, new).
    `core.romanization.predict_default_word_accent` gained a new
    `accented_syllable_index: int = 0` parameter (default-safe for every
    other pattern) and a new pattern, `"initial_falling_elsewhere_rising"`
    -- the real, commonly-cited BCMS generalization: falling on a
    word-initial syllable or any monosyllable, rising elsewhere. Length
    itself is an independent curated bernoulli rate
    (`word_accent_length_rate`, mirroring `word_accent_deviation_rate`'s
    shape), not derived from word shape -- real BCMS length on the
    accented syllable is substantially lexical, the same honesty
    standard `stress_deviation_rate` already relies on.
    `word_accent_gen.resolve_word_accent` is now a 4-tuple
    (`realization, pattern, deviation_rate, length_rate`); every call
    site across `lexicon_gen.py`/`root_pattern.py`/`sound_change.py`/
    `phonology_gen.py` was updated. `core.romanization.apply()`'s
    pitch-mark leak-stripping set and its `"pitch"`-only check were both
    extended to also cover the two new characters and
    `"pitch_and_length"` -- real Serbo-Croatian standard orthography
    doesn't write pitch accent in ordinary text either (only specialized
    dictionaries do).
  - A smaller, related fix rode along: real Portuguese default stress is
    coda-conditioned but in the *opposite* direction from Spanish's
    existing `"penultimate_or_final_by_coda"` pattern (real Portuguese:
    penultimate only if the word ends in an unstressed a/e/o, final
    otherwise) -- reusing Spanish's pattern verbatim would have silently
    applied the wrong rule. New `predict_default_stress` pattern
    `"final_unless_unstressed_vowel"` needed a genuinely new
    `final_nucleus: str` parameter (not just the existing `final_coda`),
    threaded through `predict_default_stress`/`stress_gen.assign_stress`/
    `stress_gen.mark_stress`/`word_accent_gen.mark_stress_and_word_accent`/
    `word_builder.build_word`/`build_reduplicated_word` -- both "ends in
    a/e/o" and "ends in i/u" have an *empty* `final_coda` alike (both are
    vowel-final), so the coda alone genuinely can't distinguish real
    Portuguese's two cases the way it can for Spanish. Scanning generated
    example tables surfaced a real bug this same gap caused: `apply()`'s
    own `"irregular_only"` stress-accent rendering (real Spanish's á/é/
    í/ó/ú -- marks a word only when its actual stress deviates from the
    predicted default) calls `predict_default_stress` directly too, and
    that call site was missed when `final_nucleus` was added -- it always
    passed an empty string, so Portuguese's own accent-marking silently
    always predicted "final" stress regardless of the word's real final
    vowel, both over- and under-marking words depending on which way the
    real default actually went. Fixed by deriving a `final_nucleus_symbol`
    in `apply()` the same way it already derives `final_coda_symbols` (the
    last vowel token in the word's own tokenized IPA) and threading it
    through; a new regression test
    (`test_irregular_only_marking_uses_the_words_own_final_nucleus_not_just_its_coda`
    in `test_romanization.py`) locks in both directions of the fix, since
    no existing test exercised `apply()`'s `"irregular_only"` path at all
    before this batch.
  - **Real Serbo-Croatian syllabic /r/** (vrt "garden", trg "square", Krk,
    prst "finger" -- a whole syllable with no vowel at all, /r/ itself
    carrying the nucleus) turned out to need *no* new core-engine
    architecture: `PhonemeInventory` already separates `consonants`/
    `vowels` purely by which list an entry sits in, with no deeper
    structural "is this really a vowel" check anywhere in
    `word_builder.py`/`sonority.py`. Modeled as one more `Vowel` pool
    member in `phonology_gen.py`'s `_VOWEL_EXTRAS` -- IPA `"r̩"` (U+0329
    COMBINING VERTICAL LINE BELOW, the real standard IPA syllabic-
    consonant diacritic), low prevalence (~0.04, matching this pool's own
    established "rare exotic member" rate, e.g. y/ø/œ) -- which slots
    into onset/nucleus/coda selection, frequency tiers, stress, and
    romanization through the exact existing machinery every other vowel
    already uses, with zero changes to selection/tokenization code (the
    tokenizer already handles a base symbol plus trailing combining mark
    correctly, the same mechanism nasalized vowels ã/ẽ already rely on).
    Safe for every other language by construction -- opt-in pool data, no
    existing profile referenced `"r̩"` before this batch, same status the
    ts/dz/tɕ/dʑ/long-vowel pool additions had in the Finnish/Hungarian/
    Polish batch. Real Serbo-Croatian spells syllabic /r/ identically to
    consonantal /r/ ("vrt", not "vr̩t") -- one curated `{ipa: "r̩", latin:
    r}` orthography rule, plus a `"r̩"` -> `"r"` fallback entry added to
    all three of `romanization_gen.py`'s exotic-style tables (digraph/
    diacritic/monoletter), per the established "every pool symbol needs a
    fallback entry or it leaks as raw IPA" rule.
  - **Non-architectural, reused-mechanism work**: real Russian
    palatalization is far more pervasive than the 4 symbols
    (`tʲ`/`dʲ`/`nʲ`/`lʲ`) `phonology_gen.py`'s `_PALATALIZED_GROUP`
    originally had -- extended the *same* group (more members, same
    selection mechanism) with `pʲ`/`bʲ`/`mʲ`/`fʲ`/`vʲ`/`sʲ`/`zʲ`/`kʲ`/
    `xʲ`/`rʲ`, with matching fallback-table entries (same real scholarly
    soft-sign apostrophe convention, e.g. `pʲ` -> `p'`) in all three
    `romanization_gen.py` exotic styles and in Russian's own profile
    orthography. Russian's profile also curates real akanye/ikanye
    (`stress_driven_vowel_reduction: true`) and its famously "free"
    lexical stress (`stress_pattern: "lexical"`, a high deviation rate --
    same "genuinely complex, no simple flat rule" catch-all English's own
    real stress system uses).
  - **Follow-up, closing the remaining Russian palatalization gaps**:
    completed the velar palatalized series by adding `gʲ` (real, if
    marginal/allophonic, before-front-vowel palatalization on г, the same
    status `kʲ`/`xʲ` already had) to `_PALATALIZED_GROUP`. Considered and
    *declined* adding `ʃʲ`/`ʒʲ` (an earlier `DEFERRED.md` note listed them
    as a gap) -- real Standard Russian ш/ж are canonically the language's
    "always hard" unpaired fricatives, with no phonemic soft counterpart,
    so there was nothing real to add; the note was corrected instead of
    the pool. Added the real hard/soft contrast Russian's plain л always
    had but this project didn't yet model: `ɫ` (velarized "dark l", the
    true phonetic value of unmarked л, distinct from the already-modeled
    palatalized `lʲ`) as a new `_REFERENCE_ONLY_CONSONANTS` member (no
    `velarized` field on `Consonant` -- modeled as its own atomic symbol,
    the same way affricates/clicks already are). Added `ɕː`, replacing
    plain `ɕ` as this profile's spelling of щ -- real Russian щ is always
    long with no plain short counterpart, unlike the rest of the
    palatalization series (`Consonant.long` on a `_REFERENCE_ONLY_CONSONANTS`
    member, the geminate group's own existing flag). All three symbols got
    matching entries in every downstream table the completeness tests
    require (`romanization_gen.py`'s three exotic styles;
    `ipa_to_kirshenbaum.py` needed only `ɫ` explicitly -- `gʲ`/`ɕː` already
    resolve through its existing modifier-strip/length-suffix fallback).
    Russian's own profile (consonant list, onset/coda clusters, frequency
    tiers, orthography) and its 494-word curated lexicon were updated to
    match, converting every bare `l`/`ɕ` IPA token to `ɫ`/`ɕː` via the real
    tokenizer (not a blind string substitution -- see the equivalent
    caution in the stress-mark fixes above) after cross-checking each
    resulting onset/coda cluster against the actual real word behind it;
    this also surfaced one pre-existing, unrelated data bug (*сильный*
    "strong" stored with a hard л where the real word has a soft one, and
    a matching typo in its own curated spelling) and two stale/mislabeled
    `attested_*_clusters` comments (*для* tagged as a hard `[d, l]` cluster
    when the profile already separately, correctly had `[d, "lʲ"]`; *рельс*
    tagged `[l, s]` when real рельс has a soft л) -- fixed alongside the
    main change since they're the same class of error. Real akanye/ikanye
    vowel-reduction completeness in the lexicon transcriptions themselves
    (as opposed to the `stress_driven_vowel_reduction` rule the profile
    already curates) remains open, `DEFERRED.md` updated accordingly.
  - As with every prior phoneme-pool extension, adding new consonant/
    vowel pool members shifted downstream RNG draw sequences for
    *unrelated* fixed-seed tests (new `rng.random()` calls happen during
    every run's phonology selection, regardless of which language is
    being generated) -- re-found working seeds for
    `test_french_biased_language_gives_its_verb_entries_a_silent_r` (11
    -> 3) and `test_a_reformed_symbol_still_changes_a_word_whose_own_sound_never_moved`
    (8 -> 14), same "seed-shift from new content" pattern documented
    elsewhere in this history, not a functional regression.
- **The Hindi/Tamil/Persian batch** brought a sixth trio to the same
  curation depth -- the first of these batches needing *no* new
  architecture at all: research into each language's real stress
  confirmed all three reuse an *existing* `stress_pattern` bucket. Real
  Hindi stress is genuinely quantity-sensitive (heaviest syllable in a
  3-syllable window from the right edge, default penult when all light,
  with a real, unresolved dispute in the literature over whether it's even
  phonetically robust) -- modeled as `"lexical"`, the same catch-all
  Arabic's own quantity-sensitive stress already uses, with a deviation
  rate (0.40) a touch above Arabic's own 0.35. Real Tamil is fixed
  word-initial with a narrow, mechanical exception (shifts to syllable 2
  when syllable 1 has a short vowel) -- `"initial"`, deviation 0.10. Real
  Persian is robustly word-final, with a real, systematic (not scattered)
  exception -- the whole verb word-class, personal suffixes never
  stressed, the negative prefix pulling stress to the initial syllable
  instead -- `"final"`, deviation 0.20, comparable order of magnitude to
  Turkish's own 0.18. None of the three has lexical tone or phonemic pitch
  accent -- `word_accent` stays uncurated for all three.
  - One non-major shared-pool addition rode along: real Tamil /ɻ/ (ழ), a
    retroflex approximant genuinely distinct from both the tap /ɾ/ and
    trill /r/ already modeled, and common enough to be in the language's
    own name (தமிழ் "tamiḻ"). Added to `phonology_gen.py`'s
    `_APPROXIMANT_POOL` (opt-in pool data, same shape as every prior
    batch's shared-pool additions), with fallback entries in all three of
    `romanization_gen.py`'s exotic-style tables and Tamil's own explicit
    `{ipa: "ɻ", latin: "ḻ"}` orthography rule (real ISO 15919/scholarly
    transliteration, the same retroflex dot-under convention `ʈ`/`ɳ`
    already use).
  - Real Tamil genuinely has no tautosyllabic consonant clusters at all
    (`max_onset: 1`, already accurate) and codas restricted to nasals/
    liquids/the glide /j/ -- fixed `coda_profile` from `unrestricted` to
    `sonorant` (well precedented: Italian already uses this value). Real
    Tamil retroflex `ʈ`/`ɳ`, velar `ŋ`, and the new `ɻ` also categorically
    never open a native word -- `restricted_onset_consonants`. This
    surfaced a real bug in this batch's own first draft: a symbol placed
    in `restricted_onset_consonants` must NOT also appear anywhere in
    `onset_frequency_tiers` (that field's own legal-symbol set is computed
    as `consonants - restricted_onset_consonants`, the same rule Polish's
    own excluded `ɲ` already establishes) -- caught by inspection before
    committing, since the initial draft had copied the "nothing legal left
    for that slot" comment from Polish's precedent without actually
    removing the restricted symbols from the tier list itself (the same
    mistake was independently made and fixed in Hindi's own `ɳ`
    restriction). Distinct from `coda_devoicing`/`coda_profile: sonorant`
    exclusions (Russian/Polish/Serbo-Croatian's coda-devoiced consonants,
    Tamil's own sonority-filtered obstruents), which aren't reflected in
    that computed legal-symbol set at all and so *are* correctly left in
    their tiers as harmless "dead data," the same precedent those
    profiles already established. With `coda_profile: sonorant`, Tamil
    also follows Italian's own established precedent of leaving
    `coda_frequency_tiers` uncurated entirely (checked via its own
    dedicated test, mirroring Italian's) rather than building a
    same-shaped table, since the true legal coda set (after sonority
    filtering) isn't fully expressible through `restricted_coda_consonants`
    alone. Real Tamil's own actual medial clusters (homorganic nasal+stop:
    taṅkam "gold"; liquid+stop: tīrppu "verdict") are cross-syllable, not
    tautosyllabic, and already emerge for free from a sonorant-only coda
    meeting an unrestricted next-syllable onset, needing no
    `attested_coda_onset_pairs` curation either.
  - Real Hindi has genuine onset clusters (mostly Sanskrit-derived tatsam
    vocabulary: prem, kram, grām, dvār, svar, śrī, bhram) and rich coda
    clusters driven by real, productive schwa deletion/syncope -- Hindi's
    Devanagari orthography implies open CV syllables, but the spoken
    language is full of closed CVC ones because an orthographic short "a"
    is regularly not pronounced (dharm, garv, arth, karṇ, ant, mast,
    bhakt, gupt, mitr) -- the hand-counted average-syllable-length figure
    was counted on these *pronounced* forms, not the orthographic akṣaras,
    to avoid making the language look artificially longer/more open than
    it actually is. Real Persian has no native onset clusters at all
    (`max_onset: 1`, loanword clusters get an epenthetic vowel) but real,
    common 2-consonant codas (dast, sæxt, bolænd, særd, goft, gænj).
- **The Mandarin/Japanese/Korean/Mongolian batch** brought a seventh
  quartet to the same curation depth. Unlike every prior batch, one of
  its architecture pieces was explicitly approved as a *major* extension
  up front (asked via direct question, per this whole session's own
  "ask before major work" pattern): real Japanese has a lexical pitch
  accent, but it's a genuinely different kind of system from every
  word-accent mechanism this project had built (Danish stød, Swedish/
  Norwegian pitch, even Serbo-Croatian's own 4-way tone+length) -- those
  all pick *one of a fixed number of categories* for the whole word;
  real Japanese instead contrasts words by *where* (if anywhere) a
  single pitch drop falls, with up to n+1 real patterns for an
  n-syllable word. `WordAccentCategory`'s own docstring had explicitly
  named this as a separate, bigger extension "not attempted here" (and,
  found while touching that docstring, was already stale from the
  Serbo-Croatian batch -- still said "binary by design... not attempted
  here" despite `pitch_and_length` having already shipped; both
  `WordAccentCategory` and `WordAccentSystem`'s docstrings are fixed
  here to correctly list all four realizations).
  - **`generation/word_accent_gen.py`**: new
    `assign_positional_pitch_accent(rng, num_syllables, strictness) ->
    int | None` and `mark_positional_pitch_accent(kernel_index,
    num_syllables) -> tuple[str, ...]`. A real, deliberate simplification
    versus every prior word-accent extension: real Japanese kernel
    placement is genuinely lexically arbitrary (not predictable from
    shape the way stress/stød/pitch all are), so there's no "predict a
    default, then deviate" step at all -- just a uniform random pick
    among the real n+1 patterns (honestly uniform, not weighted, since
    this project has no solid frequency data to justify any particular
    skew). The mark function implements the real Tokyo-dialect H/L rule
    (syllable 0 is Low unless the kernel *is* syllable 0; syllables 1
    through the kernel are High; everything after is Low; unaccented
    words are Low-then-High-forever with no drop), reusing the exact
    same two `TONE_DIACRITICS` characters `"pitch"` already reuses -- no
    new Unicode characters introduced by this realization at all. A
    second, explicitly documented simplification: real Japanese pitch
    accent is per-*mora* (a long vowel or the moraic-nasal coda adds a
    mora without adding a syllable); this project's entire stress/tone/
    word-accent machinery is syllable-counted throughout, and redefining
    the counting unit project-wide was judged out of scope for this
    batch -- modeled per-syllable instead, flagged as an approximation
    in the new functions' own docstrings.
  - Marks potentially *every* syllable, not one -- a real structural
    difference from every prior realization, which all compute exactly
    one mark and place it on one syllable (`accented_index`). Required
    reshaping `word_builder.build_word`/`build_reduplicated_word` and
    `word_accent_gen.mark_stress_and_word_accent`'s own mark-placement
    step from a single `accent_mark`/`accented_index` pair into a
    uniform per-syllable `accent_marks` array -- byte-identical behavior
    for every existing realization (just reshaped: `accent_mark if i ==
    accented_index else ""`), with the new realization filling the whole
    array directly instead.
  - A second, non-major architecture piece rode along: real Mongolian
    stress (Svantesson et al.) falls on the first syllable with a long
    vowel/diphthong, else the initial syllable -- none of the existing
    `stress_pattern` buckets capture that, and unlike every prior new-
    pattern addition it needs to know about *every* syllable's own
    nucleus, not just the final one. New `predict_default_stress`
    pattern `"first_long_vowel_else_initial"` plus a new
    `first_long_syllable: int | None` parameter, fed by a new
    `stress_gen.first_long_vowel_index` helper (checks for the `"ː"`
    character, the same convention every long-vowel pool symbol already
    uses, so no dependency on `core.phonology.Vowel` itself) -- threaded
    through `assign_stress`/`mark_stress` and every call site, plus
    `apply()`'s own `"irregular_only"` re-derivation (proactively, this
    time, having already found and fixed the identical *missed* call
    site for `final_nucleus` in the Russian/Serbo-Croatian/Portuguese
    batch). This pattern only has any effect if the target language's
    own vowel inventory actually includes long vowels -- Mongolian's
    profile previously had none at all, despite real Mongolian vowel
    length being phonemic and highly productive (уул uul "mountain",
    чулуу chuluu "stone"), so `aː`/`eː`/`iː`/`oː`/`uː` were added
    there too, reusing the existing shared pool.
  - Real Japanese gemination (sokuon っ, real Hepburn doubled-letter
    spelling: がっこう gakkō, きって kitte) needed zero new architecture:
    the shared geminate pool already has `kː`/`tː`/`pː`/`sː`, and
    `scholarly-macron-gemination-style` (built for Arabic, combining
    macron vowel-length with doubled-letter gemination) is an *existing*
    category that's exactly the real Hepburn shape Japanese needs -- pure
    profile-level curation. Real Japanese long vowels (chōon: お母さん
    okāsan, 東京 Tōkyō) were added alongside gemination for the same
    reason Mongolian's were -- it would be an incomplete account of real
    Japanese phonology, and of a category built to mark both together, to
    model one without the other. A genuine pre-existing correction
    surfaced while reviewing Japanese's own inventory: `"ʔ"` (glottal
    stop) was in its consonant list, but real Japanese has no phonemic
    glottal stop -- removed.
  - Real coda restrictions curated for three of the four, each a
    genuine, well-documented fact: Mandarin only ever closes a syllable
    in /n/ or /ŋ/ (never m/l/j/w, all otherwise legal under its own
    `coda_profile: sonorant`); Japanese only in the moraic nasal (spelled
    "n") or a geminate's own first half; Korean's real "seven-consonant
    rule" neutralizes its whole aspirated/tense/ affricate/fricative
    series down to a plain unreleased stop in coda position, leaving
    exactly p/t/k/m/n/ŋ/l legal (with j/w excluded outright -- they form
    diphthong nuclei in Korean, never a true coda). Mandarin and Korean's
    own /ŋ/ also got a matching *onset* restriction -- real /ŋ/ never
    opens a native syllable in either language. A real correctness bug
    surfaced and was fixed while curating these: a symbol placed in
    `restricted_onset_consonants` must never also appear in
    `onset_frequency_tiers` (that field's own legal-symbol set is
    computed as consonants-minus-restricted, the same rule Polish's own
    excluded `ɲ` already establishes) -- caught in both Korean's and (a
    second, independently-made instance of the identical mistake)
    Hindi's earlier `ɳ` restriction, both fixed.
  - Mandarin and Japanese's own `coda_profile: sonorant` meant
    `coda_frequency_tiers` had to stay uncurated for both, checked
    separately from `onset`/`nucleus`, the same established Italian/
    Tamil precedent (the true legal coda set under sonority filtering
    isn't fully expressible through `restricted_coda_consonants` alone).
    Korean, by contrast, uses `coda_profile: unrestricted` plus an
    explicit `restricted_coda_consonants` list that exactly matches its
    own real 7-consonant surface inventory, so its `coda_frequency_tiers`
    was safely curated in full, English's own `restricted_coda_consonants:
    [j, w]` precedent confirming the "excluded symbols don't appear in
    the tiers at all" rule for this specific mechanism.
  - Real Mandarin has a genuine, well-documented "neutral tone" (轻声)
    phenomenon that plays a stress-like prosodic role, and real Korean
    genuinely has neither phonemic stress nor tone in the standard (Seoul)
    dialect -- neither is modeled: Mandarin's neutral tone is lexically/
    grammatically conditioned (obligatory on a closed class of function
    morphemes, otherwise a lexical property of specific words), not a
    flat rule a phonologist would encode safely, the same "real but not
    rule-capturable" reasoning that already keeps Hindi's own schwa
    deletion out of scope; Korean's own `stress_pattern`/`word_accent`
    both stay honestly uncurated.
  - Word-length counting conventions were made explicit per language,
    the same caveat this project already gives every prior batch's own
    counting choices: Mandarin counted at the *word* level (太阳 tàiyáng
    "sun"), not the morpheme level, since Mandarin's famous
    "monosyllabic" reputation is really about morphemes, not everyday
    words (landing close to Danish/Swedish's own figures, not near 1.0);
    Korean counted using full dictionary citation forms (stem + real -다
    -da suffix, e.g. 크다 keuda "big"), consistent with how every other
    profile in this project counts (real infinitives for Russian/
    Portuguese/Hindi), even though this pushes the figure noticeably
    higher than a bare-stem count would.
  - Two real gaps surfaced from scanning generated example tables (the
    Mandarin/Korean batch's own equivalent of the Portuguese
    `irregular_only` bug found the same way in an earlier batch), both
    fixed directly:
    - Real Mandarin /ɕ/ (pinyin `x`, this project's own `"ʃ"` stand-in)
      is in complementary distribution with the retroflex/alveolar
      sibilant series -- it only ever precedes /i/ or /y/ (ü); there's no
      real pinyin syllable like "xang". `mandarin.yaml` now curates
      `restricted_onset_nucleus_pairs` blacklisting `ʃ` against
      a/u/o/e (the existing English `w`+rounded-vowel mechanism, already
      built for exactly this shape, just never used by this profile
      before). A second, unrelated pinyin-spelling gap surfaced
      alongside it: real pinyin spells the /u/+/ŋ/ rime "ong" (dong,
      long, hong...), not "ung" -- a genuine, specific orthographic
      convention, not this profile's own default identity spelling for
      "u" elsewhere -- fixed with a `following: ["ŋ"]`-conditioned
      orthography rule.
    - Real Korean Revised Romanization spells its plain/lax stop series
      with a position-conditioned letter -- b/d/g in onset, p/t/k in
      coda (바 ba vs. 밥 bap, 다 da vs. 몯 mot) -- not one fixed letter
      regardless of position; the aspirated series, by contrast, is
      spelled p/t/k uniformly. `korean.yaml` previously curated neither,
      so the plain series fell through to plain-letter identity spelling
      and the aspirated series fell through to `digraph-style`'s own
      generic capital-H fallback (`pH`/`tH`/`kH`) -- not a real Korean
      convention at all. Fixed with the existing `following: [vowel]` /
      `following: [consonant, boundary]` neighbor-tag mechanism (already
      used elsewhere for onset-vs-coda-conditioned spelling) for the
      plain series, and three unconditional rules for the aspirated one.
- Dutch's `g`/`ch` distinction is now modeled: /ɣ/ (voiced velar
  fricative -- what Dutch `g` actually represents; Dutch has no native
  /g/ stop) is a real phoneme in `phonology_gen.py`'s shared pool, Dutch's
  profile lists it, and its orthography rule (`ɣ` -> `g`, distinct from
  `x` -> `ch`) is in `reference_languages/profiles/dutch.yaml`.
  `experiments/lexicons.py` uses /ɣ/ directly rather than approximating
  with /g/. Dutch's *morphophonemic* spelling convention -- a word-final
  /ɣ/ that surfaces as devoiced [x] is still spelled `g` (e.g. "berg",
  "hoog"), not `ch` -- is now modeled too, for both paths orthography can
  take during evolution: words carried through unchanged already reused
  their verbatim old spelling; a word whose spelling gets freshly
  reconstructed after this exact devoicing happens *this run* now also
  gets it right, via `sound_change.py`'s `_evolve_ipa` (see its own
  docstring) handing the reconstruction step a spelling-oriented IPA
  string that reverts the devoicing, generalized to any voiced/voiceless
  pair (not Dutch-specific -- the same principle covers German's real
  "Rad"/"Tag" pattern). One related, smaller gap stays unmodeled: "g is
  not written before k" -- a morpheme-boundary assimilation-spelling
  rule (compounding/affixation contact), needing capability (morpheme-
  boundary awareness across coined words) this project doesn't have.
- *Automatic*, probabilistic whole-scheme `OrthographyCategory` reform
  during evolution isn't modeled -- `evolve_romanization()` carries
  forward a language's own category (`_category_from_scheme`) rather than
  ever spontaneously swapping it, so a language can't undergo something
  like China's real 1958 Wade-Giles -> Pinyin standardization *on its own*
  the way it already can undergo *symbol-level* reform (freeze/reform/
  drift, per `RomanizationRule`) -- would need its own reform-rate model
  at the scheme level, not the per-symbol one that exists today. A
  *deliberate*, user-triggered version of the same thing already exists,
  though: passing `forced_orthography` (e.g. `--orthography-style`) to
  `--evolve-from` explicitly reforms the category on that run.
- French-style word-final mute letters and German-style noun
  capitalization are now modeled, as a **citation-form spelling
  convention keyed on part of speech** -- `core.romanization.
  GrammaticalSpelling` (`capitalized_pos`, `all_caps_pos`,
  `mute_suffix_by_pos`), applied via the module-level
  `apply_grammatical_spelling(scheme, latin, pos)` right after every
  `RomanizationScheme.apply()` call site (`lexicon_gen.py`,
  `root_pattern.py`, `sound_change.py`'s `evolve_language`), since
  `apply()` itself deliberately stays a pure function of an IPA string
  with no grammatical context. `romanization_gen.py`'s
  `_roll_grammatical_spelling` rolls three independent axes: a low-rate
  capitalization roll boosted when a matched reference profile declares
  `capitalized_pos` (German, today); an even rarer all-caps roll, gated
  entirely behind `GenerationSpec.allow_all_caps` (default off, no real
  language does this); and a mute-suffix roll that reuses a matched
  profile's own `mute_suffix_by_pos` when one exists (French's
  infinitive "-r") or invents one otherwise. `evolve_romanization`
  carries a language's `grammatical_spelling` forward unchanged rather
  than re-rolling it, so the convention stays stable across evolution.
  What's still explicitly out of scope: real sentence-by-sentence
  agreement (a word capitalized only when it's the grammatical subject,
  a mute letter that appears only in some inflected forms) -- this
  project has no live inflectional system to hang that on
  (`GrammarProfile.plural_suffix`/`cases` are still generated but have
  zero consumers -- `word_classes`/`word_class_deviation_rate`, added
  alongside them on the same model, are the one exception, a real fixed
  *citation-form* shape rather than sentence-context-driven agreement;
  see `word_class_gen.py`'s own section above); and specific-word
  capitalization (e.g. English "I"), dropped because keeping it
  consistent across a pronoun's variants ("he"/"she"/"it") has no
  foothold in today's one-word-per-gloss `CORE_MEANINGS` lexicon model.
- Consonant gemination and palatalization -- both surveyed and initially
  deferred as needing a phoneme feature this project didn't model -- are
  now modeled (`Consonant.long`/`Consonant.palatalized`,
  `consonant_gemination_marked`, the `gemination-style` anchor; see
  `phonology_gen.py`/`romanization_gen.py` above). Korean's cross-syllable
  consonant assimilation and Hindi/Devanagari's schwa deletion, from that
  same survey, stayed out of reach for the reason already given above
  (word-level algorithmic systems, not per-symbol rules) until the
  word-level-phonology batch much further down this history built a
  reusable mechanism and closed schwa deletion (Hindi and, as a sibling,
  Bengali); Korean's own consonant assimilation is still open.
- Grammar generation (`grammar_gen.py`) is intentionally not being iterated
  on right now -- current focus is word-level (phonology/lexicon) quality.
  Notably, word order isn't linked to any trait yet (only morphological
  type/alignment are).
- A seed example's *phonemes* are guaranteed to be in the inventory; its
  *syllable shape* is not validated against the generated
  `SyllableStructure` (would need real syllabification of arbitrary input).
  Sentence-level seed examples are unimplemented (word-level only).
  Seed examples default to `PartOfSpeech.NOUN` -- no POS guessing.
- Onset/coda clusters cap at 2 consonants; no 3-consonant clusters (e.g.
  English "str").
- The classifier's calibration (avoiding over-eager or cascading inference
  from incidental prompt details, in either direction) is prompt-engineered,
  not testable by a unit test -- only checked manually against real prompts
  through `--llm anthropic`.
- Translation recognizes three sentence shapes only; no real syntactic
  parser.
- No idiom generation/matching yet, though `Lexicon.idioms` and
  `Language.with_new_idiom()` already exist for it.
- No custom font generation (long-term idea, explicitly deferred).
- **The Vietnamese/Cantonese/Tibetan batch** brought an eighth reference-
  profile batch to full curation depth (Vietnamese and Cantonese are
  brand-new profiles; Tibetan previously had only a phoneme inventory +
  romanization rules). Research into all three languages' real tone
  systems surfaced a genuine architecture gap this batch fixed as a
  general capability first (approved via direct question, the same "ask
  before major work" pattern as every prior major extension): this
  project's tone system capped at 4 distinct tone categories per
  language (`ToneLevel` had 5 members -- `LOW`/`MID`/`HIGH`/`RISING`/
  `FALLING` -- but `RISING` was defined and never actually reachable,
  since `_TONE_LEVEL_SETS`'s richest entry only ever used 4 of them),
  while real Cantonese and real Vietnamese both have genuine 6-tone
  systems (Cantonese: purely pitch-based, register height x contour;
  Vietnamese: also mapped 1:1 here, with 2 of its 6 tones -- ngã, nặng --
  thereby approximated as ordinary pitch, since real glottalization/
  creaky voice isn't a feature this project models at all -- flagged
  honestly in `vietnamese.yaml`'s own comments, not silently smoothed
  over).
  - `core/phonology.py`'s `ToneLevel` gained a 6th member, `DIPPING`
    (real Cantonese's own low-rising tone; also the standard English
    name for real Vietnamese's hỏi, whose own real orthographic
    diacritic -- combining hook above, U+0309 -- `TONE_DIACRITICS`
    reuses directly, since combining tilde was already spoken for by
    this project's own nasalized vowels). `phonology_gen.py` gained a
    4th `_TONE_LEVEL_SETS` entry using all 6 members.
  - Which tone-level set a tonal language actually gets was, until now,
    a uniform `rng.choice` among the sets regardless of which reference
    language matched -- even a strongly Cantonese-biased run had no
    better than a 1-in-4 chance of landing on the richest set at all.
    New `ReferenceLanguageProfile.tone_level_count: int | None` field
    (Mandarin=4, Vietnamese=6, Cantonese=6, Tibetan=2) drives a new
    `_choose_tone_levels(rng, reference_profiles, strictness)` function
    that reference-biases the selection the exact same shape
    `coda_profile`'s own selection already used just above it in
    `generate_phonology` (weight the matching entry 4x, then let
    `strictness` pull further via `biased_probability`) -- a real,
    general improvement to every tonal profile's own reference-bias
    fidelity, not just the three profiles this batch added. One real
    divergence from the `coda_profile` precedent it's modeled on, found
    by a unit test failing before it could ever manifest in real
    generation: `coda_profile` is a *required* field every profile
    always has a real value for, so its own analogous "no reference
    profiles matched" guard (`if reference_profiles:`) can never see an
    empty match set while also being non-empty overall -- but
    `tone_level_count` is *optional*, so a real edge case exists
    (reference profiles present, but none of them curate
    `tone_level_count`), where that same guard shape left every
    `_TONE_LEVEL_SETS` entry's weight pulled toward zero with nothing on
    the positive side to balance it, crashing `rng.choices` with "total
    of weights must be greater than zero" at high strictness. Fixed by
    guarding on `if reference_tone_counts:` (the actually-matched set)
    instead.
  - A new shared-pool consonant, `/tsʰ/`, was added alongside the
    pre-existing plain `/ts/` (real Cantonese ts/tsʰ contrast, e.g. 真
    zan1 vs. 陳 can4-style minimal pairs), with fallback spellings added
    to all three exotic romanization styles.
  - Real Cantonese's kw-/gw- (國 gwok3 "country") is phonologically a
    single labialized velar segment, not a true two-consonant cluster --
    modeled with the *existing* k/kʰ + w glide-sequence machinery
    (`attested_onset_clusters`) rather than any new phoneme.
  - Real Quốc Ngữ's (Vietnamese) and Jyutping's (Cantonese) own famous
    "letter doesn't mean what you'd expect" facts are now curated as
    orthography rules, the same theme as Korean's plain/aspirated
    convention from the prior batch: Quốc Ngữ's plain "d" spells /z/
    (not /d/) while "đ" spells the real stop /d/, "s"/"x" are similarly
    swapped, and "e"/"ê"/"o"/"ô" reverse the naive open/close vowel-
    letter reading; Jyutping's "voiced-looking" letters (b/d/g/z) spell
    the plain/unaspirated series and "voiceless-looking" letters
    (p/t/k/c) spell the aspirated one -- the mirror image of Korean's
    own convention, not gemination or true voicing either.
  - Real phonotactic facts curated per language: Vietnamese has no
    native onset clusters at all and /p/ never opens a syllable (the
    reverse of most languages' own onset/coda asymmetries) though it
    freely closes one; Cantonese likewise has no native onset clusters
    (aside from kw-/gw- above) and, unlike Mandarin, genuinely retains
    stop codas (a real, citable typological contrast between the two
    closely related languages) -- both restricted down to the real
    legal coda set `/p t k m n ŋ/` (plus Vietnamese's /j//w/ diphthong
    offglides) via `restricted_coda_consonants`, `coda_profile:
    unrestricted` rather than Mandarin/Japanese's `sonorant`, since a
    sonority filter would incorrectly exclude the real stop codas.
    Cantonese's vowel length is genuinely contrastive (an 11-vowel
    system with real long/short pairs) -- reuses the existing long-
    vowel pool members rather than any new mechanism. Tibetan's real
    colloquial Lhasa codas are restricted to m/n/ŋ/l/r (ɲ is onset-only;
    w/j pattern as diphthong components, not true codas); real Tibetan
    /ŋ/, unlike every other tonal language modeled so far, genuinely
    does open a syllable, so it's absent from Tibetan's own
    `restricted_onset_consonants`.
  - Because a `coda_profile: unrestricted` (not `sonorant`) profile's
    `coda_frequency_tiers` *is* directly checked against
    `restricted_coda_consonants` by this project's own test suite
    (unlike the `sonorant` profiles, where padding excluded symbols in
    as harmless "dead data" is fine), an early draft of both Vietnamese's
    and Cantonese's profiles made the same mistake this project has now
    caught three times across three separate batches: padding restricted
    (illegal) coda symbols into a `rare` tier as if they were harmless.
    Caught by the test suite itself before commit and fixed by leaving
    those tiers empty, since the real legal coda set was already fully
    covered by the tiers above.
  - Real, deliberately-unmodeled facts, each flagged in the relevant
    profile's own comments rather than silently smoothed over: real
    Vietnamese tone x coda co-occurrence (a syllable closed by an oral
    stop can only carry 2 of the 6 tones, sắc or nặng) -- this project's
    tone assignment has no coda-awareness at all; real Tibetan word-level
    (not syllable-level) tone culmination and its diachronic coda-
    reduction dynamics -- modeled only as a static synchronic coda
    restriction. Both are the same "real but not currently
    rule-capturable by the existing architecture" reasoning that already
    keeps Mandarin's neutral tone and Hindi's schwa deletion out of
    scope.
  - Word length counted at the *word* level, not the morpheme level, the
    same convention Mandarin's own count already established: Vietnamese
    (1.12) is famously monosyllabic even more strongly than Mandarin at
    the word level; Cantonese (1.29) includes real kinship reduplication
    (媽媽 maa1maa1 "mother"); Tibetan (1.37).
  - Vietnamese, Cantonese, and (now) Tibetan all curate onset/nucleus
    frequency tiers but deliberately leave `coda_frequency_tiers`
    uncurated where `coda_profile: sonorant` applies (Tibetan only --
    Vietnamese and Cantonese use `unrestricted` and do curate coda
    tiers) -- same "true legal coda set is narrower than what the test's
    own naive computation sees" reasoning as Italian/Tamil/Mandarin/
    Japanese, so Tibetan stays out of `_PERFECTED_LANGUAGES` too, checked
    by its own dedicated test instead.
- **The Thai/Indonesian/Malay batch** brought a ninth reference-profile
  batch to full curation depth (Thai and Malay are brand-new profiles;
  Indonesian previously had only a phoneme inventory + a handful of
  orthography rules, no phonotactics/frequency tiers/word length).
  Unlike the two prior batches, nothing here needed a new *architecture*
  capability -- every piece was the same shape of per-profile curation
  work (new phonemes filling out an existing pool pattern, a new named
  `OrthographyCategory` composing already-general axes) this project has
  done autonomously in every batch so far, so this one proceeded straight
  from research to an approved plan with no `AskUserQuestion` gate.
  - Real Thai's own tɕ/tɕʰ palatal affricate contrast added `tɕʰ` to
    `phonology_gen.py`'s `_ASPIRATED_GROUP` (alongside the pre-existing
    plain `tɕ`, already used by Polish/Serbo-Croatian's own ć), with
    fallback spellings added to all three exotic romanization styles,
    the same shape as `tsʰ`'s own addition last batch. Real Thai's own
    9-quality vowel system x fully phonemic length (mit vs. miːt) needed
    a new short vowel (`ɤ`, close-mid back unrounded -- the pool
    previously had close-mid front/back rounded and close back unrounded
    but not this one) and 4 new long vowels (`ɛː`/`ɔː`/`ɯː`/`ɤː`,
    alongside the pre-existing `aː`/`iː`/`uː`/`eː`/`oː`), each sharing
    its short counterpart's exact height/backness/rounded so
    `romanization_gen._short_counterpart` (matches purely on those three
    fields) pairs them up automatically -- zero new code on that side,
    the same guarantee already documented for `æː`/`øː`/`yː`.
  - A new named `OrthographyCategory`, `"rtgs-style"` (Royal Thai General
    System), composes two axes that already existed in
    `core/romanization.py` -- `ToneMarkingStrategy.UNMARKED` and
    `VowelLengthStrategy.NONE` -- but had never actually been combined
    into a named anchor or exercised by any real profile before now (both
    were already implemented and unit-tested in isolation, just dormant
    the same way `ToneLevel.RISING` was dormant before the 6-level tone
    batch). No new enum members, no new `apply()` branches -- the exact
    same "compose existing independent axes into a new named anchor"
    shape `wade-giles-style`/`zhuang-style`/`pinyin-style` already are.
    Because `vowel_length_strategy: NONE` means `_generate_length_rules`
    generates nothing for a long vowel (it falls through to the generic
    `exotic_style` table's own flat entry for that exact symbol, e.g. a
    colon suffix -- not actually "unmarked"), `thai.yaml`'s own
    orthography rules give each long vowel an *explicit* rule mapping it
    to its short counterpart's own real RTGS spelling, achieving the
    real "length simply isn't written" behavior precisely rather than
    approximately.
  - A new 5-level `_TONE_LEVEL_SETS` entry, `(LOW, MID, HIGH, RISING,
    FALLING)` -- real Thai's own 5 tones (mid/low/falling/high/rising, a
    register+contour system, historically split from an older 3-tone
    system conditioned by onset-consonant voicing) map cleanly onto all
    5 non-`DIPPING` `ToneLevel` members at once. Unlike `DIPPING` last
    batch, this needed no new `ToneLevel` member or diacritic -- just a
    new combination filling a real gap between the existing 4-level and
    6-level sets. `tone_level_count: 5` on Thai's own profile drives the
    existing reference-bias machinery (`_choose_tone_levels`, already
    generic over set length) toward it for a Thai-biased run with zero
    changes to that function itself.
  - Real Thai facts curated directly: the 3-way stop series exists only
    at bilabial/dental (no real /g/); real /ŋ/ genuinely opens a native
    syllable (nguu "snake"), unlike Mandarin/Korean's own coda-only /ŋ/
    from an earlier batch; codas restrict to exactly `/p t k m n ŋ j w/`
    (neither /l/ nor /r/ ever closes a native syllable, and the whole
    3-way onset contrast neutralizes in coda position -- real Thai
    phonetically realizes coda stops as unreleased [p̚ t̚ k̚], a fact
    left as a "below this project's modeled granularity" aside, the same
    status the tone/onset-voicing historical link gets); onset clusters
    restricted to the real native kr/khr/pr/phr/pl/phl/kl/khl/kw/khw set
    (deliberately no native "tr"). RTGS's own two well-documented, often-
    criticized real spelling ambiguities are curated as genuine facts,
    not invented simplifications: `tɕ`/`tɕʰ` both spell "ch", and `ɔ`/`o`
    both spell "o".
  - Indonesian's stub had `malay`/`bahasa` as bare *aliases* on its own
    profile -- a pre-existing conflation this batch corrects. Indonesian
    and Malay are separately standardized languages (ISO `ind` vs `zsm`),
    not a single pluricentric language the way this project's own
    Serbo-Croatian profile deliberately stays unified, so Malay now has
    its own real profile and Indonesian no longer claims its name.
    Research confirmed the two are phonotactically/orthographically
    near-identical today, a real, well-documented fact (the 1972 joint
    Malaysia-Indonesia spelling reform converged both on the same
    c/j/y/ny/sy/kh conventions) rather than a curation shortcut -- both
    profiles share the same consonant/vowel inventory, the same real
    coda restriction (`/p t k s m n ŋ l r h/`, voiced stops/affricates/
    loan-fricatives never closing a native syllable), and the same
    loanword-only onset clusters (pr/tr/kr/bl/gr/sp/st/sk -- native
    Austronesian roots have no onset clusters at all), differentiated
    only by independently hand-counted word length/frequency tiers and
    each profile's own real aliases (`bahasa melayu`/`malaysian` for
    Malay).
  - Indonesian/Malay's `stress_pattern: lexical` models a genuine,
    unresolved academic dispute (Cohn 1989, Odé 1994) over whether either
    language has phonemic word stress at all, not just a "weak" one --
    the same "genuinely complex, no simple flat rule" modeling shape
    Hindi's own disputed stress already uses, with an even higher
    `stress_deviation_rate` (0.45 vs. Hindi's 0.40) reflecting that the
    dispute here is over whether the category exists at all.
  - Word length counted at the *word* level: Thai (1.06) lands among the
    most strongly monosyllabic-leaning of this project's curated
    languages; Indonesian and Malay both land at 2.02, reflecting the
    real Austronesian disyllabic-root typology (air, api, makan, satu,
    dua) -- a genuine, citable word-length contrast with Thai, confirmed
    by a dedicated test comparing the two hand counts directly rather
    than just checking both are curated.
  - All three use `coda_profile: unrestricted` (not `sonorant`), so all
    three curate real `coda_frequency_tiers` and join
    `_PERFECTED_LANGUAGES` outright -- unlike Tibetan/Tamil/Mandarin/
    Japanese from earlier batches, no separate "onset/nucleus only" test
    was needed for any of the three.
  - Manually scanning Thai's own generated output surfaced a real,
    previously-latent bug this batch fixed at the architecture level:
    `coda_profile: unrestricted` languages had a flat, uncurated 30%
    chance of getting a genuine tautosyllabic coda *cluster* on every
    generation, completely independent of whether the matched reference
    language actually has one -- unlike the onset side, where
    `ReferenceLanguageProfile.max_onset` already reference-biases the
    equivalent onset-cluster roll (`0.85`/`0.1` base rate, further pulled
    by `strictness`). The coda side had no analogous field or bias at
    all, which is exactly how a Thai-biased run could roll a coda
    cluster like "-np-" that no real Thai syllable has, even though
    `thai.yaml`'s own comments (and Vietnamese's/Cantonese's own from
    the prior batch) already correctly stated the real "no coda
    clusters" fact -- the profile said the right thing, but nothing in
    `phonology_gen.py` actually enforced it. Fixed with a new
    `ReferenceLanguageProfile.max_coda: int | None` field and the exact
    same reference-bias shape `max_onset` already has, now curated as
    `max_coda: 1` on Thai, Indonesian, and Malay (this batch) and
    retroactively on Vietnamese and Cantonese (an already-shipped
    batch's own latent exposure to the same gap, only surfaced once
    Thai's own generation was checked) -- confirmed by script to drop
    the coda-cluster roll rate from ~23-31% to 0/100 seeds at full
    strictness for all five, while a profile that still doesn't curate
    `max_coda` (the common case for every profile predating this field)
    keeps the original flat ~30% rate unchanged. A broader audit of
    older `coda_profile: unrestricted` profiles (Korean, Mongolian,
    Hindi, Bengali, Georgian, etc.) for their own real coda-cluster
    facts is flagged as a follow-up, not done as part of this batch.
- **The `max_coda` audit follow-up** went through the remaining 25
  pre-existing `coda_profile: unrestricted` profiles for their own real
  coda-cluster facts and curated `max_coda: 1` on six where real native
  phonology has no genuine tautosyllabic coda cluster at all: Korean
  (the "seven-consonant rule" coda already documented in its own
  comments, predating this field), Finnish (native phonotactics cap
  codas at one consonant; clusters are loanword-marginal at best),
  Georgian (the language's famous multi-consonant sequences are
  word/stem-*initial* onsets, not codas), Hebrew (the "segolate" noun
  pattern historically broke up CVCC with epenthesis specifically to
  avoid real coda clusters), Portuguese (codas restricted to a small
  single-consonant set -- `s`/`z`/`ʃ`/`l`/`ɾ`/`ʁ`/`m`/`n` -- true
  clusters essentially absent natively), and Quechua ((C)V(C) is the
  real maximal syllable template). The other 19 (Arabic, Bengali,
  Danish, Dutch, English, French, German, Hindi, Hungarian, Icelandic,
  Mongolian, Norwegian, Persian, Polish, Russian, Serbo-Croatian,
  Spanish, Swedish, Turkish) were left uncurated (abstain), for two
  distinct real reasons rather than one: most (Danish, Dutch, English,
  French, German, Hungarian, Icelandic, Mongolian, Norwegian, Persian,
  Polish, Russian, Serbo-Croatian, Swedish) genuinely *do* have real
  coda clusters (e.g. English "text", German "Herbst", Hungarian
  "kert") and curating `max_coda: 2` wasn't judged necessary to fix the
  specific bug this field targets (a language with *zero* real coda
  clusters still getting a nonzero roll) -- leaving them uncurated
  keeps the original flat ~30% baseline, a defensible default the
  `max_coda` field's own docstring already sanctions. The rest (Arabic,
  Bengali, Hindi, Turkish) are genuinely register-stratified: native/
  core vocabulary avoids coda clusters but a highly productive loan or
  formal register (Sanskrit tatsama for Hindi/Bengali, Arabic's own
  pausal CVCC forms feeding Turkish borrowings) carries real ones too
  well-established to call "no clusters," so neither `1` nor `2` would
  honestly capture the mixed reality. Spanish was deliberately *not*
  added to the `max_coda: 1` list despite surface similarity to
  Portuguese/Quechua: `spanish.yaml` already curates real (if
  marginal/learned-register) `attested_coda_clusters` -- `[s, t]`
  ("estar"/"texto"), `[k, s]` ("extra"), `[n, s]` ("instante") --
  predating this audit, and `max_coda: 1` would have silently
  contradicted that existing, more specific curation rather than
  refining it.
- **The Swahili/Zulu/Yoruba batch** brought a tenth reference-profile
  batch to full curation depth (all three brand-new profiles). Zulu
  didn't exist as its own profile either -- `xhosa.yaml` previously
  listed `zulu`/`nguni` as bare aliases on Xhosa's own profile, the same
  pre-existing conflation this project found and corrected once already
  (Indonesian/Malay). Research confirmed Zulu and Xhosa are separately
  standardized languages (ISO `zul` vs `xho`) with real differences at
  the level this project curates (Xhosa's own aspirated/affricate series
  is more elaborate; its orthography has conventions Zulu's doesn't) --
  closer to a real conflation than Serbo-Croatian's own deliberate
  unification, so Zulu now has its own profile and Xhosa no longer
  claims its name (Xhosa's own curation depth otherwise stays untouched,
  not requested). Like the Thai/Indonesian/Malay batch, nothing here
  needed new *architecture* -- every piece was the same shape of
  per-profile curation (new phonemes filling out existing pool group
  patterns, tone-level counts landing on already-existing
  `_TONE_LEVEL_SETS` entries, `coda_profile: "none"` already a working,
  precedented value via Hawaiian's own stub) this project has done
  autonomously in every batch so far.
  - **Zulu's real click-accompaniment series** was the batch's biggest
    single addition: alongside the 3 bare clicks (`ǀ`/`ǃ`/`ǁ`, the same
    dental/postalveolar/lateral places and `c`/`q`/`x` letters Xhosa's
    own profile already curates), `phonology_gen.py`'s `_EXOTIC_POOL`
    gained 9 new click phonemes -- aspirated (`ǀʰ`/`ǃʰ`/`ǁʰ`), voiced/
    breathy "depressor" (`gǀ`/`gǃ`/`gǁ`, reusing the exact `breathy`
    trait Hindi's own murmured `bʱ`/`dʱ`/`gʱ` series already uses, since
    both are phonetically breathy voice), and nasalized (`ŋǀ`/`ŋǃ`/
    `ŋǁ`, tagged `Manner.NASAL` rather than their bare counterparts'
    own STOP/LATERAL_FRICATIVE, since nasalized clicks phonetically
    pattern with nasals). Zulu's own plain-obstruent depressor series
    reuses the pre-existing `bʱ`/`dʱ`/`gʱ` symbols directly -- real
    Zulu "b"/"d"/"g" letters *are* this historically-breathy-voiced
    series, not a separate additional plain-voiced one, and no new
    phonemes were needed there. The real depressor-consonant tone-
    lowering effect (one of the most-cited facts in Nguni tonology)
    stays deliberately unmodeled -- this project's tone assignment has
    no onset-conditioned logic at all, the same "real but not currently
    rule-capturable" status Thai's own onset-voicing/tone-split history
    got last batch. The fortis stop series' exact phonetic status
    (ejective vs. fortis-aspirated) is a live, minor scholarly dispute,
    sidestepped by modeling it as plain voiceless `p`/`t`/`k`, distinct
    from the uncontested aspirated `pʰ`/`tʰ`/`kʰ` series. Zulu's own
    `orthography_category` is `digraph-style` (matching the real
    aspirated `h`-suffix convention), with explicit profile-level
    overrides for the click letters (single ASCII, not this category's
    own generic digraph default), the click-accompaniment spellings
    (real Nguni `gc`/`gq`/`gx` voiced, `nc`/`nq`/`nx` nasal; aspirated
    `ch`/`qh`/`xh` inferred by analogy, flagged as such rather than
    confirmed), and the depressor series (plain `b`/`d`/`g`, overriding
    this category's own generic Hindi-style `bh`/`dh`/`gh` breathy
    default). Real Zulu also genuinely lacks native `/r/` -- a real,
    citable Bantu-wide fact curated by simply leaving it out.
  - **Swahili's real prenasalized stops** (`mb`/`nd`/`ŋg`/`nz`) are
    genuine unit phonemes, not clusters -- Swahili's own strict open-
    syllable canon (`coda_profile: none`, the same value Hawaiian's
    existing stub already establishes as working) tolerates them
    precisely because each occupies one onset slot. The real, citable
    gotcha this profile curates directly: plain `ng` spells the
    prenasalized stop (*ngoma* "drum"), while `ng'` with an apostrophe
    spells the plain velar nasal alone (*ng'ombe* "cow") -- the reverse
    of what an apostrophe-as-omission reading would suggest. Swahili
    also **genuinely lost the Bantu tone system** every other profile in
    this batch keeps (a well-known typological oddity), replaced by
    real, near-exceptionless fixed penultimate stress
    (`stress_deviation_rate: 0.04`, close to Finnish's own famously
    rigid figure but for the opposite position).
  - **Yoruba's real doubly-articulated labial-velar stop** `gb` (its
    voiceless counterpart `k͡p` is markedly more marginal/dialectal and
    isn't modeled) was added to the pool as `Place.BILABIAL` -- no
    dedicated labial-velar place exists, the same simplification `/w/`
    (also really labial-velar) already lives with. Real Yoruba's 5-vowel
    nasal series neutralizes the oral mid-height contrast under
    nasalization using the *open*-mid quality specifically, which is
    why 2 new nasal vowels (`ɛ̃`/`ɔ̃`) were needed alongside the pre-
    existing `ã`/`ẽ`/`ĩ`/`õ`/`ũ` group (Yoruba's own real nasal vowels
    are `ĩ`/`ɛ̃`/`ã`/`ɔ̃`/`ũ`, not the close-mid `ẽ`/`õ` that group
    already has). Real Yoruba orthography marks tone directly with
    acute=High/grave=Low/unmarked=Mid -- exactly this project's own
    *default* `VOWEL_DIACRITIC` tone strategy, needing no special
    category the way Thai's `rtgs-style` did last batch (this project's
    own generic Mid mark stays a macron rather than real Yoruba's true
    "unmarked," the same already-accepted simplification every other
    tonal profile's own Mid tone already lives with). Real gotcha, the
    same family as Korean/Cantonese/Vietnamese's own already-curated
    swaps: `j` spells /dʒ/ while `y` spells /j/ -- a mirror image of a
    naive IPA reading.
  - Zulu's real 2 level tones (H/L, a register system) and Yoruba's
    real 3 level tones (High/Mid/Low, also register) both land exactly
    on `_TONE_LEVEL_SETS` entries that already existed before this
    batch (the 2-level set already used by Tibetan; the 3-level set
    already present too) -- unlike Thai's own 5-level set last batch,
    neither needed a new entry, just `tone_level_count` curated to
    drive the existing reference-bias machinery toward the right one.
  - Word length counted at the *word* level, citation form (root + real
    noun-class prefix where one genuinely exists): Swahili (2.04) and
    Zulu (2.22, a real, defensible bit higher, reflecting Nguni's own
    fuller class-prefix/augment system running longer than Swahili's
    shorter prefixes) both land near Indonesian/Malay's own figures;
    Yoruba (1.92) lands lower despite its own often-longer, vowel-
    prefixed nouns, since many core Yoruba verbs are genuinely
    monosyllabic.
  - All three use `coda_profile: none` (no native syllable ever
    closes at all, a stricter fact than any `unrestricted`-profile
    language in this project), so all three curate onset/nucleus
    frequency tiers only and join Tamil/Mandarin/Japanese/Tibetan's own
    "checked separately, not `_PERFECTED_LANGUAGES`" exception list
    rather than being added to it, with their own dedicated tests
    mirroring Hawaiian's own pre-existing `coda_profile: none` stub.
- **The eight-stub-completion batch** brought the last 8 bare-stub
  profiles (Arawakan, Bengali, Georgian, Hawaiian, Nahuatl, Pama-
  Nyungan, Quechua, Xhosa) to full curation depth, finishing the full
  set of 45 reference profiles. Unlike every recent batch, this one
  needed **zero new phonemes and zero new architecture** -- every real
  fact research surfaced was already expressible with existing pool
  symbols and existing `core/romanization.py` mechanisms, confirmed
  before starting so no `phonology_gen.py`/`romanization_gen.py` changes
  were needed at all. Purely YAML-level curation, the same shape of
  work as every prior batch's own phonotactics/word-length/frequency-
  tier pass, across 8 files at once.
  - Two profiles also got a small, well-grounded *correction* to a
    stale simplification, the same shape as Vietnamese/Cantonese's own
    coda-cluster bug or Indonesian's own stale-alias fix in earlier
    batches. **Arawakan**'s 6th vowel was modeled as schwa ("ə"); real
    Garifuna/Lokono sources (Taylor, Munro, Haurholm-Larsen 2016)
    analyze it as `/ɨ/` (high central unrounded, spelled "ü") --
    corrected using the pool's own pre-existing `ɨ` symbol. **Xhosa**'s
    `coda_profile: sonorant` predated this session's own Zulu work;
    Zulu (Xhosa's closest sister, same real Bantu-wide open-syllable
    canon) was correctly curated as `coda_profile: none` two batches
    ago, and research confirmed Xhosa should match -- also gaining the
    same real click-accompaniment series (aspirated/voiced-depressor/
    nasalized) Zulu's own profile introduced to the shared pool, using
    those exact already-existing symbols, plus `tone_level_count: 2`
    (same real 2-level H/L register Zulu already has) and a switch from
    `monoletter-style` to `digraph-style` for the same real reason
    Zulu's own profile already made that call (the aspirated series
    needs a genuine h-suffix digraph convention monoletter-style's own
    generic default would collapse). Xhosa's own existing 2-way plain
    stop series (distinct from Zulu's own real 3-way plain/aspirated/
    breathy system) stayed unchanged -- research didn't confirm Xhosa's
    stops work identically to Zulu's, so this wasn't force-matched.
  - Real, citable coda restrictions newly curated: **Bengali**'s
    aspirated/breathy series (`pʰ tʰ kʰ bʱ dʱ gʱ`) essentially never
    closes a native syllable; **Quechua**'s ejective/aspirated series
    (`pʼ tʼ kʼ pʰ tʰ kʰ`) is onset-only, composing with its own already-
    curated `max_coda: 1`; **Arawakan**'s real attested finals are
    narrower than the generic "sonorant" sonority filter would allow
    (just `/m n/`, not `/l r w j/` too); **Nahuatl**'s own real coda set
    is `/l w j ʔ/` specifically, narrower than sonority alone would
    give (excluding the nasals `/m n/`, which the generic filter would
    otherwise legalize). **Georgian** was confirmed to need no coda
    restriction beyond its own already-curated `max_coda: 1` -- a real
    asymmetry worth documenting: Georgian's coda restriction is purely
    structural (never more than one consonant), not featural (which
    consonants), unlike Bengali/Quechua/Arawakan/Nahuatl's own identity-
    based restrictions.
  - Real, citable onset facts: **Georgian**'s own famous extreme
    initial clusters get an illustrative `attested_onset_clusters` set
    drawn from real words (mdivani, sxva, mtieri-type material);
    **Bengali**'s real onset clusters are Sanskrit-loan (tatsama)
    material only, the same "loanword-derived, biasing not exhaustive"
    shape this project's own Hindi profile already models. **Pama-
    Nyungan** gained a real, well-documented, near-exceptionless
    Australianist restriction (Dixon 1980): no Australian language has
    word-initial `/ŋ/`, and initial rhotics/`/l/` and the apical
    retroflex/alveolar contrast are likewise restricted or neutralized
    onset-initially -- curated via `restricted_onset_consonants`, the
    first profile in this batch to restrict onset rather than coda.
  - **Hawaiian** had a real, major gap: one of the most-cited phonemic-
    vowel-length languages in introductory linguistics, previously
    curated with none at all. The shared long-vowel pool (`aː iː uː eː
    oː`) already covered exactly Hawaiian's own five long vowels -- just
    added to its vowel list with the same real macron spelling
    convention (`ā ī ū ē ō`) already curated for Nahuatl. Its own real
    stress is weight-sensitive (a long vowel/diphthong reliably attracts
    it) rather than a flat position, modeled as `stress_pattern:
    lexical`, the same "quantity-sensitive, no flat rule" shape Arabic/
    Hindi already use, at a lower deviation rate since Hawaiian's own
    weight-sensitivity is more mechanically regular. **Pama-Nyungan**
    also gained real contrastive vowel length (`aː iː uː`), spelled with
    the real doubled-letter convention (aa/ii/uu) actual Western Desert
    practical orthographies use.
  - Real, reliable stress facts newly curated: **Bengali**'s fixed
    word-initial stress (more reliable than Hindi's own quantity-
    sensitive system -- genuine consensus, not a live dispute);
    **Pama-Nyungan**'s reliable word-initial stress (Goddard 1985), the
    same "famously rigid" territory as Finnish/Hungarian; **Nahuatl**'s
    and **Quechua**'s own real, famous, near-fixed penultimate stress.
    **Georgian**'s own stress is a genuine, live dispute over whether
    it's even phonetically real at all -- modeled the same "disputed, no
    simple flat rule" way this project's own Indonesian profile already
    is. **Arawakan**'s own real prosody is a genuine, unresolved
    question across sources (recent work re-analyzes Garifuna as a
    lexical pitch-accent system, closer to this project's own Japanese
    profile than to ordinary stress, while older sources describe
    looser "stress" and Lokono is separately described as more simply
    penultimate) -- given this family's own already-acknowledged
    thinner documentation base, `stress_pattern` stays deliberately
    uncurated rather than guessing which source to follow, the same
    "abstain when the evidence doesn't support confident curation"
    honesty this project's other axes already practice.
  - Word length counted at the *word* level, citation form where a real
    obligatory affix exists (Nahuatl's own absolutive suffix, Xhosa's
    own noun-class prefix): Bengali (1.67, close to but a bit above this
    project's own Hindi figure), Georgian (1.85), Quechua (2.05),
    Nahuatl (2.15), Xhosa (2.18, close to but not identical to Zulu's
    own 2.22), Arawakan (~2.2, flagged with meaningfully more counting
    uncertainty than even the other newly-added profiles given this
    family's own thinner documentation base), Hawaiian (2.45, running
    long for a real CV-only language with no clusters or codas ever),
    and Pama-Nyungan (2.55) -- confirmed by a dedicated test to sit
    above every other profile in this batch, reflecting the real, near-
    exceptionless Australianist fact that content words are never
    monosyllabic (this project's own word-length model only biases
    toward an average rather than enforcing a hard floor, so this stays
    a real, below-this-project's-modeled-granularity gap rather than a
    guaranteed constraint).
- **The ten-language batch** (Welsh, Basque, Nama, Navajo, Khmer, Latin,
  Old Norse, Sumerian, Ancient Greek, Sanskrit) brought this project's
  reference set from the full 45-profile "real-language coverage" to a
  broader typological/historical spread, prompted directly by "what's
  still missing for world coverage and fantasy-conlang use" -- five real-
  world gaps (Celtic, a language isolate, a primary click language, Na-
  Dene, an Austroasiatic register system) and five extinct/historical
  languages a fantasy conlang generator's own users would plausibly draw
  on (Latin, Old Norse, Sumerian, Ancient Greek, Sanskrit). Unlike the
  eight-stub batch immediately before it, this one needed real new
  phonemes and one real architecture extension.
  - **New phonemes** (all "extend an existing pattern" additions, no new
    trait axes): Nama's own 4th click place (`ǂ`, already declared but
    unused by Zulu/Xhosa) plus ~10 new stacked click accompaniments
    (nasal+aspirated, nasal+glottalized) -- a real accompaniment system
    genuinely distinct from Zulu's own Nguni-internal voiced/breathy
    "depressor" series, which Nama lacks. Navajo's own real 3-way plain/
    aspirated/ejective series completed across its postalveolar and
    lateral affricates (`tʃʰ tɬʰ` alongside the ejective `tʃʼ tɬʼ` this
    batch also added) plus 4 long-nasal vowels. Basque's own apical/
    laminal sibilant contrast (`s̺ s̻ t̺s̺ t̻s̻`). Sanskrit's own real 4-way
    stop series completed for its retroflex place (`ʈʰ ɖʱ`, alongside the
    breathy palatal affricate `dʒʱ`). Khmer's own long/diphthong-rich
    vowel space (`ɨː ɑː` plus 9 real diphthongs). Welsh's own voiceless
    trill (`r̥`). A genuinely reusable addition: `ʎ` (palatal lateral
    approximant -- Spanish/Basque "ll", Italian "gli", Portuguese "lh"),
    common enough cross-linguistically to join the unconditional
    approximant pool rather than a gated group.
  - **The one real architecture piece**: `word_accent_gen.py`'s existing
    `positional_pitch_accent` mechanism (built for Japanese) gained two
    new optional parameters -- `assign_positional_pitch_accent`'s
    `window` (restricts the accent kernel to the last N syllables, real
    Ancient Greek's own "trimoric law") and `mark_positional_pitch_accent`'s
    `long_nucleus_at_kernel` (the kernel syllable's mark becomes the
    falling/circumflex diacritic instead of plain High specifically when
    its own nucleus is long, the real Attic acute-vs-circumflex rule) --
    both threaded through `mark_stress_and_word_accent` and a new
    `ReferenceLanguageProfile.word_accent_window` field. `None`/`False`
    (the defaults) preserve Japanese's own exact prior behavior
    byte-for-byte; only Ancient Greek's own profile sets `window: 3`.
  - **Scope calls that avoided needing more architecture**: Sanskrit
    targets Classical (post-Vedic) Sanskrit specifically, which genuinely
    lost phonemic pitch accent -- `word_accent_realization` stays
    uncurated, with the real Vedic accent system (which *would* need a
    further "derive svarita on kernel+1" extension) left a deliberately
    out-of-scope historical aside. Khmer's real historical-voicing-
    conditioned vowel "register" split is modeled via the *already-
    existing* `attested_onset_nucleus_pairs`/`restricted_onset_nucleus_pairs`
    mechanism (the same one Mandarin's own real `/ɕ/`-before-i/y
    restriction already uses) -- a curation task, not new architecture,
    demonstrated for one representative vowel pair across a handful of
    onsets from each register class rather than the real full ~150-300+
    pair space, honestly flagged as partial. Nama's stacked click
    accompaniments needed no new trait axis at all: `Consonant.manner`
    and its boolean traits are already independent fields, so
    `Manner.NASAL, aspirated=True` (etc.) was already expressible.
  - **Real, citable coda facts**: Navajo is `coda_profile: unrestricted`
    (not `sonorant`, despite genuinely restrictive Na-Dene codas) because
    real Navajo verb stems can end in true obstruents (`h s ʃ`), not just
    the sonorant class a `sonorant` profile's own engine-level sonority
    filter would allow. Nama and Sumerian, by contrast, *are*
    `coda_profile: sonorant`, narrowed further (Nama to just the plain
    nasal, matching real Khoekhoe's CV/CVN canon). Ancient Greek and
    Sanskrit both narrow `unrestricted` codas to their own real small
    closed sets (Greek: n/r/s; Sanskrit: the plain voiceless stop of each
    series plus the two nasals, real pada-final sandhi neutralization).
  - **Orthography conventions curated for real, citable reasons**: Old
    Norse uses **acute accents** for vowel length (á é í ó ú ý ǽ ǿ),
    deliberately distinct from Latin/Sanskrit's own real **macron**
    convention -- two different real scholarly traditions for two
    different language families, not an inconsistency; its real hl-/hn-/
    hr- clusters are modeled as genuine two-segment /h/+sonorant
    clusters, not invented unit phonemes. Navajo's real orthography
    spells its lenis (phonetically voiceless-unaspirated) series with
    *voiced* letters (b/d/dl/dz/dj) -- a real, historically-motivated
    gotcha curated directly, not papered over -- plus the real ogonek
    convention for nasal vowels (ą ę į ǫ), stacking with length doubling
    for long nasal vowels (ąą ęę įį ǫǫ). Nama's own real click
    orthography spells clicks with their own bare letters (ǀ ǃ ǁ ǂ), a
    different real practical-orthography tradition from Zulu/Xhosa's own
    borrowed-click c/q/x convention, overriding the shared fallback
    tables' own Nguni-derived defaults. Ancient Greek's own real υ
    (upsilon) is a front rounded vowel `/y/`, not "u"; η/ω get real
    macron transliteration (ē/ō) as the long, quality-shifted partners of
    short ε/ο (a genuine asymmetric length pair, unlike α/ι/υ's own
    same-quality pairing). Sanskrit's own real IAST spells its
    always-long e/o *without* a macron (there's no short counterpart to
    disambiguate against) despite modeling them as `eː`/`oː` internally.
  - Word length: Sumerian (1.3, the shortest in this project's own set,
    reflecting its own famously monosyllabic-root-heavy core vocabulary,
    flagged with even more counting uncertainty than Arawakan/Pama-
    Nyungan given Sumerian's uniquely indirect script-only evidence
    base), Welsh (1.45, real Celtic apocope), Old Norse (1.4), Nama (1.7,
    shorter than Zulu/Xhosa's own Bantu-prefix-driven figures -- Khoekhoe
    has no comparable noun-class system), Basque (1.8), Sanskrit/Latin
    (2.0 each), Ancient Greek (2.1), Navajo (2.2, real productive
    verb/noun prefixation), Khmer (1.4, many real roots monosyllabic-
    with-a-heavy-onset, plus real unmodeled sesquisyllabic minor
    syllables this project's own syllable-counting can't distinguish from
    a genuine full syllable).
  - A pre-existing latent bug surfaced (not introduced) by this batch's
    own new pool content, fixed alongside it:
    `test_small_words_average_closer_vowels_than_big_words`
    (`test_sound_symbolism.py`) scanned a generated word's own vowel
    height character-by-character rather than by proper phoneme
    tokenization, so a word built around a multi-character vowel symbol
    sharing no individual character with any separately-registered vowel
    (e.g. the pre-existing syllabic `r̩`) could raise `StopIteration` --
    fixed to use `ipa_tokenizer.symbols_only`, the same greedy-longest-
    match tokenization the real generation pipeline itself already uses.
- **Word-level algorithmic phonology**: closing the "Korean assimilation and Hindi schwa
  deletion" limitation named much earlier in this history, starting with a survey (the same
  "ask before major work" pattern this whole history already follows) of every curated profile
  for the same shape of gap -- a word's own real pronunciation depends on scanning its *whole*
  syllable sequence, not one adjacent symbol, so no per-symbol `RomanizationRule` (however many
  `preceding`/`following` conditions it stacks) can express it. Confirmed real but *architecturally
  different* candidates (Finnish consonant gradation, Turkish/Icelandic morpheme-boundary
  alternations, Arabic/Hebrew definite-article assimilation, Welsh initial mutation, Japanese
  rendaku) all need live inflection or a cross-word/morpheme trigger this project's citation-
  form-only, no-live-morphology architecture has nowhere to hang -- a different, deeper gap than
  Hindi's own, not new instances of it. Mandarin's neutral tone and Tibetan's diachronic coda-
  reduction were already documented in the same "real but not rule-capturable" bucket. Found one
  genuine sibling: Bengali's own inherent-vowel deletion, real and citable for its word-final
  half, distinct enough from Hindi's own rule (a different vowel, /ɔ/ not /ə/, and a real but
  much less confidently documented medial pattern this project declines to guess at) to need its
  own curation rather than reusing Hindi's.

  New mechanism: `ReferenceLanguageProfile.word_level_phonology` (a string-keyed rule name, the
  same dispatch shape `stress_pattern`/`word_accent_realization` already use, not a boolean --
  each of these is a bespoke real algorithm, not a universal toggle like `vowel_harmony`),
  consulted in a new `generation/word_phonology.py`. Deliberately hooks into
  `word_builder.build_word` at the syllable-tuple-list stage (each `(onset, nucleus, coda)`
  already an unambiguous per-syllable decision made while that syllable was built) rather than
  re-tokenizing the finished flat IPA string afterward -- the latter would have to re-solve the
  maximal-onset resyllabification ambiguity the syllable-list representation already sidesteps
  for free, a real architectural dead end considered and rejected before writing any code. Runs
  once, right after every syllable is built, *before* `stress_gen.assign_stress` (deletion can
  shorten a word by a whole syllable, which stress assignment needs to already see -- doing this
  the other way around would either assign stress to a syllable about to disappear or need a
  second, re-triggered stress pass) and before any word-class affix attaches (so Hindi's own
  real "-nā" infinitive suffix attaches to the already-reduced stem, matching real "kar-nā" not
  "kara-nā"). Gated by one all-or-nothing roll against `word_level_phonology_strictness` per
  word (unlike `reduce_unstressed_vowels`'s own per-*syllable* rate just below it in the same
  function) -- this is real, citable phonology that always applies to a real word meeting its
  environment, not a generic tendency to lean into harder at higher strictness. Deliberately
  *not* threaded into `build_reduplicated_word` -- kinship words already bypass most of
  `SyllableStructure` (no coda, no cluster modeling at all) for the same Jakobson-1960
  simplest-possible-shape reason `reduce_unstressed_vowels` skips them too, so there's nothing
  here for either rule to meaningfully act on.

  Hindi's own rule is the standard, widely-cited computational formulation (Ohala 1983;
  Narasimhan, Sproat & Kiraz 2004's own "ə -> ∅ / VC_CV"): a word-final inherent vowel always
  deletes unless it's the word's only vowel (a word needs at least one nucleus); an internal one
  deletes when the syllable to its own *left* is closed (has a coda) -- the rule's own left
  context; the right context ("followed by an ordinary onset+vowel") is trivially true for any
  internal syllable, so only the left-context check actually does any work. This is where real
  "dharm"/"mitr"-shaped Hindi words come from: an underlying tri-syllabic C-schwa-C-schwa-C-schwa
  form collapsing to one syllable once both its own inherent vowels delete. Every merge is
  checked against `SyllableStructure.is_valid_syllable` first and skipped, not forced through,
  when illegal -- the same "abstain rather than fabricate" discipline
  `word_builder._STRESS_REDUCTION_RATE`'s own legality check already practices. Bengali gets only
  the word-final half of the same mechanism (`allow_medial=False`), left that narrow on purpose
  given the genuine documentation-confidence gap noted above.

  Verification: 10 new tests in `test_word_phonology.py` (the pure function directly -- final
  deletion, medial deletion gated on a closed preceding syllable, the medial rule correctly
  *not* firing when that syllable is open, an illegal merge correctly skipped, the Bengali
  variant correctly firing only word-finally, both profiles' own declared rule names, and no
  other curated profile accidentally opting in) plus one `build_word`-level integration test
  proving the wiring itself (an inventory with only "ə" as its own vowel forces every nucleus,
  so `strictness=0.0` deterministically keeps all three across 20 seeds while `strictness=1.0`
  visibly reduces at least one -- a statistical check across seeds rather than one hand-picked
  seed, since a legal-merge outcome genuinely varies by rng draw the same way the pure-function
  "illegal merge" test already demonstrates it can). Smoke-tested via real `conlang generate
  --source-language Hindi/Bengali --strictness 1.0`: across 3 seeds each (~400 words), a
  word-final inherent vowel survives almost exclusively on monosyllables (correctly never
  touched) or where the merge would be illegal -- exactly the two documented abstention cases,
  nothing unexplained. Full suite: 1003 passed, 2 skipped (up from 993 -- the 10 new tests).

  **Korean's own cross-syllable consonant assimilation**, closing the other half of the
  original "Korean assimilation and Hindi schwa deletion" limitation, followed right behind in
  the same session, reusing the `word_level_phonology` dispatch with a genuinely different
  algorithm shape: unlike Hindi/Bengali's vowel deletion (which scans rightward and can shorten
  a word by a whole syllable), this only ever rewrites one coda or onset consonant's own
  identity at a coda/onset boundary, never syllable count -- so a single left-to-right pass over
  every adjacent syllable pair, independent of each other, is enough (no cascading risk: a
  coda-side rewrite only ever touches syllable *i*, an onset-side rewrite only ever touches
  syllable *i+1*, and the next pair's own check reads syllable *i+1*'s coda, which neither kind
  of rewrite from the previous pair ever touched). Three real, purely phonetically-conditioned
  rules, all triggered on mutually exclusive conditions so there's no ordering question between
  them: nasalization (an obstruent-stop coda before a nasal onset takes that nasal's own place
  of articulation -- real *국물* gungmul "soup" /k/+/m/ -> [ŋ]+[m]), lateralization (/n/+/l/ or
  /l/+/n/ both converge on [l]+[l] -- real *신라* Silla), tensification (an obstruent-stop coda
  before a plain obstruent onset makes that onset tense -- real *학교* hakgyo "school" /k/+/k/ ->
  [k]+[kʼ]; real Korean also tensifies a following /s/, but this project's own Korean profile
  doesn't model a distinct tense /s/ at all, so that one member of the real series stays out of
  reach for the same "no symbol to render it with" reason a handful of other profiles' own gaps
  already have). Considered and declined real Korean **palatalization** (*같이* gachi "together",
  from an underlying /t/+/i/) for the same reason the wider survey above declined Welsh
  mutation/Japanese rendaku/Arabic-Hebrew article assimilation: it's conditioned on a specific
  morpheme boundary (a t/tʰ-final root meeting an i-initial suffix/particle), not a purely
  phonetic environment, so it needs live morphology this project doesn't have -- a different
  kind of gap, not a harder instance of the same one. Every rewrite is checked against
  `SyllableStructure.is_valid_syllable` first and skipped, not forced through, when illegal,
  the same discipline the deletion rules above already practice. This project's own Korean
  profile already enforces the real "seven-consonant rule" coda neutralization
  (`restricted_coda_consonants`), so every coda this function ever looks at is already one of
  the real surface seven the assimilation rules are themselves stated over -- no extra
  neutralization logic needed here.

  6 more tests in the same `test_word_phonology.py` (nasalization and lateralization each in
  both directions with real cited examples, tensification, a no-op case where neither trigger
  matches, an illegal-rewrite-skipped case, the profile's own declared rule name) plus one more
  `build_word`-level integration test (a 2-consonant/1-vowel inventory that never draws "ŋ" on
  its own, so its appearance in the output only ever comes from nasalization actually firing --
  the same "rewrite target excluded from the drawing pool" trick the Hindi integration test's
  own schwa-only inventory already uses). Smoke-tested via real `conlang generate
  --source-language Korean --strictness 1.0`: generated lexicons visibly show all three
  patterns (tense onsets, "ŋ" codas, doubled "ll") across 3 seeds. Full suite: 1009 passed, 2
  skipped (up from 1003 -- the 6 new tests).
- **"Missing symbols still"**: closed most of `DEFERRED.md`'s own list of generically-missing
  IPA symbols (as opposed to the two items right above, which needed new *mechanisms* --
  these just needed the symbol itself). `ɰ` (velar approximant) and `ɱ` (labiodental nasal)
  joined `_REFERENCE_ONLY_CONSONANTS` -- real, but not tied to any one curated profile's own
  flagship sound the way most of that pool's members are. Rhotacized schwa `ɚ` and Mandarin's
  own syllabic `ɻ̩` (儿/二, modeled the same "atomic Vowel-pool member with the real syllabic
  diacritic" way the already-existing Serbo-Croatian `r̩` is) joined the *drawn* `_VOWEL_EXTRAS`
  pool; both romanize identically ("er") in all three `romanization_gen.py` styles and in
  `ipa_to_kirshenbaum.py` -- a deliberate collision, real Hanyu Pinyin already spells 儿/二
  "er" itself, and the two sounds really are the same "er" quality one way or another, the
  same "shallow styles accept some collisions" precedent this project already has elsewhere.
  Completed the real 5-place click series (bilabial `ʘ`, the rarest place, plus its own
  aspirated/breathy/nasalized accompaniments, matching the 3-member baseline the other 4
  places already have) and the real 5-place implosive series (uvular `ʛ`). Added epiglottal
  fricatives `ʜ ʢ` -- genuinely obscure (Agul and a handful of other Northeast Caucasian
  languages, Haida), reusing `Place.PHARYNGEAL` (the closest existing place; no dedicated
  `Place.EPIGLOTTAL` exists or is needed elsewhere, the same "no dedicated category, reuse
  the closest existing shape" precedent `tɬ`'s own comment already states). All 11 new symbols
  wired through every downstream completeness-tested table; `ipa_to_kirshenbaum.py` needed
  explicit entries for the click/implosive/epiglottal/velar-approximant/labiodental-nasal
  additions (no real Kirshenbaum letter exists for most of these, so each extends its own
  nearest-cousin symbol's letter rather than failing outright -- the same honesty-over-
  authenticity approach that module's own docstring already commits to) but not for
  `gʲ`/`ɕː`-style modified consonants, which already resolve through the existing modifier-
  strip/length-suffix fallback. Verified drawable (400 seeds at `isolation=1.0`; every new
  symbol except the rarest, `gʘ`, showed up at least once) and force-includable via a seed
  example (all 8 tested, `gʘ`/`ŋʘ` following the identical mechanism as `ʘ`/`ʘʰ`).

  Extending `_EXOTIC_POOL`/`_VOWEL_EXTRAS` -- both *drawn* groups, unlike the two
  reference-only additions -- shifted downstream rng draws far more broadly than any single
  prior phoneme-pool batch (22 fixed-seed tests failed on the first full-suite run after this
  change, versus 4 for the Russian `gʲ` addition and 2 for the French/reform-seed shifts
  earlier in this project's history), simply because this batch touched *two* drawn pools at
  once rather than one. Re-found working seeds for every affected fixture, same "seed-shift
  from new content, not a functional regression" pattern as always: `test_translator.py`/
  `test_sentence_planner.py`'s shared nom-acc (2 -> 83 -> 278), ergative (283 -> 28), and
  no-features (4 -> 11) grammar-shape fixtures (the nom-acc seed needed two hops -- 83 passed
  the basic grammar-shape search but failed three deeper behavioral assertions, e.g. present-
  vs-past copula tense marking actually differing, that the search script hadn't checked for,
  a reminder that a pure grammar-shape search is necessary but not always sufficient); the
  Latin-declension seed (1 -> 2); an untoned-seed tone-roll seed
  (`test_reference_only_symbols_and_tones.py`, 3 -> 1); and the Dutch orthography-reform evolve
  seed in `test_sound_change.py` (kept generation seed=3, evolve seed 0 -> 1, the smallest
  working change once found by holding the generation seed fixed and searching evolve seeds
  alone). Full suite: 1009 passed, 2 skipped (unchanged from the Korean batch -- no new tests
  this time, only new pool content and reseeded fixtures). `conlang audit-lexicons`: still 0%
  flagged (a phoneme-pool-only change, doesn't touch curated real lexicons at all).

  **Still open, documented in `DEFERRED.md`**: Vietnamese's own creaky/glottalized ngã/nặng
  phonation (needs a new tone-adjacent phonation-marking dimension, not just a missing symbol)
  and Arabic's coarticulatory pharyngealization spreading onto *vowels* next to emphatic
  consonants (a positional-allophone question, the same kind of gap Spanish spirantization
  is already deliberately left for) -- both considered and declined for this batch since
  they need new machinery, not a symbol addition, the same distinction that separated this
  batch from the Hindi/Bengali/Korean one right above it.
- **Tone sandhi scope**: moved from "Korean assimilation and Hindi schwa deletion" and
  "Missing symbols still" (both about *word-level phonology* -- new algorithms or new
  phonemes) to `DEFERRED.md`'s separate "## 3. Tones" section -- a survey of that whole
  section first, since most of its own claims turned out to be stale. `tone_levels`/
  `tone_level_count` (the *base* tone system, as opposed to sandhi specifically) are already
  fully curated for every tonal profile except Mandarin's own already-done one (Cantonese 6,
  Thai 5, Vietnamese 6, Tibetan 2, Yoruba 3, Zulu 2, Xhosa 2; Swahili correctly stays
  `tonal: false`, a real fact -- it lost the reconstructed Bantu tone system) -- the section's
  own "Other tone systems... only Mandarin is curated" claim was wrong about this half of
  itself, confirmed by grep before touching anything (`tone_sandhi` entries specifically are
  still Mandarin-only, so that half of the same bullet was accurate). Likewise "Pitch accent...
  not carried by real lexicons" was stale -- this session's own earlier stress/pitch-accent
  batches already closed that for Japanese, Danish/Swedish/Norwegian, Ancient Greek and
  Serbo-Croatian; `DEFERRED.md`'s own real-words-coverage bullet already documents this, this
  section just hadn't caught up.

  Of the section's remaining items, **sandhi scope** was picked first: smallest, highest-
  leverage, no new linguistic content to curate (Mandarin's own sandhi rules are already
  correct, just under-applied). `conlang pronounce` now runs `tone_sandhi.apply_sandhi` on a
  single looked-up entry's own `ipa` before displaying/synthesizing it -- the function already
  treats its input as "a list of tone-bearing IPA words" with no assumption that they come
  from different lexicon entries, so a multi-syllable citation form's own internal syllable
  sequence needed no new sandhi logic, just reuse (real Mandarin dictionary entries for fixed
  multi-syllable compounds conventionally already cite the *surface*, post-sandhi tones, so
  this isn't just a convenience -- it's the linguistically correct citation-form fact this
  project's own word generation was missing). Printed as an extra "Pronounced (tone sandhi):"
  line only when it actually differs (a toneless or non-triggering word's own output is
  byte-identical to before), and the sandhi'd IPA -- not the bare citation form -- is what
  actually gets synthesized, so audio reflects real pronunciation.

  Investigated and **explicitly declined**: reflecting sandhi in the *romanized* translation
  output (`TranslationResult.text`), the other sub-item this same "Sandhi scope" bullet named.
  Traced `translate_to_english`'s own decoder (`_decode_noun`/`_decode_verb`) before touching
  anything and found it does exact-string matching against each entry's stored citation-form
  `romanization` -- respelling a token to its sandhi'd form in the *encoder's* own output would
  silently break decoding it back, a real regression the original `DEFERRED.md` bullet hadn't
  anticipated (it read as a straightforward parity fix -- "the IPA gets sandhi, the spelling
  should too" -- until this trace surfaced the round-trip dependency). Real published Pinyin
  practice is genuinely split on writing citation vs. sandhi tones besides, so there wasn't
  even a clear "more correct" answer being left undone. This is the kind of thing worth
  tracing *before* implementing a seemingly-obvious parity fix, not after.

  Verified preservation through `sound_change` evolution needed no code change at all --
  `evolve_language` already copies a language's own `ToneSystem` (levels and sandhi rules
  both) forward unchanged, and `apply_sandhi` is a pure function of whatever `ToneSystem` it's
  given, so an evolved language's own sandhi already worked correctly before this session ever
  started. Written up as a regression test (generate a strict-Mandarin language, evolve it,
  confirm `evolved.tone_system == base.tone_system` and that `apply_sandhi` gives the identical
  result against both) rather than left as an unverified assumption, the same "prove it, don't
  just assert it" standard the rest of this history holds itself to.

  The web UI has no per-word "hear this entry" affordance at all currently (checked
  `static/index.html`'s own `/api/pronounce` wiring directly -- the only call site is the
  whole-translation playback button, which already gets sandhi via the existing
  `translate_to_conlang` IPA path) -- nothing to fix there today, but a future per-word
  listen button should reuse the exact same `apply_sandhi([entry.ipa], tone_system)[0]`
  wrapping `cli/main.py`'s own `pronounce` command now uses.

  2 new tests in `test_reference_only_symbols_and_tones.py` (the single-multi-syllable-word
  case; the evolution-preservation case), plus a manual CLI smoke test against a real
  strict-Mandarin-sourced generated language with a naturally-occurring sandhi-triggering
  word (confirmed the exact expected diacritic change, and confirmed a non-triggering word's
  own output stays byte-identical). Full suite: 1011 passed, 2 skipped (up from 1009 -- the 2
  new tests).
- **Sandhi rules for the other 7 tonal languages -- surveyed, none added.** Asked to curate
  real context-conditioned tone sandhi (real `ToneSandhiRule` data, the Mandarin third-tone-
  sandhi shape) for Cantonese, Thai, Vietnamese, Tibetan, Yoruba, Zulu, Xhosa. Researched each
  before writing any code (web search, not just recalled priors) and found the premise didn't
  hold for any of them:
  - Vietnamese and Thai: no significant standard-register phonological tone sandhi is
    attested at all -- Vietnamese tones stay categorically stable in connected speech (only
    phonetic coarticulation, not rule-based change); Thai sources describe a "deafening
    silence" on the topic.
  - Cantonese: has "changed tone," but it's lexical/morphological (restricted to specific
    compounds and nominal/diminutive forms), the same shape as Mandarin's own 不/一 -- not a
    general phonological context rule.
  - Zulu/Xhosa: genuinely complex, but the real mechanism is autosegmental tone *spreading*
    (a H tone extends across multiple following syllables until blocked) plus depressor-
    consonant lowering and downstep -- `ToneSandhiRule` only models one syllable's tone
    changing based on one immediate neighbor; forcing spreading through that shape would
    misrepresent the actual phenomenon, not simplify it.
  - Yoruba: real tone assimilation exists, but the literature is explicit that it's
    conditioned by syntactic or morphological domain (across a phrase boundary, or within a
    word), not simple phonological adjacency, plus specific documented cases are themselves
    lexical (a pronoun's tone before certain particles) -- the same non-fit as Cantonese.
  - Tibetan -- the closest candidate: a real, specific, phonologically-conditioned rule
    exists (a low-toned syllable before a long high-toned syllable makes that syllable
    rising), but it needs a three-way tone system (High/Low/Rising), and this project's own
    Tibetan profile deliberately curates only 2 levels, with its own comment explaining that
    richer subdivisions are contested in the literature -- retrofitting a rule that needs a
    tone level the profile intentionally left out would fight that earlier, already-reasoned
    decision. Tibetan's more central real complexity (word-level tone culmination, only the
    first syllable really contrastive) was also already flagged out of scope earlier in this
    same history, in the same bucket as Mandarin's own neutral tone.

  Reported this back rather than fabricating rules to satisfy the task's surface framing or
  silently implementing nothing -- the same "investigate before implementing a seemingly
  obvious fix" standard the sandhi-scope romanization decision (right above) already
  practiced, just discovered before writing any code this time instead of partway through.
- **Lexically specific sandhi (Mandarin 不/一)**: the other half of the original "Lexically
  specific sandhi" limitation, picked next once the 7-language survey came up empty. New
  `core.phonology.LexicalToneSandhiRule` (`gloss`, `before`, `becomes`) and
  `ToneSystem.lexical_sandhi` -- a tone alternation bound to *one specific lexicon entry* (by
  gloss, since this project's own invented Mandarin-sourced words have no Chinese characters
  to key on) rather than any syllable sharing a tone context, the real shape of 不 "not"
  (citation falling, becomes rising before a following falling-tone syllable) and 一 "one"
  (citation high, becomes rising before falling, falling before high/rising/dipping).
  `tone_sandhi.apply_sandhi` gained an optional `glosses` parameter (one per `ipa_words`
  entry) and applies `lexical_sandhi` as a *second* pass after the existing general
  context-sandhi pass -- deliberately reading each tracked word's own already-general-
  sandhi'd neighbor tone (the real, as-spoken tone a listener actually hears next), which
  only `apply_sandhi` itself is in a position to compute, so this genuinely couldn't be
  layered on from outside the function. A tracked word with more than one tone-bearing
  syllable is keyed on its own *last* one (irrelevant for Mandarin's own monosyllabic 不/一,
  but keeps the mechanism correct for a hypothetically polysyllabic tracked gloss too); a
  word-final/isolated tracked word (real 不/一 said alone) keeps its own citation tone, the
  same default every other word's own citation form already has.

  Curated on Mandarin's own profile via a new `lexical_tone_sandhi: [[gloss, before, becomes],
  ...]` field, resolved by a new `generation.phonology_gen.resolve_lexical_tone_sandhi` --
  deliberately *simpler* than `resolve_tone_sandhi`'s own kept/replaced/invented three-way
  model: each curated rule is independently kept with probability equal to its own weighted
  strictness, with no invention or replacement at all, since there's no meaningful "invented"
  version of one specific real word's own specific real alternation (the same honest
  abstention this project's own curated-not-invented word-level-phonology rules already
  practice). Its own independent rng stream (seeded separately from the main generation's
  `rng`, the same isolation `resolve_tone_sandhi` already has) means adding this changed no
  other draw sequence -- confirmed by the full suite passing with no reseeding needed this
  time, unlike the phoneme-pool batches earlier in this history.

  Wired into both existing sandhi consumers: `translate_to_conlang` (a new parallel
  `gloss_parts` list built alongside `romanization_parts`/`ipa_parts`, `entry.primary_gloss`
  at each rendered slot) and `conlang pronounce` (though a single looked-up word has no
  following syllable to trigger it on today -- included for when a future multi-word
  `pronounce` path exists). Not modeled: the real rule's own edge case before a *neutral*-tone
  syllable, genuinely handled differently across pedagogical sources -- left as an honest
  abstention (citation tone stands) rather than a guess.

  4 new unit tests in `test_reference_only_symbols_and_tones.py` (tracked-word-only scope
  confirmed against an untracked word sharing the same tone; citation-tone fallback both
  word-final and on an unmatched next-tone; all four of 一's own real contexts in one test;
  a constructed case proving the lexical pass reads the *post*-general-sandhi tone, not the
  citation one) plus a strict-Mandarin-run resolution check folded into the existing
  strict-run test there, plus one real end-to-end `test_translator.py` test -- a real
  strict-Mandarin-sourced generated language (seed hand-found via a small search script so
  "not" naturally sits immediately before a real falling-tone word in that sentence's own
  actual slot order, not just assumed), translated through the full `sentence_planner` ->
  `translate_to_conlang` -> `tone_sandhi` pipeline, confirming the output IPA's own "not"
  token carries the rising-tone mark the real rule predicts. This mechanism's own
  independently-seeded rng stream meant no other draw sequence moved -- confirmed by the full
  suite passing with zero reseeding needed, unlike the phoneme-pool batches earlier in this
  history. Full suite: 1016 passed, 2 skipped (up from 1011 -- the 5 new tests).
- **Neutral tone as grammar -- kinship half done, particle half investigated and declined.**
  Real Mandarin kinship reduplication (妈妈 māma, 爸爸 bàba, 哥哥 gēge) canonically carries its
  own real tone only on the *first* syllable, with the second surfacing neutral --
  `word_builder.build_reduplicated_word` (previously baking one `tone_mark` into a single
  `syllable` string reused for both halves) now builds an untoned `base_syllable` once and
  applies `tone_mark`/a new `second_tone_mark` independently to each half, so the two
  syllables of a reduplicated word are no longer necessarily two copies of the same marked
  syllable. `second_tone_mark` defaults to `None` ("same as `tone_mark`", the original
  behavior, unchanged for every non-Mandarin tonal language's own kinship words).
  `lexicon_gen._propose_kinship_word` passes the language's own real neutral-tone mark there
  whenever `ToneLevel.NEUTRAL` is actually in `tone_system.levels` (only Mandarin's own
  curated `neutral_tone: true` triggers this among currently-curated profiles) -- gated on the
  tone system's own real content, not a new profile flag, the same "derive from what's already
  curated" economy this project's own axes generally prefer. `LexicalEntry.tones` was updated
  to store the real `(tone, ToneLevel.NEUTRAL)` pair too, not just the IPA's own mark, keeping
  the two in sync the way every other field on a generated entry already is. The choice between
  `tone`/`ToneLevel.NEUTRAL` is derived, not rolled -- no new `rng` call, so (unlike every
  phoneme-pool batch this session) this needed zero reseeding of any fixed-seed test.

  **Grammatical particles (的/了/吗), investigated and declined.** These are a real
  possessive/attributive marker, an aspect/tense marker, and a sentence-final question
  particle respectively -- traced each against what this project actually generates before
  writing any code, and none of them map onto an existing word. Real Mandarin has no articles
  at all (checked its own profile: `real_has_articles: false`), so "the" was never a stand-in
  for 的 to begin with -- 的 isn't an article. This project's own case/tense-affix machinery is
  switched off entirely for isolating morphology (`grammar_gen.py`'s own `cases` stays empty
  whenever `morphological_type is ISOLATING`) rather than realized as separate analytic
  particle words the way real Mandarin's 了/着/过 actually are, and there's no modeled
  sentence-final question-particle mechanic anywhere in `sentence_planner.py` either. Checked
  the remaining candidates directly too: none of this project's own already-generated function
  words ("the", "not", "and", "be") are genuinely neutral-tone in real Mandarin -- 不 and 一
  specifically get their own real, non-neutral tone-sandhi behavior, already curated
  separately (see the lexically-specific-sandhi entry above). Marking a particle neutral is the
  trivial part; there's no particle to mark neutral until this project has real isolating-
  language analytic grammar (a possessive marker, an aspect particle, a question particle) to
  generate in the first place -- a materially bigger feature, closer in size to this project's
  own already-bracketed-off case/tense-affix architecture gaps than to "add a tone rule." Left
  open rather than forced onto an existing word that wouldn't actually be linguistically
  correct.

  3 new tests: 2 in a new `test_word_builder.py` (this project's first dedicated test file for
  `word_builder.py` -- `build_reduplicated_word`'s own `second_tone_mark` axis in isolation:
  defaults to matching the first syllable; overrides only the second syllable, base
  consonant+vowel unchanged) plus one integration test in
  `test_reference_only_symbols_and_tones.py` against a real strict-Mandarin-sourced generated
  language (seed hand-found so "mother" naturally rolls the ~80%-likely kinship-reduplication
  path), confirming both the `tones` field and the stored IPA's own mark. No new `rng` call
  meant no reseeding needed -- confirmed by the full suite passing clean. Full suite: 1019
  passed, 2 skipped (up from 1016 -- the 3 new tests).
- **Contour representation**: `ToneLevel`/`TONE_DIACRITICS` (one combining mark per category)
  stay this project's own *stored*, phonemic representation, unchanged -- that's what a word's
  IPA is actually built/read/romanized from everywhere else in this codebase, and nothing about
  this batch touches it. New `core.phonology.TONE_CONTOURS` (`ToneLevel` -> real Chao (1930)
  pitch-level digits, 5=highest/1=lowest -- Standard Mandarin's own four tones are exactly
  55/35/214/51 in this convention) and `chao_letters()` (converts those digits into the real
  IPA tone-letter bars one at a time, e.g. `"51"` -> `"˥˩"`, `"214"` -> `"˨˩˦"`) are a separate,
  phonetically fuller *display*/synthesis view derived from the same stored tone, not a
  replacement for it -- the same "add a derived table, don't touch the underlying category
  system" shape this whole tone subsystem's history already has.

  This data already existed in the codebase before this batch, just privately and only for one
  consumer: `speech/tts.py`'s own `_ESPEAK_TONE_NUMBERS` ("verified by synthesizing each and
  comparing lengths/pitch against the pinyin voice" -- real, already-checked data, not
  something invented for this batch). Checked its exact values before writing any new data of
  my own, confirmed they already *are* the standard Chao numerals, and refactored
  `_ESPEAK_TONE_NUMBERS` to source from the new canonical `TONE_CONTOURS` instead of
  duplicating it (`_ESPEAK_TONE_NUMBERS = TONE_CONTOURS`, same variable name so every existing
  caller in that module stays untouched) -- eSpeak's own real pitch targets and the new
  human-readable display now share one real fact instead of two tables that could quietly
  drift apart.

  `speech/reader.py`'s `describe()` (the CLI `conlang pronounce` command's own text output,
  previously just `IPA: /.../  Romanized: ...`) now appends a `Tone contour: ˥˩ (51)`-shaped
  line, one Chao-letter/digit pair per tone-bearing syllable in order, derived directly from
  `LexicalEntry.tones` (already-stored data, no language object needed) -- only when the word
  actually has tones, so a non-tonal language's own output is byte-identical to before.
  Smoke-tested against a real strict-Mandarin-sourced generated language: `conlang pronounce
  mother` (the kinship-reduplicated word from the batch right above, its own real+neutral tone
  pair) showed `Tone contour: ˨˩˦ (214) ˩˩ (11)`, and an ordinary word showed matching
  contours for its own two same-tone syllables -- both exactly as expected, a nice
  cross-check that the two most recent batches compose correctly together.

  **Not done at the time, disclosed rather than built speculatively:** exposing per-language
  `tone_levels` with their own contour in the web UI, which then showed only a bare
  `tonal: true/false` badge. Done in a later web-app batch (see this file's own "Web app: tone
  system display, source-language weight verification" entry) -- `webui/app.py`'s own
  `_language_summary` now includes exactly this, via the same `TONE_CONTOURS`/`chao_letters`
  this entry already names.

  6 new tests: 2 in `test_phonology.py` (every `ToneLevel` member has real contour data; the
  digit-to-bar conversion for falling/rising/dipping/high, checked against the textbook
  Mandarin numerals directly) plus one in `test_tts_capabilities_and_sandhi.py` (asserting the
  refactor's own identity: `tts._ESPEAK_TONE_NUMBERS is TONE_CONTOURS`, not just equal values)
  plus 3 in a new `test_reader.py` (a toneless word's own output unchanged; a single-syllable
  tonal word's exact contour line; a multi-syllable word's own contours in the right order).
  Full suite: 1025 passed, 2 skipped (up from 1019 -- the 6 new tests).
- **Tone in evolution -- tonogenesis and detonalization, real splits/mergers/lexicalized-
  sandhi left open.** `sound_change.evolve_language` used to copy a language's own `ToneSystem`
  forward completely unchanged (its own docstring said so explicitly) -- the last remaining
  item from the original tones survey, and the biggest (tagged "L" from the start). Asked to
  "also consider when tones might stop being in a language" alongside starting tonogenesis, so
  this batch covers both directions of the same underlying question (a language's tonal
  *status*, not just its tone marks) rather than just the one named first.

  Both are modeled as a single whole-language roll, not a rate applied independently per
  eligible position the way the six existing gradient segmental rules (`_evolve_ipa`) are --
  real tone contrastiveness is systemic: once a language has tone, every syllable carries one,
  not just syllables sitting in some marked environment, so unlike lenition or palatalization
  this genuinely can't sensibly leave the change half-applied across the lexicon (`_evolve_tone_system`'s
  own docstring states this reasoning explicitly). New `_HALF_LIVES` entries
  (`detonalization: 350.0`, `tonogenesis: 400.0`), each with a real citable anchor case, the
  same discipline every other rule in this file already holds itself to.

  **Detonalization** (a tonal language loses tone): accelerated by positive `contact_intensity`,
  the same "contact drives simplification" link the three simplification-leaning segmental
  rules already use. Its own real anchor case is one this project already had, just never as a
  *transition*: Swahili's own well-documented loss of the reconstructed Bantu tone system under
  centuries of sustained Arabic/trade-contact pressure, already reflected from the start in
  this project's own curated Swahili profile (`tonal: false`). Every entry's own tone marks are
  stripped (`ipa_tokenizer.strip_tones` -- an existing, already-tested primitive, not new code)
  and its own `tones` tuple collapses to `()`.

  **Tonogenesis** (a non-tonal language gains tone): modeled via the one mechanism this
  project's own phoneme/coda machinery can actually detect -- real coda-glottal-stop loss, the
  same pathway behind Vietnamese's own historical tone origin (Haudricourt 1954). New
  `_has_qualifying_coda_glottal_stop`/`_tonogenesis_ipa`: a word's own coda `ʔ` (word-final, or
  immediately before a consonant) is removed and its own vowel surfaces `LOW`; every other
  vowel surfaces the real cross-linguistic elsewhere case, `HIGH`. Deliberately excludes an
  *intervocalic* `ʔ` -- under the maximal-onset principle this project's own phonotactics
  already use everywhere else, a consonant between two vowels belongs to the *following*
  syllable's onset, not the preceding one's coda, so it's structurally unrelated to this
  pathway. Structurally gated, not just rate-gated: a language with no word anywhere in its own
  *current* lexicon (post sound-change/replacement, not just the base language's own original
  one) that has a qualifying coda `ʔ` has no raw material for this specific pathway at all this
  run, regardless of `years` -- an honest abstention, the same discipline every other
  structurally-gated rule in this project already practices.

  `_evolve_tone_system` returns `(new_tone_system, transform)` rather than directly returning
  transformed IPA -- `transform` is a pure `list[str] -> (list[str], list[tuple])` function the
  caller applies to *both* `final_ipas` (a word's own new stored IPA) and `spelling_ipas` (the
  separate, sometimes-different basis a word's own spelling is reconstructed from, e.g. a
  word-final-devoicing hint) so the two stay consistent with each other, without rolling the
  function's own random decision twice -- a real bug considered and fixed *before* it shipped:
  first draft called the decision function once per list, which would occasionally decide
  *differently* for `final_ipas` vs `spelling_ipas` (a coin flip re-flipped), desyncing a word's
  own stored IPA from its own derived spelling. Applied once, after Pass 1 (sound change +
  lexical replacement/borrowing) so it sees the words this run's lexicon actually ends up with,
  before inventory/structure reconstruction so a tonogenesis run's own removed `ʔ` (and a
  detonalization run's own stripped marks) are reflected in what gets reconstructed, not the
  pre-transition state.

  8 new tests in `test_sound_change.py`: the coda-qualification heuristic directly (word-final,
  before-a-consonant, before-a-vowel correctly excluded, no ʔ, word-initial `ʔ` correctly
  excluded); the per-word tonogenesis transform directly; `_evolve_tone_system` itself for both
  directions plus its own structural-gating abstention; a `years=0` no-op check for both
  directions; and two full `evolve_language` pipeline tests (tonogenesis firing, and the
  spelling/IPA-consistency regression guard above) -- both silence the six segmental rules and
  lexical replacement via `monkeypatch` rather than picking a "safer" `years` value, since there
  isn't one: every segmental half-life overlaps tonogenesis's own, so any `years` long enough to
  saturate tonogenesis's rate also saturates lenition/cluster-simplification/etc., which would
  mangle (or itself remove) this test's own tiny hand-built word's qualifying coda before
  tonogenesis ever got a chance to look at it -- an unrelated confound, not a real interaction
  question, isolated out rather than chased with a seed search. Found and fixed one real
  regression from an *earlier* batch this same session: the "Sandhi scope" work's own
  `test_evolved_languages_own_tone_system_and_sandhi_still_apply_correctly` had asserted
  `evolved.tone_system == base.tone_system` as a blanket fact -- true when this batch's own
  mechanism doesn't fire, no longer true in general now that it sometimes legitimately does;
  updated to silence detonalization for that test specifically (an orthogonal concern to what it
  actually checks: sandhi surviving evolution when the tone system *does* come through
  unchanged), not to weaken the assertion.

  Smoke-tested against real generation, both directions: an isolated, ʔ-coda-bearing base
  language gained a real high/low tone contrast at a long time depth (`I: dmom -> móm`, `we:
  bɾa -> ɾá`, alongside the same run's own real segmental changes -- confirms the two kinds of
  change compose sensibly on real generated words, not just the hand-built test fixtures); a
  strict-Mandarin-sourced language lost its own tone system under high contact
  (`I: ká -> kʼa`, tones `()`). Full suite: 1033 passed, 2 skipped (up from 1025 -- the 8 new
  tests). `conlang audit-lexicons`: still 0% flagged (a generation/evolution-only change,
  doesn't touch curated real lexicons).

  **Still open at the time, left for a later pass:** tone splits/mergers, and sandhi becoming
  lexical. The next entry below closes out splits/mergers; sandhi becoming lexical remains open
  (see `DEFERRED.md`).
- **Tone in evolution -- splits and mergers (closing out the tones survey).** Asked to "go ahead
  with tone splits and mergers," the two sub-items the tonogenesis/detonalization batch above
  had explicitly left open. Both slot into `_evolve_tone_system` alongside the existing two
  directions, all four now checked in one fixed order for a tonal language --
  detonalization, then merger, then split -- each its own independent, mutually exclusive roll
  (a non-tonal language still only ever considers tonogenesis, unchanged from the batch above).

  **Mergers are tractable with the existing flat `ToneLevel` enum** -- two of a language's own
  real pitch categories collapse into one, no new representational machinery needed. New
  `_HALF_LIVES["tone_merger"] = 450.0`, the slowest of the four tone-system half-lives: real
  Middle Chinese's own "entering" (checked-syllable) tone category dispersing into modern
  Mandarin's other tones is this project's own citable case, and that dispersal is usually
  described as protracted and somewhat irregular rather than one clean cutover, which the
  slower half-life reflects. `_tone_merger_pair` picks `(survivor, absorbed)` from a tonal
  language's own current `levels`, excluding `NEUTRAL` (a real but categorically different
  unstressed/underspecified status, never a genuine register competing for survival the way two
  real pitch categories are) -- `None`, an honest abstention, when fewer than two categories are
  eligible. `_tone_merger_ipa` does a plain string substitution of the absorbed category's own
  diacritic for the survivor's, then re-tokenizes the *result* to recompute `tones` -- the same
  "the IPA's own marks are the authoritative source" discipline tonogenesis's own transform
  already uses, rather than threading the old `tones` tuple through a second, parallel path.

  A merger doesn't just rewrite lexicon entries -- an existing `ToneSandhiRule` or
  `LexicalToneSandhiRule` that mentions the now-gone category would otherwise keep referencing a
  tone this language no longer has. New `_remap_tone_sandhi`/`_remap_lexical_tone_sandhi`
  substitute the absorbed category for the survivor across every relevant field, and drop the
  rule outright if that remapping makes it map a tone to itself (`becomes == before`) --
  matching the "never map a tone to itself" discipline `resolve_tone_sandhi`'s own invented-rule
  branch already holds itself to for genuinely new rules, applied here to *existing* ones a
  merger would otherwise orphan.

  **Splits are genuinely harder** -- a real register split (Middle Chinese's own 4-tone-to-
  8-tone division, the same "yin/yang" story that motivated the "still open" note above) doubles
  each tone category by register, conditioned on the onset's own voicing before that voicing
  contrast merges away. This project's `ToneLevel` conflates register and contour into one flat
  enum (no separate register axis the way a full Chao-letter system would give it), so a
  faithful implementation isn't directly representable without inventing new tone categories
  with no real basis in this project's own curated data. Rather than do that, this reuses
  `ToneLevel`'s own *existing* categories as split outcomes wherever this project already has a
  defensible real pairing: new `_YANG_TONE = {HIGH: LOW, RISING: DIPPING}` -- `HIGH` ("55"
  contour) pairs with `LOW` ("21"), real Standard Mandarin's own textbook register-low
  counterpart; `RISING` ("35") pairs with `DIPPING` ("214"), already documented on
  `ToneLevel.DIPPING` itself (`core/phonology.py`) as "a low tone that dips" -- already this
  project's own low-register member of that pair, not a new claim invented for this feature.
  `FALLING`/`MID` have no defensible low-register partner in this project's own simplified
  7-category inventory and are deliberately left out of the table: a voiced-onset syllable with
  either tone still devoices its onset when a split fires (the conditioning contrast is still
  genuinely lost), but keeps its own tone unchanged -- an honest partial coverage rather than a
  fabricated pairing. New `_HALF_LIVES["tone_split"] = 420.0`, sharing tonogenesis's own real
  Middle-Chinese/Song-Yuan-transition anchor, since a split is the same onset-voicing-loss
  mechanism as tonogenesis applied to a language that already has tone.

  New `_is_syllable_initial` (mirrors `_apply_final_devoicing`'s own coda-side skip of
  `STRESS_MARK`/`WORD_ACCENT_MARK`, applied to the onset side instead) identifies the position
  the mechanism actually cares about -- a syllable's own first consonant, not the second member
  of an onset cluster. `_has_qualifying_voiced_onset` is the structural gate, true only when a
  real syllable-initial voiced obstruent onset (reusing the existing `_VOICED_TO_VOICELESS`
  table, originally built for lenition's own reverse direction) sits immediately before a vowel
  whose current tone has a real partner in `_YANG_TONE` -- a language with no such word anywhere
  in its own current lexicon has no raw material for a split at all, regardless of `years`, the
  same structural-gating discipline tonogenesis's own check already uses. `_tone_split_ipa` does
  a single left-to-right pass with a `pending_yang` flag that persists across any intervening
  consonants (a previous syllable's own coda, or the 2nd+ member of the *same* onset cluster --
  neither resets it) until the conditioned vowel is reached, devoicing the onset and, where a
  register partner exists, lowering the tone in the same pass. Deliberately *not* a new general
  onset-devoicing rule alongside the six segmental ones -- it only ever fires bundled inside a
  split's own transform, since most languages that devoice onsets don't also develop
  compensatory tone, and coupling the two here avoids opening up a separate, unresolved general
  onset-devoicing design question this batch doesn't need to answer.

  `_evolve_tone_system` gained a `consonant_by_ipa` parameter (the split's own onset-voicing
  check needs it; the caller in `evolve_language` already had it in scope) and now returns a
  merger's or split's own `(new_tone_system, transform)` through the same shared contract the
  other two directions already use -- a merger's `new_tone_system` drops the absorbed category
  from `levels` (and carries the remapped sandhi/lexical-sandhi forward); a split's `new_tone_system`
  adds `_YANG_TONE`'s own value categories to `levels` wherever they weren't already present
  (never removes anything, unlike a merger).

  20 new tests in `test_sound_change.py`: pure-function coverage for `_is_syllable_initial`,
  `_has_qualifying_voiced_onset` (a qualifying voiced onset, a voiceless one, and a tone with no
  `_YANG_TONE` partner), `_tone_split_ipa` (devoices-and-lowers, leaves a voiceless onset alone,
  devoices-but-keeps-tone for `FALLING`), `_tone_merger_pair` (picks two distinct eligible
  levels, never picks `NEUTRAL`, abstains with fewer than two eligible), `_tone_merger_ipa`, and
  `_remap_tone_sandhi`/`_remap_lexical_tone_sandhi` (substitutes and drops a rule that becomes
  degenerate); direct `_evolve_tone_system` calls for both mechanisms firing at a moderate time
  depth and the split's own structural-gating abstention; a `years=0` no-op check extended to
  cover both new fixtures; and full `evolve_language` pipeline wiring tests for both, following
  the tonogenesis batch's own established isolation pattern (silencing the six segmental rules
  and lexical replacement via `monkeypatch`, since their half-lives all overlap the tone-system
  ones and there's no "safer" `years` value to pick instead). One real tuning finding during this
  batch: an extreme `years` value (5000, reused from the tonogenesis tests) made detonalization's
  own rate saturate near 1.0, and since detonalization is checked first, it dominated essentially
  every seed and left no room for merger/split to ever be reached at all in a seed search --
  fixed by testing at a *moderate* `years` value (200) instead, where all of a tonal language's
  own competing directions still have comparable, non-saturated probability.

  Smoke-tested against real generation: a strict-Mandarin-sourced language merged `DIPPING` into
  `HIGH` under moderate time depth (`sỉn -> sín`, tone `DIPPING -> HIGH`, `levels` shrinking by
  one); strict-Thai-, Zulu-, and Yoruba-sourced languages each produced a real split, devoicing a
  voiced onset and lowering its register where `_YANG_TONE` has a partner (Thai `díw (HIGH) ->
  tìw (LOW)`, `dǎŋ (RISING) -> tảŋ (DIPPING)`; Zulu `dèˈvùjú -> tèˈfùjú`, `d`/`v` both devoiced;
  Yoruba `dāˈdā -> tāˈtā`) and devoicing-only where no partner exists (Thai `bîn (FALLING) -> pîn
  (FALLING)`, tone genuinely unchanged). Full suite: 1053 passed, 2 skipped (up from 1033 -- the
  20 new tests). `conlang audit-lexicons`: still 0% flagged (a generation/evolution-only change,
  doesn't touch curated real lexicons).

  That closes out every item the original tones survey opened. **Still open, left for a later
  pass** (see `DEFERRED.md`): sandhi becoming lexical -- needs its own design for exactly
  when/how a *rule*, not a single symbol or the whole tone system, transitions into per-word
  `LexicalToneSandhiRule`-style data.
- **Tone in evolution -- sandhi lexicalization (closing the tones survey for real this time).**
  Asked to "go ahead with sandhi-becoming-lexical," the one item the previous two batches had
  each in turn left open. Slots in as `_evolve_tone_system`'s own fifth direction, checked last
  among the four tonal-branch mechanisms (after detonalization, merger, split -- unchanged, still
  mutually exclusive, still at most one firing per run) and still gated behind
  `base_tone_system.enabled`, since a rule can't lexicalize out of a tone system that isn't there.

  The real phenomenon: a live, *context*-conditioned `ToneSandhiRule` (real Mandarin third-tone
  sandhi is still fully productive and context-conditioned -- this is about the *other* fate a
  sandhi rule can have) can lose its own conditioning environment over enough time and freeze
  into the affected words' own citation tones, at which point the rule itself no longer exists as
  a live process -- speakers just memorize the outcome per word. Real anchor: Cantonese "changed
  tone" (變調), commonly described as a fossilized reflex of earlier, once-productive tone sandhi
  that a modern speaker can no longer predict from any live rule at all, only recall per word --
  as direct a match for "a rule freezing into per-word data" as this project's own tone-evolution
  work has found yet. New `_HALF_LIVES["sandhi_lexicalization"] = 500.0`, the slowest of all five
  tone-system-level half-lives: a rule actually losing its own productivity and being reanalyzed
  as memorized per-word fact is a further, later diachronic stage on top of either a merger (a
  clean, wholesale category collapse) or a split (one mechanical onset-voicing-loss event).

  Three new pure helpers. `_pick_lexicalizing_sandhi_rule` picks one of a tonal language's own
  live rules from `ToneSystem.sandhi` specifically -- deliberately *not* `lexical_sandhi`, which
  is already word-specific data and has nothing left to "become" lexical -- excluding any rule
  with `before == becomes` (never produced by this project's own `resolve_tone_sandhi`, but not
  excluded by the `ToneSandhiRule` model itself; would freeze into a genuine no-op), the same
  "never map a tone to itself" discipline every other tone-system mechanism in this file already
  holds itself to; `None`, an honest abstention, when the language has no eligible rule at all.
  `_has_qualifying_lexicalization_target` is the structural gate: whether a word's own *last*
  tone-bearing syllable -- the exact position `generation.tone_sandhi.apply_sandhi` itself always
  conditions general sandhi on, tracking "the syllable immediately preceding whatever comes next"
  -- currently carries the chosen rule's own `before`. `_lexicalize_sandhi_ipa` does the actual
  per-word freeze: a qualifying word's own last tone-bearing syllable becomes `rule.becomes`;
  every other word (its own last tone elsewhere, or no tone at all) passes through unchanged.

  The one real design question this batch had to resolve: real sandhi is conditioned on what
  actually *follows* a word (Mandarin dipping-dipping becomes rising-dipping only when the next
  syllable is *also* dipping), but this project stores words independently, with no memory of
  which neighbor tones a given word's own citation form has actually sat next to over its
  lifetime -- `generation.tone_sandhi.apply_sandhi` only ever computes that adjacency at
  *utterance*-generation time, from whatever words happen to be strung together in that one
  call, not as a per-word historical fact `sound_change.py` could read back later. Modeling "did
  this specific word actually occur next to a triggering neighbor often enough to lexicalize"
  would need this project to track word collocation frequency, data nothing here currently
  gathers and a materially bigger feature than this batch's own scope. Resolved by applying the
  freeze to every word whose own last tone-bearing syllable carries the rule's `before`,
  unconditioned by what follows -- not a claim that every such word really did sit next to the
  trigger tone every time, but a fair, disclosed telling of what "the rule loses its own
  conditioning environment" concretely means once the rule no longer exists to check it: an
  honest simplification in the same spirit as tone split's own reuse of existing `ToneLevel`
  categories rather than inventing new ones, not a silently narrower implementation of the real
  phenomenon.

  `_evolve_tone_system` needed no new parameters for this direction (unlike split's own
  `consonant_by_ipa` addition) -- everything it needs (`rng`, `base_tone_system`, `years`,
  `final_ipas`, `known_symbols`, `vowel_symbols`) was already in scope. On firing, the returned
  `ToneSystem` keeps `levels` and `lexical_sandhi` exactly as they were (this direction touches
  neither) and drops the chosen rule from `sandhi`.

  13 new tests in `test_sound_change.py`: pure-function coverage for `_pick_lexicalizing_sandhi_rule`
  (picks from the available rules, abstains with none, excludes a degenerate one),
  `_has_qualifying_lexicalization_target` (a matching final tone, a non-matching one, and --
  the one genuinely tricky case -- a word whose *earlier* syllable happens to carry the target
  tone but whose own *last* one doesn't, confirming only the last position counts), and
  `_lexicalize_sandhi_ipa` (freezes a qualifying word, leaves a non-qualifying one alone, and
  only touches a word's own last tone-bearing syllable when an earlier one shares the same tone);
  a direct `_evolve_tone_system` call for the mechanism firing (seed-searched at the same
  moderate `years` the merger/split tests above already settled on, since detonalization/merger
  are still live competitors for the same fixture -- this one's own inventory deliberately has no
  voiced obstruent at all, so split specifically can never compete for the same seed) and its own
  structural-gating abstention; a `years=0` no-op check; and a full `evolve_language` pipeline
  wiring test, isolated via `monkeypatch` the same way every other tone-system wiring test in this
  file already is.

  Smoke-tested against real generation across six independent strict-sourced lineages -- Mandarin,
  Thai, Zulu, Yoruba, Vietnamese, and Cantonese itself (this mechanism's own real anchor case) --
  each producing a language with at least one live sandhi rule, evolving it, and confirming a
  seed exists where that rule freezes: real examples include Mandarin `sỉn (DIPPING) -> sǐn
  (RISING)` (its own dipping-dipping-becomes-rising rule frozen), Cantonese `nīm (MID) -> nỉm
  (DIPPING)`, and Zulu/Yoruba/Vietnamese each freezing one of their own real high/low/mid-tone
  sandhi rules the same way -- with the frozen rule itself confirmed gone from the resulting
  `tone_system.sandhi` in every case. Full suite: 1066 passed, 2 skipped (up from 1053 -- the 13
  new tests). `conlang audit-lexicons`: still 0% flagged (a generation/evolution-only change,
  doesn't touch curated real lexicons).

  That closes out the tones survey in full -- every item it ever opened, including the two this
  file's own two immediately preceding entries had each in turn left for later, is now done.
- **Other tone systems -- surveyed, mostly resolved as not applicable.** Asked to "go on with
  Other tone systems," the last remaining DEFERRED.md tones bullet -- curating real
  `tone_sandhi`/`lexical_tone_sandhi` data for Cantonese, Thai, Vietnamese, Tibetan, Yoruba, and
  Zulu/Xhosa the way Mandarin's own profile already has. Researched each language's own real,
  well-documented tonal alternations (`WebSearch`, cross-checked against primary linguistics
  sources -- Wikipedia's own "Cantonese changed tones" and "Meeussen's rule" pages, published
  Yoruba downstep/assimilation papers, a 2025 *JIPA* Lhasa Tibetan phonology paper) before writing
  anything into a profile, rather than curating from memory the way most of this project's earlier
  phoneme/syllable-structure facts safely could -- tonal alternation specifics are exactly the kind
  of narrow, easy-to-misstate claim this project's own "explicit limitations rather than pretend
  completeness" ethos (`AGENTS.md`) says to verify or abstain from, not guess at.

  The research converged on a real, useful finding rather than a pile of new curated rules: every
  one of these seven languages' own best-known tonal alternations turns out to either not exist as
  a productive sandhi process at all, or not fit this project's existing `ToneSandhiRule`/
  `LexicalToneSandhiRule` shape -- for a specific, disclosed reason in each case (see each
  profile's own new comment for the individual reasoning; DEFERRED.md's own entry summarizes all
  seven). Three genuinely distinct kinds of non-fit surfaced:

  1. **Not a sandhi process at all.** Thai's own tone is a syllable-internal *assignment* (initial
     consonant class x tone mark x live/dead syllable type), not an inter-syllable alternation --
     outside what `tone_sandhi`/`lexical_tone_sandhi` (both inter-syllable-context mechanisms by
     construction) can represent regardless of specifics. Vietnamese and Tibetan simply have no
     productive context-conditioned sandhi to curate (Vietnamese's one documented case is specific
     to *reduplication*, a derivational process this project's inter-syllable model doesn't target
     at all; Tibetan's tone is a historical reflex of a lost onset-voicing contrast, already
     resolved at the segmental level, not a live process).

  2. **A real schema mismatch, not a missing fact.** Cantonese's own real "changed tone" (變調,
     e.g. 妹 "younger sister" mui6 -> mui2 in diminutive/familiar senses) is genuinely
     *unconditioned* by any following tone -- unlike real Mandarin 不/一 (this project's own
     curated `lexical_tone_sandhi` precedent), which only change before a *specific* following
     tone. `LexicalToneSandhiRule`/`apply_sandhi` always requires that next-tone match to fire, so
     forcing Cantonese's own unconditioned fact through it would misrepresent a real fact that has
     no conditioning at all, not model it faithfully -- curating it anyway would have been *wrong*,
     not just incomplete. Fittingly, Cantonese changed tone is already this project's own real
     anchor case for the mechanism that *does* model an unconditioned lexical tone fact correctly:
     `sound_change.py`'s own sandhi-lexicalization direction from the batch immediately above,
     which bakes a tone permanently into a word's own citation form with no ongoing context check
     at all -- exactly changed tone's own real shape.

  3. **A genuine, previously-undocumented architectural gap.** Yoruba's own local H-to-L
     carry-over assimilation and Zulu/Xhosa's own Meeussen's Rule (a High tone immediately
     followed by another High lowers that *second* one to Low, H+H -> H+L, well-documented across
     Bantu -- the real substance behind this bullet's own original "tone-depression patterns"
     phrasing) both need the *later* syllable to change based on what *precedes* it. Reading
     `generation.tone_sandhi.apply_sandhi`'s own implementation confirms it only ever rewrites an
     *earlier* syllable's tone based on what *follows* it (`tones[index] = rule.becomes` keyed off
     `citation[index+1] == rule.after`) -- the direction Mandarin's own third-tone sandhi happens
     to need, but the *opposite* direction Meeussen's Rule needs. Real Nguni High-tone shift/spread
     is a positional *displacement* onto a later syllable on top of that, not even a same-position
     substitution. Both are real, well-attested facts this project's current one-directional
     `ToneSandhiRule` shape structurally cannot express, confirmed by reading the actual dispatch
     code rather than assumed -- disclosed as an explicit limitation (a second, opposite-direction
     rule shape and/or a positional-shift mechanism, a genuinely bigger design question than a data
     curation pass), not silently worked around or forced into a misleading approximation.

  The one substantive data change that *did* land: Tibetan, Zulu, and Xhosa already had their real
  2-tone High/Low register claim recorded via `tone_level_count: 2`, but no explicit `tone_levels`
  -- meaning a strict-sourced run picked up that count only through `_choose_tone_levels`'s own
  generic count-biased pool match, which happens to have exactly one 2-level stock entry
  `(LOW, HIGH)` today, not because the profile ever said so directly. Added `tone_levels: [high,
  low]` to all three, which routes a strict run through `_apply_reference_tone_profile`'s own
  "with_levels" branch instead -- the *same* observable outcome today (confirmed directly: only one
  2-level stock set exists), but now an explicit, documented claim rather than a coincidence that
  would silently break if `_TONE_LEVEL_SETS` ever grew a second 2-level entry.

  3 new tests: `tone_levels == ("high", "low")` now asserted alongside each of the three profiles'
  own existing `tone_level_count` tests in `test_reference_languages.py`, plus one true wiring test
  in `test_reference_only_symbols_and_tones.py` -- a strict Zulu-sourced generated language
  confirmed tonal with exactly `{HIGH, LOW}`, proving the new field actually reaches
  `_apply_reference_tone_profile`'s own "with_levels" code path end to end, not just that the YAML
  parses. Full suite: 1067 passed, 2 skipped (up from 1066 -- the 3 new/extended tests).
  `conlang audit-lexicons`: still 0% flagged (a reference-profile-only change, doesn't touch
  curated real lexicons).
- **Progressive tone sandhi -- closing the one genuine architectural gap the tone-systems survey
  surfaced.** Asked to "implement a solution for the genuine architectural gap" the batch above
  identified: `ToneSandhiRule`'s own `apply_sandhi` implementation only ever rewrote an *earlier*
  syllable's tone based on what *follows* it (`tones[index] = rule.becomes`, keyed off
  `citation[index + 1] == rule.after`) -- the direction Mandarin's own third-tone sandhi happens
  to need, but not the direction real Bantu Meeussen's Rule needs (a High tone immediately
  followed by another High lowers that *second* one to Low, H+H -> H+L -- the *later* syllable
  changes, based on what *precedes* it).

  Fixed with a new field, not a new mechanism: `ToneSandhiRule.target: Literal["before", "after"]
  = "before"` (`core/phonology.py`) says which of a rule's own two syllables actually changes --
  the default preserves every existing rule's own exact behavior byte-for-byte (Mandarin's own
  third-tone sandhi needed no changes at all). `generation/tone_sandhi.py`'s own `apply_sandhi`
  branches on it: `target="before"` rewrites `tones[index]` (unchanged), `target="after"` rewrites
  `tones[index + 1]` instead. Both checks always read from the same original `citation` list, never
  each other's output (unchanged from before this batch), so the one new order-dependence this
  introduces -- a syllable rewritten once as some rule's own `"after"` target from its *left*
  neighbor's check, and again as a *different* rule's own `"before"` target from its own check one
  position later -- has a simple, disclosed tie-break: the later (rightward-iterating) write wins,
  documented directly in `apply_sandhi`'s own docstring rather than left implicit.

  `ReferenceLanguageProfile.tone_sandhi` widened from `tuple[tuple[str, str, str], ...]` to
  `tuple[tuple[str, str, str] | tuple[str, str, str, str], ...]` -- a profile can still write a
  plain 3-tuple (defaults to `target="before"`) or add a 4th element. `resolve_tone_sandhi`'s own
  "carried" loop reads it (`entry[3] if len(entry) > 3 else "before"`); its own `invented()`
  branch deliberately stays `target="before"`-only for now, a disclosed scope choice (documented
  in the function's own docstring) rather than an oversight -- extending random invention to
  sometimes produce `"after"` rules too would consume an extra `rng.random()` draw on *every*
  `invented()` call, shifting every fixed-seed test downstream of one, a real cost with no
  curated-data payoff to justify it yet (this project's own well-established "seed-shift from new
  content" hazard, avoided here by scoping the change to curated data only).

  `sound_change.py`'s own two tone-sandhi-aware mechanisms both needed updating to stay correct,
  not just to keep working: `_remap_tone_sandhi` (the tone-merger direction's own sandhi-remapping
  helper) used to check `becomes == before` for its degenerate-rule test, silently assuming every
  rule is `target="before"` -- now checks whichever field (`before` or `after`) the rule's own
  `target` actually rewrites, or it would either wrongly drop a fine `"after"` rule or wrongly keep
  one that's actually become a no-op. `_pick_lexicalizing_sandhi_rule` (the sandhi-lexicalization
  direction's own rule-picker) now excludes `target="after"` rules outright: lexicalization freezes
  a *word's own last* tone-bearing syllable, exactly the position a `"before"` rule conditions and
  rewrites, but an `"after"` rule's own rewritten position is a *different* word's own *first*
  syllable instead -- freezing the wrong syllable would be silently wrong, not just incomplete, so
  this stays an honest, disclosed narrower scope rather than a naive reuse of the existing helpers.

  Curated the actual real payoff this fix unlocks: Zulu and Xhosa's own profiles (both previously
  documenting Meeussen's Rule only as *why* they couldn't curate it) now carry
  `tone_sandhi: [[high, high, low, after]]` -- real, reachable, curated Bantu tonology data, not a
  disclosed gap anymore. Real Nguni High-tone shift/spread -- a positional *displacement* of a tone
  onto a later syllable, not a same-position substitution at all -- stays uncurated; `target` alone
  doesn't solve a genuinely different rule shape, an honest, still-open gap disclosed in both
  profiles' own comments rather than conflated with what this batch actually fixed.

  13 new/extended tests: `apply_sandhi` with a `target="after"` rule (changes the second of two
  adjacent syllables, not the first; cascades H-H-H -> H-L-L across three, each pair checked
  against the same original citation tones) in `test_reference_only_symbols_and_tones.py`;
  `resolve_tone_sandhi` defaulting a 3-tuple to `"before"`, reading an explicit 4th `target`
  element, and `invented()` staying `"before"`-only across 30 seeds, in `test_phonology_realism.py`;
  `_remap_tone_sandhi`'s own target-aware degenerate check and `_pick_lexicalizing_sandhi_rule`'s
  own exclusion of `target="after"` rules (plus confirming it still picks a `"before"` rule out of
  a mixed set) in `test_sound_change.py`; Zulu/Xhosa's own curated Meeussen's Rule data in
  `test_reference_languages.py`; and one true end-to-end wiring test -- a strict Zulu-sourced
  generated language's own tone system carries the rule, and `apply_sandhi` genuinely lowers the
  second of two real adjacent High-toned words, not the first.

  Smoke-tested directly against real generation beyond the wiring test too: a strict Zulu-sourced
  language's own real lexicon (`I: lìfímfá`, `he: njùˈkívé`, both citation-High-final) spoken
  together came out `lìfímfà njùˈkívè` -- both words' own final tones genuinely lowered, the real
  iterative H-run dissimilation Meeussen's Rule produces, on real generated words, not just the
  hand-built fixtures the unit tests use. Full suite: 1077 passed, 2 skipped (up from 1067 -- the
  13 new/extended tests, minus 3 already counted from the batch above's own Zulu tone_levels
  test additions). `conlang audit-lexicons`: still 0% flagged (a phonology/reference-profile-only
  change, doesn't touch curated real lexicons).
- **Real Nguni High-tone shift -- curating the last real gap the tone-systems survey flagged.**
  Asked to "curate High-tone shift/spread for Zulu/Xhosa too" -- the one item both the survey and
  the progressive-tone-sandhi batch above had each in turn left as "an honest, still-open gap."
  Confirmed via targeted research (`Local and metrical tone shift in Nguni`, ResearchGate) before
  writing anything: "the rightmost High tone generally surfaces on the antepenultimate syllable...
  high tones must shift at least one syllable to the right" -- and, crucially, this description is
  in absolute *word-position* terms (antepenult, penult), not "before/after an adjacent tone" the
  way every mechanism this project's `tone_sandhi.py` models is stated. That's not a smaller
  version of the same gap `ToneSandhiRule.target` just closed -- it's a different *kind* of fact
  altogether, worth working out precisely before writing any code.

  **The real finding: this isn't sandhi at all, in this project's own technical sense.**
  `tone_sandhi.py`'s entire `apply_sandhi` machinery operates on already-*stored* citation tones,
  rewriting them at utterance-speaking time based on an adjacent syllable (often across a word
  boundary). Real Nguni tone shift is described the opposite way: it's already there in a word's
  own citation/isolation form -- it's part of how that citation form's own surface tone pattern
  gets derived from an underlying one *in the first place*, not a speech-time transformation layered
  on top of an already-settled citation tone. No amount of extending `ToneSandhiRule` (even with
  `target`) could reach this: the right integration point is wherever a word's own tones get
  *drawn* during generation, not `apply_sandhi` at all.

  Found that point: `lexicon_gen.build_pending_word`'s own `tones = tuple(rng.choice(...) for
  position in range(num_syllables))` -- the exact moment a word's own per-syllable tone sequence
  is first randomly assigned, before it's ever turned into marks or handed to `word_builder.build_
  word`. New pure function `generation.lexicon_gen.shift_high_tone_to_antepenult(tones)`: fewer than
  3 tone-bearing syllables (no antepenult exists) or no `HIGH` drawn at all (nothing to shift)
  returns `tones` unchanged; otherwise every originally-`HIGH` syllable surfaces `LOW` except the
  antepenult, which surfaces `HIGH` regardless of what was drawn there -- the real "only the
  rightmost High survives, and it lands on the antepenult" outcome (Downing & Gick 2001's own
  "spreading + left-deletion" account, simplified to its single most commonly cited surface
  generalization), not a per-syllable independent recoloring. Wired in right after `tones` is drawn,
  before `tone_marks` derives from it, so both the stored `LexicalEntry.tones` and the actual IPA
  built from `tone_marks` agree.

  New `ReferenceLanguageProfile.tone_shift_to_antepenult: bool = False`, gated the same
  unconditional "any matched profile has this flag" way `stress_driven_vowel_reduction`/
  `word_level_phonology` already are (`any(p.tone_shift_to_antepenult for p in reference_profiles)`)
  -- not a strictness-scaled probabilistic "kept" roll the way an individual `tone_sandhi` *rule*
  gets, since the real fact is close to exceptionless within a matched language, not something that
  sometimes applies and sometimes doesn't. Also wired into `sound_change._coin_native_word` (native-
  replacement word coinage during evolution), which its own docstring already claims coins words
  "the same way fresh core-vocabulary generation coins any word" -- leaving the newer mechanism out
  there would have quietly broken that claim, not just been an incomplete rollout. Both call sites
  reached via `lexicon_gen.shift_high_tone_to_antepenult` directly (promoted from a
  module-private `_`-prefixed name to a public one once a second module needed to call it, the
  same "underscore signals module-internal, drop it once that stops being true" discipline this
  project already follows elsewhere). The function itself draws no randomness at all -- a pure
  post-hoc transform of an already-drawn tuple -- so wiring it in changed no other test's own rng
  sequence anywhere in the suite, confirmed by the full run below showing zero regressions.

  Disclosed simplification, in the field's own docstring and both profiles' own comments: the real
  literature also documents an antepenult-vs-penult conditioning wrinkle (a High *underlyingly
  sponsored by* the antepenult shifts to the penult instead) and deep interaction with verb tense/
  aspect morphology this project doesn't model to that depth -- this curates the single most
  commonly cited surface generalization, not the full real system, the same disclosed-simplification
  discipline Tibetan's own tone-count curation and tone split's own category-reuse already practice.

  9 new tests: the pure transform directly (short words and all-Low words left alone, a single High
  moved from a non-antepenult position, a High already at the antepenult left alone, multiple Highs
  collapsing to just the antepenult) in `test_reference_only_symbols_and_tones.py`; a whole-lexicon
  sweep over a real strict-Zulu-sourced generated language confirming every entry with >= 3
  tone-bearing syllables obeys the antepenult constraint (not one cherry-picked word); a Dutch-
  sourced regression guard confirming an unrelated, non-Nguni source language is untouched; Zulu and
  Xhosa's own curated flag in `test_reference_languages.py`; and a direct `_coin_native_word` wiring
  test (mirroring the existing lineage-profile stress-pattern test's own pattern) confirming the
  evolution-time coinage path respects it too. Full suite: 1086 passed, 2 skipped (up from 1077).
  `conlang audit-lexicons`: still 0% flagged (a generation-time-only change, doesn't touch curated
  real lexicons).

  That's every item the tone-systems survey ever flagged, across all three of its own batches, now
  either curated or explicitly, correctly disclosed as out of scope for a real, specific reason.
- **Web app: tone system display, source-language weight verification.** Asked to move on to the
  web-app backlog (`DEFERRED.md` §8) after the CLI one, with manual browser testing explicitly
  deferred to the user's own pass at the end. Re-audited `webui/app.py`/`static/index.html` against
  §8's own bullets the same way the CLI audit re-checked `docs/CLI.md` against `cli/main.py` --
  several turned out stale in the *other* direction (already resolved, not documented as such):
  "Source-language weights UI" already has its own `.sl-weight` form inputs and a
  `SourceLanguageEntry.weight` field on `/api/generate`'s own request model, just never tested; "no
  per-word audio" undersold what already existed (a sentence-level "Play pronunciation" button
  already existed on the translate tab, via `/api/pronounce`) even though a *lexicon-row-level* play
  button genuinely still doesn't. The one clearly real, substantial gap: `_language_summary` (the
  one view both `/api/generate` and `/api/languages/{slug}` return) had no tone-system data at all --
  this entire session's own tone-evolution work (detonalization, tonogenesis, merger, split, sandhi
  lexicalization, Meeussen's Rule, real Nguni High-tone shift) has had zero web-UI visibility this
  whole time, and a much older, already-`architecture/OVERVIEW.md`-flagged gap (the Contour-
  representation batch's own "Not done" note, see its own entry above) named the exact same missing
  surface.

  New `tone_system` key on `_language_summary`'s own dict, always present (empty lists for a
  non-tonal language -- `ToneSystem`'s own default shape -- rather than a nullable field, so the
  frontend's own rendering logic stays a plain "is there anything to show" check): `levels` (each a
  `{level, contour, digits}` triple -- `contour`/`digits` the same real Chao (1930) pitch-level data
  `speech.reader.describe()` already prints for the CLI, via the same `TONE_CONTOURS`/`chao_letters`
  the "Not done" note above already named as trivial to add), `sandhi` (each `ToneSandhiRule`'s own
  `before`/`after`/`becomes`/`target`), `lexical_sandhi` (each `LexicalToneSandhiRule`'s own
  `gloss`/`before`/`becomes`).

  New `renderToneSection()` in `static/index.html`: a "Tone system" card section, shown only when
  `grammar.tonal` is true, with a levels-badge row and, when present, readable sandhi-rule lists. A
  `ToneSandhiRule`'s own `target` (the progressive-tone-sandhi batch's own new field) is rendered as
  the real before/after sequence transforming rather than left implicit or requiring the reader to
  already know what `target` means -- `target="before"` (Mandarin's own shape) shows
  `X + Y -> **Z** + Y` (the earlier syllable changes), `target="after"` (real Meeussen's Rule) shows
  `X + Y -> X + **Z**` (the later one does) -- each tone level shown with its own Chao contour glyph
  inline (`high ˥˥`, not just the bare word `high`), reusing the same contour data the levels badges
  already carry rather than a second lookup. Syntax-checked with `node --check` against the
  extracted `<script>` block (this project's own established substitute for a browser check, per
  this exact file's own "Untested in a browser this round" precedent -- real browser exercise stays
  the user's own manual pass, explicitly deferred this batch).

  4 new tests in `test_webui.py`: a non-tonal language's own `tone_system` is the all-empty default
  shape (a real, non-skip-guarded seed, not a flaky "if it happens to roll this way" check); a
  strict-Zulu-sourced language's own `tone_system.levels`/`sandhi` round-trip real Meeussen's Rule
  (`target: "after"`) and real Chao digits (`55`/`21`) all the way out to the API, not just through
  internal generation; and a weighted two-source-language request's own weights are confirmed
  reaching the *saved* language's own `spec.traits.source_language_weights` (reading the repository
  directly, since the summary response itself doesn't surface per-language weights back -- closing
  the "weights exist in the traits but not in the form" bullet with real proof, not just noting the
  form inputs already exist). Full suite: 1100 passed, 2 skipped (up from 1097).

  **Still open** (see `DEFERRED.md` §8, updated to match this audit): a per-lexicon-row play button
  and real-word-provenance badge (the aggregate "real-word-based: N of M" badge already exists;
  per-row doesn't); the graded-trait/`--trait`-equivalent control (the CLI's own new flag has no web
  counterpart yet); lexicon search/filter/edit/export; whole-language import/export.
- **Web app: per-lexicon-row pronunciation and provenance.** Continuing straight through the same
  §8 audit's own two remaining, genuinely tractable "Missing controls" items -- picked as the
  natural next step since both extend the exact same lexicon table the tone-system-display batch
  above had just added, rather than starting a new surface. README also updated with how to start
  and use both the CLI and the web app, at the same request (neither had ever had its own written
  quick-start before this).

  **Per-word audio.** `_language_summary`'s own lexicon entries gained `spoken_ipa`: each word's
  real spoken form with tone sandhi applied, computed as its own isolated one-word "utterance" (via
  `generation.tone_sandhi.apply_sandhi([entry.ipa], language.tone_system, [entry.primary_gloss])`)
  -- never batched across the whole lexicon, which would wrongly let a general `ToneSandhiRule`
  fire *between* two unrelated dictionary entries that just happen to sit next to each other in an
  alphabetized list. This mirrors exactly what `cli/main.py`'s own `pronounce` command already does
  for a single looked-up word, so the web UI's own per-word audio now hears the same real
  pronunciation the CLI does, not the bare, sandhi-untouched citation form. `static/index.html`
  gained a &#128266; button on every lexicon row and one event-delegated click handler (attached
  once at script load, not 400 individually-bound ones re-attached on every re-render) that POSTs
  that word's own `spoken_ipa` to the already-existing `/api/pronounce`, reusing the Translate tab's
  own `tr-tts` backend selection as a single shared pronunciation preference across the whole page
  rather than adding a second selector to keep in sync.

  **Real-word provenance.** Each lexicon entry also gained `provenance`: the entry's own real-word
  `notes` string (`"real word: Dutch"`/`"real-based word: Dutch"`) when it starts with `"real"`
  (the same test `real_words` already uses to count them), else `null`. Rendered as a small "real"
  badge next to that word's own romanization, its own `title` attribute carrying the full note
  (which language, exact vs. deviated) for a hover -- alongside the aggregate "real-word-based: N of
  M" badge that already existed, not replacing it.

  Both are pure additions to data already computed or trivially derivable server-side -- no new
  generation-side work, matching the "smallest correction" a display-only gap calls for.

  4 new tests in `test_webui.py`: every lexicon entry carries `spoken_ipa`/`provenance` (extending
  the existing "returns a language summary" test's own key-presence check); a strict-Zulu-sourced
  word's own `spoken_ipa` genuinely differs from its citation `ipa` (real Meeussen's Rule firing
  within that one word) while most words in the same lexicon are correctly left unaffected; a
  strict-Dutch/real-words-sourced language's own `provenance`-carrying entries line up exactly with
  its own `real_words` count, and every other entry's own `provenance` is `null`. Syntax-checked
  with `node --check` against the extracted `<script>` block, same established substitute for a
  browser check this file's own immediately preceding entry already used -- real browser exercise
  stays the user's own deferred manual pass. Full suite: 1102 passed, 2 skipped (up from 1100).

  **Still open** (see `DEFERRED.md` §8): the graded-trait/`--trait`-equivalent control; lexicon
  search/filter/edit/export; whole-language import/export.
- **Web app: graded-trait overrides (the CLI's own `--trait` flag, on the web).** Closes the one
  item the two batches above had each in turn left open -- of the 15 bipolar worldbuilding traits,
  the web UI had no way to set one directly, only through the prompt classifier's own reading of
  free text, same gap the CLI's own `--trait NAME=VALUE` batch (see this file's own entry on it)
  already closed there.

  New `GenerateRequest.trait_overrides: dict[str, float] = {}` on `/api/generate` -- key one of
  `core.traits.GRADED_TRAIT_FIELDS`, value -1.0..1.0, applied via the same `traits.model_copy(update=
  ...)` pattern `strictness`/`word_strictness` already use, in the same order (after both, so an
  explicit trait override always wins over whatever the prompt itself implied for that one
  dimension). `source_language_strictness`/`source_word_strictness` deliberately excluded --
  already graded 0.0-1.0 fields with their own dedicated request fields, the same "one way to set
  each, not two" discipline `cli/main.py`'s own `_parse_trait_overrides` already enforces; a request
  naming either as a trait override, or naming any field outside `GRADED_TRAIT_FIELDS` at all, or
  giving a value outside -1.0..1.0, gets a `400` with the offending name(s) named directly, mirroring
  the CLI's own error messages rather than a generic validation failure. `/api/options` gained
  `graded_trait_fields` (the same list) so the frontend never hardcodes its own duplicate.

  New "Trait overrides" dynamic rows on the Generate form's own "Advanced options" (a `<select>` of
  every graded trait name + a bounded number input, `+ trait override` to add more) -- mirrors the
  existing source-language/seed-example dynamic-row pattern exactly, except it starts with *no* row
  at page load (unlike those two): its own `<select>` needs `graded_trait_fields` from `/api/options`
  to have anything to offer, which only resolves after page load, so starting empty (rather than one
  row with a not-yet-populated select) avoids that ordering hazard entirely. No new display work
  needed for the *result* -- an overridden trait is just another nonzero value in the same
  `traits` object `/api/generate` already returns, so the existing trait-badge rendering picks it up
  automatically, the same way the CLI's own "Traits from prompt" line already shows a `--strictness`/
  `--word-strictness` override merged in without a separate visual distinction.

  5 new tests in `test_webui.py`: a request with two trait overrides reports both exact values back
  (not just "accepted"); an unknown trait name, an out-of-range value, and the two dedicated-field
  names used as overrides each get a `400` naming the actual problem; `/api/options` lists exactly
  the 15 real `GRADED_TRAIT_FIELDS` names and neither strictness field. Syntax-checked with
  `node --check`, the same established substitute for a browser check every batch in this section
  already uses -- real browser exercise stays the user's own deferred manual pass. Full suite: 1107
  passed, 2 skipped (up from 1102).

  That closes every "Missing controls" item the §8 audit originally flagged. **Still open** (see
  `DEFERRED.md` §8): lexicon search/filter/edit/export; whole-language import/export.
- **Web app: lexicon search, CSV export, in-table editing.** Asked to go ahead with "lexicon
  search/filter/edit/export" next. Scoped to a *generated* language's own lexicon specifically --
  the DEFERRED bullet's own second half (browsing/searching a *reference* language's curated real
  words) is disclosed as deliberately out of scope: `conlang audit-lexicons` already serves that
  curation-QA need on the CLI, and "editing" a reference lexicon really means editing its own YAML
  source file, a materially different, dev-facing workflow from correcting one word in a generated
  language.

  **Model layer, first.** New `Lexicon.with_replaced_entry(gloss, updated)` -- looks up the entry
  whose own *primary* gloss (case-insensitively) matches, replaces it in place (position and every
  other entry unchanged), raises `ValueError` if none matches; the *replace* counterpart to
  `with_entries`'s own *append*-only growth (real Mandarin-word-coinage-during-translation still
  goes through that one, unchanged). `Language.with_edited_entry(gloss, updated, reason)` wraps it
  the same way `with_new_words` wraps `with_entries`, logging to `history` too.

  **New endpoint, `POST /api/languages/{slug}/lexicon/edit`.** Takes `{gloss, romanization?, ipa?}`
  -- either or both, at least one required. Deliberately does *not* auto-re-derive one from the
  other (real irregular spellings exist; a user asking to edit gets direct, independent control of
  both, not a guess at which one they'd want recomputed from the other). An edited `ipa` is
  validated by round-tripping it through `ipa_tokenizer.tokenize` against the full global symbol
  pool (`_SYMBOLS`, the same "tokenize against everything this project models, not just what one
  language happens to use" pool `speech/tts.py` already needs for the same reason) -- a symbol that
  doesn't survive the round trip (silently dropped by `tokenize` itself, per its own docstring)
  means the *stored* IPA would already be broken, caught here instead of corrupting the lexicon
  silently. `tones` is recomputed from the new IPA on an IPA edit (it's its own stored field, not
  re-derived on every read, so a hand-edited IPA needs this explicitly or every tone-aware consumer
  -- pronunciation, sandhi -- would keep reading the stale sequence). The entry's own `notes` gets
  `"(manually edited)"` appended once (checked before adding, so a second edit doesn't duplicate
  it) -- an honest provenance trail, not a silent overwrite of whatever was there (including a real
  "real word: X" note, which now reads "real word: X (manually edited)").

  **Frontend: search, export, inline edit, all reusing the existing lexicon table.** A search box
  (`#lexicon-search`) filters already-rendered `<tr>`s client-side (no re-fetch) by matching
  gloss/pos/romanization/IPA/`provenance` against each row's own precomputed `data-search`
  attribute -- fast at this project's own scale (at most ~500 rows) and, since it never re-renders,
  can't clobber a row mid-edit elsewhere in the table. "Download CSV" exports only the currently
  *visible* (filtered) rows -- "search, then export" does what it looks like it should -- via a
  `Blob`/`<a download>` trick, with real CSV field-quoting (the one place this file actually
  escapes anything -- a comma or quote inside a word would otherwise corrupt the format, unlike the
  rest of this file's own established, looser HTML-interpolation convention, which is fine for
  display but not for a format with its own real syntax). A &#9998; button per row swaps that row's
  own romanization/IPA cells for `<input>`s and its own action cell for save/cancel buttons
  (`startEditingRow`); cancel just re-renders that one row from its own last-known-good data
  (`resetRow`, reusing `renderLexiconRow` -- event delegation means replacing a `<tr>`'s own
  `outerHTML` doesn't lose any handler); save POSTs to the new endpoint and, on success,
  re-renders the *whole* summary (simplest way to stay consistent with every other value the edit
  could indirectly affect, e.g. `real_words`'s own count if `notes` changed) while preserving
  whatever search filter was active; a failed save reverts that one row and shows the backend's own
  specific error message (empty value, unmodeled IPA symbol, etc.) rather than a generic failure.

  9 new tests: 3 in `test_lexicon.py` (`with_replaced_entry` swaps in place with every other entry
  and the ordering untouched, matches case-insensitively, raises for an unknown gloss); 8 in
  `test_webui.py` for the new endpoint (romanization edit persists and round-trips through a
  reload; an IPA edit recomputes `spoken_ipa`/tones correctly; editing twice doesn't duplicate the
  "(manually edited)" note; an unmodeled IPA symbol, an empty value, an unknown gloss, an unknown
  language, and a request naming neither field each get the right error). Syntax-checked with
  `node --check`, the same established substitute for a browser check every batch in this section
  already uses -- real browser exercise stays the user's own deferred manual pass. Full suite: 1118
  passed, 2 skipped (up from 1107).

  **Still open** (see `DEFERRED.md` §8): browsing/searching/exporting a *reference* language's own
  curated real-word lexicon (deliberately out of this batch's scope, see above); whole-language
  import/export.
- **Web app: whole-language export/import.** Asked to do "the whole-language import/export" next --
  the last remaining item the §8 audit's own "Missing controls"/"Persistence and sharing" bullets
  ever flagged.

  The key realization that made this simple: `YamlLanguageRepository.save`'s own 5-file split
  (`meta.yaml`/`phonology.yaml`/`romanization.yaml`/`grammar.yaml`/`lexicon.yaml`) is purely a
  storage-layer convenience (human-diffable files), not a property of the data itself --
  `load()` just re-merges all 5 back into one flat dict and calls `Language.model_validate` on
  it. So the *whole*, round-trippable representation of a language was always already
  `language.model_dump(mode="json")`, one plain dict, regardless of how many files it happens to
  live in on disk -- no new export-specific serialization logic needed, just calling that and
  handing it back as a downloadable file.

  New `GET /api/languages/{slug}/export`: `json.dumps(language.model_dump(mode="json"))`, with a
  `Content-Disposition: attachment` header so a browser triggers a real file-save dialog rather
  than navigating to a JSON blob. New `POST /api/languages/import`: takes `{data, overwrite}`,
  parses `data` through `Language.model_validate` (a real validating parse, not a trusting
  passthrough of whatever JSON showed up -- a hand-edited or corrupted file gets a `400` naming
  the actual validation failure, not a silent partial import or a crash), and refuses to save
  over an already-existing language with the same name unless `overwrite: true` is explicit (a
  `409`, not a clobber) -- the same "look before overwriting" discipline this project's own
  destructive-action conventions already require, enforced here server-side rather than left to
  whatever a browser's own file-save dialog does or doesn't warn about.

  Frontend: an "export" button next to the Translate tab's own language picker (downloads
  whichever language is currently selected there) and another on a freshly generated language's
  own result-card heading (reusing the same `downloadLanguageExport()`, just with that summary's
  own `slug` already in scope); a plain `<input type="file">` "Import a language file" control --
  reading the file client-side via `file.text()`/`JSON.parse`, not a multipart upload, keeping
  every endpoint in this API JSON-only rather than introducing a second request shape just for
  this one feature. A `409` from the import endpoint triggers a native `confirm()` dialog
  ("already exists -- overwrite it?") and, on yes, one retry with `overwrite: true` -- a plain
  browser-native prompt rather than a custom modal built for this one use case, matching this
  project's own "simple, replaceable implementations" bias. `api()` (the shared fetch helper
  every JSON endpoint call in this file already goes through) gained `error.status` on a failed
  call, so this branch (and any future one) can check the real HTTP status code rather than
  string-matching the backend's own error message text.

  5 new tests in `test_webui.py`: export returns the full model (not the trimmed summary) with the
  right `Content-Disposition`; exporting an unknown language is a `404`; a full export/import
  round trip into a genuinely *different* `LANGUAGES_DIR` (simulating a separate install, not just
  re-saving over the same store) preserves the lexicon; importing over an existing name is
  refused without `overwrite: true` and succeeds with it; importing data that isn't a valid
  language is a `400`. Syntax-checked with `node --check`, the same established substitute for a
  browser check every batch in this section already uses -- real browser exercise stays the
  user's own deferred manual pass. Full suite: 1123 passed, 2 skipped (up from 1118).

  That closes every item `DEFERRED.md` §8's own audit ever flagged, except the one explicitly
  disclosed as out of scope (reference-language lexicon browsing, see the batch above).
- **Web app: browsing a reference language's own curated lexicon.** Asked to implement the one item
  explicitly disclosed as out of scope in the batch above -- browsing/searching/exporting a
  *reference* language's own curated real-word data (`generation/reference_languages/lexicons/
  <name>.yaml`, `conlang audit-lexicons`'s own data source), not a *generated* language's lexicon
  (already done). A new, third "Reference" tab, entirely read-only -- "editing" this still means
  editing its own YAML source, a dev workflow this batch deliberately leaves alone, unchanged from
  the previous batch's own disclosure.

  New `GET /api/reference-languages`: every curated profile that actually has a lexicon (`real_
  lexicon.curated_profiles` already does this filtering -- a profile with typology only and no
  `lexicons/<name>.yaml` of its own is correctly absent, the same "abstain, don't show an empty
  browse view" discipline `conlang audit-lexicons` already practices), with its own word count and
  `tonal` flag for the picker's own option labels. New
  `GET /api/reference-languages/{name}/lexicon`: that language's own `{gloss, spelling, ipa}` triples
  (`real_lexicon.real_words`), each also carrying `loan` (`real_lexicon.loan_glosses`) and `flagged`
  -- reusing `lexicon_audit.audit_language` (the *exact* function `conlang audit-lexicons` itself
  calls, not a reimplementation) to surface *which* word has a transcription issue and *why*
  (`WordIssue.detail`, e.g. "illegal cluster/coda at n i w | s" for Dutch *nieuws*), visible per word
  here rather than only as an aggregate count on the CLI. A loanword is never flagged on being a loan
  alone -- `audit_language`'s own default (`include_loans=False`) already grants it the same real
  exemption from native phonotactic scrutiny the CLI audit does, reused as-is, not re-decided here.

  Frontend: search and CSV export mirror the generated-lexicon table's own pattern from the earlier
  batch, deliberately re-implemented as their own separate functions/element ids
  (`filterReferenceTable`/`#reference-tbody`/etc.) rather than literally shared with the generated
  table's own (`filterLexiconTable`/`#lexicon-tbody`) -- both tables can genuinely be in the DOM at
  the same time (a hidden panel, not an unmounted one, when its own tab isn't active), so sharing one
  set of ids between them would have one table's own search silently act on the other's rows. A play
  button per word reuses `playWordPronunciation` directly (generalized with a new `errBoxId`
  parameter, defaulting to the generated-lexicon table's own error box, so this is a one-line addition
  to an existing function rather than a near-duplicate copy) -- `/api/pronounce` already accepts any
  raw IPA text regardless of source, so no new synthesis path was needed. One real, disclosed
  difference from the generated lexicon's own play button, though: a reference entry carries no
  stored `ToneSystem` of its own to derive real spoken sandhi from the way a generated language's
  lexicon does (whose own `spoken_ipa` already has sandhi applied, see the earlier per-word-audio
  batch) -- so a reference word is heard exactly as transcribed, and its own button's tooltip says so
  plainly rather than silently implying the same real-spoken-form guarantee.

  5 new tests in `test_webui.py`: the language list only includes profiles with a genuine lexicon
  (cross-checked against `real_lexicon.real_words` directly, not trusted blind); a lexicon fetch
  returns real curated words with every expected field; a known real Dutch transcription issue
  (*nieuws* -- niws's own real illegal coda cluster) is correctly flagged, with its own real detail;
  a Basque loanword is correctly marked `loan` and never flagged on that basis; an unknown language
  name is a `404`. Syntax-checked with `node --check`, the same established substitute for a browser
  check every batch in this section already uses -- real browser exercise stays the user's own
  deferred manual pass. Full suite: 1128 passed, 2 skipped (up from 1123).

  That closes every item `DEFERRED.md` §8 ever flagged, in full -- nothing left open in that section.

- **Noun number and clause types (grammar pass 1).** `GrammarProfile` gains `number_affixes` (one
  `"plural"` suffix), `mood_affixes` (one `"imperative"` suffix) and `question_particle` (IPA of a free yes/no
  particle), generated for every language in `generator.py` from an *independent* rng stream
  (`Random(f"{seed}:clause-grammar")`) so no existing lexicon draw shifts; the particle is re-rolled if it
  spells like a lexicon word. `PlannedSlot.number` (`"plural"`) and `SentencePlan.mood` (`declarative`,
  `imperative`, `question`, `wh_question`) are read from the planner's reply, now `{"mood", "slots"}` (a bare
  array is still accepted). `translate_to_conlang` splits input with `sentence_planner.split_sentences`, plans
  and renders each sentence alone (`_render_plan`): plural composes with case into one affix
  (`_noun_affix`, a distinct rng salt only when number is involved, so pre-existing output is unchanged), the
  first verb/copula of an imperative takes the imperative suffix instead of tense/agreement, and a yes/no
  question gets the particle at the end (start for VSO/VOS). `translate_to_english` decodes plural
  (`_decode_noun` labels such as `"plural"`/`"accusative+plural"`), imperative (`_decode_verb` returns
  `"imperative"`) and the particle, and the fluency prompt gets the matching annotations. The fake planner
  reads mood from final punctuation and a suffix heuristic for plurals. 16 tests in `test_clause_types.py`.
  Simplifications: isolating languages get the plural as an attached clitic; vocatives are ordinary sentence-
  initial nouns; evolution does not yet evolve the new affixes/particle.

- **Nested plan structure (grammar pass 2).** `PlannedSlot` gains `kind="clause"` with `clause:
  SentencePlan` (the subordinate clause's own plan), `gloss` (the linking word: that/because/if/when/
  who/which, may be empty) and `role` (`complement`/`relative`/`adverbial`, informational). `_parse`
  reads nested `{"clause": {"slots": [...]}}` recursively (`_slots_from_raw`), caps nesting at
  `MAX_CLAUSE_DEPTH = 3` (deeper clauses are flattened into their parent, words kept), drops empty or
  malformed clause slots, and `flatten_slots` reads a plan's words in order. `translator._render_plan` is
  now recursive: a clause slot renders its nested plan (always declarative -- only a main clause can be
  an imperative or question, and only the top-level plan gets the question particle), looks up or coins
  the linking word as a particle (`_lookup_or_coin`), and places it after the clause in SOV/OSV
  languages and before it otherwise (`_linker_follows_clause`, illustrative). Decoding is unchanged: the
  linker is an ordinary lexicon word. The planner prompt describes clause slots, the never-flatten rule
  and placement, plus an example; the fake planner (`_fake_plan_dict`) splits at the first of
  that/because/if/when/although/while that has a main clause before it and two or more words after it,
  repeating on the remainder. 13 tests in `test_nested_clauses.py`.

- **Aspect and verbal mood (grammar pass 3).** `GrammarProfile` gains `aspects` (none, two-way, or four-way
  systems in `inflection_gen.ASPECT_SYSTEMS`), `aspect_affixes`, and `moods` (none / irrealis / subjunctive-
  conditional-potential, `MOOD_SYSTEMS`); their affixes join `mood_affixes` beside `"imperative"`. Rolled and
  generated in `generator.py` from a third independent rng stream (`Random(f"{seed}:aspect-mood")`), with
  suffixes re-drawn until distinct from the language's other verb suffixes (`_distinct_suffixes`), because
  short invented suffixes otherwise collide (tense/case/agreement suffixes, generated earlier, still can).
  `PlannedSlot` gains `aspect` and `verb_mood`; the planner prompt lists the language's own labels and how to
  map English wording onto them. `_combined_tense_agreement_affix` composes aspect + tense + mood + agreement
  suffixes into one affix (identical to the earlier tense+agreement output when aspect/mood are unused, and the
  rng salt only grows when they are used, so existing output is unchanged). Decoding is `_decode_verb_full`:
  generate-and-compare over tense x aspect x mood x agreement, restricted to verbs with the token's first
  letter (falling back to the earlier tense x agreement search over all verbs) and ordered plainest-reading-
  first because short suffixes concatenate alike; `_decode_verb` keeps its old `(entry, tense)` shape. The
  English side gets `(tense/aspect/mood: X)` annotations and a rough `_english_verb_phrase` draft. The fake
  planner reads "am/was ...ing", "have/has/had + participle" and would/may/might/can/could. 14 tests in
  `test_aspect_mood.py`.

- **Noun classes and agreement (grammar pass 4).** New `generation/noun_class_gen.py`:
  `NOUN_CLASS_SYSTEMS` (none, masc/fem, masc/fem/neuter, animate/inanimate, human/animal/plant/thing), rolled with
  object agreement (30%) in `generator.py` from a fourth independent rng stream (`Random(f"{seed}:noun-class")`).
  `GrammarProfile` gains `noun_classes`, `class_affixes` (one per class, for articles/adjectives), `object_agreement`
  and `object_agreement_affixes` (person labels + `"class:<name>"`); class-based *subject* agreement labels
  (`"class:<name>"`) are appended to `agreement_affixes`. A noun's class is derived, never stored
  (`noun_class`: natural gender/animacy lists first, then a stable hash of `(seed, gloss)`), so no lexicon draw
  shifts and coined nouns get a class for free. The planner gets `agrees_with` (adjectives), `subject_gloss` and
  `object_gloss` (verbs); the renderer (`_verb_agreement`, `_apply_class_agreement`, `_next_noun_gloss`) swaps a
  noun subject's class in for the `"default"` agreement label, adds the object marker, agrees adjectives with
  `agrees_with` and agrees each article with the next noun slot. Decoding: `translate_to_english` drops every
  article spelling (`_article_forms`), `_decode_adjective` reads class-marked adjectives, and
  `_decode_verb_full` searches subject-agreement labels including classes and, in stages (tense x agreement x
  object first, then aspect/mood, then all together only in object-agreement languages), the object marker. The
  fake planner sets the new fields from the noun tokens. 18 tests in `test_agreement.py`.

- **Noun-phrase features (grammar pass 5).** New `generation/noun_phrase_gen.py`, rolled from a fifth independent
  stream (`Random(f"{seed}:noun-phrase")`): `dual` number (a `"dual"` suffix appended to `number_affixes`),
  `plural_after_numeral`, `demonstrative_after_noun`, `has_indefinite_article`, and `possession` (`"genitive"`
  when the language has that case, else `"particle"` with `possessive_particle`, `"affix"` with a `"possessed"`
  suffix in `possession_affixes`, or `"none"`); the possessive particle is re-rolled to differ from the lexicon
  and the question particle. `GrammarProfile.postpositional` (SOV/OSV/OVS) is derived, not stored. The planner
  gets slot kinds `demonstrative` and `indefinite_article`, `PlannedSlot.possessive`, number `"dual"`, and a
  prompt describing the language's own number labels, demonstrative/adposition order, numeral behaviour and
  possession strategy. The renderer composes number + possessed + case into one affix (`_noun_affix`, salt only
  grows when number or possession is used), applies the genitive to a possessive slot, adds the particle after
  it, or marks the next noun (`possessed_pending`), drops the plural after a numeral where the language does
  (`_effective_number`), agrees demonstratives and the indefinite article with the noun's class
  (`_prev_noun_gloss`/`_next_noun_gloss`) and coins "a"/"this"/"that" on first use. Decoding: `_decode_noun`
  also tries the possessed forms (labels like `"accusative+plural+possessed"`), `_article_forms` includes "a",
  `_decode_adjective` also decodes class-marked demonstratives, and the possessive particle decodes to "of". The
  fake planner groups modifier runs into placeholder noun phrases (`_fake_group_noun_phrases`) so
  my/your/his/our/their, X's, this/that/these/those, numerals and a/an work. 22 tests in `test_noun_phrase.py`.

- **Voice (grammar pass 6).** `GrammarProfile` gains `voices` (`inflection_gen.VOICE_SYSTEMS_NOM_ACC`:
  none / passive / passive+causative; `VOICE_SYSTEMS_ERGATIVE`: none / antipassive / antipassive+causative /
  passive+antipassive, rolled by alignment) and `voice_affixes`, from a sixth independent stream
  (`Random(f"{seed}:voice")`), suffixes distinct from the other verb suffixes. `PlannedSlot.voice` is read from
  the planner; the prompt lists the language's voices and spells out the argument reassignment (passive
  patient = subject with no object case, agent as "by" phrase in the language's adposition order; antipassive
  agent = plain absolutive; causative causee = object; a missing voice is reworded as an active). The renderer
  only adds the suffix (voice first in the composed verb affix, `:v=` in the salt) -- case and order come from
  the plan. `_decode_verb_full` returns `(entry, tense, aspect, mood, voice)`; its search is staged (tense x
  agreement x object; voice; aspect/mood; aspect x voice; aspect/mood x object) and restricted to verbs sharing
  the token's first two letters (`_stem_prefix`). English gets `(voice: X)` annotations and a `was seen`/`made
  see` rough draft. The fake planner (`_fake_voice_slots`) plans passives (irregular participle or a "by"
  phrase, so "is tired" stays an adjective), the active rewording where the language has no passive, and "make
  X do Y" causatives. 19 tests in `test_voice.py`.

- **Existentials and possession clauses (grammar pass 7).** `GrammarProfile` gains `existential`
  (`"copula"`/`"verb"`, default `"copula"`) and `possession_clause` (`"have"`/`"dative_be"`, default `"have"`),
  rolled in `generator.py` from a seventh independent stream (`Random(f"{seed}:existence")`). This pass is
  planner-driven like voice: the prompt states the language's strategy ("there is X" = X + the copula slot / X +
  a content verb "exist"; "A has B" = a transitive "have" / no "have": possessor first in the dative or
  possessor-marked, then the existential construction with B as subject) and forbids a slot for "there"; the
  renderer needs no new mechanism (the words "exist"/"have"/"be" are ordinary lexicon words, coined on first
  use). The English direction gets `_construction_note(language)` appended to the fluency prompt so the model
  can read the pattern back. The fake planner (`_fake_existence_slots`) plans "there is/are/was X", "is there
  X?", "there is no X" and, in `dative_be` languages, "A has/had B"; `have`/`has`/`had` now map to the lemma
  "have". 15 tests in `test_existence.py`.

- **Comparatives and superlatives (grammar pass 8).** `GrammarProfile` gains `comparative_strategy`
  (`"particle"` "than" word / `"case"` oblique standard using `comparative_case` / `"exceed"` verb),
  `comparative_marking` and `superlative_marking` (`"affix"`/`"word"`) and `degree_affixes` (labels `comparative`/
  `superlative`, only for affix-marked degrees), rolled in `generator.py` from an eighth independent stream
  (`Random(f"{seed}:degree")`), suffixes distinct from class/case/number ones. `PlannedSlot.degree` marks an
  adjective; word-marked degrees and the standard are ordinary slots ("more"/"most" adverb, "than" preposition,
  a case on the standard, or a verb "exceed"), told to the planner by strategy. `_apply_class_agreement` now takes
  an optional degree (degree suffix closer to the root than the class suffix; a distinct rng salt only when a
  degree is used); `_decode_adjective_full` returns `(entry, class, degree)` over class x degree combinations,
  plainest first, and `_decode_adjective` keeps its old shape. The English side prints `more X`/`most X` and the
  fluency prompt gains a "Comparison:" note (`_construction_note`). The fake planner (`_fake_degree_slots`,
  `_fake_degree_of`) plans "X is Adj-er/more Adj than Y", "X is more Adj" and "X is Adj-est/most Adj" for a small
  list of known adjectives. Also fixed while testing this: `expansion.coin_word` now retries a colliding coined
  word up to 40 times instead of 6 (a tiny inventory produced a homograph, "than" = "cold"). 16 tests in
  `test_degree.py`.

- **Classifiers and the pronoun system (grammar pass 9).** Two new modules and two independent rng streams
  (`Random(f"{seed}:classifier")`, `Random(f"{seed}:pronoun")`). `generation/classifier_gen.py`: whether the
  language uses classifiers (`GrammarProfile.uses_classifiers`; 45% isolating, 12% otherwise; switches
  `plural_after_numeral` off) and `classifier_category(gloss)` (human/animal/long/flat/round/general from small
  gloss lists, no rng, no stored field); the classifier of a category is an ordinary lexicon word with gloss
  `classifier-<category>`, coined via `_lookup_or_coin`. `_render_plan` inserts it after a numeral or
  demonstrative slot when a noun follows (`_takes_classifier`, `_following_noun_slot`, looking past adjectives),
  and the English direction drops such tokens. `generation/pronoun_gen.py`: `clusivity`, `third_person_gender`,
  `honorific_you` (biased by `social_hierarchy`), `pro_drop` (forced off unless the four person agreement
  suffixes are distinct), the language's pronoun glosses (`pronoun_glosses`), the English-to-gloss mapping
  (`english_pronoun_gloss`, mirrored in the fake planner) and `person_label` (every pronoun gloss agrees like
  I/you/he/we). The planner prompt lists the glosses and mapping; `_dropped_subject_pronouns` omits the first
  pronoun slot matching a verb's planned person; `_decode_verb_full` now returns the agreement label as a sixth
  element so a dropped subject is read back (`translate_to_english`, guarded by `_person_suffix_is_distinct`);
  pronoun glosses read back as `you (plural)` etc. 12 tests in `test_classifiers.py`, 18
  in `test_pronouns.py`; `test_translator.py`'s fixture now also switches off `pro_drop` and classifiers.

- **Pronoun/classifier follow-ups (grammar pass 10).** Classifier variety: `classifier_gen.roll_classifier_system`
  (same first draw as before, so non-classifier languages and older seeds are unchanged) adds
  `classifier_categories` (a subset of twelve categories, always with `general`; a noun whose category the
  language lacks takes `general`), `classifier_after_noun` (25%) and `classifier_with_demonstrative` (80%). The
  renderer now inserts classifiers by transforming the slot list up front (`_with_classifiers`: a synthetic
  `"classifier"` slot after each numeral/demonstrative, the numeral and classifier moved behind the noun in an
  after-noun language, the noun's number cleared after a numeral above "one") instead of at render time.
  Pronoun extras (`pronoun_gen.roll_pronoun_extras`, its own stream `Random(f"{seed}:pronoun-extras")`): `reflexive_marking`
  / `reciprocal_marking` (`word` = an object pronoun `self`/`each-other`, `affix` = a `reflexive`/`reciprocal`
  entry appended to `voices`/`voice_affixes`, `none` = an ordinary pronoun), `possessive_pronouns` (`regular`;
  `words` = lexicon words `possessive-<gloss>` from a new `possessive_pronoun` slot kind, class-agreeing;
  `affix` = `possessor_person_affixes`, a person suffix on the possessed noun via `_noun_affix(...,
  possessor_person)`), `verb_number_agreement`/`verb_politeness` (`verb_number_affixes`, `verb_polite_affixes`,
  composed after the person suffix; planner fields `subject_number`, `polite`) and `object_pro_drop` (only with
  object agreement and four distinct person object suffixes; `_dropped_object_pronouns`). `_decode_verb_full`
  now returns nine fields (…, agreement, object label, number, polite) with a staged search that adds an
  "extras" stage; `translate_to_english` reads the new words and marks back through `pronoun_gen.english_reading`,
  `_person_suffix_is_distinct(..., objects=True)`. 20 new classifier tests and 28 in `test_pronoun_extras.py`;
  `test_voice.py` now compares the roll's voices without the reflexive/reciprocal ones.

- **Suppletive pronouns, reflexive possessives, possessive classifiers (grammar pass 11).**
  `pronoun_gen._roll_later_extras` (drawn after the pass-10 rolls, so those are unchanged) adds
  `suppletive_pronoun_persons` (35%; a random subset of I/you/he/we whose non-nominative case forms are lexicon
  words `<pronoun>-<case>`, e.g. `i-accusative`; `suppletive_gloss`/`suppletive_split`/`suppletive_reading`) and
  `reflexive_possessive` (`word` = `possessive-self`, `affix` = a `"self"` entry in `possessor_person_affixes`,
  `none`). `classifier_gen` gains `possessive_classifiers` (30% of classifier languages; classifier words
  `possessive-classifier-<category>`, `_is_possessor_word`, inserted by `_with_classifiers` after a possessor
  word). The renderer: `_suppletive_case` makes a pronoun slot look up the suppletive word instead of applying a
  case suffix (nominative/absolutive never; genitive when the possessive is genitive-marked);
  `_normalize_possessives` folds a `possessive_pronoun` slot back into an ordinary possessor where the language has
  no special form (`self` reads as `he` in a language without a reflexive possessive). Decoding reads suppletive
  forms as their English object/possessive form (`me`, `him`, `his`), `poss:self` as "the subject's own", and
  drops possessive classifiers. 20 tests in `test_pronoun_paradigms.py`.

- **Quantifier classifiers and per-noun classifiers (grammar pass 12).** `classifier_gen._roll_individual_classifiers`
  (drawn after the earlier classifier rolls, so those are unchanged) adds `classified_quantifiers` (a random subset of
  `QUANTIFIERS`), `classifier_assignment` (`category`, or `lexical` with a pool of 12-40 classifiers:
  `classifier_pool_size`, `lexical_index`, glosses `classifier-lexNN`) and `repeater_rate` (0, or 10-50% of
  nouns being their own classifier; `is_repeater`, `REPEATER_GLOSS_PREFIX`). A new plan `pos` `"quantifier"` (mapped to
  `PartOfSpeech.NUMERAL`) is placed like a numeral; `_takes_classifier(slot, grammar)` now covers numerals,
  demonstratives and the language's classified quantifiers, and `_classifier_slot` builds the synthetic classifier slot
  for a noun (repeater, else pool, else category; possessive classifiers never repeat). A repeater renders as the
  noun's own word again (`kind="classifier"`, gloss `repeater:<noun>`), and `translate_to_english` removes a noun
  repeated adjacently or around a numeral (`_drop_repeaters`). The fake planner recognizes many/few/some/several/
  every/each/all/both (every/each keep the noun singular). 19 tests in `test_classifier_individual.py`; the older
  classifier tests now pick category-assigned, repeater-free languages when they assert category names.

- **Subordination refinements (grammar pass 13).** New `generation/subordination_gen.py`, rolled from its own
  stream (`Random(f"{seed}:subordination")`): `subordinator_position` (`before`/`after`, correlated with a verb-final word
  order; empty on an older language, which keeps the earlier verb-final rule), `relativization` (`pronoun`,
  `particle`, `gap`, `resumptive`, `correlative`), `relative_clause_position`, `verb_forms`/`verb_form_affixes`
  (`infinitive`, `nominalized`, `participle`) and `subordinate_mood_use`. The renderer enforces the language's own
  strategy on any relative clause whatever the planner wrote (`_linker_gloss`: none for a gap, `rel` for a particle
  or resumptive clause, `who`/`which` otherwise); `_arrange_relatives` moves a relative clause (the planner writes it
  right after its noun) before its whole noun phrase in a `before_noun` language (`_np_start`) or to the front
  of the plan with a correlate demonstrative "that" in a correlative one; `_linker_follows_clause(language, role)`
  places the subordinator. A non-finite `PlannedSlot.verb_form` renders as its suffix instead of tense/agreement
  (`_verb_form_salt`) and decodes like the imperative (the form in the tense slot, read as `to see`/`seeing`);
  `_subordinate_mood` forces a subjunctive/irrealis on the verbs of an `if`/`unless`/`so that`/`although` clause
  (passed down through `_render_plan(..., forced_verb_mood)`; a planner's own `verb_mood` wins). The fluency prompt
  gains a "Subordination:" note. The fake planner plans relative clauses ("who"/"which", subject a gap unless
  resumptive) and infinitive complements after want/like/try/begin/need/hope/decide/love. 27 tests in
  `test_subordination.py`; `test_nested_clauses.py` now selects languages by `subordinator_position`.

- **Subordination follow-ups (grammar pass 14).** `subordination_gen.roll_subordination_followups` (drawn after the pass-13
  rolls from the same stream, so those are unchanged): `relativization_reach`, `relative_pronoun_declines`,
  `relative_pronoun_number`, `infinitive_agrees`, `nominalized_takes_case`, `conditional_main_mood`,
  `conditional_clause_tense`, `correlative_adverbials`, `clause_coordination` (`word`/`converb`/`juxtapose`),
  `conjunct_reduction`, `complementizer_by_verb`, and a `converb` non-finite form appended to `verb_forms`. New plan
  fields: `PlannedSlot.rel_function` on relative clause slots, clause roles `nominal` and `coordinate`, `case` on
  a clause slot. Renderer: `_annotate_relative_heads` (head number), `_linker_gloss(language, slot, governor)`
  (beyond-reach gap -> `rel`; declined `who-accusative`/`-plural`; class complementizers `that-<class>` from
  `_governing_verb`; coordination word only in a `word` language), `_arrange_coordination` (last verb before a
  coordinate clause becomes a converb), `_arrange_correlative_adverbials` (fronts if/when/the-more clauses and adds
  the correlate), `_reduce_conjunct`, `_main_clause_mood`/`_subordinate_tense` (conditional sequencing, threaded through
  `_render_plan(..., forced_verb_mood, forced_verb_tense, forced_nominal_case)`), and `_apply_verb_inflection` composing a
  non-finite suffix with an agreement (infinitive) or case (nominalized) suffix (`_non_finite_affix`). `_decode_verb_full`
  returns ten fields (the last is the nominalization's case) and tries plain non-finite forms first. English readings:
  `whom`/`whose`, `that (complementizer for a desire verb)`, `see and`, `to go (controller: he)`. The fake planner marks
  relative functions, keeps resumptive pronouns where needed, plans object-controlled infinitives and clause
  coordinations, and gives the main verb of a "that" sentence a verb pos. 34 tests in `test_subordination_followups.py`.

- **Agreement follow-ups (grammar pass 15).** A separate `{seed}:agreement` rng stream (`noun_class_gen.roll_agreement_extras`)
  sets `noun_class_assignment` (`hash`/`semantic`/`formal`; `assigned_class` uses natural gender first, then a
  semantic-field hash from `_SEMANTIC_FIELDS` or the noun's final sound), `class_marking` (`none`/`suffix`/`prefix`, with
  `class_marker_affixes` from `distinct_suffixes` or `generate_class_prefixes`, only when the language has classes) and
  `class_agreement_targets` / `number_agreement_targets` / `case_agreement_targets` over `AGREEMENT_CATEGORIES`
  (article, adjective, demonstrative, possessive, numeral). Old saved languages default to the legacy four class targets.
  Renderer: the class marker is the first noun affix (`_noun_affix`, `_apply_case`); `_agreement_target` finds the noun a
  word agrees with from position (direction from `adjective_after_noun`/`demonstrative_after_noun`, copula, negation and
  adverbs transparent), `_agreement_features` yields class/number/case (an explicit `agrees_with` still wins), and
  `_apply_class_agreement` composes degree, class, number and case suffixes. Decoding: `_decode_noun` loops over marker,
  case, number and possession stages; `_decode_adjective_full` and `_article_forms` enumerate class x number x case.
  Planner prompt says agreement is inferred and `agrees_with` optional. 24 tests in `test_agreement_followups.py`.

- **Aspect/mood follow-ups (grammar pass 16).** `inflection_gen.roll_aspect_followups` (own `{seed}:aspect-followups` stream)
  rolls `evidentials` (`EVIDENTIAL_SYSTEMS`), `negation_strategy` (`particle`/`affix`/`both`, with a `verb_negative_affixes`
  suffix unless `particle`), a `prohibitive` (one more `mood_affixes` label), `periphrastic_labels` (tense/aspect/mood
  labels spelled by an `aux-<label>` particle, from `PERIPHRASTIC_CANDIDATES`) and `auxiliary_position`.
  `inflection_gen.resolve_collisions` runs last in `generate_language`: over the verb, noun and modifier suffix
  groups it keeps the first suffix of each shape and re-draws later duplicates (longer ones when the short shapes run
  out). Renderer: `_split_periphrastic` takes the periphrastic labels off a verb/copula (never a command or non-finite
  form) and `_auxiliary_entries` coins/reuses the auxiliary words, emitted before or after the verb;
  `_negation_absorption` folds a `negation` slot into its nearest finite verb (`affix`/`both`) or, in an imperative,
  into the prohibitive (`_prohibitive_salt`); `PlannedSlot.evidential` adds an evidential suffix; the composed verb
  affix order is voice, aspect, tense, mood, evidential, negative, agreement, number, politeness, object.
  Decoding: `_split_auxiliary_tokens` reads each auxiliary word's label onto the verb beside it (`finite_first` tries
  finite readings before non-finite forms), `_decode_verb_full` returns twelve fields (evidential and negative appended),
  tries the prohibitive like the imperative, and searches evidential/negative combinations in extra stages. English readings:
  `will`, `reportedly`/`apparently`, `not`, `do not`. `sound_change._evolve_grammar_affixes` runs the language's sound
  changes over every `InflectionAffix` (own `{seed}:affix-evolution` stream, one result per distinct shape) and then
  re-resolves collisions, so an evolved language's grammar no longer stays frozen. The fake planner marks evidentials
  (`reportedly`, `apparently` ...) when the language has the label and understands "did/does/do not". 23 tests in
  `test_aspect_followups.py`.

- **Voice and noun-phrase follow-ups (grammar pass 17).** `generation/voice_np_gen.py` (`roll_followups`, own
  `{seed}:voice-np-followups` stream): extra `voices` (`middle`, `applicative`, `impersonal`, each a suffix), `passive_agreement`
  (`patient`/`none`), `passive_agent` (`word`/`case`), extra number labels (`trial`, `collective`), extra cases (`locative`,
  `instrumental`, only when the language already has cases), `adposition_case_strategy` (`none`/`governs`/`case_only`,
  from `ADPOSITION_CASES`), `suppletive_plurals` (`IRREGULAR_PLURALS`), `suppletive_degrees` (`SUPPLETIVE_DEGREES`) and
  `inalienable_possession`. Renderer: `_arrange_adpositions` (runs first in `_render_plan`) finds each adposition's noun
  phrase (`_np_extent`), moves the adposition to the language's side, gives the head noun the governed case and drops
  the adposition where a locative/instrumental case (or the instrumental passive agent) replaces it;
  `_suppletive_form_kind` swaps in a `child-plural` / `good-comparative` lexicon word (looked up or coined like any other,
  classed with its base noun by `_class_gloss`); `_unmarked_possessors` skips genitive/particle/possessed-affix marking
  before an inalienable noun; `_verb_agreement` gives `impersonal` (and, with `passive_agreement: none`, `passive`) the
  default agreement. Decoding needed no new search (the generic voice, number and case loops cover the new labels);
  English readings: `gets seen`, `see for`, `one sees`, `three dogs`, `group of dogs`, `in house`, `with dog`, `children`,
  `better`. The fake planner produces trial/collective from "three"/"all" and the new voices from short shapes. The
  planner prompt lists the new labels and says adpositions are always separate slots. 25 tests in
  `test_voice_np_followups.py`.

- **Noun-phrase follow-ups, round two (grammar pass 18).** `generation/np_followups_gen.py` (`roll_followups`, own
  `{seed}:np-followups-2` stream): `suppletive_pronoun_case_limits` (per suppletive person, the only cases with a word
  of their own), `adjective_placement` (`global`/`split` with `adjective_before_classes`), `adjective_stack_order` (a
  permutation of `ADJECTIVE_CLASSES`), `adjective_stack_linker`, `article_source` (`demonstrative`: `generate_language`
  replaces the `the` entry by `derive_article_ipa(that)` when that is shorter, non-tonal and collision-free) and
  `has_specific_article`. Renderer: `_arrange_adjectives` (first in the pre-transforms) gathers the adjectives around each
  noun head, sorts by class order (mirrored after the noun), places them by class in a split language (a sentence with no
  verb is treated as a predicate and left alone) and inserts `conjunction` slots; `_agreement_target` picks an
  adjective's direction from its class in a split language; `_suppletive_case` honours the limits (other cases take the
  ordinary suffix on the base pronoun); a `specific_article` slot renders the `a-certain` particle (falling back to `a`, or
  nothing). English readings: `a certain`. The fake planner now plans attributive adjectives (on the language's side) and
  "a certain". 22 tests in `test_np_followups2.py`.

- **Noun-phrase follow-ups, round three (grammar pass 19).** `np_followups_gen.roll_round_three` (own
  `{seed}:np-followups-3` stream): extra `SPATIAL_CASES` (ablative, allative, comitative, ...) for languages whose
  `adposition_case_strategy` uses cases, `classifier_with_adjective`, `drop_measure_of`, `possessive_word_persons`,
  `suppletive_past` (`voice_np_gen.IRREGULAR_PASTS`), `deictic_articles` and `demonstrative_doubling`; the derived definite
  article now also works in tonal languages (the tone of `that` is kept). Renderer: `_arrange_adpositions` knows about 25
  adpositions (`ADPOSITION_CASES`, with `FALLBACK_CASES`: with -> comitative, to -> allative) and drops "of" after a
  `MEASURE_NOUNS` head; `_arrange_adjectives` treats "adj and adj" as one run and re-decides the "and";
  `_with_classifiers` adds a classifier beside an attributive adjective (before the noun, or between the noun and a
  following adjective, never a second one for a noun already classified) and after a numeral/demonstrative that has
  `PlannedSlot.classifier_for` but no noun; `_normalize_possessives` turns a person without a possessive word into a
  possessor pronoun; the verb branch swaps in a `go-past` word (tense marking dropped) for a listed verb in the past;
  `_reduced_demonstrative` derives `this-article` on first use beside a noun; `_double_definiteness` inserts the article;
  the specific article and `this-article`/`that-article` take agreement (`_agreement_category`). Decoding: a
  suppletive past reads back as tense past on its base verb, an auxiliary's host verb prefers the reading without a tense
  suffix when the auxiliary carries the tense (`auxiliary_tense` in `_decode_verb_full`; this also fixes an ambiguity in
  pass 16), and a case-only noun is read as `in/with/from/to/together with`. 24 tests in `test_np_followups3.py`.

- **Decoding speed (pass 20).** Unknown-token decoding is generate-and-compare (render every candidate, compare with the
  token), so the cost is candidates x per-candidate rendering. Per candidate: `ipa_tokenizer.tokenize` indexes its symbol set
  by first character (`lru_cache` on the frozenset), `RomanizationScheme._known_by_first_char` (a `cached_property`) does the
  same for `_tokenize`, and `inflection_gen._known_symbols_for` computes an inventory's tokenizer symbols once (an id-keyed
  cache that holds the inventory). Fewer candidates: `_decode_noun` only tries nouns whose first two letters match the token
  when every noun affix is a suffix (with a class-marker *prefix*, it compares against each noun's marked bare form instead;
  any other prefix disables the filter), and `_decode_verb_full` runs the command and non-finite forms (`special`) over the
  same first-letter candidates before the rest. Results are unchanged: `test_decoding_speed.py` compares the indexed
  tokenizer and romanization lookup with the plain algorithms, sweeps encode -> decode over 40 languages and bounds an
  unknown token's decode time.

- **Comparison follow-ups (grammar pass 21).** `generation/comparison_gen.py` (`roll_followups`, own
  `{seed}:comparison-followups` stream, run once the cases are final): `equative_marking`, `excessive_marking`,
  `elative_marking` (`affix`/`word`, an affix adding a `degree_affixes` label), `adverb_degree`, and a re-decided standard
  (`comparative_strategy`/`comparative_case`: any of ablative, locative, dative, genitive the language has, and a 25%
  chance for a language with such a case to switch to a case standard). `DEGREE_LABELS`, `DEGREE_WORDS` and
  `DEGREE_READING` list the five degrees. Planner: `degree` accepts all five; the prompt describes each, the equative's
  standard ("as" preposition or the case) and adverbs; the fake planner plans "as big as", "too big", "very big" (an elative
  suffix language), a longer adjective list and "The more X, the more Y" (`_fake_the_more_plan`: the second part is the main
  clause, the first a `the-more` adverbial clause, each with the adverb "more"). Renderer: an adverb takes a degree suffix
  when `adverb_degree` (`_agreement_category` gives adverb-like particles the category `adverb`, degree suffix only);
  `_arrange_adpositions` leaves "as" where the planner put it (like "than"). Decoding: the degree reads back through
  `DEGREE_READING` ("as big as", "too big", "very big"), and the case-marked standard reads "than"/"as" instead of "in" when
  it follows a comparison. `inflection_gen.resolve_collisions` now takes the romanization so two suffixes spelled alike
  (`i` and `ɪ`) are treated as colliding (generation and evolution). 16 tests in `test_comparison_followups.py`.

- **Real inflection paradigms (grammar pass 22).** `core.grammar.Paradigm(name, pos, overrides)` and three
  `GrammarProfile` fields (`noun_paradigms`, `verb_paradigms`, `irregular_lexemes`, all default empty).
  `generation/paradigm_gen.py` (`roll_paradigms`, own `{seed}:paradigms` stream, drawn after
  `resolve_collisions`): the language's existing affixes are class 0; each further declension (1-3) or conjugation (1-2)
  gives about 55% of the changeable cells (noun `case_affixes`/`number_affixes`, verb `tense_affixes` and person
  `agreement_affixes`) a suffix of its own, drawn distinct -- as spelled -- from every suffix on the same kind of word;
  irregular lexemes (`IRREGULAR_NOUNS`/`IRREGULAR_VERBS`, 30% each) override one or two cells and avoid the classes' suffixes
  too. The rate follows the morphological type (fusional 0.85, isolating 0.10). `translator._paradigm_grammar(language, entry)`
  returns the grammar as that word sees it (an id-keyed cache; class by `noun_classes` index or `paradigm_gen.class_index`,
  a weighted hash of seed and gloss; suppletive forms use their base gloss), swapping the overridden affixes under the
  same labels, so `_apply_case`, `_apply_verb_inflection` and the decoders (`_decode_noun` via `_apply_case`; the verb
  search and non-finite forms per entry) need no other change. Pronouns, particles, numerals and names use the base
  grammar. `sound_change._evolve_grammar_affixes` evolves the overrides too. 14 tests in `test_paradigms.py`.

- **Paradigm follow-ups (grammar pass 23).** `Paradigm` gained `syncretisms` (`"<target>=<source>"` cells spelled alike on purpose,
  from `NOUN_/VERB_/ADJECTIVE_SYNCRETISMS`), `stem_change` (`umlaut`/`ablaut`/`gradation`) and `stem_cells` (the cells that trigger it);
  `GrammarProfile` gained `adjective_paradigms` and `stem_maps` (`paradigm_gen.build_stem_maps(inventory)`: umlaut fronts a back
  vowel, ablaut raises/lowers one height step, gradation voices a final voiceless consonant -- only pairs the inventory has, kept
  only for kinds in use). The overridable cells now include possession, aspect, mood and voice (and adjectives' degree and
  class-agreement suffixes). `translator._entry_paradigms` (class + irregular lexeme), `_paradigm_grammar`, `_stem_ipa(language,
  entry, cells)` (`paradigm_gen.change_stem` on the last mapped vowel, or the final consonant) and `_stem_prefixes` (the letters a
  changed stem can start with, so decoding's first-letter filter still finds it) are used by `_apply_case`,
  `_apply_verb_inflection`, `_apply_class_agreement` and the decoders; the pro-drop reading of an agreement suffix checks the
  verb's own conjugation (`_person_suffix_is_distinct(_paradigm_grammar(...))`). Sound change evolves `stem_maps` symbols too.
  10 tests in `test_paradigm_stems.py`.

- **Affix positions (grammar pass 24).** `InflectionAffix` gained `infix` and `infix_at` (`after_first_consonant`/`before_last_vowel`);
  `GrammarProfile.affix_positions` records the non-suffix fields. `generation/affix_position_gen.py` (`roll_and_apply`, own
  `{seed}:affix-positions` stream, run after the paradigms and followed by a `resolve_collisions` pass): 35% of languages are
  mixed; each of nine noun/verb fields then rolls suffix/prefix/circumfix/infix by morphological type, and every distinct suffix of a
  converted field (in the grammar and in paradigm overrides) maps to one fresh exponent -- so syncretisms and distinctness survive. A
  prefix is onset + vowel, a circumfix keeps the suffix and adds one, an infix is nucleus + coda. `inflection_gen.apply_affix` inserts
  the infix (`_insert_infix`) before attaching the prefix/suffix and re-deriving stress; `translator._compose_affixes` concatenates
  prefixes, infixes and suffixes of composed affixes. `resolve_collisions` now compares (prefix, infix, suffix) as spelled and redraws
  the exponent that is present. Decoding: `_decode_mode` picks how many stems an unknown token is tried against (`start`: the
  token starts like the stem; `contains`: a prefix is possible, so the stem's first letters appear anywhere; `all-after`/
  `all-before`/`all-both`: an infix can split the stem, so only its far end is checked; short stems always pass),
  `_may_spell` applies it, and the verb search skips any label combination whose affix symbols cannot be spelled with the token's
  letters (`_symbol_letters`: every letter a symbol can take in any context, so the test never rules out a real form).
  `_person_suffix_is_distinct` compares whole exponents. Sound change evolves prefixes, infixes and suffixes. 14 tests in
  `test_affix_positions.py`.

- **Morphophonology (grammar pass 25).** `GrammarProfile` gained `harmony` (`none`/`backness`/`height`/`rounding`) and
  `harmony_pairs`, `boundary_rule` (`none`/`elision`/`glide`) and `boundary_glide`, and `mutation_cells` and `mutation_pairs`.
  `generation/morphophonology_gen.py` (`roll_morphophonology`, own `{seed}:morphophonology` stream, run last): `harmony_pairs(inventory)`
  finds at least two vowel pairs (front/back of the same height, else vowels one height step apart, else unrounded/rounded);
  `mutation_pairs` maps a voiceless stop to its voiced twin and a voiced stop to the fricative of its place. `build_rules` makes a
  `Morphophonology` (vowel classes, boundary rule, glide) that `inflection_gen.apply_affix(..., morphophonology=...)` applies to the
  prefix, stem and suffix before restressing: an affix vowel in a pair takes the stem's class (last class vowel for a suffix, first for
  a prefix), then a vowel meeting a vowel at a boundary is elided or separated by the glide. `translator._stem_ipa` also mutates the
  initial consonant when the cell is in `mutation_cells`; `_stem_prefixes` includes the mutated start so decoding's first-letter filter
  still finds the stem, `_may_spell` always tries short stems under elision, and the verb search's affix-symbol test accepts a
  harmonic counterpart and ignores a prefix's last vowel under elision. Sound change evolves the pairs and the glide.
  20 tests in `test_morphophonology.py`.

- **Derivation and compounding (grammar pass 26).** `core.grammar.DerivationRule(name, pos_in, pos_out, affix)` and
  `GrammarProfile.derivations`, `compounding`, `compound_order` (`modifier_head`/`head_modifier`) and `compound_linker` (a linking vowel).
  `generation/derivation_gen.py` (`roll_derivation`, own `{seed}:derivation` stream, run after the morphophonology): each of the five `RULES`
  (agent, abstract, negative, diminutive, adjectival) is present with a probability by morphological type (agglutinative 0.85, isolating
  0.25) and gets a distinct exponent (a suffix, or mostly a prefix for the negative); compounding is likelier in isolating languages.
  `english_derivations(token)` is the closed English analyser (`-er`/`-or`, `-ness`, `un-`, `-let`/`-ling`, `-y`/`-ful`, with spelling
  repairs); `compound_splits(token, is_noun)` finds noun + noun splits of a solid or hyphenated word. `translator._lookup_or_coin` now tries
  `_derive_or_compound` before coining: it looks the base up in the language's own lexicon (right part of speech), applies the rule with
  `apply_affix` (so harmony and hiatus rules apply) or joins the two stems (`_compound_entry`: modifier + linker + head as one prefix +
  stem, restressed, no harmony across the join), and stores the result as a lexicon entry whose notes say how it was made
  (`derived: agent of teach`, `compound: moon + light`). A form that would spell like an existing word is coined instead. The planner
  prompt tells the LLM to keep derived and compound words whole. Sound change evolves the exponents and the linker. 21 tests in
  `test_derivation.py`.

- **Reduplication and root-and-pattern beyond the citation shape (grammar pass 27).** `core.grammar.PatternCell(cell, skeleton)` and
  `Reduplication(cell, kind)` with `GrammarProfile.pattern_cells` and `reduplications`, and `DerivationRule.pattern` (a template name).
  `root_pattern.roll_patterns` (own `{seed}:patterns` stream; empty unless `uses_root_and_pattern`) gives each verb tense and aspect, the
  plural and the comparative its own skeleton (distinct from the templates and each other); `reduplication_gen.roll_reduplication` (own
  `{seed}:reduplication` stream, before the derivation roll) chooses cells among `CANDIDATE_CELLS` by morphological type (isolating
  0.22 ... fusional 0.05) and a kind among `full`/`initial_cv`/`initial_syllable`/`final_syllable`; `reduplicate` copies the part
  (tones travel with their vowel, stress marks are dropped). `translator._stem_ipa(language, entry, cells)` now also rebuilds the stem
  from the word's root (`_entry_root`: the stored root if its consonants still occur in the word in order) when a cell has a pattern
  and the word's part of speech matches (`reduplication_gen.CELL_POS`), reduplicates it, then mutates it; the verb cells are now tense,
  aspect, mood and voice (the decoder's stem memo keys on all four) and an adjective's degree cell is passed too. `_stem_variants` adds
  each trigger cell's stem so the first-letter filter still finds patterned and reduplicated forms. In a templatic language a derivation
  with a `pattern` builds the word from the base's root and the template (`_pattern_derived_entry`, root shared, notes name the
  pattern) and falls back to the affix. Sound change evolves the skeleton vowels. 19 tests in `test_patterns_reduplication.py`.

- **Subordination follow-ups, second round (grammar pass 28).** `GrammarProfile` gained `reported_speech_backshift`,
  `clause_gapping`, `clause_right_node_raising` (`subordination_gen.roll_subordination_followups_2`, own
  `{seed}:subordination2` stream); `COMPLEMENT_CLASSES` grew from four to six (`manipulative`: make/let/force/cause/allow,
  `epistemic`: doubt/suspect/deny/assume); `subordination_gen.pp_relative_pied_pipes(relativization)` says whether a
  prepositional relative ("the house in which I live") fronts its preposition with the relative word (pronoun/correlative
  strategies) or leaves it stranded where the embedded clause's own verb governs it (every other strategy). `PlannedSlot`
  gained `oblique_prep`; `rel_function` gained `"oblique_pp"`. Renderer: `translator._extract_pied_piped_preposition` pulls
  a trailing `pos="preposition"` slot out of an `oblique_pp` clause's own plan in a pied-piping language and hands its gloss
  back for the (now list-valued, not single-tuple) `linker_words`, fronted with the relative pronoun; a stranding language
  leaves it where the planner put it, rendering in place. `_relative_run_start`/`_annotate_relative_heads`/`_arrange_relatives`
  were rewritten to move a *run* of consecutive relative clauses on the same noun together (stacked relatives), keeping their
  own order, instead of one clause at a time. `_governing_verb_tense` and `_reported_speech_tense` (mirroring
  `_subordinate_tense`) force a complement clause's tense to past after a past-tense speech verb in a backshifting language
  (the planner's own tense still wins); wired into `_render_plan`'s clause branch alongside the existing conditional forcing.
  Fixed in passing: the `copula` render branch never received `forced_verb_tense`/`forced_verb_mood`/`main_mood` at all (only
  the content-verb branch did), silently defeating conditional-tense/mood forcing and now backshift on any copula predicate;
  it now mirrors the content-verb branch. Coordination chains, gapping and right-node raising need no renderer changes at
  all -- a chain is just right-branching clause nesting (each level's own `_arrange_coordination` pass, already run once per
  nested `_render_plan` call, converbs that level's own last verb); gapping/right-node raising are just the planner omitting a
  verb or object slot from a clause, which already renders as nothing. The fake planner: `_fake_stacked_relative_plan` (two
  `who`/`which` subject relatives), the "PREP which" scan branch of the relative detector, `_fake_coordination_chain_plan`
  (the ordinary "X, Y, and Z" written style, without needing a conjunction before every conjunct), `_fake_gapping_plan`/
  `_fake_right_node_raising_plan` (the written comma convention for each construction, gated on the language's own flag --
  the full form is rebuilt when it lacks one), `_fake_gerund_subject_plan` ("seeing the river pleases me": a nominal clause as
  the subject), and raising verbs (seem/appear/happen/tend, added to the existing infinitive-verb set) and
  `_fake_passive_control_plan` ("he is believed to sleep": a passivized object-control verb, matrix voice `passive`, no object
  slot, the infinitive controlled by the matrix subject). 36 tests in `test_subordination_followups2.py`.

- **Agreement follow-ups, second round (grammar pass 29).** No new grammar fields -- three bug fixes and a
  data-breadth addition to pass 15's existing machinery. (1) The fake planner's `_fake_single_clause_plan` never had a
  general shape for a plain subject-plus-intransitive-verb sentence ("I sleep.", "The dogs sleep."): only a two-word
  copula-predicate-adjective branch, a three-word SVO branch and a handful of closed-list detectors (middle voice,
  antipassive, existentials) existed, so any other two-content-word sentence fell to the bare-noun fallback and got no
  verb slot at all -- no agreement, because there was no verb. A new `elif len(content_tokens) == 2:` branch fills this
  in (tense/aspect/mood, `verb_number_agreement`, politeness, evidentials, noun-class `subject_gloss`, negation), with a
  shared `is_plural_subject(tok)` closure the three-word branch was refactored to reuse. The branch initially had a real
  bug of its own: it swapped `subject_tok`/`verb_tok` based on the *target* language's `verb_first` word order, but the
  input tokens are always in fixed English surface order (subject before verb) regardless of the target word order --
  only the *output* slot order should follow it, as the three-word branch (which never reorders its input) already
  showed. Fixed by reading `subject_tok, verb_tok = content_tokens` unconditionally and keeping `verb_first` only for
  the trailing `slots = (verb_group + subject_np) if verb_first else (subject_np + verb_group)`. (2) A classifier
  "repeater" noun (`_classifier_slot`, the noun standing in as its own classifier) rendered through a bare
  `_lookup_or_coin` lookup, never through `_apply_case`, so in a class-marked language it never carried the class
  marker its head-noun copy carried a few tokens later -- the two surface forms differed, and `_drop_repeaters`
  (decode-side de-duplication) additionally identified a noun token via a raw `lexicon.by_form` lookup, which only
  matches a bare citation form and so silently failed on *either* copy once either one carried a class marker. Fixed
  by rendering the repeater through `_apply_case(language, entry, None, None)` (class marker only, matching the head
  noun's own marker) and rewriting `_drop_repeaters` to identify a noun by its decoded lexical entry (`_decode_noun`,
  the same generate-and-compare decoder used everywhere else) rather than by literal spelling, so identity survives
  whatever case/number marking the head noun carries and the repeater does not. (3) `noun_class_gen._SEMANTIC_FIELDS`
  grew three new fields (`animal`, `material`, `person`) and picked up stragglers in existing ones, raising its
  coverage of the lexicon's noun glosses from 72% to over 95% (most of the `person` field's words are already handled
  by `_MASCULINE`/`_FEMININE`/`_HUMAN` before `semantic_field` is even consulted, so its practical effect is limited to
  a language with a non-gender, non-animacy class system using `semantic` assignment). The stale-doc item "prefix-marked
  languages have no stem-prefix prefiltering when decoding a noun" was checked and found already resolved as a side
  effect of pass 24's general `_stem_prefixes`/`_decode_mode`/`_may_spell` infrastructure (`class_marker_affixes` is
  one of `inflection_gen._NOUN_SUFFIX_FIELDS`); "the planner still supplies each noun's own case/number" is a design
  choice, not a gap, and stays as-is. 11 tests in `test_agreement_followups2.py`.

- **Aspect/mood follow-ups, second round (grammar pass 30).** Everything from the pass-16 "still missing"
  list except evidential-tense interaction (left as a documented gap; evidential marking itself was explicitly
  out of scope for this pass).

  (1) **Agreeing auxiliaries.** `GrammarProfile` gained `auxiliary_agreement: bool` (~35%, its own
  `{seed}:auxiliary-agreement` stream -- deliberately *not* a further draw on `roll_aspect_followups`'s own
  `rng`, which generator.py keeps reusing afterward for the evidential/negative/prohibitive suffixes; an
  earlier version drew it there and silently shifted those suffixes for every seed). A periphrastic auxiliary
  word (`_auxiliary_entries`, `aux-<label>`) was always an invariant particle; in a language with this trait it
  now agrees with the subject exactly like the main verb does, reusing the *same* `agreement_affixes`/
  `verb_number_affixes`/`verb_polite_affixes` paradigm (`_apply_auxiliary_agreement`, via `_combined_tense_
  agreement_affix` with tense/aspect/mood/voice/object/evidential all `None` so only agreement/number/polite
  contribute -- no new affix tables needed). `_auxiliary_entries` now returns `(entry, romanization, ipa)`
  triples instead of bare entries; both call sites (content-verb and copula) pass the slot's own
  `agreement_label`/`subject_number`/`polite`. Decoding: `_decode_auxiliary_entry` tries the bare citation form
  first (the common, fast case), and only searches every agreement x number x polite combination when
  `auxiliary_agreement` is set, mirroring `_decode_noun`'s generate-and-compare against `_apply_case`;
  `_split_auxiliary_tokens` uses it instead of an exact `lexicon.by_form` match, which would otherwise silently
  fail to recognize an inflected auxiliary (the same class of bug pass 29's classifier-repeater fix hit).

  (2) **Negative non-finite forms.** A non-finite verb form (infinitive, nominalized...) could never take the
  ordinary negative suffix -- `_finite_verb_indices` (the negation-absorption target list) explicitly excluded
  any slot with a `verb_form`, so a negation slot near a non-finite-only clause (a bare infinitival complement
  has no finite verb in its own nested `_render_plan` scope at all) fell back to the bare "not" particle even
  in a suffix-negating language. Split into `_finite_verb_indices` (finite only, still used for the
  imperative/prohibitive target, which must remain finite) and a new `_negatable_verb_indices` (finite or
  non-finite, used for the ordinary affix path); `_non_finite_affix`/`_verb_form_salt` gained a `negative`
  parameter that composes in `verb_negative_affixes` alongside the form's own suffix; `_apply_verb_inflection`'s
  non-finite branch (which had a `negative` parameter it silently ignored) now uses it. Decoding:
  `_decode_verb_full`'s non-finite `form_candidates` search gained a `negative` axis; the English reading
  (`tense_label in subordination_gen.VERB_FORM_LABELS`) gained a negated reading per verb form ("to not go",
  "not going"...) and a "negative" note.

  (3) **Negative existentials.** `GrammarProfile` gained `negative_existential: bool` (~35%, the existing
  `{seed}:existence` stream -- safe to extend since nothing downstream reuses that rng afterward). In such a
  language, "there is no X" (and, in a `dative_be` language, "A has no B") now plans as one dedicated
  `{"kind": "content", "gloss": "not-exist", "pos": "preposition"}` slot (an invariant particle, `pos`
  "preposition" only because that's the JSON-string key that maps to `PartOfSpeech.PARTICLE` -- "particle"
  itself isn't a valid `PlannedSlot.pos` value) in place of the copula/verb-exist slot *and* the negation slot,
  in `_fake_existence_slots`'s `be_slots` closure and the planner's own system-prompt text
  (`negative_existential_desc`). Decoding special-cases the gloss directly (`"does not exist"`) in
  `translate_to_english`'s per-token loop, alongside the other special-gloss checks (relative pronoun,
  complementizer, suppletive form). In passing, fixed a real, independent bug in the `dative_be` possession
  path: `_fake_existence_slots` located the possessed noun as `tokens[have_index + 1]` unconditionally, so "I
  have no dog" read the negation word "no" itself as the possessed noun and silently dropped "dog"; now skips
  over "no"/"not" to find the real possessed token.

  (4) **Suffix concatenation collisions.** `inflection_gen.resolve_collisions` gained a second, narrower pass,
  `_resolve_concatenation_collisions`, run to a bounded fixed point (5 iterations) per word-kind group: for
  every pair of suffix-only affixes from *different* fields (the only pairing that can actually co-occur on
  one word), if their concatenation spells like some *other*, single affix in the group, that third affix is
  redrawn (mirroring the existing single-affix pass's own `redraw`/`key` helpers -- an early version passed
  `redraw` a `set` of bare spelled strings instead of its expected `key()` 3-tuples, so the membership check
  never matched and no real redraw ever happened; fixed by building `used` from `key()` throughout). Measured
  before/after across 60 seeds: 59 residual collisions (11 of 60 seeds) down to 26 (9 of 60) -- a real
  reduction, not a full fix, since a tiny phoneme inventory can still run out of free shapes within the bound.
  `resolve_collisions` gained a `check_concatenations: bool = True` parameter: `generator.py`'s *second* call
  (after paradigms and affix positions) passes `False`, because a redraw there is never revalidated against
  paradigm overrides already built from the *first* call's output (`paradigm_gen`'s own overrides only get
  reshaped by `affix_position_gen` when their field's *position* changes, never re-checked against a later
  suffix-content redraw) -- running the new pass there was observed to make an already-built override collide
  with a freshly-redrawn base affix. A companion ordering fix was tried and reverted: moving `paradigm_gen.
  roll_paradigms` to run strictly last (after affix positions) looked more "correct" from the collision
  pass's point of view, but `affix_position_gen`'s own docstring is explicit that it must run *after*
  paradigms specifically to reshape their overrides to match a repositioned field -- reordering silently
  stopped paradigms from ever varying a field that had already been moved to prefix position (`_override_
  labels`'s suffix-only filter then never matches). Kept the original order; `check_concatenations=False` on
  the second call is the actual fix.

  (5) **Affix evolution: grammaticalization and fusion** (`sound_change.py`, a new `_grammaticalize_and_fuse`,
  called in `evolve_language` right after `_evolve_grammar_affixes`, own `{seed}:grammaticalization` stream).
  Two more diachronic changes on top of plain sound change, both more likely at greater time depth (rates
  capped at 0.5/0.4): a periphrastic auxiliary word can grammaticalize into a bound tense/aspect/mood suffix
  (built from the auxiliary's own, already sound-changed, IPA -- tokenized the same way `_evolve_grammar_
  affixes` already tokenizes evolved affixes) once that auxiliary has actually been coined by an earlier
  translation (the lexicon entry is created lazily on first use, so a never-used auxiliary has no word yet to
  grammaticalize, at any time depth -- verified both ways); and `suppletive_past` can grow over time from the
  same fixed `voice_np_gen.IRREGULAR_PASTS` candidate list generation itself draws from (not a novel erosion
  mechanic -- `voice_np_gen.suppletive_split`'s own gate, used at decode and prompt-generation time, is
  hard-limited to that fixed list, so a genuinely arbitrary verb can't be made to fuse without touching that
  gate too, which was judged out of scope here). Fixed a real bug found while building the CLI-verified
  example: a label being grammaticalized could already have a dead, never-rendered affix entry for that same
  label (defined before it became periphrastic) sitting in `tense_affixes`/etc; the first version *appended*
  the new suffix affix alongside it, leaving two entries with the same label (whichever came first in the list
  would then win at both encode and decode, not necessarily the new one) -- fixed by filtering out any
  existing entry with that label before appending.

  22 tests in `test_aspect_followups2.py`, 6 more in `test_sound_change.py`.

- **Voice follow-ups, second round (grammar pass 31).** No new grammar fields -- three fixes to
  pass 17's middle/applicative/impersonal voices, all in `fake_client.py`/`translator.py`.

  (1) **Impersonal has no subject at all.** Pass 17 only suppressed subject *agreement*
  (`_verb_agreement`'s existing `voice == "impersonal"` check); nothing ever stopped a subject
  noun/pronoun slot next to an impersonal verb from rendering like any other subject, and the fake
  planner never produced impersonal voice at all (confirmed by grep: zero references to
  `"impersonal"` anywhere in `fake_client.py` before this pass). Fixed on both sides: a new
  `_dropped_impersonal_subjects` (mirroring `_dropped_subject_pronouns`'s own shape) finds, for
  every finite verb slot with `voice == "impersonal"`, the adjacent noun/pronoun slot (either side)
  and drops it, folded into `_render_plan`'s existing `dropped_pronouns` set -- a genuine safety net
  for a hand-built plan or a real LLM's own plan, not just the fake planner's. `_fake_voice_slots`
  gained an impersonal branch in its 2-token shape, triggered by the subject token "someone" (not
  English impersonal "one" -- confirmed by tracing that `_fake_group_noun_phrases` always swallows
  "one <word>" into a numeral-quantified noun-phrase placeholder before voice detection ever sees the
  tokens, regardless of whether the second word is a noun or a verb -- "one dances" plans as a single
  bogus noun slot, not two tokens, so "one" can never reach this branch); the branch builds the verb
  slot with no subject token at all (`agreement` stays "default", matching pass 17's own agreement
  suppression) and returns just the verb, omitting the subject noun-phrase entirely.

  (2) **Applicative promotion triggers real object agreement.** The promoted beneficiary
  ("I cook for him" -> the applicative verb takes "him" as its object) never set `object_gloss` on the
  verb slot, even in a language with `object_agreement` -- the applicative branch's own `verb_slot(...)`
  helper (shared with middle/impersonal) only ever took a subject token, never an object one, unlike the
  ordinary 3-word transitive branch a few hundred lines away which already does exactly this
  (`verb_slot["object_gloss"] = pronoun_gloss(obj_tok) if ... else base_of(obj_tok)`). Threaded
  `object_agreement`/`pronoun_gloss` into `_fake_voice_slots`'s signature (both already existed as
  locals in the caller) and set `object_gloss` on the applicative verb the same way, when the language
  has object agreement -- a real valency-changing effect (the promoted argument now behaves exactly
  like an ordinary object for agreement purposes), not just a bare suffix on the verb.

  This surfaced a real, independent decode bug: `_decode_verb_full`'s staged search (six -- nine with
  evidential/negative "extras" -- increasingly expensive stages, each varying a different subset of
  tense/aspect/mood/object/voice, cheapest first) had **no stage that ever varied voice and object
  agreement together** -- every stage fixed one to `[None]` whenever the other varied. This had never
  mattered before: reflexive/reciprocal (the only existing voices that could combine with an object)
  deliberately *never* set `object_gloss` when using the affix strategy (`fake_client.py`: `if
  object_agreement and (...): if reflexive_voice is None: verb_slot["object_gloss"] = ...` --
  reflexive/reciprocal voice already covers the missing object, so the two conditions were mutually
  exclusive by construction). Applicative is different: the beneficiary is a real, distinct object, so
  it genuinely needs both a voice suffix *and* object agreement on the same word -- the first
  combination this decode search ever had to find. Fixed by adding two more stages, `object x voice`
  (cheap, tense/aspect/mood fixed) and `aspect x mood x object x voice` (the full combination, for a
  verb that also carries aspect/mood), in the existing cost-ordered position.

  (3) **A bit wider verb-list detection.** `_FAKE_ANTIPASSIVE_VERBS`/`_FAKE_MIDDLE_VERBS` (the closed
  lists gating the 2-token bare-clause voice shapes) grew from ~19/~13 entries to ~33/~28, adding more
  common activity verbs (antipassive: bake, wash, sew, clean, build, paint, weave) and
  change-of-state verbs (middle: boil, freeze, crack, tear, bend, split, sink) -- the same kind of
  bounded, low-risk data-breadth expansion as pass 29's semantic-field growth. The applicative and
  impersonal *structural* shapes (exactly "S V for O", "someone V") stay fixed, as does the passive/
  causative detection -- widening those further was judged out of scope for this pass.

  Decode-speed indexing (a real, separately-tracked "S-M" item in this same DEFERRED.md bullet since
  pass 20) and expanding reciprocal marking beyond "word"/"affix"/"none" were both left untouched --
  neither is really a *voice* gap, and both are larger, more speculative undertakings than this
  pass's three concrete fixes. 11 tests in `test_voice_followups2.py`.

- **Comparison follow-ups, second round (grammar pass 32).** `comparison_gen.DEGREE_LABELS` grew from
  5 to 8: `comparative_negative`/`superlative_negative` ("less big [than Y]"/"least big") and
  `sufficiency` ("big enough"). `DEGREE_WORDS`/`DEGREE_READING` cover all 8 generically, so the
  existing shared `degree_affixes` pool, `_apply_class_agreement` and `_decode_adjective_full` (all
  already label-agnostic since pass 21) needed no changes at all for the new labels' own marking. Three
  genuinely new pieces:

  (1) **Negative degree.** Deliberately has no marking-strategy field of its own --
  `comparative_negative`/`superlative_negative` reuse `comparative_marking`/`superlative_marking`
  directly (a comparative suffix marks "degree exists", not "more" specifically, and English itself
  never has a synthetic "-less" suffix, always the separate word "less"), so `generator.py`'s existing
  `cmp_labels` tuple just adds two more entries gated on those same fields, with their own freshly
  drawn suffix in the shared pool when applicable. `comparison_gen.roll_followups` needed no new rng
  draw for this at all.

  (2) **Sufficiency.** Gained its own `sufficiency_marking` field (own coin flip, same shape as
  equative/excessive/elative) since, unlike the negative degree, it has no natural tie to an existing
  marking choice. The one real wrinkle: "big enough" is the sole degree whose English word *follows*
  the adjective rather than precedes it -- `sentence_planner.py`'s `_degree_desc` gained an `after`
  parameter for the prompt text, and `fake_client.py`'s word-marking branch now orders
  `[adjective, word]` instead of `[word, adjective]` specifically for `degree == "sufficiency"`.

  (3) **An equative's own standard case**, rolled independently of the comparative's
  (`equative_standard_case`, its own rng draws appended *after* every existing draw in
  `roll_followups` so no old seed's comparative/equative/excessive/elative/adverb_degree shifts).
  `_equative_now_case` (mirrors `grammar_now_case`) falls back to `comparative_case` when
  `equative_standard_case` is empty -- the field's own default, so an older saved language keeps
  exactly its old shared behavior. `_fake_degree_slots` computes one `effective_case` per degree
  (equative's own-or-fallback; every other degree's own `comparative_case if strategy == "case"`,
  unchanged) instead of the old single shared check.

  **Two real, independent bugs found and fixed along the way, not part of the plan:** (a)
  `_fake_group_noun_phrases`'s attributive-adjective grouping excludes a fixed list of words
  (`"than"`, `"and"`, `"as"`, `"too"`, `"very"`) from being treated as the *noun* of a phrase headed by
  the adjective before them -- "enough"/"less"/"least" were missing from that list, so "big enough"
  silently planned as one bogus noun phrase (adjective "big" modifying a fake noun "enough") instead of
  the intended construction; same root cause, same fix shape, as pass 31's "someone"/numeral-grouping
  bug. (b) the decode-side standard-word heuristic (choosing "as"/"than" instead of a literal case
  preposition like "in" when re-reading a comparison's case-marked standard) only ever matched the
  *combined* string `"as big as"` in the per-token `plain` list -- which only exists when the equative
  is *affix*-marked (`DEGREE_READING["equative"].format(gloss)` produces it as one entry); a
  *word*-marked equative's "as" is its own separate token, which the check never matched, so a
  word-marked equative with a case-marked standard always read back with the literal case preposition
  ("as big **in** cat") instead of "as" -- pre-existing, just never exercised before this pass gave a
  word-marked equative a case-marked standard independent of the comparative's own strategy. Fixed by
  also matching a bare `"as"` token.

  Also widened `_FAKE_KNOWN_ADJECTIVES` from ~87 to ~125 words (the same bounded, low-risk data-breadth
  expansion as pass 29's semantic fields and pass 31's verb lists). "Not as big as" beyond plain
  negation, "so big that..." result clauses (a genuinely new subordinate-clause construction -- the
  "that" linker would collide with the fake planner's existing complementizer and
  correlative-relative uses of that same surface word) and multiplicative comparison ("three times as
  big") were all investigated and left as documented limitations, not implemented -- each is either a
  design choice already accepted in the original pass-21 scope, or large/speculative enough to warrant
  its own separate pass. 14 tests in `test_comparison_followups2.py`.

- **Topic/focus and information structure (grammar pass 33, a Discourse follow-up).** The first of
  `docs/DEFERRED.md`'s five Discourse items ("as for the cat, it sleeps" -- a sentence's topic marked
  separately from its ordinary subject, Japanese `-wa`/Korean `-neun`). Had zero scaffolding before
  this pass. Built entirely from existing precedent rather than new machinery:

  - `GrammarProfile.topic_particle: str = ""` -- the invented particle's own IPA, empty meaning the
    topic is fronted but left unmarked (realistic: Mandarin, for instance, has no topic particle at
    all, relying on position alone). Mirrors `question_particle`/`possessive_particle` exactly, same
    file -- a particle's surface form lives directly on the field, not a separate bool + form pair.
    Rolled in `generator.py` right next to those two particles' own rolls (~40% chance, own rng
    stream, built and collision-checked with the same `inflection_gen.generate_question_particle`
    call already reused for the possessive particle).
  - The topicalized sentence itself reuses the existing nested-clause-with-`role` mechanism already
    used for the correlative "the-more" adverbial and for relativization (`sentence_planner.
    CLAUSE_ROLES` gains `"topic"`): the topic noun phrase is a `role="topic"` clause slot (no verb)
    placed first. This is why no new per-slot boolean or manual token-span tracking was needed --
    `_render_plan` already knows how to splice a nested clause's own rendered tokens into the parent
    stream for every other clause role.
  - `fake_client._fake_topic_plan`, hooked into `_fake_plan_dict` the same way and at the same
    priority as the existing `the_more` regex check, recognizes "as for X, Y" on the *raw* prompt text
    (the only place a sentence-initial comma is visible at all -- `_fake_tokenize` drops all
    punctuation). Deliberately builds the topic noun from the bare top-level helpers
    (`_fake_tokenize`, `_fake_singular`, `_FAKE_ARTICLES`) rather than the richer `noun_phrase`/
    `build_np` closures (local to `_fake_single_clause_plan`, not reusable standalone) -- the concrete
    shape of this pass's "bare topic noun only" scope limit.
  - `translator._arrange_topic` fronts any `role="topic"` clause slot (a no-op for the fake planner,
    which already puts it there; a safety net for a real LLM that might not), and the clause-rendering
    branch of `_render_plan` appends the particle (when set) directly after that nested clause's own
    rendered tokens -- the same place a relative/adverbial clause's own linker word gets appended.
    `translator._dropped_topic_resumptive_pronouns` drops the main clause's subject pronoun
    unconditionally when a topic is present, mirroring `_dropped_impersonal_subjects`'s "no agreement
    check needed" reasoning exactly.
  - Decode mirrors the `question_particle` detection exactly (a `topic_form` computed from the
    grammar field, a same-shaped swallow-check in the per-token loop). One genuine wrinkle, found via
    manual round-trip testing rather than anticipated in the plan: an *uncased* topic noun (no case
    suffix at all -- the common case for a bare subject in many languages) matches
    `language.lexicon.by_form` directly in `translate_to_english`'s *earlier*, generic
    direct-lexicon-entry branch, never reaching `_decode_noun` at all -- so the topic tagging needed
    adding in *two* places, not one. Factored into a single `is_topic_marked(index)` closure used by
    both. With no particle, decode has no signal to recover "this was a topic" from at all (documented
    limitation, the same tradeoff already accepted elsewhere for an unmarked/fronting-only strategy).
  - Explicitly deferred, matching the DEFERRED.md item's own remaining scope: object/oblique-coreferent
    topics ("as for the cat, I saw it" -- only subject-coreferent topics are supported); focus/cleft
    constructions ("it is X that..."); a modified topic noun phrase (adjectives, numerals, possessors);
    cross-sentence (discourse-level) topic continuity -- each sentence is still planned and translated
    independently. 10 tests in `test_topic.py`.

- **Politeness/honorific registers, second round (grammar pass 34, a Discourse follow-up).** The
  second Discourse item. Before this pass, politeness was addressee-only: `honorific_you` (a polite
  "you" pronoun, triggered by a vocative cue like "sir"/"madam") and `verb_politeness` (a verb suffix
  when the subject is "you-polite"). Real honorific systems (Japanese, Korean) also mark deference
  toward whoever a sentence's *subject* is, independent of who's being addressed. This pass adds that,
  deliberately reusing the *existing* `polite` verb affix rather than inventing a second one -- the
  same kind of simplification as pass 32's `comparative_negative`/`superlative_negative` reusing their
  positive counterpart's own marking choice:

  - `GrammarProfile.referent_honorifics: bool` -- rolled in `pronoun_gen.roll_pronoun_system` right
    alongside `honorific_you` (its own independent draw, same rate formula, added *after* every
    existing draw in that function so no old seed's sequence shifts) -- a language can have either,
    both, or neither honorific system.
  - `verb_politeness`'s own gate in `generator.py` widened from `honorific_you and
    verb_politeness_wish` to `(honorific_you or referent_honorifics) and verb_politeness_wish` -- the
    affix gets invented whenever the language wants one *and* has at least one honorific system to
    apply it to.
  - `fake_client.py` gains a closed title list, `_FAKE_REFERENT_TITLES` ("professor", "doctor",
    "teacher", "elder", "king", "queen", "president", "master") -- deliberately titles, not proper
    names: a bare name carries no inferable social status, a title does. Checked via the
    `base_of(subject_tok)` closure already in scope at both of `_fake_single_clause_plan`'s existing
    "polite" trigger sites (the plain intransitive and plain transitive sentence builders), widened
    with an `or` alongside the pre-existing addressee check -- the same two generic shapes the
    addressee trigger itself was already limited to, not a new limitation this pass introduces.
  - **Render and decode needed zero changes.** `translator.py` already resolves `slot.polite`
    generically regardless of why it was set, and already annotates an unknown verb's recognized
    polite affix generically (`notes += ["polite"] if polite_label else []`) -- this pass's entire
    point was landing on that existing, affix-reuse path.
  - **Investigated and explicitly deferred: distinct honorific vocabulary** (Japanese
    謙譲語/尊敬語-style suppletive verb stems, e.g. plain "eat" vs. an honorific word). The existing
    suppletion machinery (`voice_np_gen.suppletive_split`/`suppletive_reading`, used for irregular past
    tense and degree) is reusable *in shape* -- same hyphenated-gloss trick, same "independently coined
    lexicon entry" trick -- but needs a new "kind" added to a closed tuple baked into that machinery, a
    new hand-written English word-pair dict, a new `GrammarProfile` field, and, unlike tense/degree, a
    register/addressee-status signal that doesn't exist anywhere yet in `PlannedSlot`/`GrammarProfile`.
    A genuinely bigger lift than the affix-reuse approach taken here, left as its own future pass. An
    object/addressee-humbling (kenjougo-style) counterpart is likewise deferred -- this pass is
    subject-referent only. 9 tests in `test_honorifics.py`.

- **Reported speech, second round (grammar pass 35, a Discourse follow-up).** The third Discourse
  item. Before this pass, reported speech had only `reported_speech_backshift` (a past-tense speech
  verb's complement clause backshifts its own tense). Missing per DEFERRED.md: "no quotative
  particles/evidentials specific to reported speech." Investigated and rejected: reusing the existing
  evidentiality system's `"reported"` label -- it marks the *speaker's own* epistemic source for a
  clause's own verb ("how do I know this"), a different grammatical function from "this clause is
  someone else's claim, embedded under a speech verb." Built instead as an independent mechanism,
  following the `topic_particle` pattern from pass 33 almost exactly:

  - `GrammarProfile.quotative_particle: str` -- rolled in `generator.py` right alongside
    `question_particle`/`possessive_particle`/`topic_particle` (same ~40% weight class, same
    `inflection_gen.generate_question_particle` call, collision-checked against all three).
  - **No new plan shape, no fake-planner changes, no real-LLM prompt changes at all.** A speech-verb
    complement clause is already an ordinary `role="complement"` clause slot -- the same structure
    used for desire/perception/factive/etc. complements -- and `subordination_gen.complement_class
    (governor)` is already computed purely from the plan's own governing-verb lemma, at render/decode
    time only (exactly how `complementizer_by_verb` and `reported_speech_backshift` themselves already
    work, needing no fake-planner wiring either). The entire footprint is render + decode:
    - Render (`_render_plan`'s clause branch, the same spot `topic_particle` inserts at): when
      `slot.role == "complement"` and `complement_class(governor) == "speech"` and
      `grammar.quotative_particle`, the particle is appended after the nested clause's own rendered
      tokens -- additive alongside whatever "that"/complementizer-by-verb marking already exists, not
      a replacement.
    - Decode: a swallow-check recognizes the particle's surface form anywhere in the token stream
      (silent in `plain`, matching the `question_particle` precedent -- no natural single English
      word to insert); for `annotated`, it retags the *last* word decoded so far with `(quoted
      speech)`, the mirror image of `topic_particle`'s own forward lookahead (this particle trails its
      clause instead of leading it).
  - **Bundled bug fix**: `_reported_speech_tense` previously backshifted *any* past-tense verb's
    complement ("I knew that she was late" is not reported speech), looser than its own docstring
    claimed. Tightened to also require `complement_class(governor) == "speech"`, reusing the same
    lookup the new feature needed anyway. One pre-existing test asserted the old, looser behavior
    (`test_subordination_followups2.py::test_backshift_forces_past_after_a_past_speech_verb`, which
    called the function with no governing verb at all) -- updated to pass a real speech-verb lemma,
    plus a new sibling test asserting a factive verb's complement does *not* backshift.
  - Explicitly deferred: direct quotation ("He said: 'I am sick.'" -- unshifted first person, literal
    wording) -- the complement-clause mechanism only models *indirect* speech, a genuinely different,
    larger construction; any interaction with the evidentiality system is left orthogonal, per the
    investigation's own verdict; deep nesting ("she said that he said that...") isn't specially tested
    though nothing should prevent it, since clauses already nest arbitrarily. 7 tests in
    `test_reported_speech.py` (plus one new sibling test in
    `test_subordination_followups2.py` for the bundled bug fix).

- **Wiring existing traits (grammar pass 36).** `docs/DEFERRED.md`'s own "Wiring existing traits"
  bullet named six `TraitProfile` fields "extracted and stored but consumed by nothing." Investigated
  all six: three had an existing flat roll or channel to bias, cheaply, with the same
  `base + weight * max(0, trait)` shape `social_hierarchy` -> `honorific_you` already uses; three had
  no mechanism anywhere to hook into, needing a real new feature first, not a formula -- those three
  stay deferred, with the reasoning recorded directly in DEFERRED.md rather than re-attempted here.

  - `evidentiality_culture` biases `inflection_gen.roll_aspect_followups`'s `EVIDENTIAL_SYSTEMS` pick:
    the "no evidentiality" weight (flat `0.55`) shrinks by `_EVIDENTIALITY_CULTURE_WEIGHT *
    max(0, trait)` (floored at `0.1`), and the freed probability mass is redistributed proportionally
    across the three richer systems -- their own relative sizes to each other stay fixed, only the
    overall "does this culture mark it at all" balance shifts.
  - `spatial_reference` biases `np_followups_gen.roll_round_three`'s `SPATIAL_CASES` roll, but
    precisely: of the five optional spatial-case candidates (locative, instrumental, ablative,
    allative, comitative), only the three that are actually about *spatial* reference (locative,
    ablative, allative) get the raised rate (`0.3 + 0.5 * max(0, trait)`, capped at `0.9`);
    instrumental and comitative (means and accompaniment, not location) stay at the original flat
    `0.3` -- a deliberately narrow, not blanket, bias.
  - `salient_vocabulary_domains` was confusingly similar to, but entirely separate from, the already-
    consumed `salient_context` (free-text word-coining flavor). Rather than giving it its own parallel
    plumbing, a new `core.traits.coining_context(traits)` joins the two ("... (seafaring, herding
    culture)"), and the four existing call sites that read `salient_context` directly (two in
    `generator.py`, two in `translation/expansion.py`) now call this instead -- backward compatible by
    construction, since an older saved language's empty `salient_vocabulary_domains` makes
    `coining_context` return exactly its old `salient_context` string.
  - Both roll functions gained an optional trait parameter (`evidentiality_culture`/
    `spatial_reference`, both defaulting to `0.0`, today's unchanged behavior) rather than a new rng
    draw -- these are reweightings of *existing* draws, not new ones, so no backward-compatibility
    concern about an old seed's draw sequence shifting arises here at all, unlike most of this
    session's other passes.
  - `ritual_register`/`taboo_register`/`terrain_communication_distance` were investigated and
    confirmed to have no analogous mechanism anywhere (no register/formal-speech system, no
    euphemism/avoidance-vocabulary system, no long-range-communication proxy) -- each would need a
    real new feature built before it could be "wired," a materially bigger undertaking than this
    pass's three formula tweaks, left deferred with that reasoning recorded.
  - Also out of scope, confirmed unrelated to these six traits: `word_order` has no graded-trait
    influence at all today (only matched-reference-profile bias); `morphological_type` already has
    trait bias but no matched-reference-profile analogue, since no `real_morphological_type` field
    exists on `ReferenceLanguageProfile` -- adding one needs new data curated across ~50 profiles, not
    a formula. 10 tests in `test_trait_wiring.py`.

- **Strictness does not reach evolution (grammar passes 38-39).** `docs/DEFERRED.md`'s
  "Language evolution" item. The design process here is worth recording, since it changed twice from
  the first instinct:

  1. First instinct: a strict language's evolved inventory can pick up a phoneme the source language
     never has (traced concretely: `_apply_ejective_drift` can turn `/k/` into `/kʼ/` regardless of
     lineage; real Dutch never has ejectives) -- patch individual out-of-lineage symbols after sound
     change, substituting the nearest in-lineage phoneme via `phoneme_fit`'s existing nearest-neighbor
     machinery.
  2. **Corrected**: that's unrealistic. Real languages gain new sounds constantly (contact, conditioned
     splits, borrowing) -- a fix that made a strict lineage flatly *incapable* of ever gaining a sound,
     even at strictness 1.0, would be wrong. The actual bug is narrower: today's mechanism is
     completely lineage-blind, not that evolution changes phonemes at all.
  3. **Corrected again**: patching individual symbols after the fact treats the symptom. The right
     shape is the one fresh generation already uses: build the phonology *itself* (inventory,
     per-position frequency/"likeliness", syllable structure, onset/coda rules, clusters) as one
     evolving object -- the same rich spec `generate_phonology` already produces -- and have words draw
     from *that*, instead of deriving the spec backward from whatever survived in already-mutated
     words. Strictness then falls out naturally (reusing `_reference_biased_rate`'s own formula to
     *damp*, never *forbid*, a lineage-foreign gain) rather than being bolted on as a post-hoc patch.

  Investigated how much of stage 3's target already exists: per-phoneme frequency is a real, already-
  stored field (`SyllableStructure.onset_symbol_multipliers`/`nucleus_symbol_multipliers`/
  `coda_symbol_multipliers`, built by `phonology_gen._resolve_position_multipliers` at fresh
  generation) -- not something to invent, something evolution was *discarding*. That discarding turned
  out to be a real, separate, more basic bug worth fixing on its own first:

  - **Stage 1 (landed this pass)**: `_recompute_syllable_structure` (`sound_change.py`) rebuilt its
    returned `SyllableStructure` from scratch after every evolution, and the rebuild simply never
    mentioned most of the rich fields fresh generation can populate -- `allowed_onset_quads`/
    `allowed_coda_quads`, `excluded_initial_onset_consonants`, `excluded_onset_consonants`, all four
    onset-nucleus/nucleus-coda pair-restriction fields, both coda-onset-boundary pair fields, and all
    three frequency-multiplier fields. Pydantic defaults silently filled each one back to empty/`None`
    -- not frozen, *dropped*, independent of strictness, on every single evolution. Fixed by carrying
    each forward from the base structure, filtered to the post-evolution inventory the same way the
    fields that already survived (`allowed_onset_triples` etc.) already were -- two small new helpers,
    `_filter_pairs` (handles the `None`-means-unrestricted convention) and `_filter_multipliers`, reused
    across all of them. Needed a new `vowels` parameter threaded through (`_inventory_and_structure`
    already computes vowels, just never passed them on) since the nucleus-side pair/multiplier fields
    need the vowel set, not just the consonant set, to filter correctly. Confirmed concretely via a
    strict Dutch-lineage seed whose `onset_symbol_multipliers` (18 entries) and `excluded_onset_
    consonants` (`/ŋ/`) both silently went to empty after one `evolve_language` call, pre-fix.
  - **Two further, genuine inconsistencies surfaced once those fields actually started surviving**
    (both only ever possible once `excluded_onset_consonants`/`allowed_onset_nucleus_pairs` are
    non-empty post-evolution, which pre-fix they never were -- so both are pre-existing gaps the fix
    exposed, not regressions it caused):
    1. `word_builder._choose_nucleus` already has a documented, deliberate fallback for when
       `allowed_onset_nucleus_pairs` has zero entries for a given onset (falls back to the full,
       unrestricted vowel pool rather than crashing) -- so a brand-new consonant (introduced by sound
       change, e.g. ejective drift's own `/pʼ/`) that the *inherited* whitelist never mentions at all
       could get *picked* as a single onset by `_build_onset`, then paired with a vowel via that
       fallback, producing a combination `SyllableStructure.is_valid_syllable` correctly rejects as
       invalid -- confirmed `is_valid_syllable`'s own strict "unmentioned means illegal" semantics are
       the deliberate, tested contract (an existing unit test asserts exactly that), so the first fix
       attempt here (loosening that check) was wrong and reverted. The real fix belongs one step
       earlier: `_build_onset`'s own single-consonant candidate list now excludes a symbol with zero
       entries in the whitelist (same `or candidates` defensive fallback its neighboring
       `excluded_onset_consonants` filter already uses), so a legal onset is chosen in the first place
       whenever one exists, instead of validating an illegal choice after the fact.
    2. `allowed_onset_clusters` is regenerated fresh every evolution from `sonority.legal_onset_pairs`,
       which -- unlike `phonology_gen.generate_phonology`'s own onset-cluster setup -- never filtered
       its candidate pairs against `excluded_onset_consonants` at all. A cluster like `("v", "ŋ")`
       could end up whitelisted even though `/ŋ/` is separately marked onset-illegal *everywhere*.
       Fixed by mirroring fresh generation's own filter (`p[0] not in excluded and p[1] not in
       excluded`) before thinning the cluster pool, rather than inventing a new approach.
    Both confirmed via dedicated regression tests (a strict Mandarin-lineage seed empirically found to
    produce each clash) rather than just inferred from reading the code.
  - **A fourth inconsistency, found later via the CLI (`--evolve-from`), same root cause again**:
    `_build_onset`'s single-consonant branch excludes a consonant with zero entries in
    `allowed_onset_nucleus_pairs` (see point 1 above), but its cluster/triple/quad branches -- which
    pick straight from `allowed_onset_clusters`/`allowed_onset_triples`/`allowed_onset_quads` -- never
    applied that same filter to the cluster's *last* member (the one actually adjacent to the nucleus).
    A sound-change-introduced cluster like `("c", "s")` whose `/s/` had zero inherited nucleus pairings
    could still be chosen whole, `_choose_nucleus` then fell back to its unrestricted pool for that `/s/`,
    and `is_valid_syllable` correctly rejected the resulting `(("c", "s"), "i", ("j",))`. Fixed the same
    way as point 1: both branches now narrow their candidate pool to clusters/triples/quads whose last
    member has at least one legal pairing, falling back to the unfiltered pool only if that would empty
    it. Confirmed via a dedicated regression test (`test_evolution_does_not_crash_when_an_onset_cluster_
    has_no_nucleus_pairing` in `test_sound_change.py`, a seed reproducing it without any source-language
    lineage at all -- this gap didn't need one).
  - **Stage 2 (landed, pass 39): evolve the inventory and frequency multipliers as their own object.**
    New `_evolve_phonology_membership` (`sound_change.py`), called from `_inventory_and_structure`
    right after it tokenizes the sound-changed wordlist into `used_symbols`, before building the
    `consonants`/`vowels` tuples from it:
    - **Loss**: every phoneme the *base* (pre-evolution) inventory already had gets one roll against a
      small, time-scaled merger rate (`_saturating_rate(years, _MERGER_HALF_LIFE=600.0, 0.0)` -- no
      trait scales the rate itself, since losing a sound is ordinary lineage-internal drift, not a
      "straying from the reference" question).
    - **Gain**: the sound-change rules still produce their candidate new phonemes exactly as before --
      `_apply_ejective_drift` etc. are untouched. Each phoneme sound change actually introduced (not in
      the base inventory) gets an acceptance roll: `biased_probability(1.0, strictness if in_lineage
      else -strictness)`, floored at `_MIN_GAIN_ACCEPTANCE = 0.1` -- a candidate already in the matched
      lineage profile's own palette is accepted outright at any strictness; a foreign one is suppressed
      proportionally to strictness but never driven to exactly 0, so gaining a sound stays possible even
      for a fully strict lineage, just less likely (the "dial, not a wall" correction from this feature's
      own design history, above). Membership is a plain "in any matched lineage profile or not" check,
      not weighted by each profile's own relative influence the way fresh generation's own bias is --
      a deliberate simplification, noted in `docs/LIMITATIONS.md`.
    - **Frequency drift**: a new `_drift_position_multipliers` nudges each already-populated
      `onset_symbol_multipliers`/`nucleus_symbol_multipliers`/`coda_symbol_multipliers` entry by a small
      bounded random step (`±0.15`, clamped to `[0.1, 3.0]`) each evolution call, instead of leaving them
      frozen at whatever fresh generation first rolled (Stage 1 only *preserved* them; this is what
      finally makes them actually evolve). A no-op whenever every field is already empty -- true for any
      language that never had a matched reference profile with positive strictness at generation time,
      so this still spends no rng for the overwhelming common case.
    - A dedicated safety floor, `_restore_class_floor`: Loss and Gain roll independently per symbol, so
      an unlucky run could in principle empty out a whole consonant or vowel class for an already-small
      inventory over a long time depth. Not a modeled linguistic draw (spends no rng) -- just puts back
      one representative symbol (preferring one the base language already had) if a class would
      otherwise end up with nothing.
    - **Gated on `strictness > 0.0` (no matched lineage collapses `strictness` to `0.0` too)**: at the
      project's own default (`source_language_strictness=0.0`), `_evolve_phonology_membership` returns
      `used_symbols` completely unchanged and spends zero rng draws -- confirmed by construction (an
      early return, not just a 100%-probability roll), matching this project's own "no signal, no draw"
      convention used throughout `phonology_gen.py`. `_drift_position_multipliers` is additionally gated
      on `years > 0`, matching this file's pre-existing "zero years, zero change" invariant.
    - All three draws (Loss, Gain, and frequency drift) share one dedicated rng stream,
      `random.Random(f"{seed}:phonology-evolution")`, constructed fresh inside `_inventory_and_structure`
      each of its two call sites (provisional, pre-borrowing/coining; final, post-everything) -- an
      independent per-feature stream, so this never perturbs any other draw sequence in the file.
    - **Empirically verified** (not just unit-tested): a strict (`strictness=1.0`) Dutch-lineage language
      evolved 500 years gained ejective drift's `/pʼ,tʼ,kʼ/` in 9 of 40 seeds, versus 40 of 40 at
      `strictness=0.0` over the same seed range -- damped by roughly 4x, never blocked outright.
  - **Stage 3 (landed, pass 39): words are fit to the evolved spec, not derived into it.** New
    `_refit_rejected_symbols`, called once right after each `_inventory_and_structure` call that
    produces output actually stored on the returned `Language` (the final call; the provisional call
    feeds only word coinage, which already targets whatever inventory it's given). For each word's own
    IPA, tokenizes it against the evolved language's own restricted symbol pool and, only if some symbol
    isn't in the just-decided final inventory (a Stage-2-rejected gain, or a merged-away loss), repairs
    it via the exact same nearest-neighbour-and-syllable-repair machinery `translation/names.py`/
    `generation/real_words.py` already share (`phoneme_fit.fit_ipa`) -- no new feature-distance code
    needed, confirmed generic and reusable as investigated during this feature's own design. Functions as
    a real phonemic merger, consistently wherever that symbol occurs in the lexicon, closing exactly the
    class of inventory/wordlist inconsistency Stage 1's own testing twice surfaced (a sound-change-
    introduced consonant with no inherited onset/nucleus pairing; an onset cluster containing a
    separately-excluded symbol) -- except this time by construction, for every evolution run, not just
    patched for the two cases testing happened to find. Left deliberately untouched (never even
    tokenized) when every symbol already belongs -- the overwhelming majority of words on every run, and
    the only way to avoid `fit_ipa`'s own stress/word-accent/tone-mark-stripping preprocessing (it's
    segment-only machinery, shared as-is from its two existing callers) touching a word that never
    needed repairing; documented as a real, if rare, information loss in `docs/LIMITATIONS.md`.
  - 7 tests added to `test_sound_change.py` for stages 2/3 (on top of stage 1's own 3): the
    `strictness<=0`/no-lineage collapse-to-noop guarantee (two variants, using a `_PoisonRng` that raises
    if `.random()` is ever called, proving zero draws rather than just a matching result); the gain
    floor's exact threshold behavior via a `_FixedRng` stub (deterministic, not a seed search); a merger
    test showing a retained symbol can be lost while `_restore_class_floor` prevents total class
    collapse; the end-to-end strict-vs-loose ejective-damping statistic combined with a per-entry
    inventory-consistency check (the Stage 3 regression guard) across both configurations; frequency-
    multiplier drift (same symbol keys, moved values, still in bounds); determinism (same seed, same
    evolved spec).

- **Rules are generic, not language-specific (grammar pass 40, stages 1-3).** `docs/DEFERRED.md`'s
  "Language evolution" section's last open item: the strictness-reaches-evolution work above made each
  rule's own *candidate output* lineage-aware, but the six rules themselves (which fire, how fast) were
  still 100% generic -- `_compute_rates(years, traits)` read only `years` and the generic `TraitProfile`
  (mostly `contact_intensity`, plus `altitude` for ejectives), never `lineage_profiles` at all.

  **User feedback that reshaped a one-stage draft into three stages** -- worth recording, since it's
  the design decision behind this pass's whole shape: a first draft covered only real-lineage curation
  (Stage 1 below). Two corrections: (1) this must stay flexible to what the *prompt* says about the
  evolution period's own circumstances, not just hard-coded per-language facts; (2) a *fictional*
  language (no matched real source) should also get language-specific drift, not just the curated real
  profiles. Resolved as three independently-landable stages, same shape this session's strictness arc
  already established.

  - **Stage 1 -- real-lineage curated historical tendencies.** Six new `historical_*_affinity` fields on
    `ReferenceLanguageProfile` (one per rule), mirroring `coda_devoicing`'s own shape and the
    `Field(default=0.0, ge=-1.0, le=1.0)` convention every signed `core/traits.py` field already uses.
    `coda_devoicing`'s own docstring already flagged the gap directly ("not just `sound_change.py`'s
    diachronic `final_devoicing` rule") -- confirming this is a real, previously-unfilled need, not an
    invented one. A new `_lineage_rule_bias(lineage_profiles, field)` (a plain, unweighted mean across
    matched profiles -- the same deliberate simplification already documented for the strictness-
    acceptance work) and `_biased_strength(trait_strength, *biases)` (sums every bias, clamps to
    `[-1, 1]`) combine each rule's existing generic trait input with its own lineage bias before
    `_saturating_rate` runs. `_compute_rates` gained `lineage_profiles: tuple[...] = ()` (default keeps
    every pre-existing 2-argument call byte-identical); `evolve_language`'s own `lineage_profiles`
    computation moved a few lines earlier (it has no dependency on anything computed after it) so it's
    ready before `_compute_rates` needs it.

    First-batch curation, 14 of 51 profiles, each anchored to a real, citable case -- several already
    this module's own docstring anchors: Dutch/German/Russian/Turkish/Polish get
    `historical_final_devoicing_affinity=0.8` (reusing the exact five profiles already curated
    `coda_devoicing=true`, not re-researched); Dutch/German also get `historical_ejective_drift_affinity
    =-0.6` (real Dutch/German never developed ejectives -- this session's own running example, now
    damping the rule's own *rate* in addition to Stage 2/3's existing acceptance-damping); English gets
    `historical_cluster_simplification_affinity=0.8` and `historical_vowel_reduction_affinity=0.7` (both
    this module's own cited anchors); Latin/Spanish/French/Portuguese get `historical_lenition_affinity
    =0.7` (Western Romance intervocalic lenition) -- **Italian deliberately excluded**: a first draft
    included it, caught and corrected before committing -- real Italian sits on the "Eastern Romance"
    side of the La Spezia-Rimini isogloss and resisted this specific lenition, unlike its Western
    relatives; Russian/Polish/Serbo-Croatian get `historical_palatalization_affinity=0.7` (Slavic
    palatalization); Quechua/Georgian get `historical_ejective_drift_affinity=0.7` (confirmed both
    profiles already curate real ejectives in their own `consonants` list, not just asserted by
    reputation); Mandarin gets `historical_vowel_reduction_affinity=-0.5` (tonal, resists reduction).
    Magnitudes (0.5-0.8) are illustrative, same honesty standard as every other hand-set trait value.

  - **Stage 2 -- structural self-derived tendencies (any language, fictional included).** The direct
    answer to "what about fictional languages": a new `_derive_structural_bias(inventory, structure)`
    reads the evolving language's own *current* phonology/syllable structure -- no curation, no lineage
    match needed, so it applies identically whether or not Stage 1 found anything to match. Six signals,
    each capped at `_STRUCTURAL_BIAS_CAP=0.4` (deliberately smaller than Stage 1's 0.6-0.8 real-lineage
    magnitudes -- an inferred structural tendency is a weaker signal than a documented real fact):
    cluster_simplification scales with existing cluster-pair count; lenition scales with what fraction
    of the rule's own lenition-target voiceless stops (`_VOICELESS_TO_VOICED`'s own keys) already have
    their voiced counterpart present ("voicing-ready"); final_devoicing is a flat bonus only when the
    syllable structure currently permits a voiced obstruent in coda position at all (reusing the exact
    obstruent-manner tuple `_recompute_syllable_structure`'s own coda-devoicing check already uses);
    palatalization needs *both* an existing palatal/postalveolar output and a front vowel to condition
    it; vowel_reduction scales with vowel inventory size (the tonal counter-signal is deliberately left
    to Stage 3's `tonal_friendliness` instead, to avoid double-counting the same idea as both a
    structural and a trait signal); ejective_drift is a flat bonus when the inventory already has any
    ejective (extending a small existing series is a smaller step than inventing the category). Returned
    as a `_StructuralBias` dataclass -- same six field names as `_Rates` itself, composed into
    `_compute_rates` via the same `_biased_strength(*biases)` call each rule already had, so adding this
    source needed no new combination logic, just one more argument per call.

  - **Stage 3 -- richer use of already-extracted traits for the evolution period's own circumstances.**
    Reframes "stay flexible to the prompt" as "use traits the classifier already extracts more fully,"
    not "extend the classifier" -- deliberate, reasoned choice: the classifier's one call already
    extracts 23 distinct concepts via one large, tuned system prompt; a genuinely new free-text concept
    needs its own careful prompt engineering and risks degrading that already-large call's accuracy.
    Four traits already existed, already extracted, and were either previously proven-unused
    (`terrain_communication_distance` -- explicitly deferred in the "Wiring existing traits" pass, pass
    36, for lack of a mechanism; this *is* that mechanism, confirmed via its own classifier description,
    "+ need for loud/long-distance communication; - close-quarters, no such need") or already
    well-precedented for a directionally-similar purpose elsewhere: `orality_literacy` (already consumed
    for `_compute_orthography_rates`'s own `-traits.orality_literacy` reform-rate reasoning) is extended
    to all six segmental rules uniformly, same sign -- a written norm anchors pronunciation against
    drift the same way it anchors spelling; `tonal_friendliness` biases `vowel_reduction` negative (a
    tonal-leaning language's vowel quality carries real contrastive load, resisting reduction -- the
    generic, trait-driven version of what Stage 1's Mandarin curation already illustrates for one
    profile, now covering any tonal-leaning language); `terrain_communication_distance` also biases
    `vowel_reduction` negative (a reduced, schwa-like vowel carries less distinctly over distance --
    reinforcing, not duplicating, the `tonal_friendliness` link, same target rule, two independent real
    reasons); `aesthetic_harshness` biases `ejective_drift` positive (mirrors the exact existing
    fresh-generation precedent, `_fricative_inclusion_probability`'s own harsh-/soft-leaning fricative
    bias). Deliberately *not* wired for this pass: `isolation`/`community_scale`/`social_hierarchy`/
    `spatial_reference`/`evidentiality_culture`/`ritual_register`/`taboo_register` -- no individually
    crisp, sound-change-*rate*-specific motivation found for these beyond what they already do
    elsewhere, consistent with "illustrative, not exhaustive."

  All three sources combine *additively*, never replacing each other or the evolution's own existing
  generic traits -- the whole point of routing every one of them through the same `_biased_strength`
  clamp: a real-lineage match, a structural signal, and a prompt-described circumstance all nudge a
  rule's rate together, none silently overriding what the others already say.

  Tests: 10 new tests for Stage 1 in `test_sound_change.py` (`_lineage_rule_bias`/`_biased_strength` unit
  tests; a per-rule real-profile test for each of the six rules showing the biased rate moves in the
  expected direction relative to an unmatched run at the same years/traits; a byte-identical-at-default
  regression guard; an additive-composition-with-contact_intensity test) plus 5 in
  `test_reference_languages.py` (one `test_only_the_real_X_declares_Y`-style set-pinning test per
  curated field, mirroring the existing `coda_devoicing` precedent); 9 new tests for Stage 2 (one per
  rule's own structural signal using small synthetic `PhonemeInventory`/`SyllableStructure` fixtures, a
  minimal-fixture near-zero guard, a `_compute_rates` reach-through test, and a true wiring test that
  monkeypatches `_compute_rates` to spy on what `evolve_language` itself actually passes it -- confirms
  the derivation reads *this run's own* base being evolved, not a stale default); 4 new tests for Stage 3
  (one per trait wiring, plus a guard that `orality_literacy`'s existing orthography effect and its new
  segmental-rule effect both fire from one `TraitProfile` without silently drifting apart). A real
  regression surfaced and fixed along the way, twice: five existing tests monkeypatch `_compute_rates`
  with a fixed-arity lambda (`lambda years, traits: _ZERO_RATES`) to force a no-sound-change baseline;
  each new positional parameter (`lineage_profiles`, then `structural_bias`) broke all five until the
  lambdas were corrected -- fixed permanently the second time by switching them to `lambda *args,
  **kwargs: _ZERO_RATES`, immune to any further signature growth.

- **Evolved real words (grammar pass 41).** `docs/DEFERRED.md`'s "Evolved real words (S)" item: a word
  seeded from a real source language (`generation/real_words.py`) kept only a text tag in its own
  `notes` field (`"real word: Dutch"`/`"real-based word: Dutch"`) marking *that* it had a real origin --
  the literal original spelling/pronunciation (`RealChoice.form`/`.ipa`) was used once to build the
  entry's own `ipa`/`romanization` and then discarded, never retained anywhere. Worse, `evolve_language`'s
  own entry-rebuild loop unconditionally overwrites `notes` to an `"orthography: {path}"` tag every
  single evolution run, destroying even that provenance *tag* the moment a real word evolves once.

  Fix: a new `RealWordOrigin` model (`core/lexicon.py`: `language`/`form`/`ipa`) and a new
  `LexicalEntry.real_word: RealWordOrigin | None` field, set once at coinage
  (`real_words.build_real_entries`, for both the exact-copy and the deviated-variant path -- the
  deviated path specifically stores the *true* original, not its own already-looser starting `ipa`,
  which is a materially different string once word strictness is below 1.0). The key mechanism needing
  no new propagation code at all: `evolve_language`'s entry-rebuild loop (`sound_change.py`, the
  `evolved_entries` loop) never mentions `real_word` in its own `update` dict for the ordinary
  "same word, sound-changed" path, so `entry.model_copy(update=update)` -- Pydantic's own "only touch
  what's named" semantics -- preserves it automatically, across any number of successive evolution
  calls, each one just carrying forward whatever the previous call already set. The one place it *is*
  explicitly cleared: the "borrowed" and "replaced" paths (a genuinely different word filling the same
  meaning's slot, scenario 2a/2b, not the same word sound-changing) -- mirroring exactly how `root`/
  `word_class` are already reset to `None`/reassigned on those same two paths.

  Display: `cli/main.py`'s existing evolve-print loop (`old_entry`/`new_entry`, the "old -> new"
  comparison) appends `(real Dutch water [ˈvatər])` when `new_entry.real_word` is set -- deliberately
  reading `new_entry.real_word`, not re-deriving anything from `old_entry` (which is only ever the
  *immediately preceding* saved language; on a second-or-later evolution run it's already an evolved
  form itself, not the real source word). Verified via the CLI on two successive evolution runs: the
  printed origin stayed `(real Dutch ik [ɪk])` on both, correctly reaching all the way back past the
  first evolution step. The web UI's own lexicon table and `real_words` summary count
  (`webui/app.py`) switched from the same `notes`-prefix check to this new field for the same reason --
  the old check was silently undercounting after any evolution, a latent instance of the identical bug.

  Explicitly out of scope: a word seeded via the generic `--example gloss=form` flag (no claim of
  realness, so no marker); the exact-vs-deviated distinction, which still only lives in `notes` and
  still only survives until the first evolution step (not worth a second field for a cosmetic
  distinction once the real fix -- keeping the *word* -- already landed).

  Tests: `tests/test_real_words.py` (exact copies carry the correct `RealWordOrigin`; a deviated
  real-based word's `real_word` is the true original, not empty/blank; an algorithmically coined word
  has no `real_word` at all); `tests/test_sound_change.py` (survives one evolution step unchanged;
  survives two *successive* evolution steps unchanged -- the multi-generation case the CLI's own print
  can't reach on its own; a seed-search test confirming `real_word` is cleared specifically on a
  borrowed/replaced entry, not on an ordinary sound-changed one).

- **Orthography reform is partial -- spelling-pronunciation drift (grammar pass 42).**
  `docs/DEFERRED.md`'s "Orthography reform is partial (M)" item. `evolve_romanization`
  (`generation/romanization_gen.py`) already modeled two real diachronic forces per symbol: reform
  (drop + regenerate a symbol's own spelling rule) and freeze (keep it verbatim -- why real
  orthographies get silent letters, e.g. Dutch "berg" [bɛrx] still spelled "g"). Missing: a third real
  phenomenon where a letter's own *written form* stays exactly the same while its *conventional
  reading* quietly reassigns to a nearby sound, with no formal reform event (real Latin "c" -- always
  /k/ -- came to be read /s/ before front vowels purely by reinterpretation, not a spelling reform;
  English "gh" similarly drifted from a real consonant to silence).

  Confirmed via research before designing: this project has **zero existing notion** of "a spelling's
  own customary reading, independent of a word's authoritative stored `ipa`." `RomanizationRule`
  (`core/romanization.py`) is strictly `ipa -> latin`, one-directional, never reversed anywhere in the
  codebase; a word's `entry.ipa` is the sole authoritative pronunciation, and `entry.romanization` is
  always freshly re-derived from `(scheme, entry.ipa)` on every evolution call. This rules out
  preserving an *individual already-written word's* old fossilized spelling independent of its current
  sound (no such second, tracked quantity exists anywhere, and adding one would be a materially bigger
  architectural change) -- what the fix *can* do, within the existing one-directional architecture, is
  make the **scheme itself** reassign a grapheme's own meaning, with the natural, already-existing
  consequence that every word still pronouncing the *old* symbol gets a freshly-reformed spelling this
  same run (exactly how ordinary `reform` already behaves for any symbol). This captures the real
  phenomenon's visible effect (a letter's meaning changes) honestly within the project's existing
  "spelling is always freshly computed" design, short of a genuinely bigger rewrite -- documented as a
  real scope limit in `docs/LIMITATIONS.md`, not glossed over.

  **Mechanism**: a new `_OrthographyRates.reading_drift` field (`sound_change.py`), its own
  `_ORTHOGRAPHY_HALF_LIVES["reading_drift"] = 350.0` (between `reform`'s 500 -- rarer, deliberate -- and
  the existing cosmetic grapheme-simplification `drift`'s 200 -- this is quieter and more gradual than
  a formal reform but still a slow, centuries-scale reinterpretation), computed via the same
  `-traits.orality_literacy` link `reform` already uses (a well-taught written norm is exactly what
  keeps a letter's own conventional reading stable, the same force that keeps formal reform rare).
  Threaded into `evolve_romanization`'s new `reading_drift_rate: float = 0.0` parameter (default keeps
  every existing call byte-identical).

  In the per-symbol loop, a symbol that would otherwise *freeze* gets one further, independent roll:
  if it fires, its own rule(s) -- a symbol with multiple old context-conditioned rules moves as one
  group, the same "never split" discipline reform already uses -- keep their `latin` spelling exactly,
  but their `ipa` key reassigns to a same-class nearest neighbor still in the new inventory
  (`phoneme_fit.neighbours`, promoted from the previously-private `_neighbours` -- the exact same
  nearby-sound-substitution machinery `deviate_ipa` already uses for an analogous purpose, no new
  distance code needed; the one existing internal caller's own local variable, confusingly also named
  `neighbours`, was renamed `nearby` to avoid shadowing the newly-public function). The *vacated*
  original symbol needs its own rule now -- handled by a small two-pass structure: the main loop tracks
  which symbols "drifted away," then a short cleanup pass generates a fresh rule (via the exact same
  `_rules_for_symbol` reform already calls) for any drifted-away symbol not already covered by some
  *other* symbol's own inbound drift. That "already covered" check (by `ipa` value, not by object
  identity) is deliberate, not incidental: it lets a short reassignment chain (symbol A's old grapheme
  ends up serving symbol B, which itself later drifts away too) resolve correctly for free, without any
  cascading/recursive logic -- confirmed via a 200-seed sweep that no inventory symbol is ever left
  without a rule, including seeds that produce exactly this kind of chain.

  **Explicitly deferred**: context-conditioned drift (real Latin c/s is conditioned on a following
  front vowel, not a flat reassignment) -- a materially bigger, more linguistically precise
  undertaking; preventing two different symbols' own independently-generated replacement graphemes
  from coincidentally colliding on the same letter -- an existing risk ordinary reform already has, not
  one this introduces, so left unguarded the same way.

  Tests: `tests/test_romanization_gen.py` (`reading_drift_rate=0.0` byte-identical to omitting it
  entirely; a drifted symbol's grapheme moves to a *different* ipa key while the vacated original stays
  covered; zero dropped symbols across 200 seeds; a lone vowel with no same-class neighbor always
  keeps its own spelling, confirming the "no neighbor, freeze instead" fallback). `tests/test_sound_change.py`
  (`orality_literacy` moves `reading_drift` the same direction as the existing `reform` rate; a real
  evolved language's romanization still covers every phoneme in its final inventory across 10 seeds at
  a long time depth and low literacy, where reading drift is near-certain to fire at least once).

- **Orthography reform follow-up: an unaffected existing word keeps its own old spelling through reading
  drift (same grammar pass 42).** User follow-up directly asking to close the gap the pass above had
  just documented as an explicit limitation: "every existing word still pronouncing the vacated symbol
  gets re-spelled this same run... no simulation of old written words keeping a fossilized spelling
  while new ones follow the reassigned convention." Confirmed the real-world asymmetry that makes this
  tractable without a bigger rewrite: a genuine, deliberate *reform* really does retroactively re-spell
  every existing word (dictionaries get updated); *reading drift* is a quiet reinterpretation nobody is
  actively enforcing, so an already-written word whose own sound never moved has no real-world reason to
  look any different. The fix only needs the caller to tell the two apart per word, not a general
  per-word spelling-history mechanism.

  `evolve_romanization`'s return type changed from `RomanizationScheme` to `tuple[RomanizationScheme,
  frozenset[str]]` -- the second element is every symbol touched by drift this call, from *either* side
  of a reassignment: the already-tracked `drifted_away` (the symbol that lost its own grapheme) *and* a
  new `drift_targets` (the symbol that received a donated one, which could just as easily outweigh/
  replace whatever spelling it already had). Missing the target side initially made the fix's own first
  draft noticeably rarer to trigger in practice (confirmed via a quick seed sweep before writing the
  real test: searching for a seed that actually produces a frozen entry) -- adding it roughly doubled
  the observed hit rate (e.g. ~50% of seeds at years=300/`orality_literacy=-0.95`, up from a source-only
  version), since either side of one reassignment can now protect an affected existing word.

  `evolve_language`'s entry-rebuild loop (the "same word, sound-changed" branch) checks the returned set
  *before* its existing reform/unchanged/conventional comparison: if the word's own sound is unaffected
  this run (`final_ipa == entry.ipa`, the same condition the pre-existing "unchanged" path already uses)
  *and* its own `spelling_ipa` uses a drift-touched symbol, its spelling freezes exactly where it was
  (`notes: "orthography: pre-drift"`) -- skipping the reform/unreformed comparison entirely, since the
  whole point is to *not* re-render through the new scheme. Every other path (borrowed, replaced, a
  word whose own sound did move, or a word untouched by drift at all) is completely unaffected -- this
  is a new, narrow carve-out ahead of the existing logic, not a rewrite of it.

  All ~11 existing callers of `evolve_romanization` (the one production call site plus direct test
  calls) needed updating to unpack the new tuple return -- mechanical, `evolved, _ = ...` where the
  second value wasn't needed, following this project's own "returns `(value, auxiliary)` when there's
  real auxiliary info to report" precedent (`_evolve_ipa`, `_evolve_tone_system`).

  Tests: `tests/test_romanization_gen.py`'s existing reading-drift tests updated to also assert on the
  returned set directly (e.g. a known-drifted symbol is actually named in it, and the set never contains
  anything outside the inventory); `tests/test_sound_change.py` adds a seed-searched end-to-end test
  confirming a real "pre-drift" entry keeps `ipa`/`romanization` byte-identical to its pre-evolution
  values (years=150 was empirically found to produce this far more reliably than the original pass's own
  years=2000 example -- a *shorter* time depth leaves more words' own sounds genuinely unaffected by
  actual sound change, which is exactly the population this fix targets; a very long time depth leaves
  almost nothing unaffected, since `orality_literacy` -- needed to make drift likely -- also speeds up
  the six segmental rules themselves via this session's own earlier "rules are generic" pass).

- **Phonetic-context conditioning: a real conditioned sound-change rule, and a context-conditioned
  reading drift (grammar pass 43).** Direct user follow-up to the reading-drift pass's own explicitly-
  deferred nuance ("real Latin c/s is conditioned on a following front vowel, not a flat reassignment").

  Working through a concrete design before writing any code surfaced a correction worth recording: real
  Latin "c" -> /s/ before front vowels wasn't pure *orthography* drift (the spelling's own meaning
  silently reinterpreting with *no* underlying sound change, which is what `reading_drift_rate` models)
  -- it was a genuine **conditioned sound change** (/k/ phonetically shifted, specifically before front
  vowels) **combined with ordinary spelling freeze** (the letter "c" was never updated to reflect it).
  That's two different, independently useful features, confirmed as landed separately, both as a first
  pass each (user's own framing: "start with both"):

  - **Part 1 (`sound_change.py`)**: `_apply_palatalization` (already conditioned on a following front
    vowel -- unchanged) used to have one fixed target per source consonant,
    `_PALATALIZATION: dict[str, str] = {"k": "tʃ", "g": "dʒ"}`. Real Romance palatalization's own outcome
    varies by lineage/stage -- Italian stayed at the affricate; French/Latin-American Spanish went one
    step further, to a plain sibilant. Replaced with `_PALATALIZATION_VARIANTS: dict[str, tuple[str,
    ...]] = {"k": ("tʃ", "s"), "g": ("dʒ", "z")}` and a new `_PALATALIZATION_AFFRICATE_WEIGHT = 0.65`:
    the existing trigger roll (`rng.random() < rate`, unchanged) is followed, only when it already
    fired, by one new weighted draw picking which variant -- strictly after the existing draw in that
    function's own sequence, this project's own established RNG-stream convention for extending a roll
    rather than disturbing it. Both outcomes stay single-character, deliberately, so this never needs
    `_reachable_sound_change_symbols`'s own multi-character-tokenizer-pool handling (the intermediate
    `ts`/`dz` stage real Romance passed through is not modeled, to keep this pass's footprint small).
    `_PALATALIZATION_OUTPUTS` (already read by Stage 2's own `_derive_structural_bias` palatalization
    check, from the "rules are generic" pass) was updated to recognize both new variants too, so a
    language that already drifted this way still correctly counts as "already partway down this path"
    for that existing structural signal. Confirmed via a 300-seed sweep: both outcomes reachable, the
    affricate the clear majority, matching the configured weight.

  - **Part 2 (`romanization_gen.py`)**: confirmed via direct reading of `core/romanization.py`'s own
    module docstring and `RomanizationScheme._neighbor_tags`/`_specificity` that the conditioning
    infrastructure this needed **already fully existed and was already wired for exactly this real-
    world pattern** -- `RomanizationRule.following`/`preceding` already accept the class tags
    `"front_vowel"`/`"back_vowel"` (the docstring's own cited real example: French/Italian/Spanish
    spelling a consonant differently before a front vs. back vowel), computed dynamically by
    `_neighbor_tags` from `RomanizationScheme.vowel_backness` (already populated by `evolve_
    romanization`'s own `_scheme_context(new_inventory)` call), and `apply()` already prefers the more
    specific matching rule when both a conditioned and an unconditioned rule exist for the same symbol.
    Zero new infrastructure needed in `core/romanization.py` at all -- only a different shape of rule
    for `evolve_romanization` to *generate*. New `_CONTEXT_CONDITIONED_DRIFT_PROBABILITY = 0.4`: when
    the drifting `symbol` is a **consonant** (gated via a new `consonant_symbols` set built once before
    the loop -- a vowel can't condition on its own frontness, its identity already fixes that, per the
    docstring's own note), a further roll decides flat reassignment (today's existing behavior,
    unchanged) vs. a **conditioned split**: `symbol`'s own old rule(s) are kept completely unconditioned
    for "elsewhere," *and* a second copy is added with `ipa=target, following=("front_vowel",)` -- the
    same old grapheme now spells the target specifically before a front vowel too, while continuing to
    spell `symbol` everywhere else. `symbol` is deliberately *not* added to `drifted_away` for a
    conditioned split (nothing was vacated), but both `symbol` and `target` are still added to
    `drift_targets` (and so to the returned `reading_drifted` set) -- the prior pass's own "pre-drift"
    freeze check needs this either way: an existing word using `symbol` before a front vowel, whose own
    sound didn't change, must not be swept into the new conditioned spelling just because that specific
    context now has a competing, more-specific rule. Verified end to end with a direct `apply()` call on
    a seed-searched conditioned-split scheme: `/k/` renders "k" in any context (unaffected); `/x/` before
    a front vowel renders "k" too (the conditioned split firing); `/x/` before a back vowel still
    renders its own old "kh" (falling back to the unconditioned rule) -- the real Latin c/s shape,
    reproduced exactly.

  **Explicitly deferred**: lineage-biasing *which* palatalization variant a matched real profile prefers
  (a natural, well-precedented extension reusing the "rules are generic" pass's own `historical_*_
  affinity` shape, but a separate, later enrichment); the intermediate `ts`/`dz` stage; a reading-drift
  conditioning tag other than front/back vowel (syllable position, a specific neighboring consonant);
  preserving any *pre-existing* `following`/`preceding` constraint a drifting rule already had (this
  pass's own conditioned rule overwrites `following` outright -- a documented simplification, since
  today's drifted-from rules are typically unconditioned to begin with).

  Tests: `tests/test_sound_change.py` (both palatalization outcomes reachable across a 300-seed sweep
  with the affricate dominant; the existing front-vowel trigger condition still gates it, unchanged;
  `_PALATALIZATION_OUTPUTS` recognizes both variants). `tests/test_romanization_gen.py` (a vowel's own
  drift never produces a conditioned rule, only a consonant's can; a seed-searched conditioned split
  leaves the source symbol's own unconditioned rule intact, reports both sides in the returned
  `reading_drifted` set, and renders correctly end to end via a direct `apply()` call covering all three
  cases -- the unaffected symbol, the conditioned match, and the conditioned non-match falling back to
  the old spelling).

- **Deontic modality: an independent `"obligative"` mood (grammar pass 44).** User asked to "address
  auxiliaries and periphrastic tenses from deferred in verb phrasing" -- `docs/DEFERRED.md`'s own "Verb
  phrase still missing" bullet. Auditing that bullet against the real code found it **stale**:
  auxiliaries/periphrastic tenses are already fully built (`GrammarProfile.periphrastic_labels`/
  `auxiliary_position`/`auxiliary_agreement`; `PERIPHRASTIC_CANDIDATES`/`roll_aspect_followups` in
  `inflection_gen.py`; `_auxiliary_entries`/`_apply_auxiliary_agreement`/`_split_periphrastic`/
  `_decode_auxiliary_entry` in `translator.py`; `_grammaticalize_and_fuse` in `sound_change.py` --
  passes 16, 29, 30), as is evidentiality. The bullet was rewritten to narrow it to what's actually
  still missing (negative verbs, serial verbs, valency-changing morphology beyond pass 31, a
  state-vs-identity copula distinction, adverb placement) -- and the audit surfaced one real,
  previously-unnamed gap instead: the existing `MOOD_SYSTEMS` tiers cover epistemic/ability modality
  (`potential`, "can"/"may"/"could") and counterfactual (`conditional`, "would"), but nothing anywhere
  marked **obligation** ("must"/"should") as its own category.

  Reuses the entire existing mood pipeline end to end -- no new `GrammarProfile` field, no new
  mechanism class. One new label, `"obligative"`, threaded through every table a mood label already
  flows through:
  - **Generate** (`inflection_gen.py`): `roll_moods` gains a new, *independent* draw appended strictly
    after its existing tier-choice roll (`_OBLIGATIVE_RATE = 0.4`) -- `"obligative"` is layered onto
    whichever of the three `MOOD_SYSTEMS` tiers this seed already rolled (including the empty tier),
    rather than inserted as a fourth tier, since obligation marking is cross-linguistically independent
    of irrealis/subjunctive/conditional/potential (a language can have it with or without any of
    those). `PERIPHRASTIC_CANDIDATES` gets `"obligative"` appended at the *end* of its 11-tuple, not
    inserted into the middle -- preserves every pre-existing candidate's own draw position in
    `roll_aspect_followups`'s per-candidate roll loop. Confirmed via direct scripted sweeps: the roll
    fires at ≈40% across 2000 seeds (matching the configured rate); it fires independently of the base
    tier, including when that tier is empty; a reconstructed pre-change `roll_moods` matches the new
    one's tier-choice output byte-for-byte across 500 seeds, confirming the new draw disturbs nothing
    before it in the same call. (Both additions do shift *downstream* rng draws for existing seeds on
    their own shared streams -- `aspect_mood_rng`'s later affix-generation calls, and
    `roll_aspect_followups`'s own `position` roll -- the same accepted cost every other new-feature
    pass this session pays when extending a shared sequential stream.)
  - **Plan/render/decode** (`translator.py`): `_AUXILIARY_ENGLISH["obligative"] = "must"`;
    `_english_verb_phrase` gets a `"must {gloss}"` branch between the existing `"potential"`/
    `"subjunctive"` ones. The generic `("mood", mood_label)` annotation builder needed no change --
    already passes through any label string.
  - **Fake planner** (`fake_client.py`): `_FAKE_MODALS` gains `"must"`/`"should"` -> `"obligative"`;
    `_fake_mood_label`'s existing fallback-to-`"irrealis"` logic needed no change.
  - **Real-LLM prompt** (`sentence_planner.py`): the existing `verb_mood` worked-example list gains
    `"must/should see" -> obligative`, and "must" joins the never-write-as-its-own-slot auxiliary list.

  **Explicitly deferred**: a separate `permissive` label for permission (English already loosely covers
  it via `potential`'s "can"/"may" gloss -- splitting it out cleanly needs its own disambiguation work,
  not attempted here); a weaker "advisable" shade distinct from strong obligation ("should" vs "must" as
  two strengths sharing one label today); deontic-evidential interaction.

  Tests (`tests/test_aspect_mood.py`): `roll_moods` produces `obligative` alongside every one of the
  three `MOOD_SYSTEMS` tiers across a 400-seed sweep (confirms independence); a 200-seed sweep confirms
  the obligative draw never changes the tier-choice roll's own outcome for the same seed; the fake
  planner reads "must"/"should" as `obligative`; a direct-plan render+decode round trip on a seed where
  `obligative` is in `grammar.moods` (found by search, periphrastic or affixal depending on the seed)
  confirms the verb form differs from the plain form and decodes back with `verb_mood == "obligative"`;
  a free-text round trip confirms "must see" survives translate_to_conlang -> translate_to_english. One
  pre-existing test (`test_every_language_has_one_of_the_defined_aspect_and_mood_systems`) needed
  updating since `grammar.moods` can now include `obligative` appended to a tier, no longer matching a
  `MOOD_SYSTEMS` tuple literally -- fixed by stripping `obligative` off before comparing the tier itself.

- **Negative verbs: a dedicated `"negative_verb"` negation strategy (grammar pass 45).** The remaining
  item in the verb-phrase bullet after pass 44 (deontic modality): "negative verbs (a dedicated
  negative-verb paradigm, Finnish/Samoyedic-style, as opposed to the existing particle/affix/both
  negation strategies)." In Finnish, negation isn't a particle or a suffix on the main verb -- a
  dedicated *negative verb* ("ei") inflects for person/number while the main verb takes an invariant
  *connegative* stem instead of its normal finite form ("minä en syö" -- "en" is "ei" conjugated for
  1sg, "syö" is the bare connegative of "syödä"). Typologically a third thing, not a variant of particle
  or affix negation: agreement moves *off* the main verb onto a dedicated word, and the main verb itself
  takes a different, invariant stem.

  **New `GrammarProfile` field** (`core/grammar.py`): `connegative_affixes: tuple[InflectionAffix, ...]
  = ()` -- the single invariant `"connegative"` suffix a finite verb takes under this strategy,
  replacing tense/aspect/mood/agreement entirely. No new boolean/position field: the negative-verb word
  reuses the existing `auxiliary_position` for before/after placement (a documented shared-field
  simplification, the same kind pass 34 already used for its shared politeness affix).

  **Rolling it is an *override*, not a fourth weighted option** (`inflection_gen.py`): `negative_verb`
  is a true alternative to particle/affix/both (mutually exclusive), unlike `obligative` (pass 44), which
  layers independently on top of the mood tiers. Inserting it directly into `NEGATION_STRATEGIES` as a
  fourth weight would reshuffle that single roll's own bucket boundaries for every existing seed, so
  instead a new `_NEGATIVE_VERB_RATE = 0.15` roll runs strictly *after* the existing `NEGATION_STRATEGIES`
  draw and, when it fires, replaces whatever that draw just chose. An existing seed's particle/affix/both
  choice is byte-identical whenever the override doesn't fire; only downstream draws (prohibitive,
  periphrastic flags/position) shift when it does -- the same accepted cost pass 44 already took for its
  own new draw, applied here to an override instead of an append since these two strategies can't
  coexist.

  **Generation** (`generator.py`): the pre-existing `verb_negative_affixes` generation, previously gated
  on `negation_strategy != "particle"`, narrowed to `in ("affix", "both")`; a parallel block generates
  `connegative_affixes` (one suffix, label `"connegative"`) when the strategy is `"negative_verb"`,
  threaded into the same suffix-collision `taken` set as the others. `connegative_affixes` was added to
  `inflection_gen._VERB_SUFFIX_FIELDS` (the cross-paradigm collision guard).

  **Absorption** (`translator.py::_negation_absorption`): a new `negative_verb_ok` gate alongside the
  existing `affix_ok`, combined for both "should this run at all" and "drop the standalone negation
  particle slot" (the negative-verb word, spliced in elsewhere, carries the meaning instead -- same drop
  behavior as `"affix"`). Target selection deliberately uses `_finite_verb_indices` (the same list already
  used for imperative), not `_negatable_verb_indices` -- scoping this strategy to **finite verbs only**; a
  non-finite (infinitive/nominalized) clause's own negation stays an ordinary particle under
  `negative_verb` strategy too, the same as it already does for `"particle"` strategy (a documented scope
  limit, avoiding a connegative-for-non-finite-forms sub-feature this pass didn't need). Imperative/
  prohibitive interaction needed zero new special-casing: `negatives` was already never populated when
  `imperative=True` (the pre-existing `if imperative: ... elif affix_ok: ...` structure), so a negated
  command under `negative_verb` strategy falls back exactly like `affix`/`both` already do.

  **Rendering, the main verb** (`translator.py::_apply_verb_inflection`): a new branch mirroring the
  existing `verb_form` "special stem replaces everything" shape -- when `negative` and strategy is
  `negative_verb`, the entry's bare IPA takes just the `connegative` affix (bypassing tense/aspect/mood/
  agreement composition entirely) via a new shared `_connegative_salt` helper (mirroring `_imperative_
  salt`/`_prohibitive_salt`).

  **Rendering, the negative-verb word itself**: `_negative_verb_agreement` mirrors `_apply_auxiliary_
  agreement` almost exactly (same `_combined_tense_agreement_affix` reuse, same main-verb-paradigm
  reuse for the affixes) but **unconditionally** -- unlike a periphrastic auxiliary's optional
  `auxiliary_agreement` trait, marking person/number on this dedicated word is the strategy's entire
  reason to exist, so there's no gate. `_negative_verb_entry` mirrors `_auxiliary_entries` but for the
  single fixed `inflection_gen.NEGATIVE_VERB_GLOSS = "neg-verb"` word (one per language, not one per
  label like `aux-<label>`). Spliced into `_render_plan`'s existing `aux_entries` list (both the
  content-verb and copula branches), right after the periphrastic-auxiliary block -- reuses the already-
  uniform `aux_entries`-splice code completely unchanged, since a negative-verb word and a periphrastic
  auxiliary are positioned identically (both via `auxiliary_position`).

  **Decode, the main verb** (`_decode_verb_full`'s `special()` closure): a new connegative candidate
  check, mirroring the imperative/prohibitive shape, inserted between the prohibitive check and the
  tense x agreement x ... fallback search. **Not optional**: that fallback search only ever tries
  `negative=True` when `verb_negative_affixes` is non-empty, which is never the case for this strategy,
  so without this candidate the connegative-suffixed token would never be recognized as a verb at all.

  **Decode, the negative-verb word itself**: `_decode_negative_verb_entry`/`_split_negative_verb_tokens`
  mirror `_decode_auxiliary_entry`/`_split_auxiliary_tokens`, simplified to a single fixed word/meaning
  (a plain `dict[int, str | None]` of host index -> recovered agreement, not a per-label dict of lists).
  Unlike `_decode_auxiliary_entry` (which only confirms recognition and discards which agreement
  matched, since a periphrastic main verb always keeps its own redundant copy of agreement too), this
  **does** report the matched agreement: a connegative main verb carries none of its own, so this is the
  *only* place a pro-dropped subject's person can be recovered from for a negated sentence. Verified
  concretely during implementation: without this, "He is not happy."/"I am not happy." on a pro-drop
  language both decoded to the identical, subject-less "happy not is" -- a real round-trip regression,
  not a hypothetical. `translate_to_english` calls `_split_negative_verb_tokens` right after the existing
  `_split_auxiliary_tokens`, and uses the recovered agreement as a fallback (`if agreement_label is None:
  agreement_label = negative_verb_hosts[token_index]`) so the existing, unchanged `pro_drop`/
  `_person_suffix_is_distinct` recovery logic picks it up exactly as it already does for an ordinary
  finite verb's own agreement. The existing readback line (`if negative_label and negation_strategy !=
  "both": gloss = f"not {gloss}"`) needed no change at all, since it was already keyed on "not `both`",
  not an enumerated allow-list.

  **Explicitly deferred**: a non-finite clause's negation under this strategy (falls back to a particle,
  see Absorption above); a tense-sensitive connegative (real Finnish also has a past-participle-based
  negative form); the negative-verb word never grammaticalizing into a bound suffix over evolution
  (`sound_change.py::_grammaticalize_and_fuse` is the natural, well-precedented place to extend this
  later, not attempted here).

  Tests (`tests/test_aspect_followups.py`): `negative_verb` appears across a seed sweep alongside
  particle/affix/both; `verb_negative_affixes`/`connegative_affixes` are mutually exclusive by
  construction; the override roll (isolated by temporarily zeroing `_NEGATIVE_VERB_RATE`) leaves the
  base `NEGATION_STRATEGIES` roll's own outcome untouched whenever it doesn't fire, across a 300-seed
  sweep; a direct-plan render test confirms the particle slot is fully absorbed, the main verb's own
  form changes, and a new auxiliary token appears; the auxiliary's own form differs between an "I"
  subject and a "he" subject (the core proof agreement moved off the main verb); it sits at the position
  `auxiliary_position` gives; a free-text round trip decodes "not" and never leaks the auxiliary word as
  `<unknown:...>`; a negated command is unaffected (prohibitive if available, else an unabsorbed
  particle, exactly like `affix`/`both`).

- **Systematic word deviation: a fixed per-language sound-shift table (grammar pass 46).**
  `docs/DEFERRED.md`'s "## 7. Real lexicons" complaint: "Deviation is random, not systematic. Below
  word strictness 1.0 a real word is loosened by random nearest-phoneme swaps; a fixed per-language
  consonant-shift table would look like a real daughter language." Confirmed the word-strictness/
  deviation feature itself (`generation/real_words.py`, wired into `generator.py`) was already fully
  built and working -- only this one mechanism was the actual gap.

  The culprit was `phoneme_fit.deviate_ipa(ipa, inventory, structure, rng, probability)` -- its one call
  site, `real_words.build_real_entries`, ran it once per word inside a per-word loop, over a single
  shared, sequentially-consumed `rng`. Inside it, each IPA symbol independently rolled `rng.random() <
  probability`; on a hit it picked a random neighbour. So the *same* source phoneme (e.g. /p/) got an
  independent fresh roll -- and could land on a *different* neighbour -- every time it occurred, in a
  different word or even twice in the same word. Confirmed `deviate_ipa` had exactly one call site in
  the whole codebase and no test referenced it by name directly, so it was replaced outright rather than
  kept as unused dead code:

  ```python
  def build_deviation_shift(inventory: PhonemeInventory, rng: random.Random, rate: float) -> dict[str, str]:
      shift: dict[str, str] = {}
      for symbol in inventory.all_symbols():
          if rng.random() < rate:
              nearby = neighbours(symbol, inventory)
              if nearby:
                  shift[symbol] = rng.choice(nearby)
      return shift

  def apply_shift(ipa: str, inventory: PhonemeInventory, structure: SyllableStructure, shift: dict[str, str]) -> str:
      symbols = ipa_tokenizer.symbols_only(...)
      tokens = [(shift.get(_nearest(s, inventory)[0], _nearest(s, inventory)[0]), is_vowel) for s in symbols]
      return _repair(tokens, inventory, structure)
  ```

  One roll **per inventory symbol**, not per occurrence -- a fixed table built once, then applied
  uniformly everywhere that symbol appears. This exact shape already existed elsewhere in the codebase
  and was the model to copy: `romanization_gen.py`'s `evolve_romanization` (its own docstring: "decided
  per symbol rather than per word -- so every word sharing a symbol gets the exact same spelling for
  it"), which even reuses the same `phoneme_fit.neighbours` helper to pick a drift target. `real_words.
  build_real_entries` now builds the shift table once, before its per-word loop, from the same
  pre-existing `rng`/`DEVIATION_SCALE` formula (`rate = (1.0 - strictness) * DEVIATION_SCALE`, same
  constant, reinterpreted as "chance a given *distinct sound* shifts" rather than "chance a given
  *occurrence* shifts") -- the rest of the function (tone-fitting, stress carry-over, exact-copy
  short-circuit at strictness 1.0) is untouched.

  Verified concretely (not just reasoned about): generating a Dutch-sourced language at word strictness
  0.5 showed /ɪ/ consistently becoming /e/ and /ɣ/ consistently becoming /ŋ/ across multiple
  independent deviated words -- exactly the systematic-shift behavior the DEFERRED item asked for. The
  existing `test_higher_word_strictness_deviates_less_and_follows_more_words`/`test_partial_strictness_
  gives_looser_variants_using_only_the_languages_own_sounds` regression tests re-ran unchanged: the
  monotonic "lower strictness -> more deviation" trend holds under the new semantics too (more symbols
  land in the shift table at a lower strictness, so more words contain at least one shifted symbol).

  **Explicitly deferred**: a *conditioned* shift (context-sensitive, the way this session's earlier
  palatalization/reading-drift passes modeled a shift before a front vowel specifically) -- a flat,
  unconditioned per-symbol table is this pass's own scope, matching the DEFERRED item's wording ("a
  fixed per-language consonant-shift table"); lineage-aware targeting (biasing *which* neighbour a
  matched real source language's own historical sound changes would actually produce, reusing the
  "rules are generic" pass's `historical_*_affinity` shape); sharing one shift table across multiple
  matched source languages weighted differently (today's single table applies uniformly regardless of
  which matched language a given word came from).

  Tests (`tests/test_real_words.py`): `build_deviation_shift` rolls once per symbol (`rate=1.0` yields a
  non-empty table covering only inventory symbols, no symbol maps to itself; `rate=0.0` yields an empty
  table) and is deterministic for a fixed seed; `apply_shift` maps the same symbol identically wherever
  it occurs, including twice in the same input, using a plain CV/CVCV construction so syllable repair
  can't obscure the comparison; both pre-existing regression tests confirmed still passing.

- **Seed words: part of speech, bulk input, phonotactic-mismatch warning (grammar pass 47).**
  `docs/DEFERRED.md`'s "## 4. Generation from the user's own words": a user can already seed a
  language with their own words (`core/spec.py`'s `SeedExample(gloss, form, ipa)`, in generation since
  before this session) -- `generation/phonology_gen.py::generate_phonology` forces a seed word's own
  phonemes into the inventory regardless of base inclusion probability, and `generator.py` builds each
  as a `LexicalEntry` whose `romanization` is the user's own `form` verbatim (bypassing the romanization
  scheme entirely -- already how verbatim spelling was guaranteed, no new mechanism needed for that
  part). Confirmed via research three concrete, independent gaps, all directly named by the DEFERRED
  text: part of speech was hardcoded to NOUN (`generator.py`, `# v1 simplification -- no POS guessing
  for seed examples`); no bulk input existed, one repeatable `--example gloss=form[|ipa]` CLI flag and a
  dynamic per-row web UI section only; nothing checked a seed word's IPA against the generated
  `SyllableStructure` at all.

  **`SeedExample` gains `pos: PartOfSpeech | None = None`** (`core/spec.py`) -- mirrors `real_words.
  RealChoice.pos`, the closest existing precedent for a per-word POS. `generator.py`'s seed-entry
  construction changes from the hardcoded `pos=PartOfSpeech.NOUN` to `pos=example.pos or PartOfSpeech.
  NOUN` (preserves every existing caller's behavior unchanged) and gains `notes="seed word"` (previously
  unset), mirroring how a real-word entry already carries `notes=f"real word: {language}"` -- makes seed
  words visibly distinguishable in a saved language file. Parsing free text into `PartOfSpeech` reuses
  the enum directly (`PartOfSpeech(text.lower())` -- its own values already equal their lowercase names)
  rather than `translation/sentence_planner.POS_BY_PLAN_STRING`: confirmed via grep that no `generation/`
  module imports from `translation/` today, and that mapping's own quirks (`"adverb" -> PARTICLE`) are
  planner-specific, not what a CLI user typing "adverb" for a seed word should have to know about. CLI:
  `_parse_seed_example` extends `gloss=form|ipa` with an optional third field, `gloss=form|ipa|pos`
  (`gloss=form||pos` skips ipa) via a new `_parse_pos` helper; the `Seed examples: ...` echo and
  `--example`'s own help text both updated. Web UI: `SeedExampleEntry`/`GenerateRequest` gain `pos: str |
  None`, converted via the existing `_parse_enum(raw, enum_cls, field)` helper (member-*name* lookup,
  already used elsewhere in `webui/app.py`) rather than inventing a second enum-parsing helper;
  `index.html`'s per-row seed-example inputs gain a `<select>` of the enum's own seven values.

  **Bulk input** -- one new shared parser, `generation/seed_examples.py::parse_bulk_seed_examples(text)`,
  reused by both the CLI and the web UI rather than parsed twice: stdlib `csv`, one word per line
  (`gloss,form[,ipa[,pos]]`), an optional header row (first cell `"gloss"`, case-insensitive) skipped if
  present, a missing `ipa`/`pos` column tolerated, a row missing its required `gloss`/`form` or carrying
  an unrecognized `pos` skipped rather than raising -- this project's own "degrade gracefully, report the
  gap elsewhere" convention for lenient batch input (the same shape `real_words_llm.py`'s own batch-reply
  parsing already uses). CLI: new `--examples-file PATH` option, its rows combined with any `--example`
  flags (file first, then individual flags) before `resolve_seed_examples` runs. Web UI: `GenerateRequest`
  gains `examples_text: str | None`; `index.html` gains a paste-many textarea under Advanced options
  (deliberately no new file-upload plumbing -- the CLI already covers a real file path, so the web UI's
  own addition is a paste box through the exact same parser server-side, not multipart upload handling).

  **Phonotactic-mismatch warning** -- new `generation/seed_examples.py::phonotactic_mismatch_warnings
  (language: Language) -> list[str]`, called *after* generation (unlike `strictness_warnings`, a pure
  function of `TraitProfile` computable before generation, this needs the generated `SyllableStructure`,
  which doesn't exist until `generate_language` returns): tokenizes each seed example's own IPA against
  `language.phonology.all_symbols()` and checks `phoneme_fit.first_problem(...)` -- the exact same
  legality check `real_words.py` already reuses for its own deviated words. On a hit, a warning naming
  the gloss/IPA, noting it was kept verbatim anyway -- **never auto-repaired**: repairing would violate
  "the given words must appear verbatim," this feature's own core guarantee, so a mismatch is surfaced,
  not silently fixed, mirroring `strictness_warnings`' own "allowed, never blocked" stance on a
  word-strictness/sound-strictness mismatch. CLI: printed the same way `strictness_warnings` already is,
  right after `generate_evolved_language` returns (needs the result). Web UI: appended onto the existing
  `summary["warnings"]` list alongside `strictness_warnings(traits)` -- one shared channel, no new API
  field. Verified end to end through the actual browser UI (not just unit tests): a bulk-pasted word with
  no explicit IPA resolved through the fake LLM, triggered a real phonotactic-mismatch warning that
  rendered correctly in the page, while an invalid-POS row in the same paste was silently and correctly
  dropped rather than breaking the whole batch.

  Confirmed, empirically, a real gap in `phoneme_fit.first_problem` while designing this pass's own
  tests: a wholly vowelless IPA sequence (no nucleus at all) is **not** flagged as a problem -- the
  function's own per-nucleus loop simply never executes when there are no nuclei, vacuously returning
  "no problem found." Pre-existing, unrelated to this pass's own changes, out of scope to fix here; the
  tests below use a pathological consonant-cluster seed word instead (confirmed illegal across seeds
  1-14), not a vowelless one.

  **Explicitly deferred** (both named directly by the DEFERRED text, each its own independent, open-ended
  sub-feature with no existing mechanism to extend): structural bias derivation (syllable shapes, cluster
  frequency, orthography conventions inferred from the seed words themselves); multi-form/inflected
  grammatical forms on a seed word (the DEFERRED text's own wording hedges on the design -- "could be
  passed in the prompt or as columns" -- rather than specifying one).

  Tests: `tests/test_seed_examples.py` -- a given `pos` is honored, an omitted one still defaults to
  NOUN, a seed entry carries `notes="seed word"`; `parse_bulk_seed_examples` reads all four columns, skips
  an optional header, tolerates missing optional columns, skips a row missing `gloss`/`form` or with a bad
  `pos` without raising, deterministic; a wildly-clustered seed word triggers exactly one warning naming
  it and leaves its `ipa`/`romanization` unchanged, an ordinary one triggers none. `tests/test_cli.py` --
  `_parse_seed_example`'s `gloss=form|ipa|pos`/`gloss=form||pos` forms, rejects an unknown `pos` and a
  missing `=`. `tests/test_webui.py`'s own existing suite re-run clean (54 passed) after the
  `SeedExampleEntry`/`GenerateRequest` changes.

- **Seed words: structural bias derivation (grammar pass 48).** The first of the two items deferred
  from pass 47: today a seed word only forces its own *phonemes* into the inventory, nothing reads its
  own syllable shape to bias the rest of the generated `SyllableStructure`. Picked over the other
  deferred item (multi-form/inflected grammatical forms) for being better-bounded and closer to what the
  original DEFERRED text actually asked for.

  Two research findings made this a clean extension rather than a new mechanism. First, reading
  `_reference_biased_rate`/`_group_reference_bias`/`_reference_clamp` and the `onset_cluster_
  probability`/`coda_weights` code directly (phonology_gen.py, inside the single `generate_phonology`
  function) showed each already computes a real "soft" pull (e.g. `soft_rate = max(base_rate, 0.85) if
  in_reference else base_rate * 0.3`) the moment a profile is present in `weighted_profiles`/`reference_
  weights` -- `source_language_strictness` only adds an *extra* pull on top, and defaults to `0.0`
  whenever there's no *named* source language (the common case for someone giving only seed words). A
  pseudo-profile folded into the existing `weighted_profiles` tuple therefore has a real, immediate
  effect with **no new strictness-like dial needed** -- confirmed empirically, not assumed: a 100-seed
  sweep with 2-consonant-onset seed words (`"stra"`/`"blo"`) gave `max_onset >= 2` 53% of the time vs.
  8% for plain-CV seed words (`"ba"`/`"do"`, vs. a ~54% unbiased baseline) -- plain seed words actively
  *suppress* clusters relative to no seed words at all, exactly the intended "fill in the rest
  consistently with this shape" behavior. Coda presence (91% vs. 62%) and tone-system presence (100% vs.
  7%, using a word with an acute-accent tone mark) showed the same pattern. Second, `ReferenceLanguage
  Profile` has only six required fields (`name`, `consonants`, `vowels`, `coda_profile`, `max_onset`,
  `tonal`) and is exactly the type `generate_phonology` already builds (`WeightedProfiles = tuple[tuple[
  ReferenceLanguageProfile, float], ...]`) -- a pseudo-profile slots in as one more tuple entry with zero
  changes to any of the ~300 lines of consuming code past the point where `weighted_profiles` is
  assembled.

  **`_seed_structural_profile(seed_examples, consonant_pool, vowel_pool, reference_profiles) ->
  tuple[ReferenceLanguageProfile, float] | None`** (new, `phonology_gen.py`, placed right before
  `generate_phonology` itself): for each seed example with resolved IPA, tokenizes against the *same*
  restricted `_seed_tokenizer_pool` `generate_phonology` already uses for its own seed-IPA scanning (not
  the raw global symbol pool -- see the bug this avoided, below), then scans for maximal consonant runs
  between vowel tokens via a small new `_consonant_run_lengths` helper (a plain linear scan, deliberately
  *not* sharing code with `phoneme_fit.first_problem`'s own internal nuclei-finding loop, since that
  function is already tested/stable and this is independent, small duplication rather than a risky
  shared-code change). The longest non-trailing run informs `max_onset`; the trailing run (after the
  last vowel) informs `max_coda`/`coda_profile` (`"none"` only when every word's trailing run is 0,
  `"unrestricted"` otherwise -- the `"sonorant"` middle category is deliberately not inferred, kept
  binary for a first pass); both capped at 2 to match this project's own modeled range. `tonal` is a
  direct substring check for any `TONE_DIACRITICS` mark in the raw IPA. The returned weight is `min(1.0,
  resolved_count / 5)` -- illustrative, not rigorously calibrated (same honesty standard as every other
  hand-set constant in this project), reflecting that a couple of seed words are real but weaker evidence
  than a whole curated real-language profile. `name="seed words"` -- never matched by `match_profiles`/
  the curated registry by design, a synthetic per-generation profile, not a shared one.

  **Call site**: right after `weighted_profiles` is first assigned in `generate_phonology`, before the
  `reference_weights` accumulation loop that follows it -- `consonant_symbol_pool`/`vowel_symbol_pool`
  (previously computed a few lines later) were moved up to be available at this point, the only
  reordering needed; nothing between the old and new positions of those two lines depended on anything
  else. `strictness`/`reference_profiles` themselves are untouched -- `reference_profiles` stays
  name-matched only, so a seed-words-only run keeps `strictness == 0.0` (fine, per the unconditional-pull
  finding above); naming a real source language *too* additionally sharpens the *combined* bias via its
  own strictness dial, a free interaction needing no special-casing.

  **A real bug caught during implementation, not left in**: the first version tokenized each seed word
  against the *raw* global symbol pool rather than the restricted `_seed_tokenizer_pool`, which
  immediately regressed the pass-47-adjacent `test_seed_example_never_lets_an_unrelated_multichar_
  phoneme_swallow_two_adjacent_real_ones` test -- the same "nz" mis-tokenization bug that test already
  guards `must_include_consonants`/`must_include_vowels` against (two adjacent single-character phonemes
  "n"+"z" in a word spelled "anza" were being greedily read as the unrelated global multi-character
  phoneme "nz", which then leaked into the pseudo-profile's own `consonants`, and from there into
  `reference_weights`, giving "nz" a real but spurious selection boost). Fixed by having `_seed_
  structural_profile` take `reference_profiles` and call `_seed_tokenizer_pool` itself, the same
  restricted pool `generate_phonology`'s own existing seed-scanning code already uses -- a concrete
  demonstration of why the "reuse the existing mechanism" framing above wasn't just about writing less
  code, but about not quietly reintroducing a bug that mechanism had already fixed once.

  **`tonal`'s own no-abstain limitation**: unlike every other field read here, `ReferenceLanguageProfile.
  tonal` has no "not curated" default -- it's a required boolean. A seed-word set with no tone-marked
  word therefore mildly *suppresses* tonality (via `_reference_clamp`'s own `min(probability, 0.08)`
  branch when every weighted profile says `tonal=False`), even though "the user didn't mark tone" isn't
  strong evidence the language shouldn't be tonal. Documented as a limitation rather than solved with new
  plumbing (give at least one tone-marked seed word to avoid the pull) -- the same kind of honest,
  simple-heuristic tradeoff this project already accepts elsewhere.

  **Explicitly deferred**: `vowel_harmony` (systematic vowel-feature agreement needs more data than a
  handful of seed words reliably gives); `attested_onset_clusters`/`attested_coda_clusters` (literal
  cluster *identity* -- gated behind `reference_profiles` specifically, i.e. named real profiles only, a
  deeper integration point this pass doesn't touch); `onset_frequency_tiers`/`core_vocabulary_average_
  syllables`; and orthography/romanization bias -- the DEFERRED text's third named target, but confirmed
  via research to need materially new inference logic (diffing spelling against IPA syllable-by-syllable
  to recover a grapheme-to-phoneme convention -- a real alignment problem, not a small addition) plus a
  parallel `extra_weighted_profiles` seam in `romanization_gen.py` (today only takes language-name
  strings, re-deriving profiles internally) -- kept as its own, separate future pass.

  Tests (`tests/test_phonology_realism.py`, the established canonical home for reference-bias claims --
  same `_DIRECTIONAL_SEEDS`/directional-fraction-comparison pattern `test_arabic_source_language_
  increases_pharyngealized_consonant_presence` already uses): `_seed_structural_profile` unit tests (no
  resolved examples -> `None`; cluster/coda/tone read correctly, capped at 2; weight scales with resolved
  count, caps at 1.0 at 5+; the "nz" leak explicitly guarded against); directional tests confirming
  cluster/coda/tone-marked seed words measurably increase the corresponding generated property vs. plain
  seed words; a combined-with-named-source-language smoke test; a carve-out test mirroring `test_full_
  strictness_still_force_includes_a_seed_example_symbol_outside_the_source_language` confirming `must_
  include_*`'s own guarantee is unaffected.

- **Seed words: orthography/spelling-convention bias (grammar pass 49).** The last of the two items
  deferred from pass 48: nothing read a seed word's own *spelling* against its pronunciation to bias the
  rest of the generated romanization scheme -- only sounds and syllable shape were being picked up.
  Confirmed via research the existing reference-profile machinery in `romanization_gen.py` already biases
  spelling choices from a *named* source language's own `ReferenceLanguageProfile.orthography`, through
  the same unconditional-soft-pull shape `phonology_gen.py` already had (`_strict_weight`, romanization_
  gen.py:816 -- a flat 70% per-axis adoption chance the moment *any* profile is present, `strictness` only
  sharpening it further) -- the same "no new dial needed" conclusion both prior seed-word passes reached.

  Two things the research also confirmed, honestly, before any code was written: the plumbing is clean but
  genuinely two-sided -- `generate_romanization` and `_reference_orthography` each independently re-derive
  `weighted_profiles` from `(source_languages, source_language_weights)` by name, so a pseudo-profile
  parameter needs threading through *both* call sites, not one; and, unlike the phoneme-forcing and
  structural-bias passes (each of which slotted an inferred value into a mechanism that already consumed
  exactly that shape), **no reusable spelling-to-sound alignment exists anywhere in this codebase** --
  every existing path (`real_words.py`'s exact copies, its deviated-word re-spelling) either copies a
  real word's spelling verbatim or re-derives one from the language's own already-decided scheme, never
  the reverse. This piece needed genuinely new code.

  **Scope decision, stated plainly up front**: only words where the spelling's own letter count exactly
  equals the IPA's own symbol count are used -- no digraph/silent-letter guessing at all in this first
  pass. A naive greedy length-balancing alignment (distribute extra letters across symbols when counts
  don't match) was considered and rejected, not just deferred for size: it can silently misread an
  intentional digraph (e.g. "aqua" for /akwa/, 4 letters for 4 symbols by coincidence) as independent
  single-letter rules -- "q"->k, "u"->w -- producing an actively *wrong* rule rather than just an
  imprecise one. This project's own standing instinct is "abstain rather than guess wrong" (`seed_
  examples.parse_bulk_seed_examples`'s malformed-row handling already does exactly this), so a word that
  doesn't align 1:1 contributes nothing to orthography at all (it still contributes normally to phoneme
  forcing and the pass-48 structural profile, which don't need spelling).

  **`_seed_orthography_profile(seed_examples, inventory) -> tuple[ReferenceLanguageProfile, float] | None`**
  (new, `romanization_gen.py` -- the consuming module, mirroring where `_seed_structural_profile` was
  placed in `phonology_gen.py` for the same reason; this one runs strictly *after* the inventory exists,
  so it tokenizes seed IPA against `inventory.all_symbols()` directly rather than needing `phonology_gen`'s
  own pre-inventory `_seed_tokenizer_pool` restriction trick). For each seed example with resolved IPA,
  tokenizes via `ipa_tokenizer.symbols_only`; if the lowercased spelling's own character count doesn't
  exactly equal the token count, the word abstains entirely. Otherwise each `(symbol, letter)` pair at the
  same position casts one vote; when words disagree on a symbol's spelling, majority vote wins (ties go to
  whichever letter was seen first -- arbitrary but deterministic, since dict iteration order is insertion
  order). One `RomanizationRule(ipa=symbol, latin=winning_letter)` per voted-on symbol, folded into a
  pseudo profile with the same `min(1.0, n / 5)` weight formula `_seed_structural_profile` already
  established (`n` = words that actually *voted*, not just words with resolved IPA -- an abstained word
  contributes zero evidence and shouldn't inflate confidence). The required-but-irrelevant-here fields
  (`consonants`/`vowels`/`coda_profile`/`max_onset`/`tonal` -- `_reference_orthography` only ever reads
  `.orthography`) get trivial placeholder values, the mirror image of how `_seed_structural_profile`
  already left its own *irrelevant* fields (`orthography` and friends) at their defaults.

  **Plumbing**: `_reference_orthography` and `generate_romanization` both gained an additive, default-
  empty `extra_weighted_profiles: tuple[tuple[ReferenceLanguageProfile, float], ...] = ()` parameter --
  `generate_romanization` appends it to its own locally-computed `weighted_profiles` *and* threads it into
  the `_reference_orthography(...)` call, covering both of the two independent re-derivations the research
  flagged (easy to fix only one and silently leave the other blind to the pseudo-profile). `evolve_
  romanization` deliberately untouched this pass -- confirmed it already doesn't consult `weighted_
  profiles` for whole-scheme category, only narrower per-symbol fresh-rule generation during a reform
  event, a smaller, separate, lower-value extension.

  **Call site** (`generator.py`, right after `generate_phonology` returns, since this needs the real
  `inventory`): built from `phonology_spec.seed_examples` -- the combined user-given *and* exact-copy-
  real-word set `generate_phonology` already uses, so a real curated word's own real spelling (at word
  strictness 1.0) is, if anything, *better* alignment evidence than a made-up one, a free synergy with no
  extra code.

  Verified concretely, not just reasoned about: a seed-word pair consistently spelling /ʃ/ as "x" raised
  that spelling's adoption rate from 39% (no seed words) to 80% across a 60-seed sweep, with /ʃ/ also
  forced into every one of those 60 generated inventories via the pre-existing phoneme-forcing mechanism
  (vs. only 23/60 naturally, without seed words) -- the structural and orthographic mechanisms visibly
  compounding, as intended.

  **Explicitly deferred**: digraph/multi-letter grapheme inference (the scope decision above, not a size
  cut); `syllable_boundary_marker`/`orthography_category`/`capitalized_pos`-style *coarse* convention
  inference, distinct from per-phoneme spelling rules; wiring into `evolve_romanization`.

  Tests (`tests/test_romanization_gen.py`, reusing `_first_rule_fraction`'s established synthetic-profile
  shape but **without its monkeypatch** -- a seed-derived profile is never registered by name, so passing
  it straight through the new `extra_weighted_profiles` parameter is both possible and cleaner, the
  research's own explicit recommendation): `_seed_orthography_profile` unit tests (no resolved examples ->
  `None`; a length-matched word infers the expected rules; a length-mismatched word contributes nothing
  without blocking other words; disagreement resolved by majority vote; weight caps at 1.0 at 5+ words); a
  directional test mirroring `test_dutch_source_language_biases_romanization_toward_dutch_spelling`'s own
  shape; a direct `extra_weighted_profiles` plumbing test confirming a hand-built profile's rule actually
  surfaces in the generated scheme.

- **Seed words: multi-form/inflected grammatical forms (grammar pass 50).** The last remaining item from
  the original "Generation from the user's own words" entry: letting a user give their own word's own
  irregular (suppletive) form for one grammatical cell -- e.g. "my word for 'walk' is 'zim', but its own
  past tense is irregularly 'zanu'" -- used verbatim, the same guarantee the base seed word already has.
  Research confirmed this is generalizable but not a small patch -- three real, independent obstacles:

  1. **Storage/render was already the right shape, just needed pre-creating instead of lazy-coining.**
     The existing suppletion mechanism (`voice_np_gen.py`, used for hardcoded irregular English plurals/
     past tense/comparative-superlative) stores nothing extra on `LexicalEntry` at all -- a suppletive
     form is an ordinary `LexicalEntry` whose `glosses` tuple contains a synthetic key,
     `voice_np_gen.suppletive_gloss(base, kind)` (`f"{base}-{kind}"`), found by `translator._lookup_or_
     coin`'s plain `by_gloss`-style lookup (`_find_word`) with **zero new render-side code**: render-time
     recognition that a slot needs that lookup (`_suppletive_form_kind`/`_suppletive_case`, and the inline
     verb-past check) is already driven purely by membership in `grammar.suppletive_plurals`/
     `suppletive_degrees`/`suppletive_past` (plain tuples). So: pre-create the right `LexicalEntry` at
     generation time -- the user already supplies spelling and can supply IPA, unlike the hardcoded path,
     which coins lazily at first translation -- and fold the lemma into those same three grammar tuples;
     rendering then needs no new logic at all.
  2. **Decode's recognition was gated on fixed hardcoded dicts.** `suppletive_split(gloss)` only
     recognized a synthetic gloss as suppletive when its base was a *key in the module-level*
     `IRREGULAR_PLURALS`/`IRREGULAR_PASTS`/`SUPPLETIVE_DEGREES` dicts -- deliberately, since that's exactly
     how it avoids misparsing `"you-plural"` (a pronoun gloss) as suppletion. Fixed by giving
     `suppletive_split` (and `translator._class_gloss`, which calls it for noun-class assignment) an
     optional `grammar` parameter: a lemma also counts as known when it's in `grammar.suppletive_plurals`/
     `_degrees`/`_past` -- additive, defaults to `None`, every existing direct unit test and call site
     (3 for `_class_gloss`, 5 decode sites in `translate_to_english`) stayed byte-identical and just needed
     threading `language.grammar`/`grammar` through.
  3. **Cell-naming is genuinely inconsistent/overlapping across word classes** -- no single enumeration
     exists (`cases`/`tenses`/`aspects`/`moods`/`voices` are separate per-POS `Grammar` tuples, degree is
     hardcoded wherever it appears). Scoped down to exactly the four cells the existing suppletion
     mechanism already models -- `voice_np_gen.SUPPLETIVE_SUFFIXES = ("plural", "comparative",
     "superlative", "past")` -- each tied to one POS (plural/noun, past/verb, comparative+superlative/
     adjective). No new cell vocabulary invented; a cell not matching its own word's POS is rejected, not
     guessed (a hard CLI error for `--example`, a lenient drop for bulk/web input).

  **New types and builders**: `SeedForm(cell, form, ipa=None)` (`core/spec.py`), `SeedExample.forms:
  tuple[SeedForm, ...] = ()`. `generation/seed_examples.py` gained `CELL_POS` (the fixed cell->POS map),
  `parse_seed_forms` (the shared `;`-separated `cell:form[:ipa]` syntax parser, no POS validation),
  `valid_forms` (filters to cells matching the parent example's own POS), `seed_suppletive_entries` (one
  `LexicalEntry` per valid form, `glosses=(voice_np_gen.suppletive_gloss(base, cell),)`), and
  `seed_suppletive_lemmas(seed_examples, cell)` (the lowercased base glosses to fold into a grammar
  tuple). `resolve_seed_examples` was refactored (extracted `_guess_ipa`) to resolve a form's own missing
  IPA independently of whether the base word's IPA was already given -- the original early-return-when-
  base-ipa-is-set would otherwise have silently skipped resolving any forms.

  **Generation (`generator.py`)**: three small, additive insertions, no existing line changed --
  `seed_entries` extended with `seed_examples.seed_suppletive_entries(...)`; right after `grammar.
  suppletive_plurals`/`suppletive_degrees` are set from the existing `voice_np_gen.roll_followups` result,
  a further `model_copy` merges in `seed_suppletive_lemmas(..., "plural")`/`"comparative"`/`"superlative"`
  (deduped across the latter two, since `suppletive_degrees` doesn't distinguish which of the two a lemma
  has); the same merge for `"past"` right after `grammar.suppletive_past` is set from `np_followups_gen.
  roll_round_three`.

  **CLI/bulk/web**: `--example` gained a 4th pipe segment (`gloss=form|ipa|pos|forms`), switching
  `_parse_seed_example` from two chained `.partition("|")` calls to `rest.split("|", 3)`; a cell/POS
  mismatch is a hard `typer.Exit` (an explicit, scriptable flag should fail loudly on a typo). Bulk CSV
  gained a 5th column, same syntax; a mismatch there is dropped leniently (the base word kept), matching
  this function's own existing "skip the bad bit, keep going" convention for batch input. The web UI's
  `SeedExampleEntry` gained a `forms: str | None` field, converted the same lenient way as bulk, plus one
  more per-row text input and an updated bulk-paste label in `index.html`.

  **Known, documented quirks, not fixed this pass**: giving only one of comparative/superlative still
  marks the lemma suppletive for *both* cells (since `suppletive_degrees` doesn't distinguish which), so
  the ungiven cell falls through to `_lookup_or_coin`'s ordinary coining path -- a freshly invented,
  unrelated irregular word, not the regular affixed form; fixing it would need splitting `suppletive_
  degrees` into two tuples, a bigger change than this pass's scope. `suppletive_reading`'s comparative/
  superlative fallback for a base outside the hardcoded dict (`"more {base}"`/`"most {base}"`) was
  previously dead code (only "good"/"bad" ever reached `grammar.suppletive_degrees` before this pass) --
  now live for any seeded adjective, producing grammatically crude but informative decode text ("more
  big") rather than a properly inflected one ("bigger"). A rendered suppletive form can still take
  regular, non-tense marking (subject agreement, etc.) on top of the user's own stem -- confirmed by
  testing and by a manual CLI round trip (seeded past "zanu" for "walk" rendered as "zanun" with a 3rd-
  person suffix, decoded back as "he walked") -- the same behavior the pre-existing hardcoded mechanism
  already has, not a new limitation.

  **Explicitly out of scope this pass** (both picked up and closed by pass 51 immediately below):
  pronoun-case suppletion from seed words; verb-form suppletion beyond plain past tense.

- **Seed words: pronoun-case and verb-tense suppletion (grammar pass 51).** Direct follow-up closing both
  items pass 50 left out of scope. A dedicated Explore agent confirmed neither hits a structural wall --
  both are clean, bounded generalizations of the pass-50 architecture, not a new mechanism.

  **Verb-tense suppletion beyond past**: `grammar.tenses` (`core/grammar.py:306`) is set *once*, entirely
  inside `grammar_gen.generate_grammar` (the very first grammar-building call in `generator.py`), and
  never added to afterward -- exactly one of two fixed sets, `("past","non_past")` or
  `("past","present","future")`. `voice_np_gen.SUPPLETIVE_SUFFIXES` grew from 4 labels to 7 (adding
  `non_past`/`present`/`future`); the previous if/elif chain in `suppletive_split`/`suppletive_reading`
  was replaced with two small dicts (`_GRAMMAR_FIELD_BY_KIND`, `_KNOWN_DICT_BY_KIND`) and a new
  `suppletive_field(kind)` helper, cleaner than a growing elif chain at 7 kinds and shared by generation,
  decode, and render. `suppletive_reading` gained crude but honest fallbacks for the 3 new labels (bare
  gloss for `non_past`/`present`, `"will {gloss}"` for `future`) -- there's no real English-irregular
  concept for a tense label the way there is for a plural/past/degree, so these three fields are *only*
  ever populated by a seeded lemma, never a hardcoded dict. `translator.py`'s render check
  (`tense_in == "past" and ... in grammar.suppletive_past`) widened to `tense_in in voice_np_gen.
  TENSE_SUFFIXES and ... in getattr(grammar, voice_np_gen.suppletive_field(tense_in))` -- byte-identical
  for `"past"` by construction (`suppletive_field("past") == "suppletive_past"`), free for the other 3.
  Decode's matching `== "past"` filter widened to `in TENSE_SUFFIXES`, using the matched label instead of
  the literal string -- the existing downstream tense-reading pipeline already renders present/future/
  non_past correctly for an *ordinary* verb, confirmed genuinely free, no new reading logic needed there.
  Generation-time merge for the 3 new fields sits right after `grammar = grammar_gen.generate_grammar(...)`
  (not alongside the existing `suppletive_past` merge, which stays where it is) -- `grammar.tenses` is
  already final there, and unlike `past` these 3 fields have no existing hardcoded-roll result to merge
  into, so their first assignment IS the seed-derived one, filtered to `cell in grammar.tenses`.

  **Pronoun-case suppletion**: `generation/pronoun_gen.py`'s own, separate, pre-existing suppletion
  mechanism (I/me) needed **zero changes** -- `suppletive_gloss`/`suppletive_split`/`suppletive_reading`
  already produce/recognize exactly the `f"{person}-{case}"` shape a pre-created seed entry needs, and
  recognition doesn't depend on `grammar` (works off the fixed `CASE_NAMES` superset, same as the existing
  hardcoded-roll path already does). Confirmed separately: seeding a pronoun's own citation word (e.g.
  `gloss="I", pos=PRONOUN`) already worked with **zero changes needed** even before this pass -- the
  existing `seeded_glosses` dedup in the core-meanings loop already skips coining any seeded gloss, so a
  seeded "I"/"you"/"he"/"we" entry just replaces the algorithmically-coined one with no conflict. The real
  gap was only the *case* form. `seed_examples.CELL_POS` gained the 5 legally-suppletible cases
  (`CASE_NAMES` minus `nominative`/`absolutive`, which `translator._suppletive_case` never allows)
  mapped to `PRONOUN`; `valid_forms` gained one more condition, only for `PRONOUN`: the word's own gloss
  must itself be a recognized personal pronoun (`pronoun_gen.person_label(gloss) is not None`) -- a
  pronoun-case form on an arbitrary noun gloss makes no sense. `seed_suppletive_entries` needed no change
  at all for this -- `voice_np_gen.suppletive_gloss(base, cell)` already produces the byte-identical
  `f"{base}-{cell}"` string `pronoun_gen.suppletive_gloss` would (confirmed: the latter just additionally
  lowercases internally, and `base` is already lowercased here), so reusing it across both mechanisms is
  safe without a dispatcher.

  **The merge is the real new code** (`generator.py`, right after `grammar.cases` becomes final -- the
  `np3` block, confirmed the *last* of only two places that ever append to `cases`): a seeded person only
  becomes suppletive for a case that's actually live in *this* generated language (a case seeded for a
  language without it is caught by the warning below instead, never folded in). The case-limits merge
  has three distinct branches, each deliberately reasoned: a person already *restricted* to a case subset
  gets that subset *widened* to include the seeded case, without disturbing the rest; a person *newly*
  made suppletive by seeding gets *restricted* to just the seeded case(s) (so an unseeded case of that
  same person still takes the ordinary case suffix, rather than silently becoming "suppletive" with no
  pre-created word of its own -- the same "only one cell given" shape pass 50's own comparative/
  superlative quirk already has); a person *already unrestricted* (suppletive in every case) is left
  alone -- narrowing it here would take away pre-existing, unseeded suppletive behavior.

  **A new warning, shared by both halves**: `seed_examples.unused_suppletive_form_warnings` -- whether a
  pronoun case or extra tense is actually live can't be known until generation completes (unlike a cell/
  POS mismatch, caught immediately at CLI parse time), so, mirroring `phonotactic_mismatch_warnings`'s own
  stance, the `LexicalEntry` is still created (harmless) and the gap is only surfaced, never silently
  dropped. Wired into the CLI's existing warning-echo and the web UI's `summary["warnings"]` alongside the
  other two warning sources.

  **Known, documented quirk**: person-label granularity is coarser than literal gloss -- seeding "she"'s
  accusative makes person "he" suppletive too (since "she"/"he"/"it"/"they" all share agreement person
  label "he"), so a *separate*, unseeded "he" entry for that same case falls through to ordinary coining,
  not a crash, not silently wrong, just a fresh unrelated word -- same flavor as pass 50's own
  comparative/superlative quirk, not fixed, documented.

  Verified concretely: a seed with no periphrastic future and a live accusative case + future tense
  (found by inspecting a handful of generated `grammar.yaml`s' own `periphrastic_labels`/`cases`/`tenses`
  fields directly, since the fake planner has no "will"/future recognition at all, confirmed by grep --
  `--llm fake` genuinely cannot demonstrate future-tense suppletion through a typed English sentence) --
  "He saw me." renders with the seeded "zum" verbatim for accusative "I" and decodes back as "he me saw";
  the seeded future-tense lexicon entry and `grammar.suppletive_future`/`suppletive_pronoun_case_limits`
  fields were confirmed directly in the saved files rather than through a sentence round trip for the
  tense half, documented as such in `docs/CLI.md` rather than presented as a working free-text example.

  This closes the "Generation from the user's own words" `docs/DEFERRED.md` entry entirely.

- **Punctuation (grammar pass 52).** `docs/DEFERRED.md`'s "## 3. Translation" section: punctuation
  disappeared in translation entirely -- no mark rendered, ever, for any mood, and a declarative got no
  terminal mark at all even on decode. A dedicated Explore agent confirmed the exact state first: `sentence_
  planner.split_sentences` already keeps a sentence's own terminal mark (its own docstring: "the planner's
  cue for mood"), and `SentencePlan.mood` (`declarative`/`imperative`/`question`/`wh_question`) was already
  set correctly end to end by both the fake planner and the real-LLM JSON response -- the one missing piece
  was *using* it to render/recognize an actual character.

  **Scope decision: no new `exclamatory` plan field.** The fake planner's own existing imperative detection
  already requires a trailing `"!"` *and* a command-shaped sentence (no subject) -- a plain exclamatory
  statement ("I love it!") already silently fell through to declarative before this pass, and still does
  after it. Adding a flag genuinely independent of `mood` would have meant threading it through every one
  of `fake_client.py`'s ~14 `{"mood": ..., "slots": ...}` plan-dict construction sites (recursive sentence
  shapes -- topic-fronting, "the more X the more Y", etc. -- that copy `main_plan["mood"]` forward) for a
  marginal gain, since `"!"` is already fully consumed by the imperative heuristic. Piggybacking the mark
  on `mood` alone keeps render and decode perfectly symmetric (decode seeing a bare `"!"` can only ever mean
  `mood == "imperative"`, by construction) -- the honest, bounded scope, documented in `docs/LIMITATIONS.md`.

  **New `PunctuationStyle` enum** (`core/romanization.py`, alongside `ExoticSymbolStyle`): `STANDARD`
  (period/question mark/exclamation mark) and `NONE` (this language's own writing convention doesn't mark
  sentence type at all -- illustrative, not a survey of every real convention). `RomanizationScheme` gains
  `punctuation_style: PunctuationStyle = PunctuationStyle.STANDARD`. A new `terminal_mark(mood, style) ->
  str` sits beside `apply_grammatical_spelling` -- the same "a second function with context `apply()`
  itself doesn't have" shape (a whole sentence's mood, not one IPA string). Not tied to any named
  `OrthographyCategory` (no curated profile distinguishes real languages by this; every real language with
  a writing system marks sentence type *somehow*, so this stays a flat, non-profile-biased roll, the same
  honesty standard `word_accent_marking`'s own "not yet exercised" fields already set). **Rolled from its
  own independent rng stream in `generator.py`** (`random.Random(f"{spec.seed}:punctuation")`,
  `romanization_gen._roll_punctuation_style`), overriding the field on the already-built `RomanizationScheme`
  right after `generate_romanization` returns -- *not* drawn from the shared `rng` inside `generate_
  romanization` itself, even though that function already consumes the shared stream for several other
  fields. A first attempt did add it as the shared stream's own last draw there (reasoning it was "safe"
  since it came after every other draw *in that one function*) -- that still shifts the position of every
  draw `generator.py` makes *after* `generate_romanization` returns (grammar, lexicon, ...), which broke
  dozens of tests across both translation and pure-generation files (confirmed concretely: a declension
  test with no translation call at all broke too, proving the shift wasn't a punctuation-specific effect).
  Switching to an independent stream is this project's own established fix for exactly this situation (every
  other follow-up pass in `generator.py` already rolls its own new fields this way) -- it makes the whole
  feature's own new roll invisible to every existing seed's grammar/lexicon/translation output, and needed
  zero test-fixture seed updates once applied, unlike the first attempt.

  **Render** (`translator.py::translate_to_conlang`): `terminal_mark(plan.mood, working_language.
  romanization.punctuation_style)` appended to each sentence's own *romanization* string only, never its
  IPA (a phonetic transcription isn't a writing-system fact) -- no change to `_render_plan` itself (a
  per-slot concern) or to the existing bare-space multi-sentence join, since each sentence string now
  already carries its own mark.

  **Decode** (`translator.py`): two layers, no restructuring of the existing few-hundred-line per-token
  loop. (1) **`_normalize`** (NFC-fold + lowercase, used at essentially every surface-token comparison site
  in this file, ~28 call sites) now also strips a trailing `.`/`!`/`?` -- safe everywhere, since a freshly-
  *generated* candidate spelling never has one (a no-op there) and only an *observed* token, exactly when
  it happens to be the last word of its sentence, ever does. Centralizing the strip here, rather than only
  in `translate_to_english`'s own top-level preprocessing, was the fix for a second wave of failures this
  pass's own test-impact check didn't predict: several test files call `_decode_noun`/`_decode_verb_full`/
  `_decode_adjective_full` *directly* on a single extracted token, bypassing `translate_to_english`
  entirely -- those functions' own `_normalize(token)` call is their first line, so fixing it there fixes
  every direct caller at once, including ones no single file-level patch would have reached. (2)
  `translate_to_english` itself still separately strips `raw_tokens` up front (needed for `Lexicon.by_form`,
  which does its own inline NFC+lower and was never routed through `_normalize`) and records whether a
  `?`/`!` appeared *anywhere* in the raw tokens as a new, additional whole-input signal, OR'd into the
  existing particle-based `is_question`/`is_imperative` -- meaningful even for a language with no question
  particle, which previously had no way to decode a question at all. The final fallback text now always
  gets a terminal mark (previously a declarative got none at all) -- **deliberately still lowercase, no
  capitalization**: an early version of this pass capitalized it too, which broke far more tests than the
  mark itself (every bare `"word" in english_text` substring check this codebase already had, with no
  `.lower()` of its own, since that was always safe before); capitalization is cheaply the real fluency
  LLM's own job already ("write a natural English sentence"), so it was dropped rather than chasing down
  every affected assertion. Deliberately **not done**: re-splitting the decode input per sentence and
  looping the whole per-token machinery per chunk -- confirmed a materially bigger, riskier change than
  fixing the punctuation gap itself needed; a multi-sentence decode input still reports one whole-input
  question/imperative signal, the exact same granularity the pre-existing particle-only detection already
  had. The fluency system prompt gained one sentence noting the gloss sequence may represent more than one
  original sentence with no marker between them, and to write each as its own correctly punctuated English
  sentence.

  **Test-impact check, done before committing to the design, not after -- and still an undercount in
  practice**: `translate_to_conlang` is called from 133 sites across 32 test files. Sampling confirmed the
  dominant pattern (`result.text.split()` then `words[0]`/`len(words)`/relative comparisons) is unaffected
  by a mark landing on the *last* word, and zero tests assert a literal full-string match -- correctly
  predicting the one `test_translator.py` hit that needed `.rstrip(".")`. What the sample didn't surface,
  only running the suite did: (a) a first attempt rolled `punctuation_style` from the shared `rng` inside
  `generate_romanization`, which shifted every downstream draw for every existing seed and broke dozens of
  tests across both translation and pure-generation files -- resolved by moving the roll to its own
  independent stream (see above), which needed zero fixture-seed updates once applied, confirming the
  shared-stream version really was the cause, not some other interaction; (b) a first attempt at
  capitalizing the fallback text broke roughly 20 more tests across half a dozen files, resolved by
  dropping capitalization entirely rather than fixing each one (see above); (c) several test files extract
  a single token from a full sentence's own rendering and feed it straight to a lower-level decode
  function, which a mark landing on a sentence-*final* word broke in a way the top-level `translate_to_
  english` fix alone didn't reach -- resolved by the `_normalize` centralization above. The lesson carried
  into this entry on purpose: a static test-impact estimate from sampling call sites is a floor, not a
  ceiling -- running the affected files for real is still what actually closes a pass like this one, and a
  new roll touching a widely-shared `rng` object is worth questioning before it's added, not just after.

  **Explicitly deferred**: quotation marks (direct speech isn't modeled at all -- confirmed `quotative_
  particle`'s own docstring is reported/indirect speech only, a genuinely different, unmodeled construction);
  comma placement (needs clause/list-boundary rules this project doesn't have); the `exclamatory`-independent-
  of-`mood` idea above; per-sentence decode granularity above -- each its own bigger, separate piece of work,
  not a continuation of this pass's own scope.

- **Coined words ignore word strictness (grammar pass 53).** `docs/DEFERRED.md`'s "## 3. Translation"
  section: on-the-fly coinage (`translation/expansion.py::coin_word`, invoked when translation meets an
  English word with no existing lexicon entry) never consulted word strictness at all, always inventing.
  An earlier pass already built word strictness entirely at *generation* time (`generation/real_words.py`):
  each core-vocabulary gloss gets a chance of following a real word from a matched source language
  (curated, else one LLM-filled gap batched up to 100 glosses per call), with graded deviation below
  strictness 1.0 via a systematic per-language sound-shift table (`phoneme_fit.build_deviation_shift`/
  `apply_shift`).

  **Two things research confirmed before any code was written, not assumed**: (1) the deviation shift
  table is a *local variable* inside `build_real_entries`, discarded once generation finishes -- but it
  depends only on already-persisted data (`spec.seed`, `spec.traits.source_word_strictness`, `language.
  phonology`), so translation-time code can rebuild the *exact* same table for an unevolved language, or a
  correctly-adapted one for an evolved one -- no schema change, just a shared helper so the two call sites
  can't drift. (2) The curated lexicon (`reference_languages/real_lexicon`) is keyed by exactly `generation.
  lexicon_gen.ALL_MEANINGS`'s own fixed gloss list (496 entries) -- and this surfaced a sharper finding than
  "on-the-fly coinage sometimes gets a curated hit": **every one of those 496 glosses is, by construction,
  already in the lexicon by the time translation runs** (real or invented, decided at generation time), so
  `coin_word` is *never* reached for any of them *unless* `--vocabulary-size` (default 400) left that gloss
  out of the generated vocabulary in the first place. Confirmed concretely: at the default vocabulary size,
  96 of the 496 core meanings (e.g. "king", "door", "soup") are excluded, and several of those are curated
  for real languages -- this on-the-fly path exists specifically for that gap, not as a general safety net
  that happens to fire "often enough."

  **Two shared helpers extracted from `build_real_entries`** (same file): `deviation_shift_table(seed,
  strictness, inventory)` (the table-building line, verbatim) and `_build_real_entry(choice, shift,
  strictness, ..., allow_exact_copy)` (the per-choice loop body, verbatim, plus one new parameter).
  `build_real_entries` itself becomes a two-line wrapper (`shift = deviation_shift_table(...)`; map
  `_build_real_entry(..., allow_exact_copy=True)` over `choices`) -- byte-identical output, confirmed by
  construction since the extracted code is unchanged. `allow_exact_copy` is the one genuinely new piece of
  reasoning: at generation time, strictness `>=1.0` alone is enough to take the forced-verbatim-spelling
  branch, safe only because `phonology_gen` already force-included the real word's own phonemes into the
  inventory *before* this runs. On-the-fly coinage can't do that -- the inventory is already fixed by the
  time translation runs, so `allow_exact_copy=False` always routes through `apply_shift` (which nearest-
  neighbor-fits any phoneme outside the inventory regardless of the shift table's own contents) and always
  re-romanizes, even at strictness 1.0. It can still *end up* looking exact when the word's own sounds
  already fit and survive an empty shift table (strictness 1.0 -> shift rate 0) -- the same "exact can also
  happen organically" branch generation time already has, just never forced. Verified directly: a
  synthetic `RealChoice` with ipa `"sa"` against a 3-consonant (`p`/`t`/`m`) minimal inventory --
  `allow_exact_copy=True` keeps `"sa"` byte-identical (the "s" the inventory doesn't have, untouched);
  `allow_exact_copy=False` fits it to `"ta"`.

  **New `coin_real_word(language, gloss, pos, llm_client) -> LexicalEntry | None`** (`real_words.py`): a
  deterministic per-gloss roll (`random.Random(f"{language.spec.seed}:real-word-coinage:{gloss.lower()}")`
  -- its own independent, derived seed, not the shared generation-time stream, so this has zero effect on
  any existing seed's generated output; it only ever fires reactively during translation) against
  `source_word_strictness`; tries the curated lexicon (a new `_curated_word` helper tries the gloss exactly
  as given *and* lowercased, since the curated lexicon's own keys aren't uniformly cased -- the pronoun
  gloss `"I"` keeps its real capitalization, found only after an initial lowercase-only lookup silently
  missed it); else one single-gloss `real_words_llm.fetch_real_words` call (confirmed API-shape-compatible
  with a 1-item list, no changes needed to that function); `None` (falling back to ordinary invented
  coinage) when neither produces anything. Templatic languages/POS are excluded immediately (`language.
  grammar.uses_root_and_pattern and pos in root_pattern.TEMPLATIC_POS`) -- adapting a borrowed word into an
  existing template is a different problem, left open.

  **Wiring** (`translation/expansion.py::coin_word`): one check at the very top -- `real_entry = real_words.
  coin_real_word(...); if real_entry is not None: return real_entry` -- before the existing templatic/
  ordinary branch. No change to `_lookup_or_coin`'s 11 call sites or signature; `language` already carries
  everything the new function needs.

  **Cost, confirmed bounded, not open-ended**: the real-word attempt and `word_selection="llm"`'s own
  candidate-selection call are mutually exclusive for the same word (a successful real-word coinage returns
  immediately, before `coin_word`'s own invented-candidate path -- the only path that call belongs to --
  is ever reached), so the worst case stays "at most one extra LLM call for this one coined word," the same
  order of magnitude coinage can already cost today. Verified directly: translating a sentence needing one
  real-word-eligible coinage, with `word_selection="llm"` *also* active, costs exactly 2 calls total
  (sentence planning + the real-word gap-fill) -- never a 3rd for candidate selection.

  **Explicitly deferred**: root-and-pattern languages (above); any new collision-avoidance for a real-word-
  based spelling that happens to match an existing entry (generation time's own `build_real_entries` has no
  such guard either).

- **Raw IPA leaking into romanization: identity-rule bug + an evolution interaction (bug fix, not a
  numbered grammar pass).** A user reported two linked symptoms from a saved language ("French evolved
  forward 1000 years with influence from Chinese," `conlangs/futurefrenchchinese/`): (1) romanized words
  containing visibly non-Latin characters (`ʦ`, bare `ɔ`, `ø`, `ɛ̃`, `ʨ`); (2) specifically, a word stored
  as IPA `bɔ̃` ("bon") romanizing as `bɔ` -- the nasalization mark gone from the *spelling* while `entry.ipa`
  still correctly held it. Diagnosed by reproducing generation + evolution directly from the saved file's
  own `meta.yaml` traits, rather than reasoning about the code in the abstract -- confirmed useful, since an
  earlier pass's own first hypothesis for (2) (a lossy-tokenization coverage gap in evolution's inventory
  rebuild, written up in `docs/DEFERRED.md` before this investigation) turned out to be wrong: direct
  inspection of the saved `romanization.yaml` showed an *existing* rule for `ɔ̃` (`latin: ɔ`), not a missing
  one.

  **Root cause of (1)**: `generation/romanization_gen.py`'s `_DIACRITIC_TABLE` is mostly principled --
  `ts`/`tɕ` map to the real, historically-attested IPA ligatures `ʦ`/`ʨ` (not invented), and most
  "identity" entries (`pʰ`, `tˤ`, `bʱ`, `ø`, ...) are legitimate because the symbol
  really is a letter some real orthography/transliteration tradition uses as-is. But the table already gives
  *plain* `ɛ`/`ɔ` a real substitution (`ë`/`ö` -- reused correctly by the diphthong entries `ɛi`->`ëi`/
  `ɔi`->`öi`), and the *nasalized* forms `ɛ̃`/`ɔ̃` inconsistently ignored that and fell back to raw-IPA
  identity instead -- genuinely different from the real a/e/i/o/u-based `ã`/`ẽ`/`ĩ`/`õ`/`ũ` entries right
  next to them, which *are* built on real Latin letters. The same copy-paste-style inconsistency had spread
  to three long-vowel entries too (`ɛː`->`ɛ̄`, `ɔː`->`ɔ̄`, `ɯː`->`ɯ̄`, `ɨː`->`ɨ̄`), each wrongly reusing `ø`ː's
  own "no precomposed letter exists" comment on a base vowel that, unlike `ø`, *does* have one. Fixed by
  composing each derived entry onto the table's own already-chosen base-letter substitution instead of raw
  IPA: `ɛ̃`->`ë̃`, `ɔ̃`->`ö̃`, `ɛː`->`ë̄`, `ɔː`->`ȫ`, `ɯː`->`ı̄` (reusing `ɯ`'s own real Turkish dotless-ı),
  `ɨː`->`ï̄` (reusing `ɨ`'s own `ï`). Checked, and deliberately left alone: `ɤ`/`ɤː` (no established
  alternate substitution anywhere in the table to reuse -- a genuinely different situation, not the same
  bug) and `ɑː` (`ɑ`'s own Unicode name is "LATIN SMALL LETTER ALPHA" -- already a real Latin letter, unlike
  `ɛ`/`ɔ`/`ɯ`/`ɨ`). Note that Unicode's own character *naming* is not a usable test for "is this a real
  letter" here -- `ɛ`/`ɔ`/`ɯ`/`ɨ`/`ɤ` are *all* named "LATIN SMALL LETTER ..." by Unicode despite none of
  them being part of any real orthography's letter repertoire (the IPA chart deliberately reuses the Latin
  Unicode block); the actual criterion applied throughout this table, correctly, is "does a real writing
  system use this glyph," a linguistic judgment call, not a Unicode-property check. **The `ts`/`tɕ` ligature
  spelling itself was reconsidered right after this pass, on user feedback**: "real IPA ligature, not
  invented" turned out not to be a strong enough defense, since none of these four characters is actually
  used in any real orthography either -- re-flagged as a genuine open shortcoming in `docs/DEFERRED.md`
  rather than a settled stylistic choice (not fixed in this pass; see that entry for the candidate fix).

  **Root cause of (2), and why fixing (1) fixes it for free**: `romanization_gen.py::_apply_orthography_
  drift` -- the real mechanism behind spelling simplification over evolution time ("café" -> "cafe") --
  NFD-decomposes a grapheme and independently drops each of its combining marks. It has no way to tell a
  genuine diacritic on a genuine Latin letter apart from a nasalization mark baked into a raw-IPA identity
  rule: before the fix, `ɔ̃`'s own `latin` value *was* `ɔ̃` (literally the IPA string, decomposing under NFD
  to `ɔ` + a combining tilde U+0303), so drift could -- and, for this user's seed, did -- strip the tilde
  and leave the bare non-Latin `ɔ` behind as the word's own "simplified" romanization. Fixing (1) means the
  *same* drift mechanism, applied to the *same* rule, can only ever land on `ö̃`, `ö`, `õ`-shaped-on-the-same-
  base, or `o` -- every possible outcome (all four were enumerated and confirmed in a test, not assumed) is
  a real Latin letter. Verified end to end by regenerating and evolving the user's own prompt/traits with
  the fix applied: the evolved `ɔ̃` rule now reads `latin: o`, and the word renders as `bo`, not `bɔ`.

  **Tests**: `test_nasalized_and_long_vowel_spellings_build_on_the_already_chosen_base_letter` pins the six
  changed entries plus the two deliberately-unchanged ones (`ɤː`, `ɑː`) directly; `test_evolution_cannot_
  drift_a_nasalized_vowel_rule_down_to_raw_ipa` exhaustively enumerates `_apply_orthography_drift`'s own
  possible outputs for the `ɔ̃` rule across a seed/rate sweep and asserts none is `ɔ`/`ɔ̃` (the actual
  regression this bug caused). No other test pinned the old values (checked directly -- the one Thai RTGS
  test touching `ɛ`/`ɛː` equality uses a *curated* real-profile override at strictness 1.0, which takes
  precedence over this fallback table regardless of its contents).

- **Hover/click gloss in the translation result (web app pass, not a numbered grammar pass).**
  `docs/DEFERRED.md`'s "## 2. Web app" section: show what every rendered word means on hover/click, and
  tell coined/real-word-based words apart from ordinary ones -- a user reported this was genuinely hard to
  do otherwise.

  **The mechanism was already half-built.** `translation/translator.py::_render_plan` already built a
  `gloss_parts: list[str | None]` parallel to `romanization_parts`/`ipa_parts` -- one entry per rendered
  surface word, via `entry.primary_gloss` at every append/extend site -- but it was only ever consumed by
  `tone_sandhi.apply_sandhi(ipa_parts, tone_system, gloss_parts)` and then discarded; `TranslationResult`
  never received it. Confirmed by an Explore agent tracing every one of `_render_plan`'s own append/extend
  sites: a real `LexicalEntry` is already in scope at every one of them except four bare grammar-profile
  particles with no lexicon entry at all (topic, quotative, possessive, question particles) -- these
  already produced `gloss_parts=None` and simply stay `entries=None` too, no new lookups needed anywhere.

  **New `TokenGloss` dataclass** (`translator.py`, right above `TranslationResult`): `surface` (this word's
  own rendered romanization, *including* a sentence-final punctuation mark when it's the sentence's last
  word -- deliberately baked in here rather than left for a consumer to re-derive by splitting `text`, so
  `[t.surface for t in result.tokens] == result.text.split()` holds by construction), `ipa` (post-sandhi,
  matching `result.ipa` exactly), `gloss`/`pos`/`real_word`/`notes` (straight off the resolved
  `LexicalEntry`, `None`/`""` for a bare particle), `coined` (`entry in coined` -- newly coined *this
  call*, not "new to the language in general"). `TranslationResult` gained `tokens: tuple[TokenGloss,
  ...] = ()`, default-empty so every existing construction (including `translate_to_english`'s) stays
  unaffected by construction, not by a special case.

  **`_render_plan`'s return type grew from a 4-tuple to a 5-tuple**, adding `entries: list[LexicalEntry |
  None]` built at the exact same sites `gloss_parts` already uses (main-word, both auxiliary-loop
  directions, the possessive-particle append, the question-particle insert, and the nested-clause
  recursive extend -- the latter needed `linker_words`'s own tuples widened from 3 to 4 elements to carry
  the linker/preposition entry alongside its already-tracked gloss). `translate_to_conlang` zips
  `(rom_parts, sandhied_ipa, entry_parts)` per sentence to build each `TokenGloss`, attaching that
  sentence's own terminal mark to only its *last* token's `surface` -- mirroring exactly how the joined
  string already gets the mark appended, so the two never disagree. `coined` membership is checked against
  the whole call's accumulated `coined: list[LexicalEntry]`, so a word coined in an *earlier* sentence of
  a multi-sentence translate still reads `coined=True` in a later sentence that reuses it.

  **The large-looking but genuinely mechanical fallout**: `_render_plan` has exactly three callers in the
  whole codebase -- itself (recursive), `translate_to_conlang`, and **26 direct call sites across 24 test
  files**, every single one unpacking the exact same `(language, romanization_parts, ipa_parts,
  gloss_parts)` 4-tuple (confirmed by grep before touching anything). Fixed with one in-place `sed`
  pass (`s/ = _render_plan(/, _ = _render_plan(/g` across `tests/`) adding a 5th, ignored (`_`) unpacked
  target to every one -- zero test assertions needed to change, since none of them inspected a 5th return
  value that didn't exist before. This is not a design smell: plain tuple unpacking has no backward-
  compatible way to add a field, and a `NamedTuple`/dataclass return would have the exact same arity
  problem for any caller still unpacking positionally.

  **Explicitly scoped out, not attempted**: (a) the *live* grammatical marking actually applied this
  occurrence (case/tense/mood/degree) -- an Explore agent confirmed no single uniform "marking just
  applied" string exists anywhere in `_render_plan`; it's scattered across ~8 different kind-specific
  branches' own locals (`tense_in`/`mood_in`/`agreement_label`/`slot.case`/`slot.degree`/`features`/...),
  each live only inside the branch that computed `rendered` for that slot kind -- collecting it would mean
  threading a new string out of every one of them, a separate, materially bigger lift; (b)
  `translate_to_english`'s own `tokens` stays always-`()` -- that direction already builds a richer
  per-token `annotated` list, but it's keyed to the *source* conlang tokens, and the fluency LLM rewrite
  can reorder/merge/split words arbitrarily, so there's no clean word-for-word alignment to the final
  English output the way the conlang-render direction has.

  **Web UI** (`webui/static/index.html`): when `result.tokens` is non-empty, each glossed word renders as
  a `<span class="gloss-token">` (dotted-underline, a distinct accent color when `coined` -- visible
  without even hovering, directly answering the user's own original complaint) carrying its data in
  `data-*` attributes; a single shared `#gloss-tooltip` element, wired once via event delegation on
  `document` (survives the result card's own `innerHTML` replacement on every translate call), shows on
  hover/focus and *pins* on click/tap -- one implementation covering both "hover" and "click" from the
  item's own title. A bare particle (no gloss) renders as plain text, not a span -- nothing useful to show
  on hover for it. A new `escapeAttr` helper guards against a coined word's own spelling (or free-text
  `notes`) breaking the `data-*` attribute syntax if it ever contains a quote character; applying it to the
  *fallback* plain-text path too (`translate_to_english`, unchanged otherwise) is a small, incidental
  correctness improvement over the previous unescaped `${result.text}` interpolation.

  **CLI** (`cli/main.py`): one more unconditional line after the existing `(pattern: ...)` echo --
  `Glosses: word1(gloss1) word2(gloss2*) ...` (a bare particle prints undecorated, no parens; `*` marks a
  token coined this call) -- matching how `coined`/`pattern` are already always printed, no new flag.
  Present only for the conlang direction, since `result.tokens` is empty otherwise (no explicit `--to`
  check needed).

  **Tests**: new `tests/test_token_gloss.py` -- `entries`' length always matches `romanization_parts`'
  (direct `_render_plan` calls, including one exercising the nested-clause extend path specifically);
  `coined`/`real_word` set correctly (reusing the earlier "coined words ignore word strictness" pass's own
  Dutch word-strictness-1.0 fixture for the real-word case); `[t.surface for t in result.tokens] ==
  result.text.split()` across declarative/question/imperative and a two-sentence input (confirms the
  mark-attachment-to-last-token logic doesn't bleed a mark into the next sentence); a bare particle's token
  has `gloss=pos=real_word=None`; `translate_to_english`'s `tokens` stays always `()`; a `CliRunner`-based
  test confirms the new `Glosses:` line for `--to conlang` and its absence for `--to english`. One
  interesting fixture bug caught along the way: an early draft of the coined-vs-not-coined test asserted
  the pronoun "I" was present and not coined -- it failed, because the *raw*, un-stripped seed-278 fixture
  (unlike `test_translator.py`'s own copy of the same seed, which explicitly strips noun classes before
  use) happens to have `grammar.pro_drop = True`, so "I" never renders as its own word at all for that
  exact fixture. Fixed by asserting on "see"/"the" instead -- a reminder that "same seed number" across
  different test files doesn't guarantee the same actual generated grammar unless the fixture construction
  is identical too.

- **Fake planner: a grouped noun phrase's own placeholder leaked as a word's gloss, and the fake
  backend's response cache made the fix invisible on an already-translated sentence (two bug fixes, not
  a numbered grammar pass).** A user reported two coined words glossed as literal garbage
  (`"zznpaazz"`/`"zznpbazz"`) translating "I am Willy Wonka of the sea people, I bring good tidings to
  you, my friend." on their own saved "Moorian" language -- directly surfaced by the hover/click gloss
  feature above, which made an existing bug visible for the first time rather than introducing one.

  **Root cause 1**: `llm/fake_client.py::_fake_group_noun_phrases` collapses a noun phrase with a real
  modifier (adjective, possessor, demonstrative, numeral, quantifier -- *not* a bare "the", which has no
  `real_mods` of its own) into one opaque placeholder token (`f"zznp{...}zz"`), recorded in an `info`
  dict the real noun/modifiers can be recovered from. `_fake_single_clause_plan`'s two *dedicated* clause
  shapes (2 and 3 content words) always resolve a placeholder correctly via the shared `noun_phrase()`
  helper -- but its generic ≥4-content-word fallback ("anything else becomes one bare content slot per
  word") checked `name_by_placeholder` for a proper-name placeholder and completely forgot the parallel
  `np_info` check for a *noun-phrase* placeholder, using the raw opaque string itself as the slot's gloss.
  "I bring good tidings to you." has exactly 5 content tokens after grouping (`i bring [good+tidings] to
  you`) -- too many for either dedicated shape, landing in the broken fallback; a shorter variant missing
  either the adjective or the trailing "to you" phrase hits a shape that already worked, which is why the
  bug looked narrower than it was until traced systematically. Fixed with one more `elif t in np_info:
  slots.extend(noun_phrase(t, None))` branch, reusing the exact same resolution dedicated shapes already
  rely on -- no new mechanism.

  **Root cause 2, and the more interesting one**: fixing root cause 1 alone did not change the CLI's own
  output for the user's exact saved language, even after confirming by direct Python call that `_fake_
  plan_dict`/`plan_sentence`/`translate_to_conlang` all now produced the correct glosses in isolation.
  Traced to `llm/factory.py::build_llm_client`: every backend, including `"fake"`, was wrapped in
  `CachingLLMClient`, a disk-backed cache keyed only on `(model, system, prompt, max_tokens)` -- not on
  `fake_client.py`'s own code. The user's original, pre-fix translate call had already cached that exact
  prompt's buggy JSON plan; every later call with the same text replayed it verbatim regardless of any
  source fix, confirmed directly by inspecting `.cache/llm_cache_fake.json` and finding the stale
  `"zznpaazz"`-glossed entry already persisted in the saved language's own `lexicon.yaml` from the
  original report. Caching the fake backend was never buying anything -- it's already free and
  deterministic, so there's no cost or latency to save, only the risk that a future fake-planner fix
  silently fails to take effect for any sentence already seen once. Fixed by having `build_llm_client`
  skip the `CachingLLMClient` wrap for `kind == "fake"` entirely (still wrapped in `CostTrackingLLMClient`
  for ledger-shape parity) -- `"anthropic"` keeps its cache unchanged, since that's the backend caching
  actually protects (money, not correctness).

  **Tests**: `test_the_generic_fallback_resolves_a_grouped_noun_phrase_not_its_raw_placeholder`
  (`tests/test_noun_phrase.py`) exercises both an adjective-modified and a possessor-modified noun phrase
  in the broken fallback shape directly via `_fake_plan_dict`, asserting no gloss starts with `"zznp"`.
  `tests/test_adverbs_and_backend_caches.py`'s old `test_each_backend_gets_its_own_cache_file` (which
  asserted the fake backend *did* get a cache file -- exactly the behavior just reversed) is replaced by
  `test_the_fake_backend_is_never_cached` (two identical calls, both report `cached=False`, no cache file
  written) and `test_caching_llm_client_itself_still_caches_by_request_content` (the caching mechanism
  itself, used directly rather than through `build_llm_client`, still caches -- confirms only the
  *wiring* choice changed, not `CachingLLMClient`'s own behavior). `tests/test_generation_and_translation.
  py::test_cache_hit_is_not_billed_again` used `build_llm_client(kind="fake", ...)` purely as a free way
  to test the general "a cache hit is never billed" contract -- rewritten to build the same `Caching
  LLMClient(CostTrackingLLMClient(FakeLLMClient(), tracker), path)` stack directly (`FakeLLMClient`
  standing in for a real backend only to avoid a network call), since that contract is about `Caching
  LLMClient`/`CostTracker` together, not about the fake backend's own wiring.

- **Model choice per task, and its web-UI picker (two linked DEFERRED.md items, done together).**
  `DEFAULT_MODEL` (Haiku 4.5) was hard-wired into every one of this project's 7 `LLMRequest` call sites,
  confirmed by grepping every one before writing a line of code: `prompt_classifier.classify_prompt`;
  `lexicon_gen.choose_best_candidate`/`_choose_chunk` (candidate picking); `real_words_llm.fetch_real_
  words` (real-word gap-filling); `seed_examples._guess_ipa` (seed-word/borrowed-name IPA guessing);
  `sentence_planner.plan_sentence`; and the fluency request inside `translator.translate_to_english`
  itself. Picking the UI up properly meant building the underlying choice mechanism first, since the
  picker has nothing to attach to otherwise -- the two DEFERRED.md items were tackled as one pass.

  **The three-bucket split, and why each bucket landed where it did**: tracing every one of the 7 call
  sites' own callers (not guessed -- read end to end) showed they split cleanly into exactly three groups
  by *reuse pattern*, not by subject matter alone:
  - **Classifier** (`classify_prompt` only) -- called once, directly from the CLI/web layer, *before*
    `GenerationSpec` even exists, and never reused after generation. A new `GenerationSpec.classifier_
    model` field still records the choice (write-only after generation, kept purely for inspectability --
    `Language.spec` is frozen, the classifier never runs again for this language).
  - **Word-selection-and-coinage** (`lexicon_gen`'s picking, `real_words_llm`'s gap-filling,
    `seed_examples`'/`names`' IPA-guessing) -- every one of these is reused identically at *both*
    generation time and later translation-time coinage, via the exact same `word_selection: str =
    "algorithmic"` parameter that already threads through every one of them as a plain function
    parameter (confirmed by reading every signature -- never read from a `language`/`spec` object deep
    inside any of them). A new sibling parameter, `model: str = DEFAULT_MODEL`, rides the *exact* same
    path: `propose_word`/`propose_templatic_word`/`resolve_candidate`/`choose_best_candidate`/
    `choose_best_candidates_batch`/`_choose_chunk`/`fetch_real_words`/`_guess_ipa`/`resolve_seed_examples`
    all gained it right next to `word_selection`. A new `GenerationSpec.word_selection_model` field is
    genuinely read twice: at generation time (`generator.py`'s `build_and_pick` closure, `real_words.
    plan_real_words`, reading `spec.word_selection_model` directly) and at translation time
    (`translation/expansion.py`'s `coin_word`, `real_words.coin_real_word`, `translation/names.py`'s
    `make_name_entry`, all reading `language.spec.word_selection_model`) -- the identical two-tier reuse
    `word_selection` itself already has, not a new pattern.
  - **Translation-proper** (`plan_sentence`, the fluency request) -- deliberately *never* persisted on
    `GenerationSpec`/`Language` at all. `model` is passed fresh into `translate_to_conlang`/`translate_to_
    english` on every call, exactly the way `llm_client` itself already is -- a user translating an
    existing language may reasonably want a cheaper or pricier model than the one that generated it, call
    by call, the same flexibility `--llm` itself already has.

  **Every one of the ~15 function-signature changes is purely additive** (`model: str = DEFAULT_MODEL`,
  a new parameter with a default, never changing an existing one's position or removing anything) --
  unlike the hover/click-gloss pass's `_render_plan` arity break, *zero* existing call sites (library code
  or tests) needed to change at all; only the handful of call sites that now set `model=` for real
  (6 production sites, found by grepping for the existing `word_selection=` pattern) touched anything.

  **`llm/pricing.py` gained `TYPICAL_TOKENS`/`estimated_price`** for the picker's own "expected price per
  call" display -- a hardcoded (input, output) token estimate per task (classifier/word_selection/
  translation), taken straight from this DEFERRED item's own ledger-sourced figures, not a live
  `CostTracker` rollup: nearly all local testing runs the free `fake-llm` backend, so the real ledger has
  thin-to-zero coverage for any paid model today, and a hardcoded, clearly-labeled estimate reads more
  honestly than a rollup that would silently read "0 samples" for every real model. `webui/app.py`'s
  `/api/options` gained a `models` list (the 4 real, priced models, `_MODEL_LABELS` giving each a short
  display name -- `"fake-llm"` excluded, no real price) with `price_per_million` and a 3-way `estimated_
  price`; `static/index.html`'s Generate tab gained two selects under Advanced options (classifier/word-
  selection model) and the Translate tab gained one (translation model, hidden via a `tr-llm` change
  listener when the free backend is selected -- a model choice is meaningless there), all three populated
  from that same `models` list with the price baked into each option's own label.

  **CLI**: `generate` gained `--model`/`--word-model` (printed back as one more summary line, "Models:
  classifier=..., word selection=...", mirroring the existing trait-summary style) plus the two
  `GenerationSpec` fields; `translate` gained `--translate-model`. No new top-level command, per `AGENTS.
  md`'s own CLI discipline -- both are ordinary options on existing commands, the same shape `--word-
  selection` already is.

  **Tests**: `tests/test_llm_model_choice.py` (new) -- a shared `_Spy(FakeLLMClient)` (the same spy
  pattern `test_pronoun_extras.py`'s own `_annotation` helper already uses) confirms the chosen model
  string actually reaches the `LLMRequest` for every one of the 7 call sites, plus a regression guard that
  omitting `model` still uses `DEFAULT_MODEL` exactly as before this feature, plus CLI-level `CliRunner`
  checks (summary line + saved-spec fields) for both commands. `tests/test_webui.py` gained the `/api/
  options` `models`-list shape check and `/api/generate`/`/api/translate` field-threading checks, in the
  same file and fixture (`client`, an isolated-`tmp_path` `TestClient`) every other web-backend test here
  already uses. One fixture bug caught while writing these: an `/api/options`-reading test's own real last
  assertion line (`assert len(opts["graded_trait_fields"]) == 15`) sat just past a `Read` call's own
  line-count window, so it looked like the function ended one line earlier than it really did -- the
  first edit attempt matched only the visible part and orphaned that trailing assertion into the next
  function down; caught immediately by the resulting `NameError` on the undefined `opts` and fixed by
  moving the line back to its own function. A reminder that a truncated `Read` window can silently mislead
  an `Edit`'s own exact-match boundary, not just a human skimming it.

- **Advanced options (web app, DEFERRED.md item, done).** Two independent pieces, same item: a pure UI
  reorganization, and a genuine new classifier capability.

  **The move** (`webui/static/index.html`): the Generate tab's always-visible checkboxes (fantasy, force
  isolated, force high altitude, force tonal, allow all-caps POS) and its "Foreign names" select all moved
  into the collapsed "Advanced options" `<details>` block, alongside the model-choice selects the previous
  pass already put there. Confirmed this needed zero JavaScript changes: every control is looked up by
  `id` (`$("gen-foreign-names")`, `$("gen-fantasy")`, ...) at submit time, and an `id`-based `getElementById`
  lookup doesn't care where in the DOM tree the element actually lives -- only the HTML markup moved.

  **The classifier capability**: `translation/names.py::resolve_foreign_names` used to have only two
  tiers -- an explicit `GenerationSpec.foreign_names` override, else a weighted vote of matched `source_
  languages` profiles' own curated `foreign_name_handling` (uncurated profiles abstain, default `"keep"`).
  The prompt's own free text was never asked, even when it explicitly addressed this (e.g. "foreign names
  are always adapted to the language's own sounds"). Fixed the same way every other inferable-but-
  overridable concept in this project already is: a new `TraitProfile.requested_foreign_names: str = ""`
  field, extracted by `prompt_classifier.classify_prompt` (one more "Also extract:" bullet in the system
  prompt, one more worked example, parsed via the existing lenient `_coerce_str` -- the exact same
  treatment `requested_orthography_style` already gets, right down to reusing the same coercion function),
  consulted as a new *middle* tier in `resolve_foreign_names`: explicit override wins outright, then the
  classifier's own reading when the prompt explicitly addressed it, then the existing source-language
  vote, then `"keep"`. No fake-client changes needed -- confirmed `FakeLLMClient`'s own `"trait_profile"`
  strategy only ever populates the graded float fields it's told about via `request.metadata["trait_
  fields"]` (`GRADED_TRAIT_FIELDS` only), never any of the string/list fields (`source_languages`,
  `requested_orthography_style`, and now `requested_foreign_names` alike) -- those all already, correctly,
  come back empty under the fake backend, the same way `requested_orthography_style` always has.

  **Tests**: `tests/test_prompt_classifier.py` gained the same two-test pair (parses when given, defaults
  to empty when missing) every other lenient string field there already has; `tests/test_names.py` gained
  a three-way precedence test (classifier reading overrides the vote; an explicit `spec.foreign_names`
  still overrides the classifier reading) directly exercising `resolve_foreign_names`. Verified the UI
  move live in the browser: the top-level `.row` no longer contains `gen-foreign-names`, the `<details>`
  block contains it plus every moved checkbox, and a full generate submission with `fantasy` checked and
  `foreign_names` set to `adapt` from inside the now-collapsed section still reaches the saved `spec`
  correctly.

- **Three bugs from one real-backend test report (bug fixes, not a numbered pass).** A user generated
  "FutureMongotalian" against the real Anthropic backend (model Fable 5), manually edited a word, and
  reported four findings. One (raw IPA ligatures in romanization) was the same already-tracked,
  not-yet-fixed `docs/DEFERRED.md` shortcoming from an earlier report -- folded into that existing entry
  (now also naming `lʲ`/`ǯ`, confirming the complaint is about the diacritic style's general tendency,
  not only the original four ligatures), not re-investigated. The other three were genuinely new,
  independently root-caused by three parallel Explore agents reading the actual code.

  **Bug 1 -- a manually-edited word was silently ignored.** A sentence that's just one standalone,
  capitalized word ("...Water.") let the real LLM plan it as a `"name"` slot instead of ordinary content
  -- plausible, since each sentence is planned independently with zero cross-sentence context
  (`translator.py::translate_to_conlang`'s own per-sentence loop). That alone would just be an LLM-
  prompting imperfection; the real bug was architectural: `names.find_name_entry` is gated on
  `entry.notes == NAME_NOTE` ("proper name") *exactly*, and the web UI's lexicon-edit endpoint
  (`webui/app.py`) appends `" (manually edited)"` onto whatever `notes` a word already had -- so the
  user's own edited "water" entry (`notes="(manually edited)"`) was invisible to that lookup, and with no
  fallback to the *ordinary*-word lookup, the render branch coined a brand-new, unrelated word instead
  (the "eedemerediirenchene" the user saw). Fixed with one new fallback line (`names.find_name_entry(...)
  or _find_word(...)`, reusing the already-existing, already-case-insensitive, name-excluding `_find_word`
  helper verbatim) plus one hardening (`is_name_entry`: exact-equality -> substring containment on
  `notes`, fixing a related latent bug where a *genuine* name surviving a manual edit lost its own name
  status the same way). Verified directly: constructing a `"name"`-kind slot for a gloss that already has
  an edited ordinary entry now reuses that entry's exact spelling instead of coining.

  **Bug 2 -- "Lake Baikal" passed through as literal English.** Multi-word proper names were never
  designed for anywhere in this codebase, fake or real (the fake backend's own name-extraction regex
  matched exactly one capitalized word at a time; the real-LLM system prompt's "name" instructions only
  ever showed single-token examples). Fixed in both backends with the same targeted pattern -- a
  recognized geographic descriptor ("lake", "mount"/"mt", "river", "sea", "ocean", "cape", "fort",
  "saint"/"st", "mountain") immediately followed by another capitalized word splits off as an ordinary
  word, leaving only the specific part as the name: `llm/fake_client.py::_fake_extract_names` gained one
  lookahead check in its own `swap` closure (`re.match(r"\s+[A-Z][a-z]+", prompt[match.end():])`, peeking
  at the original string past the current match); `sentence_planner.py`'s real-LLM system prompt gained a
  matching instruction sentence plus a worked example ("I see Lake Baikal" -> a `lake` content slot + a
  `Baikal` name slot). Verified directly via `_fake_extract_names` and a full `translate_to_conlang` round
  trip: "lake" now translates as an ordinary word, "Baikal" is coined as a name, and a plain single-word
  name ("Bruno") is completely unaffected. Explicitly not attempted: a true multi-word name with no
  generic descriptor part ("New York") -- no mechanical way to know where to split it, a separate,
  bigger problem.

  **Bug 3 -- an explicit "I want tones" request still produced a non-tonal language.** The deepest of
  the three. `trait_bias.biased_probability(0.35, tonal_friendliness)` can legitimately reach 93.5% at a
  high trait value, but `phonology_gen._reference_clamp` unconditionally discarded that down to
  `min(probability, 0.08)` whenever every *matched* reference-language profile disagreed (Mongolian and
  Italian are both curated `tonal: false`) -- regardless of how strong the trait signal was, contradicting
  `core/spec.py`'s own documented "a confident reading behaves close to a guarantee." This was asymmetric
  with the function's own *agreeing* branch, which already lets an even-higher trait value escape
  *upward* past its own `0.75` anchor via `max(probability, 0.75)` -- the disagreeing branch had no
  analogous resistance at all. Fixed with a mirrored escape, gated on the *same* `0.75` "explicit and
  central" threshold the classifier's own calibration prose already uses: `0.08 + (probability - 0.75) /
  0.25 * (0.5 - 0.08)` when `probability > 0.75`, continuous with the unchanged branch at the boundary
  (both give exactly `0.08` at `probability=0.75`). The existing final `strictness`-based reduction line
  is deliberately left untouched -- hand-computed across a range of strictness values (0.0 through 0.8)
  confirmed a meaningful improvement throughout (e.g. ~5x better even at a high strictness of 0.8) while
  still letting a separately very-high, explicit strictness meaningfully suppress the escaped value
  further, which is treated as a legitimate competing signal, not a bug. Confirmed low regression risk by
  grepping every test touching `_reference_clamp`: the one direct unit test only exercises the untouched
  `any_true` branch; two of the function's four call sites (`coda_devoicing`, `word_accent_realization`)
  pass a flat `0.0` base probability that can never exceed `0.75` and are structurally unaffected;
  `vowel_harmony`'s call site gets the same fix for the same reason, not specially excluded. Also fixed a
  smaller, secondary contributor: the classifier's own few-shot calibration was asymmetric (an explicit
  tonal *request* anchored at only `0.6`; an explicit *negation* of comparable directness anchored at
  `-0.85`) -- added a new worked example, the user's own exact prompt, anchored at `0.85`, with an
  explanation distinguishing "a sentence entirely and solely about tone" from "tone as a brief lead-in to
  some other main request" (the pre-existing Wade-Giles example), so the new example doesn't read as
  contradicting the old one. Not verifiable against the real Anthropic backend without a paid call --
  verified instead via `_reference_clamp`'s own new direct unit tests and hand-computed probabilities.
