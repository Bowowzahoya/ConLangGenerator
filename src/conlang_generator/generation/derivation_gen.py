"""Derivation and compounding: new words made from words the language already has, instead of
coined from nothing.

A language may have *derivational* affixes (agent "-er", abstract "-ness", negative "un-", diminutive
"-let", adjectival "-y"): an English word such as "teacher", "happiness" or "unhappy" that the language
has no word for is built from its base ("teach", "happy") plus the language's own exponent for that
rule. A language may also *compound* two nouns ("moonlight" = moon + light, or the hyphenated
"river-bank"), the modifier first or the head first, joined by a linking vowel or not.

The rules are the language's (``GrammarProfile.derivations``, ``compounding``...), drawn from one
independent rng stream, last of all; the English side is a small closed analyser (suffix
heuristics) that only proposes a base the language really has."""

from __future__ import annotations

import random

from conlang_generator.core.grammar import DerivationRule, GrammarProfile, InflectionAffix, MorphologicalType
from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure
from conlang_generator.generation import word_builder

RULES = (
    ("agent", "verb", "noun"),
    ("abstract", "adjective", "noun"),
    ("negative", "adjective", "adjective"),
    ("diminutive", "noun", "noun"),
    ("adjectival", "noun", "adjective"),
)
_RULE_RATE = {
    MorphologicalType.ISOLATING: 0.25, MorphologicalType.AGGLUTINATIVE: 0.85,
    MorphologicalType.FUSIONAL: 0.70, MorphologicalType.POLYSYNTHETIC: 0.80,
}
_PREFIX_RATE = {"agent": 0.15, "abstract": 0.15, "negative": 0.75, "diminutive": 0.25, "adjectival": 0.15}
_COMPOUND_RATE = {
    MorphologicalType.ISOLATING: 0.90, MorphologicalType.AGGLUTINATIVE: 0.60,
    MorphologicalType.FUSIONAL: 0.50, MorphologicalType.POLYSYNTHETIC: 0.40,
}
_ENGLISH_ONLY = frozenset({"river", "silver", "water", "mother", "father", "brother", "sister", "hammer"})


def roll_derivation(
    rng: random.Random,
    grammar: GrammarProfile,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    romanization=None,
) -> dict[str, object]:
    """The derivational rules, compounding and its order/linker (every draw always made)."""
    rate = _RULE_RATE.get(grammar.morphological_type, 0.6)
    present = [rng.random() < rate for _ in RULES]
    as_prefix = [rng.random() for _ in RULES]
    compounding = rng.random() < _COMPOUND_RATE.get(grammar.morphological_type, 0.5)
    head_first = rng.random() < 0.2
    linked = rng.random() < 0.4
    linker_pick = rng.random()

    def spelled(symbols):
        return romanization.apply("".join(symbols)).lower() if romanization is not None else symbols

    rules: list[DerivationRule] = []
    taken: set = set()
    for (name, pos_in, pos_out), here, prefix_roll in zip(RULES, present, as_prefix):
        if not here:
            continue
        exponent: tuple[str, ...] = ()
        for _ in range(60):
            if prefix_roll < _PREFIX_RATE[name]:
                onset, nucleus, _coda = word_builder._build_syllable_parts(rng, inventory, structure)
                exponent = tuple(onset[:1]) + (nucleus,)
            else:
                exponent = word_builder.build_class_suffix(rng, inventory, structure)
            if spelled(exponent) not in taken:
                break
        taken.add(spelled(exponent))
        affix = (
            InflectionAffix(label=name, prefix=exponent)
            if prefix_roll < _PREFIX_RATE[name]
            else InflectionAffix(label=name, suffix=exponent)
        )
        rules.append(DerivationRule(name=name, pos_in=pos_in, pos_out=pos_out, affix=affix))
    vowels = [v for v in inventory.vowel_symbols() if len(v) == 1]
    linker = (vowels[int(linker_pick * len(vowels))],) if linked and vowels else ()
    return {
        "derivations": tuple(rules),
        "compounding": compounding,
        "compound_order": "head_modifier" if head_first else "modifier_head",
        "compound_linker": linker if compounding else (),
    }


# --- the English side ---------------------------------------------------------------------------


def _undouble(stem: str) -> list[str]:
    """Spelling repairs before a suffix: dancer -> danc(e), runner -> run, happiness -> happy."""
    out = [stem, stem + "e"]
    if len(stem) >= 3 and stem[-1] == stem[-2]:
        out.append(stem[:-1])
    if stem.endswith("i"):
        out.append(stem[:-1] + "y")
    return out


def english_derivations(token: str) -> list[tuple[str, list[str]]]:
    """``[(rule name, base candidates)]`` an English word could be derived by, most likely first
    (a closed suffix analyser; the caller checks that a base really exists)."""
    word = token.strip().lower()
    if not word.isalpha() or word in _ENGLISH_ONLY:
        return []
    found: list[tuple[str, list[str]]] = []
    if len(word) >= 5 and word.endswith(("er", "or")):
        found.append(("agent", _undouble(word[:-2])))
    if len(word) >= 7 and word.endswith("ness"):
        found.append(("abstract", _undouble(word[:-4])))
    if len(word) >= 5 and word.startswith("un"):
        found.append(("negative", [word[2:]]))
    if len(word) >= 7 and word.endswith("ling"):
        found.append(("diminutive", _undouble(word[:-4])))
    if len(word) >= 6 and word.endswith("let"):
        found.append(("diminutive", _undouble(word[:-3])))
    if len(word) >= 5 and word.endswith("y"):
        found.append(("adjectival", _undouble(word[:-1])))
    if len(word) >= 6 and word.endswith("ful"):
        found.append(("adjectival", _undouble(word[:-3])))
    return found


def compound_splits(token: str, is_noun) -> list[tuple[str, str]]:
    """``(modifier, head)`` splits of a hyphenated or solid English compound whose parts
    ``is_noun`` accepts, the most balanced split first."""
    word = token.strip().lower()
    if "-" in word:
        left, _, right = word.partition("-")
        return [(left, right)] if left.isalpha() and right.isalpha() and is_noun(left) and is_noun(right) else []
    if not word.isalpha() or len(word) < 6:
        return []
    splits = [(word[:i], word[i:]) for i in range(3, len(word) - 2)]
    good = [(a, b) for a, b in splits if is_noun(a) and is_noun(b)]
    return sorted(good, key=lambda pair: -min(len(pair[0]), len(pair[1])))
