"""Noun-phrase features: dual number, demonstratives, numerals, the indefinite
article, possession, and adposition order."""

from conlang_generator.core.grammar import GrammarProfile
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient, _fake_plan_dict
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import (
    _decode_adjective,
    _decode_noun,
    _render_plan,
    translate_to_conlang,
    translate_to_english,
)

_CLIENT = FakeLLMClient()
_CACHE: dict[int, object] = {}


def _language(seed: int):
    if seed not in _CACHE:
        _CACHE[seed] = generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())
    return _CACHE[seed]


def _find(predicate, limit: int = 200):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language.grammar):
            return language
    raise AssertionError("no seed found")


def _render(language, *slots: PlannedSlot) -> list[str]:
    _, romanized, _, _ = _render_plan(SentencePlan(slots=tuple(slots)), language, _CLIENT, [])
    return romanized


def _noun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="noun", **kw)


def _pronoun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="pronoun", **kw)


# --- generation -----------------------------------------------------------


def test_possession_strategy_matches_the_generated_marking():
    seen = set()
    for seed in range(1, 60):
        grammar = _language(seed).grammar
        seen.add(grammar.possession)
        assert bool(grammar.possessive_particle) == (grammar.possession == "particle")
        assert bool(grammar.possession_affixes) == (grammar.possession == "affix")
        if "genitive" in grammar.cases:
            assert grammar.possession == "genitive"
    assert seen == {"genitive", "particle", "affix", "none"}


def test_the_possessive_particle_is_distinct_from_the_question_particle_and_the_lexicon():
    language = _find(lambda g: g.possession == "particle")
    romanization = language.romanization
    particle = romanization.apply(language.grammar.possessive_particle).lower()
    assert particle != romanization.apply(language.grammar.question_particle).lower()
    assert language.lexicon.by_form(particle) is None


def test_dual_and_the_other_noun_phrase_options_are_rolled():
    duals = [any(a.label == "dual" for a in _language(seed).grammar.number_affixes) for seed in range(1, 60)]
    assert any(duals) and not all(duals)
    grammars = [_language(seed).grammar for seed in range(1, 60)]
    assert {g.plural_after_numeral for g in grammars} == {True, False}
    assert {g.demonstrative_after_noun for g in grammars} == {True, False}
    assert {g.has_indefinite_article for g in grammars} == {True, False}


def test_grammar_defaults_keep_old_saved_languages_valid():
    fields = GrammarProfile.model_fields
    assert fields["plural_after_numeral"].default is True
    assert fields["demonstrative_after_noun"].default is False
    assert fields["has_indefinite_article"].default is False
    assert fields["possession"].default == "none"
    assert fields["possession_affixes"].default == ()


def test_adpositions_follow_the_noun_in_object_before_verb_languages():
    for seed in range(1, 40):
        grammar = _language(seed).grammar
        assert grammar.postpositional == (grammar.word_order.value in ("SOV", "OSV", "OVS"))


# --- planning -------------------------------------------------------------


def test_parse_reads_possessive_dual_and_the_new_slot_kinds():
    plan = sentence_planner._parse(
        '[{"kind": "content", "gloss": "I", "pos": "pronoun", "possessive": true},'
        ' {"kind": "content", "gloss": "dog", "pos": "noun", "number": "dual"},'
        ' {"kind": "demonstrative", "gloss": "this"}, {"kind": "indefinite_article"},'
        ' {"kind": "content", "gloss": "cat", "pos": "noun", "number": "septal"}]'
    )
    assert plan is not None
    assert plan.slots[0].possessive is True
    assert plan.slots[1].number == "dual"
    assert [s.kind for s in plan.slots[2:4]] == ["demonstrative", "indefinite_article"]
    assert plan.slots[4].number is None


