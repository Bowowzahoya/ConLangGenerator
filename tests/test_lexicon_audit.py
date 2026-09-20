"""The curated-lexicon audit: flags words a reference profile cannot produce,
reads sounds relative to the profile (no phantom prenasalized stops), and is
reachable from the CLI."""

from typer.testing import CliRunner

from conlang_generator.cli.main import app
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation.reference_languages import REFERENCE_LANGUAGES, lexicon_audit


def _profile(name):
    return next(p for p in REFERENCE_LANGUAGES if p.name == name)


def _audit_words(monkeypatch, language, words):
    monkeypatch.setattr(lexicon_audit, "real_words", lambda name: words if name == language else {})
    return lexicon_audit.audit_language(_profile(language))


def test_a_sound_outside_the_profile_is_flagged_and_counted(monkeypatch):
    audit = _audit_words(monkeypatch, "Finnish", {"a": ("kala", "kala"), "b": ("gala", "ʈala"), "c": ("gula", "ʈula")})
    assert audit.words == 3 and len(audit.off_inventory) == 2
    assert audit.off_symbols["ʈ"] == 2 and audit.flagged_rate == 2 / 3


def test_an_illegal_cluster_is_flagged_with_its_position(monkeypatch):
    audit = _audit_words(monkeypatch, "Finnish", {"a": ("ptak", "ptak"), "b": ("kala", "kala")})
    assert [i.gloss for i in audit.structure] == ["a"]
    assert audit.illegal_runs[("initial", "pt")] == 1


def test_a_legal_word_is_not_flagged(monkeypatch):
    audit = _audit_words(monkeypatch, "Finnish", {"a": ("kala", "kala"), "b": ("talo", "talo"), "c": ("kuu", "kuː")})
    assert audit.flagged == 0


def test_a_profile_without_prenasalized_stops_reads_nd_as_n_plus_d():
    # Italian "andare" must not be audited as containing the pool's prenasalized /nd/.
    for name in ("Italian", "Spanish", "Turkish", "Latin", "Portuguese"):
        audit = lexicon_audit.audit_language(_profile(name))
        assert not {"nd", "mb", "ŋg", "nz"} & set(audit.off_symbols), name


def test_a_profile_that_lists_prenasalized_stops_keeps_them():
    known = lexicon_audit._known_symbols("Swahili")
    assert "mb" in known and "nd" in known
    assert "nd" not in lexicon_audit._known_symbols("Italian")


def test_the_report_summarizes_and_lists_examples():
    audits = lexicon_audit.audit_all(("Finnish", "Malay"))
    report = lexicon_audit.format_report(audits, examples=2)
    assert report.splitlines()[0].startswith("language")
    assert "Finnish" in report and "Malay" in report and "illegal consonant runs" in report
    assert all(a.flagged == len(a.off_inventory) + len(a.structure) for a in audits)


def test_the_cli_command_reports_and_can_fail_on_a_threshold():
    runner = CliRunner()
    ok = runner.invoke(app, ["audit-lexicons", "Yoruba"])
    assert ok.exit_code == 0 and "Yoruba" in ok.output
    strict = runner.invoke(app, ["audit-lexicons", "Finnish", "--fail-above", "0.0"])
    assert strict.exit_code == 1
    assert runner.invoke(app, ["audit-lexicons", "NoSuchLanguage"]).exit_code == 1


def test_attested_pairs_bypass_the_sonority_check():
    from conlang_generator.generation import phonology_gen, sonority

    consonants = tuple(c for c in phonology_gen.ALL_CONSONANTS if c.ipa in ("s", "t", "ʃ", "p"))
    base = sonority.legal_onset_pairs(consonants)
    assert ("ʃ", "t") not in base  # falling sonority, not the plain s+stop exception
    assert ("ʃ", "t") in sonority.with_attested(base, (("ʃ", "t"), ("x", "y")), consonants)  # unknown sounds ignored
    assert ("x", "y") not in sonority.with_attested(base, (("x", "y"),), consonants)


