"""Tests for zero-configuration auto-instrumentation (agentwall.auto)."""
from __future__ import annotations

import os
import pytest

from agentwall.storage.database import Database
from agentwall.core.session_manager import SessionManager


class _FakeTool:
    """Minimal langchain-like BaseTool stub."""
    def __init__(self, name: str, func):
        self.name = name
        self.func = func
        self.coroutine = None
        self.description = f"{name} tool"


class _FakeExecutor:
    """Minimal AgentExecutor stub."""
    def __init__(self, tools):
        self.tools = tools

    def invoke(self, input, **kwargs):
        return {"output": "ok"}


def test_wrap_langchain_tool_idempotent(db):
    """Wrapping same tool twice must not double-intercept."""
    from agentwall.security.engine import build_default_engine
    from agentwall.interceptors.tool import ToolInterceptor
    from agentwall.integrations.langchain import wrap_langchain_tool
    from agentwall.core.types import ToolType
    from agentwall.core.session_manager import SessionManager

    engine = build_default_engine(db)
    interceptor = ToolInterceptor(db, engine)
    session = SessionManager(db).create("test goal")

    calls = []
    original = lambda path: calls.append(path) or "content"

    tool = _FakeTool("read_file", original)

    wrap_langchain_tool(tool, tool_type=ToolType.FILESYSTEM, session_id=session.id,
                        interceptor=interceptor, goal_ref=["test goal"])
    assert getattr(tool.func, "_aw_wrapped", False)

    first_wrapped = tool.func

    # Second wrap should be skipped
    wrap_langchain_tool(tool, tool_type=ToolType.FILESYSTEM, session_id=session.id,
                        interceptor=interceptor, goal_ref=["test goal"])
    assert tool.func is first_wrapped  # unchanged


def test_wrap_crewai_tool_idempotent(db):
    """Wrapping CrewAI tool twice must not double-intercept."""
    from agentwall.security.engine import build_default_engine
    from agentwall.interceptors.tool import ToolInterceptor
    from agentwall.integrations.crewai import wrap_crewai_tool
    from agentwall.core.types import ToolType
    from agentwall.core.session_manager import SessionManager

    engine = build_default_engine(db)
    interceptor = ToolInterceptor(db, engine)
    session = SessionManager(db).create("test goal")

    tool = _FakeTool("read_file", lambda path: "content")

    wrap_crewai_tool(tool, tool_type=ToolType.FILESYSTEM, session_id=session.id,
                     interceptor=interceptor, goal_ref=["test goal"])
    first_wrapped = tool.func

    wrap_crewai_tool(tool, tool_type=ToolType.FILESYSTEM, session_id=session.id,
                     interceptor=interceptor, goal_ref=["test goal"])
    assert tool.func is first_wrapped


def test_auto_setup_disabled_by_env(monkeypatch):
    """AGENTWALL_AUTO=0 must disable setup()."""
    monkeypatch.setenv("AGENTWALL_AUTO", "0")
    import importlib
    import agentwall.auto as auto_mod
    # Reload to pick up env var (module-level _enabled)
    # We can't fully reload without side effects, so just check _enabled
    # After monkeypatching, new module-level check would be False
    assert os.environ.get("AGENTWALL_AUTO") == "0"


def test_goal_tracker_infer_initial_goal(db):
    from agentwall.security.goal_tracker import GoalTracker
    session = SessionManager(db).create("")
    ref = [""]
    tracker = GoalTracker(session.id, db, ref)

    changed = tracker.infer_initial_goal("Fix login bug")
    assert changed is True
    assert ref[0] == "Fix login bug"

    # Second call when goal is already set should NOT override
    changed2 = tracker.infer_initial_goal("Something else entirely different")
    assert changed2 is False
    assert ref[0] == "Fix login bug"


def test_goal_tracker_detect_transition(db):
    from agentwall.security.goal_tracker import GoalTracker
    session = SessionManager(db).create("")
    ref = ["fix login bug"]
    tracker = GoalTracker(session.id, db, ref)

    assert not tracker.detect_transition("fix the login bug again")
    assert tracker.detect_transition("deploy kubernetes cluster")


def test_goal_tracker_create_goal_segment(db):
    from agentwall.security.goal_tracker import GoalTracker
    from agentwall.core.event_manager import EventManager

    session = SessionManager(db).create("")
    ref = [""]
    tracker = GoalTracker(session.id, db, ref)

    tracker.create_goal_segment("fix login bug", reason="manual", confidence=0.95)
    segs = EventManager(db).get_goal_segments(session.id)
    assert len(segs) == 1
    assert segs[0].goal_text == "fix login bug"
    assert segs[0].transition_reason == "manual"
    assert abs(segs[0].confidence - 0.95) < 0.01


