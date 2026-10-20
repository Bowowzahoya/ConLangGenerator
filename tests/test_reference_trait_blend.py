"""Tests for ``reference_languages.blend_toward_reference`` -- "grading
reference languages on worldbuilding traits" (docs/DEFERRED.md, chapter
11): nudging a language's own trait reading toward a matched reference
profile's own curated ``typical_<field>`` values, independent of (not
instead of) the existing sound/word-strictness mechanism."""

from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.reference_languages import ReferenceLanguageProfile, blend_toward_reference

fastapi = __import__("pytest").importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from conlang_generator.webui import app as webui_app  # noqa: E402


def _profile(name: str, **typical: float) -> ReferenceLanguageProfile:
    return ReferenceLanguageProfile(
        name=name, consonants=("p",), vowels=("a",), coda_profile="none", max_onset=1, tonal=False,
        **{f"typical_{k}": v for k, v in typical.items()},
    )


def test_no_matched_profiles_leaves_traits_untouched():
    traits = TraitProfile(social_hierarchy=0.1)
    assert blend_toward_reference(traits, (), 1.0) == traits


def test_blend_weight_zero_is_a_true_no_op():
    traits = TraitProfile(social_hierarchy=0.1)
    weighted = ((_profile("A", social_hierarchy=0.9), 1.0),)
    assert blend_toward_reference(traits, weighted, 0.0) == traits


def test_blend_weight_one_snaps_to_the_curated_average():
    traits = TraitProfile(social_hierarchy=0.0)
    weighted = ((_profile("A", social_hierarchy=0.8), 1.0),)
    blended = blend_toward_reference(traits, weighted, 1.0)
    assert blended.social_hierarchy == 0.8


def test_a_field_only_some_matched_profiles_curated_averages_only_those():
    # B hasn't curated social_hierarchy at all -- it must not count as a
    # silent "0.0 vote", only A's own 0.8 should be averaged in.
    traits = TraitProfile(social_hierarchy=0.0)
    weighted = ((_profile("A", social_hierarchy=0.8), 0.5), (_profile("B"), 0.5))
    blended = blend_toward_reference(traits, weighted, 1.0)
    assert blended.social_hierarchy == 0.8


def test_an_uncurated_field_is_left_completely_untouched():
    traits = TraitProfile(isolation=0.3)
    weighted = ((_profile("A", social_hierarchy=0.8), 1.0),)  # curates a different field
    blended = blend_toward_reference(traits, weighted, 1.0)
    assert blended.isolation == 0.3


def test_partial_blend_weight_interpolates_linearly():
    traits = TraitProfile(social_hierarchy=0.0)
    weighted = ((_profile("A", social_hierarchy=1.0), 1.0),)
    blended = blend_toward_reference(traits, weighted, 0.25)
    assert abs(blended.social_hierarchy - 0.25) < 1e-9


def test_other_fields_stay_byte_identical():
    traits = TraitProfile(social_hierarchy=0.0, isolation=0.4, altitude=-0.2)
    weighted = ((_profile("A", social_hierarchy=0.8), 1.0),)
    blended = blend_toward_reference(traits, weighted, 1.0)
    assert blended.isolation == 0.4
    assert blended.altitude == -0.2


# --- end-to-end: a real curated profile (Japanese, social_hierarchy)
# nudges a generated language's own trait reading without an explicit
# --trait override, and an explicit override still wins outright. ---


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(webui_app, "CACHE_DIR", tmp_path / ".cache")
    monkeypatch.setattr(webui_app, "LANGUAGES_DIR", tmp_path / "conlangs")
    return TestClient(webui_app.app)


def test_high_strictness_japanese_source_nudges_social_hierarchy_without_an_override(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post(
        "/api/generate",
        json={
            "prompt": "a plain language", "name": "blend-test", "seed": 1, "llm": "fake",
            "vocabulary_size": 10,
            "source_languages": [{"name": "Japanese", "weight": 1.0}],
            "strictness": 1.0,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["traits"]["social_hierarchy"] > 0.5


def test_explicit_trait_override_still_wins_over_the_blend(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post(
        "/api/generate",
        json={
            "prompt": "a plain language", "name": "blend-override-test", "seed": 1, "llm": "fake",
            "vocabulary_size": 10,
            "source_languages": [{"name": "Japanese", "weight": 1.0}],
            "strictness": 1.0,
            "trait_overrides": {"social_hierarchy": -0.9},
        },
    )
    assert response.status_code == 200
    assert response.json()["traits"]["social_hierarchy"] == -0.9
