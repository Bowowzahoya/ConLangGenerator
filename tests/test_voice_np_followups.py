"""Voice and noun-phrase follow-ups: middle/applicative/impersonal voices, passive
agent and agreement, trial and collective number, locative/instrumental case,
adposition placement and case government, suppletive plurals and comparatives,
and inalienable possession."""

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.spec import GenerationSpec, SeedExample, SeedForm
from conlang_generator.generation import voice_np_gen
from tests.factories import make_minimal_language
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from tests._shared_language import cached_language
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import (
    _arrange_adpositions,
    _class_gloss,
    _decode_noun,
    _decode_verb_full,
    _english_verb_phrase,
    _render_plan,
    translate_to_conlang,
    translate_to_english,
)

_CLIENT = FakeLLMClient()

_language = cached_language


def _find(predicate, check=None, limit: int = 300):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language.grammar) and (check is None or check(language)):
            return language
    raise AssertionError("no seed found")


def _with(language, **updates):
    return language.model_copy(update={"grammar": language.grammar.model_copy(update=updates)})


def _render(language, *slots, mood: str = "declarative"):
    updated, romanized, _, glosses = _render_plan(SentencePlan(slots=tuple(slots), mood=mood), language, _CLIENT, [])
    return updated, romanized, glosses


def _noun(gloss: str, **kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="noun", **kw)


def _verb(**kw) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss="see", pos="verb", agreement="I", **kw)


def _preposition(gloss: str) -> PlannedSlot:
    return PlannedSlot(kind="content", gloss=gloss, pos="preposition")


def _plain(language):
    """Without the earlier follow-up features that would spell things another way."""
    return _with(
        language, periphrastic_labels=(), negation_strategy="particle", verb_negative_affixes=(), evidentials=(),
        evidential_affixes=(),
    )


# --- generation -----------------------------------------------------------------


def test_the_follow_up_choices_are_rolled():
    grammars = [_language(s).grammar for s in range(1, 120)]
    assert {v for g in grammars for v in g.voices} >= {"middle", "applicative", "impersonal"}
    assert {a.label for g in grammars for a in g.number_affixes} >= {"trial", "collective"}
    assert {c for g in grammars for c in g.cases} >= {"locative", "instrumental"}
    assert {g.adposition_case_strategy for g in grammars} == {"none", "governs", "case_only"}
    assert {g.passive_agreement for g in grammars} == {"patient", "none"}
    assert {g.passive_agent for g in grammars} == {"word", "case"}
    assert any(g.suppletive_plurals for g in grammars) and any(g.suppletive_degrees for g in grammars)
    assert any(g.inalienable_possession for g in grammars)
    for g in grammars:
        assert [a.label for a in g.voice_affixes] == list(g.voices)
        assert set(g.suppletive_plurals) <= set(voice_np_gen.IRREGULAR_PLURALS)
        assert set(g.suppletive_degrees) <= set(voice_np_gen.SUPPLETIVE_DEGREES)
        assert {a.label for a in g.case_affixes} == set(g.cases)


def test_extra_cases_only_join_a_language_that_already_marks_case():
    for seed in range(1, 120):
        g = _language(seed).grammar
        if not g.cases:
            assert not g.case_affixes and g.adposition_case_strategy in ("none", "governs", "case_only")


def test_the_new_grammar_fields_default_for_older_saved_languages():
    fields = type(_language(1).grammar).model_fields
    assert fields["passive_agreement"].default == "patient" and fields["passive_agent"].default == "word"
    assert fields["adposition_case_strategy"].default == "none" and fields["inalienable_possession"].default is False
    assert fields["suppletive_plurals"].default == () and fields["suppletive_degrees"].default == ()


def test_the_helpers_read_glosses():
    assert voice_np_gen.is_inalienable("hand") and voice_np_gen.is_inalienable("mother")
    assert not voice_np_gen.is_inalienable("dog")
    assert voice_np_gen.suppletive_split("child-plural") == ("child", "plural")
    assert voice_np_gen.suppletive_split("dog") is None
    assert voice_np_gen.suppletive_reading("child", "plural") == "children"
    assert voice_np_gen.suppletive_reading("good", "comparative") == "better"
    assert voice_np_gen.suppletive_reading("good", "superlative") == "best"


