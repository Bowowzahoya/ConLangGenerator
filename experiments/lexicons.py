"""Real seed vocabularies for evolution scenarios in ``experiments/evolution.py``.

The data now lives in the package (``conlang_generator/generation/
reference_languages/lexicons/*.yaml``, loaded by ``real_lexicon``) so
generation can use it too; this module just exposes each curated language
as a module-level constant (``DUTCH``, ``GERMAN``, ...) of
``(gloss, spelling, ipa)`` tuples, as ``experiments/evolution.py`` expects.
Hand-transcribed and simplified to the project's modeled phoneme set --
close enough for judging the sound-change engine's output, not a rigorous
phonetic corpus.
"""

from __future__ import annotations

from conlang_generator.generation.reference_languages import REFERENCE_LANGUAGES
from conlang_generator.generation.reference_languages.real_lexicon import real_words

for _profile in REFERENCE_LANGUAGES:
    _words = real_words(_profile.name)
    if _words:
        globals()[_profile.name.upper().replace(" ", "_").replace("-", "_")] = tuple(
            (gloss, spelling, ipa) for gloss, (spelling, ipa) in _words.items()
        )
