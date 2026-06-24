from __future__ import annotations

import pytest
from agentwall.core.types import (
    DecisionType,
    ResourceCategory,
    RuntimeEvent,
    ToolAction,
    ToolType,
)
from agentwall.security.policy_engine import PolicyEngine


def _ev(
    target: str,
    tool_type: ToolType = ToolType.FILESYSTEM,
    action: ToolAction = ToolAction.READ,
    resource_category: ResourceCategory = ResourceCategory.UNKNOWN,
) -> RuntimeEvent:
    return RuntimeEvent(
        session_id="s1",
        goal="fix login bug",
        tool_type=tool_type,
        action=action,
        target=target,
        resource_category=resource_category,
        metadata={},
    )


# ── CRUD ──────────────────────────────────────────────────────────────────

def test_create_and_get(db):
    pe = PolicyEngine(db)
    policy = pe.create("block-ssh", {
        "rules": [{"tool_type": "filesystem", "pattern": "*/.ssh/*", "decision": "block"}]
    })
    assert policy.name == "block-ssh"
    assert policy.enabled is True

    fetched = pe.get("block-ssh")
    assert fetched is not None
    assert fetched.name == "block-ssh"


def test_list_returns_all(db):
    pe = PolicyEngine(db)
    pe.create("p1", {"rules": []})
    pe.create("p2", {"rules": []})
    assert len(pe.list()) == 2


def test_update_replaces_config(db):
    pe = PolicyEngine(db)
    pe.create("p1", {"rules": []})
    updated = pe.update("p1", {"rules": [{"decision": "warn"}]})
    assert updated.config["rules"][0]["decision"] == "warn"


def test_delete_removes_policy(db):
    pe = PolicyEngine(db)
    pe.create("p1", {"rules": []})
    pe.delete("p1")
    assert pe.get("p1") is None


def test_enable_disable(db):
    pe = PolicyEngine(db)
    pe.create("p1", {"rules": []})
    pe.disable("p1")
    assert pe.get("p1").enabled is False
    pe.enable("p1")
    assert pe.get("p1").enabled is True


def test_update_nonexistent_raises(db):
    pe = PolicyEngine(db)
    with pytest.raises(KeyError):
        pe.update("no-such-policy", {})


# ── Evaluation ────────────────────────────────────────────────────────────

def test_no_match_returns_none(db):
    pe = PolicyEngine(db)
    pe.create("block-ssh", {
        "rules": [{"tool_type": "filesystem", "pattern": "*/.ssh/*", "decision": "block"}]
    })
    result = pe.evaluate(_ev("/project/src/login.tsx"))
    assert result is None


def test_pattern_match_blocks(db):
    pe = PolicyEngine(db)
    pe.create("block-ssh", {
        "rules": [{"pattern": "*/.ssh/*", "decision": "block", "reason": "SSH off-limits"}]
    })
    result = pe.evaluate(_ev("/home/user/.ssh/id_rsa"))
    assert result is not None
    assert result.type == DecisionType.BLOCK
    assert "SSH off-limits" in result.reason


def test_pattern_match_warns(db):
    pe = PolicyEngine(db)
    pe.create("warn-write", {
        "rules": [{"action": "write", "decision": "warn", "reason": "writes need review"}]
    })
    result = pe.evaluate(_ev("/project/output.txt", action=ToolAction.WRITE))
    assert result is not None
    assert result.type == DecisionType.WARN


def test_tool_type_filter(db):
    pe = PolicyEngine(db)
    pe.create("block-email", {
        "rules": [{"tool_type": "email", "action": "send", "decision": "block"}]
    })
    # Different tool type — should not match
    result = pe.evaluate(_ev("https://example.com", ToolType.API, ToolAction.SEND))
    assert result is None
    # Correct tool type — should match
    result = pe.evaluate(_ev("admin@corp.com", ToolType.EMAIL, ToolAction.SEND))
    assert result is not None
    assert result.type == DecisionType.BLOCK


def test_resource_category_filter(db):
    pe = PolicyEngine(db)
    pe.create("block-credentials", {
        "rules": [{"resource_category": "credentials", "decision": "block"}]
    })
    result = pe.evaluate(_ev("/project/login.tsx", resource_category=ResourceCategory.CODE))
    assert result is None
    result = pe.evaluate(_ev("/home/user/.env", resource_category=ResourceCategory.CREDENTIALS))
    assert result is not None
    assert result.type == DecisionType.BLOCK


def test_disabled_policy_skipped(db):
    pe = PolicyEngine(db)
    pe.create("block-ssh", {
        "rules": [{"pattern": "*/.ssh/*", "decision": "block"}]
    })
    pe.disable("block-ssh")
    result = pe.evaluate(_ev("/home/user/.ssh/id_rsa"))
    assert result is None


def test_policy_metadata_contains_name(db):
    pe = PolicyEngine(db)
    pe.create("my-policy", {
        "rules": [{"pattern": "*/.ssh/*", "decision": "block"}]
    })
    result = pe.evaluate(_ev("/home/user/.ssh/id_rsa"))
    assert result.metadata.get("policy_matched") == "my-policy"


def test_first_matching_rule_wins(db):
    pe = PolicyEngine(db)
    pe.create("mixed", {
        "rules": [
            {"pattern": "*/.ssh/*", "decision": "warn"},
            {"pattern": "*/.ssh/*", "decision": "block"},  # should not reach
        ]
    })
    result = pe.evaluate(_ev("/home/user/.ssh/id_rsa"))
    assert result.type == DecisionType.WARN