def test_the_prompt_describes_this_languages_noun_phrase():
    language = _find(lambda g: g.postpositional and g.demonstrative_after_noun and g.possession == "genitive")
    prompt = sentence_planner._build_system_prompt(language)
    assert "POSTPOSITIONS" in prompt
    assert "come AFTER their noun" in prompt
    assert "takes the genitive case" in prompt
    other = _find(lambda g: not g.postpositional and not g.demonstrative_after_noun and g.possession == "genitive")
    other_prompt = sentence_planner._build_system_prompt(other)
    assert "PREPOSITIONS" in other_prompt and "come BEFORE their noun" in other_prompt


_META = {
    "word_order": "SVO", "alignment": "nominative_accusative", "tenses": "past,non_past",
    "has_articles": "true", "has_indefinite_article": "true", "number_labels": "plural,dual",
}


def _slots(sentence: str, **overrides) -> list[dict]:
    return _fake_plan_dict(sentence, {**_META, **overrides})["slots"]


def test_the_fake_planner_marks_possessors_demonstratives_numerals_and_indefinites():
    slots = _slots("I see my dog.")
    assert {"kind": "content", "gloss": "I", "pos": "pronoun", "possessive": True} in slots
    assert _slots("This dog sees the river.")[0] == {"kind": "demonstrative", "gloss": "this"}
    two = _slots("I see two rivers.")
    assert {"kind": "content", "gloss": "two", "pos": "numeral"} in two
    assert next(s for s in two if s.get("gloss") == "river")["number"] == "dual"
    three = _slots("I see three rivers.", number_labels="plural")
    assert next(s for s in three if s.get("gloss") == "river")["number"] == "plural"
    assert {"kind": "indefinite_article"} in _slots("I see a river.")
    assert {"kind": "article"} in _slots("I see a river.", has_indefinite_article="false")
    possessor = next(s for s in _slots("The dog's bone is high.") if s.get("possessive"))
    assert possessor["gloss"] == "dog"


def test_the_fake_planner_puts_a_demonstrative_after_its_noun_when_the_language_does():
    slots = _slots("I see this river.", demonstrative_after_noun="true")
    kinds = [s["kind"] for s in slots]
    assert kinds.index("demonstrative") > [s.get("gloss") for s in slots].index("river")


def test_a_bare_this_stays_a_pronoun():
    assert all(s["kind"] != "demonstrative" for s in _slots("I see this."))


# --- rendering ------------------------------------------------------------


def test_dual_plural_and_singular_are_three_different_forms():
    language = _find(lambda g: any(a.label == "dual" for a in g.number_affixes))
    singular, plural, dual = (
        _render(language, _noun("river", number=n))[0] for n in (None, "plural", "dual")
    )
    assert len({singular, plural, dual}) == 3
    assert _decode_noun(language, dual)[1].endswith("dual")
    assert _decode_noun(language, plural)[1].endswith("plural")


def test_a_dual_falls_back_to_bare_in_a_language_without_one():
    language = _find(lambda g: not any(a.label == "dual" for a in g.number_affixes))
    assert _render(language, _noun("river", number="dual")) == _render(language, _noun("river"))


def test_the_plural_after_a_numeral_follows_the_language():
    numeral = PlannedSlot(kind="content", gloss="two", pos="numeral")
    keeps = _find(lambda g: g.plural_after_numeral)
    drops = _find(lambda g: not g.plural_after_numeral)
    assert _render(keeps, numeral, _noun("river", number="plural"))[1] != _render(keeps, numeral, _noun("river"))[1]
    assert _render(drops, numeral, _noun("river", number="plural"))[1] == _render(drops, numeral, _noun("river"))[1]
    # "one" is not a numeral above one: the noun keeps whatever number it was given
    one = PlannedSlot(kind="content", gloss="one", pos="numeral")
    assert _render(drops, one, _noun("river", number="plural"))[1] != _render(drops, one, _noun("river"))[1]


