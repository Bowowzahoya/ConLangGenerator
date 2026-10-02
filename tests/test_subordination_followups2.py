"""Subordination follow-ups, second round: prepositional (pied-piped/stranded)
relative clauses, stacked relatives, raising and passivized-control infinitives,
a nominalized clause as the subject, reported-speech tense backshift, chained
clause coordination, gapping and right-node raising, and two more complementizer
verb classes."""

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import subordination_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import (
    _decode_noun,
    _decode_verb_full,
    _governing_verb_tense,
    _render_plan,
    _reported_speech_tense,
    translate_to_conlang,
    translate_to_english,
)

_CLIENT = FakeLLMClient()
_CACHE: dict[int, object] = {}


def _language(seed: int):
    if seed not in _CACHE:
        _CACHE[seed] = generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())
    return _CACHE[seed]


def _find(predicate, limit: int = 400):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language.grammar):
            return language
    raise AssertionError("no seed found")


def _with(language, **updates):
    return language.model_copy(update={"grammar": language.grammar.model_copy(update=updates)})


def _base():
    return _find(lambda g: not g.has_articles and not g.uses_classifiers and not g.noun_classes and not g.pro_drop)


def _render(language, *slots):
    updated, romanized, _, glosses = _render_plan(SentencePlan(slots=tuple(slots)), language, _CLIENT, [])
    return updated, romanized, glosses


def _noun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="noun", **kw)


def _pronoun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="pronoun", **kw)


def _verb(gloss: str = "sleep", **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="verb", **kw)


def _clause(gloss: str, role: str, *slots: PlannedSlot, **kw) -> PlannedSlot:
    return PlannedSlot(kind="clause", gloss=gloss, role=role, clause=SentencePlan(slots=tuple(slots)), **kw)


# --- generation -------------------------------------------------------------------------


def test_the_follow_up_choices_are_rolled():
    grammars = [_language(s).grammar for s in range(1, 120)]
    for field in ("reported_speech_backshift", "clause_gapping", "clause_right_node_raising"):
        assert {getattr(g, field) for g in grammars} == {True, False}, field


def test_the_new_grammar_fields_default_for_older_saved_languages():
    fields = type(_language(1).grammar).model_fields
    assert fields["reported_speech_backshift"].default is False
    assert fields["clause_gapping"].default is False and fields["clause_right_node_raising"].default is False


def test_two_more_complementizer_classes_exist():
    assert subordination_gen.COMPLEMENT_CLASSES == (
        "speech", "desire", "perception", "factive", "manipulative", "epistemic",
    )
    assert subordination_gen.complement_class("make") == "manipulative"
    assert subordination_gen.complement_class("let") == "manipulative"
    assert subordination_gen.complement_class("doubt") == "epistemic"
    assert subordination_gen.complement_class("suspect") == "epistemic"


def test_pp_relative_pied_piping_follows_the_relativization_strategy():
    assert subordination_gen.pp_relative_pied_pipes("pronoun")
    assert subordination_gen.pp_relative_pied_pipes("correlative")
    assert not subordination_gen.pp_relative_pied_pipes("gap")
    assert not subordination_gen.pp_relative_pied_pipes("particle")
    assert not subordination_gen.pp_relative_pied_pipes("resumptive")


# --- prepositional relative clauses --------------------------------------------------------------


def _pp_relative(prep: str, verb_gloss: str = "live") -> PlannedSlot:
    return _clause(
        "which", "relative", _pronoun("I"), _verb(verb_gloss),
        PlannedSlot(kind="content", gloss=prep, pos="preposition"),
        rel_function="oblique_pp", oblique_prep=prep,
    )


def test_a_pied_piping_language_fronts_the_preposition_with_the_relative_word():
    language = _with(_base(), relativization="pronoun", relative_clause_position="after_noun")
    _, parts, glosses = _render(language, _noun("house"), _pp_relative("in"))
    assert glosses == ["house", "in", "which", "I", "live"]


