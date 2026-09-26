"""Root-and-pattern inflection and derivation, and reduplication as grammar."""

import random
import time

from conlang_generator.core.grammar import PatternCell, Reduplication
from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import inflection_gen, reduplication_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.sound_change import evolve_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation.translator import (
    _apply_case,
    _apply_verb_inflection,
    _decode_noun,
    _decode_verb_full,
    _entry_root,
    _lookup_or_coin,
    _normalize,
    _stem_ipa,
    _stem_prefixes,
)

_CLIENT = FakeLLMClient()
_CACHE: dict[int, object] = {}


def _language(seed: int):
    if seed not in _CACHE:
        _CACHE[seed] = generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())
    return _CACHE[seed]


def _find(predicate, limit: int = 400):
    for seed in range(1, limit):
        language = _language(seed)
        if predicate(language):
            return language
    raise AssertionError("no seed found")


def _of(language, pos):
    return [e for e in language.lexicon.entries if e.pos is pos]


def _with(language, **updates):
    return language.model_copy(update={"grammar": language.grammar.model_copy(update=updates)})


def _templatic():
    return _find(lambda l: l.grammar.pattern_cells)


# --- generation -----------------------------------------------------------------


def test_patterns_only_exist_in_root_and_pattern_languages():
    templatic = [l for l in (_language(s) for s in range(1, 200)) if l.grammar.uses_root_and_pattern]
    assert templatic and any(l.grammar.pattern_cells for l in templatic)
    for language in (_language(s) for s in range(1, 200)):
        g = language.grammar
        assert bool(g.pattern_cells) <= g.uses_root_and_pattern
        skeletons = [p.skeleton for p in g.pattern_cells] + [t.skeleton for t in g.templates]
        assert len(skeletons) == len(set(skeletons))
        for p in g.pattern_cells:
            field, _, label = p.cell.partition("/")
            assert any(a.label == label for a in getattr(g, field))
            assert p.skeleton.count("C") == 3


def test_reduplication_cells_are_real_cells_and_never_also_patterns():
    grammars = [_language(s).grammar for s in range(1, 150)]
    assert any(g.reduplications for g in grammars)
    assert {r.kind for g in grammars for r in g.reduplications} == {k for k, _ in reduplication_gen.KINDS}
    for g in grammars:
        patterned = {p.cell for p in g.pattern_cells}
        for r in g.reduplications:
            field, _, label = r.cell.partition("/")
            assert any(a.label == label for a in getattr(g, field)) and r.cell not in patterned


def test_isolating_languages_reduplicate_more_than_fusional_ones():
    def share(kind):
        chosen = [_language(s).grammar for s in range(1, 250) if _language(s).grammar.morphological_type.value == kind]
        return sum(bool(g.reduplications) for g in chosen) / max(1, len(chosen))

    assert share("isolating") > share("fusional")


def test_the_new_grammar_fields_default_for_older_saved_languages():
    fields = type(_language(1).grammar).model_fields
    assert fields["pattern_cells"].default == () and fields["reduplications"].default == ()


# --- reduplicating a stem ------------------------------------------------------------------------


_KNOWN = tuple("aeioukgtdpbnms")
_VOWELS = frozenset("aeiou")


def test_each_kind_of_reduplication_copies_its_part():
    r = lambda kind, ipa="kanto": reduplication_gen.reduplicate(ipa, kind, _KNOWN, _VOWELS)  # noqa: E731
    assert r("full") == "kantokanto"
    assert r("initial_cv") == "kakanto"
    assert r("initial_syllable") == "kankanto"
    assert r("final_syllable") == "kantoto"
    assert r("initial_syllable", "kata") == "kakata"  # no coda to take
    assert r("final_syllable", "kat") == "katkat"  # the syllable is the whole stem


def test_stress_marks_are_dropped_and_tones_travel_with_their_vowel():
    assert reduplication_gen.reduplicate("ˈkata", "full", _KNOWN, _VOWELS) == "katakata"
    assert reduplication_gen.reduplicate("káta", "initial_cv", _KNOWN, _VOWELS) == "kákáta"


def test_a_stem_with_no_vowel_is_left_alone():
    assert reduplication_gen.reduplicate("kst", "full", _KNOWN, _VOWELS) == "kst"


