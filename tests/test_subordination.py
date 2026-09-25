"""Subordination refinements: rolled linker placement, relativization
strategies and relative-clause position, non-finite verb forms, and the
subjunctive in subordinate clauses."""

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
        continue
    raise AssertionError("no seed found")


def _with(language, **updates):
    return language.model_copy(update={"grammar": language.grammar.model_copy(update=updates)})


def _base():
    """A language with none of the noun-phrase extras that would add words around a noun."""
    return _find(
        lambda g: not g.has_articles and not g.uses_classifiers and not g.noun_classes and g.pro_drop is False
    )


def _render(language, *slots):
    updated, romanized, _, glosses = _render_plan(SentencePlan(slots=tuple(slots)), language, _CLIENT, [])
    return updated, romanized, glosses


def _noun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="noun", **kw)


def _verb(gloss: str = "sleep", **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="verb", **kw)


def _clause(gloss: str, role: str, *slots: PlannedSlot) -> PlannedSlot:
    return PlannedSlot(kind="clause", gloss=gloss, role=role, clause=SentencePlan(slots=tuple(slots)))


# --- generation -----------------------------------------------------------


def test_every_choice_is_rolled_and_correlates_with_word_order():
    grammars = [_language(s).grammar for s in range(1, 120)]
    assert {g.relativization for g in grammars} == {"pronoun", "particle", "gap", "resumptive", "correlative"}
    assert {g.relative_clause_position for g in grammars} == {"after_noun", "before_noun"}
    assert {g.subordinator_position for g in grammars} == {"before", "after"}
    assert {f for g in grammars for f in g.verb_forms} == set(subordination_gen.VERB_FORM_LABELS)
    assert {g.subordinate_mood_use for g in grammars} == {True, False}
    final = [g.subordinator_position == "after" for g in grammars if g.word_order.value in ("SOV", "OSV")]
    other = [g.subordinator_position == "after" for g in grammars if g.word_order.value not in ("SOV", "OSV")]
    assert sum(final) / len(final) > sum(other) / len(other) + 0.3
    ov = [g.relative_clause_position == "before_noun" for g in grammars if g.postpositional]
    vo = [g.relative_clause_position == "before_noun" for g in grammars if not g.postpositional]
    assert sum(ov) / len(ov) > sum(vo) / len(vo) + 0.2


def test_the_non_finite_forms_have_suffixes():
    for seed in range(1, 60):
        grammar = _language(seed).grammar
        assert [a.label for a in grammar.verb_form_affixes] == list(grammar.verb_forms)


def test_grammar_defaults_keep_old_saved_languages_valid():
    fields = GrammarProfile.model_fields
    assert fields["subordinator_position"].default == ""
    assert fields["relativization"].default == "pronoun"
    assert fields["relative_clause_position"].default == "after_noun"
    assert fields["verb_forms"].default == () and fields["subordinate_mood_use"].default is False


# --- planning -------------------------------------------------------------


def test_parse_reads_the_verb_form():
    plan = sentence_planner._parse('[{"kind": "content", "gloss": "see", "pos": "verb", "verb_form": "infinitive"}]')
    assert plan is not None and plan.slots[0].verb_form == "infinitive"


def test_the_prompt_describes_each_strategy():
    for strategy, expected in (
        ("pronoun", 'a relative pronoun: "who" for a person'),
        ("particle", '"gloss" is "rel"'),
        ("gap", "NO linking word"),
        ("resumptive", "resumptive pronoun"),
        ("correlative", 'adds "that" before the noun'),
    ):
        language = _find(lambda g: g.relativization == strategy)
        assert expected in sentence_planner._build_system_prompt(language), strategy
    with_forms = _find(lambda g: "infinitive" in g.verb_forms and "participle" in g.verb_forms)
    prompt = sentence_planner._build_system_prompt(with_forms)
    assert 'the "infinitive" for a complement' in prompt and 'the "participle"' in prompt
    without = _find(lambda g: not g.verb_forms)
    assert "no non-finite verb forms" in sentence_planner._build_system_prompt(without)
    mood = _find(lambda g: g.subordinate_mood_use)
    assert "subjunctive/irrealis" in sentence_planner._build_system_prompt(mood)


_META = {"word_order": "SVO", "alignment": "nominative_accusative", "tenses": "past,non_past"}


def _nested(sentence: str, **meta):
    return _fake_plan_dict(sentence, {**_META, **meta})["slots"]


def test_the_fake_planner_plans_a_relative_clause_right_after_its_noun():
    slots = _nested("I see the dog who sleeps.")
    clause = slots[-1]
    assert clause["kind"] == "clause" and clause["role"] == "relative" and clause["gloss"] == "who"
    assert slots[-2]["gloss"] == "dog"
    verb = clause["clause"]["slots"][0]
    assert verb["pos"] == "verb" and verb["gloss"] == "sleep"  # the relativized subject is a gap


