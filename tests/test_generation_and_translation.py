"""End-to-end coverage using FakeLLMClient: generation determinism,
translation round-tripping, on-the-fly word coinage and persistence, and the
cache/cost-tracking contract (a cache hit must not be billed twice)."""

from pathlib import Path

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.romanization import STRESS_MARK
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.sound_change import evolve_language
from conlang_generator.llm.base import LLMRequest
from conlang_generator.llm.cost_tracker import CostTracker
from conlang_generator.llm.factory import build_llm_client
from conlang_generator.llm.fake_client import FakeLLMClient
from conlang_generator.llm.pricing import DEFAULT_MODEL
from conlang_generator.storage.yaml_backend import YamlLanguageRepository
from conlang_generator.translation.translator import translate_to_conlang, translate_to_english


def test_generation_is_deterministic_for_identical_inputs():
    spec = GenerationSpec(prompt="test language", seed=7)
    lang1 = generate_language("Test", spec, FakeLLMClient())
    lang2 = generate_language("Test", spec, FakeLLMClient())
    assert lang1 == lang2


def test_the_and_be_are_coined_only_when_their_grammar_flag_is_set():
    # A small vocabulary is enough: "the"/"be" are always in it (essential
    # glosses) and the grammar flags are drawn long before the lexicon.
    for seed in range(60):
        language = generate_language(
            "Test", GenerationSpec(prompt="p", seed=seed, vocabulary_size=20), FakeLLMClient()
        )
        assert (language.lexicon.by_gloss("the") is not None) == language.grammar.has_articles
        assert (language.lexicon.by_gloss("be") is not None) == language.grammar.has_overt_copula


def test_core_vocabulary_has_no_romanization_collisions():
    # Seeds 5 and 8 are known to have previously produced homographs among
    # CORE_MEANINGS entries (e.g. seed=8: "mountain"/"and" both romanized
    # to "lu"; seed=5: "not"/"water" both romanized to "tanh" despite
    # different IPA) before generator.py's core-vocabulary loop gained the
    # same by_form collision-avoidance retry translation.expansion.coin_word
    # already had. Lexicon.by_form returns only the first match, so a
    # homograph made the other word unreachable/misidentified via it.
    for seed in (5, 8):
        language = generate_language("Test", GenerationSpec(prompt="p", seed=seed), FakeLLMClient())
        seen: dict[str, str] = {}
        for entry in language.lexicon.entries:
            form = entry.romanization.lower()
            assert form not in seen, (
                f"seed={seed}: {entry.primary_gloss!r} and {seen.get(form)!r} "
                f"both romanize to {entry.romanization!r}"
            )
            seen[form] = entry.primary_gloss


def test_translate_round_trip_for_core_vocabulary():
    # Seed 1 -- known to round-trip "mountain"/"high" cleanly with no
    # candidate collisions. (Re-found against seed=1 after the Thai/
    # Indonesian/Malay batch's own new phoneme-pool content (tɕʰ, ɤ, and
    # the ɛː/ɔː/ɯː/ɤː long vowels) shifted downstream rng draws enough
    # that seed=0's own word choices stopped round-tripping -- same
    # "seed-shift from new content" pattern documented elsewhere in this
    # project's history.)
    spec = GenerationSpec(prompt="test language", seed=1)
    client = FakeLLMClient()
    language = generate_language("Test", spec, client)

    to_conlang = translate_to_conlang("the mountain is high", language, client)
    assert to_conlang.pattern == "llm-plan"
    assert to_conlang.coined == ()  # both words are core vocabulary

    back = translate_to_english(to_conlang.text, to_conlang.language, client)
    assert "mountain" in back.text.lower()
    assert "high" in back.text.lower()


def test_translate_coins_new_word_and_can_be_persisted(tmp_path: Path):
    spec = GenerationSpec(prompt="test language", seed=7)
    client = FakeLLMClient()
    language = generate_language("Test", spec, client)
    # Words outside the default 400-word vocabulary, so they must be coined.
    assert language.lexicon.by_gloss("canoe") is None
    assert language.lexicon.by_gloss("crimson") is None

    result = translate_to_conlang("the canoe is crimson", language, client)
    assert len(result.coined) == 2
    assert result.language.lexicon.by_gloss("canoe") is not None
    assert result.language.lexicon.by_gloss("crimson") is not None
    assert language.lexicon.by_gloss("canoe") is None  # original untouched

    repo = YamlLanguageRepository(tmp_path)
    repo.save(result.language)
    reloaded = repo.load(language.name)
    assert reloaded.lexicon.by_gloss("canoe") is not None
    assert reloaded.lexicon.by_gloss("crimson") is not None


def test_a_coined_word_is_reused_not_recoined_on_later_requests(tmp_path: Path):
    client = FakeLLMClient()
    language = generate_language("Test", GenerationSpec(prompt="p", seed=7), client)
    first = translate_to_conlang("the canoe is crimson", language, client)
    canoe = first.language.lexicon.by_gloss("canoe")

    repo = YamlLanguageRepository(tmp_path)
    repo.save(first.language)
    reloaded = repo.load(language.name)  # a later session

    again = translate_to_conlang("the canoe is crimson", reloaded, client)
    assert again.coined == ()
    assert again.text == first.text

    plural = translate_to_conlang("the canoes are crimson", reloaded, client)
    assert plural.coined == ()  # "canoes" finds the existing "canoe"
    assert canoe.romanization in plural.text.split()



