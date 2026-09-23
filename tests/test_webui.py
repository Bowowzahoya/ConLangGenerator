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
    assert {"gloss", "pos", "romanization", "ipa", "spoken_ipa", "provenance"} <= body["lexicon"][0].keys()
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


def test_generate_reports_source_language_weights_in_the_saved_spec(client):
    # The form's own per-source-language weight input (index.html's own
    # ".sl-weight" rows) -- confirms a weight actually reaches the saved
    # language's own traits, not just that the request is accepted.
    client.post(
        "/api/generate",
        json={
            "prompt": "p", "name": "Weighted", "seed": 3, "llm": "fake",
            "source_languages": [{"name": "Dutch", "weight": 0.8}, {"name": "German", "weight": 0.2}],
        },
    )
    from conlang_generator.storage.yaml_backend import YamlLanguageRepository

    language = YamlLanguageRepository(webui_app.LANGUAGES_DIR).load("weighted")
    traits = language.spec.traits
    weight_by_name = dict(zip(traits.source_languages, traits.source_language_weights))
    assert weight_by_name["Dutch"] == 0.8
    assert weight_by_name["German"] == 0.2


def test_generate_applies_trait_overrides(client):
    # The web equivalent of the CLI's own repeatable --trait NAME=VALUE.
    body = client.post(
        "/api/generate",
        json={
            "prompt": "a plain language", "name": "Trait Web", "seed": 1, "llm": "fake",
            "trait_overrides": {"tone_sandhi": 0.9, "altitude": -0.7},
        },
    ).json()
    assert body["traits"]["tone_sandhi"] == 0.9
    assert body["traits"]["altitude"] == -0.7


def test_generate_rejects_an_unknown_trait_override_name(client):
    response = client.post(
        "/api/generate",
        json={"prompt": "p", "name": "Bad Trait", "seed": 1, "llm": "fake", "trait_overrides": {"not_a_trait": 0.5}},
    )
    assert response.status_code == 400
    assert "not_a_trait" in response.json()["detail"]


def test_generate_rejects_an_out_of_range_trait_override_value(client):
    response = client.post(
        "/api/generate",
        json={"prompt": "p", "name": "Bad Trait Range", "seed": 1, "llm": "fake", "trait_overrides": {"altitude": 2.0}},
    )
    assert response.status_code == 400


def test_generate_rejects_the_dedicated_strictness_fields_own_names_as_trait_overrides(client):
    # source_language_strictness/source_word_strictness already have their
    # own dedicated strictness/word_strictness request fields -- one way
    # to set each, not two, the same exclusion cli/main.py's own
    # _parse_trait_overrides makes.
    response = client.post(
        "/api/generate",
        json={
            "prompt": "p", "name": "Strictness As Trait", "seed": 1, "llm": "fake",
            "trait_overrides": {"source_language_strictness": 0.5},
        },
    )
    assert response.status_code == 400


def test_options_endpoint_lists_the_graded_trait_fields(client):
    opts = client.get("/api/options").json()
    assert "tone_sandhi" in opts["graded_trait_fields"]
    assert "altitude" in opts["graded_trait_fields"]
    assert "source_language_strictness" not in opts["graded_trait_fields"]
    assert len(opts["graded_trait_fields"]) == 15


def test_generate_reports_no_tone_data_for_a_non_tonal_language(client):
    body = client.post("/api/generate", json={"prompt": "p", "name": "Silent Lang", "seed": 6, "llm": "fake"}).json()
    assert not body["grammar"]["tonal"]
    assert body["tone_system"] == {"levels": [], "sandhi": [], "lexical_sandhi": []}


