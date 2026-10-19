"""``generator.regenerate_orthography`` -- "Tweaking an existing language"
item 9 (docs/DEFERRED.md): re-rolling a saved language's own Roman
Orthography (romanization scheme + every lexicon entry's own spelling)
from a forced style, while phonology/grammar/script and every word's own
IPA stay byte-identical to the original -- a separate axis from phonology
tweaking (item 2/4), not combinable with it in one call (see the
function's own docstring for why: romanization draws from the same
shared ``rng`` stream grammar/lexicon coining also draw from)."""

from conlang_generator.core.romanization import OrthographyForce
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.generator import generate_language, regenerate_orthography
from conlang_generator.llm.fake_client import FakeLLMClient


def _base():
    return generate_language("Base", GenerationSpec(prompt="a test language", seed=7), FakeLLMClient())


def test_regenerate_orthography_keeps_phonology_grammar_and_ipa_identical():
    base = _base()
    tweaked = regenerate_orthography("Tweaked", base, OrthographyForce(style="wade-giles-style"), FakeLLMClient())
    assert tweaked.phonology == base.phonology
    assert tweaked.syllable_structure == base.syllable_structure
    assert tweaked.grammar == base.grammar
    assert tweaked.script == base.script
    assert [e.ipa for e in tweaked.lexicon.entries] == [e.ipa for e in base.lexicon.entries]
    assert [e.glosses for e in tweaked.lexicon.entries] == [e.glosses for e in base.lexicon.entries]


def test_regenerate_orthography_actually_changes_spellings():
    base = _base()
    tweaked = regenerate_orthography("Tweaked", base, OrthographyForce(style="wade-giles-style"), FakeLLMClient())
    base_spellings = [e.romanization for e in base.lexicon.entries]
    tweaked_spellings = [e.romanization for e in tweaked.lexicon.entries]
    assert base_spellings != tweaked_spellings


def test_regenerate_orthography_is_reproducible():
    base = _base()
    a = regenerate_orthography("Tweaked", base, OrthographyForce(exotic_symbol_style="monoletter"), FakeLLMClient())
    b = regenerate_orthography("Tweaked", base, OrthographyForce(exotic_symbol_style="monoletter"), FakeLLMClient())
    assert a == b


def test_regenerate_orthography_only_applies_non_none_overrides():
    # An override field left unset keeps whatever the base language's own
    # forced_orthography already had for that axis, the same "force just
    # the axes you set" shape OrthographyForce itself already documents.
    base = generate_language(
        "Base",
        GenerationSpec(
            prompt="a test language", seed=7,
            forced_orthography=OrthographyForce(tone_strategy="postposed_digit"),
        ),
        FakeLLMClient(),
    )
    tweaked = regenerate_orthography("Tweaked", base, OrthographyForce(exotic_symbol_style="monoletter"), FakeLLMClient())
    assert tweaked.spec.forced_orthography.tone_strategy == "postposed_digit"
    assert tweaked.spec.forced_orthography.exotic_symbol_style == "monoletter"


def test_regenerate_orthography_keeps_an_exact_real_words_own_spelling():
    traits = TraitProfile(source_languages=("Dutch",), source_language_strictness=1.0, source_word_strictness=1.0)
    base = generate_language(
        "RealBase", GenerationSpec(prompt="p", seed=3, traits=traits, vocabulary_size=400), FakeLLMClient()
    )
    empty = base.lexicon.by_gloss("empty")
    assert empty.notes.startswith("real word:")
    assert empty.romanization == "leeg"

    tweaked = regenerate_orthography("Tweaked", base, OrthographyForce(exotic_symbol_style="monoletter"), FakeLLMClient())
    tweaked_empty = tweaked.lexicon.by_gloss("empty")
    assert tweaked_empty.romanization == "leeg"
    assert tweaked_empty.ipa == empty.ipa


def test_regenerate_orthography_rejects_an_unknown_style():
    base = _base()
    try:
        regenerate_orthography("Tweaked", base, OrthographyForce(style="not-a-real-style"), FakeLLMClient())
    except ValueError:
        return
    raise AssertionError("expected ValueError for an unknown orthography style")
