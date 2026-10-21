"""Translation robustness: heuristic warnings on `TranslationResult` for two ways a real LLM's
plan can quietly go wrong without failing outright -- dropping an input content word entirely, and
coining a brand-new word for a token it never actually recognized as a real word (see
`docs/DEFERRED.md` ch. 1's "translation output is sometimes far too short" and ch. 3's "unknown
words are coined silently"). Both are warnings, not fixes -- see `TranslationResult.warnings`'s own
docstring for why a wrong auto-correction was deliberately not attempted."""

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import _dropped_word_warnings, _lookup_or_coin, _render_plan
from tests._shared_language import cached_language

_CLIENT = FakeLLMClient()
_language = cached_language


# --- A: dropped-word detection ------------------------------------------------------------------


def test_a_content_word_with_no_matching_gloss_in_the_plan_is_flagged():
    plan = SentencePlan(slots=(
        PlannedSlot(kind="content", gloss="i", pos="pronoun"),
        PlannedSlot(kind="content", gloss="see", pos="verb", agreement="default"),
    ))
    warnings = _dropped_word_warnings("I see the dog", plan)
    assert any("dog" in w for w in warnings)


def test_a_fully_covered_sentence_produces_no_warnings():
    plan = SentencePlan(slots=(
        PlannedSlot(kind="content", gloss="i", pos="pronoun"),
        PlannedSlot(kind="content", gloss="see", pos="verb", agreement="default"),
        PlannedSlot(kind="content", gloss="dog", pos="noun"),
    ))
    assert _dropped_word_warnings("I see the dog", plan) == []


def test_regular_inflection_matches_the_plans_base_lemma_gloss_by_prefix():
    # "walked" against the plan's own base-lemma gloss "walk" -- a loose prefix match either
    # direction, deliberately tolerant of regular inflection (not a guarantee for irregular forms).
    plan = SentencePlan(slots=(
        PlannedSlot(kind="content", gloss="i", pos="pronoun"),
        PlannedSlot(kind="content", gloss="walk", pos="verb", tense="past"),
    ))
    assert _dropped_word_warnings("I walked", plan) == []


def test_closed_class_stopwords_never_trigger_a_false_positive():
    # Articles, pronouns, copula/auxiliary/modal forms, conjunctions, prepositions, negation and
    # wh-words are never their own "content" slot -- an ordinary sentence full of them shouldn't
    # flag anything just because the plan has no gloss for "the" or "is".
    plan = SentencePlan(slots=(
        PlannedSlot(kind="content", gloss="dog", pos="noun"),
        PlannedSlot(kind="content", gloss="red", pos="adjective"),
    ))
    assert _dropped_word_warnings("The dog is not red, and it was never that.", plan) == []


def test_a_multi_word_name_glosses_each_of_its_own_words_too():
    # Real bug found via live verification: a real LLM plans a multi-word name ("New York") as one
    # "name" slot with gloss "new york", but the input tokenizer splits "York" apart from "New" --
    # without also checking each word of the gloss individually, "york" never prefix-matches the
    # whole-phrase gloss "new york" in either direction and gets falsely flagged as dropped.
    plan = SentencePlan(slots=(
        PlannedSlot(kind="content", gloss="i", pos="pronoun"),
        PlannedSlot(kind="content", gloss="see", pos="verb"),
        PlannedSlot(kind="name", gloss="New York"),
    ))
    assert _dropped_word_warnings("I see New York", plan) == []


def test_a_clause_nested_inside_the_plan_still_counts_as_covering_its_own_words():
    nested = SentencePlan(slots=(PlannedSlot(kind="content", gloss="run", pos="verb"),))
    plan = SentencePlan(slots=(
        PlannedSlot(kind="content", gloss="i", pos="pronoun"),
        PlannedSlot(kind="content", gloss="see", pos="verb"),
        PlannedSlot(kind="clause", gloss="that", pos="other", clause=nested),
    ))
    assert _dropped_word_warnings("I see that run", plan) == []


# --- B: flagging likely-nonsense coinage --------------------------------------------------------


def test_slots_from_raw_flags_a_missing_pos_as_guessed():
    raw = [{"kind": "content", "gloss": "lkdjhr"}]  # no "pos" key at all
    slots = sentence_planner._slots_from_raw(raw, depth=0)
    assert slots[0].pos_was_guessed is True
    assert slots[0].pos == "noun"  # still silently defaulted, just now flagged


def test_slots_from_raw_flags_an_unrecognized_pos_string_as_guessed():
    raw = [{"kind": "content", "gloss": "lkdjhr", "pos": "not-a-real-pos"}]
    slots = sentence_planner._slots_from_raw(raw, depth=0)
    assert slots[0].pos_was_guessed is True


def test_slots_from_raw_does_not_flag_a_real_recognized_pos():
    raw = [{"kind": "content", "gloss": "dumb", "pos": "adjective"}]
    slots = sentence_planner._slots_from_raw(raw, depth=0)
    assert slots[0].pos_was_guessed is False


def test_coining_a_pos_guessed_slot_adds_a_warning_but_still_coins_the_word():
    language = _language(1)
    warnings: list[str] = []
    coined = []
    updated, entry = _lookup_or_coin(
        language, "lkdjhr", PartOfSpeech.NOUN, coined, _CLIENT,
        lemma_candidates=["lkdjhr"], pos_was_guessed=True, warnings=warnings,
    )
    assert entry in coined  # still coined -- this plan only adds visibility, not a behavior change
    assert len(warnings) == 1 and "lkdjhr" in warnings[0]


def test_coining_a_real_recognized_word_adds_no_warning():
    language = _language(1)
    warnings: list[str] = []
    coined = []
    _lookup_or_coin(
        language, "sometotallynewword", PartOfSpeech.NOUN, coined, _CLIENT,
        lemma_candidates=["sometotallynewword"], pos_was_guessed=False, warnings=warnings,
    )
    assert warnings == []


def test_render_plan_surfaces_a_coinage_warning_for_a_pos_guessed_content_slot():
    language = _language(1)
    plan = SentencePlan(slots=(
        PlannedSlot(kind="content", gloss="i", pos="pronoun"),
        PlannedSlot(kind="content", gloss="seeeee", pos="verb", agreement="default"),
        PlannedSlot(kind="content", gloss="lkdjhr", pos="noun", pos_was_guessed=True),
    ))
    warnings: list[str] = []
    _render_plan(plan, language, _CLIENT, [], warnings=warnings)
    assert any("lkdjhr" in w for w in warnings)
