"""Real inflection paradigms: declension and conjugation classes, and irregular
lexemes, instead of one invented affix per feature for every word.

The language's existing affixes are its first class (class 0). A noun, verb or
adjective belongs to one class -- a noun's by its gender/class where the language
has one, otherwise by a stable hash of its gloss -- and a further class overrides
some of the labels' suffixes (the rest are shared, as real declensions share cells).
A class may also *pattern* its sharing (``syncretisms``: the accusative spelled like
the nominative, a 2nd person like a 3rd) and change its *stem* in some cells
(``stem_change``: umlaut, ablaut or consonant gradation, drawn from the language's
own ``stem_maps``). An irregular lexeme overrides one or two cells of its own and
may be a strong (ablauting) verb.

Every drawn suffix is distinct, in its group, from the paradigm's other suffixes
(also as spelled), so a form still names its label -- except where a syncretism
makes two cells equal on purpose.

One independent rng stream; it draws after everything else, so no earlier seed
choice shifts."""

from __future__ import annotations

import hashlib
import random

from conlang_generator.core.grammar import GrammarProfile, InflectionAffix, MorphologicalType, Paradigm
from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure, VowelBackness, VowelHeight
from conlang_generator.core.romanization import STRESS_MARK, WORD_ACCENT_MARK
from conlang_generator.generation import inflection_gen, ipa_tokenizer, word_builder

NOUN_FIELDS = ("case_affixes", "number_affixes", "possession_affixes")
VERB_FIELDS = ("tense_affixes", "agreement_affixes", "aspect_affixes", "mood_affixes", "voice_affixes")
ADJECTIVE_FIELDS = ("degree_affixes", "class_affixes")
_TYPE_RATE = {
    MorphologicalType.ISOLATING: 0.10,
    MorphologicalType.AGGLUTINATIVE: 0.30,
    MorphologicalType.FUSIONAL: 0.85,
    MorphologicalType.POLYSYNTHETIC: 0.40,
}
_CHANGE_RATE = 0.55
"""How likely a further class gives a label a suffix of its own (the rest are shared with class 0)."""
_SYNCRETISM_RATE = 0.6
_STEM_CHANGE_RATE = 0.4
CLASS_WEIGHTS = (1.0, 0.6, 0.4, 0.3)
IRREGULAR_NOUNS = ("man", "woman", "child", "dog", "water", "fire", "hand", "eye", "foot", "mother", "father")
IRREGULAR_VERBS = ("be", "go", "see", "eat", "come", "give", "have", "say", "know", "take")
STEM_CHANGES = ("umlaut", "ablaut", "gradation")

NOUN_SYNCRETISMS = (
    ("case_affixes/accusative", "case_affixes/nominative"),   # neuter-like: nominative = accusative
    ("case_affixes/dative", "case_affixes/ablative"),
    ("case_affixes/genitive", "case_affixes/dative"),
    ("case_affixes/ablative", "case_affixes/locative"),
    ("case_affixes/accusative", "case_affixes/genitive"),
    ("number_affixes/dual", "number_affixes/plural"),
)
VERB_SYNCRETISMS = (
    ("agreement_affixes/you", "agreement_affixes/he"),
    ("agreement_affixes/we", "agreement_affixes/you"),
    ("agreement_affixes/he", "agreement_affixes/default"),
    ("tense_affixes/present", "tense_affixes/future"),
    ("aspect_affixes/imperfective", "aspect_affixes/progressive"),
    ("mood_affixes/subjunctive", "mood_affixes/conditional"),
    ("voice_affixes/reflexive", "voice_affixes/reciprocal"),
)
ADJECTIVE_SYNCRETISMS = (
    ("degree_affixes/superlative", "degree_affixes/comparative"),
    ("degree_affixes/excessive", "degree_affixes/elative"),
)


def _spelled(romanization, suffix: tuple[str, ...]):
    return romanization.apply("".join(suffix)).lower() if romanization is not None else suffix


def _fields_for(pos: str):
    return NOUN_FIELDS if pos == "noun" else VERB_FIELDS if pos == "verb" else ADJECTIVE_FIELDS


def _override_labels(grammar: GrammarProfile, field: str) -> list[InflectionAffix]:
    """The base affixes of ``field`` that a paradigm may change."""
    affixes = [a for a in getattr(grammar, field) if a.suffix and not a.prefix]
    if field == "agreement_affixes":
        affixes = [a for a in affixes if a.label in inflection_gen.AGREEMENT_LABELS]  # class agreement stays shared
    return affixes


def _group_taken(grammar: GrammarProfile, pos: str, romanization) -> set:
    """Every suffix, as spelled, that can sit on the same kind of word (the whole
    noun, verb or modifier group, so a number suffix never spells like a case suffix)."""
    fields = (
        inflection_gen._NOUN_SUFFIX_FIELDS if pos == "noun"
        else inflection_gen._VERB_SUFFIX_FIELDS if pos == "verb"
        else inflection_gen._MODIFIER_SUFFIX_FIELDS
    )
    return {
        _spelled(romanization, a.suffix)
        for name in fields
        for a in getattr(grammar, name, ())
        if a.suffix and not a.prefix
    }


def _fresh_suffix(rng, inventory, structure, taken: set, romanization):
    for attempt in range(120):
        suffix = word_builder.build_class_suffix(rng, inventory, structure)
        for _ in range(attempt // 30):
            suffix = suffix + word_builder.build_class_suffix(rng, inventory, structure)
        if _spelled(romanization, suffix) not in taken:
            return suffix
    return None


# --- stems ---------------------------------------------------------------------------------

_HEIGHT_ORDER = [
    VowelHeight.CLOSE, VowelHeight.NEAR_CLOSE, VowelHeight.CLOSE_MID, VowelHeight.MID, VowelHeight.OPEN_MID,
    VowelHeight.NEAR_OPEN, VowelHeight.OPEN,
]


def build_stem_maps(inventory: PhonemeInventory) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    """The language's own stem changes: ``umlaut`` fronts a back vowel to the front
    vowel of the same height and rounding (else the nearest front one), ``ablaut``
    raises a vowel one step towards close (else lowers it), ``gradation`` voices a
    final voiceless consonant. Only pairs the inventory really has."""
    simple = [v for v in inventory.vowels if not v.diphthong and not v.long and not v.nasalized]
    height = {v.ipa: _HEIGHT_ORDER.index(v.height) for v in simple}
    umlaut: list[tuple[str, str]] = []
    ablaut: list[tuple[str, str]] = []
    for v in simple:
        fronted = [w for w in simple if w.backness is VowelBackness.FRONT and w.ipa != v.ipa]
        if v.backness is not VowelBackness.FRONT and fronted:
            best = min(fronted, key=lambda w: (abs(height[w.ipa] - height[v.ipa]), w.rounded != v.rounded))
            umlaut.append((v.ipa, best.ipa))
        same = [w for w in simple if w.backness is v.backness and w.rounded == v.rounded]
        higher = [w for w in same if height[w.ipa] < height[v.ipa]]
        lower = [w for w in same if height[w.ipa] > height[v.ipa]]
        if higher:
            ablaut.append((v.ipa, max(higher, key=lambda w: height[w.ipa]).ipa))
        elif lower:
            ablaut.append((v.ipa, min(lower, key=lambda w: height[w.ipa]).ipa))
    gradation: list[tuple[str, str]] = []
    for c in inventory.consonants:
        if c.voiced or c.ejective or c.aspirated or c.long:
            continue
        twin = next(
            (d for d in inventory.consonants
             if d.voiced and d.place is c.place and d.manner is c.manner and not (d.ejective or d.aspirated or d.long)
             and d.palatalized == c.palatalized),
            None,
        )
        if twin is not None:
            gradation.append((c.ipa, twin.ipa))
    return tuple(
        (kind, tuple(pairs)) for kind, pairs in (("umlaut", umlaut), ("ablaut", ablaut), ("gradation", gradation)) if pairs
    )


def change_stem(
    ipa: str, mapping: dict[str, str], vowel_symbols: frozenset[str], known_symbols, final_consonant: bool
) -> str:
    """``ipa`` with its last mapped vowel (or, for ``final_consonant``, its final
    consonant) replaced by its counterpart; unchanged when there is nothing to map."""
    tokens = ipa_tokenizer.tokenize(ipa, known_symbols)
    marks = (STRESS_MARK, WORD_ACCENT_MARK)
    body = [i for i, (symbol, _) in enumerate(tokens) if symbol not in marks]
    if not body:
        return ipa
    if final_consonant:
        index = body[-1]
        if tokens[index][0] in vowel_symbols or tokens[index][0] not in mapping:
            return ipa
    else:
        candidates = [i for i in body if tokens[i][0] in vowel_symbols and tokens[i][0] in mapping]
        if not candidates:
            return ipa
        index = candidates[-1]
    symbol, deco = tokens[index]
    tokens[index] = (mapping[symbol], deco)
    return "".join(symbol + deco for symbol, deco in tokens)


def _stem_change_for(rng, pos: str, grammar: GrammarProfile, maps: dict[str, tuple]) -> tuple[str, tuple[str, ...]]:
    """A class's stem change and the cells it applies in (``("", ())`` for none)."""
    roll = rng.random()
    pick = rng.random()
    if roll >= _STEM_CHANGE_RATE or pos == "adjective":
        return "", ()
    if pos == "noun":
        kind = "umlaut" if pick < 0.6 else "gradation"
        labels = [a.label for a in grammar.number_affixes]
        cases = [a.label for a in grammar.case_affixes]
        cells = (
            ("number_affixes/plural",) if kind == "umlaut" and "plural" in labels
            else tuple(f"case_affixes/{c}" for c in cases if c in ("genitive", "dative"))
        )
    else:
        kind = "ablaut" if pick < 0.6 else "gradation"
        tenses = [a.label for a in grammar.tense_affixes]
        wanted = "past" if "past" in tenses else (tenses[1] if len(tenses) > 1 else "")
        cells = (f"tense_affixes/{wanted}",) if wanted else ()
    if kind not in maps or not cells:
        return "", ()
    return kind, cells


# --- classes ---------------------------------------------------------------------------------


def _draw_class(rng, name, pos, grammar, inventory, structure, romanization, maps) -> Paradigm:
    overrides: dict[str, InflectionAffix] = {}
    taken = _group_taken(grammar, pos, romanization)
    for field in _fields_for(pos):
        changeable = {a.label for a in _override_labels(grammar, field)}
        for affix in getattr(grammar, field):
            if affix.label not in changeable or rng.random() >= _CHANGE_RATE:
                continue
            suffix = _fresh_suffix(rng, inventory, structure, taken, romanization)
            if suffix is None:
                continue
            taken.add(_spelled(romanization, suffix))
            overrides[f"{field}/{affix.label}"] = InflectionAffix(label=f"{field}/{affix.label}", suffix=suffix)

    def effective(cell: str):
        if cell in overrides:
            return overrides[cell].suffix
        field, _, label = cell.partition("/")
        base = next((a for a in getattr(grammar, field) if a.label == label and a.suffix and not a.prefix), None)
        return base.suffix if base is not None else None

    patterns = (
        NOUN_SYNCRETISMS if pos == "noun" else VERB_SYNCRETISMS if pos == "verb" else ADJECTIVE_SYNCRETISMS
    )
    used: list[str] = []
    for target, source in patterns:
        if rng.random() >= _SYNCRETISM_RATE or len(used) >= 2:
            continue
        shared, wanted = effective(source), effective(target)
        if shared is None or wanted is None or shared == wanted:
            continue
        overrides[target] = InflectionAffix(label=target, suffix=shared)
        used.append(f"{target}={source}")
    kind, cells = _stem_change_for(rng, pos, grammar, maps)
    return Paradigm(
        name=name, pos=pos, overrides=tuple(overrides.values()), syncretisms=tuple(used), stem_change=kind,
        stem_cells=cells,
    )


def _draw_irregulars(
    rng, candidates, pos: str, grammar, inventory, structure, romanization, classes, maps
) -> list[Paradigm]:
    found: list[Paradigm] = []
    for gloss in candidates:
        if rng.random() >= 0.3:
            continue
        chosen: list[InflectionAffix] = []
        for field in _fields_for(pos):
            options = _override_labels(grammar, field)
            if not options or rng.random() >= 0.6:
                continue
            affix = options[int(rng.random() * len(options))]
            taken = (
                _group_taken(grammar, pos, romanization)
                | {_spelled(romanization, a.suffix) for a in chosen}
                | {_spelled(romanization, o.suffix) for cls in classes for o in cls.overrides}
            )
            suffix = _fresh_suffix(rng, inventory, structure, taken, romanization)
            if suffix is not None:
                chosen.append(InflectionAffix(label=f"{field}/{affix.label}", suffix=suffix))
        kind, cells = _stem_change_for(rng, pos, grammar, maps) if pos == "verb" else ("", ())
        if chosen or kind:
            found.append(Paradigm(name=gloss, pos=pos, overrides=tuple(chosen), stem_change=kind, stem_cells=cells))
    return found


def roll_paradigms(
    rng: random.Random,
    grammar: GrammarProfile,
    inventory: PhonemeInventory,
    structure: SyllableStructure,
    romanization=None,
) -> dict[str, tuple]:
    """The extra declension, conjugation and adjective classes, the irregular
    lexemes and the language's stem-change maps."""
    rate = _TYPE_RATE.get(grammar.morphological_type, 0.3)
    noun_gate = rng.random() < rate and bool(grammar.case_affixes or grammar.number_affixes)
    verb_gate = rng.random() < rate and bool(grammar.tense_affixes or grammar.agreement_affixes)
    adjective_gate = rng.random() < rate and bool(grammar.degree_affixes or grammar.class_affixes)
    extra_nouns = 1 + int(rng.random() * 3)
    extra_verbs = 1 + int(rng.random() * 2)
    extra_adjectives = 1 + int(rng.random() * 2)
    irregular_gate = rng.random() < min(1.0, rate + 0.2)
    stem_maps = build_stem_maps(inventory)
    maps = dict(stem_maps)
    nouns = tuple(
        _draw_class(rng, f"declension-{k + 2}", "noun", grammar, inventory, structure, romanization, maps)
        for k in range(extra_nouns)
    ) if noun_gate else ()
    verbs = tuple(
        _draw_class(rng, f"conjugation-{k + 2}", "verb", grammar, inventory, structure, romanization, maps)
        for k in range(extra_verbs)
    ) if verb_gate else ()
    adjectives = tuple(
        _draw_class(rng, f"adjective-class-{k + 2}", "adjective", grammar, inventory, structure, romanization, maps)
        for k in range(extra_adjectives)
    ) if adjective_gate else ()
    irregulars: tuple[Paradigm, ...] = ()
    if irregular_gate:
        irregulars = tuple(
            _draw_irregulars(rng, IRREGULAR_NOUNS, "noun", grammar, inventory, structure, romanization, nouns, maps)
            + _draw_irregulars(rng, IRREGULAR_VERBS, "verb", grammar, inventory, structure, romanization, verbs, maps)
        )

    def keep(paradigms):  # a class that changed nothing is not a class
        return tuple(p for p in paradigms if p.overrides or p.stem_change)

    result: dict[str, tuple] = {
        "noun_paradigms": keep(nouns), "verb_paradigms": keep(verbs), "adjective_paradigms": keep(adjectives),
        "irregular_lexemes": irregulars,
    }
    used = {p.stem_change for group in result.values() for p in group if p.stem_change}
    result["stem_maps"] = tuple((kind, pairs) for kind, pairs in stem_maps if kind in used)
    return result


def class_index(seed: int, pos: str, gloss: str, count: int) -> int:
    """Which class (0 = the language's base affixes) a word with this gloss belongs to,
    among ``count`` classes, by a stable weighted hash."""
    if count <= 1:
        return 0
    digest = hashlib.sha256(f"{seed}:paradigm:{pos}:{gloss}".encode()).digest()
    unit = int.from_bytes(digest[:8], "big") / 2**64
    weights = CLASS_WEIGHTS[:count] + (CLASS_WEIGHTS[-1],) * max(0, count - len(CLASS_WEIGHTS))
    total = sum(weights)
    cumulative = 0.0
    for index, weight in enumerate(weights):
        cumulative += weight / total
        if unit < cumulative:
            return index
    return count - 1
