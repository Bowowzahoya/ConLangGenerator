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
from conlang_generator.core.phonology import PhonemeInventory, SyllableStructure, WordAccentSystem
from conlang_generator.core.romanization import RomanizationScheme, apply_grammatical_spelling
from conlang_generator.generation import sonority, stress_gen, word_accent_gen, word_builder
from conlang_generator.generation.lexicon_gen import choose_best_candidate
from conlang_generator.generation.reference_languages import match_profiles
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


_MAX_ROOT_ATTEMPTS = 20


def _root_violates_structure(
    skeleton: tuple[str, ...],
    root: tuple[str, ...],
    structure: SyllableStructure,
    inventory: PhonemeInventory,
) -> bool:
    """Whether filling `skeleton` with `root` would break any of
    `structure`'s onset/coda/onset-nucleus/nucleus-coda restrictions --
    checked locally at each ``"C"`` slot's immediate skeleton neighbors (a
    fixed vowel/literal, another ``"C"``, or a word boundary), the same
    adjacency-only spirit `SyllableStructure.is_valid_syllable`'s own
    onset+nucleus check already uses, rather than a full syllable
    re-parse of the flat root+template string. Not checking the
    cross-syllable coda-onset boundary here -- a flat, unsyllabified
    skeleton has no clean notion of "end of one syllable, start of the
    next" beyond the two-adjacent-``"C"`` cluster case already handled
    below."""
    vowel_symbols = frozenset(v.ipa for v in inventory.vowels)
    consonant_by_ipa = {c.ipa: c for c in inventory.consonants}
    root_iter = iter(root)
    filled = tuple(next(root_iter) if slot == "C" else slot for slot in skeleton)
    last_index = len(filled) - 1

    for i, slot in enumerate(skeleton):
        if slot != "C":
            continue
        symbol = filled[i]
        following_is_root_slot = i < last_index and skeleton[i + 1] == "C"
        following = filled[i + 1] if i < last_index else None
        preceding = filled[i - 1] if i > 0 else None

        intervocalic_onset = following is not None and following in vowel_symbols
        if preceding is not None and preceding in vowel_symbols and not intervocalic_onset:
            # Immediately preceded by a fixed vowel, and NOT also
            # immediately followed by one -- a genuine coda position
            # adjacent to that vowel's nucleus. A single consonant
            # sitting *between* two vowels is excluded here: under the
            # maximal-onset principle (the same one
            # `sonority.legal_onset_pairs`'s own docstring invokes), an
            # intervocalic single consonant is the *next* syllable's
            # onset, never the previous syllable's coda -- it's already
            # covered by the onset+nucleus branch below.
            pair = (preceding, symbol)
            if structure.allowed_nucleus_coda_pairs is not None and pair not in structure.allowed_nucleus_coda_pairs:
                return True
            if pair in structure.excluded_nucleus_coda_pairs:
                return True

        if following is None:
            # Word-final: this is a coda position (the cluster case below
            # separately checks the *pair* when the slot right before it
            # is also root-derived -- this still correctly covers the
            # single-consonant coda case, and matches
            # `is_valid_syllable`'s own "only the cluster's final member
            # is checked" precedent for a 2-consonant coda).
            if symbol in structure.excluded_coda_consonants:
                return True
        elif following in vowel_symbols:
            # Immediately followed by a fixed vowel -- a genuine onset,
            # whether or not another root consonant precedes it (a
            # cluster's own last member is still the one directly
            # adjacent to the nucleus).
            if symbol in structure.excluded_onset_consonants:
                return True
            pair = (symbol, following)
            if structure.allowed_onset_nucleus_pairs is not None and pair not in structure.allowed_onset_nucleus_pairs:
                return True
            if pair in structure.excluded_onset_nucleus_pairs:
                return True

        # Two root consonants back-to-back -- a genuine cluster. Checked
        # once here (keyed on the first member) against the generic
        # sonority rule only, deliberately not the further-thinned
        # allowed_onset_clusters/allowed_coda_clusters sets (those are
        # randomly culled for regular word-building; root generation
        # shouldn't risk being left with zero valid pairs). When it's an
        # onset cluster (something follows the pair), both members are
        # also checked against excluded_onset_consonants, matching
        # `is_valid_syllable`'s own "every onset position" scope. Skipped
        # entirely if either symbol isn't a recognized consonant (should
        # never happen, but stays defensive rather than raising).
        if following_is_root_slot:
            second = filled[i + 1]
            c1, c2 = consonant_by_ipa.get(symbol), consonant_by_ipa.get(second)
            ends_word = i + 1 == last_index
            if not ends_word and (symbol in structure.excluded_onset_consonants or second in structure.excluded_onset_consonants):
                return True
            if c1 is not None and c2 is not None:
                is_legal = sonority.is_legal_coda_cluster(c1, c2) if ends_word else sonority.is_legal_onset_cluster(c1, c2)
                if not is_legal:
                    return True

    return False