def test_a_resumptive_language_keeps_the_pronoun_in_the_clause():
    clause = _nested("I see the dog which sees the river.", relativization="resumptive")[-1]
    assert clause["clause"]["slots"][0]["gloss"] == "he"


def test_the_fake_planner_plans_an_infinitive_or_a_finite_complement():
    infinitive = _nested("I want to see the river.", verb_forms="infinitive")[-1]
    assert infinitive["role"] == "complement" and infinitive["gloss"] == ""
    verb = infinitive["clause"]["slots"][0]
    assert verb["verb_form"] == "infinitive" and "tense" not in verb and "agreement" not in verb
    finite = _nested("I want to see the river.")[-1]
    assert finite["gloss"] == "that" and finite["clause"]["slots"][0]["gloss"] == "i"


def test_a_to_that_is_not_an_infinitive_is_left_alone():
    assert all(s["kind"] != "clause" for s in _nested("Come to the mountains!"))


# --- relative clauses, rendered ----------------------------------------------


def _relative_plan(gloss: str = "who"):
    return (_noun("dog"), _clause(gloss, "relative", _verb()))


def test_a_gap_relative_has_no_linking_word():
    language = _with(_base(), relativization="gap", relative_clause_position="after_noun")
    updated, tokens, glosses = _render(language, *_relative_plan())
    assert len(tokens) == 2 and glosses == ["dog", "sleep"]
    assert updated.lexicon.by_gloss("rel") is None


def test_a_particle_or_resumptive_relative_uses_one_invariant_word():
    for strategy in ("particle", "resumptive"):
        language = _with(_base(), relativization=strategy, relative_clause_position="after_noun")
        for planner_word in ("who", "which"):
            _, _, glosses = _render(language, *_relative_plan(planner_word))
            assert "rel" in glosses and "who" not in glosses and "which" not in glosses


def test_a_relative_pronoun_language_keeps_the_planners_pronoun_and_defaults_to_who():
    language = _with(_base(), relativization="pronoun", relative_clause_position="after_noun")
    assert _render(language, *_relative_plan("which"))[2] == ["dog", "which", "sleep"]
    assert _render(language, _noun("dog"), _clause("", "relative", _verb()))[2] == ["dog", "who", "sleep"]


def test_a_relative_clause_follows_or_precedes_its_noun_per_language():
    after = _with(_base(), relativization="gap", relative_clause_position="after_noun")
    assert _render(after, *_relative_plan())[2] == ["dog", "sleep"]
    before = _with(_base(), relativization="gap", relative_clause_position="before_noun")
    assert _render(before, *_relative_plan())[2] == ["sleep", "dog"]


def test_a_prenominal_relative_takes_the_whole_noun_phrase_with_it():
    language = _with(_base(), relativization="gap", relative_clause_position="before_noun")
    adjective = PlannedSlot(kind="content", gloss="high", pos="adjective")
    _, _, glosses = _render(language, _verb("see"), adjective, _noun("dog"), _clause("", "relative", _verb()))
    assert glosses == ["see", "sleep", "high", "dog"]


def test_the_relative_word_leads_a_postnominal_clause_and_follows_a_prenominal_one():
    postnominal = _with(_base(), relativization="particle", relative_clause_position="after_noun")
    assert _render(postnominal, *_relative_plan())[2] == ["dog", "rel", "sleep"]
    prenominal = _with(_base(), relativization="particle", relative_clause_position="before_noun")
    assert _render(prenominal, *_relative_plan())[2] == ["sleep", "rel", "dog"]


def test_a_correlative_moves_the_clause_to_the_front_and_points_back_with_that():
    language = _with(_base(), relativization="correlative", relative_clause_position="after_noun")
    _, _, glosses = _render(language, _verb("see"), *_relative_plan("which"))
    assert glosses[0] == "which" and glosses[1] == "sleep"  # the relative clause comes first
    assert glosses.index("that") + 1 == glosses.index("dog")  # the correlate stands before the noun
    assert glosses.count("dog") == 1


def test_a_relative_clause_with_nothing_before_it_is_left_alone():
    language = _with(_base(), relativization="gap", relative_clause_position="before_noun")
    _, _, glosses = _render(language, _clause("", "relative", _verb()), _noun("dog"))
    assert glosses == ["sleep", "dog"]


# --- other linkers, non-finite verbs, moods ---------------------------------------


