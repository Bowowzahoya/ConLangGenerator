"""Every generated lexicon entry's IPA must survive a tokenize/rejoin round
trip against its own language's symbol set -- otherwise the tokenizer
silently drops or re-splits symbols and e.g. ``evolve_language(years=0)``
rewrites words that shouldn't have changed."""

from conlang_generator.core.phonology import Consonant, Manner, Place
from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation import ipa_tokenizer, sonority
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient


def _c(ipa, manner=Manner.STOP, place=Place.ALVEOLAR, voiced=False, **kw):
    return Consonant(ipa=ipa, place=place, manner=manner, voiced=voiced, **kw)


def test_cluster_pairs_never_concatenate_into_a_different_symbol_sequence():
    # /t/ + /sː/ would read back as the affricate /ts/ plus a stray "ː".
    consonants = (_c("t"), _c("sː", Manner.FRICATIVE, long=True), _c("ts", Manner.AFFRICATE), _c("r", Manner.TRILL))
    symbols = tuple(c.ipa for c in consonants)
    pairs = sonority.legal_onset_pairs(consonants) + sonority.legal_coda_pairs(consonants)
    assert ("t", "sː") not in pairs
    for first, second in pairs:
        assert ipa_tokenizer.tokenize(first + second, symbols) == [(first, ""), (second, "")]


def test_generated_lexicons_round_trip_through_the_ipa_tokenizer():
    failures = []
    for seed in range(41):
        language = generate_language("T", GenerationSpec(prompt="base", seed=seed), FakeLLMClient())
        symbols = (*language.phonology.all_symbols(), STRESS_MARK, WORD_ACCENT_MARK)
        for entry in language.lexicon.entries:
            rejoined = "".join(sym + deco for sym, deco in ipa_tokenizer.tokenize(entry.ipa, symbols))
            if rejoined != entry.ipa:
                failures.append((seed, entry.glosses, entry.ipa, rejoined))
    assert not failures, failures


def test_syllable_boundaries_never_join_into_a_different_symbol_sequence():
    # /n/ + /dʒ/ would read back as the prenasalized /nd/ plus a stray "ʒ".
    consonants = (_c("n", Manner.NASAL, voiced=True), _c("dʒ", Manner.AFFRICATE, Place.POSTALVEOLAR, True),
                  _c("nd", Manner.STOP, voiced=True), _c("l", Manner.LATERAL_APPROXIMANT, voiced=True))
    unsafe = sonority.unreadable_boundary_pairs(consonants)
    assert ("n", "dʒ") in unsafe and ("l", "dʒ") not in unsafe
    symbols = tuple(c.ipa for c in consonants)
    for first, second in unsafe:
        assert ipa_tokenizer.tokenize(first + second, symbols) != [(first, ""), (second, "")]
