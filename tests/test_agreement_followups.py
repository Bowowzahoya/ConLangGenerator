"""Agreement follow-ups: class assignment strategies, class marked on the noun
itself, agreement in number and case (and by numerals), and agreement worked out
from position instead of named by the planner."""

from conlang_generator.core.grammar import GrammarProfile
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import noun_class_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import (
    _article_forms,
    _decode_adjective_full,
    _decode_noun,
    _render_plan,
    translate_to_conlang,
    translate_to_english,
)

_CLIENT = FakeLLMClient()
_CACHE: dict[int, object] = {}
_ANIMACY = ("animate", "inanimate")
_CASES = ("nominative", "accusative", "genitive", "dative")


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


def _noun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="noun", **kw)


def _adjective(**kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss="high", pos="adjective", **kw)


def _animacy_language():
    """An animate/inanimate language with adjectives, plain otherwise."""
    language = _find(
        lambda g: g.noun_classes == _ANIMACY and g.class_marking == "none" and not g.uses_classifiers
    )
    return _with(language, number_agreement_targets=(), case_agreement_targets=())


# --- generation -----------------------------------------------------------


def test_the_follow_up_choices_are_rolled():
    grammars = [_language(s).grammar for s in range(1, 120)]
    with_classes = [g for g in grammars if g.noun_classes]
    assert {g.noun_class_assignment for g in with_classes} == {"hash", "semantic", "formal"}
    assert {g.class_marking for g in with_classes} == {"none", "suffix", "prefix"}
    assert all(g.class_marking == "none" and g.noun_class_assignment == "hash" for g in grammars if not g.noun_classes)
    for g in grammars:
        assert set(noun_class_gen.LEGACY_CLASS_AGREEMENT) <= set(g.class_agreement_targets)
        assert set(g.class_agreement_targets) <= set(noun_class_gen.AGREEMENT_CATEGORIES)
        assert set(g.number_agreement_targets) <= set(noun_class_gen.AGREEMENT_CATEGORIES)
        assert set(g.case_agreement_targets) <= set(noun_class_gen.AGREEMENT_CATEGORIES)
        assert [a.label for a in g.class_marker_affixes] == (list(g.noun_classes) if g.class_marking != "none" else [])
    assert any("numeral" in g.class_agreement_targets for g in grammars)
    assert any(g.number_agreement_targets for g in grammars) and any(g.case_agreement_targets for g in grammars)


def test_class_prefixes_are_open_syllables_and_suffixes_are_endings():
    for g in (_language(s).grammar for s in range(1, 120)):
        for affix in g.class_marker_affixes:
            assert bool(affix.prefix) == (g.class_marking == "prefix")
            assert bool(affix.suffix) == (g.class_marking == "suffix")


def test_grammar_defaults_keep_old_saved_languages_valid():
    fields = GrammarProfile.model_fields
    assert fields["noun_class_assignment"].default == "hash" and fields["class_marking"].default == "none"
    assert fields["class_agreement_targets"].default == noun_class_gen.LEGACY_CLASS_AGREEMENT
    assert fields["number_agreement_targets"].default == () and fields["case_agreement_targets"].default == ()


# --- assignment ------------------------------------------------------------


def test_semantic_fields_group_nouns():
    assert noun_class_gen.semantic_field("hand") == noun_class_gen.semantic_field("eye") == "body"
    assert noun_class_gen.semantic_field("river") == noun_class_gen.semantic_field("sea") == "nature"
    assert noun_class_gen.semantic_field("knife") == "artifact" and noun_class_gen.semantic_field("idea") is None


def test_a_semantic_assignment_gives_a_whole_field_one_class():
    classes = ("masculine", "feminine", "neuter")
    body = {noun_class_gen.assigned_class(classes, 7, w, "semantic") for w in ("hand", "eye", "head", "leg", "foot")}
    nature = {noun_class_gen.assigned_class(classes, 7, w, "semantic") for w in ("river", "sea", "lake", "cloud")}
    assert len(body) == 1 and len(nature) == 1
    across = {
        noun_class_gen.assigned_class(classes, seed, "hand", "semantic")
        for seed in range(1, 40)
    }
    assert len(across) > 1  # which class a field gets depends on the language
    assert noun_class_gen.assigned_class(classes, 7, "man", "semantic") == "masculine"  # natural gender first


