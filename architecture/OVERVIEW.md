# Architecture overview

Reflects the code as it exists after the first generation/translation slice.
Update this alongside future structural changes (per AGENTS.md).

## `core/` -- immutable domain models (pydantic, `frozen=True`)

All mutation-shaped operations return a new instance (`model_copy` /
`with_*` methods); nothing here is mutated in place.

- **`phonology.py`**: `Consonant`, `Vowel` (IPA symbol + articulatory
  features) -> `PhonemeInventory`. `ToneSystem` (enabled levels + combining
  diacritics). `SyllableStructure`: onset/coda size limits, an onset-cluster
  allowlist, and `is_valid_syllable()` -- the one phonotactics check used
  everywhere a word is validated.
- **`romanization.py`**: `RomanizationRule` (IPA fragment -> Latin), and
  `RomanizationScheme.apply()`, which greedily rewrites longest-IPA-fragment
  first (so multi-symbol sequences like affricates match before their parts)
  and NFC-normalizes the result so accented output matches what a human
  would type or paste.
- **`grammar.py`**: `GrammarProfile` -- word order, morphological type,
  alignment, articles/copula/adjective-position flags, case labels, plural
  suffix. Typed value objects only, no rule engine.
- **`lexicon.py`**: `LexicalEntry` (form + glosses + POS + tones),
  `Lexicon` (entries + idioms, with case-insensitive `by_gloss`/`by_form`
  lookup, both NFC-normalized on the form side).
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
  `contact_languages` feeds `generation/reference_languages.py` (milestone
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
  inventories (the schwa-in-English effect). `build_word` picks one
  front/back harmony class per word up front when `vowel_harmony` is set
  and threads it into every syllable, with a small leak probability
  (central vowels stay harmony-neutral); an optional `size_bias`
  ("small"/"big") layers a further soft preference for close/open vowel
  height on top (Sapir 1929 size sound symbolism). `build_reduplicated_word()`
  is a separate, simpler path for the mama/papa kinship pattern (Jakobson
  1960) -- one onset restricted to a manner class, repeated twice,
  deliberately bypassing `SyllableStructure` since it isn't a phonotactic
  rule.
- **`sonority.py`**: `sonority(consonant) -> int`, derived from
  `Consonant.manner` (stops/affricates < fricatives < nasals < liquids <
  glides) rather than stored per-phoneme. `is_legal_onset_cluster()`/
  `is_legal_coda_cluster()` implement the sonority sequencing principle
  (rising toward the nucleus, falling away from it), plus the documented
  cross-linguistic exception for word-initial /s/ + voiceless stop. Used by
  `phonology_gen.py` to *derive* cluster legality from whatever's in a
  generated inventory, instead of a hardcoded pair list tied to one fixed
  symbol set.
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
  ~45 consonants / ~17 vowels spanning the major IPA categories, including
  a few very-low-prevalence "exotic" extras like clicks/implosives --
  illustrative coverage, not exhaustive IPA) gets an independent
  `rng.random() < prevalence` draw, except trait-linked symbols (ejectives,
  the uvular series, harshness-tagged fricatives/affricate/velar nasal),
  which use `biased_probability` (or `1.0` under the matching `force_*`
  flag) instead: ejectives from `traits.altitude` (Everett 2013), uvulars
  from `traits.isolation`, harsh-vs-soft fricative/affricate/nasal
  selection from `traits.aesthetic_harshness`. Voiced stops/affricates are
  only added alongside their voiceless counterpart (near-universal
  implicational rule, guaranteed by construction). A floor tops up from the
  highest-prevalence unused symbols if the probabilistic draw produces a
  degenerate inventory. Onset/coda cluster legality comes from
  `sonority.py`, not a hardcoded list; each generated language also gets a
  coda profile (none / sonorant-only / unrestricted, illustrative-weighted)
  and a vowel-harmony flag (modestly boosted by `traits.isolation`).
  Tone-system-enabled uses `traits.tonal_friendliness` the same way.
  Milestone 5 adds two more inputs, both soft biases layered on the same
  probabilistic mechanism (never a hard override): `traits.contact_languages`
  matched against `reference_languages.py` boosts symbols/coda-profile/
  onset-tolerance/tonality toward the matched real language(s)' profile and
  suppresses the rest (`_reference_biased_rate`/`_group_reference_bias`/
  `_reference_clamp`); `spec.seed_examples`' IPA (tokenized against the full
  known symbol pool, greedy longest-match like `RomanizationScheme.apply`)
  is a hard floor -- those specific phonemes are unconditionally forced into
  the inventory (`_force_include`), since a seed word's sounds must actually
  be available for the word to make sense as part of the language.