def test_german_words_can_end_in_uvular_r():
    from conlang_generator.generation.reference_languages import lexicon_audit

    structure = lexicon_audit.profile_structure("German")
    assert "ʁ" not in structure.excluded_coda_consonants


def test_final_devoicing_only_bars_word_final_codas():
    from conlang_generator.core.phonology import SyllableStructure

    structure = SyllableStructure(max_coda=1, excluded_final_coda_consonants=("d",))
    assert structure.is_valid_syllable((), "a", ("d",))  # medial coda: fine
    assert not structure.is_valid_syllable((), "a", ("d",), final=True)
    assert structure.is_valid_syllable((), "a", ("t",), final=True)


def test_generated_strict_russian_words_never_end_in_a_voiced_obstruent():
    import random

    from conlang_generator.generation import phonology_gen, word_builder

    for seed in range(15):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("Russian",), source_language_strictness=1.0)
        )
        inventory, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        if not structure.excluded_final_coda_consonants:
            continue
        rng = random.Random(seed)
        for _ in range(60):
            word = word_builder.build_word(rng, inventory, structure, rng.choice((1, 2, 3)))
            assert word[-1] not in structure.excluded_final_coda_consonants, word


def test_turkish_keeps_its_voiced_fricatives_word_finally():
    import random

    from conlang_generator.generation import phonology_gen

    spec = GenerationSpec(
        prompt="p", seed=3, traits=TraitProfile(source_languages=("Turkish",), source_language_strictness=1.0)
    )
    _, structure, _, _ = phonology_gen.generate_phonology(random.Random(3), spec)
    assert "z" not in structure.excluded_final_coda_consonants


def test_reference_only_geminate_twins_exist_and_are_never_drawn():
    from conlang_generator.generation import phonology_gen

    twins = {c.ipa for c in phonology_gen._REFERENCE_ONLY_CONSONANTS if c.long}
    assert {"bː", "mː", "rː", "tʃː", "dˤː"} <= twins
    assert not twins & {c.ipa for c in phonology_gen._DRAWN_CONSONANTS}


def test_italian_words_carry_real_geminates_and_pass_the_audit():
    from conlang_generator.generation.reference_languages.real_lexicon import real_words

    ipa = real_words("Italian")
    assert any("tː" in v[1] for v in ipa.values())  # fatto/otto-style words use one long consonant, not "tt"
    assert not any("tt" in v[1].replace("tts", "") for v in ipa.values())  # (/tts/ is a geminate affricate, not modeled)


def test_strict_italian_geminates_are_medial_only():
    import random

    from conlang_generator.generation import phonology_gen, word_builder

    for seed in range(15):
        spec = GenerationSpec(
            prompt="p", seed=seed, traits=TraitProfile(source_languages=("Italian",), source_language_strictness=1.0)
        )
        inventory, structure, _, _ = phonology_gen.generate_phonology(random.Random(seed), spec)
        rng = random.Random(seed)
        for _ in range(60):
            word = word_builder.build_word(rng, inventory, structure, rng.choice((1, 2, 3)))
            plain = word.replace("ˈ", "")
            assert not plain.endswith(("kː", "tː", "pː", "sː", "nː", "lː", "mː", "rː", "fː", "bː")), word


def test_three_consonant_onsets_and_codas_need_a_listed_triple():
    from conlang_generator.core.phonology import SyllableStructure

    structure = SyllableStructure(
        max_onset=2, max_coda=2,
        allowed_onset_clusters=(("s", "t"), ("t", "r")), allowed_coda_clusters=(("n", "t"),),
        allowed_onset_triples=(("s", "t", "r"),), allowed_coda_triples=(("n", "t", "s"),),
    )
    assert structure.is_valid_syllable(("s", "t", "r"), "a", ())
    assert not structure.is_valid_syllable(("s", "p", "r"), "a", ())
    assert structure.is_valid_syllable((), "a", ("n", "t", "s"))
    assert not structure.is_valid_syllable((), "a", ("n", "t", "s", "k"))
    # without any triple listed, three consonants are never legal
    assert not SyllableStructure(max_onset=2, allowed_onset_clusters=(("s", "t"),)).is_valid_syllable(("s", "t", "r"), "a", ())


