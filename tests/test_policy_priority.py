from __future__ import annotations

import pytest

from agentwall.core.types import ResourceCategory, RuntimeEvent, ToolAction, ToolType
from agentwall.security.policy_engine import PolicyEngine


def _ev(target: str = "/file") -> RuntimeEvent:
    return RuntimeEvent(
        session_id="s1", goal="test",
        tool_type=ToolType.FILESYSTEM, action=ToolAction.READ,
        target=target, resource_category=ResourceCategory.UNKNOWN, metadata={},
    )


def test_higher_priority_wins(db):
    pe = PolicyEngine(db)
    pe.create("low", {"rules": [{"decision": "warn", "reason": "low"}]}, priority=1)
    pe.create("high", {"rules": [{"decision": "block", "reason": "high"}]}, priority=10)
    decision = pe.evaluate(_ev())
    assert decision.type.value == "block"


def test_lower_priority_does_not_override(db):
    pe = PolicyEngine(db)
    pe.create("high", {"rules": [{"decision": "allow", "reason": "high"}]}, priority=10)
    pe.create("low", {"rules": [{"decision": "block", "reason": "low"}]}, priority=1)
    decision = pe.evaluate(_ev())
    assert decision.type.value == "allow"


def test_equal_priority_creation_order(db):
    pe = PolicyEngine(db)
    pe.create("first", {"rules": [{"decision": "warn"}]}, priority=0)
    pe.create("second", {"rules": [{"decision": "block"}]}, priority=0)
    decision = pe.evaluate(_ev())
    assert decision.type.value == "warn"  # creation-order tiebreak


def test_default_priority_zero(db):
    pe = PolicyEngine(db)
    p = pe.create("x", {"rules": []})
    assert p.priority == 0


def test_set_priority(db):
    pe = PolicyEngine(db)
    pe.create("p", {"rules": []}, priority=0)
    pe.set_priority("p", 99)
    row = pe.get("p")
    assert row.priority == 99


def test_set_priority_unknown_raises(db):
    pe = PolicyEngine(db)
    with pytest.raises(KeyError):
        pe.set_priority("nonexistent", 5)


def test_list_ordered_by_priority_desc(db):
    pe = PolicyEngine(db)
    pe.create("a", {"rules": []}, priority=5)
    pe.create("b", {"rules": []}, priority=10)
    pe.create("c", {"rules": []}, priority=1)
    names = [p.name for p in pe.list()]
    assert names[0] == "b"
    assert names[-1] == "c"


def test_priority_in_schema(db):
    pe = PolicyEngine(db)
    p = pe.create("z", {"rules": []}, priority=7)
    from agentwall.models.schemas import PolicySchema
    schema = PolicySchema.model_validate(p)
    assert schema.priority == 7
