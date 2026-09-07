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
  on the word: about/item/lemon/focus/pencil).

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
  affix). Typed value objects only, no rule engine.
- **`lexicon.py`**: `LexicalEntry` (form + glosses + POS + tones + `root`
  -- the consonantal root a templatic word was derived from, `None`
  otherwise), `Lexicon` (entries + idioms, with case-insensitive
  `by_gloss`/`by_form` lookup, both NFC-normalized on the form side).
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
  verbs reliably get their silent "-r") and to `grammar_gen.py`'s two
  existing reference-bias axes (`uses_root_and_pattern`, the `FUSIONAL`
  weight boost) -- deliberately *not* to typological axes with no
  per-profile data at all (word order, alignment: see "Known v0
  limitations" below).
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
- **`lexicon_gen.py`**: `CORE_MEANINGS` (the ~49-word core vocabulary) and
  `propose_word()` -- builds candidate forms deterministically, asks the LLM
  to pick one via `choose_best_candidate()` (shared with `root_pattern.py`).
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
  for those same four languages: English 1.14, Dutch 1.27, French 1.35,
  German 1.43) lets a matched `source_languages` bias graded by
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

## `translation/` -- bidirectional translation

- **`translator.py`**: `translate_to_conlang()` / `translate_to_english()`.
  Recognizes exactly three sentence shapes (predicate-adjective,
  subject-verb-object, word-for-word fallback); see the module docstring for
  the full list of explicit v0 limitations (no real parser, naive
  lemmatization, English assumed canonical SVO for reconstruction).
- **`expansion.py`**: `coin_word()` -- reuses `lexicon_gen.propose_word()`
  with a per-gloss RNG seed derived from `sha256(spec.seed, gloss)`, so
  coinage is reproducible independent of translation order.

## `speech/`

- **`reader.py`**: `lookup_pronunciation()` / `describe()` -- IPA and
  romanization lookup only. No audio synthesis (explicit limitation, not a
  stand-in for real TTS).

## `cli/main.py`

Typer app with exactly three commands (`generate`, `translate`, `pronounce`),
per AGENTS.md's CLI discipline. `generate`'s `--source-language` (repeatable)
and `--example` (repeatable, `gloss=form` or `gloss=form|ipa`) are milestone-5
inputs; `--evolve-from <name>` + `--years N` (milestone 6) switch `generate`
into evolving an existing saved language instead of generating fresh --
`--prompt`/`--source-language` are reinterpreted as the evolution period's
own characteristics in that mode (classified the same way, just describing
something different). None of these add new commands. See `docs/CLI.md`
for verified examples.

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
  rate, not by fresh generation. `time_depth_years` itself is still
  unconsumed too (`--evolve-from`/`--years` on the CLI is the actual years
  input; the classifier-extracted field isn't wired to it yet).
- `source_language_strictness` only reaches the reference-bias mechanisms
  that already exist (phonology's inventory/syllable-shape/tonal/vowel-
  harmony axes; `romanization_gen.py`'s category/per-symbol/grammatical-
  spelling rolls; `grammar_gen.py`'s `uses_root_and_pattern`/`FUSIONAL`
  boost) -- it can't push `word_order`, `alignment`, or an explicit
  `morphological_type` toward a matched language's real value, because
  `ReferenceLanguageProfile` doesn't store that data for any of the 30
  profiles today (adding real, accurate values for all of them is a
  separate curation project, same discipline the phonological/
  orthographic profile fields already required). It also doesn't reach
  `sound_change.py`'s own, separate inventory-recompute path during
  multi-century evolution -- a strict language's phonology can still
  drift back toward looser/generic over a long evolution run, same as
  any other language's.
- `restricted_onset_consonants`/`attested_onset_clusters` are curated for
  German, English, French, and Dutch only -- every other profile leaves
  both empty (falls back to the generic sonority-only check, same "not
  yet curated" honesty `orthography` already practices). The full local-
  adjacency family now covers all three positions in `(onset) nucleus
  (coda)`: onset+nucleus (`allowed_onset_nucleus_pairs`/
  `excluded_onset_nucleus_pairs`, e.g. real English "dw-"/"tw-" never
  preceding a rounded vowel), nucleus+coda (`allowed_nucleus_coda_pairs`/
  `excluded_nucleus_coda_pairs`, e.g. real English `/ŋ/` only closing a
  syllable after a lax/checked vowel), and the cross-syllable
  `SyllableStructure.is_valid_boundary` (coda-then-next-onset, e.g. a
  word's own coda "p" immediately followed by the next syllable's own
  onset "d") -- all three resolved by the one generic
  `phonology_gen._resolve_pair_restriction`, all three consumed by
  `word_builder.py`. The onset+nucleus and cross-syllable-boundary
  curated fields are empty for every profile except onset+nucleus's
  English entry -- real, solidly-verifiable, purely *combinatorial*
  (non-assimilation) facts of this shape are genuinely sparse for the
  four perfected languages (most real syllable-boundary phenomena in
  German/French/Dutch are assimilation/liaison processes, not a flat
  "this coda never precedes that onset," and this project's word-builder
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
- `reference_languages/profiles/` covers 30 languages (Arabic, Arawakan,
  Bengali, Dutch, English, Finnish, French, Georgian, German, Hawaiian,
  Hebrew, Hindi, Icelandic, Indonesian, Italian, Japanese, Korean,
  Mandarin, Mongolian, Nahuatl, Pama-Nyungan, Persian, Portuguese,
  Quechua, Russian, Spanish, Tamil, Tibetan, Turkish, Xhosa), chosen for
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
  (`GrammarProfile.plural_suffix`/`cases` are generated but have zero
  consumers); and specific-word capitalization (e.g. English "I"),
  dropped because keeping it consistent across a pronoun's variants
  ("he"/"she"/"it") has no foothold in today's one-word-per-gloss
  `CORE_MEANINGS` lexicon model.
- Consonant gemination and palatalization -- both surveyed and initially
  deferred as needing a phoneme feature this project didn't model -- are
  now modeled (`Consonant.long`/`Consonant.palatalized`,
  `consonant_gemination_marked`, the `gemination-style` anchor; see
  `phonology_gen.py`/`romanization_gen.py` above). Korean's cross-syllable
  consonant assimilation and Hindi/Devanagari's schwa deletion, from that
  same survey, stay out of reach for the reason already given above
  (word-level algorithmic systems, not per-symbol rules).
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
