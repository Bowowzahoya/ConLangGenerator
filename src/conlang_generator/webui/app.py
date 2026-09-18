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

import io
import uuid
import wave
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from conlang_generator.core.language import Language
from conlang_generator.core.romanization import (
    ExoticSymbolStyle,
    OrthographyForce,
    SyllableBoundaryMarker,
    ToneMarkingStrategy,
    VowelLengthStrategy,
)
from conlang_generator.core.spec import GenerationSpec, SeedExample
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.prompt_classifier import classify_prompt
from conlang_generator.generation.romanization_gen import ORTHOGRAPHY_STYLE_NAMES
from conlang_generator.generation.seed_examples import resolve_seed_examples
from conlang_generator.llm.cost_tracker import CostTracker
from conlang_generator.llm.factory import build_llm_client
from conlang_generator.speech import tts
from conlang_generator.storage.yaml_backend import YamlLanguageRepository
from conlang_generator.translation.translator import translate_to_conlang, translate_to_english

CACHE_DIR = Path(".cache")
LANGUAGES_DIR = Path("conlangs")
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="ConLangGenerator")


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
        },
        "traits": {
            **nonzero_traits,
            "source_languages": list(traits.source_languages),
            "source_language_strictness": traits.source_language_strictness,
            "salient_context": traits.salient_context,
        },
        "orthography_category": language.romanization.category_name,
        "lexicon": [
            {
                "gloss": entry.primary_gloss,
                "pos": entry.pos.value,
                "romanization": entry.romanization,
                "ipa": entry.ipa,
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


class SeedExampleEntry(BaseModel):
    gloss: str
    form: str
    ipa: str | None = None


class GenerateRequest(BaseModel):
    prompt: str
    name: str
    seed: int = 0
    llm: str = "fake"
    isolated: bool = False
    high_altitude: bool = False
    tonal: bool = False
    fantasy: bool = False
    source_languages: list[SourceLanguageEntry] = []
    strictness: float | None = None
    examples: list[SeedExampleEntry] = []
    orthography_style: str | None = None
    exotic_symbol_style: str | None = None
    vowel_length_style: str | None = None
    short_vowel_doubling: bool | None = None
    tone_style: str | None = None
    syllable_boundary_marker: str | None = None
    consonant_gemination_marked: bool | None = None
    allow_all_caps: bool = False
    word_selection: str = "algorithmic"


class TranslateRequest(BaseModel):
    lang: str
    text: str
    to: str = "conlang"
    llm: str = "fake"


@app.get("/api/languages")
def list_languages() -> dict:
    return {"languages": _repository().list()}


@app.get("/api/languages/{slug}")
def get_language(slug: str) -> dict:
    try:
        language = _repository().load(slug)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _language_summary(language)


@app.get("/api/cost")
def get_cost() -> dict:
    return _cost_snapshot()


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
    }


@app.post("/api/generate")
def generate(request: GenerateRequest) -> dict:
    if request.orthography_style is not None and request.orthography_style not in ORTHOGRAPHY_STYLE_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"orthography_style must be one of {', '.join(ORTHOGRAPHY_STYLE_NAMES)}, got {request.orthography_style!r}",
        )
    if request.strictness is not None and not 0.0 <= request.strictness <= 1.0:
        raise HTTPException(status_code=400, detail="strictness must be between 0.0 and 1.0")
    if request.word_selection not in ("algorithmic", "llm"):
        raise HTTPException(status_code=400, detail="word_selection must be 'algorithmic' or 'llm'")

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

    traits = classify_prompt(request.prompt, request.fantasy, client)
    if request.source_languages:
        names = tuple(e.name for e in request.source_languages)
        weights = tuple(e.weight if e.weight is not None else 1.0 for e in request.source_languages)
        traits = traits.model_copy(update={"source_languages": names, "source_language_weights": weights})
    if request.strictness is not None:
        traits = traits.model_copy(update={"source_language_strictness": request.strictness})

    raw_examples = tuple(SeedExample(gloss=e.gloss, form=e.form, ipa=e.ipa) for e in request.examples)
    seed_examples = resolve_seed_examples(raw_examples, client)

    spec = GenerationSpec(
        prompt=request.prompt,
        seed=request.seed,
        traits=traits,
        force_isolated=request.isolated,
        force_high_altitude=request.high_altitude,
        force_tonal=request.tonal,
        forced_orthography=forced_orthography,
        fantasy=request.fantasy,
        seed_examples=seed_examples,
        allow_all_caps=request.allow_all_caps,
        word_selection=request.word_selection,
    )
    language = generate_language(request.name, spec, client)
    _repository().save(language)

    after = _cost_snapshot()
    summary = _language_summary(language)
    summary["cost"] = _cost_delta(before, after)
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
        result = translate_to_conlang(request.text, language, client)
    else:
        result = translate_to_english(request.text, language, client)
    after = _cost_snapshot()

    if result.coined:
        repository.save(result.language)

    return {
        "text": result.text,
        "ipa": result.ipa,
        "pattern": result.pattern,
        "coined": [e.romanization for e in result.coined],
        "cost": _cost_delta(before, after),
    }