def test_generate_reports_tone_levels_and_sandhi_for_a_tonal_language(client):
    # Strict Zulu -- real Meeussen's Rule (target="after", see
    # sound_change.py's own progressive-tone-sandhi work) round-trips all
    # the way out to the API, not just through internal generation.
    body = client.post(
        "/api/generate",
        json={
            "prompt": "Zulu", "name": "Zulu Web", "seed": 0, "llm": "fake",
            "source_languages": [{"name": "Zulu", "weight": None}], "strictness": 1.0,
        },
    ).json()
    assert body["grammar"]["tonal"]
    levels = body["tone_system"]["levels"]
    assert {entry["level"] for entry in levels} == {"high", "low"}
    # Real Chao pitch-level digits (core.phonology.TONE_CONTOURS), not just
    # the bare level name -- the exact gap architecture/OVERVIEW.md's own
    # "Contour representation" entry left open for the web UI specifically.
    assert {entry["digits"] for entry in levels} == {"55", "21"}
    assert all(entry["contour"] for entry in levels)
    assert body["tone_system"]["sandhi"] == [{"before": "high", "after": "high", "becomes": "low", "target": "after"}]


def test_lexicon_entries_report_their_own_real_spoken_sandhi_form(client):
    # Same strict-Zulu fixture as the tone_system test above -- a
    # per-lexicon-row "play" button needs each word's own real spoken
    # form (sandhi applied within that one word, isolated from every
    # other dictionary entry -- see _language_summary's own comment on
    # why this is never batched across the whole lexicon), not just its
    # unmodified citation IPA.
    body = client.post(
        "/api/generate",
        json={
            "prompt": "Zulu", "name": "Zulu Sandhi Web", "seed": 0, "llm": "fake",
            "source_languages": [{"name": "Zulu", "weight": None}], "strictness": 1.0,
        },
    ).json()
    dog = next(e for e in body["lexicon"] if e["gloss"] == "dog")
    assert dog["ipa"] != dog["spoken_ipa"]  # Meeussen's Rule firing on its own internal High-High
    assert len(dog["ipa"]) == len(dog["spoken_ipa"])  # a tone mark swapped, not a symbol added/removed
    # Every entry has the field, even when sandhi changes nothing.
    assert all("spoken_ipa" in e for e in body["lexicon"])
    unaffected = [e for e in body["lexicon"] if e["ipa"] == e["spoken_ipa"]]
    assert unaffected  # most words have no internal trigger at all


def test_lexicon_entries_report_their_own_real_word_provenance(client):
    body = client.post(
        "/api/generate",
        json={"prompt": "p", "name": "Real Dutch Web", "seed": 3, "llm": "fake", "vocabulary_size": 60,
              "source_languages": [{"name": "Dutch", "weight": None}], "strictness": 1.0, "word_strictness": 1.0},
    ).json()
    real_entries = [e for e in body["lexicon"] if e["provenance"]]
    assert len(real_entries) == body["real_words"]
    assert all(e["provenance"].startswith("real") and "Dutch" in e["provenance"] for e in real_entries)
    invented = [e for e in body["lexicon"] if e not in real_entries]
    assert all(e["provenance"] is None for e in invented)


def test_get_unknown_language_is_404(client):
    response = client.get("/api/languages/does-not-exist")
    assert response.status_code == 404


def test_lexicon_edit_updates_romanization_and_persists(client):
    client.post("/api/generate", json={"prompt": "p", "name": "Edit Test", "seed": 1, "llm": "fake"})
    body = client.post(
        "/api/languages/edit-test/lexicon/edit", json={"gloss": "water", "romanization": "wassermann"}
    ).json()
    water = next(e for e in body["lexicon"] if e["gloss"] == "water")
    assert water["romanization"] == "wassermann"

    from conlang_generator.storage.yaml_backend import YamlLanguageRepository

    reloaded = YamlLanguageRepository(webui_app.LANGUAGES_DIR).load("edit-test")
    assert reloaded.lexicon.by_gloss("water").romanization == "wassermann"
    assert "manually edited 'water'" in reloaded.history[-1]
    assert "(manually edited)" in reloaded.lexicon.by_gloss("water").notes


