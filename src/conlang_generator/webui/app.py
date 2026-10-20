"""A local JSON API plus static frontend wrapping this project's own
generate/translate core (``generation.generator.generate_language``,
``translation.translator.translate_to_conlang``/``translate_to_english``)
-- a second, independent driver over the same functions ``cli/main.py``
already uses, for smoother interactive testing than the CLI. This module
is API-only; see ``static/index.html`` for the frontend it serves.

Deliberately does not import from ``cli/main.py``: that module's own
``_merge_source_languages``/``_parse_enum_option``/``_parse_seed_example``
helpers exist to parse flat CLI-string syntax (``"French:0.7"``,
``"gloss=form|ipa"``) a JSON request body never needs -- a request here
carries already-structured fields instead, so this module builds
``GenerationSpec``/``OrthographyForce`` directly rather than reusing that
string-parsing layer.

Not installed by default (see the ``web`` dependency group in
``pyproject.toml``) -- run via ``conlang serve`` or directly with
``uvicorn conlang_generator.webui.app:app``.
"""

from __future__ import annotations

import atexit
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.phonology import TONE_CONTOURS, TONE_DIACRITICS, chao_letters
from conlang_generator.core.romanization import (
    ExoticSymbolStyle,
    OrthographyForce,
    SyllableBoundaryMarker,
    ToneMarkingStrategy,
    VowelLengthStrategy,
)
from conlang_generator.core.script import ScriptTraits, ScriptTraitsForce
from conlang_generator.core.spec import GenerationSpec, SeedExample
from conlang_generator.core.traits import EVOLUTION_TRAIT_FIELDS, GRADED_TRAIT_FIELDS, PHONOLOGY_ONLY_TRAIT_FIELDS
from conlang_generator.generation import ipa_tokenizer, phoneme_fit, phonology_gen, script_gen, sound_change
from conlang_generator.generation.generator import (
    generate_evolved_language,
    regenerate_orthography,
    regenerate_phonology,
    regenerate_phonology_adapt_words,
    resolve_evolve_years,
)
from conlang_generator.generation.lexicon_gen import ALL_MEANINGS
from conlang_generator.generation.prompt_classifier import classify_prompt
from conlang_generator.generation.real_words import strictness_warnings
from conlang_generator.generation.reference_languages import (
    REFERENCE_LANGUAGES,
    blend_toward_reference,
    lexicon_audit,
    match_profiles_weighted,
    real_lexicon,
)
from conlang_generator.generation.romanization_gen import ORTHOGRAPHY_STYLE_NAMES
from conlang_generator.generation.seed_examples import (
    CELL_POS,
    parse_bulk_seed_examples,
    parse_seed_forms,
    phonotactic_mismatch_warnings,
    resolve_seed_examples,
    unused_suppletive_form_warnings,
)
from conlang_generator.generation.tone_sandhi import apply_sandhi
from conlang_generator.llm.cost_tracker import CostTracker
from conlang_generator.llm.factory import build_llm_client
from conlang_generator.llm import pricing
from conlang_generator.llm.pricing import DEFAULT_MODEL
from conlang_generator.script import script_render
from conlang_generator.script.font_builder import build_font
from conlang_generator.speech import articulation, engine_selection, sentence_synthesis, tts, tts_cache
from conlang_generator.webui import glossary
from conlang_generator.speech.pregenerate import pregenerate_audio as run_pregenerate_audio
from conlang_generator.speech.sapi_worker import SapiWorker
from conlang_generator.storage.yaml_backend import YamlLanguageRepository
from conlang_generator.translation import names
from conlang_generator.translation.translator import translate_to_conlang, translate_to_english

CACHE_DIR = Path(".cache")
LANGUAGES_DIR = Path("conlangs")
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="ConLangGenerator")

_sapi_worker: SapiWorker | None = None
"""Lazily started on this server's first `"sapi"`/`"auto"` request, then
reused for every request after -- a one-shot `SapiTTSClient` call pays a
real, measured ~3.7s PowerShell-process-startup cost every time; a
`uvicorn` server process is long-lived across many requests, unlike a
single CLI invocation, so this is the one place that cost is worth
paying only once per server run rather than once per request. No
existing FastAPI lifespan hook in this app to extend instead --
`atexit` is simpler for one resource than introducing one just for
this."""


def _get_sapi_worker() -> SapiWorker:
    global _sapi_worker
    if _sapi_worker is None:
        _sapi_worker = SapiWorker()
        atexit.register(_sapi_worker.close)
    return _sapi_worker


_piper_client: tts.PiperTTSClient | None = None
"""Same reasoning as `_sapi_worker` above, for Piper's own real
~2.2-2.4s voice-load cost: lazily built on this server's first
`"piper"`/`"auto"` request, then reused for every request after. No
`atexit` cleanup needed -- `PiperTTSClient` holds no subprocess/file
handle of its own to close, just an in-memory loaded voice."""


def _get_piper_client() -> tts.PiperTTSClient:
    global _piper_client
    if _piper_client is None:
        _piper_client = tts.PiperTTSClient()
    return _piper_client


_SYMBOLS = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)
"""The full global phoneme pool, not any one language's own narrower
inventory -- the same "tokenize against everything this project ever
models, not just what happened to get drawn" pool ``speech/tts.py``'s own
``tones_in``/``strip_tone_marks`` already use, needed here so the lexicon
editor's own free-text IPA field can validate a hand-typed symbol against
every real symbol this project supports, not just this one language's."""


def _repository() -> YamlLanguageRepository:
    return YamlLanguageRepository(LANGUAGES_DIR)


