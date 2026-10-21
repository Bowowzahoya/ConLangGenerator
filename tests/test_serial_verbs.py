"""Serial verb constructions (resultative subtype only -- see `docs/DEFERRED.md` ch. 10's own
scoping note): Mandarin's own 打破 "hit-break" = to break, a finite verb directly followed, with no
conjunction, by an invariant bare verb naming the result."""

from conlang_generator.core.grammar import MorphologicalType
from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.generation.voice_np_gen import RESULT_VERB_POOL
from conlang_generator.llm.fake_client import FakeLLMClient
from tests._shared_language import cached_language
from conlang_generator.translation import sentence_planner
from conlang_generator.translation.sentence_planner import PlannedSlot, SentencePlan
from conlang_generator.translation.translator import _render_plan, translate_to_conlang, translate_to_english

_CLIENT = FakeLLMClient()
_language = cached_language


def _find(predicate, limit: int = 300):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language):
            return language
    raise AssertionError("no seed found")


# --- generation -------------------------------------------------------------------------------


def test_the_serial_verb_roll_is_isolating_skewed_with_a_real_result_pool():
    isolating_hits = total_isolating = 0
    other_hits = total_other = 0
    for seed in range(1, 200):
        grammar = _language(seed).grammar
        if grammar.morphological_type is MorphologicalType.ISOLATING:
            total_isolating += 1
            isolating_hits += grammar.has_serial_verbs
        else:
            total_other += 1
            other_hits += grammar.has_serial_verbs
        if grammar.has_serial_verbs:
            assert 3 <= len(grammar.serial_result_verbs) <= 6
            assert len(set(grammar.serial_result_verbs)) == len(grammar.serial_result_verbs)
            assert all(v in RESULT_VERB_POOL for v in grammar.serial_result_verbs)
        else:
            assert grammar.serial_result_verbs == ()
    assert total_isolating > 5 and total_other > 5  # sanity: both buckets actually sampled
    assert (isolating_hits / total_isolating) > (other_hits / total_other)


# --- render -----------------------------------------------------------------------------------


def _serial_language():
    return _find(lambda l: l.grammar.has_serial_verbs)


def test_the_result_verb_renders_as_its_own_exact_bare_citation_form():
    language = _serial_language()
    result_gloss = language.grammar.serial_result_verbs[0]
    plan = SentencePlan(slots=(
        PlannedSlot(kind="content", gloss="i", pos="pronoun"),
        PlannedSlot(kind="content", gloss="hit", pos="verb", agreement="default", tense="past"),
        PlannedSlot(kind="content", gloss=result_gloss, pos="verb", serial_result=True),
        PlannedSlot(kind="content", gloss="stone", pos="noun"),
    ))
    new_language, romanized, ipa, coined, _ = _render_plan(plan, language, _CLIENT, [])
    result_entry = new_language.lexicon.by_gloss(result_gloss)
    assert result_entry.romanization in romanized
    assert result_entry.ipa in ipa
    # No tense/agreement suffix landed on it -- the rendered form is byte-identical to the bare
    # citation entry, not a longer inflected one.
    index = romanized.index(result_entry.romanization)
    assert ipa[index] == result_entry.ipa


def test_the_object_is_positioned_around_the_whole_two_verb_complex():
    language = _serial_language()
    result_gloss = language.grammar.serial_result_verbs[0]
    plan = SentencePlan(slots=(
        PlannedSlot(kind="content", gloss="i", pos="pronoun"),
        PlannedSlot(kind="content", gloss="hit", pos="verb", agreement="default"),
        PlannedSlot(kind="content", gloss=result_gloss, pos="verb", serial_result=True),
        PlannedSlot(kind="content", gloss="stone", pos="noun"),
    ))
    new_language, romanized, ipa, coined, _ = _render_plan(plan, language, _CLIENT, [])
    result_entry = new_language.lexicon.by_gloss(result_gloss)
    stone_entry = new_language.lexicon.by_gloss("stone")
    verb_index = romanized.index(result_entry.romanization)
    object_index = next(i for i, w in enumerate(romanized) if w == stone_entry.romanization or stone_entry.romanization in w)
    # The object never sits between the two verbs -- it's on one side of the whole V1+V2 complex.
    assert object_index > verb_index or object_index < verb_index - 1 or object_index == 0


# --- decode -------------------------------------------------------------------------------------


def test_decoding_a_serial_verb_sentence_reads_back_both_verbs_and_the_object():
    language = _serial_language()
    result_gloss = language.grammar.serial_result_verbs[0]
    plan = SentencePlan(slots=(
        PlannedSlot(kind="content", gloss="i", pos="pronoun"),
        PlannedSlot(kind="content", gloss="hit", pos="verb", agreement="default"),
        PlannedSlot(kind="content", gloss=result_gloss, pos="verb", serial_result=True),
        PlannedSlot(kind="content", gloss="stone", pos="noun"),
    ))
    new_language, romanized, ipa, coined, _ = _render_plan(plan, language, _CLIENT, [])
    text = " ".join(romanized)
    decoded = translate_to_english(text, new_language, _CLIENT)
    lower = decoded.text.lower()
    assert "hit" in lower
    assert result_gloss in lower
    assert "stone" in lower


# --- fake planner free-text detection --------------------------------------------------------


def _serial_language_with(result_gloss: str):
    return _find(lambda l: l.grammar.has_serial_verbs and result_gloss in l.grammar.serial_result_verbs)


def test_the_fake_planner_detects_the_fixed_svc_shape():
    language = _serial_language_with("break")
    plan = sentence_planner.plan_sentence("I hit it break", language, _CLIENT)
    kinds_and_glosses = [(s.pos, s.gloss, s.serial_result) for s in plan.slots]
    verb_slots = [s for s in plan.slots if s.pos == "verb"]
    assert len(verb_slots) == 2
    assert verb_slots[0].gloss == "hit" and verb_slots[0].serial_result is False
    assert verb_slots[1].gloss == "break" and verb_slots[1].serial_result is True
    assert any(s.pos == "pronoun" and s.gloss == "i" for s in plan.slots)


def test_a_language_without_serial_verbs_does_not_trigger_the_shape():
    language = _find(lambda l: not l.grammar.has_serial_verbs)
    plan = sentence_planner.plan_sentence("I hit it break", language, _CLIENT)
    assert not any(s.serial_result for s in plan.slots)


def test_the_result_word_must_really_be_in_this_languages_own_pool():
    # "break" only triggers the shape when THIS language's own rolled pool actually contains it --
    # a different, un-pooled result-looking word falls through to the ordinary general case.
    language = _find(lambda l: l.grammar.has_serial_verbs and "break" not in l.grammar.serial_result_verbs)
    plan = sentence_planner.plan_sentence("I hit it break", language, _CLIENT)
    assert not any(s.serial_result for s in plan.slots)


def test_translate_to_conlang_round_trips_a_real_serial_verb_sentence():
    language = _serial_language_with("break")
    result = translate_to_conlang("I hit it break", language, _CLIENT)
    assert result.coined == ()  # every word already exists in the core lexicon
    decoded = translate_to_english(result.text, result.language, _CLIENT)
    assert "hit" in decoded.text.lower() and "break" in decoded.text.lower()
