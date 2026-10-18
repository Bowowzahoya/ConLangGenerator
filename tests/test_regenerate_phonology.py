"""``generator.regenerate_phonology``/``regenerate_phonology_adapt_words``
-- "Tweaking an existing language" items 2 and 4 (docs/DEFERRED.md):
re-rolling a saved language's own phonology from an edited phonology-only
trait, while its grammar's own typological choices stay byte-identical to
the original, with a choice of a fresh lexicon or the old one adapted to
the new sound inventory."""

import pytest

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.generator import (
    generate_language,
    regenerate_phonology,
    regenerate_phonology_adapt_words,
)
from conlang_generator.llm.fake_client import FakeLLMClient


def _base():
    return generate_language("Base", GenerationSpec(prompt="a test language", seed=7), FakeLLMClient())


def _tonal_base():
    return generate_language(
        "TonalBase", GenerationSpec(prompt="a test language", seed=7, force_tonal=True), FakeLLMClient()
    )


def test_regenerate_phonology_keeps_grammar_typology_identical():
    base = _base()
    tweaked = regenerate_phonology("Tweaked", base, {"altitude": 1.0}, FakeLLMClient())
    g, h = base.grammar, tweaked.grammar
    assert (g.word_order, g.alignment, g.morphological_type) == (h.word_order, h.alignment, h.morphological_type)
    assert (g.has_articles, g.has_overt_copula, g.adjective_after_noun) == (
        h.has_articles, h.has_overt_copula, h.adjective_after_noun,
    )
    assert g.cases == h.cases
    assert g.tenses == h.tenses


def test_regenerate_phonology_actually_changes_the_phonology():
    base = _base()
    tweaked = regenerate_phonology("Tweaked", base, {"altitude": 1.0}, FakeLLMClient())
    assert tweaked.phonology.consonants != base.phonology.consonants


def test_regenerate_phonology_recoins_the_lexicon_fresh():
    # "Regenerate words" mode (item 3) falls out of this for free -- the
    # lexicon is coined fresh against the new phonology, not reused.
    base = _base()
    tweaked = regenerate_phonology("Tweaked", base, {"aesthetic_harshness": 1.0}, FakeLLMClient())
    base_spellings = {e.primary_gloss: e.romanization for e in base.lexicon.entries}
    tweaked_spellings = {e.primary_gloss: e.romanization for e in tweaked.lexicon.entries}
    assert base_spellings != tweaked_spellings


def test_regenerate_phonology_is_reproducible():
    base = _base()
    a = regenerate_phonology("Tweaked", base, {"phonotactic_restrictiveness": 0.7}, FakeLLMClient())
    b = regenerate_phonology("Tweaked", base, {"phonotactic_restrictiveness": 0.7}, FakeLLMClient())
    assert a == b


@pytest.mark.parametrize("field", ["altitude", "aesthetic_harshness", "phonotactic_restrictiveness"])
def test_regenerate_phonology_accepts_every_allowed_field(field):
    base = _base()
    regenerate_phonology("Tweaked", base, {field: 0.5}, FakeLLMClient())  # must not raise


def test_regenerate_phonology_rejects_a_grammar_affecting_trait():
    base = _base()
    with pytest.raises(ValueError, match="social_hierarchy"):
        regenerate_phonology("Tweaked", base, {"social_hierarchy": 0.5}, FakeLLMClient())


def test_regenerate_phonology_rejects_isolation_despite_looking_phonology_adjacent():
    # isolation also nudges grammar (ergative alignment, morphology type)
    # -- see PHONOLOGY_ONLY_TRAIT_FIELDS's own docstring for why this one
    # specifically is excluded despite the tempting name.
    base = _base()
    with pytest.raises(ValueError, match="isolation"):
        regenerate_phonology("Tweaked", base, {"isolation": 0.5}, FakeLLMClient())


def test_regenerate_phonology_rejects_a_mix_with_one_out_of_scope_field():
    base = _base()
    with pytest.raises(ValueError, match="spatial_reference"):
        regenerate_phonology("Tweaked", base, {"altitude": 0.5, "spatial_reference": 0.5}, FakeLLMClient())


def test_regenerate_phonology_empty_overrides_still_rerolls_phonology():
    # No trait actually changed, but phonology is still re-rolled from the
    # same (now independent) stream -- deterministic, so it reproduces
    # byte-identically to the base language's own phonology.
    base = _base()
    result = regenerate_phonology("Base2", base, {}, FakeLLMClient())
    assert result.phonology == base.phonology


# --- regenerate_phonology_adapt_words ("reuse old words, adapted" mode, item 4) ---


