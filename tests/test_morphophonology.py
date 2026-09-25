"""Morphophonology at affix boundaries: vowel harmony, hiatus resolution and mutation."""

import random
import time

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import inflection_gen, morphophonology_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.morphophonology_gen import Morphophonology
from conlang_generator.generation.sound_change import evolve_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation.translator import (
    _apply_case,
    _apply_verb_inflection,
    _decode_noun,
    _decode_verb_full,
    _normalize,
    _stem_ipa,
    _stem_prefixes,
)

_CACHE: dict[int, object] = {}


def _language(seed: int):
    if seed not in _CACHE:
        _CACHE[seed] = generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())
    return _CACHE[seed]


def _with(language, **updates):
    return language.model_copy(update={"grammar": language.grammar.model_copy(update=updates)})


def _of(language, pos):
    return [e for e in language.lexicon.entries if e.pos is pos]


def _find(predicate, limit: int = 300):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language):
            return language
    raise AssertionError("no seed found")


# --- generation -----------------------------------------------------------------


def test_the_morphophonology_choices_are_rolled():
    grammars = [_language(s).grammar for s in range(1, 120)]
    assert {g.harmony for g in grammars} >= {"none", "backness"}
    assert {g.boundary_rule for g in grammars} == {"none", "elision", "glide"}
    assert any(g.mutation_cells for g in grammars)
    for g in grammars:
        assert (g.harmony != "none") == bool(g.harmony_pairs)
        assert (g.boundary_rule == "glide") == bool(g.boundary_glide)
        assert bool(g.mutation_cells) == bool(g.mutation_pairs)


def test_harmony_pairs_use_the_inventorys_own_vowels_and_no_vowel_twice():
    for seed in range(1, 80):
        language = _language(seed)
        g = language.grammar
        if not g.harmony_pairs:
            continue
        vowels = set(language.phonology.vowel_symbols())
        flat = [v for pair in g.harmony_pairs for v in pair]
        assert set(flat) <= vowels and len(flat) == len(set(flat)) and len(g.harmony_pairs) >= 2


def test_mutation_pairs_are_lenitions_the_inventory_has():
    for seed in range(1, 80):
        language = _language(seed)
        consonants = set(language.phonology.consonant_symbols())
        for a, b in language.grammar.mutation_pairs:
            assert a in consonants and b in consonants and a != b
        for cell in language.grammar.mutation_cells:
            field, _, label = cell.partition("/")
            assert any(x.label == label for x in getattr(language.grammar, field))


def test_the_new_grammar_fields_default_for_older_saved_languages():
    fields = type(_language(1).grammar).model_fields
    assert fields["harmony"].default == "none" and fields["boundary_rule"].default == "none"
    assert fields["mutation_cells"].default == () and fields["harmony_pairs"].default == ()


# --- the boundary rules -----------------------------------------------------------------------


def _rules(boundary="none", glide="j"):
    return Morphophonology(
        classes={"i": (0, "u"), "u": (1, "i"), "e": (0, "o"), "o": (1, "e")},
        boundary=boundary, glide=glide, vowels=frozenset("aiueo"),
    )


def test_a_suffix_vowel_takes_the_class_of_the_stems_last_vowel():
    rules = _rules()
    assert rules.apply((), tuple("kutu"), tuple("in"))[2] == tuple("un")  # back stem: i -> u
    assert rules.apply((), tuple("kiti"), tuple("un"))[2] == tuple("in")  # front stem: u -> i
    assert rules.apply((), tuple("kita"), tuple("un"))[2] == tuple("in")  # 'a' is neutral: the last class vowel counts
    assert rules.apply((), tuple("kta"), tuple("un"))[2] == tuple("un")  # no class vowel: unchanged


def test_a_prefix_vowel_takes_the_class_of_the_stems_first_vowel():
    rules = _rules()
    assert rules.apply(tuple("ki"), tuple("tumi"), ())[0] == tuple("ku")
    assert rules.apply(tuple("ku"), tuple("timu"), ())[0] == tuple("ki")


