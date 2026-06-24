from __future__ import annotations

import time

from .base import BaseEvaluator, ProviderHealth, ProviderStatus, build_prompt, parse_llm_response
from .keyring import get_api_key
from agentwall.core.types import Decision, EvalContext


class AnthropicEvaluator(BaseEvaluator):
    PROVIDER = "anthropic"
    DEFAULT_MODEL = "claude-haiku-4-5-20251001"
    MODELS = ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]
    NEEDS_API_KEY = True

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
        from anthropic import Anthropic
        key = api_key or get_api_key(self.PROVIDER)
        if not key:
            raise ValueError(f"No API key for {self.PROVIDER}. Run: agentwall config")
        self._client = Anthropic(api_key=key)
        self.model = model

    def evaluate(self, ctx: EvalContext) -> Decision:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=150,
            messages=[{"role": "user", "content": build_prompt(ctx)}],
        )
        text = response.content[0].text if response.content else ""
        return parse_llm_response(text)

    def health_check(self) -> ProviderStatus:
        t = time.perf_counter()
        try:
            key = get_api_key(self.PROVIDER)
            if not key:
                return ProviderStatus(self.PROVIDER, ProviderHealth.UNAVAILABLE, self.model, error="No API key")
            from anthropic import Anthropic
            Anthropic(api_key=key).models.list(limit=1)
            return ProviderStatus(self.PROVIDER, ProviderHealth.HEALTHY, self.model,
                                  latency_ms=(time.perf_counter() - t) * 1000)
        except Exception as e:
            return ProviderStatus(self.PROVIDER, ProviderHealth.UNAVAILABLE, self.model, error=str(e))