def test_strict_english_generates_str_words_and_invented_languages_do_not():
    import random

    from conlang_generator.generation import phonology_gen, word_builder

    spec = GenerationSpec(prompt="p", seed=4, traits=TraitProfile(source_languages=("English",), source_language_strictness=1.0))
    inventory, structure, _, _ = phonology_gen.generate_phonology(random.Random(4), spec)
    for seed in range(8):  # the cluster roll decides per seed; most strict English seeds get triples
        s = GenerationSpec(prompt="p", seed=seed, traits=TraitProfile(source_languages=("English",), source_language_strictness=1.0))
        inv, st, _, _ = phonology_gen.generate_phonology(random.Random(seed), s)
        symbols = {c.ipa for c in inv.consonants}
        assert all(x in symbols for triple in st.allowed_onset_triples for x in triple)
        if st.allowed_onset_triples:
            break
    else:
        raise AssertionError("no strict English seed produced onset triples")
    plain = GenerationSpec(prompt="p", seed=4, traits=TraitProfile())
    _, plain_structure, _, _ = phonology_gen.generate_phonology(random.Random(4), plain)
    assert plain_structure.allowed_onset_triples == () and plain_structure.allowed_coda_triples == ()
    rng = random.Random(1)
    for _ in range(200):
        word = word_builder.build_word(rng, inventory, structure, 2)
        assert word  # builds without tripping the syllable-validity assertion


def test_audit_structure_carries_the_profiles_triples():
    structure = lexicon_audit.profile_structure("English")
    assert ("s", "t", "r") in structure.allowed_onset_triples


def test_old_norse_and_icelandic_lexicons_fit_their_profiles_and_allow_final_geminates():
    for name in ("Old Norse", "Icelandic"):
        (audit,) = lexicon_audit.audit_all((name,))
        assert not audit.off_inventory, (name, audit.off_symbols)
        assert audit.flagged_rate < 0.05, name
    icelandic = next(p for p in REFERENCE_LANGUAGES if p.name == "Icelandic")
    assert icelandic.final_geminates and {"iː", "aː", "ɔː"} <= set(icelandic.vowels)
    assert "ŋ" in icelandic.restricted_onset_consonants


def test_mandarin_and_korean_lexicons_fit_their_profiles():
    for name in ("Mandarin", "Korean"):
        (audit,) = lexicon_audit.audit_all((name,))
        assert not audit.off_inventory, (name, audit.off_symbols)
        assert audit.flagged_rate < 0.03, name
    mandarin = next(p for p in REFERENCE_LANGUAGES if p.name == "Mandarin")
    assert {"tʰ", "tɕʰ", "tsʰ", "ə", "ɨ", "ɛ", "ɥ"} <= set(mandarin.symbols())
    assert ("ɕ", "j") in mandarin.attested_onset_clusters  # medial glides are onset clusters


def test_cantonese_tibetan_tamil_and_hindi_lexicons_fit_their_profiles():
    for name, limit in (("Cantonese", 0.01), ("Tibetan", 0.01), ("Tamil", 0.03), ("Hindi", 0.02)):
        (audit,) = lexicon_audit.audit_all((name,))
        assert audit.flagged_rate <= limit, (name, audit.flagged_rate)
    by_name = {p.name: p for p in REFERENCE_LANGUAGES}
    assert {"ɔ", "ø", "œ", "y"} <= set(by_name["Cantonese"].vowels)
    assert "ʔ" in by_name["Tibetan"].consonants and "ʔ" in by_name["Tibetan"].restricted_onset_consonants
    assert "ʈ" not in by_name["Tamil"].restricted_onset_consonants  # medial ʈ needs an onset slot
