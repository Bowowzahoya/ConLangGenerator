"""Tests for ``POST /api/languages/{slug}/evolve`` -- the "Language
evolution" restructuring's own backing endpoint (docs/DEFERRED.md,
chapter 11), the web UI's Evolve tab. Evolving an already-saved language
with its own (optionally different) trait profile, independent of
Generate's own combined generate+evolve path."""

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from conlang_generator.webui import app as webui_app  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(webui_app, "CACHE_DIR", tmp_path / ".cache")
    monkeypatch.setattr(webui_app, "LANGUAGES_DIR", tmp_path / "conlangs")
    return TestClient(webui_app.app)


def _make_base(client, name="evolve-base"):
    response = client.post(
        "/api/generate",
        json={"prompt": "p", "name": name, "seed": 5, "llm": "fake", "vocabulary_size": 10},
    )
    assert response.status_code == 200
    return response.json()


def test_evolve_saves_a_new_language_with_identical_grammar_typology(client):
    base = _make_base(client)
    response = client.post(
        "/api/languages/evolve-base/evolve",
        json={"name": "evolve-result", "years": 300, "trait_overrides": {"isolation": 0.9}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "evolve-result"
    assert body["grammar"]["word_order"] == base["grammar"]["word_order"]
    assert body["grammar"]["alignment"] == base["grammar"]["alignment"]
    assert body["grammar"]["morphological_type"] == base["grammar"]["morphological_type"]
    assert body["saved"] is True
    assert client.get("/api/languages/evolve-result").status_code == 200


def test_evolve_with_a_grammar_adjacent_trait_still_keeps_typology_identical(client):
    # The exact trait regenerate_phonology's own PHONOLOGY_ONLY_TRAIT_FIELDS
    # excludes isolation for (it also nudges grammar during FRESH
    # generation) -- confirming evolve_language's own "no grammar re-roll"
    # property holds even for this specific trait. `tonal` is deliberately
    # excluded from this comparison: real tonogenesis (a non-tonal language
    # gaining tone over a long evolution run, modeled in sound_change.py)
    # can legitimately flip it, unlike word_order/alignment/morphological_
    # type/has_articles, which evolution never touches at all.
    base = _make_base(client)
    response = client.post(
        "/api/languages/evolve-base/evolve",
        json={"name": "evolve-isolation", "years": 300, "trait_overrides": {"social_hierarchy": 0.9}},
    )
    assert response.status_code == 200
    body = response.json()
    for key in ("word_order", "alignment", "morphological_type", "has_articles", "has_overt_copula"):
        assert body["grammar"][key] == base["grammar"][key], key


def test_evolve_rejects_zero_years(client):
    _make_base(client)
    response = client.post("/api/languages/evolve-base/evolve", json={"name": "x", "years": 0})
    assert response.status_code == 400


def test_evolve_rejects_negative_years(client):
    _make_base(client)
    response = client.post("/api/languages/evolve-base/evolve", json={"name": "x", "years": -10})
    assert response.status_code == 400


def test_evolve_rejects_an_unknown_trait(client):
    _make_base(client)
    response = client.post(
        "/api/languages/evolve-base/evolve",
        json={"name": "x", "years": 100, "trait_overrides": {"not_a_real_trait": 0.5}},
    )
    assert response.status_code == 400


def test_evolve_404s_for_an_unknown_language(client):
    response = client.post("/api/languages/does-not-exist/evolve", json={"name": "x", "years": 100})
    assert response.status_code == 404


def test_evolve_dry_run_does_not_save(client):
    _make_base(client)
    response = client.post(
        "/api/languages/evolve-base/evolve",
        json={"name": "evolve-preview", "years": 200, "dry_run": True},
    )
    assert response.status_code == 200
    assert response.json()["saved"] is False
    assert client.get("/api/languages/evolve-preview").status_code == 404


def test_evolve_merges_new_source_languages_additively(client):
    response = client.post(
        "/api/generate",
        json={
            "prompt": "p", "name": "evolve-src-base", "seed": 5, "llm": "fake", "vocabulary_size": 10,
            "source_languages": [{"name": "French", "weight": 1.0}],
        },
    )
    assert response.status_code == 200
    evolved = client.post(
        "/api/languages/evolve-src-base/evolve",
        json={
            "name": "evolve-src-result", "years": 200,
            "source_languages": [{"name": "Dutch", "weight": 1.0}],
        },
    )
    assert evolved.status_code == 200
    saved = client.get("/api/languages/evolve-src-result").json()
    assert "French" in saved["traits"]["source_languages"]
    assert "Dutch" in saved["traits"]["source_languages"]
