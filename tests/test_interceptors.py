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