def _client(llm: str):
    try:
        return build_llm_client(kind=llm, cache_dir=CACHE_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _cost_snapshot() -> dict:
    return CostTracker(CACHE_DIR / "cost_ledger.jsonl").summarize()


def _cost_delta(before: dict, after: dict) -> dict:
    """This one request's own marginal spend -- diffed from the cumulative
    ledger rather than tracked directly, so this module never needs to
    touch ``cost_tracker.py``'s own recording path (already wired in via
    ``build_llm_client``'s ``CostTrackingLLMClient`` layer)."""
    return {
        "delta_usd": after["total_cost_usd"] - before["total_cost_usd"],
        "delta_calls": after["num_calls"] - before["num_calls"],
        "total_usd": after["total_cost_usd"],
        "total_calls": after["num_calls"],
    }


def _tone_example(language: Language, level) -> dict | None:
    """The first lexicon entry whose own IPA actually carries ``level``'s
    diacritic (see ``TONE_DIACRITICS``), so a tone badge can show a real
    word from *this* language the same way a sound-inventory badge's own
    click-to-popover already does -- unlike a sound's entry (a fixed,
    curated real-world description), a tone has no language-independent
    "how to pronounce it," so the only real example is one of this
    language's own words. ``None`` for a level no generated word happens
    to carry (small lexicons, or a level only ever reached via sandhi)."""
    mark = TONE_DIACRITICS.get(level)
    if not mark:
        return None
    for entry in language.lexicon.entries:
        if mark in entry.ipa:
            return {"gloss": entry.primary_gloss, "romanization": entry.romanization, "ipa": entry.ipa}
    return None


def _language_summary(language: Language) -> dict:
    """The one view both ``/api/generate`` and ``/api/languages/{slug}``
    return, so the frontend renders a freshly generated language and one
    reloaded from the list identically. Only the "most important"
    characteristics -- full trait/grammar/phonology dumps stay on disk,
    not in this view -- matching ``cli/main.py``'s own "only show
    nonzero traits" restraint."""
    grammar = language.grammar
    traits = language.spec.traits
    nonzero_traits = {
        field: value
        for field, value in traits.model_dump().items()
        if isinstance(value, float) and value != 0.0
    }
    return {
        "name": language.name,
        "slug": language.slug,
        # Already recorded on every `Language` at generation/evolution
        # time (`"generated core language"`, `"evolved N years
        # (seed=...)"`, ...) but never surfaced to the web UI before --
        # pure frontend display, no new backend data.
        "history": list(language.history),
        "grammar": {
            "word_order": grammar.word_order.value,
            "alignment": grammar.alignment.value,
            "morphological_type": grammar.morphological_type.value,
            "has_articles": grammar.has_articles,
            "has_overt_copula": grammar.has_overt_copula,
            "adjective_after_noun": grammar.adjective_after_noun,
            "cases": list(grammar.cases),
            "tenses": list(grammar.tenses),
            "tonal": language.tone_system.enabled,
            "word_selection": language.spec.word_selection,
            "word_formation": language.spec.word_formation,
            "foreign_names": names.resolve_foreign_names(language),
            "evolved_years": resolve_evolve_years(language.spec) if any(h.startswith("evolved") for h in language.history) else 0,
        },
        "traits": {
            **nonzero_traits,
            "source_languages": list(traits.source_languages),
            "source_language_strictness": traits.source_language_strictness,
            "salient_context": traits.salient_context,
        },
        "orthography_category": language.romanization.category_name,
        # Recorded at generation time (`GenerationSpec.classifier_model`/
        # `word_selection_model`) but never surfaced to the web UI before
        # the "Generation Details" summary section needed them.
        "classifier_model": language.spec.classifier_model,
        "word_selection_model": language.spec.word_selection_model,
        # Empty lists for a non-tonal language (ToneSystem's own default
        # shape), not omitted -- the frontend only renders this section
        # when `grammar.tonal` is true, so an always-present, empty-when-
        # irrelevant shape is simpler than a nullable field. `contour`/
        # `digits` are the same real Chao (1930) pitch-level data
        # `speech.reader.describe()` already prints for the CLI -- was
        # backend-only before this (see architecture/OVERVIEW.md's own
        # "Not done" note on this exact gap).
        "tone_system": {
            "levels": [
                {
                    "level": level.value,
                    "contour": chao_letters(level),
                    "digits": TONE_CONTOURS.get(level, ""),
                    "example": _tone_example(language, level),
                }
                for level in language.tone_system.levels
            ],
            "sandhi": [
                {"before": r.before.value, "after": r.after.value, "becomes": r.becomes.value, "target": r.target}
                for r in language.tone_system.sandhi
            ],
            "lexical_sandhi": [
                {"gloss": r.gloss, "before": r.before.value, "becomes": r.becomes.value}
                for r in language.tone_system.lexical_sandhi
            ],
        },
        "phoneme_inventory": [e.as_dict() for e in articulation.full_inventory(language)],
        # None when this language has no invented script (the common
        # case -- see core.script's own module docstring); the frontend
        # only shows the "own script" section/toggle when this is set.
        "script": (
            {
                "direction": language.script.direction.value,
                "glyph_count": len(language.script.glyphs),
                # All 15, not just the nonzero ones (unlike `nonzero_traits`
                # above) -- a ScriptTraits dial is rolled from a continuous
                # uniform draw, so every one of them is a real, meaningful
                # reading, not "0 = no opinion" the worldbuilding traits'
                # own default means.
                "traits": language.script.traits.model_dump(),
            }
            if language.script is not None
            else None
        ),
        # `entry.real_word` (not `entry.notes`, which an evolution step
        # overwrites to an "orthography: ..." tag regardless of a word's
        # own real origin) survives any number of evolution steps --
        # see `core/lexicon.py`'s own `RealWordOrigin` docstring.
        "real_words": sum(1 for e in language.lexicon.entries if e.real_word is not None),
        "lexicon": [
            {
                "gloss": entry.primary_gloss,
                "pos": entry.pos.value,
                "romanization": entry.romanization,
                "ipa": entry.ipa,
                # Real citation-form sandhi (Mandarin's own third-tone
                # rule, real Meeussen's Rule, etc.) can fire *within* a
                # single multi-syllable word's own tone sequence -- each
                # word is its own isolated one-word "utterance" here
                # (never batched across the whole lexicon, which would
                # wrongly apply cross-word sandhi between unrelated
                # dictionary entries that just happen to sit next to
                # each other in this list), so a per-row "play" button
                # hears the same real spoken form `cli/main.py`'s own
                # `pronounce` command already produces for this word.
                "spoken_ipa": apply_sandhi([entry.ipa], language.tone_system, [entry.primary_gloss])[0],
                "provenance": (
                    f"real {entry.real_word.language}: {entry.real_word.form} [{entry.real_word.ipa}]"
                    if entry.real_word is not None
                    else None
                ),
                "script_text": script_render.render_word(language.script, entry.ipa) if language.script else None,
            }
            for entry in sorted(language.lexicon.entries, key=lambda e: e.primary_gloss)
        ],
    }


def _parse_enum(raw: str | None, enum_cls: type, field: str):
    """Same "look up by member *name*, uppercased" lookup ``cli/main.py``'s
    own ``_parse_enum_option`` uses -- not by ``.value`` -- since
    ``SyllableBoundaryMarker.NONE`` deliberately has ``value == ""``
    (doubles as the literal marker text), so a value-based lookup of the
    CLI-typed word "none" wouldn't resolve."""
    if raw is None:
        return None
    try:
        return enum_cls[raw.upper()]
    except KeyError:
        valid = ", ".join(member.name.lower() for member in enum_cls)
        raise HTTPException(status_code=400, detail=f"{field} must be one of {valid}, got {raw!r}") from None


class SourceLanguageEntry(BaseModel):
    name: str
    weight: float | None = None


class EvolveSourceLanguageEntry(BaseModel):
    name: str
    intensity: float
    """How much this specific source language actively reshapes the
    language during this evolution run -- not Generate's own `weight`
    (a relative blend proportion among several sources, used to bias a
    palette), but an absolute contact-pressure dial `EvolveRequest`'s
    own docstring explains in full. Required, no default: a silently
    defaulted intensity would make it too easy to introduce heavy,
    unintended contact just by adding a source language without
    thinking about how strong it should be."""


class SeedExampleEntry(BaseModel):
    gloss: str
    form: str
    ipa: str | None = None
    pos: str | None = None
    forms: str | None = None
    """One or more of this word's own irregular (suppletive) forms, in
    ``generation.seed_examples.parse_seed_forms``'s ``;``-separated
    ``cell:form[:ipa]`` syntax -- a form whose cell doesn't match ``pos``
    is dropped, the same lenient handling as the bulk-paste field."""


class GenerateRequest(BaseModel):
    prompt: str
    name: str
    seed: int = 0
    llm: str = "fake"
    tonal: bool = False
    own_script: str = "auto"
    """"auto" (infer from the prompt), "yes", or "no" -- see
    ``generation.script_gen.should_generate_script``."""
    source_languages: list[SourceLanguageEntry] = []
    strictness: float | None = None
    examples: list[SeedExampleEntry] = []
    examples_text: str | None = None
    """Bulk-paste seed words, one per line: gloss,form[,ipa[,pos[,forms]]]
    -- see ``generation.seed_examples.parse_bulk_seed_examples``. Combined
    with ``examples`` (that list's own rows are applied after this text's)."""
    orthography_style: str | None = None
    exotic_symbol_style: str | None = None
    vowel_length_style: str | None = None
    short_vowel_doubling: bool | None = None
    tone_style: str | None = None
    syllable_boundary_marker: str | None = None
    consonant_gemination_marked: bool | None = None
    allow_all_caps: bool = False
    word_selection: str = "algorithmic"
    word_formation: str = "algorithmic"
    model: str = DEFAULT_MODEL
    """Model for prompt classification."""
    word_model: str = DEFAULT_MODEL
    """Model for word selection/coinage -- used at generation time and
    reused for any word coined later during translation."""
    vocabulary_size: int = 400
    foreign_names: str | None = None
    word_strictness: float | None = None
    evolve_years: int | None = None
    pregenerate_audio: str = "none"
    """Eagerly synthesize+cache every lexicon word's own pronunciation
    right after generating -- none/espeak/sapi/piper/auto. "sapi"/"auto"
    used to measure ~3.7s/word (a fresh PowerShell+.NET startup cost on
    every one-shot call), too slow for a synchronous request; `speech.
    pregenerate.pregenerate_audio` now shares one persistent `speech.
    sapi_worker.SapiWorker` across the whole lexicon instead (confirmed:
    a full 400-word vocabulary takes ~2.7s total, not tens of minutes),
    so all these values are accepted here now."""
    trait_overrides: dict[str, float] = {}
    """Directly set one or more graded worldbuilding traits (the web
    equivalent of the CLI's own repeatable ``--trait NAME=VALUE``) --
    key one of ``GRADED_TRAIT_FIELDS``, value -1.0..1.0, overriding
    that trait's own prompt-inferred value. Deliberately excludes
    ``source_language_strictness``/``source_word_strictness`` -- those
    already have their own dedicated ``strictness``/``word_strictness``
    fields above, one way to set each rather than two, the same
    exclusion ``cli/main.py``'s own ``_parse_trait_overrides`` makes."""
    script_trait_overrides: dict[str, float] = {}
    """Directly set one or more invented-script style dials (the web
    equivalent of the CLI's own repeatable ``--script-trait NAME=VALUE``)
    -- key one of ``ScriptTraits.model_fields``, value -1.0..1.0,
    overriding that dial's own seeded roll. Only takes effect when a
    script is actually generated (see ``own_script``)."""


class TranslateRequest(BaseModel):
    lang: str
    text: str
    to: str = "conlang"
    llm: str = "fake"
    translate_model: str = DEFAULT_MODEL
    """Model for sentence planning and (decode direction) fluency."""


@app.get("/api/languages")
def list_languages() -> dict:
    repo = _repository()
    slugs = repo.list()
    # A cheap per-language check (one small script.yaml read, not a full
    # language load) -- the Script tab's own language picker uses this to
    # grey out/italicize a language with none, without a round trip per
    # option.
    return {"languages": slugs, "scripted_languages": [slug for slug in slugs if repo.has_script(slug)]}


@app.get("/api/languages/{slug}")
def get_language(slug: str) -> dict:
    try:
        language = _repository().load(slug)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _language_summary(language)


@app.get("/api/languages/{slug}/sounds")
def get_word_sounds(slug: str, word: str) -> dict:
    """The word-scoped tier of the pronunciation guide -- the full,
    per-language tier already rides along on ``_language_summary``'s
    own ``phoneme_inventory`` field, so this endpoint only ever needs to
    filter/order by one specific word's own IPA."""
    try:
        language = _repository().load(slug)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not word.strip():
        raise HTTPException(status_code=400, detail="word must not be empty")
    return {"slug": slug, "word": word, "sounds": [e.as_dict() for e in articulation.word_inventory(language, word)]}


@app.get("/api/languages/{slug}/export")
def export_language(slug: str) -> Response:
    """The whole language, not the trimmed ``_language_summary`` view --
    everything ``YamlLanguageRepository.save`` would otherwise split
    across its own 5 files on disk (``model_dump`` doesn't care that the
    repository happens to store it that way), as one downloadable JSON
    file re-importable by ``import_language`` below, on this same
    install or someone else's."""
    try:
        language = _repository().load(slug)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    body = json.dumps(language.model_dump(mode="json"), indent=2, ensure_ascii=False)
    return Response(
        content=body, media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{language.slug}.json"'},
    )


@app.get("/api/languages/{slug}/script/font")
def get_script_font(slug: str) -> Response:
    """The language's own invented script, compiled to a real .ttf --
    served inline (no attachment header) so the frontend can load it
    straight into an ``@font-face`` rule; cached to disk under
    ``CACHE_DIR / "fonts"`` since a saved language's own script never
    changes, the same build-once-serve-many-times spirit
    ``speech.tts_cache`` already has for audio."""
    try:
        language = _repository().load(slug)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if language.script is None:
        raise HTTPException(status_code=404, detail=f"'{slug}' has no invented script")
    font_path = CACHE_DIR / "fonts" / f"{slug}.ttf"
    if not font_path.is_file():
        build_font(language.script, font_path, language.name)
    return Response(
        content=font_path.read_bytes(),
        media_type="font/ttf",
        headers={"Content-Disposition": f'inline; filename="{slug}.ttf"'},
    )


@app.get("/api/languages/{slug}/script/keyboard")
def get_script_keyboard(slug: str) -> dict:
    """What a user types to produce each of this language's own glyphs
    (a single key, or a short multi-key sequence -- see
    ``script_render.assign_keyboard_triggers``), and what that glyph
    means (IPA + romanization) -- the web UI's own Script tab builds
    both its reference legend and its live-typing transliteration from
    this single call, no per-keystroke round trip."""
    try:
        language = _repository().load(slug)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if language.script is None:
        raise HTTPException(status_code=404, detail=f"'{slug}' has no invented script")
    return {
        "slug": slug,
        "direction": language.script.direction.value,
        "keys": script_render.keyboard_layout(language.script, language.romanization),
    }


class ImportLanguageRequest(BaseModel):
    data: dict
    overwrite: bool = False


@app.post("/api/languages/import")
def import_language(request: ImportLanguageRequest) -> dict:
    """The reverse of ``export_language`` above -- ``request.data`` is
    exactly what that endpoint's own download contains (or, in
    principle, a hand-edited variant of it; this is a real validating
    parse via ``Language.model_validate``, not a trusting passthrough).
    Refuses to silently clobber an already-saved language with the same
    name -- ``overwrite`` must be explicit, the same "look before
    overwriting" discipline every destructive action in this project
    already follows, just enforced here rather than left to the browser
    file-picker's own save dialog to (not) catch."""
    try:
        language = Language.model_validate(request.data)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"not a valid exported language file: {exc}") from exc
    repository = _repository()
    if repository.exists(language.name) and not request.overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"a language named '{language.name}' already exists -- confirm to overwrite it",
        )
    repository.save(language)
    return _language_summary(language)


