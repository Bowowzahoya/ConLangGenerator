"""Wiring existing traits: three of docs/DEFERRED.md's six "extracted and
stored but consumed by nothing" traits get a cheap, precedented wire-up --
evidentiality_culture (EVIDENTIAL_SYSTEMS richness), spatial_reference
(locative/ablative/allative case richness, specifically -- not
instrumental/comitative), and salient_vocabulary_domains (folded into the
same word-coining context channel salient_context already uses). The other
three (ritual_register, taboo_register, terrain_communication_distance)
have no existing mechanism to hook into yet and stay unconsumed."""

import random

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile, coining_context
from conlang_generator.generation import inflection_gen, np_followups_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from tests._shared_language import cached_language

_CLIENT = FakeLLMClient()

_language = cached_language


def _spatial_grammar():
    return _language(1).grammar.model_copy(update={"adposition_case_strategy": "case", "cases": ()})


# --- coining_context -----------------------------------------------------


def test_coining_context_combines_both_fields():
    traits = TraitProfile(salient_context="a cold mountain village", salient_vocabulary_domains=("herding", "weaving"))
    assert coining_context(traits) == "a cold mountain village (herding, weaving culture)"


def test_coining_context_falls_back_to_either_field_alone():
    assert coining_context(TraitProfile(salient_vocabulary_domains=("seafaring",))) == "seafaring culture"
    assert coining_context(TraitProfile(salient_context="a windswept coast")) == "a windswept coast"


def test_coining_context_matches_old_salient_context_only_behavior():
    # Backward compatibility: an older saved language's traits (no
    # salient_vocabulary_domains) get back exactly their old salient_context.
    traits = TraitProfile(salient_context="a windswept coast")
    assert coining_context(traits) == traits.salient_context == "a windswept coast"
    assert coining_context(TraitProfile()) == ""


def test_coining_context_is_threaded_into_word_coining():
    language = _language(1)
    spy_requests: list = []

    class _Spy(FakeLLMClient):
        def complete(self, request):
            spy_requests.append(request)
            return super().complete(request)

    from conlang_generator.translation.expansion import coin_word
    from conlang_generator.core.lexicon import PartOfSpeech

    language = language.model_copy(
        update={
            "spec": language.spec.model_copy(
                update={"traits": language.spec.traits.model_copy(update={"salient_vocabulary_domains": ("piracy",)})}
            )
        }
    )
    coin_word(language, "zzsurelynewzz", PartOfSpeech.NOUN, _Spy())
    assert any("piracy" in (r.prompt or "") for r in spy_requests) or language.spec.word_selection != "llm"


# --- evidentiality_culture -------------------------------------------------


class _AspectGrammar:
    tenses: tuple = ()
    aspects: tuple = ()
    moods: tuple = ()


def test_evidentiality_culture_zero_or_negative_keeps_the_original_rates():
    grammar = _AspectGrammar()
    for trait in (0.0, -1.0):
        counts = {0: 0, 1: 0, 2: 0, 3: 0}
        n = 2000
        for i in range(n):
            result = inflection_gen.roll_aspect_followups(random.Random(i), grammar, trait)
            counts[inflection_gen.EVIDENTIAL_SYSTEMS.index(result["evidentials"])] += 1
        assert abs(counts[0] / n - 0.55) < 0.05
        assert abs(counts[1] / n - 0.15) < 0.05


def test_evidentiality_culture_raises_richer_systems_proportionally():
    grammar = _AspectGrammar()
    n = 3000
    baseline = sum(1 for i in range(n) if inflection_gen.roll_aspect_followups(random.Random(i), grammar, 0.0)["evidentials"] == ())
    rich = sum(1 for i in range(n) if inflection_gen.roll_aspect_followups(random.Random(i), grammar, 1.0)["evidentials"] == ())
    assert rich < baseline * 0.7  # meaningfully less "no evidentiality"
    # The three richer systems keep roughly their original relative sizes.
    rich_counts = [0, 0, 0]
    for i in range(n):
        result = inflection_gen.roll_aspect_followups(random.Random(i), grammar, 1.0)
        if result["evidentials"]:
            rich_counts[len(result["evidentials"]) - 1] += 1
    assert max(rich_counts) - min(rich_counts) < n * 0.08


# --- spatial_reference ------------------------------------------------------


def test_spatial_reference_zero_keeps_the_original_flat_rate():
    grammar = _spatial_grammar()
    n = 2000
    counts = {c: 0 for c in np_followups_gen.SPATIAL_CASES}
    for i in range(n):
        for c in np_followups_gen.roll_round_three(random.Random(i), grammar, 0.0)["cases"]:
            counts[c] += 1
    for c in np_followups_gen.SPATIAL_CASES:
        assert abs(counts[c] / n - 0.3) < 0.05


def test_spatial_reference_raises_only_the_truly_spatial_cases():
    grammar = _spatial_grammar()
    n = 3000
    counts = {c: 0 for c in np_followups_gen.SPATIAL_CASES}
    for i in range(n):
        for c in np_followups_gen.roll_round_three(random.Random(i), grammar, 1.0)["cases"]:
            counts[c] += 1
    for c in ("locative", "ablative", "allative"):
        assert counts[c] / n > 0.6
    for c in ("instrumental", "comitative"):
        assert abs(counts[c] / n - 0.3) < 0.05


# --- end-to-end through generate_language -----------------------------------


def test_generate_language_passes_evidentiality_culture_through(monkeypatch):
    seen = []
    original = inflection_gen.roll_aspect_followups

    def spy(rng, grammar, evidentiality_culture=0.0):
        seen.append(evidentiality_culture)
        return original(rng, grammar, evidentiality_culture)

    monkeypatch.setattr(inflection_gen, "roll_aspect_followups", spy)
    generate_language("Test", GenerationSpec(prompt="p", seed=9, traits=TraitProfile(evidentiality_culture=0.73)), _CLIENT)
    assert seen == [0.73]


def test_generate_language_passes_spatial_reference_through(monkeypatch):
    seen = []
    original = np_followups_gen.roll_round_three

    def spy(rng, grammar, spatial_reference=0.0):
        seen.append(spatial_reference)
        return original(rng, grammar, spatial_reference)

    monkeypatch.setattr(np_followups_gen, "roll_round_three", spy)
    generate_language("Test", GenerationSpec(prompt="p", seed=9, traits=TraitProfile(spatial_reference=-0.42)), _CLIENT)
    assert seen == [-0.42]
