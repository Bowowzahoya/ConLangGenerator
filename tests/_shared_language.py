"""A language-generation cache shared across test files.

``generate_language`` is expensive (phonology, a several-hundred-word
lexicon, ~30 grammar passes), and dozens of test files each generate the
same ``(name, prompt, seed)`` combinations -- most often
``("Test", "p", seed)`` -- independently. A cache keyed by those three
values, shared process-wide instead of one private dict per file, means
each distinct combination is only ever built once per test run, no matter
how many files ask for it.
"""

from __future__ import annotations

from conlang_generator.core.language import Language
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.generation.generator import generate_language
from conlang_generator.llm.fake_client import FakeLLMClient

_CACHE: dict[tuple[str, str, int], Language] = {}


def cached_language(seed: int, name: str = "Test", prompt: str = "p") -> Language:
    key = (name, prompt, seed)
    if key not in _CACHE:
        _CACHE[key] = generate_language(name, GenerationSpec(prompt=prompt, seed=seed), FakeLLMClient())
    return _CACHE[key]
