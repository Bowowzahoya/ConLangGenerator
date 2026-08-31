"""Deterministic, zero-cost stand-in for a real LLM.

Used as the default everywhere (dry runs, tests) per the project's
fake-LLM-first rule. It doesn't try to understand a prompt's meaning; callers
that need specific fake behavior say so explicitly via ``request.metadata``:

- ``fake_strategy=\"choose_index\"`` + ``num_options=\"N\"``: returns a stable
  ``\"1\"``..``\"N\"`` derived from a hash of the prompt (used by
  ``generation/lexicon_gen.py`` to pick among pre-built candidate words).
- ``fake_strategy=\"passthrough\"`` + ``fallback_text=\"...\"``: echoes that
  text back verbatim (used where a real model would polish a deterministic
  draft -- in fake mode the draft is the answer).
- ``fake_strategy=\"trait_profile\"`` + ``trait_fields=\"a,b,c\"``: returns a
  JSON object with each named field set to a hash-derived float in
  ``[0.0, 1.0]`` (used by ``generation/prompt_classifier.py``). List/free-text
  fields are intentionally left empty -- the fake doesn't understand prompt
  semantics, it just needs to vary deterministically by prompt so tests can
  exercise "different prompts -> different generated languages."
- anything else: an opaque deterministic placeholder string.
"""

from __future__ import annotations

import hashlib
import json

from conlang_generator.llm.base import LLMRequest, LLMResponse

FAKE_MODEL_NAME = "fake-llm"


def stable_hash(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)


def _fake_trait_profile(prompt: str, field_names: list[str]) -> str:
    values = {name: round((stable_hash(prompt + name) % 100) / 100.0, 2) for name in field_names}
    return json.dumps(values)


class FakeLLMClient:
    def complete(self, request: LLMRequest) -> LLMResponse:
        strategy = request.metadata.get("fake_strategy", "generic")
        if strategy == "choose_index":
            num_options = int(request.metadata.get("num_options", "1"))
            index = stable_hash(request.prompt) % num_options + 1
            text = str(index)
        elif strategy == "passthrough":
            text = request.metadata.get("fallback_text", "")
        elif strategy == "trait_profile":
            field_names = [f for f in request.metadata.get("trait_fields", "").split(",") if f]
            text = _fake_trait_profile(request.prompt, field_names)
        else:
            text = f"fake-response-{stable_hash(request.prompt) % 10_000}"

        return LLMResponse(
            text=text,
            model=FAKE_MODEL_NAME,
            input_tokens=max(1, len(request.system) + len(request.prompt)) // 4,
            output_tokens=max(1, len(text) // 4),
            stop_reason="end_turn",
        )
