"""Subordination follow-ups: relativization reach, declining relative pronouns,
infinitive agreement, case-marked nominalizations, conditional sequencing,
correlative adverbials, clause coordination and complementizer choice."""

from conlang_generator.core.grammar import GrammarProfile
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import subordination_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient, _fake_plan_dict
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import (
    _decode_verb_full,
    _render_plan,
    translate_to_conlang,
    translate_to_english,
)

_CLIENT = FakeLLMClient()
_CACHE: dict[int, object] = {}
_CASES = ("nominative", "accusative", "genitive", "dative")


class _SpyClient(FakeLLMClient):
    def __init__(self) -> None:
        self.requests: list = []

    def complete(self, request):
        self.requests.append(request)
        return super().complete(request)


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


# --- generation and the small pure functions ---------------------------------


def test_every_follow_up_choice_is_rolled():
    grammars = [_language(s).grammar for s in range(1, 100)]
    assert {g.relativization_reach for g in grammars} == set(subordination_gen.RELATIVE_FUNCTIONS)
    assert {g.clause_coordination for g in grammars} == {"word", "converb", "juxtapose"}
    assert {g.conditional_clause_tense for g in grammars} == {"", "past"}
    for field in (
        "relative_pronoun_declines", "relative_pronoun_number", "infinitive_agrees", "nominalized_takes_case",
        "conditional_main_mood", "correlative_adverbials", "conjunct_reduction", "complementizer_by_verb",
    ):
        assert {getattr(g, field) for g in grammars} == {True, False}, field
    assert any("converb" in g.verb_forms for g in grammars)
    for g in grammars:
        assert [a.label for a in g.verb_form_affixes] == list(g.verb_forms)
        if g.clause_coordination == "converb":
            assert "converb" in g.verb_forms


def test_grammar_defaults_keep_old_saved_languages_valid():
    fields = GrammarProfile.model_fields
    assert fields["relativization_reach"].default == "possessor"
    assert fields["clause_coordination"].default == "word"
    assert not any(
        fields[f].default
        for f in (
            "relative_pronoun_declines", "infinitive_agrees", "nominalized_takes_case", "conditional_main_mood",
            "correlative_adverbials", "conjunct_reduction", "complementizer_by_verb",
        )
    )


def test_reach_is_a_position_on_the_accessibility_hierarchy():
    assert not subordination_gen.beyond_reach("possessor", "possessor")
    assert not subordination_gen.beyond_reach("object", "subject")
    assert subordination_gen.beyond_reach("object", "oblique")
    assert subordination_gen.beyond_reach("subject", "object")


def test_relative_pronoun_glosses_and_readings():
    gloss = subordination_gen.relative_pronoun_gloss
    assert gloss("who", "subject", False, True, True, _CASES) == "who"
    assert gloss("who", "object", False, True, True, _CASES) == "who-accusative"
    assert gloss("who", "possessor", True, True, True, _CASES) == "who-genitive-plural"
    assert gloss("who", "object", False, False, False, _CASES) == "who"
    assert gloss("who", "oblique", False, True, False, ("nominative", "accusative")) == "who"  # no dative here
    reading = subordination_gen.relative_reading
    assert [reading(g) for g in ("who", "who-accusative", "who-genitive-plural", "which-accusative", "which-genitive")] == [
        "who", "whom", "whose", "which", "whose",
    ]
    assert reading("dog") is None and reading("who-nonsense-extra") is None


def test_governing_verbs_select_a_complementizer_class():
    classes = [subordination_gen.complement_class(v) for v in ("say", "want", "see", "know", "sleep")]
    assert classes == ["speech", "desire", "perception", "factive", None]
    assert subordination_gen.complementizer_split("that-desire") == ("that", "desire")
    assert subordination_gen.complementizer_split("that") is None and subordination_gen.complementizer_split("dog-cat") is None


# --- planning -------------------------------------------------------------