def test_suppletive_split_also_recognizes_a_seeded_lemma_via_grammar():
    # Without a grammar, a lemma outside the hardcoded dicts is still
    # unrecognized -- the default `grammar=None` keeps today's exact
    # behavior (the test above already pins this down).
    assert voice_np_gen.suppletive_split("stone-plural") is None
    grammar = make_minimal_language().grammar.model_copy(update={"suppletive_plurals": ("stone",)})
    assert voice_np_gen.suppletive_split("stone-plural", grammar) == ("stone", "plural")
    # A pronoun-shaped gloss ("you-plural") must still never be misread,
    # even with a grammar passed in -- only membership in the right tuple
    # (here: suppletive_plurals) counts, not just the "-plural" suffix.
    assert voice_np_gen.suppletive_split("you-plural", grammar) is None
    assert _class_gloss("stone-plural", grammar) == "stone"
    assert _class_gloss("stone-plural") == "stone-plural"  # no grammar -- unrecognized, unchanged


# --- voices ---------------------------------------------------------------------------


def _voice_language(voice: str):
    def check(language) -> bool:
        language = _plain(language)
        _, parts, _ = _render(language, _verb(voice=voice))
        decoded = _decode_verb_full(language, parts[0])
        return decoded is not None and decoded[4] == voice

    return _plain(_find(lambda g: voice in g.voices and not g.object_agreement and not g.pro_drop, check))


def test_the_new_voices_mark_the_verb_and_decode_back():
    for voice in ("middle", "applicative", "impersonal"):
        language = _voice_language(voice)
        active = _render(language, _verb())[1][0]
        marked = _render(language, _verb(voice=voice))[1][0]
        assert marked != active


def test_the_new_voices_read_back_in_english():
    language = _find(lambda g: True)
    see = language.lexicon.by_gloss("see")
    assert _english_verb_phrase(see, None, None, None, "middle") == "gets seen"
    assert _english_verb_phrase(see, "past", None, None, "middle") == "got seen"
    assert _english_verb_phrase(see, None, None, None, "applicative") == "see for"
    assert _english_verb_phrase(see, None, None, None, "impersonal") == "one sees"


def test_an_impersonal_verb_takes_no_subject_agreement():
    language = _voice_language("impersonal")
    assert _render(language, _verb(voice="impersonal"))[1] == _render(
        language, PlannedSlot(kind="content", gloss="see", pos="verb", agreement="you", voice="impersonal")
    )[1]


def test_a_passive_agrees_only_where_the_language_says_so():
    def clean(language) -> bool:
        return language.grammar.passive_agreement == "none" and "passive" in language.grammar.voices

    none = _plain(_find(lambda g: g.passive_agreement == "none" and "passive" in g.voices and not g.object_agreement))
    i_form = _render(none, _verb(voice="passive"))[1]
    you_form = _render(none, PlannedSlot(kind="content", gloss="see", pos="verb", agreement="you", voice="passive"))[1]
    assert i_form == you_form
    patient = _plain(_find(lambda g: g.passive_agreement == "patient" and "passive" in g.voices and not g.object_agreement))
    a = _render(patient, _verb(voice="passive"))[1]
    b = _render(patient, PlannedSlot(kind="content", gloss="see", pos="verb", agreement="you", voice="passive"))[1]
    assert a != b


# --- trial and collective ------------------------------------------------------------


def _number_language(label: str):
    def check(language) -> bool:
        _, parts, _ = _render(language, _noun("dog", number=label))
        decoded = _decode_noun(language, parts[0])
        return decoded is not None and decoded[1].endswith(label)

    return _find(lambda g: label in [a.label for a in g.number_affixes] and not g.uses_classifiers, check)


def test_trial_and_collective_are_their_own_marked_forms():
    for label in ("trial", "collective"):
        language = _number_language(label)
        plural = _render(language, _noun("dog", number="plural"))[1][0]
        marked = _render(language, _noun("dog", number=label))[1][0]
        assert marked != plural != _render(language, _noun("dog"))[1][0]


