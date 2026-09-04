"""Root-and-pattern (templatic) word formation -- Semitic-style
non-concatenative morphology, where a consonantal root (k-t-b
"write"-related) fills a template to derive related words (kataba "he
wrote", kitāb "book", kātib "writer", maktaba "library").

This models word *shape* only: every templatic word gets authentic
root+template phonotactics. It does not attempt derivational
*relatedness* between words (e.g. coining "writer" by reusing the root
behind an existing "write") -- that needs semantic judgment between an
English gloss and the existing lexicon, LLM territory, not attempted here.
``LexicalEntry.root`` is recorded on every templatic word regardless, so
that future work has the data already in place.

Pure rule-based, no LLM, except the same candidate-then-pick step
``lexicon_gen.propose_word`` already uses (``choose_best_candidate``) --
several root candidates are built, the LLM picks the best-sounding one,
same cheap/cache-friendly shape as everywhere else in this pipeline.
"""

from __future__ import annotations

import random

from conlang_generator.core.grammar import WordTemplate
from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from conlang_generator.core.phonology import PhonemeInventory
from conlang_generator.core.romanization import RomanizationScheme, apply_grammatical_spelling
from conlang_generator.generation import word_builder
from conlang_generator.generation.lexicon_gen import choose_best_candidate
from conlang_generator.llm.base import LLMClient

TEMPLATIC_POS: frozenset[PartOfSpeech] = frozenset({PartOfSpeech.NOUN, PartOfSpeech.VERB, PartOfSpeech.ADJECTIVE})
"""Which parts of speech get root-and-pattern treatment. Pronouns/
particles/numerals stay non-templatic regardless -- real Semitic function
words aren't derived this way either, consistent with this project's own
``lexicon_gen._FUNCTION_LIKE_POS`` special-casing elsewhere."""

_ROOT_SIZE = 3
"""Triliteral -- the dominant real Semitic pattern. Not attempting
biliteral/quadriliteral variation."""


def _template_vowel(rng: random.Random, inventory: PhonemeInventory, prefer_long: bool = False) -> str:
    """One vowel symbol, chosen once for a template and then fixed for
    every word built from it (a real template's vowel pattern doesn't
    vary by root). ``prefer_long`` tries the long-vowel subset first
    (falls back to any vowel if the inventory has none -- not every
    generated language will have rolled phonemic length)."""
    candidates = inventory.vowels
    if prefer_long:
        long_vowels = tuple(v for v in inventory.vowels if v.long)
        if long_vowels:
            candidates = long_vowels
    return word_builder.weighted_choice(rng, candidates).ipa


def generate_templates(rng: random.Random, inventory: PhonemeInventory) -> tuple[WordTemplate, ...]:
    """A small, illustrative template set (real Semitic morphology has
    dozens of "measures" -- this models the pattern, not the inventory),
    each with vowel slots filled from this language's actual generated
    phonemes. One verb template, three noun templates (for real variety
    across different nouns -- a basic shape, an agent/instrument shape
    that prefers a long vowel when available, a place/instrument shape
    with a literal m- prefix), one adjective template."""
    v1 = _template_vowel(rng, inventory)
    v2 = _template_vowel(rng, inventory)
    v3 = _template_vowel(rng, inventory, prefer_long=True)
    v4 = _template_vowel(rng, inventory)
    v5 = _template_vowel(rng, inventory)

    return (
        WordTemplate(name="verb-basic", pos=PartOfSpeech.VERB, skeleton=("C", v1, "C", v1, "C")),
        WordTemplate(name="noun-basic", pos=PartOfSpeech.NOUN, skeleton=("C", v2, "C", "C")),
        WordTemplate(name="noun-agent", pos=PartOfSpeech.NOUN, skeleton=("C", v3, "C", v4, "C")),
        WordTemplate(name="noun-place", pos=PartOfSpeech.NOUN, skeleton=("m", v2, "C", "C", v2, "C")),
        WordTemplate(name="adjective-basic", pos=PartOfSpeech.ADJECTIVE, skeleton=("C", v3, "C", v5, "C")),
    )


def generate_root(rng: random.Random, inventory: PhonemeInventory, size: int = _ROOT_SIZE) -> tuple[str, ...]:
    """``size`` consonants weighted by prevalence, with a simple OCP-style
    constraint: no two *adjacent* root consonants identical (real Semitic
    roots avoid this)."""
    root: list[str] = []
    for _ in range(size):
        candidates = tuple(c for c in inventory.consonants if not root or c.ipa != root[-1])
        if not candidates:
            candidates = inventory.consonants
        root.append(word_builder.weighted_choice(rng, candidates).ipa)
    return tuple(root)


def fill_template(template: WordTemplate, root: tuple[str, ...]) -> str:
    """Walks the skeleton; each ``"C"`` consumes the next unused root
    consonant, everything else (this template's own fixed vowel/affix)
    passes through verbatim."""
    root_iter = iter(root)
    return "".join(next(root_iter) if slot == "C" else slot for slot in template.skeleton)


def template_for_pos(rng: random.Random, templates: tuple[WordTemplate, ...], pos: PartOfSpeech) -> WordTemplate:
    matching = tuple(t for t in templates if t.pos is pos)
    return rng.choice(matching) if matching else rng.choice(templates)


def propose_templatic_word(
    rng: random.Random,
    inventory: PhonemeInventory,
    templates: tuple[WordTemplate, ...],
    romanization: RomanizationScheme,
    gloss: str,
    pos: PartOfSpeech,
    llm_client: LLMClient,
    language_name: str,
    num_candidates: int = 5,
    context: str = "",
) -> LexicalEntry:
    """Pick a template matching ``pos`` (varying across same-POS calls,
    for real variety across e.g. multiple nouns), generate several root
    candidates, fill the template with each, and let the LLM pick the
    best-sounding one -- same candidate-then-pick shape as
    ``lexicon_gen.propose_word``."""
    template = template_for_pos(rng, templates, pos)

    seen: set[tuple[str, ...]] = set()
    roots: list[tuple[str, ...]] = []
    for _ in range(num_candidates):
        root = generate_root(rng, inventory)
        if root not in seen:
            seen.add(root)
            roots.append(root)

    candidates = [fill_template(template, root) for root in roots]
    chosen = choose_best_candidate(rng, candidates, gloss, pos, llm_client, language_name, context)
    chosen_root = roots[candidates.index(chosen)]

    return LexicalEntry(
        ipa=chosen,
        romanization=apply_grammatical_spelling(romanization, romanization.apply(chosen), pos),
        glosses=(gloss,),
        pos=pos,
        root=chosen_root,
    )