def test_the_subordinator_position_is_the_languages_own_fact():
    for position in ("before", "after"):
        language = _with(_base(), subordinator_position=position)
        _, _, glosses = _render(language, _noun("dog"), _clause("that", "complement", _noun("river")))
        assert (glosses[-1] == "that") == (position == "after")
        assert (glosses[1] == "that") == (position == "before")


def test_an_infinitive_replaces_tense_and_agreement_with_its_own_suffix():
    language = _find(lambda g: "infinitive" in g.verb_forms)
    finite = _render(language, _verb("see", tense=None, agreement="I"))[1][0]
    infinitive = _render(language, _verb("see", verb_form="infinitive"))[1][0]
    assert infinitive != finite
    decoded = _decode_verb_full(language, infinitive)
    assert decoded is not None and decoded[0] == language.lexicon.by_gloss("see") and decoded[1] == "infinitive"
    english = translate_to_english(infinitive, language, _CLIENT).text
    assert "to see" in english


def test_each_non_finite_form_reads_back():
    language = _find(
        lambda g: len(g.verb_forms) >= 2
        and len({a.suffix for a in g.verb_form_affixes}) == len(g.verb_form_affixes)
        and not g.infinitive_agrees
    )
    for form in language.grammar.verb_forms:
        token = _render(language, _verb("see", verb_form=form))[1][0]
        decoded = _decode_verb_full(language, token)
        assert decoded is not None and decoded[1] == form


def test_a_form_the_language_lacks_is_ignored():
    language = _find(lambda g: "participle" not in g.verb_forms)
    assert _render(language, _verb("see", verb_form="participle")) == _render(language, _verb("see"))


def _clause_verb(language, tokens):
    """The clause verb's token: the one after the leading noun that starts like "see"."""
    stem = language.lexicon.by_gloss("see").romanization[:2].lower()
    return next(t for t in tokens[1:] if t.lower().startswith(stem))


def test_an_if_clause_takes_the_subjunctive_in_a_language_that_does_so():
    language = _with(
        _find(lambda g: g.subordinate_mood_use and not g.periphrastic_labels and not g.affix_positions and not g.correlative_adverbials and ("subjunctive" in g.moods or "irrealis" in g.moods)),
        suppletive_past=(),
    )
    main = _noun("dog")
    with_if = _clause_verb(language, _render(language, main, _clause("if", "adverbial", _verb("see")))[1])
    with_because = _clause_verb(language, _render(language, main, _clause("because", "adverbial", _verb("see")))[1])
    assert with_if != with_because
    decoded = _decode_verb_full(language, with_if)
    assert decoded is not None and decoded[3] in ("subjunctive", "irrealis")


def test_a_planners_own_mood_wins_over_the_forced_one():
    language = _with(
        _find(lambda g: g.subordinate_mood_use and not g.periphrastic_labels and not g.affix_positions and not g.correlative_adverbials and "subjunctive" in g.moods and "conditional" in g.moods),
        suppletive_past=(),
    )
    forced = _clause_verb(language, _render(language, _noun("dog"), _clause("if", "adverbial", _verb("see")))[1])
    own = _clause_verb(
        language, _render(language, _noun("dog"), _clause("if", "adverbial", _verb("see", verb_mood="conditional")))[1]
    )
    assert own != forced


def test_a_language_without_subordinate_moods_leaves_the_verb_alone():
    language = _find(lambda g: not g.subordinate_mood_use)
    a = _render(language, _noun("dog"), _clause("if", "adverbial", _verb("see")))[1]
    b = _render(language, _noun("dog"), _clause("because", "adverbial", _verb("see")))[1]
    assert a[1] == b[1]


# --- reading back and whole sentences ------------------------------------------------


def test_the_fluency_prompt_explains_the_subordination_strategy():
    language = _find(lambda g: g.relativization == "gap" and "infinitive" in g.verb_forms)
    spy = _SpyClient()
    translate_to_english("anything", language, spy)
    system = next(r.system for r in spy.requests if r.purpose == "translate.fluency")
    assert "Subordination:" in system and "no linking word" in system and "infinitives (to see)" in system


def test_a_whole_relative_sentence_renders_in_a_gap_language():
    language = _find(lambda g: g.relativization == "gap" and g.word_order.value == "SVO")
    result = translate_to_conlang("I see the dog who sleeps.", language, _CLIENT)
    assert result.language.lexicon.by_gloss("rel") is None
    assert not any(e.primary_gloss in ("who", "which", "rel") for e in result.coined)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "dog" in english and "sleep" in english


def test_a_whole_infinitive_sentence_renders():
    language = _find(lambda g: "infinitive" in g.verb_forms)
    result = translate_to_conlang("I want to see the river.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "to see" in english and "river" in english
