from __future__ import annotations

import pytest

from agentwall.core.event_manager import EventManager
from agentwall.core.session_manager import SessionManager
from agentwall.core.types import ResourceCategory, ToolAction, ToolType
from agentwall.interceptors.tool import ToolInterceptor, protect_tool
from agentwall.security.engine import SecurityEngine
from agentwall.security.result_analyzer import ResultClassification


def _engine() -> SecurityEngine:
    return SecurityEngine(detectors=[])


def _make_event(session_id: str, tool_type: ToolType = ToolType.FILESYSTEM):
    from agentwall.core.types import RuntimeEvent, ToolAction, ResourceCategory
    return RuntimeEvent(
        session_id=session_id,
        goal="fix bug",
        tool_type=tool_type,
        action=ToolAction.READ,
        target="/app/login.tsx",
        resource_category=ResourceCategory.CODE,
        metadata={},
        tool_name="read_file",
    )


def test_after_execute_stores_classification(db):
    session = SessionManager(db).create("fix bug")
    interceptor = ToolInterceptor(db, _engine())
    event = _make_event(session.id)

    interceptor.before_execute(event)
    interceptor.after_execute(event, "normal file content here")

    events = EventManager(db).get_events_with_evaluations(session.id)
    assert len(events) == 1
    eval_ = events[0].evaluation
    assert eval_ is not None
    assert eval_.result_classification == ResultClassification.NORMAL.value
    assert eval_.post_execution_risk == 0.0
    assert eval_.result_detector_hits == []
    assert eval_.result_metadata is not None
    assert "output_length" in eval_.result_metadata


def test_after_execute_detects_sensitive_content(db):
    session = SessionManager(db).create("fix bug")
    interceptor = ToolInterceptor(db, _engine())
    event = _make_event(session.id)

    interceptor.before_execute(event)
    interceptor.after_execute(event, "-----BEGIN RSA PRIVATE KEY-----\nMIIEo...")

    events = EventManager(db).get_events_with_evaluations(session.id)
    eval_ = events[0].evaluation
    assert eval_.result_classification == ResultClassification.SENSITIVE_DATA_EXPOSURE.value
    assert eval_.post_execution_risk > 0
    assert "sensitive_content_in_output" in eval_.result_detector_hits


def test_after_execute_does_not_retroactively_block(db):
    """Even with sensitive result, pre-execution ALLOW decision is unchanged."""
    session = SessionManager(db).create("fix bug")
    interceptor = ToolInterceptor(db, _engine())
    event = _make_event(session.id)

    decision = interceptor.before_execute(event)
    assert decision.type.value == "allow"

    # after_execute should not raise or change pre-execution decision
    interceptor.after_execute(event, "-----BEGIN PRIVATE KEY-----\nsecret")

    events = EventManager(db).get_events_with_evaluations(session.id)
    assert events[0].evaluation.decision == "allow"  # unchanged


def test_after_execute_email_dispatch(db):
    session = SessionManager(db).create("send report")
    interceptor = ToolInterceptor(db, _engine())
    event = _make_event(session.id, ToolType.EMAIL)

    interceptor.before_execute(event)
    interceptor.after_execute(event, "Email sent to recipient@example.com")

    events = EventManager(db).get_events_with_evaluations(session.id)
    eval_ = events[0].evaluation
    assert eval_.result_classification == ResultClassification.EMAIL_DISPATCH.value
    assert "email_dispatched" in eval_.result_detector_hits


def test_after_execute_without_before_is_noop(db):
    """after_execute with no matching before_execute should not raise."""
    session = SessionManager(db).create("test")
    interceptor = ToolInterceptor(db, _engine())
    event = _make_event(session.id)
    # Never called before_execute — should silently do nothing
    interceptor.after_execute(event, "some result")


def test_protect_tool_after_execute_wired(db):
    """protect_tool wrapper calls after_execute on successful tool return."""
    session = SessionManager(db).create("fix bug")
    interceptor = ToolInterceptor(db, _engine())

    def read_file(path: str) -> str:
        return "normal file contents"

    wrapped = protect_tool(
        read_file,
        tool_type=ToolType.FILESYSTEM,
        session_id=session.id,
        goal="fix bug",
        interceptor=interceptor,
    )
    result = wrapped("/app/login.tsx")
    assert result == "normal file contents"

    events = EventManager(db).get_events_with_evaluations(session.id)
    assert len(events) == 1
    assert events[0].evaluation.result_classification == ResultClassification.NORMAL.value


def test_protect_tool_metadata_no_content_stored(db):
    """result_metadata must not contain raw tool output."""
    session = SessionManager(db).create("fix bug")
    # Use high thresholds so pre-execution never blocks (we're testing post-exec only)
    engine = SecurityEngine(warn_threshold=200, block_threshold=201, detectors=[])
    interceptor = ToolInterceptor(db, engine)
    secret = "-----BEGIN RSA PRIVATE KEY-----\nSECRET_DATA"

    def read_creds(path: str) -> str:
        return secret

    wrapped = protect_tool(
        read_creds,
        tool_type=ToolType.FILESYSTEM,
        session_id=session.id,
        goal="fix bug",
        interceptor=interceptor,
    )
    wrapped("/app/config.txt")

    events = EventManager(db).get_events_with_evaluations(session.id)
    meta = events[0].evaluation.result_metadata
    # Raw secret must not appear in metadata
    for v in meta.values():
        assert secret not in str(v)