class LexiconEditRequest(BaseModel):
    gloss: str
    romanization: str | None = None
    ipa: str | None = None


@app.post("/api/languages/{slug}/lexicon/edit")
def edit_lexicon_entry(slug: str, request: LexiconEditRequest) -> dict:
    """A user-driven correction to one already-saved word's own spelling
    and/or pronunciation -- deliberately *not* auto-re-deriving the other
    field from whichever one changed (real irregular spellings exist;
    this hands the user full, direct control of both independently,
    rather than guessing which one they'd want recomputed). Re-saves the
    whole language, the same "load, mutate, save back" shape
    ``translator.py``'s own word-coinage path already uses."""
    repository = _repository()
    try:
        language = repository.load(slug)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    entry = language.lexicon.by_gloss(request.gloss)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"{request.gloss!r} is not in {slug}'s lexicon")
    if request.romanization is None and request.ipa is None:
        raise HTTPException(status_code=400, detail="provide romanization and/or ipa to edit")

    updates: dict = {}
    if request.romanization is not None:
        romanization = request.romanization.strip()
        if not romanization:
            raise HTTPException(status_code=400, detail="romanization must not be empty")
        updates["romanization"] = romanization
    if request.ipa is not None:
        ipa = request.ipa.strip()
        if not ipa:
            raise HTTPException(status_code=400, detail="ipa must not be empty")
        tokens = ipa_tokenizer.tokenize(ipa, _SYMBOLS)
        if "".join(symbol + deco for symbol, deco in tokens) != ipa:
            raise HTTPException(status_code=400, detail="ipa contains a symbol this project doesn't model")
        updates["ipa"] = ipa
        # tones is its own stored field, not re-derived from ipa on every
        # read (see LexicalEntry.tones's own docstring) -- a hand-edited
        # ipa needs this recomputed explicitly, or every other tone-aware
        # consumer (pronunciation, sandhi) would keep reading the old,
        # now-stale tone sequence.
        updates["tones"] = ipa_tokenizer.tone_sequence(ipa, _SYMBOLS)
    if "(manually edited)" not in entry.notes:
        updates["notes"] = f"{entry.notes} (manually edited)".strip()

    updated_entry = entry.model_copy(update=updates)
    updated_language = language.with_edited_entry(
        entry.primary_gloss, updated_entry, reason=f"manually edited '{entry.primary_gloss}'"
    )
    repository.save(updated_language)
    return _language_summary(updated_language)


