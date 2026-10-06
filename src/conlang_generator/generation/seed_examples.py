"""Fills in ``SeedExample.ipa`` from ``SeedExample.form`` when the user
didn't give one directly.

This is an explicit guess, not phonetic analysis -- there's no reliable way
to recover pronunciation from arbitrary spelling without knowing what
convention the user had in mind. Real-model output should be treated the
same way: a plausible reading, not a fact. See ``llm/fake_client.py``'s
``guess_ipa`` strategy for the (deliberately cruder) fake-mode equivalent.
"""

from __future__ import annotations

import csv
import io
import unicodedata

from conlang_generator.core.lexicon import LexicalEntry, PartOfSpeech
from conlang_generator.core.language import Language
from conlang_generator.core.spec import SeedExample, SeedForm
from conlang_generator.generation import ipa_tokenizer, phoneme_fit, pronoun_gen, voice_np_gen
from conlang_generator.llm.base import LLMClient, LLMRequest
from conlang_generator.llm.pricing import DEFAULT_MODEL

_SYSTEM_PROMPT = (
    "Give a plausible IPA (International Phonetic Alphabet) pronunciation for "
    "the given word. It has no stated source language or spelling convention "
    "-- just give a reasonable, natural-sounding reading of the letters as "
    "written. Respond with ONLY the IPA transcription: no slashes, brackets, "
    "or prose."
)

CELL_POS: dict[str, PartOfSpeech] = {
    "plural": PartOfSpeech.NOUN,
    "past": PartOfSpeech.VERB,
    "non_past": PartOfSpeech.VERB,
    "present": PartOfSpeech.VERB,
    "future": PartOfSpeech.VERB,
    "comparative": PartOfSpeech.ADJECTIVE,
    "superlative": PartOfSpeech.ADJECTIVE,
    "accusative": PartOfSpeech.PRONOUN,
    "ergative": PartOfSpeech.PRONOUN,
    "genitive": PartOfSpeech.PRONOUN,
    "dative": PartOfSpeech.PRONOUN,
    "locative": PartOfSpeech.PRONOUN,
}
"""Which part of speech each suppletive cell applies to -- the verb/noun/
adjective cells match ``generation.voice_np_gen.SUPPLETIVE_SUFFIXES``; the
pronoun cells are ``pronoun_gen.CASE_NAMES`` minus ``nominative``/
``absolutive`` (never suppletive -- see ``translator._suppletive_case``).
A ``SeedForm`` naming any other cell, or one that doesn't match its own
``SeedExample``'s own ``pos``, is invalid."""


def _guess_ipa(form: str, llm_client: LLMClient) -> str:
    request = LLMRequest(
        system=_SYSTEM_PROMPT,
        prompt=form,
        model=DEFAULT_MODEL,
        max_tokens=32,
        purpose="seed_example.guess_ipa",
        metadata={"fake_strategy": "guess_ipa"},
    )
    response = llm_client.complete(request)
    return _clean_ipa(response.text)


def resolve_seed_examples(examples: tuple[SeedExample, ...], llm_client: LLMClient) -> tuple[SeedExample, ...]:
    resolved: list[SeedExample] = []
    for example in examples:
        ipa = example.ipa if example.ipa is not None else _guess_ipa(example.form, llm_client)
        forms = tuple(
            form if form.ipa is not None else form.model_copy(update={"ipa": _guess_ipa(form.form, llm_client)})
            for form in example.forms
        )
        resolved.append(example.model_copy(update={"ipa": ipa, "forms": forms}))
    return tuple(resolved)


def _clean_ipa(text: str) -> str:
    stripped = text.strip().strip("/[]")
    return stripped or text.strip()


def parse_seed_forms(text: str) -> tuple[SeedForm, ...]:
    """Parses the ``cell:form[:ipa]`` mini-syntax (``;``-separated for more
    than one form), with no part-of-speech validation -- shared, syntax-only
    parsing for both the CLI (which errors on a cell/POS mismatch, see
    ``cli/main.py``) and bulk/web input (which drops it, see ``valid_forms``).
    A chunk with no ``:`` is malformed and skipped."""
    forms: list[SeedForm] = []
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        cell, _, remainder = chunk.partition(":")
        form, _, ipa = remainder.partition(":")
        if not cell.strip() or not form.strip():
            continue
        forms.append(SeedForm(cell=cell.strip(), form=form.strip(), ipa=(ipa.strip() or None)))
    return tuple(forms)


def valid_forms(example: SeedExample) -> tuple[SeedForm, ...]:
    """``example.forms`` filtered to cells matching ``example.pos`` (default
    ``NOUN``) via ``CELL_POS`` -- the single place both generation-time
    entry-building and lemma-registration apply the same validity rule.
    A pronoun-cell form is additionally only valid when the word's own
    gloss is itself a recognized personal pronoun ("I"/"you"/"he"/"she"/
    "it"/"they"/...) -- a pronoun case form on an arbitrary noun gloss
    makes no sense."""
    pos = example.pos or PartOfSpeech.NOUN
    return tuple(
        form for form in example.forms
        if CELL_POS.get(form.cell) is pos
        and (pos is not PartOfSpeech.PRONOUN or pronoun_gen.person_label(example.gloss) is not None)
    )


