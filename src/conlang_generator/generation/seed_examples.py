"""Fills in ``SeedExample.ipa`` from ``SeedExample.form`` when the user
didn't give one directly.

This is an explicit guess, not phonetic analysis -- there's no reliable way
to recover pronunciation from arbitrary spelling without knowing what
convention the user had in mind. Real-model output should be treated the
same way: a plausible reading, not a fact. See ``llm/fake_client.py``'s
``guess_ipa`` strategy for the (deliberately cruder) fake-mode equivalent.
"""

from __future__ import annotations

from conlang_generator.core.spec import SeedExample
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
