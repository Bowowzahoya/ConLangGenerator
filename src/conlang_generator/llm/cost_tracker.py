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
        )
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self._ledger_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry)) + "\n")
        return entry

    def summarize(self) -> dict:
        if not self._ledger_path.exists():
            return {"total_cost_usd": 0.0, "num_calls": 0, "by_model": {}}
        records = [
            json.loads(line)
            for line in self._ledger_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        by_model: dict[str, float] = {}
        for r in records:
            by_model[r["model"]] = by_model.get(r["model"], 0.0) + r["cost_usd"]
        return {
            "total_cost_usd": sum(r["cost_usd"] for r in records),
            "num_calls": len(records),
            "by_model": by_model,
        }


class CostTrackingLLMClient:
    def __init__(self, wrapped, tracker: CostTracker) -> None:
        self._wrapped = wrapped
        self._tracker = tracker

    def complete(self, request: LLMRequest) -> LLMResponse:
        response = self._wrapped.complete(request)
        self._tracker.record(request, response)
        return response