def test_lexicon_edit_updates_ipa_and_recomputes_tones(client):
    client.post("/api/generate", json={"prompt": "p", "name": "Edit Tones", "seed": 1, "llm": "fake"})
    body = client.post("/api/languages/edit-tones/lexicon/edit", json={"gloss": "water", "ipa": "akwa"}).json()
    water = next(e for e in body["lexicon"] if e["gloss"] == "water")
    assert water["ipa"] == "akwa"
    assert water["spoken_ipa"] == "akwa"  # no sandhi rule fires on this toneless word


def test_lexicon_edit_twice_does_not_duplicate_the_edited_note(client):
    client.post("/api/generate", json={"prompt": "p", "name": "Edit Twice", "seed": 1, "llm": "fake"})
    client.post("/api/languages/edit-twice/lexicon/edit", json={"gloss": "water", "romanization": "a"})
    client.post("/api/languages/edit-twice/lexicon/edit", json={"gloss": "water", "romanization": "b"})

    from conlang_generator.storage.yaml_backend import YamlLanguageRepository

    entry = YamlLanguageRepository(webui_app.LANGUAGES_DIR).load("edit-twice").lexicon.by_gloss("water")
    assert entry.notes.count("(manually edited)") == 1


def test_lexicon_edit_rejects_ipa_with_an_unmodeled_symbol(client):
    client.post("/api/generate", json={"prompt": "p", "name": "Edit Bad Ipa", "seed": 1, "llm": "fake"})
    response = client.post("/api/languages/edit-bad-ipa/lexicon/edit", json={"gloss": "water", "ipa": "xyz123"})
    assert response.status_code == 400


def test_lexicon_edit_rejects_empty_romanization_or_ipa(client):
    client.post("/api/generate", json={"prompt": "p", "name": "Edit Empty", "seed": 1, "llm": "fake"})
    assert client.post("/api/languages/edit-empty/lexicon/edit", json={"gloss": "water", "romanization": "  "}).status_code == 400
    assert client.post("/api/languages/edit-empty/lexicon/edit", json={"gloss": "water", "ipa": ""}).status_code == 400


def test_lexicon_edit_rejects_an_unknown_gloss(client):
    client.post("/api/generate", json={"prompt": "p", "name": "Edit Unknown", "seed": 1, "llm": "fake"})
    response = client.post(
        "/api/languages/edit-unknown/lexicon/edit", json={"gloss": "not-a-real-gloss", "romanization": "x"}
    )
    assert response.status_code == 404


def test_lexicon_edit_rejects_an_unknown_language(client):
    response = client.post("/api/languages/does-not-exist/lexicon/edit", json={"gloss": "water", "romanization": "x"})
    assert response.status_code == 404


def test_lexicon_edit_requires_at_least_one_field(client):
    client.post("/api/generate", json={"prompt": "p", "name": "Edit Nothing", "seed": 1, "llm": "fake"})
    response = client.post("/api/languages/edit-nothing/lexicon/edit", json={"gloss": "water"})
    assert response.status_code == 400


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
@pytest.mark.slow
def test_pronounce_synthesizes_a_multi_word_sentence_with_sapi(client):
    single = client.post("/api/pronounce", json={"ipa": "kat", "tts": "sapi"}).content
    sentence = client.post("/api/pronounce", json={"ipa": "kat mat", "tts": "sapi"}).content
    assert len(sentence) > len(single)  # two words (plus inter-word silence) outlasts one


@pytest.mark.skipif(not _ESPEAK_AVAILABLE, reason="espeak-ng not installed on this machine")
def test_pronounce_synthesizes_with_espeak(client):
    response = client.post("/api/pronounce", json={"ipa": "kat", "tts": "espeak"})
    assert response.status_code == 200
    assert len(response.content) > 0


def test_generate_word_selection_defaults_to_algorithmic_and_round_trips(client):
    body = client.post("/api/generate", json={"prompt": "p", "name": "Ws Default", "seed": 2, "llm": "fake"}).json()
    assert body["grammar"]["word_selection"] == "algorithmic"
    fetched = client.get("/api/languages/ws-default").json()
    assert fetched["grammar"]["word_selection"] == "algorithmic"