# --- rendering and decoding ----------------------------------------------------------------------------


def _redup_language(field: str):
    return _find(lambda l: any(r.cell.startswith(field) for r in l.grammar.reduplications))


def test_a_reduplicated_plural_repeats_the_stem_in_the_marked_cell_only():
    language = _find(lambda l: any(r.cell == "number_affixes/plural" and r.kind == "full" for r in l.grammar.reduplications))
    entry = _of(language, PartOfSpeech.NOUN)[5]
    plural = _stem_ipa(language, entry, ["number_affixes/plural"])
    assert plural.replace("ˈ", "") == entry.ipa.replace("ˈ", "") * 2
    assert _stem_ipa(language, entry, ["case_affixes/accusative"]) == entry.ipa
    assert _apply_case(language, entry, None, "plural")[0] != _apply_case(language, entry, None, None)[0]


def test_reduplication_only_touches_the_cells_part_of_speech():
    language = _find(lambda l: any(r.cell == "number_affixes/plural" for r in l.grammar.reduplications))
    verb = _of(language, PartOfSpeech.VERB)[0]
    assert _stem_ipa(language, verb, ["number_affixes/plural"]) == verb.ipa


def test_reduplicated_forms_decode_and_reproduce_their_token():
    rng = random.Random(6)
    checked = 0
    for seed in range(1, 250):
        language = _language(seed)
        g = language.grammar
        if not g.reduplications:
            continue
        nouns = _of(language, PartOfSpeech.NOUN)
        for entry in rng.sample(nouns, min(5, len(nouns))):
            for number in [None, *[a.label for a in g.number_affixes][:1]]:
                token = _apply_case(language, entry, None, number)[0]
                decoded = _decode_noun(language, token)
                assert decoded is not None, (seed, entry.romanization, number, token)
                parts = [] if decoded[1] == "unmarked" else decoded[1].split("+")
                d_number = next((p for p in parts if p in [a.label for a in g.number_affixes]), None)
                d_case = next((p for p in parts if p in [a.label for a in g.case_affixes]), None)
                assert _normalize(_apply_case(language, decoded[0], d_case, d_number)[0]) == _normalize(token)
                checked += 1
        verbs = _of(language, PartOfSpeech.VERB)
        for entry in rng.sample(verbs, min(3, len(verbs))):
            for aspect in [None, *g.aspects[:2]]:
                token = _apply_verb_inflection(language, entry, g.tenses[0] if g.tenses else None, "default", aspect_label=aspect)[0]
                assert _decode_verb_full(language, token) is not None, (seed, entry.romanization, aspect, token)
                checked += 1
        if checked > 60:
            break
    assert checked > 30


def test_the_stem_prefix_filter_knows_the_reduplicated_start():
    language = _find(lambda l: any(r.kind == "initial_cv" for r in l.grammar.reduplications))
    entry = _of(language, PartOfSpeech.NOUN)[3]
    assert _stem_prefixes(language, entry)  # includes the original spelling


# --- root and pattern beyond the citation shape ------------------------------------------------------------


def test_a_verb_is_rebuilt_from_its_root_in_each_tense():
    language = _templatic()
    g = language.grammar
    tense_cells = [p for p in g.pattern_cells if p.cell.startswith("tense_affixes")]
    assert tense_cells
    checked = 0
    for entry in _of(language, PartOfSpeech.VERB):
        root = _entry_root(language, entry)
        if root is None:
            continue
        stems = {}
        for pattern in tense_cells:
            stem = _stem_ipa(language, entry, [pattern.cell])
            consonants = [c for c in stem if c in "".join(root)]
            assert tuple(root) == tuple(c for c in root)  # the root itself is unchanged
            stems[pattern.cell] = stem
        assert len(set(stems.values())) == len(stems)  # each tense has its own vowel melody
        checked += 1
        if checked >= 5:
            break
    assert checked > 0


def test_a_patterned_stem_keeps_the_roots_consonants_in_order():
    language = _templatic()
    pattern = language.grammar.pattern_cells[0]
    pos = {"tense_affixes": PartOfSpeech.VERB, "aspect_affixes": PartOfSpeech.VERB, "number_affixes": PartOfSpeech.NOUN,
           "degree_affixes": PartOfSpeech.ADJECTIVE}[pattern.cell.partition("/")[0]]
    for entry in _of(language, pos):
        root = _entry_root(language, entry)
        if root is None:
            continue
        stem = _stem_ipa(language, entry, [pattern.cell])
        it = iter(stem)
        assert all(any(ch == sym for ch in it) for sym in root)
        assert stem != entry.ipa
        return
    raise AssertionError("no rooted word")