def test_trial_and_collective_read_back_in_english():
    for label, expected in (("trial", "three"), ("collective", "group of")):
        language = _number_language(label)
        token = _render(language, _noun("dog", number=label))[1][0]
        assert expected in translate_to_english(token, language, _CLIENT).text


def test_the_fake_planner_marks_a_trial_and_a_collective():
    trial = _find(lambda g: "trial" in [a.label for a in g.number_affixes])
    plan = sentence_planner.plan_sentence("I see three dogs.", trial, _CLIENT)
    assert any(slot.number == "trial" for slot in plan.slots)
    collective = _find(lambda g: "collective" in [a.label for a in g.number_affixes])
    plan = sentence_planner.plan_sentence("I see all dogs.", collective, _CLIENT)
    assert any(slot.number == "collective" for slot in plan.slots)


# --- adpositions and case -------------------------------------------------------------


def _case_language(strategy: str, case: str, postpositional: bool):
    return _plain(
        _find(
            lambda g: g.adposition_case_strategy == strategy and case in g.cases
            and g.postpositional == postpositional and not g.uses_classifiers and not g.noun_classes
            and g.class_marking == "none"
        )
    )


def _in_the_house(language, before: bool):
    house = _noun("house")
    adposition = _preposition("in")
    return [adposition, house] if before else [house, adposition]


def test_a_locative_case_replaces_its_adposition():
    for postpositional in (False, True):
        language = _case_language("case_only", "locative", postpositional)
        bare_house = _render(language, _noun("house"))[1][0]
        parts = _render(language, *_in_the_house(language, not postpositional))[1]
        assert len(parts) == 1 and parts[0] != bare_house
        assert parts == _render(language, _noun("house", case="locative"))[1]


def test_a_governing_adposition_stays_and_its_noun_takes_the_case():
    language = _case_language("governs", "locative", False)
    parts = _render(language, *_in_the_house(language, True))[1]
    assert len(parts) == 2
    in_word = language.lexicon.by_gloss("in")
    assert parts[0] == in_word.romanization or parts[1] == in_word.romanization
    assert _render(language, _noun("house", case="locative"))[1][0] in parts


def test_without_a_strategy_the_adposition_and_noun_are_left_alone():
    language = _plain(_find(lambda g: g.adposition_case_strategy == "none" and not g.uses_classifiers))
    parts = _render(language, *_in_the_house(language, not language.grammar.postpositional))[1]
    assert len(parts) == 2 and _render(language, _noun("house"))[1][0] in parts


def test_an_adposition_is_moved_to_the_languages_own_side():
    for postpositional in (False, True):
        language = _plain(
            _find(lambda g: g.adposition_case_strategy == "none" and g.postpositional == postpositional)
        )
        wrong = _arrange_adpositions(language, tuple(_in_the_house(language, before=postpositional)))
        assert [s.gloss for s in wrong] == (["house", "in"] if postpositional else ["in", "house"])


def test_an_adposition_takes_its_whole_noun_phrase_with_it():
    language = _plain(_find(lambda g: g.adposition_case_strategy == "none" and g.postpositional and not g.adjective_after_noun))
    adjective = PlannedSlot(kind="content", gloss="big", pos="adjective")
    arranged = _arrange_adpositions(language, (_preposition("in"), adjective, _noun("house")))
    assert [s.gloss for s in arranged] == ["big", "house", "in"]


def test_the_passive_agent_can_be_an_instrumental_case():
    language = _plain(
        _find(
            lambda g: g.passive_agent == "case" and "instrumental" in g.cases and "passive" in g.voices
            and not g.uses_classifiers and not g.noun_classes and g.class_marking == "none"
        )
    )
    by = _preposition("by")
    dog = _noun("dog")
    agent = [dog, by] if language.grammar.postpositional else [by, dog]
    parts = _render(language, *agent)[1]
    assert len(parts) == 1 and parts == _render(language, _noun("dog", case="instrumental"))[1]


def test_case_marked_nouns_read_back_with_their_adposition():
    language = _case_language("case_only", "locative", False)
    updated, parts, _ = _render(language, _noun("house", case="locative"))
    assert "in" in translate_to_english(parts[0], updated, _CLIENT).text.split()


# --- suppletive plurals and degrees -----------------------------------------------------


def _suppletive_plural_language():
    def check(language) -> bool:
        updated, parts, _ = _render(_plain(language), _noun("child", number="plural"))
        return _decode_noun(updated, parts[0]) is not None

    return _plain(_find(lambda g: "child" in g.suppletive_plurals and not g.uses_classifiers, check))


def test_an_irregular_plural_is_a_separate_word_that_reads_back():
    language = _suppletive_plural_language()
    updated, parts, glosses = _render(language, _noun("child", number="plural"))
    assert "child-plural" in [e.primary_gloss for e in updated.lexicon.entries]
    assert parts[0] != _render(language, _noun("child"))[1][0]
    assert "children" in translate_to_english(parts[0], updated, _CLIENT).text


def test_a_regular_noun_still_takes_the_plural_suffix():
    language = _suppletive_plural_language()
    dog_plural = _render(language, _noun("dog", number="plural"))[1][0]
    assert dog_plural != _render(language, _noun("dog"))[1][0]
    assert "child-plural" not in _render(language, _noun("dog", number="plural"))[2]


def test_a_suppletive_comparative_is_a_separate_word():
    language = _plain(_find(lambda g: "good" in g.suppletive_degrees and g.degree_affixes and not g.noun_classes))
    adjective = PlannedSlot(kind="content", gloss="good", pos="adjective", degree="comparative")
    updated, parts, _ = _render(language, adjective)
    assert "good-comparative" in [e.primary_gloss for e in updated.lexicon.entries]
    assert "better" in translate_to_english(parts[0], updated, _CLIENT).text
    regular = PlannedSlot(kind="content", gloss="big", pos="adjective", degree="comparative")
    _, big_parts, _ = _render(language, regular)
    assert big_parts[0] != language.lexicon.by_gloss("big").romanization


# --- suppletive forms from the user's own seed words -----------------------------------


def _seeded_language(example, grammar_check=lambda g: True, seed_range=range(1, 30)):
    """A freshly generated language from a custom seed example -- cannot
    reuse the shared `_language` cache (it doesn't know about custom
    `seed_examples`). Searches for a seed with no noun classes/classifiers
    so a rendered suppletive form's own agreement/classifier marking can't
    perturb it away from the user's exact given spelling, mirroring
    `_suppletive_plural_language`'s own `not g.uses_classifiers` guard and
    `test_a_suppletive_comparative_is_a_separate_word`'s own
    `not g.noun_classes` guard above. `grammar_check` adds any further
    per-test condition (e.g. "this language rolled the 3-way tense system"
    or "this language has an accusative case")."""
    for seed in seed_range:
        spec = GenerationSpec(prompt="p", seed=seed, seed_examples=(example,))
        language = _plain(generate_language("Test", spec, _CLIENT))
        if (
            not language.grammar.noun_classes and not language.grammar.uses_classifiers
            and grammar_check(language.grammar)
        ):
            return language
    raise AssertionError("no seed found satisfying all conditions")


def test_a_seed_words_own_plural_form_is_used_verbatim():
    example = SeedExample(
        gloss="stone", form="tek", ipa="tek", pos=PartOfSpeech.NOUN,
        forms=(SeedForm(cell="plural", form="tekuli", ipa="tekuli"),),
    )
    language = _seeded_language(example)
    assert "stone" in language.grammar.suppletive_plurals
    entry = language.lexicon.by_gloss("stone-plural")
    assert entry is not None and entry.romanization == "tekuli" and entry.ipa == "tekuli"
    assert entry.notes == "seed word"  # pre-created at generation time, not coined at render

    _, parts, glosses = _render(language, _noun("stone", number="plural"))
    assert parts[0] == "tekuli"
    assert "stone-plural" in glosses
    assert "tekuli" in [e.romanization for e in language.lexicon.entries]  # no second word coined
    assert "stones" in translate_to_english(parts[0], language, _CLIENT).text


