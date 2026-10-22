"""``generator.regenerate_script`` -- "Tweaking an existing language"
item 11 (docs/DEFERRED.md): re-rolling a saved language's own invented
script from a forced ``ScriptTraits`` dial, while phonology/grammar/
romanization/lexicon (both IPA and spelling) stay byte-identical --
a separate axis from phonology/orthography tweaking, and unlike either
of those, 100% procedural (no LLM involved)."""

import pytest

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.generator import generate_language, regenerate_script
from conlang_generator.llm.fake_client import FakeLLMClient


def _base(**spec_kwargs):
    return generate_language(
        "Base", GenerationSpec(prompt="a test language", seed=7, force_own_script=True, **spec_kwargs),
        FakeLLMClient(),
    )


def test_regenerate_script_keeps_phonology_grammar_romanization_and_ipa_identical():
    base = _base()
    tweaked = regenerate_script("Tweaked", base, {"stroke_continuity": 1.0})
    assert tweaked.phonology == base.phonology
    assert tweaked.syllable_structure == base.syllable_structure
    assert tweaked.grammar == base.grammar
    assert tweaked.romanization == base.romanization
    assert [e.ipa for e in tweaked.lexicon.entries] == [e.ipa for e in base.lexicon.entries]
    assert [e.romanization for e in tweaked.lexicon.entries] == [e.romanization for e in base.lexicon.entries]


def test_regenerate_script_actually_changes_the_script():
    base = _base()
    tweaked = regenerate_script("Tweaked", base, {"stroke_continuity": 1.0, "complexity": 1.0})
    assert tweaked.script != base.script
    assert tweaked.script.direction == base.script.direction  # script-wide rolls stay unchanged
    assert (tweaked.script.grid_max_x, tweaked.script.grid_max_y) == (base.script.grid_max_x, base.script.grid_max_y)


def test_regenerate_script_is_reproducible():
    base = _base()
    a = regenerate_script("Tweaked", base, {"dot_prevalence": 0.5})
    b = regenerate_script("Tweaked", base, {"dot_prevalence": 0.5})
    assert a == b


def test_regenerate_script_only_applies_non_default_overrides():
    # An override field left unset keeps whatever the base language's own forced_script_traits
    # already had for that dial, the same "force just the dials you set" shape ScriptTraitsForce
    # itself already documents.
    from conlang_generator.core.script import ScriptTraitsForce

    base = _base(forced_script_traits=ScriptTraitsForce(terminal_style=0.8))
    tweaked = regenerate_script("Tweaked", base, {"dot_prevalence": 0.5})
    assert tweaked.spec.forced_script_traits.terminal_style == 0.8
    assert tweaked.spec.forced_script_traits.dot_prevalence == 0.5


def test_regenerate_script_rejects_an_unknown_trait():
    base = _base()
    with pytest.raises(ValueError, match="dot_density"):
        regenerate_script("Tweaked", base, {"dot_density": 1.0})


def test_regenerate_script_rejects_a_language_with_no_script():
    base = generate_language("Base", GenerationSpec(prompt="a test language", seed=7), FakeLLMClient())
    assert base.script is None
    with pytest.raises(ValueError, match="no invented script"):
        regenerate_script("Tweaked", base, {"dot_prevalence": 0.5})


def test_regenerate_script_leaves_a_render_only_dial_edit_byte_identical():
    # weight/slant/... are never read by script_gen.py -- editing only one of them should still
    # rebuild script.glyphs, but to the exact same geometry, since nothing topology-affecting changed.
    base = _base()
    tweaked = regenerate_script("Tweaked", base, {"weight": 0.9, "slant": -0.7})
    assert tweaked.script.glyphs == base.script.glyphs
    assert tweaked.script.traits.weight == 0.9
    assert tweaked.script.traits.slant == -0.7
