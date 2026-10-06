"""Word strictness: real source-language words in a generated language, a
knob separate from the sound strictness that only limits allowed sounds."""

from conlang_generator.core.lexicon import PartOfSpeech, RealWordOrigin
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import phoneme_fit, real_words
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.lexicon_gen import select_meanings
from conlang_generator.generation.prompt_classifier import _parse
from conlang_generator.llm.base import LLMResponse
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.translation.translator import translate_to_conlang
from tests.factories import make_minimal_language


def _language(word, sound=0.8, source=("Dutch",), seed=3, client=None):
    traits = TraitProfile(source_languages=source, source_language_strictness=sound, source_word_strictness=word)
    return generate_language("T", GenerationSpec(prompt="p", seed=seed, traits=traits), client or FakeLLMClient())


def _real(language):
    return [e for e in language.lexicon.entries if e.notes.startswith("real")]


def test_word_strictness_one_makes_exact_copies_of_the_real_words_with_correct_pos():
    language = _language(1.0, sound=1.0)
    water = language.lexicon.by_gloss("water")
    assert (water.romanization, water.ipa, water.notes) == ("water", "ˈwatər", "real word: Dutch")
    assert language.lexicon.by_gloss("fire").romanization == "vuur"
    assert language.lexicon.by_gloss("mountain").pos is PartOfSpeech.NOUN
    assert language.lexicon.by_gloss("eat").pos is PartOfSpeech.VERB
    assert len(_real(language)) >= 350  # nearly every pregenerated meaning is a curated Dutch word


def test_exact_real_words_carry_their_own_origin():
    language = _language(1.0, sound=1.0)
    water = language.lexicon.by_gloss("water")
    assert water.real_word == RealWordOrigin(language="Dutch", form="water", ipa="ˈwatər")


def test_deviated_real_words_still_carry_the_true_original_not_the_looser_variant():
    language = _language(0.5)
    based = [e for e in _real(language) if e.notes.startswith("real-based")]
    assert based, "no deviated real-based word in this sample -- test would be vacuous"
    for entry in based:
        assert entry.real_word is not None
        assert entry.real_word.language == "Dutch"
        # The true original, not the deviated ipa/romanization this
        # entry's own fields now hold.
        assert entry.real_word.ipa != "" and entry.real_word.form != ""


def test_algorithmically_coined_words_have_no_real_word_origin():
    language = _language(0.0)
    coined = [e for e in language.lexicon.entries if not e.notes.startswith("real")]
    assert coined
    assert all(e.real_word is None for e in coined)


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
    assert 120 <= len(based) <= 280  # about half of the 400 pregenerated meanings
    inventory = tuple(language.phonology.all_symbols())
    vowels = {v.ipa for v in language.phonology.vowels}
    from conlang_generator.generation import ipa_tokenizer

    for entry in based:
        if entry.notes.startswith("real-based"):
            symbols = ipa_tokenizer.symbols_only(entry.ipa, inventory)
            assert "".join(symbols) == entry.ipa.replace("ˈ", "")
            assert phoneme_fit.first_problem([(s, s in vowels) for s in symbols], language.syllable_structure) is None


def test_build_deviation_shift_rolls_once_per_symbol_not_per_occurrence():
    import random

    language = _language(0.5)
    inventory = language.phonology
    full = phoneme_fit.build_deviation_shift(inventory, random.Random(1), rate=1.0)
    assert full  # something shifted
    assert set(full) <= set(inventory.all_symbols())
    assert all(target != symbol for symbol, target in full.items())
    none = phoneme_fit.build_deviation_shift(inventory, random.Random(1), rate=0.0)
    assert none == {}


def test_build_deviation_shift_is_deterministic():
    import random

    language = _language(0.5)
    a = phoneme_fit.build_deviation_shift(language.phonology, random.Random(42), rate=0.5)
    b = phoneme_fit.build_deviation_shift(language.phonology, random.Random(42), rate=0.5)
    assert a == b


def test_apply_shift_maps_the_same_symbol_identically_everywhere():
    """The DEFERRED.md complaint this pass fixes: a given source phoneme
    becomes the SAME target sound wherever it occurs -- not an
    independently re-rolled substitution each time, like a real daughter
    language's own systematic sound shift (Grimm's Law). Uses a plain
    CV/CVCV construction so syllable repair can't obscure the comparison."""
    language = _language(0.5)
    inventory = language.phonology
    structure = language.syllable_structure
    consonant = inventory.consonants[0].ipa
    vowel = inventory.vowels[0].ipa
    target = phoneme_fit.neighbours(consonant, inventory)[0]
    shift = {consonant: target}
    once = phoneme_fit.apply_shift(consonant + vowel, inventory, structure, shift)
    twice = phoneme_fit.apply_shift(consonant + vowel + consonant + vowel, inventory, structure, shift)
    assert target in once
    assert twice.count(target) >= 2  # both occurrences shifted the same way
    assert consonant not in twice  # the source symbol never survives once it's in the table


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


