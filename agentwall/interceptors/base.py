from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agentwall.core.types import Decision, RuntimeEvent
from agentwall.storage.models import ToolEvent


class BaseInterceptor(ABC):
    @abstractmethod
    def before_execute(self, event: RuntimeEvent) -> Decision: ...

    @abstractmethod
    def after_execute(self, event: RuntimeEvent, result: Any) -> None: ...

    @abstractmethod
    def record_event(self, event: RuntimeEvent) -> ToolEvent: ...

    @abstractmethod
    def evaluate_event(self, event: RuntimeEvent) -> Decision: ...
