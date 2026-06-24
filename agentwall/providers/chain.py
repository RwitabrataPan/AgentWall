from __future__ import annotations

from agentwall.core.types import Decision, DecisionType, EvalContext
from .base import BaseEvaluator


class ProviderChain:
    """Evaluates using primary provider; falls back to next on failure."""

    def __init__(self, evaluators: list[BaseEvaluator]) -> None:
        if not evaluators:
            raise ValueError("ProviderChain requires at least one evaluator")
        self._chain = evaluators

    def evaluate(self, ctx: EvalContext) -> Decision:
        last_error: Exception | None = None
        for evaluator in self._chain:
            try:
                return evaluator.evaluate(ctx)
            except Exception as e:
                last_error = e
                continue
        return Decision(
            DecisionType.BLOCK,
            100.0,
            f"All providers failed. Last error: {last_error}",
        )

    @property
    def providers(self) -> list[str]:
        return [e.PROVIDER for e in self._chain]
