from __future__ import annotations

import json
import time

import httpx

from .base import BaseEvaluator, ProviderHealth, ProviderStatus, build_prompt, parse_llm_response
from agentwall.core.types import Decision, EvalContext


class OllamaEvaluator(BaseEvaluator):
    PROVIDER = "ollama"
    DEFAULT_MODEL = "llama3.2"
    MODELS = ["llama3.2", "llama3.1", "mistral", "gemma2", "phi3"]
    NEEDS_API_KEY = False

    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = "http://localhost:11434",
                 api_key: str | None = None) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")

    def evaluate(self, ctx: EvalContext) -> Decision:
        response = httpx.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": build_prompt(ctx), "stream": False},
            timeout=30,
        )
        response.raise_for_status()
        text = response.json().get("response", "")
        return parse_llm_response(text)

    def health_check(self) -> ProviderStatus:
        t = time.perf_counter()
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            if self.model not in models and models:
                return ProviderStatus(
                    self.PROVIDER, ProviderHealth.DEGRADED, self.model,
                    latency_ms=(time.perf_counter() - t) * 1000,
                    error=f"Model '{self.model}' not pulled. Available: {', '.join(models[:3])}",
                )
            return ProviderStatus(self.PROVIDER, ProviderHealth.HEALTHY, self.model,
                                  latency_ms=(time.perf_counter() - t) * 1000)
        except Exception as e:
            return ProviderStatus(self.PROVIDER, ProviderHealth.UNAVAILABLE, self.model, error=str(e))