def _uncurated(monkeypatch, name="Zulu"):
    """Pretend ``name`` has no curated words, whatever the data files hold."""
    original = real_words.real_words
    monkeypatch.setattr(real_words, "real_words", lambda n: {} if n == name else original(n))


def test_the_llm_fills_meanings_a_language_has_no_curated_words_for(monkeypatch):
    _uncurated(monkeypatch)
    reply = "\n".join(f"{i}|palabra{i}|kata" for i in range(1, 101))
    client = _StubClient(reply)
    language = _language(1.0, sound=1.0, source=("Zulu",), client=client)
    filled = [e for e in _real(language) if e.notes == "real word: Zulu"]
    assert client.calls >= 1 and len(filled) > 50
    assert all(e.ipa == "kata" and e.romanization.startswith("palabra") for e in filled)


def test_a_malformed_or_invalid_llm_reply_leaves_the_words_invented(monkeypatch):
    _uncurated(monkeypatch)
    for reply in ("I cannot help with that.", "\n".join(f"{i}|palabra|zzzz$$" for i in range(1, 101))):
        language = _language(1.0, sound=1.0, source=("Zulu",), client=_StubClient(reply))
        assert _real(language) == []


def test_a_non_latin_spelling_from_the_llm_is_rejected_not_accepted_verbatim(monkeypatch):
    # The real bug this guards against: a real LLM disregarding the
    # system prompt's own "romanize it" instruction and answering with an
    # actual word in another script (e.g. a Chinese character, reportedly
    # seen for "now" on a Chinese-influenced language) must never end up
    # as a word's own spelling.
    _uncurated(monkeypatch)
    reply = "\n".join(f"{i}|呢|kɑtɑ" for i in range(1, 101))
    language = _language(1.0, sound=1.0, source=("Zulu",), client=_StubClient(reply))
    assert _real(language) == []


def test_real_words_llm_is_romanized_accepts_latin_extended_rejects_other_scripts():
    from conlang_generator.generation.real_words_llm import _is_romanized

    assert _is_romanized("koning")
    assert _is_romanized("øre")  # a real Latin-extended letter
    assert _is_romanized("n'a")  # punctuation/apostrophe, not a script issue
    assert not _is_romanized("呢")  # Chinese
    assert not _is_romanized("я")  # Cyrillic
    assert not _is_romanized("α")  # Greek


def test_the_classifier_parses_the_word_strictness_field():
    traits = _parse('{"source_languages": ["Dutch"], "source_word_strictness": 0.9, "time_depth_years": 200}')
    assert traits.source_word_strictness == 0.9 and traits.time_depth_years == 200
    assert _parse('{"source_word_strictness": 5}').source_word_strictness == 1.0  # clamped


# --- on-the-fly real-word coinage (coin_real_word) --------------------------


def test_deviation_shift_table_matches_the_old_inline_construction():
    # Regression guard for extracting deviation_shift_table out of
    # build_real_entries's own local variable.
    import random

    language = _language(0.5)
    inventory = language.phonology
    rate = (1.0 - 0.5) * real_words.DEVIATION_SCALE
    expected = phoneme_fit.build_deviation_shift(inventory, random.Random(f"{language.spec.seed}:real-deviation"), rate)
    assert real_words.deviation_shift_table(language.spec.seed, 0.5, inventory) == expected


def test_build_real_entry_with_allow_exact_copy_false_never_forces_a_verbatim_copy():
    # allow_exact_copy=True (generation time) takes the forced-verbatim
    # branch purely from strictness>=1.0, keeping a phoneme outside this
    # language's own inventory untouched -- only safe because phonology_
    # gen already force-included it beforehand. allow_exact_copy=False
    # (on-the-fly coinage, after the inventory is already fixed) must
    # never do that: it always fits the ipa to the inventory that already
    # exists, even at strictness 1.0.
    language = make_minimal_language()  # consonants p/t/m, vowels a/i -- no "s"
    choice = real_words.RealChoice("madeupgloss", PartOfSpeech.NOUN, "Dutch", "saform", "sa")
    shift = real_words.deviation_shift_table(1, 1.0, language.phonology)
    forced = real_words._build_real_entry(
        choice, shift, 1.0, language.phonology, language.syllable_structure, language.romanization,
        language.tone_system, allow_exact_copy=True,
    )
    fitted = real_words._build_real_entry(
        choice, shift, 1.0, language.phonology, language.syllable_structure, language.romanization,
        language.tone_system, allow_exact_copy=False,
    )
    assert forced.ipa == "sa" and forced.notes == "real word: Dutch"  # verbatim, "s" untouched
    assert fitted.ipa != "sa" and fitted.notes == "real-based word: Dutch"  # "s" fit to the nearest available sound
    assert "s" not in fitted.ipa


