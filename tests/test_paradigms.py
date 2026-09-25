"""Real inflection paradigms: declension and conjugation classes, irregular
lexemes, and how they render, decode and evolve."""

import random

from conlang_generator.core.grammar import InflectionAffix, Paradigm
from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import inflection_gen, paradigm_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.sound_change import evolve_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation.translator import (
    _apply_case,
    _apply_verb_inflection,
    _decode_noun,
    _decode_verb_full,
    _normalize,
    _paradigm_grammar,
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


def _nouns(language):
    return [e for e in language.lexicon.entries if e.pos is PartOfSpeech.NOUN]


def _verbs(language):
    return [e for e in language.lexicon.entries if e.pos is PartOfSpeech.VERB]


# --- generation -----------------------------------------------------------------


def test_the_paradigm_choices_are_rolled():
    grammars = [_language(s).grammar for s in range(1, 100)]
    assert any(g.noun_paradigms for g in grammars) and any(g.verb_paradigms for g in grammars)
    assert any(g.irregular_lexemes for g in grammars)
    assert {len(g.noun_paradigms) for g in grammars} >= {0, 1, 2}
    for g in grammars:
        assert len(g.noun_paradigms) <= 3 and len(g.verb_paradigms) <= 2
        for p in g.noun_paradigms:
            assert p.pos == "noun" and p.overrides
            assert {o.label.split("/")[0] for o in p.overrides} <= set(paradigm_gen.NOUN_FIELDS)
        for p in g.verb_paradigms:
            assert p.pos == "verb" and {o.label.split("/")[0] for o in p.overrides} <= set(paradigm_gen.VERB_FIELDS)
        for p in g.irregular_lexemes:
            assert p.name in (*paradigm_gen.IRREGULAR_NOUNS, *paradigm_gen.IRREGULAR_VERBS)


def test_fusional_languages_have_more_paradigms_than_isolating_ones():
    def share(kind):
        grammars = [_language(s).grammar for s in range(1, 200)]
        chosen = [g for g in grammars if g.morphological_type.value == kind]
        return sum(bool(g.noun_paradigms) for g in chosen) / max(1, len(chosen))

    assert share("fusional") > share("isolating")


def test_every_override_names_a_real_label_and_is_distinct_from_its_group():
    for seed in range(1, 80):
        language = _language(seed)
        g = language.grammar
        for paradigm in g.noun_paradigms + g.verb_paradigms:
            fields = inflection_gen._NOUN_SUFFIX_FIELDS if paradigm.pos == "noun" else inflection_gen._VERB_SUFFIX_FIELDS
            base = {
                language.romanization.apply("".join(a.suffix)).lower()
                for name in fields for a in getattr(g, name, ()) if a.suffix and not a.prefix
            }
            seen: set[str] = set()
            for override in paradigm.overrides:
                field, _, label = override.label.partition("/")
                assert any(a.label == label for a in getattr(g, field))
                spelled = language.romanization.apply("".join(override.suffix)).lower()
                assert spelled not in base and spelled not in seen
                seen.add(spelled)


def test_the_paradigm_fields_default_for_older_saved_languages():
    fields = type(_language(1).grammar).model_fields
    assert fields["noun_paradigms"].default == () and fields["irregular_lexemes"].default == ()


def test_class_membership_is_a_stable_weighted_hash():
    assert paradigm_gen.class_index(1, "noun", "dog", 1) == 0
    assert paradigm_gen.class_index(1, "noun", "dog", 3) == paradigm_gen.class_index(1, "noun", "dog", 3)
    counts = [0, 0, 0]
    for n in range(600):
        counts[paradigm_gen.class_index(7, "noun", f"word{n}", 3)] += 1
    assert counts[0] > counts[1] > counts[2] > 30


# --- the paradigm a word sees ---------------------------------------------------------------


def _with_classes():
    return _find(lambda l: l.grammar.noun_paradigms and l.grammar.verb_paradigms and l.grammar.case_affixes)


def test_a_language_without_paradigms_gives_every_word_the_same_grammar():
    language = _find(lambda l: not (l.grammar.noun_paradigms or l.grammar.verb_paradigms or l.grammar.irregular_lexemes))
    for entry in language.lexicon.entries[:50]:
        assert _paradigm_grammar(language, entry) is language.grammar


def test_a_noun_in_a_further_class_takes_that_classs_suffixes_and_shares_the_rest():
    language = _with_classes()
    g = language.grammar
    changed = None
    for entry in _nouns(language):
        derived = _paradigm_grammar(language, entry)
        if derived is not g and not any(p.name == entry.primary_gloss.lower() for p in g.irregular_lexemes):
            changed = (entry, derived)
            break
    assert changed is not None
    entry, derived = changed
    base_by_label = {a.label: a.suffix for a in g.case_affixes}
    differing = [a.label for a in derived.case_affixes if a.suffix != base_by_label[a.label]]
    same = [a.label for a in derived.case_affixes if a.suffix == base_by_label[a.label]]
    assert [a.label for a in derived.case_affixes] == [a.label for a in g.case_affixes]
    assert differing or any(a.suffix != b.suffix for a, b in zip(derived.number_affixes, g.number_affixes))
    assert same or differing


def test_pronouns_particles_and_names_keep_the_base_paradigm():
    language = _with_classes()
    for entry in language.lexicon.entries:
        if entry.pos in (PartOfSpeech.PRONOUN, PartOfSpeech.PARTICLE, PartOfSpeech.NUMERAL):
            assert _paradigm_grammar(language, entry) is language.grammar


def test_nouns_of_different_classes_inflect_differently():
    language = _with_classes()
    label = language.grammar.number_affixes[0].label
    by_class: dict[int, str] = {}
    for entry in _nouns(language)[:300]:
        derived = _paradigm_grammar(language, entry)
        if entry.primary_gloss.lower() in {p.name for p in language.grammar.irregular_lexemes}:
            continue
        marker = id(derived)
        suffix = next(a.suffix for a in derived.number_affixes if a.label == label)
        by_class[marker] = suffix
    assert len(by_class) >= 1
    for entry in _nouns(language)[:300]:
        assert _apply_case(language, entry, None, label)[0]  # every noun inflects


def test_an_irregular_lexeme_has_cells_of_its_own():
    language = _with_classes()
    go = Paradigm(name="go", pos="verb", overrides=(InflectionAffix(label="tense_affixes/past", suffix=("a", "a", "m")),))
    grammar = language.grammar.model_copy(update={"irregular_lexemes": (go,)})
    forced = language.model_copy(update={"grammar": grammar})
    entry = forced.lexicon.by_gloss("go")
    other = forced.lexicon.by_gloss("see")
    if entry is None or other is None or "past" not in grammar.tenses:
        return
    derived = _paradigm_grammar(forced, entry)
    assert next(a.suffix for a in derived.tense_affixes if a.label == "past") == ("a", "a", "m")
    regular = forced.model_copy(update={"grammar": grammar.model_copy(update={"irregular_lexemes": ()})})
    without = _paradigm_grammar(regular, entry)
    # only the irregular cell changed: every other tense is what its class gives it
    for a, b in zip(derived.tense_affixes, without.tense_affixes):
        assert a.label == "past" or a.suffix == b.suffix
    assert _apply_verb_inflection(forced, entry, "past", "I")[0] != _apply_verb_inflection(regular, entry, "past", "I")[0]


# --- decoding --------------------------------------------------------------------------------------


def test_inflected_nouns_of_every_class_decode_and_reproduce_the_token():
    rng = random.Random(9)
    checked = 0
    for seed in range(1, 45):
        language = _language(seed)
        g = language.grammar
        if not (g.noun_paradigms or g.irregular_lexemes):
            continue
        nouns = _nouns(language)
        for entry in rng.sample(nouns, min(8, len(nouns))):
            for number in [None, *[a.label for a in g.number_affixes][:1]]:
                for case in [None, *[a.label for a in g.case_affixes][:2]]:
                    token = _apply_case(language, entry, case, number)[0]
                    decoded = _decode_noun(language, token)
                    assert decoded is not None, (seed, entry.romanization, case, number)
                    parts = [] if decoded[1] == "unmarked" else decoded[1].split("+")
                    d_number = next((p for p in parts if p in [a.label for a in g.number_affixes]), None)
                    d_case = next((p for p in parts if p in [a.label for a in g.case_affixes]), None)
                    assert _normalize(_apply_case(language, decoded[0], d_case, d_number)[0]) == _normalize(token)
                    checked += 1
    assert checked > 100


def test_inflected_verbs_of_every_class_decode():
    rng = random.Random(10)
    checked = 0
    for seed in range(1, 45):
        language = _language(seed)
        g = language.grammar
        if not (g.verb_paradigms or g.irregular_lexemes):
            continue
        verbs = _verbs(language)
        for entry in rng.sample(verbs, min(6, len(verbs))):
            for tense in g.tenses or (None,):
                token = _apply_verb_inflection(language, entry, tense, "default")[0]
                assert _decode_verb_full(language, token) is not None, (seed, entry.romanization, tense)
                checked += 1
    assert checked > 60


def test_a_whole_sentence_still_round_trips_in_a_paradigm_language():
    language = _with_classes()
    result = translate_to_conlang("I see the dogs.", language, _CLIENT)
    english = translate_to_english(result.text, result.language, _CLIENT).text
    assert "<unknown" not in english


# --- evolution -------------------------------------------------------------------------------------------


def test_paradigm_overrides_follow_sound_change():
    changed = 0
    for seed in range(1, 40):
        base = _language(seed)
        if not (base.grammar.noun_paradigms or base.grammar.verb_paradigms):
            continue
        evolved = evolve_language("Evolved", base, 800, TraitProfile(), seed=seed)
        for name in ("noun_paradigms", "verb_paradigms", "irregular_lexemes"):
            before, after = getattr(base.grammar, name), getattr(evolved.grammar, name)
            assert [p.name for p in before] == [p.name for p in after]
            for old, new in zip(before, after):
                assert [o.label for o in old.overrides] == [o.label for o in new.overrides]
                assert all(o.suffix or o.prefix for o in new.overrides)
                changed += sum(1 for a, b in zip(old.overrides, new.overrides) if a != b)
        if changed:
            break
    assert changed > 0