def test_generate_accepts_llm_word_selection(client):
    body = client.post(
        "/api/generate", json={"prompt": "p", "name": "Ws Llm", "seed": 2, "llm": "fake", "word_selection": "llm"}
    ).json()
    assert body["grammar"]["word_selection"] == "llm"
    assert len(body["lexicon"]) > 40


def test_generate_rejects_an_invalid_word_selection(client):
    response = client.post(
        "/api/generate", json={"prompt": "p", "name": "Ws Bad", "seed": 2, "llm": "fake", "word_selection": "psychic"}
    )
    assert response.status_code == 400


def test_generate_respects_vocabulary_size_and_defaults_to_400(client):
    default = client.post("/api/generate", json={"prompt": "p", "name": "Vs Default", "seed": 2, "llm": "fake"}).json()
    assert len(default["lexicon"]) >= 390
    small = client.post(
        "/api/generate", json={"prompt": "p", "name": "Vs Small", "seed": 2, "llm": "fake", "vocabulary_size": 60}
    ).json()
    assert 55 <= len(small["lexicon"]) <= 70


def test_generate_rejects_an_out_of_range_vocabulary_size(client):
    for bad in (0, 100000):
        response = client.post(
            "/api/generate", json={"prompt": "p", "name": "Vs Bad", "seed": 2, "llm": "fake", "vocabulary_size": bad}
        )
        assert response.status_code == 400


def test_options_endpoint_reports_the_max_vocabulary_size(client):
    assert client.get("/api/options").json()["max_vocabulary_size"] > 400


def test_generate_reports_and_accepts_the_foreign_names_trait(client):
    auto = client.post(
        "/api/generate",
        json={"prompt": "p", "name": "Fn Auto", "seed": 2, "llm": "fake", "vocabulary_size": 40,
              "source_languages": [{"name": "Mandarin", "weight": None}], "strictness": 1.0},
    ).json()
    assert auto["grammar"]["foreign_names"] == "adapt"  # derived from the source language
    forced = client.post(
        "/api/generate",
        json={"prompt": "p", "name": "Fn Keep", "seed": 2, "llm": "fake", "vocabulary_size": 40,
              "foreign_names": "keep"},
    ).json()
    assert forced["grammar"]["foreign_names"] == "keep"


def test_generate_rejects_an_invalid_foreign_names_value(client):
    response = client.post(
        "/api/generate",
        json={"prompt": "p", "name": "Fn Bad", "seed": 2, "llm": "fake", "foreign_names": "translate"},
    )
    assert response.status_code == 400


def test_generate_with_real_words_and_evolution_reports_them_and_warns_on_a_split_vocabulary(client):
    body = client.post(
        "/api/generate",
        json={"prompt": "p", "name": "Real Dutch", "seed": 3, "llm": "fake", "vocabulary_size": 60,
              "source_languages": [{"name": "Dutch", "weight": None}], "strictness": 1.0,
              "word_strictness": 1.0, "evolve_years": 200},
    ).json()
    assert body["real_words"] > 30
    assert body["grammar"]["evolved_years"] == 200
    assert body["warnings"] == []
    split = client.post(
        "/api/generate",
        json={"prompt": "p", "name": "Split", "seed": 3, "llm": "fake", "vocabulary_size": 60,
              "source_languages": [{"name": "Dutch", "weight": None}], "strictness": 0.1, "word_strictness": 1.0},
    ).json()
    assert len(split["warnings"]) == 1


def test_generate_rejects_out_of_range_word_strictness_and_evolve_years(client):
    for extra in ({"word_strictness": 1.5}, {"evolve_years": -1}):
        response = client.post(
            "/api/generate", json={"prompt": "p", "name": "Bad Range", "seed": 3, "llm": "fake", **extra}
        )
        assert response.status_code == 400
