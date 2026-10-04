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

from conlang_generator.core.lexicon import PartOfSpeech
from conlang_generator.core.language import Language
from conlang_generator.core.spec import SeedExample
from conlang_generator.generation import ipa_tokenizer, phoneme_fit
from conlang_generator.llm.base import LLMClient, LLMRequest
from conlang_generator.llm.pricing import DEFAULT_MODEL

_SYSTEM_PROMPT = (
    "Give a plausible IPA (International Phonetic Alphabet) pronunciation for "
    "the given word. It has no stated source language or spelling convention "
    "-- just give a reasonable, natural-sounding reading of the letters as "
    "written. Respond with ONLY the IPA transcription: no slashes, brackets, "
    "or prose."
)


def resolve_seed_examples(examples: tuple[SeedExample, ...], llm_client: LLMClient) -> tuple[SeedExample, ...]:
    resolved: list[SeedExample] = []
    for example in examples:
        if example.ipa is not None:
            resolved.append(example)
            continue
        request = LLMRequest(
            system=_SYSTEM_PROMPT,
            prompt=example.form,
            model=DEFAULT_MODEL,
            max_tokens=32,
            purpose="seed_example.guess_ipa",
            metadata={"fake_strategy": "guess_ipa"},
        )
        response = llm_client.complete(request)
        resolved.append(example.model_copy(update={"ipa": _clean_ipa(response.text)}))
    return tuple(resolved)


def _clean_ipa(text: str) -> str:
    stripped = text.strip().strip("/[]")
    return stripped or text.strip()


def parse_bulk_seed_examples(text: str) -> tuple[SeedExample, ...]:
    """CSV-ish bulk seed-word input: one word per line, ``gloss,form[,ipa[,pos]]``
    -- a header row (first cell ``"gloss"``, case-insensitive) is skipped if
    present. Shared by the CLI's ``--examples-file`` and the web UI's
    bulk-paste field so both get identical parsing. A row missing its
    required ``gloss``/``form``, or carrying an unrecognized ``pos``, is
    skipped rather than raising -- this project's own "degrade gracefully,
    report the gap elsewhere" convention for lenient batch input (compare
    ``generation/real_words_llm.py``'s own batch-reply parsing)."""
    rows = [row for row in csv.reader(io.StringIO(text.strip())) if any(cell.strip() for cell in row)]
    if rows and rows[0][0].strip().lower() == "gloss":
        rows = rows[1:]
    examples: list[SeedExample] = []
    for row in rows:
        cells = [cell.strip() for cell in row] + [""] * max(0, 4 - len(row))
        gloss, form, ipa, pos_text = cells[:4]
        if not gloss or not form:
            continue
        pos = None
        if pos_text:
            try:
                pos = PartOfSpeech(pos_text.lower())
            except ValueError:
                continue
        examples.append(SeedExample(gloss=gloss, form=form, ipa=(ipa or None), pos=pos))
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