def generate_root(
    rng: random.Random,
    inventory: PhonemeInventory,
    structure: SyllableStructure | None = None,
    skeleton: tuple[str, ...] | None = None,
    size: int = _ROOT_SIZE,
) -> tuple[str, ...]:
    """``size`` consonants weighted by prevalence, with a simple OCP-style
    constraint: no two *adjacent* root consonants identical (real Semitic
    roots avoid this). Also excludes any consonant marked ``.long``
    (Arabic's own real shadda/gemination) from the candidate pool --
    real Semitic roots are always sequences of plain consonants; gemination
    is a property the *template* imposes on an ordinary radical (Form II
    verbs double the middle radical), never an inherent property of the
    root's own letters, so a geminate consonant should never itself be
    "the" root's third letter. When ``structure``/``skeleton`` are given,
    retries (bounded) until the filled root clears
    `_root_violates_structure` -- generate-and-check rather than
    fully-correct forward-constrained generation, so it stays robust to
    any future template shape; falls back to its last attempt if none
    fully clears it within the bound, never blocking generation entirely
    (same "defensive fallback" spirit as `_ensure_floor`/`_choose_nucleus`
    elsewhere in this codebase)."""
    plain_consonants = tuple(c for c in inventory.consonants if not c.long) or inventory.consonants
    attempts = _MAX_ROOT_ATTEMPTS if structure is not None and skeleton is not None else 1
    root: tuple[str, ...] = ()
    for _ in range(attempts):
        candidates_root: list[str] = []
        for _ in range(size):
            candidates = tuple(c for c in plain_consonants if not candidates_root or c.ipa != candidates_root[-1])
            if not candidates:
                candidates = plain_consonants
            candidates_root.append(word_builder.weighted_choice(rng, candidates).ipa)
        root = tuple(candidates_root)
        if structure is None or skeleton is None:
            return root
        if not _root_violates_structure(skeleton, root, structure, inventory):
            return root
    return root


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
    structure: SyllableStructure | None = None,
    num_candidates: int = 5,
    context: str = "",
    source_languages: tuple[str, ...] = (),
    strictness: float = 0.0,
    word_accent_system: WordAccentSystem = WordAccentSystem(),
) -> LexicalEntry:
    """Pick a template matching ``pos`` (varying across same-POS calls,
    for real variety across e.g. multiple nouns), generate several root
    candidates, fill the template with each, and let the LLM pick the
    best-sounding one -- same candidate-then-pick shape as
    ``lexicon_gen.propose_word``. ``structure``, when given, makes every
    generated root respect this language's own onset/coda/onset-nucleus
    restrictions -- see ``generate_root``'s own docstring. ``source_languages``/
    ``strictness`` resolve stress the same way ``lexicon_gen.propose_word``
    does; a templatic word has no per-syllable build loop of its own to
    hook stress into, so it's assigned as a post-processing step on the
    chosen candidate's already-filled skeleton (see
    ``word_accent_gen.mark_stress_and_word_accent``) -- a real
    approximation for languages whose actual stress typology depends on
    morphological structure the way Semitic languages' own does, not
    attempted in depth here, same spirit as this module's other
    simplifications. ``word_accent_system`` (default disabled, unlike
    ``tone_system`` -- this function has never threaded tone through at
    all, a separate pre-existing gap not addressed here) gates word
    accent the same per-language-systemic way ``lexicon_gen.propose_word``
    already does."""
    template = template_for_pos(rng, templates, pos)

    seen: set[tuple[str, ...]] = set()
    roots: list[tuple[str, ...]] = []
    for _ in range(num_candidates):
        root = generate_root(rng, inventory, structure, template.skeleton)
        if root not in seen:
            seen.add(root)
            roots.append(root)

    candidates = [fill_template(template, root) for root in roots]
    chosen = choose_best_candidate(rng, candidates, gloss, pos, llm_client, language_name, context)
    chosen_root = roots[candidates.index(chosen)]

    root_iter = iter(chosen_root)
    filled_symbols = tuple(next(root_iter) if slot == "C" else slot for slot in template.skeleton)
    vowel_symbols = frozenset(v.ipa for v in inventory.vowels)
    reference_profiles = match_profiles(source_languages)
    stress_pattern, stress_deviation_rate = stress_gen.resolve_stress_pattern(reference_profiles)
    word_accent_pattern = ""
    word_accent_deviation_rate: float | None = None
    word_accent_length_rate: float | None = None
    word_accent_window: int | None = None
    if word_accent_system.enabled:
        (
            _, word_accent_pattern, word_accent_deviation_rate, word_accent_length_rate, word_accent_window,
        ) = word_accent_gen.resolve_word_accent(reference_profiles)
    stressed = word_accent_gen.mark_stress_and_word_accent(
        rng, filled_symbols, vowel_symbols, stress_pattern, stress_deviation_rate, strictness,
        word_accent_realization=word_accent_system.realization,
        word_accent_pattern=word_accent_pattern,
        word_accent_deviation_rate=word_accent_deviation_rate,
        word_accent_length_rate=word_accent_length_rate,
        word_accent_window=word_accent_window,
    )

    return LexicalEntry(
        ipa=stressed,
        romanization=apply_grammatical_spelling(romanization, romanization.apply(stressed), pos),
        glosses=(gloss,),
        pos=pos,
        root=chosen_root,
    )
