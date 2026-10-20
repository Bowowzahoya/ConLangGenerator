"""Compound/derivation/ablaut word formation (``traits.compound_likelihood``) -- see
``generation/derivation_gen.py``'s own word-formation docstrings and
``generation/word_relations.py`` for the curated relatedness table this exercises."""

from __future__ import annotations

import random

from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import derivation_gen, lexicon_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.word_relations import WordRelation
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import translator

_SEEDS = range(30)


def _related_count(compound_likelihood: float) -> float:
    hits = 0
    for seed in _SEEDS:
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(compound_likelihood=compound_likelihood), vocabulary_size=496,
        )
        lang = generate_language("Test", spec, FakeLLMClient())
        hits += sum(1 for e in lang.lexicon.entries if e.compound_of is not None or e.notes.startswith("derived:"))
    return hits / len(_SEEDS)


def test_compound_likelihood_gradient_is_monotonic():
    low = _related_count(-1.0)
    neutral = _related_count(0.0)
    high = _related_count(1.0)
    assert low <= neutral < high


def test_core_meanings_are_never_flagged_for_word_formation():
    rng = random.Random(1)
    for gloss, pos in lexicon_gen.CORE_MEANINGS:
        assert derivation_gen.should_attempt_word_formation(rng, 1.0, pos, is_core_meaning=True) is False


def test_function_like_pos_are_never_flagged_for_word_formation():
    rng = random.Random(1)
    for pos in (PartOfSpeech.PRONOUN, PartOfSpeech.PARTICLE, PartOfSpeech.NUMERAL):
        assert derivation_gen.should_attempt_word_formation(rng, 1.0, pos, is_core_meaning=False) is False


def test_nouns_are_flagged_more_often_than_verbs_at_the_same_trait_strength():
    rng = random.Random(1)
    noun_hits = sum(
        derivation_gen.should_attempt_word_formation(rng, 0.5, PartOfSpeech.NOUN, False) for _ in range(400)
    )
    verb_hits = sum(
        derivation_gen.should_attempt_word_formation(rng, 0.5, PartOfSpeech.VERB, False) for _ in range(400)
    )
    assert noun_hits > verb_hits


def test_ablaut_derivation_builds_a_real_death_from_die_relationship():
    # Seed empirically found (same "fixed seed, found by search" convention as every other
    # content-dependent fixture in this suite) to roll both the `ablaut_v2n` rule and a usable
    # `ablaut` stem map for this inventory -- confirmed directly, not assumed.
    spec = GenerationSpec(prompt="p", seed=18, traits=TraitProfile(compound_likelihood=1.0), vocabulary_size=496)
    lang = generate_language("Test", spec, FakeLLMClient())
    die = lang.lexicon.by_gloss("die")
    death = lang.lexicon.by_gloss("death")
    assert die is not None and death is not None
    assert "ablaut_v2n of die" in death.notes
    assert death.ipa != die.ipa  # a real vowel change happened, not a no-op
    assert death.pos is PartOfSpeech.NOUN


def test_agent_derivation_builds_teacher_from_teach():
    spec = GenerationSpec(prompt="p", seed=1, traits=TraitProfile(compound_likelihood=1.0), vocabulary_size=496)
    lang = generate_language("Test", spec, FakeLLMClient())
    teach = lang.lexicon.by_gloss("teach")
    teacher = lang.lexicon.by_gloss("teacher")
    assert teach is not None and teacher is not None
    assert "agent of teach" in teacher.notes
    assert teacher.ipa.startswith(teach.ipa.rstrip("ˈ"))  # a real suffix attached, not a fresh root


def test_word_formation_llm_mode_is_deterministic_with_the_fake_client():
    client = FakeLLMClient()
    first = derivation_gen.relation_for("xyzzyplugh", PartOfSpeech.NOUN, "llm", client, "fake-llm")
    second = derivation_gen.relation_for("xyzzyplugh", PartOfSpeech.NOUN, "llm", client, "fake-llm")
    assert first == second


# --- translation-time recursive coinage: depth control and the archaic-synonym fallback ---


def _compounding_language():
    """A real generated language, coerced (``model_copy``) to guarantee compounding is on and the
    typical-element budget is tiny (2) -- so a forced-deep recursive split reliably exceeds it,
    without depending on any one seed happening to roll that combination."""
    spec = GenerationSpec(prompt="p", seed=1, traits=TraitProfile(), vocabulary_size=496, word_formation="llm")
    lang = generate_language("Test", spec, FakeLLMClient())
    return lang.model_copy(update={"grammar": lang.grammar.model_copy(update={
        "compounding": True, "compound_typical_elements": 2, "compound_order": "modifier_head", "compound_linker": (),
    })})


def test_depth_ceiling_is_never_exceeded(monkeypatch):
    # Every gloss "wants" to keep splitting forever (a pathological always-compound relation) --
    # the hard ceiling (5) must still stop recursion regardless of trait/roll values.
    def always_split(gloss, pos, word_formation, llm_client, model):
        return WordRelation("compound", (f"{gloss}a", f"{gloss}b"))

    monkeypatch.setattr(translator.derivation_gen, "relation_for", always_split)
    lang = _compounding_language()
    coined: list[LexicalEntry] = []
    _language, entry = translator._resolve_component(
        lang, "runaway", PartOfSpeech.NOUN, coined, FakeLLMClient(), "fake-llm", depth=0,
    )
    assert entry is not None
    assert len(coined) <= 5 + 2  # a handful of components, never an unbounded chain


def test_archaic_synonym_fallback_produces_a_second_retrievable_entry():
    lang = _compounding_language()
    # Plant an already-committed compound for "oldword" directly (as `_compound_entry` would).
    base_entries = lang.lexicon.entries
    committed = LexicalEntry(
        ipa="tatat", romanization="tatat", glosses=("oldword",), pos=PartOfSpeech.NOUN,
        notes="compound: part1 + part2", compound_of=("part1", "part2"),
    )
    lang = lang.model_copy(update={"lexicon": lang.lexicon.model_copy(update={"entries": base_entries + (committed,)})})
    coined: list[LexicalEntry] = []
    # depth=3 > compound_typical_elements=2 -- the budget says "no more splitting," so the
    # already-committed compound can't just be reused as a fresh sub-element.
    new_language, resolved = translator._resolve_component(
        lang, "oldword", PartOfSpeech.NOUN, coined, FakeLLMClient(), "fake-llm", depth=3,
    )
    assert resolved.primary_gloss == "oldword (archaic)"
    assert resolved.compound_of is None  # a real, independent non-compound coinage
    assert new_language.lexicon.by_gloss("oldword (archaic)") is resolved
    assert new_language.lexicon.by_gloss("oldword") is committed  # the original is untouched
