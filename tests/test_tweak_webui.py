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
    assert set(opts["phonology_only_trait_fields"]) == {
        "altitude", "aesthetic_harshness", "phonotactic_restrictiveness", "tonal_friendliness", "tone_sandhi",
    }


# --- dry_run (item 7: word-by-word preview before saving) ---


def test_tweak_dry_run_does_not_save_the_language(client):
    _make_base(client)
    response = client.post(
        "/api/languages/tweak-base/tweak",
        json={"name": "tweak-preview", "trait_overrides": {"altitude": 1.0}, "words": "regenerate", "dry_run": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["saved"] is False
    assert body["name"] == "tweak-preview"
    # Never written to disk -- loading it back must 404.
    assert client.get("/api/languages/tweak-preview").status_code == 404


def test_tweak_dry_run_preview_matches_a_real_save_with_the_same_inputs(client):
    # regenerate_phonology/_adapt_words are deterministic -- a client that
    # likes the preview just re-POSTs the identical body with
    # dry_run=false, and must get exactly what it previewed.
    _make_base(client)
    body = {"name": "tweak-commit", "trait_overrides": {"aesthetic_harshness": 0.8}, "words": "adapt"}
    preview = client.post("/api/languages/tweak-base/tweak", json={**body, "dry_run": True}).json()
    saved = client.post("/api/languages/tweak-base/tweak", json={**body, "dry_run": False}).json()
    assert preview["saved"] is False
    assert saved["saved"] is True
    assert [e["ipa"] for e in preview["lexicon"]] == [e["ipa"] for e in saved["lexicon"]]
    assert client.get("/api/languages/tweak-commit").status_code == 200


def test_tweak_without_dry_run_still_defaults_to_saving(client):
    _make_base(client)
    response = client.post(
        "/api/languages/tweak-base/tweak",
        json={"name": "tweak-default-save", "words": "regenerate"},
    )
    assert response.json()["saved"] is True
    assert client.get("/api/languages/tweak-default-save").status_code == 200


def test_tweak_with_an_orthography_field_set_tweaks_spelling_not_phonology(client):
    # "Tweaking an existing language" item 9 -- any orthography field set
    # dispatches to regenerate_orthography instead of the phonology path,
    # ignoring trait_overrides/words entirely (the two axes can't combine
    # in one request).
    _make_base(client)
    base_full = client.get("/api/languages/tweak-base").json()
    response = client.post(
        "/api/languages/tweak-base/tweak",
        json={
            "name": "tweak-ortho",
            "trait_overrides": {"aesthetic_harshness": 0.9},  # ignored
            "orthography_style": "wade-giles-style",
            "dry_run": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    base_ipa = [e["ipa"] for e in base_full["lexicon"]]
    tweaked_ipa = [e["ipa"] for e in body["lexicon"]]
    base_romanization = [e["romanization"] for e in base_full["lexicon"]]
    tweaked_romanization = [e["romanization"] for e in body["lexicon"]]
    assert base_ipa == tweaked_ipa
    assert base_romanization != tweaked_romanization
    assert body["grammar"] == base_full["grammar"]


def test_tweak_orthography_rejects_an_unknown_style(client):
    _make_base(client)
    response = client.post(
        "/api/languages/tweak-base/tweak",
        json={"name": "tweak-ortho-bad", "orthography_style": "not-a-real-style", "dry_run": True},
    )
    assert response.status_code == 400


def test_tweak_orthography_rejects_an_unknown_exotic_symbol_style(client):
    _make_base(client)
    response = client.post(
        "/api/languages/tweak-base/tweak",
        json={"name": "tweak-ortho-bad2", "exotic_symbol_style": "not-a-real-choice", "dry_run": True},
    )
    assert response.status_code == 400


def test_tweak_orthography_response_includes_sound_correspondence(client):
    _make_base(client)
    response = client.post(
        "/api/languages/tweak-base/tweak",
        json={"name": "tweak-ortho-corr", "exotic_symbol_style": "monoletter", "dry_run": True},
    )
    assert "sound_correspondence" in response.json()