def test_parse_reads_the_relative_function_and_the_new_roles():
    plan = sentence_planner._parse(
        '[{"kind": "clause", "gloss": "who", "role": "relative", "rel_function": "possessor",'
        ' "clause": {"slots": [{"kind": "content", "gloss": "dog", "pos": "noun"}]}},'
        ' {"kind": "clause", "gloss": "", "role": "nominal", "case": "accusative",'
        ' "clause": {"slots": [{"kind": "content", "gloss": "see", "pos": "verb", "verb_form": "nominalized"}]}},'
        ' {"kind": "clause", "gloss": "and", "role": "coordinate", "rel_function": "weird",'
        ' "clause": {"slots": [{"kind": "content", "gloss": "run", "pos": "verb"}]}}]'
    )
    assert plan is not None
    relative, nominal, coordinate = plan.slots
    assert relative.rel_function == "possessor" and relative.role == "relative"
    assert nominal.role == "nominal" and nominal.case == "accusative"
    assert coordinate.role == "coordinate" and coordinate.rel_function is None


def test_the_prompt_describes_each_follow_up():
    gap = _find(lambda g: g.relativization in ("gap", "particle") and g.relativization_reach in ("subject", "object"))
    text = sentence_planner._build_system_prompt(gap)
    assert f"reaches up to the {gap.grammar.relativization_reach} position" in text and "resumptive pronoun slot" in text
    declining = _find(lambda g: g.relativization == "pronoun" and g.relative_pronoun_declines and g.relative_pronoun_number)
    text = sentence_planner._build_system_prompt(declining)
    assert "takes the case of its function" in text and "has a plural" in text
    agreeing = _find(lambda g: g.infinitive_agrees and "infinitive" in g.verb_forms)
    assert "an infinitive agrees with its controller" in sentence_planner._build_system_prompt(agreeing)
    nominal = _find(lambda g: "nominalized" in g.verb_forms and g.nominalized_takes_case)
    assert '"role":"nominal"' in sentence_planner._build_system_prompt(nominal)
    conditional = _find(lambda g: g.conditional_main_mood and g.conditional_clause_tense == "past")
    assert "conditional and" in sentence_planner._build_system_prompt(conditional)
    correlative = _find(lambda g: g.correlative_adverbials)
    assert '"the-more"' in sentence_planner._build_system_prompt(correlative)
    for strategy, expected in (("word", "a conjunction word joins"), ("converb", "medial form"), ("juxtapose", "simply follow")):
        language = _find(lambda g: g.clause_coordination == strategy)
        assert expected in sentence_planner._build_system_prompt(language), strategy
    assert "depends on the class of the governing verb" in sentence_planner._build_system_prompt(
        _find(lambda g: g.complementizer_by_verb)
    )


_META = {"word_order": "SVO", "alignment": "nominative_accusative", "tenses": "past,non_past"}


def _plan(sentence: str, **meta):
    return _fake_plan_dict(sentence, {**_META, **meta})["slots"]


def test_the_fake_planner_marks_the_relative_function():
    assert _plan("I see the dog who sleeps.")[-1]["rel_function"] == "subject"
    obj = _plan("I see the dog which I hear.")[-1]
    assert obj["rel_function"] == "object" and [s["gloss"] for s in obj["clause"]["slots"]] == ["i", "hear"]
    possessor = _plan("I see the man whose dog sleeps.")[-1]
    assert possessor["rel_function"] == "possessor" and possessor["clause"]["slots"][0]["gloss"] == "dog"


def test_the_fake_planner_keeps_a_resumptive_pronoun_where_needed():
    resumptive = _plan("I see the dog which I hear.", relativization="resumptive")[-1]
    assert resumptive["clause"]["slots"][-1] == {"kind": "content", "gloss": "he", "pos": "pronoun", "case": "accusative"}
    beyond = _plan("I see the man whose dog sleeps.", relativization="gap", relativization_reach="object")[-1]
    assert beyond["clause"]["slots"][0].get("possessive") is True
    within = _plan("I see the dog which I hear.", relativization="gap", relativization_reach="object")[-1]
    assert within["clause"]["slots"][-1]["gloss"] == "hear"


def test_the_fake_planner_plans_an_object_controlled_infinitive_and_a_clause_coordination():
    control = _plan("I told him to go.", verb_forms="infinitive", infinitive_agrees="true")
    assert control[2]["gloss"] == "he" and control[-1]["clause"]["slots"][0]["agreement"] == "he"
    subject = _plan("I want to go.", verb_forms="infinitive", infinitive_agrees="true")[-1]
    assert subject["clause"]["slots"][0]["agreement"] == "I"
    assert "agreement" not in _plan("I want to go.", verb_forms="infinitive")[-1]["clause"]["slots"][0]
    coordinate = _plan("I see the dog and I hear the cat.")[-1]
    assert coordinate["role"] == "coordinate" and coordinate["gloss"] == "and"
    assert all(s.get("role") != "coordinate" for s in _plan("I see the mountain and the river."))


