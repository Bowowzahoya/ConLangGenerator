"""Paradigm follow-ups: more cells, patterned syncretism, stem changes (umlaut,
ablaut, gradation), adjective classes and per-conjugation pro-drop."""

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import paradigm_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.sound_change import evolve_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation.translator import (
    _apply_case,
    _apply_class_agreement,
    _apply_verb_inflection,
    _decode_noun,
    _decode_verb_full,
    _entry_paradigms,
    _paradigm_grammar,
    _person_suffix_is_distinct,
    _stem_ipa,
)

_CACHE: dict[int, object] = {}


def _language(seed: int):
    if seed not in _CACHE:
        _CACHE[seed] = generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())
    return _CACHE[seed]


def _of(language, pos: PartOfSpeech):
    return [e for e in language.lexicon.entries if e.pos is pos]


def test_paradigms_cover_aspect_mood_voice_possession_and_degree_cells():
    fields = set()
    for seed in range(1, 150):
        g = _language(seed).grammar
        for p in g.noun_paradigms + g.verb_paradigms + g.adjective_paradigms:
            fields |= {o.label.split("/")[0] for o in p.overrides}
    assert {"aspect_affixes", "mood_affixes", "voice_affixes", "possession_affixes", "degree_affixes"} <= fields


def test_a_class_can_spell_two_cells_alike_on_purpose():
    for seed in range(1, 100):
        g = _language(seed).grammar
        for paradigm in g.noun_paradigms + g.verb_paradigms:
            for cell in paradigm.syncretisms:
                target, source = cell.split("=")
                suffixes = {o.label: o.suffix for o in paradigm.overrides}
                assert target in suffixes
                if source in suffixes:
                    assert suffixes[target] == suffixes[source]
                else:
                    field, _, label = source.partition("/")
                    assert suffixes[target] == next(a.suffix for a in getattr(g, field) if a.label == label)
                return
    raise AssertionError("no syncretism found")


def test_stem_maps_only_use_symbols_the_inventory_has():
    for seed in range(1, 60):
        language = _language(seed)
        vowels = set(language.phonology.vowel_symbols())
        consonants = set(language.phonology.consonant_symbols())
        for kind, pairs in paradigm_gen.build_stem_maps(language.phonology):
            for a, b in pairs:
                allowed = consonants if kind == "gradation" else vowels
                assert a in allowed and b in allowed and a != b


def test_change_stem_replaces_the_last_vowel_or_the_final_consonant():
    known = tuple("aeioukgtdpb")
    vowels = frozenset("aeiou")
    assert paradigm_gen.change_stem("kato", {"a": "e", "o": "u"}, vowels, known, False) == "katu"
    assert paradigm_gen.change_stem("kat", {"a": "e"}, vowels, known, False) == "ket"
    assert paradigm_gen.change_stem("kat", {"t": "d"}, vowels, known, True) == "kad"
    assert paradigm_gen.change_stem("kata", {"t": "d"}, vowels, known, True) == "kata"  # ends in a vowel
    assert paradigm_gen.change_stem("kit", {"a": "e"}, vowels, known, False) == "kit"  # nothing to map


def test_a_noun_class_changes_its_stem_only_in_the_triggering_cells():
    for seed in range(1, 150):
        language = _language(seed)
        for entry in _of(language, PartOfSpeech.NOUN):
            for paradigm in _entry_paradigms(language, entry):
                if paradigm.pos == "noun" and paradigm.stem_change:
                    changed = _stem_ipa(language, entry, paradigm.stem_cells)
                    assert _stem_ipa(language, entry, ["case_affixes/none"]) == entry.ipa
                    if changed != entry.ipa:
                        return
    raise AssertionError("no noun changed its stem")


def test_a_stem_changed_noun_decodes_and_reproduces_its_token():
    checked = 0
    for seed in range(1, 150):
        language = _language(seed)
        for entry in _of(language, PartOfSpeech.NOUN)[:200]:
            for paradigm in _entry_paradigms(language, entry):
                if paradigm.pos != "noun" or not paradigm.stem_change:
                    continue
                if _stem_ipa(language, entry, paradigm.stem_cells) == entry.ipa:
                    continue
                field, _, label = paradigm.stem_cells[0].partition("/")
                token = _apply_case(
                    language, entry, label if field == "case_affixes" else None,
                    label if field == "number_affixes" else None,
                )[0]
                assert _decode_noun(language, token) is not None, (seed, entry.romanization, paradigm.stem_cells)
                checked += 1
        if checked >= 6:
            return
    assert checked > 0


def test_a_stem_changed_verb_decodes():
    checked = 0
    for seed in range(1, 150):
        language = _language(seed)
        for entry in _of(language, PartOfSpeech.VERB)[:150]:
            for paradigm in _entry_paradigms(language, entry):
                if paradigm.pos != "verb" or not paradigm.stem_change or not paradigm.stem_cells:
                    continue
                if _stem_ipa(language, entry, paradigm.stem_cells) == entry.ipa:
                    continue
                tense = paradigm.stem_cells[0].split("/")[1]
                token = _apply_verb_inflection(language, entry, tense, "default")[0]
                assert _decode_verb_full(language, token) is not None, (seed, entry.romanization, tense)
                checked += 1
        if checked >= 5:
            return
    assert checked > 0


def test_a_strong_verb_can_be_irregular():
    for seed in range(1, 200):
        g = _language(seed).grammar
        if any(p.pos == "verb" and p.stem_change for p in g.irregular_lexemes):
            return
    raise AssertionError("no strong irregular verb")


def test_an_adjective_class_changes_degree_or_agreement_suffixes():
    for seed in range(1, 150):
        language = _language(seed)
        g = language.grammar
        if not (g.adjective_paradigms and g.degree_affixes):
            continue
        base = tuple(a.suffix for a in g.degree_affixes) + tuple(a.suffix for a in g.class_affixes)
        for entry in _of(language, PartOfSpeech.ADJECTIVE):
            derived = _paradigm_grammar(language, entry)
            if derived is not g and tuple(a.suffix for a in derived.degree_affixes) + tuple(
                a.suffix for a in derived.class_affixes
            ) != base:
                assert _apply_class_agreement(language, entry, None, g.degree_affixes[0].label)[0]
                return
    raise AssertionError("no adjective class found")


def test_pro_drop_checks_the_verbs_own_conjugation():
    for seed in range(1, 200):
        language = _language(seed)
        g = language.grammar
        if not any(cell.startswith("agreement_affixes") for p in g.verb_paradigms for cell in p.syncretisms):
            continue
        for entry in _of(language, PartOfSpeech.VERB):
            derived = _paradigm_grammar(language, entry)
            if derived is g:
                continue
            for label in ("I", "you", "he", "we"):
                if _person_suffix_is_distinct(g, label) and not _person_suffix_is_distinct(derived, label):
                    return
    raise AssertionError("no conjugation with a syncretic person found")


def test_stem_maps_evolve_with_the_language():
    for seed in range(1, 60):
        base = _language(seed)
        if not base.grammar.stem_maps:
            continue
        evolved = evolve_language("Evolved", base, 500, TraitProfile(), seed=seed)
        assert [k for k, _ in evolved.grammar.stem_maps] == [k for k, _ in base.grammar.stem_maps]
        return
    raise AssertionError("no language with stem maps")
