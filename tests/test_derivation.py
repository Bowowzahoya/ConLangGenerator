"""Derivation and compounding: words built from words the language has."""

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import derivation_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.sound_change import evolve_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.translator import (
    _apply_case,
    _decode_noun,
    _derive_or_compound,
    _lookup_or_coin,
    translate_to_conlang,
    translate_to_english,
)

_CLIENT = FakeLLMClient()
_CACHE: dict[int, object] = {}


def _language(seed: int):
    if seed not in _CACHE:
        _CACHE[seed] = generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())
    return _CACHE[seed]


def _find(predicate, limit: int = 300):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language):
            return language
    raise AssertionError("no seed found")


def _with(language, **updates):
    return language.model_copy(update={"grammar": language.grammar.model_copy(update=updates)})


def _has_rule(name):
    return lambda l: any(r.name == name for r in l.grammar.derivations)


# --- generation -----------------------------------------------------------------


def test_the_derivation_choices_are_rolled():
    grammars = [_language(s).grammar for s in range(1, 100)]
    names = {r.name for g in grammars for r in g.derivations}
    assert names == {n for n, _, _ in derivation_gen.RULES}
    assert any(g.compounding for g in grammars) and not all(g.compounding for g in grammars)
    assert {g.compound_order for g in grammars} == {"modifier_head", "head_modifier"}
    for g in grammars:
        for rule in g.derivations:
            assert (rule.affix.prefix or rule.affix.suffix) and not (rule.affix.prefix and rule.affix.suffix)
            assert (rule.pos_in, rule.pos_out) == next((i, o) for n, i, o in derivation_gen.RULES if n == rule.name)
        assert bool(g.compound_linker) <= g.compounding


def test_agglutinative_languages_derive_more_than_isolating_ones():
    def average(kind):
        chosen = [_language(s).grammar for s in range(1, 200) if _language(s).grammar.morphological_type.value == kind]
        return sum(len(g.derivations) for g in chosen) / max(1, len(chosen))

    assert average("agglutinative") > average("isolating")


def test_derivational_exponents_are_spelled_differently():
    for seed in range(1, 60):
        language = _language(seed)
        spelled = [
            language.romanization.apply("".join(r.affix.prefix or r.affix.suffix)).lower()
            for r in language.grammar.derivations
        ]
        assert len(spelled) == len(set(spelled)), seed


def test_the_new_grammar_fields_default_for_older_saved_languages():
    fields = type(_language(1).grammar).model_fields
    assert fields["derivations"].default == () and fields["compounding"].default is False
    assert fields["compound_order"].default == "modifier_head" and fields["compound_linker"].default == ()


# --- the English analyser ------------------------------------------------------------------------


def _rules_for(word):
    return {name: cands for name, cands in derivation_gen.english_derivations(word)}


def test_the_analyser_proposes_bases_for_derived_english_words():
    assert "teach" in _rules_for("teacher")["agent"]
    assert "dance" in _rules_for("dancer")["agent"] and "run" in _rules_for("runner")["agent"]
    assert "happy" in _rules_for("happiness")["abstract"]
    assert _rules_for("unhappy")["negative"] == ["happy"]
    assert "duck" in _rules_for("duckling")["diminutive"]
    assert "rain" in _rules_for("rainy")["adjectival"] and "sun" in _rules_for("sunny")["adjectival"]
    assert "joy" in _rules_for("joyful")["adjectival"]


def test_the_analyser_leaves_ordinary_words_alone():
    assert derivation_gen.english_derivations("river") == []
    assert derivation_gen.english_derivations("dog") == []
    assert derivation_gen.english_derivations("two words") == []


def test_compound_splits_need_both_parts_to_be_nouns():
    nouns = {"moon", "light", "river", "bank", "sun"}
    is_noun = lambda w: w in nouns  # noqa: E731
    assert derivation_gen.compound_splits("moonlight", is_noun) == [("moon", "light")]
    assert derivation_gen.compound_splits("river-bank", is_noun) == [("river", "bank")]
    assert derivation_gen.compound_splits("moonwalk", is_noun) == []
    assert derivation_gen.compound_splits("sun", is_noun) == []


# --- derivation -----------------------------------------------------------------------------------


def test_a_derived_word_is_its_base_plus_the_languages_own_exponent():
    language = _find(_has_rule("abstract"))
    rule = next(r for r in language.grammar.derivations if r.name == "abstract")
    base = language.lexicon.by_gloss("happy")
    coined: list = []
    updated, entry = _lookup_or_coin(language, "happiness", PartOfSpeech.NOUN, coined, _CLIENT, ["happiness"])
    assert entry.notes == "derived: abstract of happy" and entry.pos is PartOfSpeech.NOUN
    assert entry.glosses == ("happiness",) and coined == [entry]
    assert entry.ipa != base.ipa
    stripped = entry.ipa.replace("ˈ", "")
    exponent = "".join(rule.affix.prefix or rule.affix.suffix)
    assert exponent in stripped or len(exponent) == 0
    assert updated.lexicon.by_gloss("happiness") == entry


def test_a_derived_word_is_reused_not_derived_twice():
    language = _find(_has_rule("agent"))
    updated, first = _lookup_or_coin(language, "teacher", PartOfSpeech.NOUN, [], _CLIENT, ["teacher"])
    coined: list = []
    _, second = _lookup_or_coin(updated, "teacher", PartOfSpeech.NOUN, coined, _CLIENT, ["teacher"])
    assert second == first and coined == []


