"""Attributes every real LLM call to a cost, appended to a JSONL ledger.

Wrap the real client with ``CostTrackingLLMClient`` *before* wrapping with
``CachingLLMClient`` (cache on the outside) so cache hits are never recorded
as spend.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from conlang_generator.llm.base import LLMRequest, LLMResponse
from conlang_generator.llm.pricing import estimate_cost


@dataclass(frozen=True)
class UsageRecord:
    timestamp: str
    model: str
    purpose: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    system: str = ""
    prompt: str = ""
    response_text: str = ""
    """The actual request/response text for this call -- defaulted (not
    required) so a ledger line recorded before these three fields existed
    still parses fine via ``list_entries`` (see docs/DEFERRED.md's "See
    the actual LLM prompts" item)."""


class CostTracker:
    def __init__(self, ledger_path: Path) -> None:
        self._ledger_path = ledger_path

    def record(self, request: LLMRequest, response: LLMResponse) -> UsageRecord:
        entry = UsageRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            model=response.model,
            purpose=request.purpose,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=estimate_cost(
                response.model, response.input_tokens, response.output_tokens
            ),
            system=request.system,
            prompt=request.prompt,
            response_text=response.text,
        )
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self._ledger_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry)) + "\n")
        return entry

    def _records(self) -> list[dict]:
        if not self._ledger_path.exists():
            return []
        return [
            json.loads(line)
            for line in self._ledger_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def summarize(self) -> dict:
        records = self._records()
        if not records:
            return {"total_cost_usd": 0.0, "num_calls": 0, "by_model": {}}
        by_model: dict[str, float] = {}
        for r in records:
            by_model[r["model"]] = by_model.get(r["model"], 0.0) + r["cost_usd"]
        return {
            "total_cost_usd": sum(r["cost_usd"] for r in records),
            "num_calls": len(records),
            "by_model": by_model,
        }

    def list_entries(self, limit: int = 300) -> list[dict]:
        """The most recent ``limit`` ledger entries, newest first -- for a
        human-browsable call log (the web UI's own "Log" tab). Every dict
        always has every ``UsageRecord`` field, even for a line recorded
        before ``system``/``prompt``/``response_text`` existed (defaulted
        to ``""`` for those, the same backward-compatible shape every
        other new field added to a persisted model in this project gets)."""
        records = self._records()
        for r in records:
            for field_name in ("system", "prompt", "response_text"):
                r.setdefault(field_name, "")
        records.reverse()
        return records[:limit]


class CostTrackingLLMClient:
    def __init__(self, wrapped, tracker: CostTracker) -> None:
        self._wrapped = wrapped
        self._tracker = tracker

    def complete(self, request: LLMRequest) -> LLMResponse:
        response = self._wrapped.complete(request)
        self._tracker.record(request, response)
        return response
