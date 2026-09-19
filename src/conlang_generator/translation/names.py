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
respelling), each sound maps to the nearest inventory phoneme by feature
distance, and the result is repaired to the language's syllable rules by
inserting an epenthetic vowel where a cluster/coda is illegal (dropping a
consonant only as a last resort). It is deterministic -- no rng -- so the
same name always yields the same form.
"""

from __future__ import annotations

import unicodedata

from conlang_generator.core.language import Language
from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from conlang_generator.core.phonology import (
    Consonant, Manner, PhonemeInventory, Place, SyllableStructure, Vowel, VowelHeight,
)
from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK, apply_grammatical_spelling
from conlang_generator.core.spec import SeedExample
from conlang_generator.generation import ipa_tokenizer, phonology_gen
from conlang_generator.generation.reference_languages import match_profiles_weighted
from conlang_generator.generation.seed_examples import resolve_seed_examples
from conlang_generator.llm.base import LLMClient

NAME_NOTE = "proper name"

_PLACE_ORDER = {place: i for i, place in enumerate(Place)}
_HEIGHT_ORDER = {height: i for i, height in enumerate(VowelHeight)}
_BACKNESS_ORDER = {"front": 0, "central": 1, "back": 2}
_CONSONANT_BY_IPA = {c.ipa: c for c in phonology_gen.ALL_CONSONANTS}
_VOWEL_BY_IPA = {v.ipa: v for v in phonology_gen.ALL_VOWELS}
_ALL_SYMBOLS = tuple(_CONSONANT_BY_IPA) + tuple(_VOWEL_BY_IPA)

# Manners that sound alike enough to substitute at low cost.
_MANNER_COST: dict[frozenset[Manner], float] = {
    frozenset({Manner.STOP, Manner.AFFRICATE}): 1.0,
    frozenset({Manner.FRICATIVE, Manner.AFFRICATE}): 1.0,
    frozenset({Manner.TAP, Manner.TRILL}): 0.5,
    frozenset({Manner.TAP, Manner.APPROXIMANT}): 1.0,
    frozenset({Manner.TRILL, Manner.APPROXIMANT}): 1.5,
    frozenset({Manner.APPROXIMANT, Manner.LATERAL_APPROXIMANT}): 1.0,
    frozenset({Manner.TAP, Manner.LATERAL_APPROXIMANT}): 1.0,
    frozenset({Manner.TRILL, Manner.LATERAL_APPROXIMANT}): 1.5,
    frozenset({Manner.STOP, Manner.FRICATIVE}): 2.0,
    frozenset({Manner.STOP, Manner.NASAL}): 2.0,
}


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
    ipa = adapt_ipa(guessed_ipa, language.phonology, language.syllable_structure)
    latin = apply_grammatical_spelling(language.romanization, language.romanization.apply(ipa), PartOfSpeech.NOUN)
    latin = latin[:1].upper() + latin[1:]
    return LexicalEntry(ipa=ipa, romanization=latin, glosses=(name,), pos=PartOfSpeech.NOUN, notes=NAME_NOTE)


def _consonant_distance(source: Consonant, target: Consonant) -> float:
    if source.ipa == target.ipa:
        return 0.0
    cost = 1.5 * abs(_PLACE_ORDER[source.place] - _PLACE_ORDER[target.place])
    if source.manner is not target.manner:
        cost += _MANNER_COST.get(frozenset({source.manner, target.manner}), 4.0)
    if source.voiced != target.voiced:
        cost += 1.0
    for attribute in ("ejective", "aspirated", "pharyngealized", "long", "palatalized", "breathy"):
        if getattr(source, attribute) != getattr(target, attribute):
            cost += 0.75
    return cost


def _vowel_distance(source: Vowel, target: Vowel) -> float:
    if source.ipa == target.ipa:
        return 0.0
    cost = 1.0 * abs(_HEIGHT_ORDER[source.height] - _HEIGHT_ORDER[target.height])
    cost += 1.5 * abs(_BACKNESS_ORDER[source.backness.value] - _BACKNESS_ORDER[target.backness.value])
    if source.rounded != target.rounded:
        cost += 1.0
    for attribute in ("long", "diphthong", "nasalized"):
        if getattr(source, attribute) != getattr(target, attribute):
            cost += 0.75
    return cost


def _nearest(symbol: str, inventory: PhonemeInventory) -> tuple[str, bool]:
    """The closest inventory phoneme to a foreign ``symbol``, and whether
    it is a vowel."""
    if symbol in _VOWEL_BY_IPA:
        source = _VOWEL_BY_IPA[symbol]
        best = min(inventory.vowels, key=lambda v: (_vowel_distance(source, v), -v.prevalence, v.ipa))
        return best.ipa, True
    source_c = _CONSONANT_BY_IPA[symbol]
    best_c = min(inventory.consonants, key=lambda c: (_consonant_distance(source_c, c), -c.prevalence, c.ipa))
    return best_c.ipa, False


def _epenthetic_vowel(inventory: PhonemeInventory) -> str:
    """The language's own most natural filler vowel: a schwa/central mid
    vowel when it has one, else its most prevalent plain vowel."""
    plain = [v for v in inventory.vowels if not (v.long or v.diphthong or v.nasalized)] or list(inventory.vowels)
    central = [v for v in plain if v.backness.value == "central"]
    return max(central or plain, key=lambda v: (v.prevalence, v.ipa)).ipa


def adapt_ipa(guessed_ipa: str, inventory: PhonemeInventory, structure: SyllableStructure) -> str:
    """Re-fits a guessed foreign pronunciation to ``inventory`` and
    ``structure`` (see the module docstring)."""
    symbols = ipa_tokenizer.symbols_only(guessed_ipa.replace(STRESS_MARK, "").replace(WORD_ACCENT_MARK, ""), _ALL_SYMBOLS)
    epenthetic = _epenthetic_vowel(inventory)
    tokens: list[tuple[str, bool]] = [_nearest(s, inventory) for s in symbols]
    if not any(is_vowel for _, is_vowel in tokens):
        tokens.append((epenthetic, True))

    for _ in range(4 * len(tokens) + 8):
        problem = _first_problem(tokens, structure)
        if problem is None:
            break
        index, drop = problem
        if drop:
            del tokens[index]
        else:
            tokens.insert(index, (epenthetic, True))
        if not any(is_vowel for _, is_vowel in tokens):
            tokens.append((epenthetic, True))
    return "".join(symbol for symbol, _ in tokens)


def _first_problem(tokens: list[tuple[str, bool]], structure: SyllableStructure) -> tuple[int, bool] | None:
    """The first spot where ``tokens`` isn't a legal word, as ``(index,
    drop)``: insert an epenthetic vowel *at* ``index``, or (``drop``) delete
    the consonant there because no vowel can rescue it."""
    nuclei = [i for i, (_, is_vowel) in enumerate(tokens) if is_vowel]
    onset: tuple[str, ...] = ()
    onset_start = 0
    for n, nucleus_index in enumerate(nuclei):
        nucleus = tokens[nucleus_index][0]
        # consonants between this nucleus and the next (or word end)
        run_start = nucleus_index + 1
        run_end = nuclei[n + 1] if n + 1 < len(nuclei) else len(tokens)
        run = tuple(symbol for symbol, _ in tokens[run_start:run_end])
        if n == 0:
            leading = tuple(symbol for symbol, _ in tokens[:nucleus_index])
            if not structure.is_valid_syllable(leading, nucleus, ()):
                return _fix_leading(leading, nucleus, structure)
            onset = leading

        if n + 1 == len(nuclei):
            if structure.is_valid_syllable(onset, nucleus, run):
                return None
            return _fix_final(onset, nucleus, run, run_start, structure)

        next_nucleus = tokens[nuclei[n + 1]][0]
        split = _find_split(onset, nucleus, run, next_nucleus, structure)
        if split is None:
            if len(run) == 1:
                return run_start, True
            return run_start + 1, False
        onset = run[split:]
    return None


def _find_split(
    onset: tuple[str, ...], nucleus: str, run: tuple[str, ...], next_nucleus: str, structure: SyllableStructure
) -> int | None:
    """How many of ``run``'s consonants close this syllable as its coda (the
    rest open the next syllable as its onset) -- maximal onset first."""
    for coda_len in range(len(run) + 1):
        coda, next_onset = run[:coda_len], run[coda_len:]
        if not structure.is_valid_syllable(onset, nucleus, coda):
            continue
        if not structure.is_valid_syllable(next_onset, next_nucleus, ()):
            continue
        if not structure.is_valid_boundary(coda[-1] if coda else None, next_onset[0] if next_onset else None):
            continue
        return coda_len
    return None


def _fix_leading(leading: tuple[str, ...], nucleus: str, structure: SyllableStructure) -> tuple[int, bool]:
    if len(leading) <= 1:
        return 0, True  # a lone consonant this language never allows to open a word
    return 1, False


def _fix_final(
    onset: tuple[str, ...], nucleus: str, coda: tuple[str, ...], coda_start: int, structure: SyllableStructure
) -> tuple[int, bool]:
    if len(coda) == 1:
        return coda_start + 1, False  # give the lone final consonant a vowel to lean on
    return coda_start + 1, False
