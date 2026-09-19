"""Word strictness: real source-language words in a generated language, a
knob separate from the sound strictness that only limits allowed sounds."""

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import phoneme_fit, real_words
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.prompt_classifier import _parse
from conlang_generator.llm.base import LLMResponse
from conlang_generator.llm.fake_client import FakeLLMClient


def _language(word, sound=0.8, source=("Dutch",), seed=3, client=None):
    traits = TraitProfile(source_languages=source, source_language_strictness=sound, source_word_strictness=word)
    return generate_language("T", GenerationSpec(prompt="p", seed=seed, traits=traits), client or FakeLLMClient())


def _real(language):
    return [e for e in language.lexicon.entries if e.notes.startswith("real")]


def test_word_strictness_one_makes_exact_copies_of_the_real_words_with_correct_pos():
    language = _language(1.0, sound=1.0)
    water = language.lexicon.by_gloss("water")
    assert (water.romanization, water.ipa, water.notes) == ("water", "watər", "real word: Dutch")
    assert language.lexicon.by_gloss("fire").romanization == "vuur"
    assert language.lexicon.by_gloss("mountain").pos is PartOfSpeech.NOUN
    assert language.lexicon.by_gloss("eat").pos is PartOfSpeech.VERB
    assert len(_real(language)) == 49  # every curated Dutch meaning


def test_exact_copies_force_their_sounds_into_the_inventory_even_at_low_sound_strictness():
    language = _language(1.0, sound=0.2)
    inventory = set(language.phonology.all_symbols())
    from conlang_generator.generation import ipa_tokenizer

    for entry in _real(language):
        assert "".join(ipa_tokenizer.symbols_only(entry.ipa, tuple(inventory))) == entry.ipa.replace("ˈ", "")


def test_word_strictness_zero_uses_no_real_words_and_matches_a_plain_generation():
    plain = generate_language(
        "T",
        GenerationSpec(prompt="p", seed=3, traits=TraitProfile(source_languages=("Dutch",), source_language_strictness=0.8)),
        FakeLLMClient(),
    )
    assert _real(_language(0.0)) == []
    assert _language(0.0) == plain


def test_generation_with_real_words_is_deterministic():
    assert _language(0.6) == _language(0.6)


def test_partial_strictness_gives_looser_variants_using_only_the_languages_own_sounds():
    language = _language(0.5)
    based = _real(language)
    assert 12 <= len(based) <= 38  # about half of the 49 curated meanings
    inventory = tuple(language.phonology.all_symbols())
    vowels = {v.ipa for v in language.phonology.vowels}
    from conlang_generator.generation import ipa_tokenizer

    for entry in based:
        if entry.notes.startswith("real-based"):
            symbols = ipa_tokenizer.symbols_only(entry.ipa, inventory)
            assert "".join(symbols) == entry.ipa
            assert phoneme_fit.first_problem([(s, s in vowels) for s in symbols], language.syllable_structure) is None


def test_higher_word_strictness_deviates_less_and_follows_more_words():
    def unchanged_fraction(word):
        language = _language(word, sound=1.0)
        real = _real(language)
        curated = {e.primary_gloss: e for e in _language(1.0, sound=1.0).lexicon.entries if e.notes.startswith("real")}
        same = sum(1 for e in real if curated[e.primary_gloss].ipa.replace("ˈ", "") == e.ipa.replace("ˈ", ""))
        return len(real), same / max(1, len(real))

    low_count, low_same = unchanged_fraction(0.3)
    high_count, high_same = unchanged_fraction(0.9)
    assert high_count > low_count
    assert high_same > low_same


def test_the_split_vocabulary_warning_fires_only_when_word_strictness_far_exceeds_sound_strictness():
    def warns(word, sound):
        return bool(real_words.strictness_warnings(TraitProfile(source_word_strictness=word, source_language_strictness=sound)))

    assert warns(1.0, 0.2) and warns(0.8, 0.4)
    assert not warns(0.6, 0.4)  # within the 0.25 margin
    assert not warns(0.2, 1.0)  # low word / high sound strictness is normal
    assert not warns(0.0, 0.0)


class _StubClient:
    def __init__(self, text):
        self.text = text
        self.calls = 0

    def complete(self, request):
        self.calls += 1
        return LLMResponse(text=self.text, model="stub", input_tokens=1, output_tokens=1)


def test_the_llm_fills_meanings_a_language_has_no_curated_words_for():
    reply = "\n".join(f"{i}|palabra{i}|kata" for i in range(1, 101))
    client = _StubClient(reply)
    language = _language(1.0, sound=1.0, source=("Spanish",), client=client)
    filled = [e for e in _real(language) if e.notes == "real word: Spanish"]
    assert client.calls >= 1 and len(filled) > 50
    assert all(e.ipa == "kata" and e.romanization.startswith("palabra") for e in filled)


def test_a_malformed_or_invalid_llm_reply_leaves_the_words_invented():
    for reply in ("I cannot help with that.", "\n".join(f"{i}|palabra|zzzz$$" for i in range(1, 101))):
        language = _language(1.0, sound=1.0, source=("Spanish",), client=_StubClient(reply))
        assert _real(language) == []


def test_the_classifier_parses_the_word_strictness_field():
    traits = _parse('{"source_languages": ["Dutch"], "source_word_strictness": 0.9, "time_depth_years": 200}')
    assert traits.source_word_strictness == 0.9 and traits.time_depth_years == 200
    assert _parse('{"source_word_strictness": 5}').source_word_strictness == 1.0  # clamped
