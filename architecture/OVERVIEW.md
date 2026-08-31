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
- **`traits.py`**: `TraitProfile` -- an LLM-classified, graded (`0.0-1.0`)
  reading of a free-text prompt against a broad set of factors that shape
  real languages (terrain, community structure, contact history, culture,
  aesthetics; non-human/anatomy factors excluded by design). `0.0` means
  "no textual evidence -> use the world-typical base rate," never a
  separate randomization step. A field's value *is* the probability of the
  matching outcome (see `generation/trait_bias.py`) -- it scales all the way
  to near-certainty at `1.0`, it isn't capped short of it. The safety valve
  is the classifier's calibration (rarely reporting values near `1.0`), not
  a mathematical ceiling -- see `generation/prompt_classifier.py`.
  `GRADED_TRAIT_FIELDS` lists the float fields; a handful are consumed by
  generation today (see `generation/` below), the rest are extracted and
  stored for future use. `salient_context` is a free-text catch-all for
  anything the classifier notices that doesn't map to a named field --
  consumed today only as extra flavor context in word-coinage prompts.
- **`spec.py`**: `GenerationSpec` -- the resolved generation request:
  `prompt`, `seed`, `traits: TraitProfile` (LLM-inferred; a confident
  reading behaves close to a guarantee, but it's still inference from
  prose), and `force_isolated`/`force_high_altitude`/`force_tonal`
  (explicit CLI flags only, default `False`) -- a structurally separate,
  unconditional channel that bypasses the probabilistic path entirely
  regardless of the prompt or the classifier's assessment. These two
  channels are deliberately kept apart in code and naming.
- **`language.py`**: `Language` -- the aggregate root (phonology + syllable
  structure + tone system + romanization + grammar + lexicon + spec +
  history log). `with_new_words()` / `with_new_idiom()` are the only
  mutation-shaped operations, both append to `history`.

## `llm/` -- provider-agnostic LLM access

- **`base.py`**: `LLMClient` protocol, `LLMRequest`/`LLMResponse`. Nothing
  outside this package imports a specific SDK.
- **`fake_client.py`**: `FakeLLMClient`, the default everywhere. Reads
  `request.metadata["fake_strategy"]` (`choose_index`, `passthrough`, or
  generic) to fabricate a deterministic response without guessing at prompt
  semantics.
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
  construction (never generates then validates).
- **`trait_bias.py`**: `biased_probability(base_rate, strength) -> float` --
  the single place "graded trait -> probability" logic lives.
  `strength=0` returns `base_rate` unchanged; `strength=1` reaches
  certainty (`1.0`). The strength *is* the intended probability -- there is
  no mathematical ceiling below `1.0`; the classifier is what's expected to
  keep reported strengths near `1.0` rare (see `prompt_classifier.py`). A
  `force_*` flag guarantees an outcome unconditionally, independent of this
  function entirely.
- **`prompt_classifier.py`**: `classify_prompt()` -- one LLM call that reads
  the free-text prompt and returns a `TraitProfile`. The system prompt is
  calibrated specifically against over-eager/cascading inference: rate each
  dimension independently from direct evidence only, default to 0.0, and
  two worked examples anchor "incidental mention" vs. "explicit and
  central" magnitudes. Parsing is lenient (malformed/missing fields degrade
  to "no evidence," never a crash) since LLM JSON isn't a reliable typed
  API.
- **`phonology_gen.py`**: `generate_phonology()`. Illustrative typological
  nudges, all via `biased_probability` (or `1.0` when the matching
  `force_*` flag is set): ejectives from `traits.altitude` (Everett 2013);
  uvulars from `traits.isolation`; tone-system-enabled from
  `traits.tonal_friendliness`; fricative-pool/nasal/affricate selection
  re-weighted by `traits.aesthetic_harshness` (harsh vs. soft "vibe").
  Voiced stops are only added alongside their voiceless counterpart
  (near-universal implicational rule, guaranteed by construction, not
  probabilistic).
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
- **`lexicon_gen.py`**: `CORE_MEANINGS` (the ~47-word core vocabulary) and
  `propose_word()` -- builds candidate forms deterministically, asks the LLM
  to pick one. Shared by both initial generation and later expansion.
- **`generator.py`**: `generate_language()` -- orchestrates the above into
  one `Language`.

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
per AGENTS.md's CLI discipline. See `docs/CLI.md` for verified examples.

## Known v0 limitations (intentional, not oversights)

- Several `TraitProfile` fields are extracted and stored but not yet
  consumed by generation: `social_hierarchy`, `orality_literacy`,
  `evidentiality_culture`, `spatial_reference`, `ritual_register`,
  `taboo_register`, `terrain_communication_distance`,
  `salient_vocabulary_domains`, `contact_languages`, `time_depth_years`.
  `time_depth_years` in particular needs a separate diachronic
  sound-change derivation pipeline from an existing language, not the
  fresh-generation path.
- The typological tendency nudges in `phonology_gen.py`/`grammar_gen.py` are
  a small illustrative set, not a typological database.
- The classifier's calibration (avoiding over-eager or cascading inference
  from incidental prompt details) is prompt-engineered, not testable by a
  unit test -- only checked manually against real prompts through
  `--llm anthropic`.
- Translation recognizes three sentence shapes only; no real syntactic
  parser.
- No idiom generation/matching yet, though `Lexicon.idioms` and
  `Language.with_new_idiom()` already exist for it.
- No custom font generation (long-term idea, explicitly deferred).