@app.get("/api/reference-languages")
def list_reference_languages() -> dict:
    """Every curated real language with an actual lexicon to browse --
    ``real_lexicon.curated_profiles`` already excludes a profile that
    exists (typology only) but has no ``lexicons/<name>.yaml`` of its
    own, the same "abstain, don't show an empty browse view" discipline
    ``conlang audit-lexicons`` already applies."""
    return {
        "languages": [
            {"name": p.name, "words": len(real_lexicon.real_words(p.name)), "tonal": p.tonal}
            for p in real_lexicon.curated_profiles()
        ]
    }


@app.get("/api/reference-languages/{name}/lexicon")
def get_reference_lexicon(name: str) -> dict:
    """A curated real language's own actual words -- read-only (unlike a
    generated language's own lexicon, "editing" this means editing its
    own YAML source file, a dev workflow, not a web-UI one; see
    ``docs/DEFERRED.md`` §8). Each entry's own ``flagged`` reuses
    ``lexicon_audit.audit_language`` (the same check `conlang
    audit-lexicons` runs) -- a transcription slip or a profile missing
    something the language really has, visible per word here rather
    than only as an aggregate count on the CLI. A loanword (``loan``)
    isn't held to the language's own native phonotactics by default,
    the same real linguistic exemption the CLI audit already grants it
    (a loanword legitimately can use clusters/sounds the native
    inventory otherwise bars), so it's never ``flagged`` on that basis
    alone."""
    profile = next((p for p in REFERENCE_LANGUAGES if p.name == name), None)
    words = real_lexicon.real_words(name)
    if profile is None or not words:
        raise HTTPException(status_code=404, detail=f"no curated lexicon for {name!r}")
    loans = real_lexicon.loan_glosses(name)
    audit = lexicon_audit.audit_language(profile)
    flagged_detail = {issue.gloss: issue.detail for issue in audit.off_inventory + audit.structure}
    return {
        "name": profile.name,
        "words": [
            {
                "gloss": gloss,
                "spelling": spelling,
                "ipa": ipa,
                "loan": gloss in loans,
                "flagged": flagged_detail.get(gloss),
            }
            for gloss, (spelling, ipa) in sorted(words.items())
        ],
    }


@app.get("/api/cost")
def get_cost() -> dict:
    return _cost_snapshot()


