"""Web UI tests for the invented-script feature: /api/generate's own
own_script option, the script/script_text fields on a language summary,
and the GET /api/languages/{slug}/script/font endpoint."""

import pytest
from fastapi.testclient import TestClient

from conlang_generator.core.script import SCRIPT_TRAIT_GROUP, SCRIPT_TRAIT_RANGE, ScriptTraits
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
    # All 15 ScriptTraits dials, not just the nonzero ones -- unlike the
    # worldbuilding traits (0.0 = "no opinion"), every rolled script-trait
    # dial is a real, meaningful reading (see webui/app.py's own
    # _language_summary docstring on this field).
    assert set(body["script"]["traits"]) == set(ScriptTraits.model_fields)
    assert all(-1.0 <= v <= 1.0 for v in body["script"]["traits"].values())


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


def test_script_keyboard_endpoint_serves_trigger_ipa_romanization_and_codepoint(client):
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
    # Identity-first assignment: a single-plain-letter IPA symbol is
    # typed with that exact letter -- the first glyph of a real
    # generated inventory (consonants before vowels) is almost always
    # one (see script_render.assign_keyboard_triggers).
    assert first["trigger"] == first["ipa"]
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


def test_generate_applies_a_forced_script_trait(client, tmp_path):
    response = client.post(
        "/api/generate",
        json={
            "prompt": "p", "name": "webscript-forced-trait", "seed": 1, "llm": "fake", "vocabulary_size": 8,
            "own_script": "yes", "script_trait_overrides": {"angularity": 1.0, "weight": -1.0},
        },
    )
    assert response.status_code == 200
    from conlang_generator.storage.yaml_backend import YamlLanguageRepository

    language = YamlLanguageRepository(tmp_path / "conlangs").load("webscript-forced-trait")
    assert language.script.traits.angularity == 1.0
    assert language.script.traits.weight == -1.0


def test_generate_rejects_an_unknown_script_trait_name(client):
    response = client.post(
        "/api/generate",
        json={
            "prompt": "p", "name": "webscript-bad-trait", "seed": 1, "llm": "fake",
            "script_trait_overrides": {"not_a_dial": 0.5},
        },
    )
    assert response.status_code == 400
    assert "not_a_dial" in response.json()["detail"]


def test_generate_rejects_a_script_trait_value_outside_the_bipolar_range(client):
    response = client.post(
        "/api/generate",
        json={
            "prompt": "p", "name": "webscript-oor-trait", "seed": 1, "llm": "fake",
            "script_trait_overrides": {"angularity": 2.0},
        },
    )
    assert response.status_code == 400
    assert "angularity" in response.json()["detail"]


def test_generate_rejects_a_negative_value_for_a_unipolar_script_trait(client):
    # stroke_contrast/regularity/dot_ornateness are unipolar (0.0..1.0 only, no meaningful negative
    # pole) -- a negative value must be rejected the same way a >1.0 bipolar value already is.
    response = client.post(
        "/api/generate",
        json={
            "prompt": "p", "name": "webscript-negative-unipolar", "seed": 1, "llm": "fake",
            "script_trait_overrides": {"regularity": -0.5},
        },
    )
    assert response.status_code == 400
    assert "regularity" in response.json()["detail"]


def test_options_endpoint_serves_the_script_trait_fields(client):
    opts = client.get("/api/options").json()
    assert set(opts["script_trait_fields"]) == set(ScriptTraits.model_fields)


def test_options_endpoint_serves_the_script_trait_groups_and_ranges(client):
    # Single server-side source of truth (core.script.SCRIPT_TRAIT_GROUP/SCRIPT_TRAIT_RANGE) -- the
    # web UI reads these instead of hand-duplicating the topology/style split or each dial's own
    # valid range in JS.
    opts = client.get("/api/options").json()
    assert opts["script_trait_groups"] == {k: v for k, v in SCRIPT_TRAIT_GROUP.items()}
    assert set(opts["script_trait_groups"]) == set(ScriptTraits.model_fields)
    assert set(opts["script_trait_groups"].values()) == {"topology", "style"}
    assert opts["script_trait_ranges"] == {k: list(v) for k, v in SCRIPT_TRAIT_RANGE.items()}


def test_options_endpoint_serves_the_script_trait_glossary(client):
    glossary = client.get("/api/options").json()["glossary"]
    for field in ScriptTraits.model_fields:
        entry = glossary["script_traits"][field]
        lo, _hi = SCRIPT_TRAIT_RANGE[field]
        if lo == 0.0:
            assert entry["kind"] == "unipolar"
            assert entry["summary"] and entry["low"] and entry["high"]
        else:
            assert entry["kind"] == "bipolar"
            assert entry["summary"] and entry["positive"] and entry["negative"]


def test_languages_list_reports_which_ones_have_a_script(client):
    client.post(
        "/api/generate",
        json={"prompt": "p", "name": "webscript-list-yes", "seed": 1, "llm": "fake", "vocabulary_size": 8,
              "own_script": "yes"},
    )
    client.post(
        "/api/generate",
        json={"prompt": "p", "name": "webscript-list-no", "seed": 1, "llm": "fake", "vocabulary_size": 8},
    )
    body = client.get("/api/languages").json()
    assert "webscript-list-yes" in body["languages"]
    assert "webscript-list-no" in body["languages"]
    assert "webscript-list-yes" in body["scripted_languages"]
    assert "webscript-list-no" not in body["scripted_languages"]
