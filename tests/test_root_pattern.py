import random

from conlang_generator.core.grammar import WordTemplate
from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.phonology import Consonant, Manner, Place, PhonemeInventory, Vowel, VowelBackness, VowelHeight
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.root_pattern import TEMPLATIC_POS, fill_template, generate_root, generate_templates
from conlang_generator.llm.fake_client import FakeLLMClient

_SEEDS = range(60)


def _small_inventory() -> PhonemeInventory:
    return PhonemeInventory(
        consonants=(
            Consonant(ipa="k", place=Place.VELAR, manner=Manner.STOP, voiced=False, prevalence=0.9),
            Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, prevalence=0.9),
            Consonant(ipa="b", place=Place.BILABIAL, manner=Manner.STOP, voiced=True, prevalence=0.9),
        ),
        vowels=(
            Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=0.9),
            Vowel(ipa="aː", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, long=True, prevalence=0.5),
        ),
    )


def test_fill_template_exact_skeletons():
    verb = WordTemplate(name="verb", pos=PartOfSpeech.VERB, skeleton=("C", "a", "C", "a", "C"))
    assert fill_template(verb, ("k", "t", "b")) == "katab"
    place = WordTemplate(name="place", pos=PartOfSpeech.NOUN, skeleton=("m", "a", "C", "C", "a", "C"))
    assert fill_template(place, ("k", "t", "b")) == "maktab"


def test_generate_root_never_repeats_an_adjacent_consonant():
    inventory = _small_inventory()
    rng = random.Random(1)
    for _ in range(500):
        root = generate_root(rng, inventory)
        assert len(root) == 3
        assert root[0] != root[1]
        assert root[1] != root[2]


def test_generate_templates_covers_every_templatic_pos():
    inventory = _small_inventory()
    templates = generate_templates(random.Random(1), inventory)
    covered = {t.pos for t in templates}
    assert TEMPLATIC_POS <= covered


def test_generate_templates_prefers_a_long_vowel_for_the_agent_template_when_available():
    # The agent template's vowel slots should include the long vowel at
    # least once across a handful of seeds, given it's preferred whenever
    # the inventory has one.
    inventory = _small_inventory()
    found_long = any(
        "aː" in next(t for t in generate_templates(random.Random(seed), inventory) if t.name == "noun-agent").skeleton
        for seed in range(20)
    )
    assert found_long


def _find_root_and_pattern_language(seed_range=_SEEDS):
    client = FakeLLMClient()
    for seed in seed_range:
        spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile(contact_languages=("Arabic",)))
        language = generate_language("Test", spec, client)
        if language.grammar.uses_root_and_pattern:
            return language
    raise AssertionError("no seed in range produced a root-and-pattern language")


def test_root_and_pattern_language_entries_have_roots_that_reproduce_their_ipa():
    language = _find_root_and_pattern_language()
    templates_by_pos = {}
    for template in language.grammar.templates:
        templates_by_pos.setdefault(template.pos, []).append(template)

    checked = 0
    for entry in language.lexicon.entries:
        if entry.pos not in TEMPLATIC_POS:
            assert entry.root is None
            continue
        assert entry.root is not None
        # The entry's IPA must be reproducible by filling *some* template
        # for its POS with its own recorded root.
        assert any(fill_template(t, entry.root) == entry.ipa for t in templates_by_pos[entry.pos])
        checked += 1
    assert checked > 0


def test_non_root_and_pattern_language_entries_have_no_root():
    client = FakeLLMClient()
    language = generate_language("Test", GenerationSpec(prompt="p", seed=13), client)
    assert not language.grammar.uses_root_and_pattern
    assert all(entry.root is None for entry in language.lexicon.entries)
