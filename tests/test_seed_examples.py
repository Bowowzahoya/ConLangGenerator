import random

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.spec import GenerationSpec, SeedExample, SeedForm
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import phonology_gen
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.seed_examples import (
    parse_bulk_seed_examples,
    parse_seed_forms,
    phonotactic_mismatch_warnings,
    resolve_seed_examples,
    seed_suppletive_entries,
    seed_suppletive_lemmas,
    unused_suppletive_form_warnings,
    valid_forms,
)
from conlang_generator.llm.fake_client import FakeLLMClient


def test_explicit_ipa_is_preserved_unchanged():
    examples = (SeedExample(gloss="water", form="aqua", ipa="akwa"),)
    resolved = resolve_seed_examples(examples, FakeLLMClient())
    assert resolved == examples  # nothing to resolve, no LLM call needed


def test_missing_ipa_gets_filled_in_deterministically():
    examples = (SeedExample(gloss="water", form="aqua"),)
    a = resolve_seed_examples(examples, FakeLLMClient())
    b = resolve_seed_examples(examples, FakeLLMClient())
    assert a[0].ipa is not None
    assert a == b  # deterministic for the same input


def test_a_forms_own_missing_ipa_is_resolved_even_when_the_base_word_already_has_one():
    # resolve_seed_examples used to return early for an already-resolved
    # base word, which would have wrongly skipped resolving its own forms.
    examples = (
        SeedExample(gloss="water", form="aqua", ipa="akwa", forms=(SeedForm(cell="plural", form="aquae"),)),
    )
    resolved = resolve_seed_examples(examples, FakeLLMClient())
    assert resolved[0].ipa == "akwa"  # unchanged
    assert resolved[0].forms[0].ipa is not None


def test_a_forms_own_explicit_ipa_is_preserved_unchanged():
    examples = (
        SeedExample(gloss="water", form="aqua", forms=(SeedForm(cell="plural", form="aquae", ipa="akwai"),)),
    )
    resolved = resolve_seed_examples(examples, FakeLLMClient())
    assert resolved[0].forms[0].ipa == "akwai"


def test_seed_word_appears_verbatim_in_generated_language():
    client = FakeLLMClient()
    examples = (SeedExample(gloss="water", form="aqua", ipa="akwa"),)
    spec = GenerationSpec(prompt="p", seed=5, seed_examples=examples)
    language = generate_language("Test", spec, client)

    entry = language.lexicon.by_gloss("water")
    assert entry is not None
    assert entry.ipa == "akwa"


def test_seed_word_romanization_is_the_users_own_spelling_not_reconstructed():
    # The stored romanization must be `form` itself, not the scheme applied
    # to `ipa` -- a seed word's IPA is often already an approximation (this
    # project doesn't model diphthongs, tone/length nuances, etc.), so
    # reconstructing from it can never recover the real spelling even in
    # principle. Using a spelling with no plausible relationship to the IPA
    # makes any accidental reconstruction-based match implausible.
    client = FakeLLMClient()
    examples = (SeedExample(gloss="water", form="XyZzy", ipa="akwa"),)
    spec = GenerationSpec(prompt="p", seed=5, seed_examples=examples)
    language = generate_language("Test", spec, client)

    entry = language.lexicon.by_gloss("water")
    assert entry is not None
    assert entry.romanization == "XyZzy"


def test_seed_word_phonemes_are_present_in_generated_inventory():
    client = FakeLLMClient()
    # "ʁ" (voiced uvular fricative) has very low base prevalence -- forcing
    # it via a seed example should guarantee its presence regardless.
    examples = (SeedExample(gloss="water", form="test", ipa="aʁa"),)
    spec = GenerationSpec(prompt="p", seed=5, seed_examples=examples)
    language = generate_language("Test", spec, client)

    assert "ʁ" in language.phonology.consonant_symbols()
    assert "a" in language.phonology.vowel_symbols()