def test_genitive_possession_marks_the_possessor():
    language = _find(lambda g: g.possession == "genitive")
    possessed = _render(language, _pronoun("I", possessive=True), _noun("dog"))
    plain = _render(language, _pronoun("I"), _noun("dog"))
    assert len(possessed) == 2 and possessed[1] == plain[1]
    assert possessed[0] != plain[0]


def test_particle_possession_adds_the_particle_after_the_possessor():
    language = _find(lambda g: g.possession == "particle")
    particle = language.romanization.apply(language.grammar.possessive_particle)
    possessed = _render(language, _pronoun("I", possessive=True), _noun("dog"))
    assert len(possessed) == 3 and possessed[1] == particle
    assert _render(language, _pronoun("I"), _noun("dog")) == [possessed[0], possessed[2]]
    english = translate_to_english(" ".join(possessed), language, _CLIENT).text
    assert "of" in english.split()


def test_affix_possession_marks_the_possessed_noun_and_decodes_back():
    language = _find(lambda g: g.possession == "affix")
    possessed = _render(language, _pronoun("I", possessive=True), _noun("dog"))
    plain = _render(language, _pronoun("I"), _noun("dog"))
    assert len(possessed) == 2 and possessed[0] == plain[0] and possessed[1] != plain[1]
    dog = language.lexicon.by_gloss("dog")
    decoded = _decode_noun(language, possessed[1])
    assert decoded is not None and decoded[0] == dog and "possessed" in decoded[1]


def test_juxtaposition_leaves_a_possession_unmarked():
    language = _find(lambda g: g.possession == "none")
    assert _render(language, _pronoun("I", possessive=True), _noun("dog")) == _render(
        language, _pronoun("I"), _noun("dog")
    )


def test_the_possessed_affix_only_marks_the_next_noun():
    language = _find(lambda g: g.possession == "affix")
    tokens = _render(language, _pronoun("I", possessive=True), _noun("dog"), _noun("river"))
    assert tokens[2] == _render(language, _noun("river"))[0]


def test_an_indefinite_article_is_rendered_only_where_the_language_has_one():
    with_indefinite = _find(lambda g: g.has_indefinite_article)
    without = _find(lambda g: not g.has_indefinite_article)
    article = PlannedSlot(kind="indefinite_article")
    assert len(_render(with_indefinite, article, _noun("river"))) == 2
    assert len(_render(without, article, _noun("river"))) == 1
    updated, romanized, _, _ = _render_plan(
        SentencePlan(slots=(article, _noun("river"))), with_indefinite, _CLIENT, []
    )  # rendering coins the word "a", so decode against the updated language
    english = translate_to_english(" ".join(romanized), updated, _CLIENT).text
    assert "<unknown" not in english and "river" in english


def test_a_demonstrative_agrees_with_its_noun_class_and_decodes_back():
    language = _find(lambda g: g.noun_classes == ("animate", "inanimate") and not g.demonstrative_after_noun)
    demonstrative = PlannedSlot(kind="demonstrative", gloss="this")
    of_dog = _render(language, demonstrative, _noun("dog"))[0]
    of_river = _render(language, demonstrative, _noun("river"))[0]
    assert of_dog != of_river
    this = language.lexicon.by_gloss("this")
    assert _decode_adjective(language, of_dog) == (this, "animate")


def test_a_demonstrative_after_the_noun_agrees_with_the_noun_before_it():
    language = _find(lambda g: g.noun_classes == ("animate", "inanimate") and g.demonstrative_after_noun)
    demonstrative = PlannedSlot(kind="demonstrative", gloss="this")
    after_dog = _render(language, _noun("dog"), demonstrative)[1]
    after_river = _render(language, _noun("river"), demonstrative)[1]
    assert after_dog != after_river


def test_a_whole_sentence_with_a_possessed_numbered_noun_round_trips_its_content():
    language = _find(lambda g: g.possession == "affix")
    result = translate_to_conlang("I see my two rivers.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "river" in english and "<unknown" not in english