@app.post("/api/cost/reset")
def reset_cost() -> dict:
    """Permanently discards every recorded LLM call -- also empties the
    Log tab's own history, since both read the same ledger file. The
    frontend confirms with the user before calling this; nothing here
    guards against an accidental call, same as any other explicit
    user-initiated reset."""
    CostTracker(CACHE_DIR / "cost_ledger.jsonl").reset()
    return _cost_snapshot()


@app.get("/api/llm-log")
def get_llm_log(limit: int = 300) -> dict:
    """The actual request/response text for the most recent LLM calls
    (fake backend included -- it's still wrapped in `CostTrackingLLMClient`,
    just at `cost_usd=0.0`), newest first -- see docs/DEFERRED.md's "See
    the actual LLM prompts used for a translation" item. Empty (not an
    error) for a fresh session with no calls recorded yet."""
    return {"entries": CostTracker(CACHE_DIR / "cost_ledger.jsonl").list_entries(limit)}


_MODEL_LABELS = {
    "claude-haiku-4-5-20251001": "Haiku 4.5",
    "claude-sonnet-5": "Sonnet 5",
    "claude-opus-5": "Opus 5.5",
    "claude-fable-5": "Fable 5",
}
"""Real, paid models a user can pick -- excludes ``"fake-llm"`` (no price,
not a real choice) from ``pricing.PRICE_PER_MILLION_TOKENS``."""


@app.get("/api/options")
def get_options() -> dict:
    """The valid values for every orthography-force select the frontend
    renders -- fetched rather than hardcoded into ``static/index.html``,
    since ``ORTHOGRAPHY_STYLE_NAMES`` in particular is built dynamically
    from ``romanization_gen``'s own named-preset dict, not a fixed list
    safe to duplicate."""
    return {
        "orthography_styles": list(ORTHOGRAPHY_STYLE_NAMES),
        "exotic_symbol_styles": [m.name.lower() for m in ExoticSymbolStyle],
        "vowel_length_styles": [m.name.lower() for m in VowelLengthStrategy],
        "tone_styles": [m.name.lower() for m in ToneMarkingStrategy],
        "syllable_boundary_markers": [m.name.lower() for m in SyllableBoundaryMarker],
        "tts_backends": tts.available_backends(),
        "tts_capabilities": tts.backend_capabilities(),
        "max_vocabulary_size": len(ALL_MEANINGS),
        "graded_trait_fields": list(GRADED_TRAIT_FIELDS),
        "phonology_only_trait_fields": list(PHONOLOGY_ONLY_TRAIT_FIELDS),
        "evolution_trait_fields": list(EVOLUTION_TRAIT_FIELDS),
        # Direct user request from a deep-dive review: typing a source
        # language the curated reference-language matcher (generation.
        # reference_languages.match_profiles) doesn't recognize -- by name
        # or alias, case-insensitively -- has it silently ignored
        # everywhere a source language is consulted (phoneme-inventory
        # bias, romanization convention, real-word sourcing), with no
        # feedback that it had zero effect. source_language_names (the
        # curated display names, for a <datalist>) and source_language_
        # matchable_names (every name *and* alias, lowercased, for
        # client-side "does this match?" checking) let the web UI surface
        # that distinction without duplicating the matcher's own logic --
        # any free-text name still works exactly as before; this is
        # purely an added feedback layer.
        "source_language_names": sorted(p.name for p in REFERENCE_LANGUAGES),
        "source_language_matchable_names": sorted(
            {p.name.lower() for p in REFERENCE_LANGUAGES} | {alias for p in REFERENCE_LANGUAGES for alias in p.aliases}
        ),
        "script_trait_fields": list(ScriptTraits.model_fields),
        "glossary": glossary.as_dict(),
        "models": [
            {
                "id": model_id,
                "label": label,
                "provider": "Anthropic",
                "price_per_million": {
                    "input": pricing.PRICE_PER_MILLION_TOKENS[model_id][0],
                    "output": pricing.PRICE_PER_MILLION_TOKENS[model_id][1],
                },
                "estimated_price": {
                    "classifier": pricing.estimated_price(model_id, "classifier"),
                    "word_selection": pricing.estimated_price(model_id, "word_selection"),
                    "translation": pricing.estimated_price(model_id, "translation"),
                    "word_formation": pricing.estimated_price(model_id, "word_formation"),
                },
            }
            for model_id, label in _MODEL_LABELS.items()
        ],
    }


@app.post("/api/generate")
def generate(request: GenerateRequest) -> dict:
    if request.orthography_style is not None and request.orthography_style not in ORTHOGRAPHY_STYLE_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"orthography_style must be one of {', '.join(ORTHOGRAPHY_STYLE_NAMES)}, got {request.orthography_style!r}",
        )
    if request.evolve_years is not None and not 0 <= request.evolve_years <= 100000:
        raise HTTPException(status_code=400, detail="evolve_years must be between 0 and 100000")
    if request.word_strictness is not None and not 0.0 <= request.word_strictness <= 1.0:
        raise HTTPException(status_code=400, detail="word_strictness must be between 0.0 and 1.0")
    if request.strictness is not None and not 0.0 <= request.strictness <= 1.0:
        raise HTTPException(status_code=400, detail="strictness must be between 0.0 and 1.0")
    if not 1 <= request.vocabulary_size <= len(ALL_MEANINGS):
        raise HTTPException(status_code=400, detail=f"vocabulary_size must be between 1 and {len(ALL_MEANINGS)}")
    if request.foreign_names not in (None, "keep", "adapt"):
        raise HTTPException(status_code=400, detail="foreign_names must be 'keep' or 'adapt' (or omitted)")
    if request.word_selection not in ("algorithmic", "llm"):
        raise HTTPException(status_code=400, detail="word_selection must be 'algorithmic' or 'llm'")
    if request.word_formation not in ("algorithmic", "llm"):
        raise HTTPException(status_code=400, detail="word_formation must be 'algorithmic' or 'llm'")
    if request.pregenerate_audio not in ("none", "espeak", "sapi", "piper", "auto"):
        raise HTTPException(
            status_code=400, detail="pregenerate_audio must be 'none', 'espeak', 'sapi', 'piper' or 'auto'"
        )
    if request.own_script not in ("auto", "yes", "no"):
        raise HTTPException(status_code=400, detail="own_script must be 'auto', 'yes', or 'no'")
    force_own_script = None if request.own_script == "auto" else request.own_script == "yes"
    unknown_traits = set(request.trait_overrides) - set(GRADED_TRAIT_FIELDS)
    if unknown_traits:
        raise HTTPException(
            status_code=400,
            detail=f"trait_overrides has unknown trait name(s): {', '.join(sorted(unknown_traits))}",
        )
    out_of_range = {k: v for k, v in request.trait_overrides.items() if not -1.0 <= v <= 1.0}
    if out_of_range:
        raise HTTPException(status_code=400, detail=f"trait_overrides values must be between -1.0 and 1.0: {out_of_range}")
    unknown_script_traits = set(request.script_trait_overrides) - set(ScriptTraits.model_fields)
    if unknown_script_traits:
        raise HTTPException(
            status_code=400,
            detail=f"script_trait_overrides has unknown dial name(s): {', '.join(sorted(unknown_script_traits))}",
        )
    script_out_of_range = {k: v for k, v in request.script_trait_overrides.items() if not -1.0 <= v <= 1.0}
    if script_out_of_range:
        raise HTTPException(
            status_code=400, detail=f"script_trait_overrides values must be between -1.0 and 1.0: {script_out_of_range}"
        )

    forced_orthography = OrthographyForce(
        style=request.orthography_style,
        exotic_symbol_style=_parse_enum(request.exotic_symbol_style, ExoticSymbolStyle, "exotic_symbol_style"),
        vowel_length_strategy=_parse_enum(request.vowel_length_style, VowelLengthStrategy, "vowel_length_style"),
        short_vowel_consonant_doubling=request.short_vowel_doubling,
        tone_strategy=_parse_enum(request.tone_style, ToneMarkingStrategy, "tone_style"),
        syllable_boundary_marker=_parse_enum(
            request.syllable_boundary_marker, SyllableBoundaryMarker, "syllable_boundary_marker"
        ),
        consonant_gemination_marked=request.consonant_gemination_marked,
    )

    client = _client(request.llm)
    before = _cost_snapshot()

    traits = classify_prompt(request.prompt, client, model=request.model)
    if request.source_languages:
        names = tuple(e.name for e in request.source_languages)
        weights = tuple(e.weight if e.weight is not None else 1.0 for e in request.source_languages)
        traits = traits.model_copy(update={"source_languages": names, "source_language_weights": weights})
    if request.strictness is not None:
        traits = traits.model_copy(update={"source_language_strictness": request.strictness})
    if request.word_strictness is not None:
        traits = traits.model_copy(update={"source_word_strictness": request.word_strictness})
    # Grading reference languages on worldbuilding traits: nudges the
    # classifier's own trait reading toward whatever matched source
    # language(s) have curated as their own typical reading -- reuses
    # source_language_strictness as the blend weight rather than a new
    # dial (see blend_toward_reference's own docstring). Applied before
    # trait_overrides so an explicit override always wins outright.
    traits = blend_toward_reference(
        traits, match_profiles_weighted(traits.source_languages, traits.source_language_weights),
        traits.source_language_strictness,
    )
    if request.trait_overrides:
        traits = traits.model_copy(update=request.trait_overrides)

    text_examples = parse_bulk_seed_examples(request.examples_text) if request.examples_text else ()
    row_examples = []
    for e in request.examples:
        pos = _parse_enum(e.pos, PartOfSpeech, "examples[].pos")
        forms = (
            tuple(f for f in parse_seed_forms(e.forms) if CELL_POS.get(f.cell) is (pos or PartOfSpeech.NOUN))
            if e.forms else ()
        )
        row_examples.append(SeedExample(gloss=e.gloss, form=e.form, ipa=e.ipa, pos=pos, forms=forms))
    row_examples = tuple(row_examples)
    raw_examples = text_examples + row_examples
    seed_examples = resolve_seed_examples(raw_examples, client, model=request.word_model)

    spec = GenerationSpec(
        prompt=request.prompt,
        seed=request.seed,
        traits=traits,
        force_tonal=request.tonal,
        force_own_script=force_own_script,
        forced_orthography=forced_orthography,
        forced_script_traits=ScriptTraitsForce(**request.script_trait_overrides),
        seed_examples=seed_examples,
        allow_all_caps=request.allow_all_caps,
        word_selection=request.word_selection,
        word_formation=request.word_formation,
        classifier_model=request.model,
        word_selection_model=request.word_model,
        vocabulary_size=request.vocabulary_size,
        foreign_names=request.foreign_names,
        evolve_years=request.evolve_years,
    )
    language = generate_evolved_language(request.name, spec, client)
    _repository().save(language)

    after = _cost_snapshot()
    summary = _language_summary(language)
    summary["cost"] = _cost_delta(before, after)
    summary["warnings"] = (
        strictness_warnings(traits) + phonotactic_mismatch_warnings(language)
        + unused_suppletive_form_warnings(language)
    )
    if request.pregenerate_audio != "none":
        pregenerated = run_pregenerate_audio(language, request.pregenerate_audio, CACHE_DIR)
        summary["pregenerated_audio"] = {
            "total": pregenerated.total, "synthesized": pregenerated.synthesized, "failed": pregenerated.failed,
        }
    return summary


class TweakRequest(BaseModel):
    name: str
    """Where the tweaked result is saved -- a new, separate language,
    same "source is never overwritten" precedent `--tweak-from`'s own
    CLI twin (`cli/main.py`) already follows; reusing the source
    language's own name here overwrites it, the same pre-existing
    behavior `/api/generate` itself already has for a name collision."""
    trait_overrides: dict[str, float] = {}
    """Restricted to `PHONOLOGY_ONLY_TRAIT_FIELDS` -- any other key is
    rejected outright (see `generation.generator.regenerate_phonology`'s
    own docstring for why only these three)."""
    words: str = "regenerate"
    """'regenerate' (recoin the lexicon fresh against the new phonology)
    or 'adapt' (re-fit each existing word's own IPA to the new phonology
    instead, so it stays traceably the same word)."""
    llm: str = "fake"
    orthography_style: str | None = None
    exotic_symbol_style: str | None = None
    vowel_length_style: str | None = None
    short_vowel_doubling: bool | None = None
    tone_style: str | None = None
    syllable_boundary_marker: str | None = None
    consonant_gemination_marked: bool | None = None
    """"Tweaking an existing language" item 9 (`docs/DEFERRED.md`): any of
    these set (non-`None`) tweaks Roman Orthography instead of phonology
    -- the two axes can't be combined in the same request (see
    `generation.generator.regenerate_orthography`'s own docstring for
    why: romanization draws from the same shared `rng` stream grammar/
    lexicon coining also draw from, so changing it inside the same
    `generate_language` call phonology-tweaking itself makes would also
    shift grammar/lexicon, not just the spelling). `trait_overrides`/
    `words` are ignored when any of these is set; chain two separate
    tweak requests to change both axes."""
    dry_run: bool = False
    """"Tweaking an existing language" item 7 (`docs/DEFERRED.md`):
    compute the tweaked language exactly as normal, but don't save it --
    lets the web UI's own Tweak tab show a word-by-word before/after
    preview and let the user decide whether to actually commit it.
    `regenerate_phonology`/`regenerate_phonology_adapt_words` are both
    deterministic (same inputs -> same output, see their own
    reproducibility tests), so a client that likes what it previewed
    just POSTs the exact same body again with `dry_run=false` -- no
    server-side preview state to track or expire."""


@app.post("/api/languages/{slug}/tweak")
def tweak_language(slug: str, request: TweakRequest) -> dict:
    """"Tweaking an existing language" item 6 (`docs/DEFERRED.md`) --
    the web UI's own Tweak tab backing endpoint, mirroring `/api/generate`'s
    own response shape exactly so the result renders through the
    already-existing `showInspectResult`/`renderLanguageSummary`
    unchanged, a tweaked language being just a `Language` like any
    other. `dry_run=true` (item 7) computes but never saves."""
    if request.words not in ("regenerate", "adapt"):
        raise HTTPException(status_code=400, detail="words must be 'regenerate' or 'adapt'")
    try:
        base = _repository().load(slug)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    client = _client(request.llm)
    before = _cost_snapshot()
    orthography_overrides = OrthographyForce(
        style=request.orthography_style,
        exotic_symbol_style=_parse_enum(request.exotic_symbol_style, ExoticSymbolStyle, "exotic_symbol_style"),
        vowel_length_strategy=_parse_enum(request.vowel_length_style, VowelLengthStrategy, "vowel_length_style"),
        short_vowel_consonant_doubling=request.short_vowel_doubling,
        tone_strategy=_parse_enum(request.tone_style, ToneMarkingStrategy, "tone_style"),
        syllable_boundary_marker=_parse_enum(
            request.syllable_boundary_marker, SyllableBoundaryMarker, "syllable_boundary_marker"
        ),
        consonant_gemination_marked=request.consonant_gemination_marked,
    )
    try:
        if orthography_overrides != OrthographyForce():
            language = regenerate_orthography(request.name, base, orthography_overrides, client)
        else:
            regenerate = regenerate_phonology if request.words == "regenerate" else regenerate_phonology_adapt_words
            language = regenerate(request.name, base, request.trait_overrides, client)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not request.dry_run:
        _repository().save(language)

    after = _cost_snapshot()
    summary = _language_summary(language)
    summary["cost"] = _cost_delta(before, after)
    summary["warnings"] = phonotactic_mismatch_warnings(language) + unused_suppletive_form_warnings(language)
    summary["saved"] = not request.dry_run
    # "Tweaking Phase 2": which old sound now maps to which new one, by
    # feature distance -- the same per-symbol match regenerate_phonology_
    # adapt_words' own fit_ipa already uses internally, surfaced directly
    # so the preview can show it without the user having to infer it from
    # individual word diffs.
    summary["sound_correspondence"] = phoneme_fit.sound_correspondence(base.phonology, language.phonology)
    return summary


class EvolveRequest(BaseModel):
    name: str
    """Where the evolved result is saved -- a new, separate language,
    same "source is never overwritten" precedent every other tweak-
    family endpoint already follows."""
    years: int
    """Must be > 0 -- unlike the combined generate+evolve path's own
    "0 = none" convenience default, a dedicated Evolve action with
    nothing to do isn't a meaningful request."""
    trait_overrides: dict[str, float] = {}
    """Unlike `TweakRequest.trait_overrides`, **no allowlist**:
    `sound_change.evolve_language` never re-rolls grammar typology
    (word order, alignment, morphological_type, word_classes) the way
    fresh generation does -- confirmed by reading `_evolve_grammar_
    affixes` (only evolves existing affixes' own *spelling*, never
    calls `grammar_gen.generate_grammar`/`word_class_gen.
    generate_word_classes`) -- so every one of the 15 `GRADED_TRAIT_
    FIELDS` is safe to change here, unlike `regenerate_phonology`'s own
    `PHONOLOGY_ONLY_TRAIT_FIELDS` restriction."""
    source_languages: list[EvolveSourceLanguageEntry] = []
    """New contact language(s) to introduce during this evolution run,
    merged *additively* with the base language's own existing lineage
    by `evolve_language` itself (confirmed: `lineage_languages = tuple(
    dict.fromkeys((*base.spec.traits.source_languages, *traits.
    source_languages)))`, sound_change.py) -- never replaces it.

    Unlike Generate's own `source_languages` (a relative blend
    proportion, `SourceLanguageEntry.weight`), each entry's own
    `intensity` here is an *absolute* contact-pressure dial: 0.1 always
    means "mild," regardless of how many other source languages are
    also active, and 0.1 among five other 0.1s is not a fifth of
    anything. The SUM of every entry's own intensity in one request
    must not exceed 1.0 -- "the maximum influence imaginable without
    this language losing its own identity entirely," not a target to
    reach (ordinary contact should sit well below it). This sum becomes
    this run's own `contact_intensity` trait value directly (see
    `core.traits.TraitProfile.contact_intensity`'s own docstring --
    already read throughout `sound_change.py`'s evolution mechanics:
    phoneme-inventory gain/loss, lexical-replacement rate, orthography
    reform/drift speed, native-word accent fidelity, and tonal-language
    detonalization chance), which is why `trait_overrides` is rejected
    outright if it also tries to set `contact_intensity` directly
    alongside a nonempty `source_languages` here -- it would be
    ambiguous which one wins. Direct user request: "sound strictness
    should be removed from evolution... introduce words from the
    source languages slowly, as well as take over phonology, grammar
    etc., with a particular speed based on weight... Contact intensity
    should follow directly from the sum of intensities of source
    languages." See `docs/DEFERRED.md` ch. 13 for the full history --
    including why this is deliberately *not* cumulative across separate
    evolution runs (a language's own prior contact history doesn't
    count toward this run's own 1.0 ceiling)."""
    llm: str = "fake"
    dry_run: bool = False
    """Same "compute but don't save" contract every other tweak-family
    endpoint already has."""


