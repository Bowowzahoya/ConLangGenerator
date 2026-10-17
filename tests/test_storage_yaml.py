from pathlib import Path

from conlang_generator.core.language import Language
from conlang_generator.storage.yaml_backend import _FILE_FIELDS, YamlLanguageRepository
from tests.factories import make_minimal_language


def test_save_then_load_round_trips(tmp_path: Path):
    repo = YamlLanguageRepository(tmp_path)
    language = make_minimal_language()

    repo.save(language)
    loaded = repo.load(language.name)

    assert loaded == language


def test_every_language_field_is_covered_by_file_fields():
    # A field missing from _FILE_FIELDS isn't an error anywhere -- save()
    # just never writes it, and load()'s model_validate() silently falls
    # back to that field's own pydantic default, so a round-trip test
    # using only default values (like the one above) can't catch this.
    # Caught in practice: word_accent and (at introduction) script were
    # both missing this way, discarded on every real save/load with no
    # error. This test instead checks structural coverage directly, so a
    # future new Language field can't repeat it silently.
    covered = {field for fields in _FILE_FIELDS.values() for field in fields}
    assert covered == set(Language.model_fields)


def test_list_and_exists(tmp_path: Path):
    repo = YamlLanguageRepository(tmp_path)
    assert repo.list() == []
    assert not repo.exists("Test Tongue")

    repo.save(make_minimal_language())

    assert repo.list() == ["test-tongue"]
    assert repo.exists("Test Tongue")


def test_a_generated_script_survives_a_real_save_and_load(tmp_path: Path):
    import random

    from conlang_generator.generation.script_gen import generate_script

    repo = YamlLanguageRepository(tmp_path)
    language = make_minimal_language()
    script = generate_script(random.Random(1), language.phonology)
    language = language.model_copy(update={"script": script})

    repo.save(language)
    loaded = repo.load(language.name)

    assert loaded.script == script


def test_load_missing_language_raises(tmp_path: Path):
    repo = YamlLanguageRepository(tmp_path)
    try:
        repo.load("nope")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass
