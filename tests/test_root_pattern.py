import random

from conlang_generator.core.grammar import WordTemplate
from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.phonology import (
    Consonant,
    Manner,
    Place,
    PhonemeInventory,
    SyllableStructure,
    Vowel,
    VowelBackness,
    VowelHeight,
)
from conlang_generator.core.romanization import STRESS_MARK
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.root_pattern import (
    TEMPLATIC_POS,
    _root_violates_structure,
    fill_template,
    generate_root,
    generate_templates,
    propose_templatic_word,
    template_for_pos,
)
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


def test_generate_root_never_includes_a_geminate_consonant():
    # Real Semitic roots are always sequences of plain consonants --
    # gemination (real Arabic shadda) is a property the *template*
    # imposes on an ordinary radical (Form II verbs double the middle
    # one), never an inherent property of the root's own letters. A
    # geminate consonant weighted heavily enough to dominate the draw
    # would still never show up as a root member if this holds.
    inventory = PhonemeInventory(
        consonants=(
            Consonant(ipa="k", place=Place.VELAR, manner=Manner.STOP, voiced=False, prevalence=0.1),
            Consonant(ipa="t", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, prevalence=0.1),
            Consonant(ipa="kː", place=Place.VELAR, manner=Manner.STOP, voiced=False, long=True, prevalence=0.99),
        ),
        vowels=(Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=0.9),),
    )
    rng = random.Random(1)
    for _ in range(200):
        root = generate_root(rng, inventory)
        assert "kː" not in root


def test_generate_root_falls_back_to_all_consonants_when_every_one_is_a_geminate():
    # Defensive-fallback guard: if a hypothetical inventory somehow had
    # *only* geminate consonants, the plain-consonants filter would empty
    # the pool entirely -- generate_root must fall back to the full
    # (all-geminate) inventory rather than crash or return an empty root.
    inventory = PhonemeInventory(
        consonants=(
            Consonant(ipa="kː", place=Place.VELAR, manner=Manner.STOP, voiced=False, long=True, prevalence=0.9),
            Consonant(ipa="tː", place=Place.ALVEOLAR, manner=Manner.STOP, voiced=False, long=True, prevalence=0.9),
        ),
        vowels=(Vowel(ipa="a", height=VowelHeight.OPEN, backness=VowelBackness.CENTRAL, rounded=False, prevalence=0.9),),
    )
    root = generate_root(random.Random(1), inventory)
    assert len(root) == 3


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
        spec = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile(source_languages=("Arabic",)))
        language = generate_language("Test", spec, client)
        if language.grammar.uses_root_and_pattern:
            return language
    raise AssertionError("no seed in range produced a root-and-pattern language")


def test_root_and_pattern_language_entries_have_roots_that_reproduce_their_ipa():
    language = _find_root_and_pattern_language()
    templates_by_pos = {}
    for template in language.grammar.templates:
        templates_by_pos.setdefault(template.pos, []).append(template)
    classes_by_name = {c.name: c for c in language.grammar.word_classes}

    checked = 0
    for entry in language.lexicon.entries:
        if entry.pos not in TEMPLATIC_POS:
            assert entry.root is None
            continue
        assert entry.root is not None
        # The entry's IPA must be reproducible by filling *some* template
        # for its POS with its own recorded root -- modulo the embedded
        # stress mark, which `fill_template` itself knows nothing about
        # (stress is a separate post-processing step, see
        # `root_pattern.propose_templatic_word`'s own docstring), and
        # modulo any word_class prefix/suffix (real Arabic's own
        # feminine -a marker, applied *after* the template is filled --
        # see word_class_gen.py -- so it must be stripped back off
        # before comparing against the template-filled form).
        bare_ipa = entry.ipa.replace(STRESS_MARK, "")
        if entry.word_class is not None:
            cls = classes_by_name[entry.word_class]
            prefix, suffix = "".join(cls.prefix), "".join(cls.suffix)
            assert bare_ipa.startswith(prefix) and bare_ipa.endswith(suffix)
            end = len(bare_ipa) - len(suffix)
            bare_ipa = bare_ipa[len(prefix) : end]
        assert any(fill_template(t, entry.root) == bare_ipa for t in templates_by_pos[entry.pos])
        checked += 1
    assert checked > 0


def test_non_root_and_pattern_language_entries_have_no_root():
    client = FakeLLMClient()
    language = generate_language("Test", GenerationSpec(prompt="p", seed=13), client)
    assert not language.grammar.uses_root_and_pattern
    assert all(entry.root is None for entry in language.lexicon.entries)


# --- Structure-aware root generation (templatic words respecting phonotactics) ---


def test_root_violates_structure_catches_an_onset_restricted_consonant():
    skeleton = ("C", "a", "C", "a", "C")
    structure = SyllableStructure(excluded_onset_consonants=("k",))
    assert _root_violates_structure(skeleton, ("k", "t", "b"), structure, _small_inventory())
    # Every non-final slot in this skeleton sits directly before "a" --
    # a genuine onset (real "ka.tab"-style syllabification: both "k" and
    # "t" open a syllable, only "b" closes one) -- so "k" only avoids the
    # restriction in the skeleton's last (coda) slot.
    assert not _root_violates_structure(skeleton, ("t", "b", "k"), structure, _small_inventory())


