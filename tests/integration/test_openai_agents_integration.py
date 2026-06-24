"""
Integration tests for AgentWall + OpenAI Agents SDK.

Tests invoke the real framework's FunctionTool.on_invoke_tool pipeline — no
LLM calls are made. The SDK's async dispatch mechanism is exercised directly.
"""
from __future__ import annotations

import json

import pytest
from agents import Agent, function_tool
from agents.tool_context import ToolContext
from agents.usage import Usage

from agentwall.core.event_manager import EventManager
from agentwall.core.session_manager import SessionManager
from agentwall.core.types import ToolType
from agentwall.integrations.openai_agents import (
    protect_openai_agent,
    wrap_openai_function_tool,
)
from agentwall.interceptors.tool import ToolInterceptor
from agentwall.security.engine import SecurityEngine
from agentwall.security.exceptions import AgentWallSecurityException


def _make_ctx(tool_name: str, args_json: str) -> ToolContext:
    return ToolContext(
        context=None,
        usage=Usage(),
        tool_name=tool_name,
        tool_call_id="call_test_123",
        tool_arguments=args_json,
    )


# ── wrap_openai_function_tool ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wrapped_tool_passes_through_allow(db):
    """Wrapped FunctionTool invokes original function on safe input."""
    @function_tool
    def read_file(path: str) -> str:
        """Read a file."""
        return f"contents:{path}"

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    from agentwall.core.session_manager import SessionManager
    session = SessionManager(db).create("fix login bug")
    interceptor = ToolInterceptor(db, engine)

    wrapped = wrap_openai_function_tool(
        read_file,
        tool_type=ToolType.FILESYSTEM,
        session_id=session.id,
        goal="fix login bug",
        interceptor=interceptor,
    )

    args_json = json.dumps({"path": "/project/login.tsx"})
    ctx = _make_ctx("read_file", args_json)
    result = await wrapped.on_invoke_tool(ctx, args_json)

    assert "contents:/project/login.tsx" in str(result)


@pytest.mark.asyncio
async def test_wrapped_tool_blocks_sensitive_path(db):
    """Wrapped FunctionTool raises AgentWallSecurityException on sensitive target."""
    @function_tool
    def read_file(path: str) -> str:
        """Read a file."""
        return "secret"

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    session = SessionManager(db).create("fix login bug")
    interceptor = ToolInterceptor(db, engine)

    wrapped = wrap_openai_function_tool(
        read_file,
        tool_type=ToolType.FILESYSTEM,
        session_id=session.id,
        goal="fix login bug",
        interceptor=interceptor,
    )

    args_json = json.dumps({"path": "/home/user/.ssh/id_rsa"})
    ctx = _make_ctx("read_file", args_json)

    with pytest.raises(AgentWallSecurityException) as exc_info:
        await wrapped.on_invoke_tool(ctx, args_json)

    assert exc_info.value.decision.risk_score >= 70
    assert exc_info.value.event.target == "/home/user/.ssh/id_rsa"


@pytest.mark.asyncio
async def test_wrapped_tool_persists_event_and_evaluation(db):
    """Event and evaluation are recorded in DB on every tool call."""
    @function_tool
    def list_files(directory: str) -> str:
        """List files."""
        return "file1.py\nfile2.py"

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    session = SessionManager(db).create("fix login bug")
    interceptor = ToolInterceptor(db, engine)

    wrapped = wrap_openai_function_tool(
        list_files,
        tool_type=ToolType.FILESYSTEM,
        session_id=session.id,
        goal="fix login bug",
        interceptor=interceptor,
    )

    args_json = json.dumps({"directory": "/project/src"})
    ctx = _make_ctx("list_files", args_json)
    await wrapped.on_invoke_tool(ctx, args_json)

    events = EventManager(db).get_events_with_evaluations(session.id)
    assert len(events) == 1
    assert events[0].tool_type == "filesystem"
    assert events[0].target == "/project/src"
    assert events[0].evaluation is not None
    assert events[0].evaluation.decision in ("allow", "warn")


@pytest.mark.asyncio
async def test_blocked_call_still_recorded(db):
    """Blocked tool calls are still recorded in DB before raising."""
    @function_tool
    def read_file(path: str) -> str:
        """Read a file."""
        return "secret"

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    session = SessionManager(db).create("fix login bug")
    interceptor = ToolInterceptor(db, engine)

    wrapped = wrap_openai_function_tool(
        read_file,
        tool_type=ToolType.FILESYSTEM,
        session_id=session.id,
        goal="fix login bug",
        interceptor=interceptor,
    )

    args_json = json.dumps({"path": "/etc/shadow"})
    with pytest.raises(AgentWallSecurityException):
        await wrapped.on_invoke_tool(_make_ctx("read_file", args_json), args_json)

    events = EventManager(db).get_events_with_evaluations(session.id)
    assert len(events) == 1
    assert events[0].evaluation.decision == "block"


# ── protect_openai_agent ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_protect_agent_wraps_all_tools(db):
    """protect_openai_agent replaces all FunctionTools with wrapped versions."""
    @function_tool
    def tool_a(x: str) -> str:
        """Tool A."""
        return x

    @function_tool
    def tool_b(y: str) -> str:
        """Tool B."""
        return y

    agent = Agent(name="test", instructions="test", tools=[tool_a, tool_b])
    engine = SecurityEngine(detectors=[])
    wall, protected = protect_openai_agent(
        agent,
        goal="test goal",
        db=db,
        engine=engine,
    )

    assert len(protected.tools) == 2
    # Wrapped tools have different on_invoke_tool
    assert protected.tools[0].on_invoke_tool is not tool_a.on_invoke_tool
    assert protected.tools[1].on_invoke_tool is not tool_b.on_invoke_tool
    wall.end_session()


@pytest.mark.asyncio
async def test_protect_agent_session_created(db):
    """protect_openai_agent creates a DB session."""
    agent = Agent(name="test", instructions="test", tools=[])
    engine = SecurityEngine(detectors=[])
    wall, _ = protect_openai_agent(agent, goal="test goal", db=db, engine=engine)

    session = SessionManager(db).get(wall.session_id)
    assert session is not None
    assert session.user_goal == "test goal"
    wall.end_session()


@pytest.mark.asyncio
async def test_protect_agent_tool_type_map(db):
    """tool_type_map assigns correct ToolType to wrapped tools."""
    @function_tool
    def read_file(path: str) -> str:
        """Read a file."""
        return "ok"

    agent = Agent(name="test", instructions="test", tools=[read_file])
    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    wall, protected = protect_openai_agent(
        agent,
        goal="test",
        tool_type_map={"read_file": ToolType.FILESYSTEM},
        db=db,
        engine=engine,
    )

    # invoke a safe path — should succeed
    args_json = json.dumps({"path": "/project/src/app.py"})
    ctx = _make_ctx("read_file", args_json)
    result = await protected.tools[0].on_invoke_tool(ctx, args_json)
    assert "ok" in str(result)

    events = EventManager(db).get_events(wall.session_id)
    assert events[0].tool_type == "filesystem"
    wall.end_session()


@pytest.mark.asyncio
async def test_protect_agent_end_session(db):
    """end_session() closes the DB session."""
    agent = Agent(name="test", instructions="test", tools=[])
    engine = SecurityEngine(detectors=[])
    wall, _ = protect_openai_agent(agent, goal="test", db=db, engine=engine)

    wall.end_session()
    session = SessionManager(db).get(wall.session_id)
    assert session.ended_at is not None
