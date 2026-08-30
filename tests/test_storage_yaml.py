from pathlib import Path

from conlang_generator.storage.yaml_backend import YamlLanguageRepository
from tests.factories import make_minimal_language


def test_save_then_load_round_trips(tmp_path: Path):
    repo = YamlLanguageRepository(tmp_path)
    language = make_minimal_language()

    repo.save(language)
    loaded = repo.load(language.name)

    assert loaded == language


def test_list_and_exists(tmp_path: Path):
    repo = YamlLanguageRepository(tmp_path)
    assert repo.list() == []
    assert not repo.exists("Test Tongue")

    repo.save(make_minimal_language())

    assert repo.list() == ["test-tongue"]
    assert repo.exists("Test Tongue")


def test_load_missing_language_raises(tmp_path: Path):
    repo = YamlLanguageRepository(tmp_path)
    try:
        repo.load("nope")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass
