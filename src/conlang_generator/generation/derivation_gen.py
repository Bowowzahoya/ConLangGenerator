"""Derivation and compounding: new words made from words the language already has, instead of
coined from nothing.

A language may have *derivational* affixes (agent "-er", abstract "-ness", negative "un-", diminutive
"-let", adjectival "-y"): an English word such as "teacher", "happiness" or "unhappy" that the language
has no word for is built from its base ("teach", "happy") plus the language's own exponent for that
rule. A language may also derive *non-concatenatively* -- a changed root vowel instead of an affix
(``ABLAUT_RULES``, ``DerivationRule.stem_change``) -- the real mechanism behind English's own (mostly
fossilized) "sing"/"song", "die"/"death". A language may also *compound* two nouns ("moonlight" = moon
+ light, or the hyphenated "river-bank"), the modifier first or the head first, joined by a linking
vowel or not.

The rules are the language's (``GrammarProfile.derivations``, ``compounding``...), drawn from one
independent rng stream, last of all; the English side is a small closed analyser (suffix
heuristics) that only proposes a base the language really has.

``traits.compound_likelihood`` (``should_attempt_word_formation``/``relation_for`` below) decides,
for any gloss, *whether* it gets a chance at being realized this way at all and *what* it's related
to -- a curated list (``word_relations.WORD_RELATIONS``) or the configured LLM
(``GenerationSpec.word_formation``) -- independent of (and prior to) the English-surface-form
heuristic above, which stays as a fallback for genuinely novel vocabulary neither source covers. See
``translation.translator``'s own ``_build_from_relation``/``_resolve_component`` for where an
already-decided relation actually gets assembled into a real word, at both fresh-generation and
translation time."""

from __future__ import annotations

import random

from conlang_generator.core.grammar import DerivationRule, GrammarProfile, InflectionAffix, MorphologicalType
from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure
from conlang_generator.generation import paradigm_gen, word_builder
from conlang_generator.generation.trait_bias import biased_probability
from conlang_generator.generation.word_relations import WORD_RELATIONS, WordRelation
from conlang_generator.llm.base import LLMRequest