def test_a_formal_assignment_follows_the_final_sound():
    classes = ("masculine", "feminine", "neuter")
    a = {noun_class_gen.assigned_class(classes, 3, g, "formal", ipa) for g, ipa in (("x1", "kata"), ("x2", "moka"), ("x3", "ˈsala"))}
    assert len(a) == 1  # all end in "a"
    ends = {noun_class_gen.assigned_class(classes, 3, "n", "formal", f"ka{v}") for v in "aeiou"}
    assert len(ends) > 1
    assert noun_class_gen.assigned_class(classes, 3, "n", "formal", None) == noun_class_gen.noun_class(classes, 3, "n")


def test_the_hash_assignment_and_no_classes_are_unchanged():
    classes = ("masculine", "feminine")
    assert noun_class_gen.assigned_class(classes, 5, "river", "hash") == noun_class_gen.noun_class(classes, 5, "river")
    assert noun_class_gen.assigned_class((), 5, "river", "formal", "kata") is None


# --- class marked on the noun ---------------------------------------------------


def _marked(marking: str):
    return _find(lambda g: g.class_marking == marking and not g.uses_classifiers)


def test_a_suffix_marked_noun_carries_its_class_and_decodes_back():
    language = _marked("suffix")
    dog = language.lexicon.by_gloss("dog")
    token = _render(language, _noun("dog"))[1][0]
    assert token != dog.romanization and token.lower().startswith(dog.romanization.lower()[:2])
    decoded = _decode_noun(language, token)
    assert decoded is not None and decoded[0] == dog


def test_a_prefix_marked_noun_carries_its_class_and_decodes_back():
    language = _marked("prefix")
    dog = language.lexicon.by_gloss("dog")
    token = _render(language, _noun("dog"))[1][0]
    assert token != dog.romanization
    decoded = _decode_noun(language, token)
    assert decoded is not None and decoded[0] == dog


def test_nouns_of_one_class_share_a_marker_and_other_classes_differ():
    language = _with(_marked("suffix"), noun_class_assignment="semantic")
    forms = {}
    for word in ("hand", "eye", "river", "sea", "knife", "bread"):
        entry = language.lexicon.by_gloss(word)
        if entry is None:
            continue
        forms[word] = _render(language, _noun(word))[1][0][len(entry.romanization):]
    assert forms["hand"] == forms["eye"] and forms["river"] == forms["sea"]


def test_an_unmarked_language_leaves_the_noun_bare():
    language = _find(lambda g: g.noun_classes and g.class_marking == "none" and not g.uses_classifiers)
    dog = language.lexicon.by_gloss("dog")
    assert _render(language, _noun("dog"))[1][0] == dog.romanization


def test_a_marked_noun_still_takes_number_and_case():
    language = _marked("suffix")
    dog = language.lexicon.by_gloss("dog")
    plural = _render(language, _noun("dog", number="plural"))[1][0]
    assert plural != _render(language, _noun("dog"))[1][0]
    decoded = _decode_noun(language, plural)
    assert decoded is not None and decoded[0] == dog


def test_a_whole_sentence_reads_back_in_a_marked_language():
    language = _marked("suffix")
    result = translate_to_conlang("I see the dog.", language, _CLIENT)
    assert "dog" in translate_to_english(result.text, result.language, _CLIENT).text


# --- agreement worked out from position ---------------------------------------------


def test_an_adjective_agrees_with_the_adjacent_noun_without_being_told():
    base = _animacy_language()
    before = _with(base, adjective_after_noun=False)
    dog, river = (_render(before, _adjective(), _noun(n))[1][0] for n in ("dog", "river"))
    assert dog != river
    after = _with(base, adjective_after_noun=True)
    dog, river = (_render(after, _noun(n), _adjective())[1][1] for n in ("dog", "river"))
    assert dog != river


def test_a_predicate_adjective_agrees_with_its_subject_across_the_copula():
    language = _with(_animacy_language(), adjective_after_noun=True)
    copula = PlannedSlot(kind="copula")
    dog, river = (_render(language, _noun(n), copula, _adjective())[1][-1] for n in ("dog", "river"))
    assert dog != river


