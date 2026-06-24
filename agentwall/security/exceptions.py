from __future__ import annotations

from agentwall.core.types import Decision, RuntimeEvent


class AgentWallSecurityException(Exception):
    def __init__(self, decision: Decision, event: RuntimeEvent) -> None:
        self.decision = decision
        self.event = event
        super().__init__(
            f"[risk={decision.risk_score:.0f}] {decision.reason} "
            f"(tool={event.tool_type.value}.{event.action.value} target={event.target!r})"
        )