def test_elision_drops_the_vowel_that_meets_another_vowel():
    rules = _rules("elision")
    assert rules.apply((), tuple("kata"), tuple("in"))[1:] == (tuple("kat"), tuple("in"))
    assert rules.apply((), tuple("kat"), tuple("in"))[1:] == (tuple("kat"), tuple("in"))  # no clash
    assert rules.apply(tuple("ka"), tuple("ita"), ())[:2] == (tuple("k"), tuple("ita"))


def test_a_glide_is_put_between_two_vowels():
    rules = _rules("glide", "j")
    assert rules.apply((), tuple("kata"), tuple("in"))[1:] == (tuple("kata"), tuple("jin"))
    assert rules.apply(tuple("ka"), tuple("ita"), ())[0] == tuple("kaj")


def test_decorated_vowels_count_as_vowels():
    rules = _rules("elision")
    assert rules.apply((), ("k", "á"), tuple("in"))[1] == ("k",)


def test_mutation_changes_only_the_initial_consonant():
    known = tuple("aeioukgtdpbzs")
    vowels = frozenset("aeiou")
    mapping = {"p": "b", "t": "d", "k": "g"}
    assert morphophonology_gen.mutate_initial("kata", mapping, known, vowels) == "gata"
    assert morphophonology_gen.mutate_initial("ˈkata", mapping, known, vowels) == "ˈgata"
    assert morphophonology_gen.mutate_initial("ata", mapping, known, vowels) == "ata"
    assert morphophonology_gen.mutate_initial("sata", mapping, known, vowels) == "sata"


# --- rendering ---------------------------------------------------------------------------------------


def _harmony_language():
    return _find(lambda l: l.grammar.harmony != "none" and not l.grammar.affix_positions)


def test_a_harmonic_suffix_agrees_with_stems_of_different_classes():
    language = _harmony_language()
    g = language.grammar
    vowels = {v for pair in g.harmony_pairs for v in pair}
    forms: set = set()
    for entry in _of(language, PartOfSpeech.NOUN)[:400]:
        label = g.number_affixes[0].label if g.number_affixes else None
        if label is None:
            break
        ipa = _apply_case(language, entry, None, label)[1].replace("ˈ", "")
        stem = entry.ipa.replace("ˈ", "")
        forms.add(ipa[len(stem):] if ipa.startswith(stem) else ipa)
    assert len(forms) >= 2 or not vowels  # the same suffix appears in more than one vowel shape


def test_a_language_without_the_rules_renders_as_before():
    language = _find(lambda l: l.grammar.harmony == "none" and l.grammar.boundary_rule == "none")
    assert morphophonology_gen.build_rules(language.grammar, language.phonology) is None


def test_mutation_applies_only_in_its_cells():
    language = _find(lambda l: l.grammar.mutation_cells)
    g = language.grammar
    cell = g.mutation_cells[0]
    mapping = dict(g.mutation_pairs)
    changed = 0
    for entry in _of(language, PartOfSpeech.NOUN) + _of(language, PartOfSpeech.VERB):
        assert _stem_ipa(language, entry, ["case_affixes/none"]) == entry.ipa
        mutated = _stem_ipa(language, entry, [cell])
        if mutated != entry.ipa:
            changed += 1
            assert any(mutated.replace("ˈ", "").startswith(v) for v in mapping.values())
    assert changed > 0


def test_a_mutated_stems_new_initial_is_a_possible_start():
    language = _find(lambda l: l.grammar.mutation_cells)
    g = language.grammar
    for entry in _of(language, PartOfSpeech.NOUN):
        mutated = _stem_ipa(language, entry, g.mutation_cells)
        if mutated != entry.ipa:
            from conlang_generator.core.romanization import apply_grammatical_spelling
            from conlang_generator.translation.translator import _stem_prefix

            spelled = apply_grammatical_spelling(language.romanization, language.romanization.apply(mutated), entry.pos)
            assert _stem_prefix(spelled) in _stem_prefixes(language, entry)
            return
    raise AssertionError("no mutating noun")


