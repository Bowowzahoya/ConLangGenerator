"""Tests for the diachronic sound-change engine (generation/sound_change.py).

Several comparisons below deliberately reuse the same ``seed`` across two
trait variants: since every rule always consumes exactly one rng draw per
eligible position regardless of outcome (same pattern used throughout
``phonology_gen.py``), the same seed means the *same underlying random
draws* get compared against a higher vs. lower rate -- so "low rate < high
rate" is guaranteed monotonic, not just statistically likely, and these
tests can't be flaky.
"""

from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import ipa_tokenizer, phonology_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.sound_change import evolve_language
from conlang_generator.llm.fake_client import FakeLLMClient

_KNOWN_SYMBOLS = tuple(c.ipa for c in phonology_gen.ALL_CONSONANTS) + tuple(v.ipa for v in phonology_gen.ALL_VOWELS)


def _base_language():
    return generate_language("Base", GenerationSpec(prompt="base", seed=13), FakeLLMClient())


def _changed_count(base, years, traits, seed) -> int:
    evolved = evolve_language("Evolved", base, years, traits, seed)
    return sum(1 for old, new in zip(base.lexicon.entries, evolved.lexicon.entries) if old.ipa != new.ipa)


def test_zero_years_produces_no_changes():
    base = _base_language()
    evolved = evolve_language("Evolved", base, 0, TraitProfile(), seed=1)
    assert [e.ipa for e in base.lexicon.entries] == [e.ipa for e in evolved.lexicon.entries]


def test_more_years_changes_more_words():
    base = _base_language()
    assert _changed_count(base, 20, TraitProfile(), seed=1) < _changed_count(base, 2000, TraitProfile(), seed=1)


def test_deterministic_for_same_inputs():
    base = _base_language()
    a = evolve_language("Evolved", base, 300, TraitProfile(contact_intensity=0.5), seed=7)
    b = evolve_language("Evolved", base, 300, TraitProfile(contact_intensity=0.5), seed=7)
    assert [e.ipa for e in a.lexicon.entries] == [e.ipa for e in b.lexicon.entries]


def test_glosses_and_pos_preserved():
    base = _base_language()
    evolved = evolve_language("Evolved", base, 500, TraitProfile(), seed=3)
    for old, new in zip(base.lexicon.entries, evolved.lexicon.entries):
        assert old.glosses == new.glosses
        assert old.pos == new.pos


def test_evolved_ipa_round_trips_through_the_tokenizer():
    # Every character in the evolved IPA is accounted for as either a known
    # symbol or a combining-mark decoration on one -- nothing silently
    # mangled to unmodeled output.
    base = _base_language()
    evolved = evolve_language("Evolved", base, 800, TraitProfile(altitude=0.8, contact_intensity=0.8), seed=9)
    for entry in evolved.lexicon.entries:
        tokens = ipa_tokenizer.tokenize(entry.ipa, _KNOWN_SYMBOLS)
        assert "".join(symbol + deco for symbol, deco in tokens) == entry.ipa


def test_contact_intensity_increases_change_rate():
    base = _base_language()
    assert _changed_count(base, 200, TraitProfile(contact_intensity=-0.9), seed=5) < _changed_count(
        base, 200, TraitProfile(contact_intensity=0.9), seed=5
    )


def _ejective_occurrences(base, years, altitude, seed) -> int:
    evolved = evolve_language("Evolved", base, years, TraitProfile(altitude=altitude), seed=seed)
    count = 0
    for entry in evolved.lexicon.entries:
        tokens = ipa_tokenizer.symbols_only(entry.ipa, _KNOWN_SYMBOLS)
        count += sum(1 for t in tokens if t in ("pʼ", "tʼ", "kʼ"))
    return count


def test_altitude_increases_ejective_drift():
    base = _base_language()
    assert _ejective_occurrences(base, 200, -0.9, seed=5) < _ejective_occurrences(base, 200, 0.9, seed=5)
