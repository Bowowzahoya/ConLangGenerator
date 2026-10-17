"""Web UI tests for the invented-script feature: /api/generate's own
own_script option, the script/script_text fields on a language summary,
and the GET /api/languages/{slug}/script/font endpoint."""

import pytest
from fastapi.testclient import TestClient

from conlang_generator.webui import app as webui_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(webui_app, "CACHE_DIR", tmp_path / ".cache")
    monkeypatch.setattr(webui_app, "LANGUAGES_DIR", tmp_path / "conlangs")
    return TestClient(webui_app.app)


def test_generate_defaults_to_no_script(client):
    response = client.post(
        "/api/generate",
        json={"prompt": "p", "name": "webscript-auto", "seed": 1, "llm": "fake", "vocabulary_size": 8},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["script"] is None
    assert all(entry["script_text"] is None for entry in body["lexicon"])


def test_generate_own_script_yes_produces_a_script_and_per_word_text(client):
    response = client.post(
        "/api/generate",
        json={
            "prompt": "p", "name": "webscript-yes", "seed": 1, "llm": "fake", "vocabulary_size": 8,
            "own_script": "yes",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["script"]["glyph_count"] > 0
    assert body["script"]["direction"] in ("ltr", "rtl", "ttb_ltr", "ttb_rtl", "boustrophedon")
    assert any(entry["script_text"] for entry in body["lexicon"])


def test_generate_rejects_an_invalid_own_script_value(client):
    response = client.post(
        "/api/generate",
        json={"prompt": "p", "name": "webscript-bad", "seed": 1, "llm": "fake", "own_script": "maybe"},
    )
    assert response.status_code == 400
    assert "own_script" in response.json()["detail"]


def test_script_font_endpoint_serves_a_real_font(client):
    client.post(
        "/api/generate",
        json={
            "prompt": "p", "name": "webscript-font", "seed": 1, "llm": "fake", "vocabulary_size": 8,
            "own_script": "yes",
        },
    )
    response = client.get("/api/languages/webscript-font/script/font")
    assert response.status_code == 200
    assert response.headers["content-type"] == "font/ttf"

    from fontTools.ttLib import TTFont
    import io

    tt = TTFont(io.BytesIO(response.content))
    try:
        assert len(tt.getGlyphOrder()) > 1  # more than just .notdef
    finally:
        tt.close()


def test_script_font_endpoint_404s_for_a_language_with_no_script(client):
    client.post(
        "/api/generate",
        json={"prompt": "p", "name": "webscript-noscript", "seed": 1, "llm": "fake", "vocabulary_size": 8},
    )
    response = client.get("/api/languages/webscript-noscript/script/font")
    assert response.status_code == 404


def test_script_font_endpoint_404s_for_an_unknown_language(client):
    response = client.get("/api/languages/does-not-exist/script/font")
    assert response.status_code == 404


def test_options_endpoint_serves_the_own_script_advanced_option_glossary(client):
    glossary = client.get("/api/options").json()["glossary"]
    assert set(glossary["advanced_options"]["own_script"]["values"]) == {"auto", "yes", "no"}


def test_script_keyboard_endpoint_serves_key_ipa_romanization_and_codepoint(client):
    client.post(
        "/api/generate",
        json={
            "prompt": "p", "name": "webscript-keyboard", "seed": 1, "llm": "fake", "vocabulary_size": 8,
            "own_script": "yes",
        },
    )
    response = client.get("/api/languages/webscript-keyboard/script/keyboard")
    assert response.status_code == 200
    body = response.json()
    assert body["direction"] in ("ltr", "rtl", "ttb_ltr", "ttb_rtl", "boustrophedon")
    assert len(body["keys"]) > 0
    first = body["keys"][0]
    assert first["key"] == "a"
    assert first["ipa"] and first["romanization"]
    assert first["codepoint"] >= 0xE000


def test_script_keyboard_endpoint_404s_for_a_language_with_no_script(client):
    client.post(
        "/api/generate",
        json={"prompt": "p", "name": "webscript-nokeyboard", "seed": 1, "llm": "fake", "vocabulary_size": 8},
    )
    response = client.get("/api/languages/webscript-nokeyboard/script/keyboard")
    assert response.status_code == 404


def test_script_keyboard_endpoint_404s_for_an_unknown_language(client):
    response = client.get("/api/languages/does-not-exist/script/keyboard")
    assert response.status_code == 404