@app.post("/api/languages/{slug}/evolve")
def evolve_language_endpoint(slug: str, request: EvolveRequest) -> dict:
    """"Language evolution" restructuring (`docs/DEFERRED.md`, chapter
    11) -- the web UI's own Evolve tab backing endpoint, the first place
    evolving an *already-saved* language is possible outside the CLI's
    own `generate --evolve-from`. Trait-resolution shape: start from the
    base language's own traits, merge in any new `source_languages`
    (deriving `contact_intensity` as their own capped intensity sum --
    see `EvolveRequest.source_languages`'s own docstring, ch. 13), blend
    toward matched reference profiles by that same derived intensity,
    then apply `trait_overrides` on top. Unlike the CLI's own
    `--evolve-from` (which still passes `contact_intensity` through
    unvalidated via a plain `--trait`, same as any other trait -- see
    `sound_change._evolve_phonology_membership`'s own docstring), only
    this endpoint has the capped-sum derivation/validation; a deliberate
    scope limit, not an oversight. `dry_run=true` computes but never
    saves, same contract `/api/languages/{slug}/tweak` already has."""
    unknown_traits = set(request.trait_overrides) - set(GRADED_TRAIT_FIELDS)
    if unknown_traits:
        raise HTTPException(
            status_code=400, detail=f"trait_overrides has unknown trait name(s): {', '.join(sorted(unknown_traits))}"
        )
    out_of_range = {k: v for k, v in request.trait_overrides.items() if not -1.0 <= v <= 1.0}
    if out_of_range:
        raise HTTPException(status_code=400, detail=f"trait_overrides values must be between -1.0 and 1.0: {out_of_range}")
    if request.years <= 0:
        raise HTTPException(status_code=400, detail="years must be > 0")
    total_intensity = sum(e.intensity for e in request.source_languages)
    if request.source_languages:
        out_of_range_intensity = {e.name: e.intensity for e in request.source_languages if not 0.0 <= e.intensity <= 1.0}
        if out_of_range_intensity:
            raise HTTPException(
                status_code=400, detail=f"source-language intensity must be between 0.0 and 1.0: {out_of_range_intensity}"
            )
        if total_intensity > 1.0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "the sum of source-language intensities must not exceed 1.0 (the maximum influence "
                    f"imaginable without the language losing its own identity) -- got {total_intensity:.2f}"
                ),
            )
        if "contact_intensity" in request.trait_overrides:
            raise HTTPException(
                status_code=400,
                detail=(
                    "contact_intensity can't be set via trait_overrides alongside source_languages during "
                    "evolution -- it's derived automatically as the sum of their own intensities"
                ),
            )
    try:
        base = _repository().load(slug)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    client = _client(request.llm)
    before = _cost_snapshot()

    traits = base.spec.traits
    new_source_languages = ()
    blend_weight = 0.0
    if request.source_languages:
        names = tuple(e.name for e in request.source_languages)
        intensities = tuple(e.intensity for e in request.source_languages)
        traits = traits.model_copy(
            update={"source_languages": names, "source_language_weights": intensities, "contact_intensity": total_intensity}
        )
        new_source_languages = match_profiles_weighted(names, intensities)
        blend_weight = total_intensity
    traits = blend_toward_reference(traits, new_source_languages, blend_weight)
    if request.trait_overrides:
        traits = traits.model_copy(update=request.trait_overrides)

    language = sound_change.evolve_language(
        request.name, base, request.years, traits, base.spec.seed, forced_orthography=base.spec.forced_orthography
    )
    if not request.dry_run:
        _repository().save(language)

    after = _cost_snapshot()
    summary = _language_summary(language)
    summary["cost"] = _cost_delta(before, after)
    summary["warnings"] = phonotactic_mismatch_warnings(language) + unused_suppletive_form_warnings(language)
    summary["saved"] = not request.dry_run
    return summary


@app.post("/api/translate")
def translate(request: TranslateRequest) -> dict:
    if request.to not in ("conlang", "english"):
        raise HTTPException(status_code=400, detail="to must be 'conlang' or 'english'")

    repository = _repository()
    try:
        language = repository.load(request.lang)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    client = _client(request.llm)
    before = _cost_snapshot()
    if request.to == "conlang":
        result = translate_to_conlang(request.text, language, client, model=request.translate_model)
    else:
        result = translate_to_english(request.text, language, client, model=request.translate_model)
    after = _cost_snapshot()

    if result.coined:
        repository.save(result.language)

    return {
        "text": result.text,
        "ipa": result.ipa,
        "pattern": result.pattern,
        "coined": [e.romanization for e in result.coined],
        "tokens": [
            {
                "surface": t.surface, "ipa": t.ipa, "gloss": t.gloss, "pos": t.pos,
                "real_word": t.real_word, "notes": t.notes, "coined": t.coined,
            }
            for t in result.tokens
        ],
        "cost": _cost_delta(before, after),
    }


class PronounceRequest(BaseModel):
    ipa: str
    tts: str = "espeak"


@app.post("/api/pronounce")
def pronounce(request: PronounceRequest) -> Response:
    if request.tts not in ("espeak", "sapi", "piper", "auto"):
        raise HTTPException(status_code=400, detail="tts must be 'espeak', 'sapi', 'piper' or 'auto'")
    if not request.ipa.strip():
        raise HTTPException(status_code=400, detail="ipa must not be empty")
    if request.tts == "auto":
        client_for_word = engine_selection.auto_client_for_word(
            request.ipa, tts.available_engine_kinds(), cache_dir=CACHE_DIR / "tts_cache",
            sapi_worker=_get_sapi_worker(), piper_client=_get_piper_client(),
        )
    else:
        sapi_worker = _get_sapi_worker() if request.tts == "sapi" else None
        piper_client = _get_piper_client() if request.tts == "piper" else None
        client = tts.build_tts_client(request.tts, sapi_worker=sapi_worker, piper_client=piper_client)
        if hasattr(client, "for_utterance"):  # engines that pick a voice per sentence (eSpeak's tonal one)
            client = client.for_utterance(request.ipa)
        client = tts_cache.CachingTTSClient(client, CACHE_DIR / "tts_cache")
        client_for_word = lambda _word: client  # noqa: E731
    audio = sentence_synthesis.synthesize_sentence(client_for_word, request.ipa, CACHE_DIR / "audio")
    if audio is None:
        raise HTTPException(status_code=503, detail=f"'{request.tts}' TTS backend unavailable or synthesis failed.")
    return Response(content=audio, media_type="audio/wav")


@app.post("/api/pronunciation-check")
def pronunciation_check(request: PronounceRequest) -> dict:
    """What the chosen pronunciation engine can't voice in this IPA (today:
    tones), plus its own capability summary -- the UI shows the alerts before
    (and again with) any playback. ``"auto"`` has no single engine's own
    capabilities to check against -- its warnings instead come from each
    word's own per-engine selection (``engine_selection.auto_pronunciation_
    warnings``), reporting which word fell short and why."""
    if request.tts not in ("none", "espeak", "sapi", "piper", "auto"):
        raise HTTPException(status_code=400, detail="tts must be 'none', 'espeak', 'sapi', 'piper' or 'auto'")
    if request.tts == "auto":
        return {
            "capabilities": tts.backend_capabilities()["auto"],
            "warnings": engine_selection.auto_pronunciation_warnings(request.ipa, tts.available_engine_kinds()),
        }
    capabilities = tts.build_tts_client(request.tts).capabilities()
    return {
        "capabilities": capabilities.as_dict(),
        "warnings": tts.pronunciation_warnings(capabilities, request.ipa) if request.tts != "none" else [],
    }


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
