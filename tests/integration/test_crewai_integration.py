"""
Integration tests for AgentWall + CrewAI.

Tests invoke tools through CrewAI's real BaseTool.run() pipeline — no
LLM calls are made. The framework's tool dispatch mechanism is exercised
end-to-end via the monkey-patched _run() interception.
"""
from __future__ import annotations

import pytest
from crewai.tools import tool, BaseTool
from crewai import Agent as CrewAgent, Task, Crew

from agentwall.core.event_manager import EventManager
from agentwall.core.session_manager import SessionManager
from agentwall.core.types import ToolType
from agentwall.integrations.crewai import protect_crewai_crew, wrap_crewai_tool
from agentwall.interceptors.tool import ToolInterceptor
from agentwall.security.engine import SecurityEngine
from agentwall.security.exceptions import AgentWallSecurityException


# ── wrap_crewai_tool ───────────────────────────────────────────────────────

def test_wrapped_tool_passes_through_allow(db):
    """Wrapped CrewAI tool invokes original function on safe input."""
    @tool("Read File")
    def read_file(path: str) -> str:
        """Read a file from the filesystem."""
        return f"contents:{path}"

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    session = SessionManager(db).create("fix login bug")
    interceptor = ToolInterceptor(db, engine)

    wrap_crewai_tool(
        read_file,
        tool_type=ToolType.FILESYSTEM,
        session_id=session.id,
        goal="fix login bug",
        interceptor=interceptor,
    )

    result = read_file.run("/project/login.tsx")
    assert "contents:/project/login.tsx" in result


def test_wrapped_tool_blocks_sensitive_path(db):
    """Wrapped CrewAI tool raises AgentWallSecurityException on sensitive target."""
    @tool("Read File")
    def read_file(path: str) -> str:
        """Read a file from the filesystem."""
        return "secret"

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    session = SessionManager(db).create("fix login bug")
    interceptor = ToolInterceptor(db, engine)

    wrap_crewai_tool(
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
    @tool("Search")
    def search(query: str) -> str:
        """Search for code."""
        return f"results:{query}"

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    session = SessionManager(db).create("fix login bug")
    interceptor = ToolInterceptor(db, engine)

    wrap_crewai_tool(
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
    """Every tool call records an Evaluation with decision and risk score."""
    @tool("Search")
    def search(query: str) -> str:
        """Search."""
        return "ok"

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    session = SessionManager(db).create("fix login bug")
    interceptor = ToolInterceptor(db, engine)

    wrap_crewai_tool(
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
    @tool("Read File")
    def read_file(path: str) -> str:
        """Read a file."""
        return "secret"

    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    session = SessionManager(db).create("fix login bug")
    interceptor = ToolInterceptor(db, engine)

    wrap_crewai_tool(
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
    """Wrapping does not change the tool's name."""
    @tool("My Custom Tool")
    def my_tool(x: str) -> str:
        """My custom tool."""
        return x

    engine = SecurityEngine(detectors=[])
    session = SessionManager(db).create("test")
    interceptor = ToolInterceptor(db, engine)

    wrap_crewai_tool(
        my_tool,
        tool_type=ToolType.API,
        session_id=session.id,
        goal="test",
        interceptor=interceptor,
    )

    assert my_tool.name == "My Custom Tool"


# ── protect_crewai_crew ────────────────────────────────────────────────────

def _make_crew(tools: list) -> Crew:
    agent = CrewAgent(
        role="Developer",
        goal="Fix bugs",
        backstory="Expert developer.",
        tools=tools,
    )
    task = Task(
        description="Fix the login bug",
        expected_output="Fixed code",
        agent=agent,
    )
    return Crew(agents=[agent], tasks=[task])


def test_protect_crew_wraps_all_agent_tools(db):
    """protect_crewai_crew wraps all tools on all crew agents."""
    @tool("Tool A")
    def tool_a(x: str) -> str:
        """Tool A."""
        return x

    @tool("Tool B")
    def tool_b(y: str) -> str:
        """Tool B."""
        return y

    original_a_func = tool_a.func
    original_b_func = tool_b.func

    crew = _make_crew([tool_a, tool_b])
    engine = SecurityEngine(detectors=[])
    wall = protect_crewai_crew(crew, goal="test", db=db, engine=engine)

    assert tool_a.func is not original_a_func
    assert tool_b.func is not original_b_func
    wall.end_session()


def test_protect_crew_session_created(db):
    """protect_crewai_crew creates a DB session."""
    crew = _make_crew([])
    engine = SecurityEngine(detectors=[])
    wall = protect_crewai_crew(crew, goal="fix auth bug", db=db, engine=engine)

    session = SessionManager(db).get(wall.session_id)
    assert session is not None
    assert session.user_goal == "fix auth bug"
    wall.end_session()


def test_protect_crew_tool_type_map(db):
    """tool_type_map assigns correct ToolType per tool name."""
    @tool("Read File")
    def read_file(path: str) -> str:
        """Read a file."""
        return "ok"

    crew = _make_crew([read_file])
    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    wall = protect_crewai_crew(
        crew,
        goal="test",
        tool_type_map={"Read File": ToolType.FILESYSTEM},
        db=db,
        engine=engine,
    )

    read_file.run("/project/login.tsx")

    events = EventManager(db).get_events(wall.session_id)
    assert events[0].tool_type == "filesystem"
    wall.end_session()


def test_protect_crew_blocks_sensitive_tool_call(db):
    """After protect_crew, sensitive tool calls raise AgentWallSecurityException."""
    @tool("Read File")
    def read_file(path: str) -> str:
        """Read a file."""
        return "secret"

    crew = _make_crew([read_file])
    engine = SecurityEngine(warn_threshold=30.0, block_threshold=70.0, detectors=[])
    wall = protect_crewai_crew(
        crew,
        goal="test",
        tool_type_map={"Read File": ToolType.FILESYSTEM},
        db=db,
        engine=engine,
    )

    with pytest.raises(AgentWallSecurityException):
        read_file.run("/home/user/.ssh/id_rsa")

    wall.end_session()


def test_protect_crew_end_session(db):
    """end_session() marks the DB session as ended."""
    crew = _make_crew([])
    engine = SecurityEngine(detectors=[])
    wall = protect_crewai_crew(crew, goal="test", db=db, engine=engine)
    wall.end_session()

    session = SessionManager(db).get(wall.session_id)
    assert session.ended_at is not None
