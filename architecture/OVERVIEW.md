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
    breathy "depressor" (`ɡǀ`/`ɡǃ`/`ɡǁ`, reusing the exact `breathy`
    trait Hindi's own murmured `bʱ`/`dʱ`/`ɡʱ` series already uses, since
    both are phonetically breathy voice), and nasalized (`ŋǀ`/`ŋǃ`/
    `ŋǁ`, tagged `Manner.NASAL` rather than their bare counterparts'
    own STOP/LATERAL_FRICATIVE, since nasalized clicks phonetically
    pattern with nasals). Zulu's own plain-obstruent depressor series
    reuses the pre-existing `bʱ`/`dʱ`/`ɡʱ` symbols directly -- real
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
  - **Yoruba's real doubly-articulated labial-velar stop** `ɡb` (its
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
    aspirated/breathy series (`pʰ tʰ kʰ bʱ dʱ ɡʱ`) essentially never
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