def test_coin_real_word_is_none_below_or_at_zero_word_strictness():
    language = _language(0.0, sound=1.0)
    assert real_words.coin_real_word(language, "king", PartOfSpeech.NOUN, FakeLLMClient()) is None


def test_coin_real_word_is_none_with_no_matched_source_language():
    language = generate_language("T", GenerationSpec(
        prompt="p", seed=3, traits=TraitProfile(source_word_strictness=1.0),
    ), FakeLLMClient())
    assert real_words.coin_real_word(language, "king", PartOfSpeech.NOUN, FakeLLMClient()) is None


def test_coin_real_word_is_none_for_a_templatic_language_and_pos():
    client = FakeLLMClient()
    language = next(
        (
            l for l in (
                generate_language("T", GenerationSpec(
                    prompt="p", seed=seed, traits=TraitProfile(source_languages=("Hebrew",), source_word_strictness=1.0),
                ), client)
                for seed in range(1, 60)
            )
            if l.grammar.uses_root_and_pattern
        ),
        None,
    )
    assert language is not None, "no templatic seed found in range -- widen the search"
    assert real_words.coin_real_word(language, "fire", PartOfSpeech.NOUN, client) is None


def test_coin_real_word_finds_a_curated_word_excluded_from_the_generated_vocabulary():
    # "king" is curated for Dutch but falls outside the default 400-word
    # generated vocabulary (496 total core meanings) -- the exact gap
    # on-the-fly coinage exists to fill.
    excluded = {g for g, _ in select_meanings(496)} - {g for g, _ in select_meanings(400)}
    assert "king" in excluded  # sanity: the premise this test relies on
    language = _language(1.0, sound=1.0)
    assert language.lexicon.by_gloss("king") is None
    entry = real_words.coin_real_word(language, "king", PartOfSpeech.NOUN, FakeLLMClient())
    assert entry is not None
    assert entry.notes.startswith("real") and entry.real_word is not None and entry.real_word.language == "Dutch"


def test_coin_real_word_is_deterministic():
    language = _language(1.0, sound=1.0)
    client = FakeLLMClient()
    a = real_words.coin_real_word(language, "king", PartOfSpeech.NOUN, client)
    b = real_words.coin_real_word(language, "king", PartOfSpeech.NOUN, client)
    assert a == b


def test_coin_real_word_falls_back_to_none_when_curated_and_llm_both_miss(monkeypatch):
    _uncurated(monkeypatch, "Dutch")
    language = _language(1.0, sound=1.0)
    stub = _StubClient("I cannot help with that.")
    assert real_words.coin_real_word(language, "king", PartOfSpeech.NOUN, stub) is None
    assert stub.calls >= 1  # it did attempt the LLM gap-fill


def test_on_the_fly_coinage_uses_a_real_word_at_high_strictness_and_invents_at_zero():
    high = _language(1.0, sound=1.0)
    low = _language(0.0, sound=1.0)
    client = FakeLLMClient()
    high_result = translate_to_conlang("I see the king", high, client)
    low_result = translate_to_conlang("I see the king", low, client)
    high_coined = [e for e in high_result.coined if e.primary_gloss == "king"]
    low_coined = [e for e in low_result.coined if e.primary_gloss == "king"]
    assert high_coined and high_coined[0].notes.startswith("real") and high_coined[0].real_word is not None
    assert low_coined and low_coined[0].notes == "" and low_coined[0].real_word is None


def test_on_the_fly_real_word_coinage_never_also_pays_for_word_selection_llm(monkeypatch):
    # A successful real-word gap-fill must never ALSO pay for
    # word_selection="llm"'s own candidate-selection call for the same
    # word -- the two paths are mutually exclusive by construction (real-
    # word coinage returns immediately, before the invented-candidate
    # path that call belongs to is ever reached).
    _uncurated(monkeypatch, "Zulu")
    language = _language(1.0, sound=1.0, source=("Zulu",))
    language = language.model_copy(update={"spec": language.spec.model_copy(update={"word_selection": "llm"})})
    client = _StubClient("1|palabra|kata")
    translate_to_conlang("I see the king", language, client)
    # Exactly one call for sentence planning, one for the real-word gap-
    # fill on "king" -- never a third for word_selection="llm".
    assert client.calls == 2
