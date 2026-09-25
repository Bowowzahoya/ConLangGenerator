"""Comparison follow-ups: equatives, excessives, elatives, degrees on adverbs,
"more" of a noun, any oblique case for the standard, "the more..., the more...",
and a longer fake-planner adjective list."""

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import comparison_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import (
    _decode_adjective_full,
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


def _find(predicate, limit: int = 300):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language.grammar):
            return language
    raise AssertionError("no seed found")


def _with(language, **updates):
    return language.model_copy(update={"grammar": language.grammar.model_copy(update=updates)})


def _render(language, *slots):
    updated, romanized, _, glosses = _render_plan(SentencePlan(slots=tuple(slots)), language, _CLIENT, [])
    return updated, romanized, glosses


def _adjective(degree=None, gloss="big") -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="adjective", degree=degree)


def _plan(sentence: str, language):
    return sentence_planner.plan_sentence(sentence, language, _CLIENT)


def _simple(marking_field: str, marking: str):
    """A language with no agreement, so a degree-marked adjective is only its degree suffix."""
    language = _find(lambda g: getattr(g, marking_field) == marking and not g.noun_classes and not g.uses_classifiers)
    return _with(
        language, number_agreement_targets=(), case_agreement_targets=(), adjective_placement="global",
        adjective_stack_order=(), adjective_stack_linker=False, suppletive_degrees=(),
    )


# --- generation -----------------------------------------------------------------


def test_the_follow_up_choices_are_rolled():
    grammars = [_language(s).grammar for s in range(1, 120)]
    for field in ("equative_marking", "excessive_marking", "elative_marking"):
        assert {getattr(g, field) for g in grammars} == {"affix", "word"}
    assert any(g.adverb_degree for g in grammars) and not all(g.adverb_degree for g in grammars)
    assert {g.comparative_case for g in grammars if g.comparative_strategy == "case"} >= {"ablative", "locative"}
    for g in grammars:
        labels = {a.label for a in g.degree_affixes}
        for label, field in (
            ("comparative", "comparative_marking"), ("superlative", "superlative_marking"),
            ("equative", "equative_marking"), ("excessive", "excessive_marking"), ("elative", "elative_marking"),
        ):
            assert (label in labels) == (getattr(g, field) == "affix")
        if g.comparative_strategy == "case":
            assert g.comparative_case in g.cases
        else:
            assert g.comparative_case == ""


def test_the_new_grammar_fields_default_for_older_saved_languages():
    fields = type(_language(1).grammar).model_fields
    assert fields["equative_marking"].default == "word" and fields["adverb_degree"].default is False


def test_degree_suffixes_are_spelled_differently():
    for seed in range(1, 80):
        language = _language(seed)
        spelled = [language.romanization.apply("".join(a.suffix)).lower() for a in language.grammar.degree_affixes if a.suffix]
        assert len(spelled) == len(set(spelled)), seed


def test_the_degree_words_and_readings_cover_every_label():
    assert set(comparison_gen.DEGREE_WORDS) == set(comparison_gen.DEGREE_LABELS) == set(comparison_gen.DEGREE_READING)
    assert comparison_gen.DEGREE_READING["equative"].format("big") == "as big as"


# --- degrees as suffixes -----------------------------------------------------------------


def test_each_degree_suffix_marks_the_adjective_and_decodes_back():
    for label, field in (("equative", "equative_marking"), ("excessive", "excessive_marking"), ("elative", "elative_marking")):
        worked = False
        for seed in range(1, 200):
            language = _language(seed)
            if getattr(language.grammar, field) != "affix" or language.grammar.noun_classes or language.grammar.uses_classifiers:
                continue
            language = _with(
                language, number_agreement_targets=(), case_agreement_targets=(), adjective_placement="global",
                adjective_stack_order=(), adjective_stack_linker=False, suppletive_degrees=(),
            )
            bare = language.lexicon.by_gloss("big").romanization
            updated, parts, _ = _render(language, _adjective(label))
            assert parts[0] != bare
            decoded = _decode_adjective_full(updated, parts[0])
            if decoded is None or decoded[2] != label:
                continue  # a short suffix spelled like another reading: try another language
            english = translate_to_english(parts[0], updated, _CLIENT).text
            if comparison_gen.DEGREE_READING[label].format("big") in english:
                worked = True
                break
        assert worked, label


def test_a_language_with_a_word_for_a_degree_uses_no_suffix():
    language = _simple("excessive_marking", "word")
    bare = language.lexicon.by_gloss("big").romanization
    assert _render(language, _adjective("excessive"))[1][0] == bare


# --- planner and fake planner -----------------------------------------------------------------