def test_adapt_words_keeps_grammar_typology_identical():
    base = _base()
    adapted = regenerate_phonology_adapt_words("Adapted", base, {"altitude": 1.0}, FakeLLMClient())
    g, h = base.grammar, adapted.grammar
    assert (g.word_order, g.alignment, g.morphological_type) == (h.word_order, h.alignment, h.morphological_type)
    assert g.cases == h.cases and g.tenses == h.tenses


def test_adapt_words_keeps_the_same_glosses_in_the_same_order():
    base = _base()
    adapted = regenerate_phonology_adapt_words("Adapted", base, {"aesthetic_harshness": 1.0}, FakeLLMClient())
    assert [e.glosses for e in adapted.lexicon.entries] == [e.glosses for e in base.lexicon.entries]
    assert [e.pos for e in adapted.lexicon.entries] == [e.pos for e in base.lexicon.entries]


def test_adapt_words_preserves_non_phonological_metadata():
    base = _base()
    adapted = regenerate_phonology_adapt_words("Adapted", base, {"altitude": 1.0}, FakeLLMClient())
    for old, new in zip(base.lexicon.entries, adapted.lexicon.entries):
        assert new.root == old.root
        assert new.word_class == old.word_class
        assert new.notes == old.notes
        assert new.real_word == old.real_word


def test_adapt_words_actually_changes_at_least_some_spellings():
    base = _base()
    adapted = regenerate_phonology_adapt_words("Adapted", base, {"altitude": 1.0}, FakeLLMClient())
    base_ipa = [e.ipa for e in base.lexicon.entries]
    adapted_ipa = [e.ipa for e in adapted.lexicon.entries]
    assert base_ipa != adapted_ipa


def test_adapt_words_is_reproducible():
    base = _base()
    a = regenerate_phonology_adapt_words("Adapted", base, {"phonotactic_restrictiveness": 0.6}, FakeLLMClient())
    b = regenerate_phonology_adapt_words("Adapted", base, {"phonotactic_restrictiveness": 0.6}, FakeLLMClient())
    assert a == b


def test_adapt_words_still_validates_trait_overrides():
    base = _base()
    with pytest.raises(ValueError, match="social_hierarchy"):
        regenerate_phonology_adapt_words("Adapted", base, {"social_hierarchy": 0.5}, FakeLLMClient())


def test_adapt_words_clears_tones_on_a_tonal_base_language_without_crashing():
    # Known v1 limitation (documented on the function itself): fit_ipa
    # only fits the segmental shape, so a tonal base language's own
    # tones can't be carried through faithfully -- every adapted entry's
    # own `tones` is cleared to () rather than left stale/inconsistent
    # with its now-unmarked ipa.
    base = _tonal_base()
    assert any(e.tones for e in base.lexicon.entries)
    adapted = regenerate_phonology_adapt_words("Adapted", base, {"altitude": 1.0}, FakeLLMClient())
    assert all(e.tones == () for e in adapted.lexicon.entries)
    assert len(adapted.lexicon.entries) == len(base.lexicon.entries)


def test_adapt_words_keeps_an_exact_real_words_own_spelling_when_its_sounds_survive():
    # Real bug caught from a direct user report: real Dutch "leeg" (an
    # exact source_word_strictness=1.0 copy -- real_words._build_real_
    # entry's own notes="real word: ..." branch, spelling = the real
    # word's own literal form, never derived from RomanizationScheme at
    # all) was coming out "leech" after an adapt-mode tweak, purely
    # because this language's own (freshly rolled) orthography spells
    # /x/ differently than Dutch itself does -- even though the word's
    # own ipa never actually changed. An exact real word whose sounds
    # still all fit the new inventory unchanged must keep its own real
    # spelling verbatim, not get silently re-romanized like an ordinary
    # coined word.
    traits = TraitProfile(source_languages=("Dutch",), source_language_strictness=1.0, source_word_strictness=1.0)
    base = generate_language(
        "RealBase", GenerationSpec(prompt="p", seed=3, traits=traits, vocabulary_size=400), FakeLLMClient()
    )
    empty = base.lexicon.by_gloss("empty")
    assert empty.notes.startswith("real word:")
    assert empty.real_word is not None and empty.real_word.form == "leeg"

    adapted = regenerate_phonology_adapt_words("RealTweaked", base, {"altitude": 0.5}, FakeLLMClient())
    adapted_empty = adapted.lexicon.by_gloss("empty")
    if adapted_empty.ipa == empty.ipa:
        assert adapted_empty.romanization == empty.romanization == "leeg"