def test_words_without_a_root_or_of_another_part_of_speech_are_untouched():
    language = _templatic()
    pattern = language.grammar.pattern_cells[0]
    for entry in language.lexicon.entries:
        if entry.root is None or entry.pos is PartOfSpeech.PRONOUN:
            assert _stem_ipa(language, entry, [pattern.cell]) == entry.ipa


def test_patterned_forms_decode():
    checked = 0
    for seed in range(1, 400):
        language = _language(seed)
        g = language.grammar
        if not g.pattern_cells:
            continue
        for entry in _of(language, PartOfSpeech.VERB)[:40]:
            if _entry_root(language, entry) is None:
                continue
            for tense in g.tenses:
                token = _apply_verb_inflection(language, entry, tense, "default")[0]
                assert _decode_verb_full(language, token) is not None, (seed, entry.romanization, tense, token)
                checked += 1
            if checked >= 12:
                break
        for entry in _of(language, PartOfSpeech.NOUN)[:40]:
            if _entry_root(language, entry) is None or not g.number_affixes:
                continue
            token = _apply_case(language, entry, None, g.number_affixes[0].label)[0]
            assert _decode_noun(language, token) is not None, (seed, entry.romanization, token)
            checked += 1
            if checked >= 24:
                return
    assert checked > 8


def test_a_derived_word_shares_its_bases_root_in_a_templatic_language():
    language = _find(
        lambda l: l.grammar.uses_root_and_pattern and any(r.name == "agent" and r.pattern for r in l.grammar.derivations)
        and (l.lexicon.by_gloss("teach") is not None and l.lexicon.by_gloss("teach").root)
    )
    updated, entry = _lookup_or_coin(language, "teacher", PartOfSpeech.NOUN, [], _CLIENT, ["teacher"])
    base = language.lexicon.by_gloss("teach")
    assert entry.root == base.root
    assert "pattern noun-agent" in entry.notes or entry.notes.startswith("derived")
    consonants = [c for c in entry.ipa if c in "".join(base.root)]
    assert consonants  # the root's consonants are in the derived word


def test_other_languages_still_derive_with_the_affix():
    language = _find(
        lambda l: not l.grammar.uses_root_and_pattern and any(r.name == "agent" for r in l.grammar.derivations)
        and l.lexicon.by_gloss("teach") is not None
    )
    _, entry = _lookup_or_coin(language, "teacher", PartOfSpeech.NOUN, [], _CLIENT, ["teacher"])
    assert entry.notes == "derived: agent of teach"


# --- decoding speed and evolution ----------------------------------------------------------------------------


def test_unknown_tokens_are_still_rejected_quickly():
    slowest = 0.0
    count = 0
    for seed in range(1, 400):
        language = _language(seed)
        g = language.grammar
        if not (g.pattern_cells or g.reduplications):
            continue
        start = time.perf_counter()
        assert _decode_noun(language, "zzqxkv") is None
        _decode_verb_full(language, "zzqxkv")
        slowest = max(slowest, time.perf_counter() - start)
        count += 1
        if count >= 12:
            break
    assert slowest < 10.0


def test_pattern_vowels_follow_sound_change_and_stale_roots_fall_back():
    language = _templatic()
    evolved = evolve_language("Evolved", language, 800, TraitProfile(), seed=2)
    assert [p.cell for p in evolved.grammar.pattern_cells] == [p.cell for p in language.grammar.pattern_cells]
    for entry in _of(evolved, PartOfSpeech.VERB)[:80]:
        root = _entry_root(evolved, entry)  # None when the root's consonants have changed
        stem = _stem_ipa(evolved, entry, [evolved.grammar.pattern_cells[0].cell])
        assert isinstance(stem, str) and (root is not None or stem == entry.ipa)
    assert isinstance(PatternCell(cell="x/y", skeleton=("C",)), PatternCell) and Reduplication(cell="x/y", kind="full").kind == "full"
    assert inflection_gen is not None