class PronounceRequest(BaseModel):
    ipa: str
    tts: str = "espeak"


def _synthesize_sentence(client: tts.TTSClient, ipa_sentence: str) -> bytes | None:
    """Every real ``TTSClient.synthesize`` is documented as a *word's*
    own IPA -> one ``.wav`` file -- a translated sentence is several
    words separated by plain spaces, which neither backend's own
    single-``[[...]]``/single-``<phoneme>`` call is built to span (and
    ``ipa_tokenizer.tokenize`` -- see its own docstring -- silently drops
    any character it doesn't recognize, spaces included, so simply
    handing the whole sentence to ``synthesize`` would just run every
    word's phonemes together with no word boundary at all). Synthesizes
    each word separately instead, into its own temp file under
    ``CACHE_DIR / "audio"``, then concatenates the raw PCM frames (with a
    short silence between words for intelligibility) into one combined
    in-memory ``.wav`` -- ``None`` if any single word's own synthesis
    fails, matching every ``TTSClient``'s own "unavailable/failed is a
    normal, non-exceptional state" contract."""
    words = ipa_sentence.split()
    if not words:
        return None
    temp_paths = [CACHE_DIR / "audio" / f"webui-{uuid.uuid4().hex}.wav" for _ in words]
    try:
        for word_ipa, path in zip(words, temp_paths):
            if not client.synthesize(word_ipa, path):
                return None
        params = None
        silence = b""
        frames: list[bytes] = []
        for path in temp_paths:
            with wave.open(str(path), "rb") as wf:
                if params is None:
                    params = wf.getparams()
                    silence = b"\x00" * int(0.15 * params.framerate) * params.sampwidth * params.nchannels
                frames.append(wf.readframes(wf.getnframes()))
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as out:
            out.setparams(params)
            for i, frame in enumerate(frames):
                if i > 0:
                    out.writeframesraw(silence)
                out.writeframesraw(frame)
        return buffer.getvalue()
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)


@app.post("/api/pronounce")
def pronounce(request: PronounceRequest) -> Response:
    if request.tts not in ("espeak", "sapi"):
        raise HTTPException(status_code=400, detail="tts must be 'espeak' or 'sapi'")
    if not request.ipa.strip():
        raise HTTPException(status_code=400, detail="ipa must not be empty")
    client = tts.build_tts_client(request.tts)
    audio = _synthesize_sentence(client, request.ipa)
    if audio is None:
        raise HTTPException(status_code=503, detail=f"'{request.tts}' TTS backend unavailable or synthesis failed.")
    return Response(content=audio, media_type="audio/wav")


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
