from __future__ import annotations

from agentwall.core.types import (
    Decision,
    DecisionType,
    EvalContext,
    RuntimeEvent,
    ToolCall,
)
from agentwall.security import rules


def build_default_engine(db: "Database") -> "SecurityEngine":
    """Build SecurityEngine with thresholds and provider chain from DB config.

    Reads low/high thresholds from ConfigManager. Attempts to load a ProviderChain
    from configured providers in ProviderRegistry. Falls back to chain=None if no
    providers are configured or all fail to load.
    """
    from agentwall.core.config_manager import ConfigManager
    from agentwall.providers.registry import ProviderRegistry
    from agentwall.security.policy_engine import PolicyEngine

    thresholds = ConfigManager(db).get_thresholds()

    chain = None
    try:
        chain = ProviderRegistry(db).load_chain()
    except (ValueError, Exception):
        chain = None

    return SecurityEngine(
        warn_threshold=thresholds["low_threshold"],
        block_threshold=thresholds["high_threshold"],
        provider_chain=chain,
        policy_engine=PolicyEngine(db),
    )


def _default_detectors() -> list:
    from agentwall.security.detectors import (
        DataExfiltrationDetector,
        GoalDriftDetector,
        ScopeExpansionDetector,
        SensitiveResourceDetector,
    )
    return [
        SensitiveResourceDetector(),
        ScopeExpansionDetector(),
        DataExfiltrationDetector(),
        GoalDriftDetector(),
    ]


class SecurityEngine:
    """Framework-agnostic security evaluator. Operates only on RuntimeEvent.

    Evaluation pipeline:
      1. Detectors     → detector_hits, risk modifier
      2. Rule engine   → base risk score (0-100)
      3. Policy engine → hard override (optional)
      4. Thresholds    → ALLOW / WARN / escalate
      5. LLM chain     → ALLOW / WARN / BLOCK + alignment_score (if escalated)
    """

    def __init__(
        self,
        *,
        warn_threshold: float = 30.0,
        block_threshold: float = 70.0,
        provider_chain=None,
        policy_engine=None,
        detectors: list | None = None,
    ) -> None:
        self._warn = warn_threshold
        self._block = block_threshold
        self._chain = provider_chain
        self._policy_engine = policy_engine
        self._detectors = detectors if detectors is not None else _default_detectors()

    def evaluate(
        self,
        event: RuntimeEvent,
        history: list[RuntimeEvent] | None = None,
    ) -> Decision:
        history = history or []

        # 1. Detectors
        detector_hits: list[str] = []
        for det in self._detectors:
            detector_hits.extend(det.detect(event, history))
        unique_hits = list(dict.fromkeys(detector_hits))  # dedup, preserve order

        # 2. Rule engine (base risk)
        risk = rules.compute_risk(event)
        risk = min(risk + len(set(unique_hits)) * 10.0, 100.0)

        # 3. Policy override (before threshold checks)
        if self._policy_engine is not None:
            pd = self._policy_engine.evaluate(event)
            if pd is not None:
                pd.detector_hits = unique_hits
                return pd

        # 4. Threshold routing
        if risk < self._warn:
            return Decision(
                DecisionType.ALLOW, risk, "low risk", detector_hits=unique_hits
            )
        if risk < self._block:
            return Decision(
                DecisionType.WARN, risk, "elevated risk", detector_hits=unique_hits
            )

        # 5. LLM escalation
        if self._chain is not None:
            ctx = EvalContext(
                user_goal=event.goal,
                tool_call=ToolCall(
                    name=event.tool_name or f"{event.tool_type.value}.{event.action.value}",
                    arguments={"target": event.target, **event.metadata},
                    session_id=event.session_id,
                ),
                recent_history=[
                    ToolCall(
                        name=h.tool_name or f"{h.tool_type.value}.{h.action.value}",
                        arguments={"target": h.target, **h.metadata},
                        session_id=h.session_id,
                    )
                    for h in history
                ],
            )
            decision = self._chain.evaluate(ctx)
            decision.llm_used = True
            decision.risk_score = max(decision.risk_score, risk)
            decision.detector_hits = unique_hits
            return decision

        return Decision(
            DecisionType.BLOCK,
            risk,
            "high risk — no LLM evaluator configured",
            detector_hits=unique_hits,
        )
