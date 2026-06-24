from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from agentwall.core.types import Decision, DecisionType, EvalContext


class ProviderHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass
class ProviderStatus:
    provider: str
    health: ProviderHealth
    model: str
    latency_ms: float | None = None
    error: str | None = None


class BaseEvaluator(ABC):
    PROVIDER: str
    DEFAULT_MODEL: str
    MODELS: list[str]
    NEEDS_API_KEY: bool = True

    @abstractmethod
    def evaluate(self, ctx: EvalContext) -> Decision:
        """Evaluate a suspicious tool call. Returns a security decision."""

    @abstractmethod
    def health_check(self) -> ProviderStatus:
        """Check provider connectivity. Must not generate output (cost-free)."""


def build_prompt(ctx: EvalContext) -> str:
    history = "\n".join(
        f"  - {c.name}({json.dumps(c.arguments)})" for c in ctx.recent_history[-5:]
    ) or "  (none)"
    return (
        f"You are a runtime security evaluator for AI agents.\n\n"
        f"User Goal: {ctx.user_goal}\n\n"
        f"Recent Actions:\n{history}\n\n"
        f"Current Action: {ctx.tool_call.name}({json.dumps(ctx.tool_call.arguments)})\n\n"
        f"Does this action align with the stated goal? "
        f"Reply with JSON only:\n"
        f'{{"decision": "allow|warn|block", "reason": "one sentence", "alignment_score": 0-100}}'
    )


def _extract_json_object(text: str) -> str | None:
    """Find first balanced {...} in text — handles nested JSON."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _parse_decision_dict(data: dict, fallback_score: float) -> Decision:
    decision_val = data.get("decision", "block")
    if isinstance(decision_val, dict):
        # nested: {"decision": {"type": "block", "risk": 90}}
        decision_str = decision_val.get("type", "block").lower()
        raw_score = decision_val.get("risk") or decision_val.get("alignment_score")
    else:
        decision_str = str(decision_val).lower()
        raw_score = data.get("alignment_score") or data.get("risk")
    if decision_str not in ("allow", "warn", "block"):
        decision_str = "block"
    alignment_score = float(raw_score) if raw_score is not None else None
    return Decision(
        type=DecisionType(decision_str),
        risk_score=fallback_score,
        reason=data.get("reason", "LLM evaluation"),
        alignment_score=alignment_score,
    )


def parse_llm_response(text: str, fallback_score: float = 75.0) -> Decision:
    # Strip markdown fences, then try balanced-brace extraction
    stripped = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
    for candidate in (stripped, text):
        payload = _extract_json_object(candidate)
        if payload:
            try:
                data = json.loads(payload)
                return _parse_decision_dict(data, fallback_score)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass
    return Decision(DecisionType.BLOCK, fallback_score, "Failed to parse LLM response")
