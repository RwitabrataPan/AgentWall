from __future__ import annotations

import pytest
from agentwall.core.types import DecisionType, ResourceCategory, ToolAction, ToolType
from agentwall.interceptors import protect_agent, protect_tool
from agentwall.interceptors.tool import ToolInterceptor
from agentwall.security.engine import SecurityEngine
from agentwall.security.exceptions import AgentWallSecurityException


# --- protect_tool ---

def test_protect_tool_allows_safe_call(db):
    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0)
    interceptor = ToolInterceptor(db, engine)
    session_id = "sess-test"

    # Create a session so FK constraint passes
    from agentwall.core.session_manager import SessionManager
    session = SessionManager(db).create("fix login bug")

    def read_file(path: str) -> str:
        return f"contents of {path}"

    wrapped = protect_tool(
        read_file,
        tool_type=ToolType.FILESYSTEM,
        session_id=session.id,
        goal="fix login bug",
        interceptor=interceptor,
    )
    result = wrapped("/home/user/project/login.tsx")
    assert result == "contents of /home/user/project/login.tsx"


def test_protect_tool_blocks_sensitive_path(db):
    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0)
    interceptor = ToolInterceptor(db, engine)

    from agentwall.core.session_manager import SessionManager
    session = SessionManager(db).create("fix login bug")

    def read_file(path: str) -> str:
        return "secret"

    wrapped = protect_tool(
        read_file,
        tool_type=ToolType.FILESYSTEM,
        session_id=session.id,
        goal="fix login bug",
        interceptor=interceptor,
    )
    with pytest.raises(AgentWallSecurityException) as exc_info:
        wrapped("/home/user/.ssh/id_rsa")

    assert exc_info.value.decision.type == DecisionType.BLOCK
    assert exc_info.value.event.target == "/home/user/.ssh/id_rsa"


def test_protect_tool_persists_event(db):
    from agentwall.core.event_manager import EventManager
    from agentwall.core.session_manager import SessionManager

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0)
    interceptor = ToolInterceptor(db, engine)
    session = SessionManager(db).create("fix login bug")

    def read_file(path: str) -> str:
        return "ok"

    wrapped = protect_tool(
        read_file,
        tool_type=ToolType.FILESYSTEM,
        session_id=session.id,
        goal="fix login bug",
        interceptor=interceptor,
    )
    wrapped("/home/user/project/auth.ts")

    events = EventManager(db).get_events(session.id)
    assert len(events) == 1
    assert events[0].tool_type == "filesystem"
    assert events[0].target == "/home/user/project/auth.ts"


def test_protect_tool_persists_evaluation(db):
    from agentwall.core.event_manager import EventManager
    from agentwall.core.session_manager import SessionManager

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0)
    interceptor = ToolInterceptor(db, engine)
    session = SessionManager(db).create("fix login bug")

    def read_file(path: str) -> str:
        return "ok"

    wrapped = protect_tool(
        read_file,
        tool_type=ToolType.FILESYSTEM,
        session_id=session.id,
        goal="fix login bug",
        interceptor=interceptor,
    )
    wrapped("/home/user/project/auth.ts")

    events = EventManager(db).get_events_with_evaluations(session.id)
    assert events[0].evaluation is not None
    assert events[0].evaluation.decision in ("allow", "warn", "block")


def test_protect_tool_blocked_event_still_persisted(db):
    from agentwall.core.event_manager import EventManager
    from agentwall.core.session_manager import SessionManager

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0)
    interceptor = ToolInterceptor(db, engine)
    session = SessionManager(db).create("fix login bug")

    def read_file(path: str) -> str:
        return "secret"

    wrapped = protect_tool(
        read_file,
        tool_type=ToolType.FILESYSTEM,
        session_id=session.id,
        goal="fix login bug",
        interceptor=interceptor,
    )
    with pytest.raises(AgentWallSecurityException):
        wrapped("/etc/shadow")

    events = EventManager(db).get_events_with_evaluations(session.id)
    assert len(events) == 1
    assert events[0].evaluation.decision == "block"


# --- protect_agent ---

class _FakeAgent:
    def run(self, prompt: str) -> str:
        return f"done: {prompt}"


def test_protect_agent_creates_session(db):
    engine = SecurityEngine()
    agent = protect_agent(_FakeAgent(), goal="fix login bug", db=db, engine=engine)
    assert agent.session_id is not None
    assert agent.goal == "fix login bug"


def test_protect_agent_run_delegates(db):
    engine = SecurityEngine()
    agent = protect_agent(_FakeAgent(), goal="fix login bug", db=db, engine=engine)
    result = agent.run("hello")
    assert result == "done: hello"


def test_protect_agent_explicit_session_close(db):
    from agentwall.core.session_manager import SessionManager

    engine = SecurityEngine()
    agent = protect_agent(_FakeAgent(), goal="fix login bug", db=db, engine=engine)
    sid = agent.session_id

    session_before = SessionManager(db).get(sid)
    assert session_before.ended_at is None

    agent.end_session()

    session_after = SessionManager(db).get(sid)
    assert session_after.ended_at is not None


def test_protect_agent_context_manager_closes_session(db):
    from agentwall.core.session_manager import SessionManager

    engine = SecurityEngine()
    with protect_agent(_FakeAgent(), goal="fix login bug", db=db, engine=engine) as agent:
        sid = agent.session_id
        agent.run("hello")

    session = SessionManager(db).get(sid)
    assert session.ended_at is not None