- **`reference_languages.py`**: `ReferenceLanguageProfile` and
  `REFERENCE_LANGUAGES` -- ~8 hand-curated, typologically-spread real
  languages (Japanese, Finnish, Mandarin, Arabic, Hawaiian, Georgian, a
  click-language stand-in, a Romance stand-in), symbol sets restricted to
  what `phonology_gen.py` already models. `match_profiles()` case-
  insensitively matches names/aliases; unknown names are silently ignored.
  Illustrative sketches for flavor, not authoritative descriptions.
- **`seed_examples.py`**: `resolve_seed_examples()` -- fills in
  `SeedExample.ipa` from `.form` via one LLM call per unresolved example
  when the user didn't supply IPA directly. An explicit guess (stated as
  such in the prompt), not phonetic analysis -- there's no reliable way to
  recover pronunciation from arbitrary spelling without knowing the
  intended convention.
- **`romanization_gen.py`**: `generate_romanization()` -- picks one of two
  whole-language styles (digraphs vs. diacritics) and applies it
  consistently.
- **`grammar_gen.py`**: `generate_grammar()` -- weighted picks reflecting
  rough cross-linguistic frequency (SOV/SVO dominate; nominative-accusative
  dominates), nudged via `biased_probability`/weight shifts by
  `traits.isolation` and `traits.community_scale` (toward
  polysynthetic/agglutinative and ergative alignment -- Trudgill) and
  opposed by `traits.contact_intensity` (toward isolating/analytic --
  creolization tendency).
- **`lexicon_gen.py`**: `CORE_MEANINGS` (the ~49-word core vocabulary) and
  `propose_word()` -- builds candidate forms deterministically, asks the LLM
  to pick one. Shared by both initial generation and later expansion.
  Syllable count is weighted by part of speech and a `favor_short` flag
  (pronouns/particles skew short regardless; core generation defaults
  `favor_short=True`, `translation/expansion.py`'s coinage passes `False`)
  -- Zipf's law of abbreviation, using core-vs-coined as the one frequency
  proxy the system has. Two meaning-specific sound-symbolism effects layer
  on top: `"mother"`/`"father"` try `word_builder.build_reduplicated_word()`
  first (nasal vs. stop onset, ~80% of the time, falling back to normal
  generation if the inventory has neither or the roll misses) -- the
  mama/papa convergence; `"small"`/`"big"` thread `size_bias` into the
  normal candidate-build loop instead of replacing it.
- **`generator.py`**: `generate_language()` -- orchestrates the above into
  one `Language`. Builds a `LexicalEntry` directly from each
  `spec.seed_examples` entry (skipping `CORE_MEANINGS` generation for any
  gloss a seed example already covers) before generating the rest, so
  seeded words land in the lexicon like any other entry and translation
  picks them up with no special-casing.

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
per AGENTS.md's CLI discipline. `generate`'s `--contact-language` (repeatable)
and `--example` (repeatable, `gloss=form` or `gloss=form|ipa`) are milestone-5
inputs, not new commands. See `docs/CLI.md` for verified examples.

## Known v0 limitations (intentional, not oversights)

- Several `TraitProfile` fields are extracted and stored but not yet
  consumed by generation: `social_hierarchy`, `orality_literacy`,
  `evidentiality_culture`, `spatial_reference`, `ritual_register`,
  `taboo_register`, `terrain_communication_distance`,
  `salient_vocabulary_domains`, `time_depth_years`. `time_depth_years` in
  particular needs a separate diachronic sound-change derivation pipeline
  from an existing language (milestone 6), not the fresh-generation path.
- The typological tendency nudges and phoneme-pool prevalence values in
  `phonology_gen.py`/`grammar_gen.py`, and the reference-language sketches
  in `reference_languages.py`, are illustrative approximations, not a
  typological database (e.g. PHOIBLE) or authoritative descriptions.
- `reference_languages.py` covers ~8 languages, chosen for typological
  spread, not a general "any named language" capability -- an unmatched
  name is silently ignored.
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
