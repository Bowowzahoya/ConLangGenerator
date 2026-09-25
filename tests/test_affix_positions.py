"""Affix positions: prefix, circumfix and infix inflection, alongside the default suffix."""

import random
import time

from conlang_generator.core.grammar import InflectionAffix
from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import affix_position_gen, inflection_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.sound_change import evolve_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation.translator import (
    _apply_case,
    _apply_verb_inflection,
    _decode_mode,
    _decode_noun,
    _decode_verb_full,
    _normalize,
    _person_suffix_is_distinct,
    translate_to_conlang,
    translate_to_english,
)

_CLIENT = FakeLLMClient()
_CACHE: dict[int, object] = {}


def _language(seed: int):
    if seed not in _CACHE:
        _CACHE[seed] = generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())
    return _CACHE[seed]


def _mixed(limit: int = 200):
    for seed in range(1, limit):
        language = _language(seed)
        if language.grammar.affix_positions:
            yield language


def _of(language, pos):
    return [e for e in language.lexicon.entries if e.pos is pos]


# --- generation -----------------------------------------------------------------


def test_most_languages_stay_suffixing_and_the_rest_mix_positions():
    grammars = [_language(s).grammar for s in range(1, 100)]
    mixed = [g for g in grammars if g.affix_positions]
    assert 0.15 < len(mixed) / len(grammars) < 0.6
    positions = {p for g in mixed for _, p in g.affix_positions}
    assert positions == {"prefix", "circumfix", "infix"}
    assert all(not g.affix_positions for g in grammars if not g.affix_positions)


def test_each_field_carries_the_exponent_its_position_names():
    for language in _mixed(120):
        g = language.grammar
        for field, position in g.affix_positions:
            assert field in affix_position_gen.NOUN_FIELDS + affix_position_gen.VERB_FIELDS
            for affix in getattr(g, field):
                if not (affix.prefix or affix.suffix or affix.infix):
                    continue
                if position == "prefix":
                    assert affix.prefix and not affix.suffix and not affix.infix
                elif position == "circumfix":
                    assert affix.prefix and affix.suffix and not affix.infix
                else:
                    assert affix.infix and not affix.prefix and not affix.suffix
                    assert affix.infix_at in affix_position_gen.INFIX_PLACES


def test_the_paradigms_keep_their_shape_when_positions_change():
    checked = 0
    for language in _mixed(150):
        g = language.grammar
        positions = dict(g.affix_positions)
        for paradigm in g.noun_paradigms + g.verb_paradigms + g.irregular_lexemes:
            for override in paradigm.overrides:
                field = override.label.partition("/")[0]
                if field in positions:
                    assert (override.prefix or override.infix) and (positions[field] != "prefix" or not override.suffix)
                    checked += 1
        for field, _ in g.affix_positions:
            exponents = [(a.prefix, a.infix, a.suffix) for a in getattr(g, field)]
            assert all(e != ((), (), ()) for e in exponents if e)
    assert checked > 0


def test_labels_of_a_field_stay_distinct_after_the_conversion():
    for language in _mixed(120):
        g = language.grammar
        for field, _ in g.affix_positions:
            keys = [(a.prefix, a.infix, a.suffix) for a in getattr(g, field)]
            assert len(keys) == len(set(keys)) or len(keys) < 2


def test_the_new_grammar_fields_default_for_older_saved_languages():
    assert InflectionAffix(label="x").infix == () and InflectionAffix(label="x").infix_at == ""
    assert type(_language(1).grammar).model_fields["affix_positions"].default == ()


# --- applying an affix ----------------------------------------------------------------------


def test_a_prefix_a_circumfix_and_an_infix_attach_where_they_should():
    language = _language(2)
    inventory = language.phonology
    kwargs = dict(stress_pattern="initial", stress_deviation_rate=0.0, stress_strictness=1.0)
    consonants = [c for c in inventory.consonant_symbols() if len(c) == 1][:3]
    vowels = [v for v in inventory.vowel_symbols() if len(v) == 1][:3]
    stem = consonants[0] + vowels[0] + consonants[1] + vowels[1]
    rng = lambda: random.Random(1)  # noqa: E731
    prefix = inflection_gen.apply_affix(rng(), InflectionAffix(label="p", prefix=(consonants[2], vowels[2])), stem, inventory, **kwargs)
    assert prefix.replace("ˈ", "").startswith(consonants[2] + vowels[2] + stem)
    circumfix = inflection_gen.apply_affix(
        rng(), InflectionAffix(label="c", prefix=(consonants[2], vowels[2]), suffix=(vowels[2],)), stem, inventory, **kwargs
    )
    assert circumfix.replace("ˈ", "").startswith(consonants[2] + vowels[2]) and circumfix.replace("ˈ", "").endswith(stem + vowels[2])
    after_first = inflection_gen.apply_affix(
        rng(), InflectionAffix(label="i", infix=(vowels[2], consonants[2]), infix_at="after_first_consonant"), stem, inventory, **kwargs
    )
    assert after_first.replace("ˈ", "") == consonants[0] + vowels[2] + consonants[2] + vowels[0] + consonants[1] + vowels[1]
    before_last = inflection_gen.apply_affix(
        rng(), InflectionAffix(label="i", infix=(consonants[2],), infix_at="before_last_vowel"), stem, inventory, **kwargs
    )
    assert before_last.replace("ˈ", "") == consonants[0] + vowels[0] + consonants[1] + consonants[2] + vowels[1]


