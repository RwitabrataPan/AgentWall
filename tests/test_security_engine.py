from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from agentwall.core.types import (
    Decision,
    DecisionType,
    ResourceCategory,
    RuntimeEvent,
    ToolAction,
    ToolType,
)
from agentwall.security.engine import SecurityEngine


def _event(target: str, tool_type=ToolType.FILESYSTEM, action=ToolAction.READ) -> RuntimeEvent:
    return RuntimeEvent(
        session_id="sess-1",
        goal="fix login bug",
        tool_type=tool_type,
        action=action,
        target=target,
        resource_category=ResourceCategory.UNKNOWN,
        metadata={},
    )


def test_allow_below_warn_threshold():
    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0)
    decision = engine.evaluate(_event("/home/user/project/login.tsx"))
    assert decision.type == DecisionType.ALLOW
    assert decision.risk_score < 30.0
    assert decision.llm_used is False


def test_warn_between_thresholds():
    engine = SecurityEngine(warn_threshold=0.0, block_threshold=70.0)
    # Write action pushes risk to ~25 which is >= warn_threshold=0
    decision = engine.evaluate(_event("/tmp/output.txt", action=ToolAction.WRITE))
    assert decision.type == DecisionType.WARN
    assert decision.llm_used is False


def test_block_no_llm_when_chain_none():
    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, provider_chain=None)
    decision = engine.evaluate(_event("rm -rf /", ToolType.TERMINAL, ToolAction.EXECUTE))
    assert decision.type == DecisionType.BLOCK
    assert decision.llm_used is False


def test_llm_escalation_when_chain_present():
    mock_chain = MagicMock()
    mock_chain.evaluate.return_value = Decision(
        type=DecisionType.WARN,
        risk_score=50.0,
        reason="LLM says warn",
        llm_used=False,
    )
    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, provider_chain=mock_chain)
    decision = engine.evaluate(_event("rm -rf /", ToolType.TERMINAL, ToolAction.EXECUTE))

    assert mock_chain.evaluate.called
    assert decision.llm_used is True
    assert decision.risk_score >= 70.0  # max(llm_score, rule_score)


def test_llm_escalation_preserves_block():
    mock_chain = MagicMock()
    mock_chain.evaluate.return_value = Decision(
        type=DecisionType.BLOCK,
        risk_score=80.0,
        reason="LLM blocked",
        llm_used=False,
    )
    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, provider_chain=mock_chain)
    decision = engine.evaluate(_event("/etc/shadow", ToolType.FILESYSTEM, ToolAction.READ))
    assert decision.type == DecisionType.BLOCK
    assert decision.llm_used is True


def test_custom_thresholds():
    engine = SecurityEngine(warn_threshold=5.0, block_threshold=10.0)
    # Safe filesystem read has base risk ~0; verify it's ALLOW
    decision = engine.evaluate(_event("/home/user/login.tsx"))
    assert decision.type == DecisionType.ALLOW


def test_decision_has_risk_score():
    engine = SecurityEngine()
    decision = engine.evaluate(_event("/home/user/login.tsx"))
    assert isinstance(decision.risk_score, float)
    assert decision.risk_score >= 0.0