def test_root_violates_structure_catches_an_excluded_onset_nucleus_pair():
    skeleton = ("C", "a", "C", "a", "C")
    structure = SyllableStructure(excluded_onset_nucleus_pairs=(("k", "a"),))
    assert _root_violates_structure(skeleton, ("k", "t", "b"), structure, _small_inventory())
    # "k" lands in the skeleton's *last* slot here (word-final, no fixed
    # vowel follows it) -- the only position not immediately before "a".
    assert not _root_violates_structure(skeleton, ("t", "b", "k"), structure, _small_inventory())


def test_root_violates_structure_catches_an_excluded_nucleus_coda_pair():
    # "noun-place"-shaped: m-a-C-C-a-C -- the second "C" (index 3) is
    # word-final, preceded by another "C" (a genuine coda cluster), not a
    # fixed vowel, so it doesn't exercise this check. Use a simpler
    # skeleton with a genuine single coda before a word boundary.
    skeleton = ("C", "a", "C")
    structure = SyllableStructure(excluded_nucleus_coda_pairs=(("a", "b"),))
    assert _root_violates_structure(skeleton, ("k", "b"), structure, _small_inventory())
    assert not _root_violates_structure(skeleton, ("k", "t"), structure, _small_inventory())


def test_root_violates_structure_ignores_an_intervocalic_consonant_for_nucleus_coda():
    # A single consonant sitting between two fixed vowels is the *next*
    # syllable's onset under the maximal-onset principle, never the
    # previous syllable's coda -- the nucleus-coda check must not apply
    # to it even though a vowel immediately precedes it.
    skeleton = ("C", "a", "C", "a", "C")
    structure = SyllableStructure(excluded_nucleus_coda_pairs=(("a", "t"),))
    # "t" (root[1]) sits at index 2, preceded by "a" and followed by "a" --
    # intervocalic, so this must NOT be flagged by the nucleus-coda check.
    assert not _root_violates_structure(skeleton, ("k", "t", "b"), structure, _small_inventory())


def test_root_violates_structure_catches_a_restricted_coda_consonant():
    skeleton = ("C", "a", "C", "a", "C")
    structure = SyllableStructure(excluded_coda_consonants=("b",))
    assert _root_violates_structure(skeleton, ("k", "t", "b"), structure, _small_inventory())
    assert not _root_violates_structure(skeleton, ("b", "t", "k"), structure, _small_inventory())  # b not word-final here


def test_root_violates_structure_catches_an_illegal_adjacent_cluster():
    # "noun-basic"-shaped: C-a-C-C, the trailing CC is a genuine cluster.
    skeleton = ("C", "a", "C", "C")
    inventory = _small_inventory()
    # t (stop) + b (stop) has flat sonority -- not a legal cluster either
    # direction (onset needs rising, coda needs falling).
    structure = SyllableStructure()
    assert _root_violates_structure(skeleton, ("k", "t", "b"), structure, inventory)


def test_generate_root_with_structure_never_returns_a_violating_root():
    inventory = _small_inventory()
    skeleton = ("C", "a", "C", "a", "C")
    structure = SyllableStructure(excluded_onset_consonants=("k",), excluded_coda_consonants=("b",))
    rng = random.Random(1)
    for _ in range(200):
        root = generate_root(rng, inventory, structure, skeleton)
        assert not _root_violates_structure(skeleton, root, structure, inventory)


def test_generate_root_falls_back_gracefully_when_nothing_satisfies_the_structure():
    # An impossible structure (every consonant excluded from onset) must
    # still return a root within the attempt bound, not hang or crash.
    inventory = _small_inventory()
    skeleton = ("C", "a", "C", "a", "C")
    structure = SyllableStructure(excluded_onset_consonants=tuple(c.ipa for c in inventory.consonants))
    root = generate_root(random.Random(1), inventory, structure, skeleton)
    assert len(root) == 3


def test_forced_templatic_word_for_english_never_puts_w_before_a_rounded_vowel():
    # Reproduces the original bug directly: build English's real
    # strictness=1.0 inventory/SyllableStructure (which excludes
    # w+u/o/ʊ), then force the root-and-pattern path -- bypassing
    # grammar's own low-probability roll entirely -- against every one
    # of its own templates, and confirm no generated word violates the
    # restriction.
    from conlang_generator.generation import phonology_gen

    spec = GenerationSpec(
        prompt="p", seed=1, traits=TraitProfile(source_languages=("English",), source_language_strictness=1.0)
    )
    inventory, structure, _, _ = phonology_gen.generate_phonology(random.Random(1), spec)
    assert ("w", "u") in structure.excluded_onset_nucleus_pairs  # sanity: this run's structure really is restricted

    templates = generate_templates(random.Random(1), inventory)
    rng = random.Random(2)
    for _ in range(300):
        for pos in TEMPLATIC_POS:
            template = template_for_pos(rng, templates, pos)
            root = generate_root(rng, inventory, structure, template.skeleton)
            word = fill_template(template, root)
            for i in range(len(word) - 1):
                assert not (word[i] == "w" and word[i + 1] in ("u", "o", "ʊ")), word