def test_seed_example_never_lets_an_unrelated_multichar_phoneme_swallow_two_adjacent_real_ones():
    # Direct, synthetic reproduction of the same tokenizer-ambiguity bug
    # `test_sound_change.py`'s own
    # `test_reconstruction_never_lets_an_unrelated_multichar_phoneme_
    # swallow_two_adjacent_real_ones` guards against, at this project's
    # other structurally-similar call site: `phonology_gen.ALL_CONSONANTS`
    # models a genuine Swahili-style prenasalized stop "nz" as a distinct,
    # unrelated global entry, with nothing to do with this test's own
    # seed example. A seed word whose IPA happens to contain the literal
    # substring "nz" -- here, two real, adjacent single-character
    # phonemes "n" and "z" -- used to get greedily mis-tokenized as the
    # *global* "nz" phoneme when `generate_phonology` scanned
    # `seed_examples` against the full, unrestricted global multi-
    # character pool, wrongly force-including "nz" itself (and neither
    # "n" nor "z" individually) in the generated inventory via
    # `_force_include`. With a matched reference profile that has no
    # "nz" of its own (real French has neither the phoneme nor any
    # multi-character consonant at all), the fix restricts multi-
    # character tokenizer candidates to that profile's own palette, so
    # this now tokenizes as two ordinary single-character phonemes.
    rng = random.Random(0)
    examples = (SeedExample(gloss="test", form="anza", ipa="anza"),)
    spec = GenerationSpec(
        prompt="p", seed=0, seed_examples=examples,
        traits=TraitProfile(source_languages=("French",)),
    )
    inventory, _, _, _ = phonology_gen.generate_phonology(rng, spec)
    assert "n" in inventory.consonant_symbols()
    assert "z" in inventory.consonant_symbols()
    assert "nz" not in inventory.consonant_symbols()


def test_seeded_gloss_is_not_also_generated():
    client = FakeLLMClient()
    examples = (SeedExample(gloss="water", form="aqua", ipa="akwa"),)
    spec = GenerationSpec(prompt="p", seed=5, seed_examples=examples)
    language = generate_language("Test", spec, client)

    water_entries = [e for e in language.lexicon.entries if "water" in e.glosses]
    assert len(water_entries) == 1


# --- part of speech -------------------------------------------------------


def test_a_given_pos_is_honored():
    client = FakeLLMClient()
    examples = (SeedExample(gloss="run", form="zim", ipa="zim", pos=PartOfSpeech.VERB),)
    spec = GenerationSpec(prompt="p", seed=5, seed_examples=examples)
    language = generate_language("Test", spec, client)

    entry = language.lexicon.by_gloss("run")
    assert entry is not None
    assert entry.pos is PartOfSpeech.VERB


def test_an_omitted_pos_still_defaults_to_noun():
    client = FakeLLMClient()
    examples = (SeedExample(gloss="water", form="aqua", ipa="akwa"),)
    spec = GenerationSpec(prompt="p", seed=5, seed_examples=examples)
    language = generate_language("Test", spec, client)

    entry = language.lexicon.by_gloss("water")
    assert entry is not None
    assert entry.pos is PartOfSpeech.NOUN


def test_seed_entries_are_tagged_as_seed_words():
    client = FakeLLMClient()
    examples = (SeedExample(gloss="water", form="aqua", ipa="akwa"),)
    spec = GenerationSpec(prompt="p", seed=5, seed_examples=examples)
    language = generate_language("Test", spec, client)

    entry = language.lexicon.by_gloss("water")
    assert entry is not None
    assert entry.notes == "seed word"


# --- bulk input -------------------------------------------------------------


def test_parse_bulk_seed_examples_reads_gloss_form_ipa_pos():
    text = "water,aqua,akwa,noun\nrun,zim,,verb"
    examples = parse_bulk_seed_examples(text)
    assert examples == (
        SeedExample(gloss="water", form="aqua", ipa="akwa", pos=PartOfSpeech.NOUN),
        SeedExample(gloss="run", form="zim", ipa=None, pos=PartOfSpeech.VERB),
    )


def test_parse_bulk_seed_examples_skips_an_optional_header_row():
    with_header = parse_bulk_seed_examples("gloss,form,ipa,pos\nwater,aqua,akwa,noun")
    without_header = parse_bulk_seed_examples("water,aqua,akwa,noun")
    assert with_header == without_header


def test_parse_bulk_seed_examples_tolerates_missing_optional_columns():
    assert parse_bulk_seed_examples("water,aqua") == (SeedExample(gloss="water", form="aqua"),)


