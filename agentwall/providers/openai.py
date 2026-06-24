from __future__ import annotations

import time

from .base import BaseEvaluator, ProviderHealth, ProviderStatus, build_prompt, parse_llm_response
from .keyring import get_api_key
from agentwall.core.types import Decision, EvalContext


class OpenAIEvaluator(BaseEvaluator):
    PROVIDER = "openai"
    DEFAULT_MODEL = "gpt-4o-mini"
    MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
    NEEDS_API_KEY = True

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
        from openai import OpenAI
        key = api_key or get_api_key(self.PROVIDER)
        if not key:
            raise ValueError(f"No API key for {self.PROVIDER}. Run: agentwall config")
        self._client = OpenAI(api_key=key)
        self.model = model

    def evaluate(self, ctx: EvalContext) -> Decision:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": build_prompt(ctx)}],
            max_tokens=150,
            temperature=0,
        )
        return parse_llm_response(response.choices[0].message.content or "")

    def health_check(self) -> ProviderStatus:
        t = time.perf_counter()
        try:
            key = get_api_key(self.PROVIDER)
            if not key:
                return ProviderStatus(self.PROVIDER, ProviderHealth.UNAVAILABLE, self.model, error="No API key")
            from openai import OpenAI
            OpenAI(api_key=key).models.list()
            return ProviderStatus(self.PROVIDER, ProviderHealth.HEALTHY, self.model,
                                  latency_ms=(time.perf_counter() - t) * 1000)
        except Exception as e:
            return ProviderStatus(self.PROVIDER, ProviderHealth.UNAVAILABLE, self.model, error=str(e))
