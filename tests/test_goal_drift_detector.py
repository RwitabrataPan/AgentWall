from __future__ import annotations

import pytest

from agentwall.core.types import ResourceCategory, RuntimeEvent, ToolAction, ToolType
from agentwall.security.detectors import GoalDriftDetector


def _event(
    goal: str,
    tool_type: ToolType = ToolType.FILESYSTEM,
    action: ToolAction = ToolAction.READ,
    target: str = "login.py",
    resource_category: ResourceCategory = ResourceCategory.CODE,
) -> RuntimeEvent:
    return RuntimeEvent(
        session_id="test",
        goal=goal,
        tool_type=tool_type,
        action=action,
        target=target,
        resource_category=resource_category,
        metadata={},
        tool_name="test_tool",
    )


det = GoalDriftDetector()


def test_no_drift_code_goal_code_access():
    hits = det.detect(_event("fix login bug"), [])
    assert not hits


def test_credential_access_off_code_goal():
    e = _event(
        "fix login bug",
        target=".env",
        resource_category=ResourceCategory.CREDENTIALS,
    )
    hits = det.detect(e, [])
    assert "goal_drift:credential_access_off_goal" in hits


def test_no_drift_when_goal_mentions_credentials():
    e = _event(
        "rotate api key credential",
        target=".env",
        resource_category=ResourceCategory.CREDENTIALS,
    )
    hits = det.detect(e, [])
    assert "goal_drift:credential_access_off_goal" not in hits


def test_unexpected_email_off_goal():
    e = _event(
        "fix authentication bug",
        tool_type=ToolType.EMAIL,
        action=ToolAction.SEND,
        target="attacker@evil.com",
        resource_category=ResourceCategory.UNKNOWN,
    )
    hits = det.detect(e, [])
    assert "goal_drift:unexpected_email" in hits


def test_email_expected_when_goal_mentions_send():
    e = _event(
        "send report via email",
        tool_type=ToolType.EMAIL,
        action=ToolAction.SEND,
        target="team@company.com",
        resource_category=ResourceCategory.UNKNOWN,
    )
    hits = det.detect(e, [])
    assert "goal_drift:unexpected_email" not in hits


def test_system_access_off_code_goal():
    e = _event(
        "fix login bug",
        target="/etc/shadow",
        resource_category=ResourceCategory.SYSTEM,
    )
    hits = det.detect(e, [])
    assert "goal_drift:system_access_off_goal" in hits


def test_no_drift_empty_goal():
    e = _event("", resource_category=ResourceCategory.CREDENTIALS)
    hits = det.detect(e, [])
    assert not hits


def test_sensitive_target_off_goal():
    e = _event(
        "fix bug in auth module",
        target="id_rsa",
        resource_category=ResourceCategory.CODE,
    )
    hits = det.detect(e, [])
    assert "goal_drift:sensitive_target_off_goal" in hits
