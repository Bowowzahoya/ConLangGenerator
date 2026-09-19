"""Foreign proper names in translation.

A recognized name (the sentence plan's ``"name"`` slot) must not be coined
as an ordinary vocabulary word. How a language treats one is a per-language
trait (``GenerationSpec.foreign_names``): ``"keep"`` uses the name as
written (Dutch-style); ``"adapt"`` re-fits it to the nearest form this
language's own phonology permits (Chinese-style).

A name becomes a ``LexicalEntry`` (``pos=NOUN``, gloss = the name as
written, ``notes=NAME_NOTE``) so it is made once, reused on every later
request and after save/reload, and decodes back to English via ``by_form``
like any other word. ``is_name_entry`` lets ordinary word lookups skip
these entries, so a name like "Rose" never collides with the word "rose".

Adaptation is an approximation, not real loanword phonology: the name's
pronunciation is guessed once (one LLM request, or the deterministic fake
respelling) and fitted to the language by ``generation.phoneme_fit`` --
deterministic, so the same name always yields the same form.
"""

from __future__ import annotations

import unicodedata

from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from conlang_generator.core.romanization import apply_grammatical_spelling
from conlang_generator.core.spec import SeedExample
from conlang_generator.generation import phoneme_fit
from conlang_generator.generation.reference_languages import match_profiles_weighted
from conlang_generator.generation.seed_examples import resolve_seed_examples
from conlang_generator.llm.base import LLMClient

NAME_NOTE = "proper name"

def resolve_foreign_names(language: Language) -> str:
    """``"keep"`` or ``"adapt"``: an explicit ``spec.foreign_names`` wins;
    otherwise the weighted vote of the matched ``source_languages``
    profiles' curated ``foreign_name_handling`` (uncurated profiles
    abstain); otherwise ``"keep"``."""
    explicit = language.spec.foreign_names
    if explicit in ("keep", "adapt"):
        return explicit
    traits = language.spec.traits
    votes = {"keep": 0.0, "adapt": 0.0}
    for profile, weight in match_profiles_weighted(traits.source_languages, traits.source_language_weights):
        if profile.foreign_name_handling in votes:
            votes[profile.foreign_name_handling] += weight
    return "adapt" if votes["adapt"] > votes["keep"] else "keep"


def find_name_entry(language: Language, name: str) -> LexicalEntry | None:
    wanted = unicodedata.normalize("NFC", name).lower()
    for entry in language.lexicon.entries:
        if is_name_entry(entry) and unicodedata.normalize("NFC", entry.primary_gloss).lower() == wanted:
            return entry
    return None


def is_name_entry(entry: LexicalEntry) -> bool:
    return entry.notes == NAME_NOTE


def make_name_entry(language: Language, name: str, llm_client: LLMClient) -> LexicalEntry:
    name = unicodedata.normalize("NFC", name.strip())
    guessed_ipa = resolve_seed_examples((SeedExample(gloss=name, form=name),), llm_client)[0].ipa or ""
    if resolve_foreign_names(language) == "keep":
        return LexicalEntry(
            ipa=guessed_ipa or name.lower(), romanization=name, glosses=(name,),
            pos=PartOfSpeech.NOUN, notes=NAME_NOTE,
        )
    ipa = phoneme_fit.fit_ipa(guessed_ipa, language.phonology, language.syllable_structure)
    latin = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), PartOfSpeech.NOUN)
    latin = latin[:1].upper() + latin[1:]
    return LexicalEntry(ipa=ipa, romanization=latin, glosses=(name,), pos=PartOfSpeech.NOUN, notes=NAME_NOTE)