def test_a_regular_seed_noun_still_takes_the_plural_suffix():
    example = SeedExample(
        gloss="stone", form="tek", ipa="tek", pos=PartOfSpeech.NOUN,
        forms=(SeedForm(cell="plural", form="tekuli", ipa="tekuli"),),
    )
    language = _seeded_language(example)
    other_plural = _render(language, _noun("dog", number="plural"))[1][0]
    assert other_plural != _render(language, _noun("dog"))[1][0]
    assert "stone-plural" not in _render(language, _noun("dog", number="plural"))[2]


def test_a_seed_words_own_past_tense_form_is_used_verbatim():
    example = SeedExample(
        gloss="jump", form="zim", ipa="zim", pos=PartOfSpeech.VERB,
        forms=(SeedForm(cell="past", form="zanu", ipa="zanu"),),
    )
    language = _seeded_language(example)
    assert "jump" in language.grammar.suppletive_past
    entry = language.lexicon.by_gloss("jump-past")
    assert entry is not None and entry.romanization == "zanu"

    # The suppletive *stem* ("zanu") is used instead of a regularly tense-
    # affixed "zim" -- but, same as the pre-existing hardcoded-irregular
    # mechanism, person agreement (independent of tense) can still mark
    # the surface word, so this checks the right lexicon entry was used
    # (via the returned gloss) and the decoded reading, not byte-exact
    # surface equality.
    verb = PlannedSlot(kind="content", gloss="jump", pos="verb", agreement="I", tense="past")
    _, parts, glosses = _render(language, verb)
    assert "jump-past" in glosses
    assert "jumped" in translate_to_english(parts[0], language, _CLIENT).text
    # The present tense is unaffected -- the suppletive form only covers "past".
    present = PlannedSlot(kind="content", gloss="jump", pos="verb", agreement="I")
    _, present_parts, present_glosses = _render(language, present)
    assert "jump-past" not in present_glosses
    assert present_parts[0] != parts[0]


def test_a_seed_words_own_comparative_and_superlative_forms_are_used_verbatim():
    example = SeedExample(
        gloss="tall", form="bik", ipa="bik", pos=PartOfSpeech.ADJECTIVE,
        forms=(
            SeedForm(cell="comparative", form="biko", ipa="biko"),
            SeedForm(cell="superlative", form="bikomo", ipa="bikomo"),
        ),
    )
    language = _seeded_language(example)
    assert "tall" in language.grammar.suppletive_degrees
    assert language.lexicon.by_gloss("tall-comparative").romanization == "biko"
    assert language.lexicon.by_gloss("tall-superlative").romanization == "bikomo"

    comparative = PlannedSlot(kind="content", gloss="tall", pos="adjective", degree="comparative")
    assert _render(language, comparative)[1][0] == "biko"
    superlative = PlannedSlot(kind="content", gloss="tall", pos="adjective", degree="superlative")
    assert _render(language, superlative)[1][0] == "bikomo"


def test_giving_only_one_degree_cell_still_renders_the_other_as_some_word():
    # Documented quirk: suppletive_degrees doesn't distinguish which of the
    # two cells a lemma has, so giving only "comparative" still makes the
    # language treat "superlative" as suppletive too -- it falls through
    # to ordinary coining (a fresh, unrelated irregular word), not the
    # regular affixed form and not a crash.
    example = SeedExample(
        gloss="tall", form="bik", ipa="bik", pos=PartOfSpeech.ADJECTIVE,
        forms=(SeedForm(cell="comparative", form="biko", ipa="biko"),),
    )
    language = _seeded_language(example)
    superlative = PlannedSlot(kind="content", gloss="tall", pos="adjective", degree="superlative")
    updated, parts, _ = _render(language, superlative)
    assert parts[0] != "biko"
    assert updated.lexicon.by_gloss("tall-superlative") is not None