# --- decoding -----------------------------------------------------------------------------------------


def _decode_sweep(predicate, seeds=range(1, 150), want=40):
    rng = random.Random(5)
    checked = 0
    for seed in seeds:
        language = _language(seed)
        if not predicate(language.grammar):
            continue
        g = language.grammar
        nouns = _of(language, PartOfSpeech.NOUN)
        for entry in rng.sample(nouns, min(6, len(nouns))):
            for number in [None, *[a.label for a in g.number_affixes][:1]]:
                for case in [None, *[a.label for a in g.case_affixes][:2]]:
                    token = _apply_case(language, entry, case, number)[0]
                    decoded = _decode_noun(language, token)
                    assert decoded is not None, (seed, entry.romanization, case, number, token)
                    parts = [] if decoded[1] == "unmarked" else decoded[1].split("+")
                    d_number = next((p for p in parts if p in [a.label for a in g.number_affixes]), None)
                    d_case = next((p for p in parts if p in [a.label for a in g.case_affixes]), None)
                    assert _normalize(_apply_case(language, decoded[0], d_case, d_number)[0]) == _normalize(token)
                    checked += 1
        verbs = _of(language, PartOfSpeech.VERB)
        for entry in rng.sample(verbs, min(4, len(verbs))):
            for tense in g.tenses or (None,):
                token = _apply_verb_inflection(language, entry, tense, "default")[0]
                assert _decode_verb_full(language, token) is not None, (seed, entry.romanization, tense, token)
                checked += 1
        if checked >= want:
            break
    return checked


def test_forms_decode_in_harmonic_languages():
    assert _decode_sweep(lambda g: g.harmony != "none") > 20


def test_forms_decode_where_a_vowel_is_elided_or_a_glide_inserted():
    assert _decode_sweep(lambda g: g.boundary_rule == "elision") > 20
    assert _decode_sweep(lambda g: g.boundary_rule == "glide") > 20


def test_forms_decode_where_the_initial_consonant_mutates():
    assert _decode_sweep(lambda g: bool(g.mutation_cells)) > 20


def test_unknown_tokens_are_still_rejected_quickly():
    slowest = 0.0
    count = 0
    for seed in range(1, 150):
        language = _language(seed)
        g = language.grammar
        if g.harmony == "none" and g.boundary_rule == "none" and not g.mutation_cells:
            continue
        start = time.perf_counter()
        assert _decode_noun(language, "zzqxkv") is None
        _decode_verb_full(language, "zzqxkv")
        slowest = max(slowest, time.perf_counter() - start)
        count += 1
        if count >= 12:
            break
    assert slowest < 10.0


# --- evolution -------------------------------------------------------------------------------------------


def test_harmony_and_mutation_pairs_follow_sound_change():
    for seed in range(1, 80):
        base = _language(seed)
        g = base.grammar
        if not (g.harmony_pairs or g.mutation_pairs):
            continue
        evolved = evolve_language("Evolved", base, 500, TraitProfile(), seed=seed)
        assert len(evolved.grammar.harmony_pairs) == len(g.harmony_pairs)
        assert len(evolved.grammar.mutation_pairs) == len(g.mutation_pairs)
        assert evolved.grammar.harmony == g.harmony and evolved.grammar.mutation_cells == g.mutation_cells
        return
    raise AssertionError("no language with harmony or mutation")


def test_inflection_gen_accepts_the_rules_directly():
    language = _find(lambda l: l.grammar.boundary_rule == "elision")
    inventory = language.phonology
    rules = morphophonology_gen.build_rules(language.grammar, inventory)
    assert rules is not None and rules.boundary == "elision"
    assert inflection_gen.apply_affix(random.Random(1), None, "kata", inventory, "initial", 0.0, 1.0, morphophonology=rules) == "kata"
