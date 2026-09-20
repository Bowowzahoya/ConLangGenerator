"""Audit of the curated real lexicons against their own reference profiles.

Every curated word is checked two ways:

* **off-inventory** -- it uses a sound the profile does not list (either a
  transcription slip, or a profile that is missing a sound the language
  really has);
* **structure** -- its sounds are all in the profile, but syllabified with
  the profile's own phonotactics (max onset/coda, allowed clusters,
  restricted onset/coda consonants, onset+nucleus / nucleus+coda pairs) the
  word is not a legal one.

The structure comes from a strict-source-language phonology generation
(sound strictness 1.0), with one correction: generation randomly *thins* the
cluster list, so the audit uses the profile's whole curated cluster list
(restricted to sonority-legal pairs), or the full sonority-legal closure when
the profile curates none -- the audit should flag real transcription
problems, not the luck of a seed.

Run it with ``conlang audit-lexicons``. It is advisory: a flagged word is a
prompt to look at the transcription *or* the profile, and either may be the
thing that is wrong.
"""

from __future__ import annotations

import functools
import random
from collections import Counter
from dataclasses import dataclass, field

from conlang_generator.core.phonology import SyllableStructure
from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK
from conlang_generator.core.spec import GenerationSpec
from conlang_generator.core.traits import TraitProfile
from conlang_generator.generation import ipa_tokenizer, phoneme_fit, phonology_gen, sonority
from conlang_generator.generation.reference_languages import REFERENCE_LANGUAGES, ReferenceLanguageProfile
from conlang_generator.generation.reference_languages.real_lexicon import real_words

_CONSONANTS = {c.ipa: c for c in phonology_gen.ALL_CONSONANTS}
_VOWEL_SYMBOLS = frozenset(v.ipa for v in phonology_gen.ALL_VOWELS)
_GLOBAL = tuple(_CONSONANTS) + tuple(_VOWEL_SYMBOLS)
_SINGLE = tuple(s for s in _GLOBAL if len(s) == 1)


@functools.lru_cache(maxsize=None)
def _known_symbols(name: str) -> tuple[str, ...]:
    """The symbols ``name``'s words are tokenized with: every single-character
    sound, the profile's own multi-character sounds, and any other pool symbol
    that cannot be spelled as a sequence of those (``aː``, ``tʃʰ``). A pool
    symbol that *can* (prenasalized ``nd``, an affricate ``ts`` the profile
    doesn't list) is read as its parts -- otherwise ``andare`` would be
    tokenized with a prenasalized stop it doesn't have."""
    profile = next(p for p in REFERENCE_LANGUAGES if p.name == name)
    base = _SINGLE + tuple(s for s in profile.symbols() if len(s) > 1)
    extra = tuple(
        s for s in _GLOBAL
        if len(s) > 1 and s not in base
        and "".join(sym + deco for sym, deco in ipa_tokenizer.tokenize(s, base)) != s
    )
    return base + extra + (STRESS_MARK, WORD_ACCENT_MARK)


@dataclass(frozen=True)
class WordIssue:
    gloss: str
    spelling: str
    ipa: str
    detail: str


@dataclass
class LanguageAudit:
    name: str
    words: int
    off_inventory: list[WordIssue] = field(default_factory=list)
    structure: list[WordIssue] = field(default_factory=list)
    off_symbols: Counter = field(default_factory=Counter)
    illegal_runs: Counter = field(default_factory=Counter)
    """``(position, consonant run)`` -> how many words have that illegal run,
    e.g. ``("initial", "pt")`` or ``("final", "ms")``."""

    @property
    def flagged(self) -> int:
        return len(self.off_inventory) + len(self.structure)

    @property
    def flagged_rate(self) -> float:
        return self.flagged / self.words if self.words else 0.0


@functools.lru_cache(maxsize=None)
def profile_structure(name: str) -> SyllableStructure:
    """The syllable structure the audit holds ``name``'s words to (see the
    module docstring)."""
    profile = next(p for p in REFERENCE_LANGUAGES if p.name == name)
    spec = GenerationSpec(
        prompt="audit", seed=0, traits=TraitProfile(source_languages=(name,), source_language_strictness=1.0)
    )
    _, structure, _, _ = phonology_gen.generate_phonology(random.Random(0), spec)
    updates: dict = {}
    consonants = tuple(_CONSONANTS[s] for s in profile.consonants if s in _CONSONANTS)
    # generation rolls whether clusters exist at all; the audit takes the
    # profile's word for it
    if profile.max_onset >= 2:
        structure = structure.model_copy(update={"max_onset": 2})
    if profile.max_coda is not None and profile.max_coda >= 2 and structure.max_coda != 0:
        structure = structure.model_copy(update={"max_coda": 2})
    elif profile.attested_coda_clusters and structure.max_coda == 1 and profile.coda_profile == "unrestricted":
        structure = structure.model_copy(update={"max_coda": 2})
    if structure.max_onset >= 2:
        pairs = sonority.legal_onset_pairs(consonants)
        attested = set(profile.attested_onset_clusters)
        updates["allowed_onset_clusters"] = (
            tuple(p for p in sonority.with_attested(pairs, tuple(sorted(attested)), consonants) if p in attested)
            if attested else pairs
        )
    if structure.max_coda != 0 and (structure.max_coda or 0) >= 2:
        pairs = sonority.legal_coda_pairs(consonants)
        attested = set(profile.attested_coda_clusters)
        updates["allowed_coda_clusters"] = (
            tuple(p for p in sonority.with_attested(pairs, tuple(sorted(attested)), consonants) if p in attested)
            if attested else pairs
        )
    symbols = set(profile.consonants)
    triples = {
        "allowed_onset_triples": tuple(t for t in profile.attested_onset_triples if all(s in symbols for s in t)),
        "allowed_coda_triples": tuple(t for t in profile.attested_coda_triples if all(s in symbols for s in t)),
    }
    if triples["allowed_onset_triples"] and structure.max_onset >= 2:
        updates["allowed_onset_triples"] = triples["allowed_onset_triples"]
    if triples["allowed_coda_triples"] and structure.max_coda >= 2:
        updates["allowed_coda_triples"] = triples["allowed_coda_triples"]
    return structure.model_copy(update=updates) if updates else structure