def test_a_vowel_initial_stem_takes_an_infix_at_its_start():
    language = _language(2)
    inventory = language.phonology
    vowels = [v for v in inventory.vowel_symbols() if len(v) == 1][:3]
    consonant = next(c for c in inventory.consonant_symbols() if len(c) == 1)
    stem = vowels[0] + consonant
    out = inflection_gen.apply_affix(
        random.Random(1), InflectionAffix(label="i", infix=(vowels[1],), infix_at="after_first_consonant"), stem,
        inventory, "initial", 0.0, 1.0,
    )
    assert out.replace("ˈ", "").startswith(vowels[1] + vowels[0])


# --- rendering and decoding ---------------------------------------------------------------------


def test_inflected_nouns_decode_in_every_position_and_reproduce_their_token():
    rng = random.Random(3)
    checked = 0
    seen_positions = set()
    for language in _mixed(150):
        g = language.grammar
        noun_positions = {p for f, p in g.affix_positions if f in affix_position_gen.NOUN_FIELDS}
        if not noun_positions:
            continue
        nouns = _of(language, PartOfSpeech.NOUN)
        for entry in rng.sample(nouns, min(6, len(nouns))):
            for number in [None, *[a.label for a in g.number_affixes][:1]]:
                for case in [None, *[a.label for a in g.case_affixes][:2]]:
                    token = _apply_case(language, entry, case, number)[0]
                    decoded = _decode_noun(language, token)
                    assert decoded is not None, (entry.romanization, case, number, token)
                    parts = [] if decoded[1] == "unmarked" else decoded[1].split("+")
                    d_number = next((p for p in parts if p in [a.label for a in g.number_affixes]), None)
                    d_case = next((p for p in parts if p in [a.label for a in g.case_affixes]), None)
                    assert _normalize(_apply_case(language, decoded[0], d_case, d_number)[0]) == _normalize(token)
                    checked += 1
        seen_positions |= noun_positions
        if checked > 120 and len(seen_positions) >= 3:
            break
    assert checked > 60 and seen_positions >= {"prefix", "infix"}


def test_inflected_verbs_decode_in_every_position():
    rng = random.Random(4)
    checked = 0
    seen = set()
    for language in _mixed(150):
        g = language.grammar
        verb_positions = {p for f, p in g.affix_positions if f in affix_position_gen.VERB_FIELDS}
        if not verb_positions:
            continue
        verbs = _of(language, PartOfSpeech.VERB)
        for entry in rng.sample(verbs, min(4, len(verbs))):
            for tense in g.tenses or (None,):
                token = _apply_verb_inflection(language, entry, tense, "default")[0]
                assert _decode_verb_full(language, token) is not None, (entry.romanization, tense, token)
                checked += 1
        seen |= verb_positions
        if checked > 60 and len(seen) >= 3:
            break
    assert checked > 30 and seen >= {"prefix"}


def test_a_whole_sentence_round_trips_in_a_mixed_language():
    for language in _mixed(60):
        result = translate_to_conlang("I see the dogs.", language, _CLIENT)
        english = translate_to_english(result.text, result.language, _CLIENT).text
        assert "<unknown" not in english, (result.text, english)
        return
    raise AssertionError("no mixed language")


def test_the_decode_mode_follows_the_positions():
    plain = next(l for l in (_language(s) for s in range(1, 30)) if not l.grammar.affix_positions and not any(
        a.prefix for name in inflection_gen._NOUN_SUFFIX_FIELDS for a in getattr(l.grammar, name)
    ))
    assert _decode_mode(plain, inflection_gen._NOUN_SUFFIX_FIELDS) == "start"
    modes = {
        _decode_mode(l, inflection_gen._VERB_SUFFIX_FIELDS) for l in _mixed(120)
    }
    assert "contains" in modes and any(m.startswith("all") for m in modes)


def test_persons_marked_by_prefix_still_count_as_distinct():
    for language in _mixed(120):
        g = language.grammar
        if dict(g.affix_positions).get("agreement_affixes") in ("prefix", "infix", "circumfix"):
            assert all(_person_suffix_is_distinct(g, label) for label in ("I", "you", "he", "we"))
            return
    raise AssertionError("no language with prefixed agreement")


def test_an_unknown_token_is_still_rejected_quickly_in_mixed_languages():
    slowest = 0.0
    count = 0
    for language in _mixed(80):
        start = time.perf_counter()
        assert _decode_noun(language, "zzqxkv") is None
        _decode_verb_full(language, "zzqxkv")
        slowest = max(slowest, time.perf_counter() - start)
        count += 1
        if count >= 12:
            break
    assert slowest < 10.0


# --- evolution ----------------------------------------------------------------------------------------


def test_prefixes_and_infixes_follow_sound_change():
    changed = 0
    for language in _mixed(80):
        evolved = evolve_language("Evolved", language, 800, TraitProfile(), seed=3)
        for field, _ in language.grammar.affix_positions:
            before, after = getattr(language.grammar, field), getattr(evolved.grammar, field)
            assert [a.label for a in before] == [a.label for a in after]
            for a, b in zip(before, after):
                assert (b.prefix or b.suffix or b.infix) or not (a.prefix or a.suffix or a.infix)
                changed += (a.prefix, a.infix) != (b.prefix, b.infix)
        if changed:
            break
    assert changed > 0
