"""Tests for webui.app -- the local JSON API driving the browser front
end. Skipped entirely when the optional ``web`` dependency group isn't
installed (``pytest.importorskip``), so the main suite stays green
without it. Fake-LLM-only (``llm="fake"``), matching this project's own
fake-LLM-first testing rule -- no real Anthropic calls here. The one
exception is ``/api/pronounce``'s real-backend tests, gated behind actual
backend availability the same way ``tests/test_tts.py`` already gates
its own -- no LLM involved either way."""

import sys

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from conlang_generator.speech import tts  # noqa: E402
from conlang_generator.webui import app as webui_app  # noqa: E402

_ESPEAK_AVAILABLE = tts.available_backends()["espeak"]
_IS_WINDOWS = sys.platform.startswith("win")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(webui_app, "CACHE_DIR", tmp_path / ".cache")
    monkeypatch.setattr(webui_app, "LANGUAGES_DIR", tmp_path / "conlangs")
    return TestClient(webui_app.app)


def test_generate_returns_a_language_summary_with_words_grammar_and_cost(client):
    response = client.post(
        "/api/generate",
        json={"prompt": "a language spoken in the mountains", "name": "Webtest", "seed": 2, "llm": "fake"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Webtest"
    assert body["slug"] == "webtest"
    assert len(body["lexicon"]) > 0
    assert {"gloss", "pos", "romanization", "ipa"} <= body["lexicon"][0].keys()
    assert "word_order" in body["grammar"]
    assert "alignment" in body["grammar"]
    assert body["cost"]["delta_usd"] == 0.0  # fake backend never spends


def test_generated_language_is_saved_and_listed(client):
    client.post("/api/generate", json={"prompt": "p", "name": "Listed Lang", "seed": 1, "llm": "fake"})
    response = client.get("/api/languages")
    assert response.status_code == 200
    assert "listed-lang" in response.json()["languages"]


def test_get_language_by_slug_matches_generate_response_shape(client):
    generated = client.post("/api/generate", json={"prompt": "p", "name": "Reload Me", "seed": 3, "llm": "fake"}).json()
    fetched = client.get("/api/languages/reload-me").json()
    assert fetched["name"] == generated["name"]
    assert fetched["grammar"] == generated["grammar"]
    assert [w["gloss"] for w in fetched["lexicon"]] == [w["gloss"] for w in generated["lexicon"]]


def test_get_unknown_language_is_404(client):
    response = client.get("/api/languages/does-not-exist")
    assert response.status_code == 404


def test_translate_to_conlang_and_back_round_trips(client):
    client.post("/api/generate", json={"prompt": "p", "name": "Translator Test", "seed": 2, "llm": "fake"})
    to_conlang = client.post(
        "/api/translate", json={"lang": "Translator Test", "text": "I see the mountain", "to": "conlang", "llm": "fake"}
    )
    assert to_conlang.status_code == 200
    conlang_body = to_conlang.json()
    assert conlang_body["text"]
    assert conlang_body["ipa"]

    to_english = client.post(
        "/api/translate", json={"lang": "Translator Test", "text": conlang_body["text"], "to": "english", "llm": "fake"}
    )
    assert to_english.status_code == 200
    assert "mountain" in to_english.json()["text"].lower()


def test_translate_against_unknown_language_is_404(client):
    response = client.post("/api/translate", json={"lang": "nope", "text": "hi", "to": "conlang", "llm": "fake"})
    assert response.status_code == 404


def test_translate_rejects_an_invalid_direction(client):
    client.post("/api/generate", json={"prompt": "p", "name": "Dir Test", "seed": 2, "llm": "fake"})
    response = client.post("/api/translate", json={"lang": "Dir Test", "text": "hi", "to": "sideways", "llm": "fake"})
    assert response.status_code == 400


def test_cost_endpoint_reflects_generation_spend(client):
    before = client.get("/api/cost").json()
    client.post("/api/generate", json={"prompt": "p", "name": "Cost Test", "seed": 2, "llm": "fake"})
    after = client.get("/api/cost").json()
    assert after["total_cost_usd"] == before["total_cost_usd"] == 0.0  # fake backend, always free


def test_options_endpoint_lists_orthography_choices(client):
    response = client.get("/api/options")
    assert response.status_code == 200
    body = response.json()
    assert "monoletter" in body["exotic_symbol_styles"]
    assert "none" in body["vowel_length_styles"]
    assert isinstance(body["orthography_styles"], list) and len(body["orthography_styles"]) > 0


def test_generate_rejects_an_unknown_orthography_style(client):
    response = client.post(
        "/api/generate",
        json={"prompt": "p", "name": "Bad Style", "seed": 0, "llm": "fake", "orthography_style": "not-a-real-style"},
    )
    assert response.status_code == 400


def test_options_endpoint_reports_tts_backend_availability(client):
    response = client.get("/api/options")
    backends = response.json()["tts_backends"]
    assert backends["none"] is True
    assert backends["espeak"] == _ESPEAK_AVAILABLE
    assert backends["sapi"] == _IS_WINDOWS


def test_pronounce_rejects_the_none_backend(client):
    response = client.post("/api/pronounce", json={"ipa": "kat", "tts": "none"})
    assert response.status_code == 400


def test_pronounce_rejects_empty_ipa(client):
    response = client.post("/api/pronounce", json={"ipa": "   ", "tts": "espeak"})
    assert response.status_code == 400


def test_pronounce_reports_503_when_the_backend_is_unavailable(client, monkeypatch):
    class _AlwaysFailsClient:
        def synthesize(self, ipa_text, output_path):
            return False

    monkeypatch.setattr(webui_app.tts, "build_tts_client", lambda kind: _AlwaysFailsClient())
    response = client.post("/api/pronounce", json={"ipa": "kat", "tts": "espeak"})
    assert response.status_code == 503


@pytest.mark.skipif(not _IS_WINDOWS, reason="SAPI is Windows-only")
def test_pronounce_synthesizes_a_single_word_with_sapi(client):
    response = client.post("/api/pronounce", json={"ipa": "kat", "tts": "sapi"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert len(response.content) > 0


@pytest.mark.skipif(not _IS_WINDOWS, reason="SAPI is Windows-only")
def test_pronounce_synthesizes_a_multi_word_sentence_with_sapi(client):
    single = client.post("/api/pronounce", json={"ipa": "kat", "tts": "sapi"}).content
    sentence = client.post("/api/pronounce", json={"ipa": "kat mat", "tts": "sapi"}).content
    assert len(sentence) > len(single)  # two words (plus inter-word silence) outlasts one


@pytest.mark.skipif(not _ESPEAK_AVAILABLE, reason="espeak-ng not installed on this machine")
def test_pronounce_synthesizes_with_espeak(client):
    response = client.post("/api/pronounce", json={"ipa": "kat", "tts": "espeak"})
    assert response.status_code == 200
    assert len(response.content) > 0