RULES = (
    ("agent", "verb", "noun"),
    ("abstract", "adjective", "noun"),
    ("negative", "adjective", "adjective"),
    ("diminutive", "noun", "noun"),
    ("adjectival", "noun", "adjective"),
)
ABLAUT_RULES = (
    ("ablaut_v2n", "verb", "noun", "ablaut"),
)
"""Non-concatenative derivation -- a changed root vowel instead of an affix, the real mechanism
behind English's own (now mostly fossilized) "sing"/"song", "die"/"death", "live"/"life" -- see
``core.grammar.DerivationRule.stem_change`` and ``GrammarProfile.derivation_stem_maps`` (built from
``paradigm_gen.build_stem_maps``, the same table/applier inflection's own umlaut-plural mechanism
already uses, just rolled independently here). Only ``verb``/``noun`` for now -- the only direction
this project's own curated ``word_relations.WORD_RELATIONS`` entries actually need; a real language
could have more (adjective/verb ablaut pairs exist too), left for whenever a real curated example
needs one, not invented speculatively."""
_ABLAUT_RATE = {
    MorphologicalType.ISOLATING: 0.05, MorphologicalType.AGGLUTINATIVE: 0.15,
    MorphologicalType.FUSIONAL: 0.45, MorphologicalType.POLYSYNTHETIC: 0.20,
}
"""Fusional languages weighted highest -- real Germanic-style ablaut is a fusional-typology
phenomenon (fossilized strong verbs), not an isolating/agglutinative one; still nonzero everywhere,
since non-concatenative derivation isn't exclusively a fusional-language property."""
_COMPOUND_ELEMENT_WEIGHTS = {
    True: ((2, 85), (3, 13), (4, 2)),
    False: ((2, 65), (3, 28), (4, 7)),
}
"""Keyed by whether this language actually compounds at all -- real compounding is overwhelmingly
2-element cross-linguistically (Chinese-style), even more so for languages whose own typology
favors heavy compounding (``_COMPOUND_RATE``'s own isolating-highest skew) -- longer *surface*
compounds are usually nested binary ones (a compound-of-a-compound), not literally 5-way splits."""
_RULE_RATE = {
    MorphologicalType.ISOLATING: 0.25, MorphologicalType.AGGLUTINATIVE: 0.85,
    MorphologicalType.FUSIONAL: 0.70, MorphologicalType.POLYSYNTHETIC: 0.80,
}
_PREFIX_RATE = {"agent": 0.15, "abstract": 0.15, "negative": 0.75, "diminutive": 0.25, "adjectival": 0.15}
_COMPOUND_RATE = {
    MorphologicalType.ISOLATING: 0.90, MorphologicalType.AGGLUTINATIVE: 0.60,
    MorphologicalType.FUSIONAL: 0.50, MorphologicalType.POLYSYNTHETIC: 0.40,
}
_PATTERN_TEMPLATE = {"agent": "noun-agent", "abstract": "noun-basic", "adjectival": "adjective-basic"}
"""The root-and-pattern template each derivation uses in a templatic language."""
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
        rules.append(
            DerivationRule(
                name=name, pos_in=pos_in, pos_out=pos_out, affix=affix,
                pattern=_PATTERN_TEMPLATE.get(name, "") if grammar.uses_root_and_pattern else "",
            )
        )
    stem_maps = paradigm_gen.build_stem_maps(inventory)
    available_kinds = {kind for kind, pairs in stem_maps if pairs}
    ablaut_rate = _ABLAUT_RATE.get(grammar.morphological_type, 0.2)
    used_kinds: set[str] = set()
    for name, pos_in, pos_out, kind in ABLAUT_RULES:
        if kind not in available_kinds or rng.random() >= ablaut_rate:
            continue
        rules.append(
            DerivationRule(name=name, pos_in=pos_in, pos_out=pos_out, affix=InflectionAffix(label=name), stem_change=kind)
        )
        used_kinds.add(kind)
    derivation_stem_maps = tuple((kind, pairs) for kind, pairs in stem_maps if kind in used_kinds)
    vowels = [v for v in inventory.vowel_symbols() if len(v) == 1]
    linker = (vowels[int(linker_pick * len(vowels))],) if linked and vowels else ()
    element_counts, element_weights = zip(*_COMPOUND_ELEMENT_WEIGHTS[compounding])
    compound_typical_elements = rng.choices(element_counts, weights=element_weights)[0]
    return {
        "derivations": tuple(rules),
        "derivation_stem_maps": derivation_stem_maps,
        "compound_typical_elements": compound_typical_elements,
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


# --- compound_likelihood: should a gloss be realized this way at all, and what's it built from ---


_POS_MULTIPLIER = {
    PartOfSpeech.NOUN: 1.0,
    PartOfSpeech.ADJECTIVE: 0.45,
    PartOfSpeech.VERB: 0.2,
    PartOfSpeech.PRONOUN: 0.0,
    PartOfSpeech.PARTICLE: 0.0,
    PartOfSpeech.NUMERAL: 0.0,
    PartOfSpeech.OTHER: 0.3,
}
"""Real cross-linguistic hierarchy (confirmed in this feature's own design conversation): noun
compounding is by far the most productive type everywhere; adjective compounding is real but rarer,
often itself built from noun+participle; verb-verb compounding is rare/unproductive in English and
most Indo-European (though robustly productive in Japanese/Mandarin/much of Niger-Congo and
Austronesian -- modeling *that* typological split is a separate, not-yet-modeled axis, not attempted
here, see docs/DEFERRED.md's own serial-verb-constructions entry). Closed-class words essentially
never compound synchronically, matching ``lexicon_gen._FUNCTION_LIKE_POS`` exactly."""
_BASE_RATE = 0.15
"""At ``compound_likelihood=0.0``, how often an eligible (non-core, POS-weighted) gloss realizes as
a compound/derived word at all -- illustrative, not a corpus statistic, same honesty standard as
every other curated rate in this project."""


def should_attempt_word_formation(
    rng: random.Random, compound_likelihood: float, pos: PartOfSpeech, is_core_meaning: bool,
) -> bool:
    """Whether this gloss gets a chance at being realized as a compound/derived/ablaut word instead
    of a fresh root -- gated by ``traits.compound_likelihood`` (``trait_bias.biased_probability``),
    the per-part-of-speech multiplier above, and a hard suppression for core/basic vocabulary
    (``is_core_meaning``, the caller's own ``lexicon_gen._CORE_MEANING_GLOSSES`` membership check --
    frequent/basic words are definitionally the ones nothing else has been built from yet). A ``True``
    here only means "try" -- ``relation_for`` below can still come back empty."""
    if is_core_meaning:
        return False
    multiplier = _POS_MULTIPLIER.get(pos, 0.0)
    if multiplier <= 0.0:
        return False
    rate = biased_probability(_BASE_RATE, compound_likelihood) * multiplier
    return rng.random() < rate


def _llm_relation_for(gloss: str, pos: PartOfSpeech, llm_client, model: str) -> WordRelation | None:
    prompt = (
        f"The English word '{gloss}' ({pos.value}). Is it built from other, simpler English words? "
        "If it is a compound of exactly two other English words (e.g. 'moonlight' from 'moon' and "
        "'light'), reply 'COMPOUND: word1 word2'. If it is derived from one simpler base word by a "
        "prefix, suffix, or internal vowel change (e.g. 'teacher' from 'teach', 'death' from 'die'), "
        "reply 'DERIVE: baseword'. If neither, reply 'NONE'. Reply with only that line."
    )
    request = LLMRequest(
        system="You are analyzing English word formation for a constructed-language project.",
        prompt=prompt,
        model=model,
        max_tokens=20,
        purpose="lexicon.decompose",
        metadata={"fake_strategy": "decompose_word", "gloss": gloss},
    )
    text = llm_client.complete(request).text.strip()
    if text.upper().startswith("COMPOUND:"):
        words = text.split(":", 1)[1].split()
        if len(words) == 2:
            return WordRelation("compound", (words[0].lower(), words[1].lower()))
    elif text.upper().startswith("DERIVE:"):
        words = text.split(":", 1)[1].split()
        if words:
            return WordRelation("derive", (words[0].lower(),))
    return None


def relation_for(gloss: str, pos: PartOfSpeech, word_formation: str, llm_client, model: str) -> WordRelation | None:
    """What ``gloss`` is built from -- the curated ``word_relations.WORD_RELATIONS`` table
    (``word_formation="algorithmic"``, no LLM call) or the configured LLM
    (``word_formation="llm"``, reaches any gloss, not just a pre-tabulated one). ``None`` when
    neither source has an answer -- the caller then falls back to coining a fresh root, exactly as
    if ``should_attempt_word_formation`` had said no in the first place."""
    if word_formation == "llm":
        return _llm_relation_for(gloss, pos, llm_client, model)
    return WORD_RELATIONS.get(gloss.lower())