def test_the_planner_marks_an_equative_per_the_languages_marking():
    word = _find(lambda g: g.equative_marking == "word" and g.comparative_strategy != "case")
    plan = _plan("The dog is as big as the cat.", word)
    glosses = [s.gloss for s in plan.slots if s.kind == "content"]
    assert glosses.count("as") == 2 and "big" in glosses
    affix = _find(lambda g: g.equative_marking == "affix" and g.comparative_strategy != "case")
    plan = _plan("The dog is as big as the cat.", affix)
    assert any(s.gloss == "big" and s.degree == "equative" for s in plan.slots)
    assert [s.gloss for s in plan.slots if s.kind == "content"].count("as") == 1


def test_an_equative_standard_can_take_the_comparative_case():
    language = _find(lambda g: g.comparative_strategy == "case" and g.equative_marking == "affix")
    plan = _plan("The dog is as big as the cat.", language)
    cat = next(s for s in plan.slots if s.gloss == "cat")
    assert cat.case == language.grammar.comparative_case
    assert not any(s.gloss == "as" for s in plan.slots)


def test_an_equative_in_an_exceed_language_uses_as_instead_of_a_verb():
    language = _find(lambda g: g.comparative_strategy == "exceed" and g.equative_marking == "affix")
    plan = _plan("The dog is as big as the cat.", language)
    assert any(s.gloss == "as" and s.pos == "preposition" for s in plan.slots)
    assert not any(s.gloss == "exceed" for s in plan.slots)


def test_the_planner_marks_excessive_and_elative():
    excessive = _find(lambda g: g.excessive_marking == "affix")
    assert any(s.degree == "excessive" for s in _plan("The dog is too big.", excessive).slots)
    word = _find(lambda g: g.excessive_marking == "word")
    assert any(s.gloss == "too" for s in _plan("The dog is too big.", word).slots)
    elative = _find(lambda g: g.elative_marking == "affix")
    assert any(s.degree == "elative" for s in _plan("The dog is very big.", elative).slots)


def test_the_fake_planner_knows_more_adjectives():
    language = _find(lambda g: g.comparative_marking == "affix" and g.comparative_strategy == "particle")
    plan = _plan("The dog is sweeter than the cat.", language)
    assert any(s.gloss == "sweet" and s.degree == "comparative" for s in plan.slots)


def test_the_more_the_more_is_two_parallel_parts():
    language = _find(lambda g: g.correlative_adverbials)
    plan = sentence_planner.plan_sentence("The more you read, the more you learn.", language, _CLIENT)
    clause = next(s for s in plan.slots if s.kind == "clause")
    assert clause.gloss == "the-more" and clause.role == "adverbial"
    inner = [s.gloss for s in clause.clause.slots if s.kind == "content"]
    outer = [s.gloss for s in plan.slots if s.kind == "content"]
    assert "more" in inner and "more" in outer
    result = translate_to_conlang("The more you read, the more you learn.", language, _CLIENT)
    assert len(result.text.split()) >= 6


# --- standard case ----------------------------------------------------------------------------


def test_the_standard_can_take_an_ablative_or_locative():
    language = _find(lambda g: g.comparative_strategy == "case" and g.comparative_case in ("ablative", "locative"))
    case = language.grammar.comparative_case
    plan = _plan("The dog is bigger than the cat.", language)
    assert next(s for s in plan.slots if s.gloss == "cat").case == case
    updated, parts, _ = _render(
        language, PlannedSlot(kind="content", gloss="cat", pos="noun", case=case)
    )
    assert parts[0] != language.lexicon.by_gloss("cat").romanization


# --- adverbs and nouns ---------------------------------------------------------------------------


def test_an_adverb_can_take_a_degree_suffix():
    language = _simple("comparative_marking", "affix")
    language = _with(language, adverb_degree=True)
    adverb = PlannedSlot(kind="content", gloss="quickly", pos="adverb", degree="comparative")
    updated, parts, _ = _render(language, adverb)
    plain = _render(language, PlannedSlot(kind="content", gloss="quickly", pos="adverb"))[1][0]
    assert parts[0] != plain
    assert "more quickly" in translate_to_english(parts[0], updated, _CLIENT).text
    off = _with(language, adverb_degree=False)
    assert _render(off, adverb)[1][0] == _render(off, PlannedSlot(kind="content", gloss="quickly", pos="adverb"))[1][0]


def test_more_of_a_noun_is_the_word_more():
    language = _simple("comparative_marking", "word")
    more = PlannedSlot(kind="content", gloss="more", pos="quantifier")
    updated, parts, glosses = _render(language, more, PlannedSlot(kind="content", gloss="water", pos="noun"))
    assert glosses[0] == "more" and len(parts) == 2


def test_the_planner_prompt_describes_the_new_degrees():
    prompt = sentence_planner._build_system_prompt(_language(1))
    assert "Equatives" in prompt and '"too big"' in prompt.lower() or "Too big" in prompt
    assert "more water" in prompt and "more quickly" in prompt
