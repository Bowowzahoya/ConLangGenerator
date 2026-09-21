"""The pool, the reference profiles and the real lexicons write every /g/ as ASCII "g".

The strict-IPA script g (U+0261) used to appear only in ``gʱ``, ``gb`` and the click clusters,
so a lexicon or profile author had to know which one to type. Normalized; this keeps it so.
"""

from pathlib import Path

from conlang_generator.generation import phonology_gen
from conlang_generator.generation.reference_languages import REFERENCE_LANGUAGES

_SCRIPT_G = "\u0261"
_PACKAGE = Path(phonology_gen.__file__).resolve().parent


def test_no_pool_symbol_contains_the_script_g():
    symbols = [c.ipa for c in phonology_gen.ALL_CONSONANTS] + [v.ipa for v in phonology_gen.ALL_VOWELS]
    assert not [s for s in symbols if _SCRIPT_G in s]
    assert "gʱ" in symbols and "gb" in symbols


def test_no_profile_symbol_contains_the_script_g():
    assert not [(p.name, s) for p in REFERENCE_LANGUAGES for s in p.symbols() if _SCRIPT_G in s]


def test_no_yaml_or_python_source_contains_the_script_g():
    offenders = [
        str(path.relative_to(_PACKAGE))
        for path in _PACKAGE.rglob("*")
        if path.suffix in {".py", ".yaml"} and _SCRIPT_G in path.read_text(encoding="utf-8")
        and path.name != "test_pool_uses_ascii_g.py"
    ]
    assert not offenders


def test_a_prenasalized_symbol_does_not_eat_the_start_of_a_breathy_one():
    # Sanskrit ŋ + gʱ (jaṅghā): with an ASCII g the greedy match would read the prenasalized
    # "ŋg" and strand the breathy mark.
    from conlang_generator.generation import ipa_tokenizer

    known = ("ŋg", "ŋ", "gʱ", "g", "a", "dʒ", "aː")
    assert ipa_tokenizer.tokenize("dʒaŋgʱaː", known) == [("dʒ", ""), ("a", ""), ("ŋ", ""), ("gʱ", ""), ("aː", "")]
    assert ipa_tokenizer.tokenize("aŋga", known) == [("a", ""), ("ŋg", ""), ("a", "")]  # plain ŋg still reads as a unit