def _tokens(ipa: str, name: str) -> list[tuple[str, bool]]:
    """``(symbol, is_vowel)`` for the word's sounds, without tone/stress marks."""
    return [
        (symbol, symbol in _VOWEL_SYMBOLS)
        for symbol, _ in ipa_tokenizer.tokenize(ipa, _known_symbols(name))
        if symbol not in (STRESS_MARK, WORD_ACCENT_MARK)
    ]


def _run_around(tokens: list[tuple[str, bool]], index: int) -> tuple[str, str]:
    """The consonant run a problem at ``index`` belongs to, as ``(position,
    run)`` with position ``initial``/``medial``/``final`` (or ``all`` for a
    word with no run to blame, e.g. a lone vowel-less word)."""
    n = len(tokens)
    at = min(index, n - 1)
    if tokens[at][1] and at > 0 and not tokens[at - 1][1]:
        at -= 1  # the problem is at a vowel boundary: blame the consonants just before it
    if tokens[at][1]:
        return "all", tokens[at][0]
    start = at
    while start > 0 and not tokens[start - 1][1]:
        start -= 1
    end = at
    while end + 1 < n and not tokens[end + 1][1]:
        end += 1
    position = "initial" if start == 0 else "final" if end == n - 1 else "medial"
    return position, "".join(s for s, _ in tokens[start:end + 1])


def audit_language(profile: ReferenceLanguageProfile) -> LanguageAudit:
    words = real_words(profile.name)
    audit = LanguageAudit(profile.name, len(words))
    inventory = profile.symbols()
    structure = profile_structure(profile.name)
    for gloss, (spelling, ipa) in words.items():
        tokens = _tokens(ipa, profile.name)
        outside = [s for s, _ in tokens if s not in inventory]
        if outside:
            audit.off_symbols.update(dict.fromkeys(set(outside), 1))
            audit.off_inventory.append(WordIssue(gloss, spelling, ipa, "not in the profile: " + " ".join(sorted(set(outside)))))
            continue
        problem = phoneme_fit.first_problem(list(tokens), structure)
        if problem is not None:
            index, drop = problem
            symbols = [s for s, _ in tokens]
            marked = " ".join(symbols[:index] + ["|"] + symbols[index:])
            position, run = _run_around(tokens, index)
            audit.illegal_runs[(position, run)] += 1
            audit.structure.append(
                WordIssue(gloss, spelling, ipa, ("illegal consonant" if drop else "illegal cluster/coda") + f" at {marked}")
            )
    return audit


def audit_all(names: tuple[str, ...] | None = None) -> list[LanguageAudit]:
    """Audits every curated language (or just ``names``), worst first."""
    audits = [
        audit_language(p)
        for p in REFERENCE_LANGUAGES
        if real_words(p.name) and (names is None or p.name.lower() in {n.lower() for n in names})
    ]
    return sorted(audits, key=lambda a: -a.flagged_rate)


def format_report(audits: list[LanguageAudit], examples: int = 0) -> str:
    """A summary table, then (with ``examples`` > 0) up to that many flagged
    words per language and the most common off-profile sounds."""
    lines = [f"{'language':<16}{'words':>6}{'off-profile':>13}{'structure':>11}{'flagged':>9}"]
    for a in audits:
        lines.append(
            f"{a.name:<16}{a.words:>6}{len(a.off_inventory):>13}{len(a.structure):>11}{a.flagged_rate:>8.0%} "
        )
    total = sum(a.words for a in audits)
    flagged = sum(a.flagged for a in audits)
    lines.append(f"{'all':<16}{total:>6}{'':>13}{'':>11}{(flagged / total if total else 0):>8.0%} ")
    if examples:
        for a in audits:
            if not a.flagged:
                continue
            lines.append("")
            lines.append(f"{a.name}:")
            if a.off_symbols:
                lines.append("  sounds not in the profile: " + ", ".join(f"{s} x{n}" for s, n in a.off_symbols.most_common(8)))
            if a.illegal_runs:
                lines.append(
                    "  illegal consonant runs: "
                    + ", ".join(f"{pos} {run} x{n}" for (pos, run), n in a.illegal_runs.most_common(10))
                )
            for issue in (a.off_inventory + a.structure)[:examples]:
                lines.append(f"  {issue.gloss:<12}{issue.spelling:<18}/{issue.ipa}/  {issue.detail}")
    return "\n".join(lines)
