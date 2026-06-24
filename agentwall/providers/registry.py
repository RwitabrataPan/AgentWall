from __future__ import annotations

from agentwall.core.config_manager import ConfigManager
from agentwall.storage.database import Database
from .base import BaseEvaluator, ProviderStatus
from .chain import ProviderChain
from .keyring import get_api_key

from .anthropic import AnthropicEvaluator
from .deepseek import DeepSeekEvaluator
from .groq import GroqEvaluator
from .ollama import OllamaEvaluator
from .openai import OpenAIEvaluator

EVALUATOR_CLASSES: dict[str, type[BaseEvaluator]] = {
    "openai": OpenAIEvaluator,
    "anthropic": AnthropicEvaluator,
    "groq": GroqEvaluator,
    "deepseek": DeepSeekEvaluator,
    "ollama": OllamaEvaluator,
}


class ProviderRegistry:
    def __init__(self, db: Database) -> None:
        self._config = ConfigManager(db)

    def load_chain(self) -> ProviderChain:
        settings = self._config.list_providers_ordered()
        evaluators: list[BaseEvaluator] = []
        for s in settings:
            if not s.enabled:
                continue
            cls = EVALUATOR_CLASSES.get(s.provider)
            if cls is None:
                continue
            try:
                api_key = get_api_key(s.provider) if cls.NEEDS_API_KEY else None
                kwargs = {"model": s.model}
                if api_key:
                    kwargs["api_key"] = api_key
                evaluators.append(cls(**kwargs))
            except Exception:
                continue
        return ProviderChain(evaluators)

    def health_check_all(self) -> list[ProviderStatus]:
        settings = self._config.list_providers_ordered()
        statuses: list[ProviderStatus] = []
        for s in settings:
            cls = EVALUATOR_CLASSES.get(s.provider)
            if cls is None:
                continue
            try:
                api_key = get_api_key(s.provider) if cls.NEEDS_API_KEY else None
                kwargs = {"model": s.model}
                if api_key:
                    kwargs["api_key"] = api_key
                evaluator = cls(**kwargs)
                statuses.append(evaluator.health_check())
            except Exception as e:
                from .base import ProviderHealth
                statuses.append(ProviderStatus(s.provider, ProviderHealth.UNAVAILABLE, s.model, error=str(e)))
        return statuses