# --- relative clauses, rendered ----------------------------------------------


def _relative(function: str, gloss: str = "who", head_number=None):
    return (_noun("dog", number=head_number), _clause(gloss, "relative", _verb(), rel_function=function))


def test_a_declining_relative_pronoun_takes_the_case_of_its_function():
    language = _with(
        _base(), relativization="pronoun", relative_clause_position="after_noun", cases=_CASES,
        relative_pronoun_declines=True, relative_pronoun_number=False,
    )
    assert _render(language, *_relative("subject"))[2] == ["dog", "who", "sleep"]
    updated, tokens, glosses = _render(language, *_relative("object"))
    assert glosses == ["dog", "who-accusative", "sleep"]
    assert _render(language, *_relative("possessor"))[2][1] == "who-genitive"
    assert _render(language, *_relative("oblique"))[2][1] == "who-dative"
    assert "whom" in translate_to_english(" ".join(tokens), updated, _CLIENT).text.split()


def test_a_relative_pronoun_that_does_not_decline_stays_who():
    language = _with(
        _base(), relativization="pronoun", relative_clause_position="after_noun", cases=_CASES,
        relative_pronoun_declines=False, relative_pronoun_number=False,
    )
    assert _render(language, *_relative("object"))[2][1] == "who"


def test_a_relative_pronoun_agrees_in_number_with_its_head():
    language = _with(
        _base(), relativization="pronoun", relative_clause_position="after_noun", cases=_CASES,
        relative_pronoun_number=True,
    )
    assert _render(language, *_relative("subject", head_number="plural"))[2][1] == "who-plural"
    assert _render(language, *_relative("subject"))[2][1] == "who"


def test_a_position_beyond_the_reach_of_a_gap_takes_the_invariant_word():
    language = _with(_base(), relativization="gap", relativization_reach="object", relative_clause_position="after_noun")
    assert _render(language, *_relative("subject"))[2] == ["dog", "sleep"]
    assert _render(language, *_relative("object"))[2] == ["dog", "sleep"]
    assert _render(language, *_relative("possessor"))[2] == ["dog", "rel", "sleep"]
    assert _render(language, *_relative("oblique"))[2] == ["dog", "rel", "sleep"]


def test_a_relative_clause_without_a_function_is_a_subject_relative():
    language = _with(_base(), relativization="gap", relativization_reach="subject", relative_clause_position="after_noun")
    assert _render(language, _noun("dog"), _clause("", "relative", _verb()))[2] == ["dog", "sleep"]


# --- non-finite verbs ---------------------------------------------------------


def test_an_infinitive_agrees_with_its_controller_where_the_language_does_that():
    language = _find(lambda g: "infinitive" in g.verb_forms and g.infinitive_agrees)
    first = _render(language, _verb("go", verb_form="infinitive", agreement="I"))[1][0]
    third = _render(language, _verb("go", verb_form="infinitive", agreement="he"))[1][0]
    bare = _render(language, _verb("go", verb_form="infinitive"))[1][0]
    assert len({first, third, bare}) >= 2
    decoded = _decode_verb_full(language, first)
    assert decoded is not None and decoded[1] == "infinitive" and decoded[5] in ("I", None)
    controlled = _decode_verb_full(language, third)
    assert controlled is not None and controlled[1] == "infinitive"
    english = translate_to_english(third, language, _CLIENT).text
    assert "to go" in english


def test_an_infinitive_without_agreement_ignores_the_controller():
    language = _find(lambda g: "infinitive" in g.verb_forms and not g.infinitive_agrees)
    assert (
        _render(language, _verb("go", verb_form="infinitive", agreement="I"))[1]
        == _render(language, _verb("go", verb_form="infinitive", agreement="he"))[1]
    )


def test_a_nominalized_clause_takes_the_case_of_its_function():
    language = _find(lambda g: "nominalized" in g.verb_forms and g.nominalized_takes_case and "accusative" in g.cases)
    verb = _verb("see", verb_form="nominalized")
    plain = _render(language, _clause("", "nominal", verb))[1]
    accusative = _render(language, _clause("", "nominal", verb, case="accusative"))[1]
    assert plain != accusative
    decoded = _decode_verb_full(language, accusative[-1])
    assert decoded is not None and decoded[1] == "nominalized" and decoded[9] == "accusative"
    assert "case: accusative" in _annotation(language, accusative[-1])