def test_cache_hit_is_not_billed_again(tmp_path: Path):
    client = build_llm_client(kind="fake", cache_dir=tmp_path)
    request = LLMRequest(
        system="system prompt",
        prompt="same prompt every time",
        model=DEFAULT_MODEL,
        purpose="test",
    )

    first = client.complete(request)
    second = client.complete(request)

    assert first.text == second.text
    assert first.cached is False
    assert second.cached is True

    summary = CostTracker(tmp_path / "cost_ledger.jsonl").summarize()
    assert summary["num_calls"] == 1


def test_german_biased_language_capitalizes_its_noun_entries():
    # seed 1 rolls capitalized_pos=(NOUN,) for a German-contact language
    # (see romanization_gen.py's grammatical-spelling roll) -- an
    # empirically-found seed, same "search for a working seed" convention
    # this project already uses elsewhere (test_sound_change.py). (Re-found
    # against seed=1 after the ten-language batch's own new phoneme-pool
    # content shifted downstream rng draws enough that seed=0 stopped
    # rolling this -- same "seed-shift from new content" pattern
    # documented throughout this project's history.)
    spec = GenerationSpec(prompt="test", seed=1, traits=TraitProfile(source_languages=("German",)))
    language = generate_language("Test", spec, FakeLLMClient())
    assert PartOfSpeech.NOUN in language.romanization.grammatical_spelling.capitalized_pos
    nouns = [e for e in language.lexicon.entries if e.pos is PartOfSpeech.NOUN]
    assert nouns
    assert all(entry.romanization[:1].isupper() for entry in nouns)


_FRENCH_VERB_CLASS_SUFFIXES = {("e",), ("i", "ʁ"), ("ʁ",)}  # -er / -ir / -re, see french.yaml's own word_classes


def test_french_biased_language_gives_its_verb_entries_a_real_conjugation_class():
    # seed=2 rolls French's own real word_classes adoption for VERB and
    # actually assigns (not deviates) every core-vocabulary verb this
    # run -- an empirically-found seed, same "search for a working seed"
    # convention this project already uses elsewhere (test_sound_change.py).
    spec = GenerationSpec(prompt="test", seed=2, traits=TraitProfile(source_languages=("French",)))
    language = generate_language("Test", spec, FakeLLMClient())
    verbs = [e for e in language.lexicon.entries if e.pos is PartOfSpeech.VERB]
    assert verbs
    classed_verbs = [e for e in verbs if e.word_class is not None]
    assert classed_verbs  # at least one verb actually got a real class assignment this run
    for entry in classed_verbs:
        assert entry.word_class in {"-er verbs", "-ir verbs", "-re verbs"}
        assert any(entry.ipa.endswith("".join(suffix)) for suffix in _FRENCH_VERB_CLASS_SUFFIXES)


_LATIN_NOUN_CLASS_SUFFIXES = {("a",), ("u", "s"), ("u", "m")}  # 1st / 2nd-masc / 2nd-neut, see latin.yaml's own word_classes


def test_latin_biased_language_gives_its_noun_entries_a_real_declension():
    # seed=1 rolls Latin's own real word_classes adoption for NOUN and
    # actually assigns (not deviates) at least one core-vocabulary noun.
    spec = GenerationSpec(prompt="test", seed=1, traits=TraitProfile(source_languages=("Latin",)))
    language = generate_language("Test", spec, FakeLLMClient())
    nouns = [e for e in language.lexicon.entries if e.pos is PartOfSpeech.NOUN]
    assert nouns
    classed_nouns = [e for e in nouns if e.word_class is not None]
    assert classed_nouns
    for entry in classed_nouns:
        assert entry.word_class in {"1st declension", "2nd declension (masculine)", "2nd declension (neuter)"}
        assert any(entry.ipa.endswith("".join(suffix)) for suffix in _LATIN_NOUN_CLASS_SUFFIXES)


def test_swahili_biased_language_gives_its_noun_entries_a_real_class_prefix():
    # seed=2 rolls Swahili's own real word_classes adoption for NOUN and
    # actually assigns (not deviates) at least one core-vocabulary noun.
    spec = GenerationSpec(prompt="test", seed=2, traits=TraitProfile(source_languages=("Swahili",)))
    language = generate_language("Test", spec, FakeLLMClient())
    nouns = [e for e in language.lexicon.entries if e.pos is PartOfSpeech.NOUN]
    assert nouns
    classed_nouns = [e for e in nouns if e.word_class is not None]
    assert classed_nouns
    real_prefixes = {"m", "ji", "ki", "n", "u"}
    for entry in classed_nouns:
        assert entry.word_class.startswith("class")
        unstressed = entry.ipa.replace(STRESS_MARK, "")  # the mark can land on the word's own first syllable too
        assert any(unstressed.startswith(prefix) for prefix in real_prefixes)


def test_grammatical_spelling_convention_survives_evolution_with_no_new_source_language():
    # seed=1 -- see test_german_biased_language_capitalizes_its_noun_entries's
    # own comment for why this moved here.
    spec = GenerationSpec(prompt="test", seed=1, traits=TraitProfile(source_languages=("German",)))
    base = generate_language("Base", spec, FakeLLMClient())
    assert PartOfSpeech.NOUN in base.romanization.grammatical_spelling.capitalized_pos

    evolved = evolve_language("Evolved", base, years=200, traits=TraitProfile(), seed=1)
    assert evolved.romanization.grammatical_spelling == base.romanization.grammatical_spelling
    nouns = [e for e in evolved.lexicon.entries if e.pos is PartOfSpeech.NOUN]
    assert nouns
    assert all(entry.romanization[:1].isupper() for entry in nouns)