def test_a_stranding_language_leaves_the_preposition_in_the_clause():
    language = _with(_base(), relativization="gap", relative_clause_position="after_noun")
    _, parts, glosses = _render(language, _noun("house"), _pp_relative("in"))
    assert glosses == ["house", "I", "live", "in"]  # no relative word at all; the preposition trails its verb


def test_a_pp_relative_reads_back_and_round_trips():
    language = _with(_base(), relativization="pronoun")
    updated, tokens, _ = _render(language, _noun("house"), _pp_relative("in"))
    english = translate_to_english(" ".join(tokens), updated, _CLIENT).text
    assert "house" in english and "live" in english


def test_a_whole_pp_relative_sentence_round_trips():
    language = _find(lambda g: g.relativization in ("pronoun", "correlative"))
    result = translate_to_conlang("I see the house in which I live.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "<unknown" not in english and "house" in english and "live" in english


# --- stacked relative clauses -----------------------------------------------------------------


def _two_subject_relatives(verb1: str = "bark", verb2: str = "bite") -> tuple[PlannedSlot, PlannedSlot]:
    return (
        _clause("which", "relative", _verb(verb1), rel_function="subject"),
        _clause("which", "relative", _verb(verb2), rel_function="subject"),
    )


def test_two_relative_clauses_stack_after_the_noun():
    language = _with(_base(), relative_clause_position="after_noun", relativization="particle")
    r1, r2 = _two_subject_relatives()
    _, _, glosses = _render(language, _noun("dog"), r1, r2)
    assert glosses[0] == "dog" and "bark" in glosses and "bite" in glosses
    assert glosses.index("bark") < glosses.index("bite")


def test_stacked_relatives_move_together_before_the_noun():
    language = _with(_base(), relative_clause_position="before_noun", relativization="particle")
    r1, r2 = _two_subject_relatives()
    _, _, glosses = _render(language, _noun("dog"), r1, r2)
    dog_index = glosses.index("dog")
    assert glosses.index("bark") < dog_index and glosses.index("bite") < dog_index
    assert glosses.index("bark") < glosses.index("bite")  # original order kept


def test_stacked_relatives_front_together_in_a_correlative_language():
    language = _with(_base(), relativization="correlative")
    r1, r2 = _two_subject_relatives()
    _, _, glosses = _render(language, _noun("dog"), r1, r2)
    assert glosses.index("bark") < glosses.index("bite") < glosses.index("dog")


def test_a_stacked_relative_does_not_confuse_an_unrelated_earlier_noun():
    language = _with(_base(), relative_clause_position="after_noun", relativization="particle")
    r1, r2 = _two_subject_relatives()
    _, _, glosses = _render(language, _noun("cat"), _noun("dog"), r1, r2)
    assert glosses[:2] == ["cat", "dog"]
    assert glosses.index("bark") < glosses.index("bite")


def test_both_stacked_clauses_round_trip():
    language = _with(_base(), relative_clause_position="after_noun", relativization="particle")
    r1, r2 = _two_subject_relatives()
    updated, tokens, _ = _render(language, _noun("dog"), r1, r2)
    english = translate_to_english(" ".join(tokens), updated, _CLIENT).text
    assert "dog" in english and "bark" in english and "bite" in english


def test_the_fake_planner_stacks_two_relative_clauses_on_who_or_which():
    language = _find(lambda g: True)
    plan = sentence_planner.plan_sentence("I see the dog which barks which bites.", language, _CLIENT)
    relatives = [s for s in plan.slots if s.kind == "clause" and s.role == "relative"]
    assert len(relatives) == 2
    assert {s.gloss for s in relatives} == {"which"}


# --- raising and passivized control ------------------------------------------------------------


def test_the_fake_planner_treats_a_raising_verb_like_a_control_verb():
    language = _find(lambda g: "infinitive" in g.verb_forms)
    plan = sentence_planner.plan_sentence("He seems to sleep.", language, _CLIENT)
    complement = next(s for s in plan.slots if s.kind == "clause" and s.role == "complement")
    inner = complement.clause.slots[0]
    assert inner.verb_form == "infinitive" and inner.gloss == "sleep"
    matrix_verb = next(s for s in plan.slots if s.kind == "content" and s.pos == "verb")
    assert matrix_verb.gloss == "seem"


def test_the_fake_planner_builds_a_passivized_control_matrix():
    language = _find(lambda g: "infinitive" in g.verb_forms)
    plan = sentence_planner.plan_sentence("He is known to sleep.", language, _CLIENT)
    matrix_verb = next(s for s in plan.slots if s.kind == "content" and s.pos == "verb")
    assert matrix_verb.gloss == "know" and matrix_verb.voice == "passive"
    assert not any(s.kind == "content" and s.pos == "noun" for s in plan.slots)  # no object slot
    complement = next(s for s in plan.slots if s.kind == "clause" and s.role == "complement")
    assert complement.clause.slots[0].verb_form == "infinitive"


def test_a_passivized_control_sentence_round_trips():
    language = _find(lambda g: "infinitive" in g.verb_forms)
    result = translate_to_conlang("He is known to sleep.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "<unknown" not in english and "know" in english and "sleep" in english


# --- a nominalized clause as the subject -----------------------------------------------------------


def test_a_nominal_clause_can_be_placed_as_the_subject():
    language = _base()
    subject_clause = _clause("", "nominal", _verb("see"), _noun("river"))
    _, _, glosses = _render(
        language, subject_clause, _verb("please", agreement="default"), _pronoun("I", case="accusative"),
    )
    assert glosses[0] == "see" and "river" in glosses and "please" in glosses


def test_the_fake_planner_plans_a_gerund_subject_clause():
    language = _find(lambda g: True)
    plan = sentence_planner.plan_sentence("Seeing the river pleases me.", language, _CLIENT)
    assert plan.slots[0].kind == "clause" and plan.slots[0].role == "nominal"
    inner = plan.slots[0].clause.slots
    assert any(s.gloss == "see" for s in inner) and any(s.gloss == "river" for s in inner)
    assert any(s.gloss == "please" for s in plan.slots)


def test_a_gerund_subject_sentence_round_trips():
    language = _find(lambda g: True)
    result = translate_to_conlang("Seeing the river pleases me.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "<unknown" not in english and "river" in english and "please" in english


# --- reported speech tense backshift ----------------------------------------------------------------


def test_backshift_forces_past_after_a_past_speech_verb():
    language = _with(_find(lambda g: "past" in g.tenses), reported_speech_backshift=True)
    slot = PlannedSlot(kind="clause", role="complement")
    assert _reported_speech_tense(language, slot, "past", "say") == "past"
    assert _reported_speech_tense(language, slot, "non_past", "say") is None
    off = _with(language, reported_speech_backshift=False)
    assert _reported_speech_tense(off, slot, "past", "say") is None


def test_backshift_is_gated_to_speech_verbs_specifically():
    # "I knew that she was late" is not reported speech: a factive verb's
    # complement must not backshift even when every other condition holds.
    language = _with(_find(lambda g: "past" in g.tenses), reported_speech_backshift=True)
    slot = PlannedSlot(kind="clause", role="complement")
    assert _reported_speech_tense(language, slot, "past", "know") is None
    assert _reported_speech_tense(language, slot, "past", None) is None


def test_governing_verb_tense_reads_the_planned_tense():
    slots = (_pronoun("he"), _verb("say", tense="past"), _clause("that", "complement", _verb("be")))
    assert _governing_verb_tense(slots, 2) == "past"


def _verb_token(language, romanized, glosses, gloss: str) -> str:
    return romanized[glosses.index(gloss)]


def test_a_backshifting_language_renders_the_complement_in_the_past():
    language = _find(
        lambda g: g.reported_speech_backshift and "past" in g.tenses and "non_past" in g.tenses
        and "past" not in g.periphrastic_labels
    )
    # the embedded verb's own tense is left unset, so the forced backshift is the only thing that can supply one
    updated, romanized, glosses = _render(language, _pronoun("he"), _verb("say", tense="past"), _clause("that", "complement", _verb("be")))
    backshifted_token = _verb_token(updated, romanized, glosses, "be")
    off = _with(language, reported_speech_backshift=False)
    updated2, romanized2, glosses2 = _render(off, _pronoun("he"), _verb("say", tense="past"), _clause("that", "complement", _verb("be")))
    no_backshift_token = _verb_token(updated2, romanized2, glosses2, "be")
    assert backshifted_token != no_backshift_token
    decoded = _decode_verb_full(updated, backshifted_token)
    assert decoded is not None and decoded[1] == "past"


def test_the_planners_own_tense_wins_over_the_forced_backshift():
    language = _find(
        lambda g: g.reported_speech_backshift and "future" in g.tenses
        and "future" not in g.periphrastic_labels and "past" not in g.periphrastic_labels
    )
    updated_forced, romanized_forced, glosses_forced = _render(
        language, _pronoun("he"), _verb("say", tense="past"), _clause("that", "complement", _verb("be")),
    )
    updated_own, romanized_own, glosses_own = _render(
        language, _pronoun("he"), _verb("say", tense="past"), _clause("that", "complement", _verb("be", tense="future")),
    )
    forced_token = _verb_token(updated_forced, romanized_forced, glosses_forced, "be")
    own_token = _verb_token(updated_own, romanized_own, glosses_own, "be")
    assert forced_token != own_token
    decoded = _decode_verb_full(updated_own, own_token)
    assert decoded is not None and decoded[1] == "future"


def test_backshift_only_applies_to_a_speech_verbs_complement():
    language = _with(
        _find(lambda g: "past" in g.tenses and "non_past" in g.tenses), reported_speech_backshift=True,
    )
    with_backshift = _render(
        language, _pronoun("he"), _verb("want", tense="past"), _clause("that", "complement", _verb("be", tense="non_past")),
    )[1]
    without = _render(
        _with(language, reported_speech_backshift=False),
        _pronoun("he"), _verb("want", tense="past"), _clause("that", "complement", _verb("be", tense="non_past")),
    )[1]
    assert with_backshift == without  # "want" is not a speech verb: no backshift either way


# --- chained coordination -----------------------------------------------------------------------------


def test_the_fake_planner_nests_a_third_coordinate_clause():
    language = _find(lambda g: True)
    plan = sentence_planner.plan_sentence("I go, you go, and she works.", language, _CLIENT)
    first = next(s for s in plan.slots if s.kind == "clause" and s.role == "coordinate")
    second = next(s for s in first.clause.slots if s.kind == "clause" and s.role == "coordinate")
    assert any(s.gloss == "she" for s in second.clause.slots)
    assert any(s.gloss == "work" for s in second.clause.slots)


def test_a_chain_of_three_clauses_round_trips():
    language = _find(lambda g: True)
    result = translate_to_conlang("I go, you go, and she works.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "<unknown" not in english and "go" in english and "work" in english


def test_a_converb_coordinating_language_converbs_every_clause_but_the_last():
    language = _find(lambda g: g.clause_coordination == "converb" and "converb" in g.verb_forms)
    plan_slots = (
        _pronoun("i"), _verb("go", agreement="I"),
        _clause(
            "and", "coordinate", _pronoun("you"), _verb("go", agreement="you"),
            _clause("and", "coordinate", _pronoun("he"), _verb("go", agreement="he")),
        ),
    )
    updated, tokens, glosses = _render(language, *plan_slots)
    go_tokens = [tok for tok, gloss in zip(tokens, glosses) if gloss == "go"]
    assert len(go_tokens) == 3
    decoded = [_decode_verb_full(updated, tok) for tok in go_tokens]
    assert all(d is not None for d in decoded)
    # the first two conjuncts (not the last one) take the medial converb form, not tense/agreement
    assert decoded[0][1] == "converb" and decoded[1][1] == "converb"
    assert decoded[2][1] != "converb"


# --- gapping and right-node raising ----------------------------------------------------------------------


def test_gapping_drops_the_second_clauses_verb():
    plan_slots = (
        _pronoun("i"), _verb("eat", agreement="I"), _noun("rice", case="accusative"),
        _clause("and", "coordinate", _pronoun("she"), _noun("bean", case="accusative", number="plural")),
    )
    language = _base()
    _, _, glosses = _render(language, *plan_slots)
    assert glosses.count("eat") == 1
    assert "she" in glosses and "bean" in glosses


def test_the_fake_planner_builds_a_gapped_clause_when_the_language_allows_it():
    language = _with(_find(lambda g: True), clause_gapping=True)
    plan = sentence_planner.plan_sentence("I eat rice, and she, beans.", language, _CLIENT)
    coordinate = next(s for s in plan.slots if s.kind == "clause" and s.role == "coordinate")
    assert not any(s.pos == "verb" for s in coordinate.clause.slots)
    assert {s.gloss for s in coordinate.clause.slots} == {"she", "bean"}


def test_a_language_without_gapping_repeats_the_verb():
    language = _with(_find(lambda g: True), clause_gapping=False)
    plan = sentence_planner.plan_sentence("I eat rice, and she, beans.", language, _CLIENT)
    coordinate = next(s for s in plan.slots if s.kind == "clause" and s.role == "coordinate")
    assert any(s.pos == "verb" for s in coordinate.clause.slots)


def test_a_gapped_sentence_round_trips():
    language = _with(_find(lambda g: True), clause_gapping=True)
    result = translate_to_conlang("I eat rice, and she, beans.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "<unknown" not in english and "rice" in english and "bean" in english


def test_right_node_raising_drops_the_earlier_objects():
    plan_slots = (
        _pronoun("i"), _verb("buy", agreement="I"),
        _clause("and", "coordinate", _pronoun("she"), _verb("sell", agreement="she"), _noun("car", case="accusative")),
    )
    language = _base()
    _, _, glosses = _render(language, *plan_slots)
    assert glosses.count("car") == 1
    assert "buy" in glosses and "sell" in glosses


def test_the_fake_planner_builds_an_rnr_clause_when_the_language_allows_it():
    language = _with(_find(lambda g: True), clause_right_node_raising=True)
    plan = sentence_planner.plan_sentence("I washed, and she cooked, the fish.", language, _CLIENT)
    first_verb_index = next(i for i, s in enumerate(plan.slots) if s.kind == "content" and s.pos == "verb")
    assert not any(s.kind == "content" and s.pos == "noun" for s in plan.slots[: first_verb_index + 1])
    coordinate = next(s for s in plan.slots if s.kind == "clause" and s.role == "coordinate")
    assert any(s.pos == "noun" and s.gloss == "fish" for s in coordinate.clause.slots)


def test_a_language_without_right_node_raising_repeats_the_object():
    language = _with(_find(lambda g: True), clause_right_node_raising=False)
    plan = sentence_planner.plan_sentence("I washed, and she cooked, the fish.", language, _CLIENT)
    assert any(s.kind == "content" and s.pos == "noun" and s.gloss == "fish" for s in plan.slots)


def test_an_rnr_sentence_round_trips():
    language = _with(_find(lambda g: True), clause_right_node_raising=True)
    result = translate_to_conlang("I washed, and she cooked, the fish.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "<unknown" not in english and "fish" in english and "wash" in english and "cook" in english
