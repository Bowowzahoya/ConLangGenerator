"""Decoding an unknown token searches inflected forms; these tests check that the
speed-ups (a cached tokenizer, a per-inventory symbol cache, and filtering
candidate nouns and verbs by their first letters) change no result."""

import random
import time

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import inflection_gen, ipa_tokenizer
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation.translator import (
    _apply_case,
    _apply_verb_inflection,
    _decode_noun,
    _decode_verb_full,
    _normalize,
)

_CACHE: dict[int, object] = {}


def _language(seed: int):
    if seed not in _CACHE:
        _CACHE[seed] = generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())
    return _CACHE[seed]


def _reference_tokenize(text: str, known_symbols):
    """The original, unindexed algorithm."""
    ordered = sorted(set(known_symbols), key=len, reverse=True)
    tokens = []
    i = 0
    import unicodedata

    while i < len(text):
        if text[i] in ipa_tokenizer._STANDALONE_MARKS:
            tokens.append((text[i], ""))
            i += 1
            continue
        candidates = [s for s in ordered if text.startswith(s, i)]
        matched = next((s for s in candidates if not ipa_tokenizer._strands_a_modifier(text, i + len(s))), None)
        if matched is None and candidates:
            matched = candidates[0]
        if matched is None:
            if tokens and unicodedata.combining(text[i]):
                symbol, deco = tokens[-1]
                tokens[-1] = (symbol, deco + text[i])
            i += 1
            continue
        i += len(matched)
        deco = ""
        while i < len(text) and unicodedata.combining(text[i]):
            deco += text[i]
            i += 1
        tokens.append((matched, deco))
    return tokens


def test_the_indexed_tokenizer_matches_the_plain_algorithm():
    for seed in range(1, 25):
        language = _language(seed)
        known = inflection_gen._known_symbols_for(language.phonology)
        for entry in language.lexicon.entries[:80]:
            assert ipa_tokenizer.tokenize(entry.ipa, known) == _reference_tokenize(entry.ipa, known)


def test_the_indexed_romanization_matches_the_plain_lookup():
    for seed in range(1, 25):
        language = _language(seed)
        scheme = language.romanization
        plain = scheme._known_symbols()
        for first, symbols in scheme._known_by_first_char.items():
            assert list(symbols) == [s for s in plain if s.startswith(first)]


def test_the_symbol_cache_is_per_inventory():
    a, b = _language(1).phonology, _language(2).phonology
    assert inflection_gen._known_symbols_for(a) is inflection_gen._known_symbols_for(a)
    assert set(inflection_gen._known_symbols_for(a)) != set(inflection_gen._known_symbols_for(b)) or a == b


def test_every_inflected_noun_still_decodes_to_its_own_entry():
    rng = random.Random(4)
    checked = 0
    for seed in range(1, 40):
        language = _language(seed)
        grammar = language.grammar
        nouns = [e for e in language.lexicon.entries if e.pos.value == "noun"]
        for entry in rng.sample(nouns, min(6, len(nouns))):
            for case in [None, *[a.label for a in grammar.case_affixes][:2]]:
                for number in [None, *[a.label for a in grammar.number_affixes][:2]]:
                    token = _apply_case(language, entry, case, number)[0]
                    decoded = _decode_noun(language, token)
                    assert decoded is not None, (seed, entry.romanization, case, number, token)
                    # another word may spell alike; the reading must reproduce the token
                    assert _normalize(_apply_case(language, decoded[0], *_labels(decoded[1]))[0]) == _normalize(token)
                    checked += 1
    assert checked > 200


def _labels(label: str):
    parts = [] if label == "unmarked" else label.split("+")
    number = next((p for p in parts if p in ("plural", "dual", "trial", "collective")), None)
    case = next((p for p in parts if p not in ("plural", "dual", "trial", "collective", "possessed") and not p.startswith("poss:")), None)
    return case, number


def test_every_inflected_verb_still_decodes():
    rng = random.Random(5)
    checked = 0
    for seed in range(1, 40):
        language = _language(seed)
        verbs = [e for e in language.lexicon.entries if e.pos.value == "verb"]
        tenses = language.grammar.tenses or (None,)
        for entry in rng.sample(verbs, min(5, len(verbs))):
            for tense in tenses:
                token = _apply_verb_inflection(language, entry, tense, "default")[0]
                decoded = _decode_verb_full(language, token)
                assert decoded is not None, (seed, entry.romanization, tense, token)
                checked += 1
            command = _apply_verb_inflection(language, entry, None, "default", "imperative")[0]
            assert _decode_verb_full(language, command) is not None
    assert checked > 200


def test_an_unknown_token_is_rejected_quickly_in_every_language():
    slowest = 0.0
    for seed in range(1, 16):
        language = _language(seed)
        start = time.perf_counter()
        assert _decode_noun(language, "zzqxkv") is None
        _decode_verb_full(language, "zzqxkv")
        slowest = max(slowest, time.perf_counter() - start)
    assert slowest < 6.0  # was several times that before the candidate filtering