def test_a_seed_words_own_future_tense_form_is_used_verbatim():
    example = SeedExample(
        gloss="jump", form="zim", ipa="zim", pos=PartOfSpeech.VERB,
        forms=(SeedForm(cell="future", form="zufu", ipa="zufu"),),
    )
    language = _seeded_language(example, grammar_check=lambda g: "future" in g.tenses)
    assert "jump" in language.grammar.suppletive_future
    entry = language.lexicon.by_gloss("jump-future")
    assert entry is not None and entry.romanization == "zufu"

    verb = PlannedSlot(kind="content", gloss="jump", pos="verb", agreement="I", tense="future")
    _, parts, glosses = _render(language, verb)
    assert "jump-future" in glosses
    assert "will jump" in translate_to_english(parts[0], language, _CLIENT).text
    # The past tense is unaffected -- the suppletive form only covers "future".
    past = PlannedSlot(kind="content", gloss="jump", pos="verb", agreement="I", tense="past")
    _, past_parts, past_glosses = _render(language, past)
    assert "jump-future" not in past_glosses
    assert past_parts[0] != parts[0]


def test_a_seed_words_own_accusative_pronoun_form_is_used_verbatim():
    example = SeedExample(
        gloss="I", form="zu", ipa="zu", pos=PartOfSpeech.PRONOUN,
        forms=(SeedForm(cell="accusative", form="zum", ipa="zum"),),
    )
    language = _seeded_language(example, grammar_check=lambda g: "accusative" in g.cases)
    assert "I" in language.grammar.suppletive_pronoun_persons
    entry = language.lexicon.by_gloss("i-accusative")
    assert entry is not None and entry.romanization == "zum"

    slot = PlannedSlot(kind="content", gloss="I", pos="pronoun", case="accusative")
    _, parts, glosses = _render(language, slot)
    assert parts[0] == "zum"
    assert "i-accusative" in glosses
    assert "me" in translate_to_english(parts[0], language, _CLIENT).text
    # The nominative (citation) form is unaffected.
    nominative = PlannedSlot(kind="content", gloss="I", pos="pronoun")
    _, nom_parts, _ = _render(language, nominative)
    assert nom_parts[0] == "zu"


def test_seeding_a_case_or_tense_the_language_lacks_leaves_the_entry_unused_not_crashing():
    example = SeedExample(
        gloss="I", form="zu", ipa="zu", pos=PartOfSpeech.PRONOUN,
        forms=(SeedForm(cell="locative", form="zul", ipa="zul"),),
    )
    language = _seeded_language(example, grammar_check=lambda g: "locative" not in g.cases)
    # Never folded into the suppletion-gating fields for an absent case.
    assert "I" not in language.grammar.suppletive_pronoun_persons
    # Still created -- just unused (seed_examples.unused_suppletive_form_warnings flags it).
    assert language.lexicon.by_gloss("i-locative") is not None


# --- inalienable possession -------------------------------------------------------------


def test_an_inalienable_noun_takes_no_possessive_marking():
    language = _plain(
        _find(lambda g: g.inalienable_possession and g.possession == "particle" and g.possessive_pronouns == "regular")
    )
    owner = PlannedSlot(kind="content", gloss="he", pos="pronoun", possessive=True)
    dog = _render(language, owner, _noun("dog"))[1]
    hand = _render(language, owner, _noun("hand"))[1]
    assert len(dog) == len(hand) + 1  # the possessive particle is missing


def test_an_alienable_language_marks_every_possessed_noun():
    language = _plain(_find(lambda g: not g.inalienable_possession and g.possession == "particle"))
    owner = PlannedSlot(kind="content", gloss="he", pos="pronoun", possessive=True)
    assert len(_render(language, owner, _noun("dog"))[1]) == len(_render(language, owner, _noun("hand"))[1])


# --- planner ---------------------------------------------------------------------------


def test_the_fake_planner_marks_the_new_voices():
    for voice, sentence in (("antipassive", "The man eats."), ("middle", "The door opens."), ("applicative", "I cook for him.")):
        language = _find(lambda g: voice in g.voices)
        plan = sentence_planner.plan_sentence(sentence, language, _CLIENT)
        assert any(slot.voice == voice for slot in plan.slots), voice


def test_the_planner_prompt_describes_the_new_constructions():
    language = _find(lambda g: "middle" in g.voices)
    prompt = sentence_planner._build_system_prompt(language)
    assert '"middle"' in prompt and '"applicative"' in prompt and '"impersonal"' in prompt
    assert '"trial"' in prompt and "turns them into case endings" in prompt
