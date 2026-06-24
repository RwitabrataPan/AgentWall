"""
Integration tests for AgentWall + LangChain.

Tests invoke tools through LangChain's real BaseTool.run() pipeline — no
LLM calls are made. The framework's tool dispatch mechanism is exercised
end-to-end via the monkey-patched _run() interception.
"""
from __future__ import annotations

import pytest
from langchain_core.tools import tool, StructuredTool

from agentwall.core.event_manager import EventManager
from agentwall.core.session_manager import SessionManager
from agentwall.core.types import ToolType
from agentwall.integrations.langchain import protect_langchain_agent, wrap_langchain_tool
from agentwall.interceptors.tool import ToolInterceptor
from agentwall.security.engine import SecurityEngine
from agentwall.security.exceptions import AgentWallSecurityException


# ── wrap_langchain_tool ────────────────────────────────────────────────────

def test_wrapped_tool_passes_through_allow(db):
    """Wrapped LangChain tool invokes original function on safe input."""
    @tool
    def read_file(path: str) -> str:
        """Read a file."""
        return f"contents:{path}"

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    session = SessionManager(db).create("fix login bug")
    interceptor = ToolInterceptor(db, engine)

    wrap_langchain_tool(
        read_file,
        tool_type=ToolType.FILESYSTEM,
        session_id=session.id,
        goal="fix login bug",
        interceptor=interceptor,
    )

    result = read_file.run("/project/login.tsx")
    assert "contents:/project/login.tsx" in result


def test_wrapped_tool_blocks_sensitive_path(db):
    """Wrapped LangChain tool raises AgentWallSecurityException on sensitive target."""
    @tool
    def read_file(path: str) -> str:
        """Read a file."""
        return "secret"

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    session = SessionManager(db).create("fix login bug")
    interceptor = ToolInterceptor(db, engine)

    wrap_langchain_tool(
        read_file,
        tool_type=ToolType.FILESYSTEM,
        session_id=session.id,
        goal="fix login bug",
        interceptor=interceptor,
    )

    with pytest.raises(AgentWallSecurityException) as exc_info:
        read_file.run("/home/user/.ssh/id_rsa")

    assert exc_info.value.event.target == "/home/user/.ssh/id_rsa"
    assert exc_info.value.decision.risk_score >= 70


def test_wrapped_tool_persists_event(db):
    """Every tool call records a ToolEvent in DB."""
    @tool
    def search(query: str) -> str:
        """Search the codebase."""
        return f"results:{query}"

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    session = SessionManager(db).create("fix login bug")
    interceptor = ToolInterceptor(db, engine)

    wrap_langchain_tool(
        search,
        tool_type=ToolType.API,
        session_id=session.id,
        goal="fix login bug",
        interceptor=interceptor,
    )

    search.run("authentication bug")

    events = EventManager(db).get_events(session.id)
    assert len(events) == 1
    assert events[0].tool_type == "api"


def test_wrapped_tool_persists_evaluation(db):
    """Every tool call records an Evaluation in DB."""
    @tool
    def search(query: str) -> str:
        """Search."""
        return "ok"

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    session = SessionManager(db).create("fix login bug")
    interceptor = ToolInterceptor(db, engine)

    wrap_langchain_tool(
        search,
        tool_type=ToolType.API,
        session_id=session.id,
        goal="fix login bug",
        interceptor=interceptor,
    )

    search.run("safe query")

    events = EventManager(db).get_events_with_evaluations(session.id)
    assert events[0].evaluation is not None
    assert events[0].evaluation.decision in ("allow", "warn")


def test_blocked_call_recorded(db):
    """Blocked tool calls are still persisted before raising."""
    @tool
    def read_file(path: str) -> str:
        """Read a file."""
        return "secret"

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    session = SessionManager(db).create("fix login bug")
    interceptor = ToolInterceptor(db, engine)

    wrap_langchain_tool(
        read_file,
        tool_type=ToolType.FILESYSTEM,
        session_id=session.id,
        goal="fix login bug",
        interceptor=interceptor,
    )

    with pytest.raises(AgentWallSecurityException):
        read_file.run("/etc/shadow")

    events = EventManager(db).get_events_with_evaluations(session.id)
    assert events[0].evaluation.decision == "block"


