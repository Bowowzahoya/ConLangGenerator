"""Evolving the freshly generated language in the same step (``evolve_years``,
defaulting to the prompt-inferred ``time_depth_years``)."""

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.generator import generate_evolved_language, generate_language, resolve_evolve_years
from conlang_generator.llm.fake_client import FakeLLMClient


def _traits(**extra):
    return TraitProfile(
        source_languages=("Dutch",), source_language_strictness=1.0, source_word_strictness=1.0, **extra
    )


def _spec(**kwargs):
    traits = kwargs.pop("traits", _traits())
    return GenerationSpec(prompt="p", seed=3, traits=traits, vocabulary_size=60, **kwargs)


def test_zero_or_missing_years_returns_the_plain_generated_language():
    plain = generate_language("T", _spec(), FakeLLMClient())
    assert generate_evolved_language("T", _spec(), FakeLLMClient()) == plain
    assert generate_evolved_language("T", _spec(evolve_years=0), FakeLLMClient()).lexicon == plain.lexicon


def test_evolving_changes_real_words_by_sound_change_and_records_history():
    base = generate_language("T", _spec(), FakeLLMClient())
    evolved = generate_evolved_language("T", _spec(evolve_years=400), FakeLLMClient())
    changed = [
        g for g in ("water", "fire", "mountain", "hand", "eat", "stone")
        if base.lexicon.by_gloss(g).romanization != evolved.lexicon.by_gloss(g).romanization
    ]
    assert changed  # real Dutch words really moved
    assert evolved.history[-1].startswith("evolved 400 years")
    assert evolved.spec.evolve_years == 400


def test_the_callers_own_settings_survive_evolution():
    spec = _spec(evolve_years=200, word_selection="algorithmic", foreign_names="adapt", fantasy=True)
    evolved = generate_evolved_language("T", spec, FakeLLMClient())
    assert (evolved.spec.foreign_names, evolved.spec.fantasy, evolved.spec.vocabulary_size) == ("adapt", True, 60)
    assert evolved.spec.traits.source_word_strictness == 1.0


def test_years_default_to_the_prompt_inferred_time_depth_unless_set_explicitly():
    inferred = _spec(traits=_traits(time_depth_years=300))
    assert resolve_evolve_years(inferred) == 300
    assert generate_evolved_language("T", inferred, FakeLLMClient()).history[-1].startswith("evolved 300 years")
    forced_off = _spec(traits=_traits(time_depth_years=300), evolve_years=0)
    assert resolve_evolve_years(forced_off) == 0
    assert resolve_evolve_years(_spec(evolve_years=50, traits=_traits(time_depth_years=300))) == 50
    assert resolve_evolve_years(_spec()) == 0