def test_parse_bulk_seed_examples_skips_rows_missing_gloss_or_form_or_with_a_bad_pos():
    text = "\n".join(["water,aqua,akwa,noun", ",missing-gloss", "missing-form,", "bad,pos,,notapos"])
    examples = parse_bulk_seed_examples(text)
    assert examples == (SeedExample(gloss="water", form="aqua", ipa="akwa", pos=PartOfSpeech.NOUN),)


def test_parse_bulk_seed_examples_is_deterministic():
    text = "water,aqua,akwa,noun\nrun,zim,,verb"
    assert parse_bulk_seed_examples(text) == parse_bulk_seed_examples(text)


def test_parse_bulk_seed_examples_reads_a_forms_column():
    examples = parse_bulk_seed_examples("run,zim,zim,verb,past:zanu")
    assert examples[0].forms == (SeedForm(cell="past", form="zanu"),)


def test_parse_bulk_seed_examples_drops_a_form_whose_cell_does_not_match_the_row_pos():
    # Lenient for batch input: the mismatched form is dropped, the base
    # word is still kept (unlike the CLI's --example, which errors).
    examples = parse_bulk_seed_examples("run,zim,zim,verb,plural:zimu")
    assert examples == (SeedExample(gloss="run", form="zim", ipa="zim", pos=PartOfSpeech.VERB),)


# --- irregular (suppletive) forms -------------------------------------------


def test_parse_seed_forms_a_single_form():
    assert parse_seed_forms("past:zanu") == (SeedForm(cell="past", form="zanu"),)


def test_parse_seed_forms_with_an_explicit_ipa():
    assert parse_seed_forms("past:zanu:za.nu") == (SeedForm(cell="past", form="zanu", ipa="za.nu"),)


def test_parse_seed_forms_multiple_forms():
    assert parse_seed_forms("comparative:biko;superlative:bikomo") == (
        SeedForm(cell="comparative", form="biko"),
        SeedForm(cell="superlative", form="bikomo"),
    )


def test_parse_seed_forms_skips_a_malformed_chunk():
    assert parse_seed_forms("past:zanu;nocolon;;") == (SeedForm(cell="past", form="zanu"),)


def test_parse_seed_forms_empty_text_is_empty():
    assert parse_seed_forms("") == ()


def test_valid_forms_filters_by_cell_pos_match():
    example = SeedExample(
        gloss="run", form="zim", pos=PartOfSpeech.VERB,
        forms=(SeedForm(cell="past", form="zanu"), SeedForm(cell="plural", form="zimu")),
    )
    assert valid_forms(example) == (SeedForm(cell="past", form="zanu"),)


def test_valid_forms_defaults_the_examples_own_pos_to_noun():
    example = SeedExample(gloss="stone", form="tek", forms=(SeedForm(cell="plural", form="tekuli"),))
    assert valid_forms(example) == (SeedForm(cell="plural", form="tekuli"),)


def test_seed_suppletive_entries_builds_one_entry_per_valid_form():
    examples = (
        SeedExample(
            gloss="run", form="zim", pos=PartOfSpeech.VERB,
            forms=(SeedForm(cell="past", form="zanu", ipa="zanu"), SeedForm(cell="plural", form="zimu")),
        ),
    )
    entries = seed_suppletive_entries(examples)
    assert len(entries) == 1  # the mismatched "plural" cell is dropped
    entry = entries[0]
    assert entry.glosses == ("run-past",)
    assert entry.romanization == "zanu" and entry.ipa == "zanu"
    assert entry.pos is PartOfSpeech.VERB
    assert entry.notes == "seed word"


def test_seed_suppletive_lemmas_returns_the_right_base_per_cell():
    examples = (
        SeedExample(gloss="run", form="zim", pos=PartOfSpeech.VERB, forms=(SeedForm(cell="past", form="zanu"),)),
        SeedExample(gloss="water", form="aqua"),
    )
    assert seed_suppletive_lemmas(examples, "past") == ("run",)
    assert seed_suppletive_lemmas(examples, "plural") == ()


# --- pronoun-case and extra-tense cells --------------------------------------


def test_valid_forms_rejects_a_pronoun_cell_on_a_non_pronoun_gloss():
    example = SeedExample(
        gloss="stone", form="tek", pos=PartOfSpeech.PRONOUN, forms=(SeedForm(cell="accusative", form="tok"),)
    )
    assert valid_forms(example) == ()