def seed_suppletive_entries(seed_examples: tuple[SeedExample, ...]) -> tuple[LexicalEntry, ...]:
    """One ``LexicalEntry`` per valid user-given form, keyed by the exact
    synthetic gloss (``voice_np_gen.suppletive_gloss(base, cell)``) the
    existing hardcoded-irregular suppletion mechanism already uses --
    ``translator._lookup_or_coin`` then finds it directly at render time,
    with no further code. For a pronoun cell this produces the identical
    ``f"{base}-{cell}"`` shape ``pronoun_gen.suppletive_gloss`` itself
    builds (that function just additionally lowercases internally, and
    ``base`` here is already lowercased) -- safe to reuse without a
    dispatcher."""
    return tuple(
        LexicalEntry(
            ipa=form.ipa,
            romanization=unicodedata.normalize("NFC", form.form),
            glosses=(voice_np_gen.suppletive_gloss(example.gloss.strip().lower(), form.cell),),
            pos=example.pos or PartOfSpeech.NOUN,
            notes="seed word",
        )
        for example in seed_examples
        for form in valid_forms(example)
    )


def seed_suppletive_lemmas(seed_examples: tuple[SeedExample, ...], cell: str) -> tuple[str, ...]:
    """The lowercased base glosses with a valid user-given form for ``cell``
    -- folded into ``grammar.suppletive_plurals``/``_degrees``/``_past`` at
    generation time (``generator.py``) so the existing render-time gates
    (``translator._suppletive_form_kind``, the inline verb-past check) pick
    the word up automatically, exactly as they already do for a rolled
    hardcoded-irregular lemma."""
    return tuple(
        example.gloss.strip().lower()
        for example in seed_examples
        for form in valid_forms(example)
        if form.cell == cell
    )


def parse_bulk_seed_examples(text: str) -> tuple[SeedExample, ...]:
    """CSV-ish bulk seed-word input: one word per line,
    ``gloss,form[,ipa[,pos[,forms]]]`` -- a header row (first cell
    ``"gloss"``, case-insensitive) is skipped if present. ``forms`` is
    ``parse_seed_forms``'s ``cell:form[:ipa]`` syntax (``;``-separated for
    more than one). Shared by the CLI's ``--examples-file`` and the web
    UI's bulk-paste field so both get identical parsing. A row missing its
    required ``gloss``/``form``, or carrying an unrecognized ``pos``, is
    skipped rather than raising; a form whose cell doesn't match the row's
    own ``pos`` is dropped (the base word is kept) -- this project's own
    "degrade gracefully, report the gap elsewhere" convention for lenient
    batch input (compare ``generation/real_words_llm.py``'s own
    batch-reply parsing)."""
    rows = [row for row in csv.reader(io.StringIO(text.strip())) if any(cell.strip() for cell in row)]
    if rows and rows[0][0].strip().lower() == "gloss":
        rows = rows[1:]
    examples: list[SeedExample] = []
    for row in rows:
        cells = [cell.strip() for cell in row] + [""] * max(0, 5 - len(row))
        gloss, form, ipa, pos_text, forms_text = cells[:5]
        if not gloss or not form:
            continue
        pos = None
        if pos_text:
            try:
                pos = PartOfSpeech(pos_text.lower())
            except ValueError:
                continue
        resolved_pos = pos or PartOfSpeech.NOUN
        forms = tuple(f for f in parse_seed_forms(forms_text) if CELL_POS.get(f.cell) is resolved_pos)
        examples.append(SeedExample(gloss=gloss, form=form, ipa=(ipa or None), pos=pos, forms=forms))
    return tuple(examples)


def phonotactic_mismatch_warnings(language: Language) -> list[str]:
    """One warning per seed example whose IPA isn't a legal word under this
    language's own generated ``SyllableStructure`` -- never auto-repaired
    (that would break the feature's own core guarantee that a seed word
    appears verbatim), only surfaced, mirroring ``real_words.strictness_
    warnings``' own "allowed, never blocked" stance."""
    vowels = {v.ipa for v in language.phonology.vowels}
    symbols = language.phonology.all_symbols()
    warnings = []
    for example in language.spec.seed_examples:
        if example.ipa is None:
            continue
        tokens = ipa_tokenizer.symbols_only(example.ipa, symbols)
        if phoneme_fit.first_problem([(s, s in vowels) for s in tokens], language.syllable_structure) is not None:
            warnings.append(
                f"seed word '{example.gloss}' ({example.ipa}) is not a legal syllable shape in this "
                "language's own generated phonology -- kept verbatim anyway."
            )
    return warnings


def unused_suppletive_form_warnings(language: Language) -> list[str]:
    """One warning per seed-given irregular form whose own cell never
    became live in this specific generated grammar -- a pronoun case the
    language doesn't have, or a ``non_past``/``present``/``future`` tense
    from the tense system this language didn't roll. Whether a case/tense
    is live can't be known until generation completes (unlike a cell/POS
    mismatch, caught immediately at parse time), so -- mirroring
    ``phonotactic_mismatch_warnings``'s own stance -- the ``LexicalEntry``
    is still created (harmless), just never used at render time, and this
    is only surfaced, never silently dropped."""
    warnings = []
    for example in language.spec.seed_examples:
        pos = example.pos or PartOfSpeech.NOUN
        for form in valid_forms(example):
            if pos is PartOfSpeech.PRONOUN and form.cell not in language.grammar.cases:
                warnings.append(
                    f"seed word '{example.gloss}' gave an irregular {form.cell} form, but this language "
                    f"has no {form.cell} case -- kept in the lexicon but never used."
                )
            elif form.cell in ("non_past", "present", "future") and form.cell not in language.grammar.tenses:
                warnings.append(
                    f"seed word '{example.gloss}' gave an irregular {form.cell} form, but this language's "
                    f"tense system has no {form.cell} -- kept in the lexicon but never used."
                )
    return warnings
