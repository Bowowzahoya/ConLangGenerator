"""Foreign proper names in translation: recognized as names (never coined as
ordinary words), kept as written or adapted to the language's own phonology
per the ``foreign_names`` trait, reused on later requests, and kept apart
from a same-spelled ordinary word."""

from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from conlang_generator.core.spec import GenerationSpec, SeedExample
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import phoneme_fit
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.seed_examples import resolve_seed_examples
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.storage.yaml_backend import YamlLanguageRepository
from conlang_generator.translation import names
from conlang_generator.translation.translator import translate_to_conlang, translate_to_english


def _language(seed=2, **spec_kwargs):
    return generate_language("T", GenerationSpec(prompt="p", seed=seed, vocabulary_size=120, **spec_kwargs), FakeLLMClient())


def test_a_name_is_kept_as_written_and_never_coined_as_an_ordinary_word():
    result = translate_to_conlang("I see Bruno", _language(foreign_names="keep"), FakeLLMClient())
    assert "Bruno" in result.text.split()
    assert [(e.primary_gloss, e.notes) for e in result.coined] == [("Bruno", names.NAME_NOTE)]
    back = translate_to_english(result.text, result.language, FakeLLMClient())
    assert "Bruno" in back.text


def test_an_adapted_name_uses_only_the_languages_own_sounds_and_syllable_rules():
    language = _language(foreign_names="adapt")
    result = translate_to_conlang("I see Bruno", language, FakeLLMClient())
    entry = result.coined[0]
    inventory = set(language.phonology.all_symbols())
    from conlang_generator.generation import ipa_tokenizer

    symbols = ipa_tokenizer.symbols_only(entry.ipa, tuple(inventory))
    assert "".join(symbols) == entry.ipa  # nothing outside the inventory
    tokens = [(s, s in {v.ipa for v in language.phonology.vowels}) for s in symbols]
    assert phoneme_fit.first_problem(tokens, language.syllable_structure) is None  # phonotactically legal
    assert entry.romanization[:1].isupper()
    back = translate_to_english(result.text, result.language, FakeLLMClient())
    assert "Bruno" in back.text


def test_adapting_is_deterministic_and_always_legal_across_languages_and_names():
    for seed in range(15):
        for source in ((), ("Mandarin",), ("Hawaiian",)):
            traits = TraitProfile(source_languages=source, source_language_strictness=1.0 if source else 0.0)
            language = _language(seed=seed, traits=traits)
            for name in ("Bruno", "Christopher", "Strasbourg", "Xi"):
                guess = resolve_seed_examples((SeedExample(gloss=name, form=name),), FakeLLMClient())[0].ipa
                first = phoneme_fit.fit_ipa(guess, language.phonology, language.syllable_structure)
                assert first and first == phoneme_fit.fit_ipa(guess, language.phonology, language.syllable_structure)
                from conlang_generator.generation import ipa_tokenizer

                symbols = ipa_tokenizer.symbols_only(first, tuple(language.phonology.all_symbols()))
                assert "".join(symbols) == first
                vowels = {v.ipa for v in language.phonology.vowels}
                assert phoneme_fit.first_problem([(s, s in vowels) for s in symbols], language.syllable_structure) is None


def test_the_trait_derives_from_source_languages_unless_set_explicitly():
    dutch = _language(traits=TraitProfile(source_languages=("Dutch",), source_language_strictness=0.5))
    mandarin = _language(traits=TraitProfile(source_languages=("Mandarin",), source_language_strictness=0.5))
    assert names.resolve_foreign_names(_language()) == "keep"  # nothing curated: keep
    assert names.resolve_foreign_names(dutch) == "keep"
    assert names.resolve_foreign_names(mandarin) == "adapt"
    override = _language(traits=TraitProfile(source_languages=("Mandarin",)), foreign_names="keep")
    assert names.resolve_foreign_names(override) == "keep"


def test_a_name_is_reused_not_regenerated_including_after_save_and_reload(tmp_path):
    language = _language(foreign_names="adapt")
    first = translate_to_conlang("I see Bruno", language, FakeLLMClient())
    repo = YamlLanguageRepository(tmp_path)
    repo.save(first.language)
    reloaded = repo.load(language.name)
    again = translate_to_conlang("I see Bruno", reloaded, FakeLLMClient())
    assert again.coined == () and again.text == first.text


def test_a_name_and_a_same_spelled_ordinary_word_stay_distinct():
    language = _language()
    language = language.with_new_words(
        (LexicalEntry(ipa="boat", romanization="Boat", glosses=("Boat",), pos=PartOfSpeech.NOUN, notes=names.NAME_NOTE),),
        reason="test name",
    )
    assert language.lexicon.by_gloss("canoe") is None
    result = translate_to_conlang("I see the canoe", language, FakeLLMClient())
    assert [e.primary_gloss for e in result.coined] == ["canoe"]
    word = translate_to_conlang("the boat is red", language, FakeLLMClient())
    assert "boat" in [e.primary_gloss for e in word.coined]  # the ordinary word, not the name entry