def test_a_nominalization_in_a_language_without_case_marking_stays_bare():
    language = _find(lambda g: "nominalized" in g.verb_forms and not g.nominalized_takes_case)
    verb = _verb("see", verb_form="nominalized")
    assert _render(language, _clause("", "nominal", verb, case="accusative"))[1] == _render(language, _clause("", "nominal", verb))[1]


def _annotation(language, token: str) -> str:
    spy = _SpyClient()
    translate_to_english(token, language, spy)
    return next(r.prompt for r in spy.requests if r.purpose == "translate.fluency")


# --- conditionals and correlatives ---------------------------------------------


def _token_of(language, gloss: str, *slots) -> str:
    _, tokens, glosses = _render(language, *slots)
    return tokens[glosses.index(gloss)]


def test_the_main_clause_of_an_if_sentence_takes_the_conditional():
    language = _find(lambda g: g.conditional_main_mood and ("conditional" in g.moods or "irrealis" in g.moods))
    mood = next(m for m in ("conditional", "irrealis", "subjunctive") if m in language.grammar.moods)
    with_if = _token_of(language, "see", _verb("see"), _clause("if", "adverbial", _verb("sleep")))
    without = _token_of(language, "see", _verb("see"), _clause("because", "adverbial", _verb("sleep")))
    explicit = _token_of(language, "see", _verb("see", verb_mood=mood))
    assert with_if != without
    assert with_if == explicit  # exactly what setting the mood by hand gives


def test_a_language_without_conditional_sequencing_leaves_the_main_verb():
    language = _find(lambda g: not g.conditional_main_mood)
    a = _token_of(language, "see", _verb("see"), _clause("if", "adverbial", _verb("sleep")))
    b = _token_of(language, "see", _verb("see"), _clause("because", "adverbial", _verb("sleep")))
    assert a == b


def test_an_if_clause_takes_the_sequenced_tense_unless_the_planner_set_one():
    language = _find(lambda g: g.conditional_clause_tense == "past" and "past" in g.tenses and not g.subordinate_mood_use)
    forced = _render(language, _noun("dog"), _clause("if", "adverbial", _verb("see")))[1][1]
    because = _render(language, _noun("dog"), _clause("because", "adverbial", _verb("see")))[1][1]
    explicit_past = _render(language, _verb("see", tense="past"))[1][0]
    assert forced != because
    assert forced == explicit_past
    other = next(t for t in language.grammar.tenses if t != "past")
    own = _render(language, _noun("dog"), _clause("if", "adverbial", _verb("see", tense=other)))[1][1]
    assert own == _render(language, _verb("see", tense=other))[1][0]  # the planner's own tense wins


def test_correlative_adverbials_front_the_clause_and_add_then():
    language = _with(_base(), correlative_adverbials=True)
    _, _, glosses = _render(language, _noun("dog"), _verb("see"), _clause("if", "adverbial", _verb("sleep")))
    assert glosses.index("sleep") < glosses.index("then") < glosses.index("dog")
    assert glosses[glosses.index("then"):] == ["then", "dog", "see"]


def test_the_more_the_more_repeats_its_correlate():
    language = _with(_base(), correlative_adverbials=True, subordinator_position="before")
    _, _, glosses = _render(language, _verb("know"), _clause("the-more", "adverbial", _verb("read")))
    assert glosses.count("the-more") == 2 and glosses[0] == "the-more"


def test_a_language_without_correlative_adverbials_keeps_the_order():
    language = _with(_base(), correlative_adverbials=False, subordinator_position="before")
    _, _, glosses = _render(language, _noun("dog"), _verb("see"), _clause("if", "adverbial", _verb("sleep")))
    assert glosses[:2] == ["dog", "see"] and "then" not in glosses


# --- clause coordination ---------------------------------------------------------


def _coordination(strategy: str, **extra):
    base = _find(lambda g: "converb" in g.verb_forms and not g.pro_drop and not g.has_articles and not g.noun_classes)
    return _with(base, clause_coordination=strategy, **extra)