def test_valid_forms_accepts_a_pronoun_cell_on_a_recognized_pronoun_gloss():
    example = SeedExample(
        gloss="I", form="zu", pos=PartOfSpeech.PRONOUN, forms=(SeedForm(cell="accusative", form="zum"),)
    )
    assert valid_forms(example) == (SeedForm(cell="accusative", form="zum"),)


def test_valid_forms_accepts_a_pronoun_cell_on_a_gloss_that_maps_to_a_person():
    # "she" isn't itself a PERSON_LABEL, but it maps to person "he" via
    # pronoun_gen.PERSON_BY_GLOSS -- still a recognized personal pronoun.
    example = SeedExample(
        gloss="she", form="sa", pos=PartOfSpeech.PRONOUN, forms=(SeedForm(cell="genitive", form="sas"),)
    )
    assert valid_forms(example) == (SeedForm(cell="genitive", form="sas"),)


def test_seed_suppletive_entries_builds_a_pronoun_case_entry():
    examples = (
        SeedExample(
            gloss="I", form="zu", pos=PartOfSpeech.PRONOUN,
            forms=(SeedForm(cell="accusative", form="zum", ipa="zum"),),
        ),
    )
    entries = seed_suppletive_entries(examples)
    assert len(entries) == 1
    assert entries[0].glosses == ("i-accusative",)
    assert entries[0].romanization == "zum"
    assert entries[0].pos is PartOfSpeech.PRONOUN


def test_unused_suppletive_form_warnings_is_empty_without_pronoun_or_tense_seed_forms():
    client = FakeLLMClient()
    examples = (SeedExample(gloss="run", form="zim", ipa="zim", pos=PartOfSpeech.VERB,
                             forms=(SeedForm(cell="past", form="zanu", ipa="zanu"),)),)
    spec = GenerationSpec(prompt="p", seed=5, seed_examples=examples)
    language = generate_language("Test", spec, client)
    assert unused_suppletive_form_warnings(language) == []  # "past" is always live


def test_unused_suppletive_form_warnings_fires_for_a_case_the_language_lacks():
    client = FakeLLMClient()
    examples = (
        SeedExample(gloss="I", form="zu", ipa="zu", pos=PartOfSpeech.PRONOUN,
                    forms=(SeedForm(cell="locative", form="zul", ipa="zul"),)),
    )
    # Seed-search for a language with no "locative" case, so the seeded
    # form is guaranteed unused regardless of this test's own seed.
    for seed in range(1, 15):
        spec = GenerationSpec(prompt="p", seed=seed, seed_examples=examples)
        language = generate_language("Test", spec, client)
        if "locative" not in language.grammar.cases:
            warnings = unused_suppletive_form_warnings(language)
            assert len(warnings) == 1
            assert "I" in warnings[0] and "locative" in warnings[0]
            # Still created, just unused -- never silently dropped.
            assert language.lexicon.by_gloss("i-locative") is not None
            return
    raise AssertionError("no seed found without a locative case")


# --- phonotactic-mismatch warning -------------------------------------------


def test_a_wildly_clustered_seed_word_triggers_a_phonotactic_mismatch_warning():
    # Five consonants before the only vowel -- an onset cluster far beyond
    # any realistic generated syllable structure's own max. Confirmed
    # empirically illegal across seeds 1-14, so this doesn't need a seed
    # search.
    client = FakeLLMClient()
    examples = (SeedExample(gloss="test", form="bzdrga", ipa="bzdrga"),)
    spec = GenerationSpec(prompt="p", seed=5, seed_examples=examples)
    language = generate_language("Test", spec, client)

    warnings = phonotactic_mismatch_warnings(language)
    assert len(warnings) == 1
    assert "test" in warnings[0] and "bzdrga" in warnings[0]
    # Never auto-repaired -- the word is kept exactly as given regardless.
    entry = language.lexicon.by_gloss("test")
    assert entry is not None and entry.ipa == "bzdrga" and entry.romanization == "bzdrga"


def test_an_ordinary_seed_word_triggers_no_warning():
    client = FakeLLMClient()
    examples = (SeedExample(gloss="test", form="pa", ipa="pa"),)
    spec = GenerationSpec(prompt="p", seed=5, seed_examples=examples)
    language = generate_language("Test", spec, client)

    assert phonotactic_mismatch_warnings(language) == []