def test_wrap_preserves_tool_name(db):
    """Wrapping does not change the tool's name or description."""
    @tool
    def my_special_tool(x: str) -> str:
        """My special tool description."""
        return x

    engine = SecurityEngine(detectors=[])
    session = SessionManager(db).create("test")
    interceptor = ToolInterceptor(db, engine)

    wrap_langchain_tool(
        my_special_tool,
        tool_type=ToolType.API,
        session_id=session.id,
        goal="test",
        interceptor=interceptor,
    )

    assert my_special_tool.name == "my_special_tool"
    assert "My special tool" in my_special_tool.description


# ── protect_langchain_agent ────────────────────────────────────────────────

class _FakeExecutor:
    """Minimal executor stub with tools list."""
    def __init__(self, tools):
        self.tools = tools


def test_protect_langchain_agent_wraps_all_tools(db):
    """protect_langchain_agent wraps all tools in executor.tools."""
    @tool
    def tool_a(x: str) -> str:
        """Tool A."""
        return x

    @tool
    def tool_b(y: str) -> str:
        """Tool B."""
        return y

    original_a_func = tool_a.func
    original_b_func = tool_b.func

    executor = _FakeExecutor([tool_a, tool_b])
    engine = SecurityEngine(detectors=[])
    wall = protect_langchain_agent(
        executor,
        goal="test",
        db=db,
        engine=engine,
    )

    # Both tools are now patched
    assert tool_a.func is not original_a_func
    assert tool_b.func is not original_b_func
    wall.end_session()


def test_protect_langchain_agent_session_created(db):
    """protect_langchain_agent creates a DB session."""
    executor = _FakeExecutor([])
    engine = SecurityEngine(detectors=[])
    wall = protect_langchain_agent(executor, goal="fix bugs", db=db, engine=engine)

    session = SessionManager(db).get(wall.session_id)
    assert session is not None
    assert session.user_goal == "fix bugs"
    wall.end_session()


def test_protect_langchain_agent_tool_type_map(db):
    """tool_type_map is applied per tool name."""
    @tool
    def read_file(path: str) -> str:
        """Read a file."""
        return "ok"

    executor = _FakeExecutor([read_file])
    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    wall = protect_langchain_agent(
        executor,
        goal="test",
        tool_type_map={"read_file": ToolType.FILESYSTEM},
        db=db,
        engine=engine,
    )

    read_file.run("/project/login.tsx")

    events = EventManager(db).get_events(wall.session_id)
    assert events[0].tool_type == "filesystem"
    wall.end_session()


def test_protect_langchain_agent_end_session(db):
    """end_session() marks session as ended."""
    executor = _FakeExecutor([])
    engine = SecurityEngine(detectors=[])
    wall = protect_langchain_agent(executor, goal="test", db=db, engine=engine)
    wall.end_session()

    session = SessionManager(db).get(wall.session_id)
    assert session.ended_at is not None


# ── async tool interception ────────────────────────────────────────────────

def test_async_tool_coroutine_patched(db):
    """wrap_langchain_tool patches coroutine for async tools, not func."""
    @tool
    async def fetch_data(url: str) -> str:
        """Fetch data."""
        return f"data:{url}"

    assert fetch_data.coroutine is not None
    original_coro = fetch_data.coroutine

    session = SessionManager(db).create("test")
    engine = SecurityEngine(detectors=[])
    interceptor = ToolInterceptor(db, engine)
    wrap_langchain_tool(
        fetch_data,
        tool_type=ToolType.API,
        session_id=session.id,
        goal="test",
        interceptor=interceptor,
    )

    assert fetch_data.coroutine is not original_coro
    assert fetch_data.func is None  # not touched for async tools


def test_async_tool_intercepted_via_arun(db):
    """AgentWall fires before_execute when an async LangChain tool is arun()."""
    import asyncio

    call_log: list[str] = []

    @tool
    async def async_read(path: str) -> str:
        """Async file read."""
        call_log.append(f"original:{path}")
        return f"contents:{path}"

    session = SessionManager(db).create("fix bug")
    engine = SecurityEngine(detectors=[])
    interceptor = ToolInterceptor(db, engine)

    wrap_langchain_tool(
        async_read,
        tool_type=ToolType.FILESYSTEM,
        session_id=session.id,
        goal="fix bug",
        interceptor=interceptor,
    )

    result = asyncio.run(async_read.arun("/app/main.py"))

    assert "contents:/app/main.py" in result
    assert call_log == ["original:/app/main.py"]

    events = EventManager(db).get_events(session_id=session.id)
    assert len(events) == 1
    assert events[0].tool_type == "filesystem"