def test_a_language_without_the_rule_coins_the_word_normally():
    language = _find(lambda l: not _has_rule("agent")(l) and not l.grammar.compounding)
    _, entry = _lookup_or_coin(language, "teacher", PartOfSpeech.NOUN, [], _CLIENT, ["teacher"])
    assert not entry.notes.startswith("derived")


def test_the_word_class_of_the_result_must_match_the_rule():
    language = _find(_has_rule("agent"))
    assert _derive_or_compound(language, "teacher", PartOfSpeech.VERB, []) is None
    assert _derive_or_compound(language, "teacher", PartOfSpeech.NOUN, []) is not None


def test_a_negative_prefix_derives_an_adjective():
    language = _find(_has_rule("negative"))
    rule = next(r for r in language.grammar.derivations if r.name == "negative")
    _, entry = _lookup_or_coin(language, "unhappy", PartOfSpeech.ADJECTIVE, [], _CLIENT, ["unhappy"])
    assert entry.pos is PartOfSpeech.ADJECTIVE and entry.notes == "derived: negative of happy"
    if rule.affix.prefix:
        assert entry.ipa.replace("ˈ", "").startswith("".join(rule.affix.prefix)[:1])


def test_a_derived_noun_inflects_and_decodes_like_any_noun():
    language = _find(lambda l: _has_rule("agent")(l) and l.grammar.number_affixes)
    updated, entry = _lookup_or_coin(language, "teacher", PartOfSpeech.NOUN, [], _CLIENT, ["teacher"])
    label = updated.grammar.number_affixes[0].label
    token = _apply_case(updated, entry, None, label)[0]
    decoded = _decode_noun(updated, token)
    assert decoded is not None and decoded[0] == entry


def test_a_derived_word_is_used_in_a_sentence_and_read_back():
    language = _find(_has_rule("agent"))
    result = translate_to_conlang("I see the teacher.", language, _CLIENT)
    assert [e.notes for e in result.coined] == ["derived: agent of teach"]
    assert "teacher" in translate_to_english(result.text, result.language, _CLIENT).text


# --- compounding -------------------------------------------------------------------------------------


def _compounder(order: str, linked: bool):
    return _find(
        lambda l: l.grammar.compounding and l.grammar.compound_order == order and bool(l.grammar.compound_linker) == linked
        and l.lexicon.by_gloss("moon") is not None and l.lexicon.by_gloss("light") is not None
    )


def test_a_compound_joins_modifier_and_head_in_the_languages_order():
    for order in ("modifier_head", "head_modifier"):
        language = _compounder(order, False)
        moon, light = language.lexicon.by_gloss("moon"), language.lexicon.by_gloss("light")
        _, entry = _lookup_or_coin(language, "moonlight", PartOfSpeech.NOUN, [], _CLIENT, ["moonlight"])
        assert entry.notes == "compound: moon + light"
        first, second = (moon, light) if order == "modifier_head" else (light, moon)
        plain = entry.ipa.replace("ˈ", "")
        assert plain.startswith(first.ipa.replace("ˈ", "")[:2]) and plain.endswith(second.ipa.replace("ˈ", "")[-2:])


def test_a_linking_vowel_sits_between_the_parts():
    language = _compounder("modifier_head", True)
    moon = language.lexicon.by_gloss("moon").ipa.replace("ˈ", "")
    light = language.lexicon.by_gloss("light").ipa.replace("ˈ", "")
    linker = "".join(language.grammar.compound_linker)
    _, entry = _lookup_or_coin(language, "moonlight", PartOfSpeech.NOUN, [], _CLIENT, ["moonlight"])
    assert moon + linker in entry.ipa.replace("ˈ", "").replace("ˌ", "") or linker in entry.ipa


def test_a_hyphenated_compound_is_built_the_same_way():
    language = _compounder("modifier_head", False)
    _, entry = _lookup_or_coin(language, "moon-light", PartOfSpeech.NOUN, [], _CLIENT, ["moon-light"])
    assert entry.notes == "compound: moon + light"


def test_a_language_that_does_not_compound_coins_it():
    language = _find(lambda l: not l.grammar.compounding and l.lexicon.by_gloss("moon") is not None)
    _, entry = _lookup_or_coin(language, "moonlight", PartOfSpeech.NOUN, [], _CLIENT, ["moonlight"])
    assert not entry.notes.startswith("compound")


def test_a_compound_reads_back_and_takes_the_case_of_a_noun():
    language = _compounder("modifier_head", False)
    result = translate_to_conlang("I see the moonlight.", language, _CLIENT)
    assert any(e.notes.startswith("compound") for e in result.coined)
    assert "moonlight" in translate_to_english(result.text, result.language, _CLIENT).text


# --- evolution and the planner ------------------------------------------------------------------------------


def test_derivational_exponents_follow_sound_change():
    for seed in range(1, 60):
        base = _language(seed)
        if len(base.grammar.derivations) < 2:
            continue
        evolved = evolve_language("Evolved", base, 600, TraitProfile(), seed=seed)
        assert [r.name for r in evolved.grammar.derivations] == [r.name for r in base.grammar.derivations]
        assert all(r.affix.prefix or r.affix.suffix for r in evolved.grammar.derivations)
        return
    raise AssertionError("no language with derivations")


def test_the_planner_is_told_to_keep_derived_words_whole():
    prompt = sentence_planner._build_system_prompt(_language(1))
    assert "teacher" in prompt and "moonlight" in prompt