def test_a_conjunction_word_joins_clauses_in_a_word_language():
    language = _coordination("word")
    _, _, glosses = _render(language, _verb("see"), _clause("and", "coordinate", _verb("hear")))
    assert glosses == ["see", "and", "hear"]
    assert _render(language, _verb("see"), _clause("but", "coordinate", _verb("hear")))[2][1] == "but"


def test_a_converb_language_joins_clauses_with_a_medial_verb():
    language = _coordination("converb")
    updated, tokens, glosses = _render(language, _verb("see"), _clause("and", "coordinate", _verb("hear")))
    assert glosses == ["see", "hear"]
    decoded = _decode_verb_full(language, tokens[0])
    assert decoded is not None and decoded[1] == "converb"
    assert "see and" in translate_to_english(" ".join(tokens), updated, _CLIENT).text


def test_a_juxtaposing_language_uses_no_conjunction():
    language = _coordination("juxtapose")
    _, _, glosses = _render(language, _verb("see"), _clause("and", "coordinate", _verb("hear")))
    assert glosses == ["see", "hear"]


def test_conjunction_reduction_drops_a_repeated_subject_pronoun():
    language = _coordination("word", conjunct_reduction=True)
    slots = (_pronoun("I"), _verb("see", agreement="I"), _clause("and", "coordinate", _pronoun("I"), _verb("hear", agreement="I")))
    reduced = _render(language, *slots)[2]
    kept = _render(_with(language, conjunct_reduction=False), *slots)[2]
    assert len(reduced) == len(kept) - 1 and reduced.count("I") == 1
    other = (_pronoun("I"), _verb("see", agreement="I"), _clause("and", "coordinate", _pronoun("you"), _verb("hear", agreement="you")))
    assert len(_render(language, *other)[2]) == len(_render(_with(language, conjunct_reduction=False), *other)[2])


# --- complementizers ----------------------------------------------------------------


def test_the_complementizer_follows_the_class_of_the_governing_verb():
    language = _with(_base(), complementizer_by_verb=True, subordinator_position="before")
    for verb, expected in (("want", "that-desire"), ("say", "that-speech"), ("see", "that-perception"), ("know", "that-factive")):
        _, _, glosses = _render(language, _pronoun("I"), _verb(verb), _clause("that", "complement", _noun("river")))
        assert expected in glosses, verb
    _, _, glosses = _render(language, _pronoun("I"), _verb("sleep"), _clause("that", "complement", _noun("river")))
    assert "that" in glosses and "that-desire" not in glosses


def test_one_complementizer_where_the_language_does_not_distinguish():
    language = _with(_base(), complementizer_by_verb=False, subordinator_position="before")
    _, _, glosses = _render(language, _pronoun("I"), _verb("want"), _clause("that", "complement", _noun("river")))
    assert "that" in glosses and "that-desire" not in glosses


def test_a_class_complementizer_reads_back_as_that():
    language = _with(_base(), complementizer_by_verb=True, subordinator_position="before")
    updated, tokens, _ = _render(language, _pronoun("I"), _verb("want"), _clause("that", "complement", _noun("river")))
    english = translate_to_english(" ".join(tokens), updated, _CLIENT).text.split()
    assert "that" in english and "river" in english


# --- reading back ---------------------------------------------------------------------


def test_the_fluency_prompt_mentions_the_new_strategies():
    language = _find(lambda g: g.relative_pronoun_declines and g.complementizer_by_verb and g.correlative_adverbials)
    spy = _SpyClient()
    translate_to_english("anything", language, spy)
    system = next(r.system for r in spy.requests if r.purpose == "translate.fluency")
    assert "the relative pronoun declines" in system and "complementizer depends on the governing verb" in system
    assert '"then" in the main clause' in system
    word = _find(lambda g: g.clause_coordination == "converb")
    spy = _SpyClient()
    translate_to_english("anything", word, spy)
    assert "medial verb form" in next(r.system for r in spy.requests if r.purpose == "translate.fluency")


def test_whole_sentences_still_translate():
    language = _find(lambda g: g.word_order.value == "SVO")
    for sentence in ("I see the dog which I hear.", "I see the man whose dog sleeps.", "I see the dog and I hear the cat."):
        result = translate_to_conlang(sentence, language, _CLIENT)
        assert result.text
        assert "dog" in translate_to_english(result.text, result.language, _CLIENT).text