def test_a_named_noun_overrides_the_inferred_one():
    language = _with(_animacy_language(), adjective_after_noun=False)
    named = _render(language, _adjective(agrees_with="river"), _noun("dog"))[1][0]
    assert named == _render(language, _adjective(), _noun("river"))[1][0]


def test_an_adjective_with_no_noun_stays_bare():
    language = _animacy_language()
    adjective = language.lexicon.by_gloss("high")
    assert _render(language, _adjective())[1][0] == adjective.romanization


def test_the_agreeing_adjective_decodes_back():
    language = _with(_animacy_language(), adjective_after_noun=False)
    token = _render(language, _adjective(), _noun("dog"))[1][0]
    decoded = _decode_adjective_full(language, token)
    assert decoded is not None and decoded[0] == language.lexicon.by_gloss("high") and decoded[1] == "animate"


# --- number, case and numerals ---------------------------------------------------------


def test_an_adjective_agrees_in_number_where_the_language_says_so():
    language = _with(_animacy_language(), adjective_after_noun=False, number_agreement_targets=("adjective",))
    singular = _render(language, _adjective(), _noun("dog"))[1][0]
    plural = _render(language, _adjective(), _noun("dog", number="plural"))[1][0]
    assert singular != plural
    decoded = _decode_adjective_full(language, plural)
    assert decoded is not None and decoded[0] == language.lexicon.by_gloss("high")
    off = _with(language, number_agreement_targets=())
    assert _render(off, _adjective(), _noun("dog"))[1][0] == _render(off, _adjective(), _noun("dog", number="plural"))[1][0]


def test_an_adjective_agrees_in_case_where_the_language_says_so():
    base = _with(_animacy_language(), adjective_after_noun=False, cases=_CASES)
    if not base.grammar.case_affixes:
        base = _find(lambda g: g.noun_classes == _ANIMACY and len(g.case_affixes) >= 2)
        base = _with(base, adjective_after_noun=False)
    language = _with(base, case_agreement_targets=("adjective",))
    case = language.grammar.case_affixes[-1].label
    plain = _render(language, _adjective(), _noun("dog"))[1][0]
    marked = _render(language, _adjective(), _noun("dog", case=case))[1][0]
    assert plain != marked


def test_articles_and_demonstratives_agree_in_number_too():
    language = _find(lambda g: g.has_articles and g.noun_classes == _ANIMACY and not g.uses_classifiers)
    language = _with(language, number_agreement_targets=("article", "demonstrative"), demonstrative_after_noun=False)
    article = PlannedSlot(kind="article")
    demonstrative = PlannedSlot(kind="demonstrative", gloss="this")
    for slot in (article, demonstrative):
        assert _render(language, slot, _noun("dog"))[1][0] != _render(language, slot, _noun("dog", number="plural"))[1][0]
    forms = _article_forms(language)
    singular = _render(language, article, _noun("dog"))[1][0].lower()
    plural = _render(language, article, _noun("dog", number="plural"))[1][0].lower()
    assert singular in forms and plural in forms


def test_a_numeral_agrees_in_class_where_the_language_says_so():
    language = _with(_animacy_language(), class_agreement_targets=noun_class_gen.LEGACY_CLASS_AGREEMENT + ("numeral",))
    two = PlannedSlot(kind="content", gloss="two", pos="numeral")
    dog, river = (_render(language, two, _noun(n))[1][0] for n in ("dog", "river"))
    assert dog != river
    plain = _with(language, class_agreement_targets=noun_class_gen.LEGACY_CLASS_AGREEMENT)
    assert _render(plain, two, _noun("dog"))[1][0] == _render(plain, two, _noun("river"))[1][0]


def test_a_possessive_word_agrees_in_number_where_the_language_says_so():
    language = _find(lambda g: g.possessive_pronouns == "words" and not g.uses_classifiers)
    language = _with(language, number_agreement_targets=("possessive",))
    mine = PlannedSlot(kind="possessive_pronoun", gloss="I")
    assert _render(language, mine, _noun("dog"))[1][0] != _render(language, mine, _noun("dog", number="plural"))[1][0]


def test_the_planner_is_told_agreement_is_worked_out_from_position():
    language = _animacy_language()
    prompt = sentence_planner._build_system_prompt(language)
    assert "works out from position which noun" in prompt and "so \"agrees_with\" is optional" in prompt