def test_protect_agent_session_not_closed_after_run(db):
    from agentwall.core.session_manager import SessionManager

    engine = SecurityEngine()
    agent = protect_agent(_FakeAgent(), goal="fix login bug", db=db, engine=engine)
    agent.run("hello")

    session = SessionManager(db).get(agent.session_id)
    assert session.ended_at is None


def test_protect_agent_protect_tool_blocks(db):
    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0)
    agent = protect_agent(_FakeAgent(), goal="fix login bug", db=db, engine=engine)

    def read_file(path: str) -> str:
        return "secret"

    safe_read = agent.protect_tool(read_file, tool_type=ToolType.FILESYSTEM)
    with pytest.raises(AgentWallSecurityException):
        safe_read("/etc/shadow")


def test_protect_agent_proxies_unknown_attrs(db):
    engine = SecurityEngine()

    class RichAgent:
        name = "my-agent"

        def run(self, x):
            return x

    agent = protect_agent(RichAgent(), goal="test", db=db, engine=engine)
    assert agent.name == "my-agent"


# --- execution tracking regression (v0.2.4) ---

def test_protect_agent_creates_execution(db):
    """ProtectedAgent must create exactly one Execution row per instantiation."""
    from agentwall.core.execution_manager import ExecutionManager

    engine = SecurityEngine()
    agent = protect_agent(_FakeAgent(), goal="train model", db=db, engine=engine)

    assert agent.execution_id is not None
    mgr = ExecutionManager(db)
    executions = mgr.list_all()
    assert len(executions) == 1
    assert executions[0].id == agent.execution_id


def test_protect_agent_links_session_to_execution(db):
    """Session created by ProtectedAgent must have execution_id matching the execution."""
    from agentwall.core.session_manager import SessionManager

    engine = SecurityEngine()
    agent = protect_agent(_FakeAgent(), goal="deploy pipeline", db=db, engine=engine)

    session = SessionManager(db).get(agent.session_id)
    assert session.execution_id == agent.execution_id


def test_protect_agent_finishes_execution_on_end_session(db):
    """end_session() must mark the execution as completed."""
    from agentwall.core.execution_manager import ExecutionManager

    engine = SecurityEngine()
    agent = protect_agent(_FakeAgent(), goal="run analysis", db=db, engine=engine)
    eid = agent.execution_id

    agent.end_session()

    executions = ExecutionManager(db).list_all()
    finished = next(e for e in executions if e.id == eid)
    assert finished.status == "completed"
    assert finished.finished_at is not None


# --- execution lifecycle regression (v0.2.5) ---

def test_end_session_idempotent(db):
    """Calling end_session() twice must not raise and must not change status."""
    from agentwall.core.execution_manager import ExecutionManager

    engine = SecurityEngine()
    agent = protect_agent(_FakeAgent(), goal="idempotent test", db=db, engine=engine)
    eid = agent.execution_id

    agent.end_session()
    agent.end_session()  # second call must be a no-op

    row = ExecutionManager(db).get(eid)
    assert row.status == "completed"


def test_end_session_finish_called_even_if_session_end_raises(db):
    """Regression (Gap 1): finish() must run even when session_mgr.end() raises."""
    from unittest.mock import patch
    from agentwall.core.execution_manager import ExecutionManager

    engine = SecurityEngine()
    agent = protect_agent(_FakeAgent(), goal="resilience test", db=db, engine=engine)
    eid = agent.execution_id

    with patch.object(agent._session_mgr, "end", side_effect=RuntimeError("db error")):
        agent.end_session()  # must not raise, and finish() must still run

    row = ExecutionManager(db).get(eid)
    assert row.status == "completed"
    assert row.finished_at is not None


def test_context_manager_marks_failed_on_exception(db):
    """Regression (Gap 3): __exit__ with exception must finalize as 'failed'."""
    from agentwall.core.execution_manager import ExecutionManager

    engine = SecurityEngine()
    eid = None
    try:
        with protect_agent(_FakeAgent(), goal="will fail", db=db, engine=engine) as agent:
            eid = agent.execution_id
            raise ValueError("agent error")
    except ValueError:
        pass

    row = ExecutionManager(db).get(eid)
    assert row.status == "failed"
    assert row.finished_at is not None


def test_context_manager_marks_completed_on_success(db):
    """__exit__ without exception must finalize as 'completed'."""
    from agentwall.core.execution_manager import ExecutionManager

    engine = SecurityEngine()
    with protect_agent(_FakeAgent(), goal="will succeed", db=db, engine=engine) as agent:
        eid = agent.execution_id

    row = ExecutionManager(db).get(eid)
    assert row.status == "completed"


def test_init_failure_after_execution_created_marks_failed(db):
    """Regression (Gap 2): execution must be 'failed' if __init__ raises after exec_mgr.create()."""
    from unittest.mock import patch
    from agentwall.core.execution_manager import ExecutionManager

    engine = SecurityEngine()
    with patch("agentwall.core.session_manager.SessionManager.create", side_effect=RuntimeError("db locked")):
        with pytest.raises(RuntimeError):
            protect_agent(_FakeAgent(), goal="orphan test", db=db, engine=engine)

    executions = ExecutionManager(db).list_all()
    assert len(executions) == 1
    assert executions[0].status == "failed"
