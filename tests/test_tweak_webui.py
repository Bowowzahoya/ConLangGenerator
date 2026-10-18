"""Tests for ``POST /api/languages/{slug}/tweak`` -- "Tweaking an existing
language" item 6's own backing endpoint (docs/DEFERRED.md), the web UI's
Tweak tab."""

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from conlang_generator.webui import app as webui_app  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(webui_app, "CACHE_DIR", tmp_path / ".cache")
    monkeypatch.setattr(webui_app, "LANGUAGES_DIR", tmp_path / "conlangs")
    return TestClient(webui_app.app)


def _make_base(client, name="tweak-base"):
    response = client.post(
        "/api/generate",
        json={"prompt": "p", "name": name, "seed": 5, "llm": "fake", "vocabulary_size": 10},
    )
    assert response.status_code == 200
    return response.json()


def test_tweak_regenerate_saves_a_new_language_with_identical_grammar(client):
    base = _make_base(client)
    response = client.post(
        "/api/languages/tweak-base/tweak",
        json={"name": "tweak-regen", "trait_overrides": {"aesthetic_harshness": 0.9}, "words": "regenerate"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "tweak-regen"
    assert body["grammar"]["word_order"] == base["grammar"]["word_order"]
    assert body["grammar"]["alignment"] == base["grammar"]["alignment"]

    tweaked = client.get("/api/languages/tweak-regen").json()
    base_full = client.get("/api/languages/tweak-base").json()
    base_ipa = [e["ipa"] for e in base_full["lexicon"]]
    tweaked_ipa = [e["ipa"] for e in tweaked["lexicon"]]
    assert base_ipa != tweaked_ipa


def test_tweak_adapt_keeps_the_same_glosses(client):
    _make_base(client)
    response = client.post(
        "/api/languages/tweak-base/tweak",
        json={"name": "tweak-adapt", "trait_overrides": {"altitude": 1.0}, "words": "adapt"},
    )
    assert response.status_code == 200
    base_full = client.get("/api/languages/tweak-base").json()
    tweaked = client.get("/api/languages/tweak-adapt").json()
    assert [e["gloss"] for e in tweaked["lexicon"]] == [e["gloss"] for e in base_full["lexicon"]]


def test_tweak_rejects_an_invalid_words_value(client):
    _make_base(client)
    response = client.post(
        "/api/languages/tweak-base/tweak",
        json={"name": "x", "words": "bogus"},
    )
    assert response.status_code == 400
    assert "words" in response.json()["detail"]


def test_tweak_rejects_a_grammar_affecting_trait(client):
    _make_base(client)
    response = client.post(
        "/api/languages/tweak-base/tweak",
        json={"name": "x", "trait_overrides": {"social_hierarchy": 0.5}, "words": "regenerate"},
    )
    assert response.status_code == 400
    assert "social_hierarchy" in response.json()["detail"]


def test_tweak_404s_for_an_unknown_language(client):
    response = client.post(
        "/api/languages/does-not-exist/tweak",
        json={"name": "x", "words": "regenerate"},
    )
    assert response.status_code == 404


def test_options_endpoint_serves_the_phonology_only_trait_fields(client):
    opts = client.get("/api/options").json()
    assert set(opts["phonology_only_trait_fields"]) == {"altitude", "aesthetic_harshness", "phonotactic_restrictiveness"}