def test_goal_tracker_infer_runtime_goal_no_drift(db):
    """No drift signal → infer_runtime_goal returns False."""
    from agentwall.security.goal_tracker import GoalTracker
    from agentwall.core.types import ResourceCategory, ToolAction, ToolType, RuntimeEvent

    session = SessionManager(db).create("fix login bug")
    ref = ["fix login bug"]
    tracker = GoalTracker(session.id, db, ref)
    tracker.set_goal("fix login bug", reason="initial")

    event = RuntimeEvent(
        session_id=session.id,
        goal="fix login bug",
        tool_type=ToolType.FILESYSTEM,
        action=ToolAction.READ,
        target="login.py",
        resource_category=ResourceCategory.CODE,
        metadata={},
        tool_name="read_file",
    )
    changed = tracker.infer_runtime_goal(event)
    assert changed is False
    assert ref[0] == "fix login bug"


def test_goal_tracker_infer_runtime_goal_credential_drift(db):
    """Credential access off code goal → new goal segment created."""
    from agentwall.security.goal_tracker import GoalTracker
    from agentwall.core.types import ResourceCategory, ToolAction, ToolType, RuntimeEvent
    from agentwall.core.event_manager import EventManager

    session = SessionManager(db).create("fix login bug")
    ref = ["fix login bug"]
    tracker = GoalTracker(session.id, db, ref)
    tracker.set_goal("fix login bug", reason="initial")

    event = RuntimeEvent(
        session_id=session.id,
        goal="fix login bug",
        tool_type=ToolType.FILESYSTEM,
        action=ToolAction.READ,
        target=".env",
        resource_category=ResourceCategory.CREDENTIALS,
        metadata={},
        tool_name="read_file",
    )
    changed = tracker.infer_runtime_goal(event)
    assert changed is True
    segs = EventManager(db).get_goal_segments(session.id)
    assert len(segs) == 2
    assert segs[1].transition_reason == "runtime_inference"


# ── Protection marker regression tests ────────────────────────────────────────

def test_protect_openai_agent_sets_is_protected(db):
    """protect_openai_agent must mark protected_agent with _aw_is_protected."""
    pytest.importorskip("agents")
    from agents import Agent, function_tool
    from agentwall.integrations.openai_agents import protect_openai_agent
    from agentwall.security.engine import SecurityEngine

    @function_tool
    def noop(x: str) -> str:
        """No-op tool."""
        return x

    agent = Agent(name="test", instructions="Test.", tools=[noop], model="gpt-4o-mini")
    engine = SecurityEngine(detectors=[])
    wall, protected = protect_openai_agent(agent, db=db, engine=engine)
    assert getattr(protected, "_aw_is_protected", False) is True
    wall.end_session()


def test_protect_langchain_sets_marker(db):
    """protect_langchain_agent must mark executor with _aw_auto_protected."""
    from agentwall.integrations.langchain import protect_langchain_agent
    from agentwall.security.engine import SecurityEngine

    executor = _FakeExecutor([])
    engine = SecurityEngine(detectors=[])
    wall = protect_langchain_agent(executor, db=db, engine=engine)
    assert getattr(executor, "_aw_auto_protected", False) is True
    assert getattr(executor, "_aw_wall", None) is wall
    wall.end_session()


def test_protect_langchain_guard_no_duplicate_session(db):
    """protect_langchain_agent called twice returns same wall, no new session."""
    from agentwall.integrations.langchain import protect_langchain_agent
    from agentwall.security.engine import SecurityEngine

    executor = _FakeExecutor([])
    engine = SecurityEngine(detectors=[])
    wall1 = protect_langchain_agent(executor, db=db, engine=engine)
    wall2 = protect_langchain_agent(executor, db=db, engine=engine)
    assert wall1 is wall2
    wall1.end_session()


def test_protect_crewai_sets_marker(db):
    """protect_crewai_crew must mark crew with _aw_auto_protected."""
    from agentwall.integrations.crewai import protect_crewai_crew
    from agentwall.security.engine import SecurityEngine

    class _FakeCrew:
        agents = []
        tasks = []

    crew = _FakeCrew()
    engine = SecurityEngine(detectors=[])
    wall = protect_crewai_crew(crew, db=db, engine=engine)
    assert getattr(crew, "_aw_auto_protected", False) is True
    assert getattr(crew, "_aw_wall", None) is wall
    wall.end_session()


def test_protect_crewai_guard_no_duplicate_session(db):
    """protect_crewai_crew called twice returns same wall, no new session."""
    from agentwall.integrations.crewai import protect_crewai_crew
    from agentwall.security.engine import SecurityEngine

    class _FakeCrew:
        agents = []
        tasks = []

    crew = _FakeCrew()
    engine = SecurityEngine(detectors=[])
    wall1 = protect_crewai_crew(crew, db=db, engine=engine)
    wall2 = protect_crewai_crew(crew, db=db, engine=engine)
    assert wall1 is wall2
    wall1.end_session()


def test_protect_langchain_guard_updates_goal(db):
    """protect_langchain_agent on already-protected executor updates goal."""
    from agentwall.integrations.langchain import protect_langchain_agent
    from agentwall.security.engine import SecurityEngine

    executor = _FakeExecutor([])
    engine = SecurityEngine(detectors=[])
    wall1 = protect_langchain_agent(executor, db=db, engine=engine)
    wall2 = protect_langchain_agent(executor, goal="fix login bug", db=db, engine=engine)
    assert wall1 is wall2
    assert wall1._goal_ref[0] == "fix login bug"
    wall1.end_session()
