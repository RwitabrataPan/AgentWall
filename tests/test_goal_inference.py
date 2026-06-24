from __future__ import annotations

import pytest
from agentwall.core.session_manager import SessionManager
from agentwall.interceptors.agent import ProtectedAgent
from agentwall.security.engine import SecurityEngine


class _Stub:
    def run(self, *a, **kw):
        return None


def _engine():
    return SecurityEngine(detectors=[])


# ── SessionManager.update_goal ─────────────────────────────────────────────

def test_session_manager_update_goal(db):
    mgr = SessionManager(db)
    session = mgr.create("original goal")
    mgr.update_goal(session.id, "updated goal")
    refreshed = mgr.get(session.id)
    assert refreshed.user_goal == "updated goal"


def test_session_manager_update_goal_nonexistent_id_is_noop(db):
    mgr = SessionManager(db)
    # should not raise
    mgr.update_goal("nonexistent-id-abc", "anything")


# ── ProtectedAgent optional goal ───────────────────────────────────────────

def test_protected_agent_no_goal_creates_session_with_empty_goal(db):
    wall = ProtectedAgent(_Stub(), db=db, engine=_engine())
    session = SessionManager(db).get(wall.session_id)
    assert session is not None
    assert session.user_goal == ""
    wall.end_session()


def test_protected_agent_explicit_goal_still_works(db):
    wall = ProtectedAgent(_Stub(), goal="fix login bug", db=db, engine=_engine())
    assert wall.goal == "fix login bug"
    session = SessionManager(db).get(wall.session_id)
    assert session.user_goal == "fix login bug"
    wall.end_session()


def test_protected_agent_set_goal_updates_property_and_db(db):
    wall = ProtectedAgent(_Stub(), db=db, engine=_engine())
    assert wall.goal == ""

    wall.set_goal("fix authentication bug")

    assert wall.goal == "fix authentication bug"
    session = SessionManager(db).get(wall.session_id)
    assert session.user_goal == "fix authentication bug"
    wall.end_session()


def test_protected_agent_set_goal_overwrites_explicit_goal(db):
    wall = ProtectedAgent(_Stub(), goal="original", db=db, engine=_engine())
    wall.set_goal("overridden goal")
    assert wall.goal == "overridden goal"
    wall.end_session()


def test_protected_agent_goal_ref_is_shared_mutable_list(db):
    wall = ProtectedAgent(_Stub(), goal="initial", db=db, engine=_engine())
    ref = wall._goal_ref
    wall.set_goal("updated")
    # same list object, updated in-place
    assert ref[0] == "updated"
    wall.end_session()


# ── LangChain goal inference ───────────────────────────────────────────────

def test_langchain_goal_inferred_from_invoke_input_key(db):
    """protect_langchain_agent with no goal infers from executor.invoke({'input': ...})."""
    from agentwall.integrations.langchain import protect_langchain_agent

    try:
        from langchain_core.tools import tool as lc_tool
    except ImportError:
        pytest.skip("langchain-core not installed")

    @lc_tool
    def safe_tool(path: str) -> str:
        """Read a file."""
        return f"content:{path}"

    class _FakeExecutor:
        tools = [safe_tool]
        def invoke(self, input, **kwargs):
            return {"output": "done"}

    executor = _FakeExecutor()
    wall = protect_langchain_agent(executor, db=db, engine=_engine())
    assert wall.goal == ""

    executor.invoke({"input": "fix the login page bug"})

    assert wall.goal == "fix the login page bug"
    session = SessionManager(db).get(wall.session_id)
    assert session.user_goal == "fix the login page bug"
    wall.end_session()


def test_langchain_explicit_goal_not_overridden_by_invoke(db):
    """When goal is provided explicitly, invoke does not overwrite it."""
    from agentwall.integrations.langchain import protect_langchain_agent

    try:
        from langchain_core.tools import tool as lc_tool
    except ImportError:
        pytest.skip("langchain-core not installed")

    @lc_tool
    def safe_tool(path: str) -> str:
        """Read."""
        return "ok"

    class _FakeExecutor:
        tools = [safe_tool]
        def invoke(self, input, **kwargs):
            return {"output": "done"}

    executor = _FakeExecutor()
    wall = protect_langchain_agent(executor, goal="explicit goal", db=db, engine=_engine())
    executor.invoke({"input": "different input"})
    assert wall.goal == "explicit goal"
    wall.end_session()


# ── CrewAI goal inference ──────────────────────────────────────────────────

def test_crewai_goal_inferred_from_kickoff_inputs(db):
    """protect_crewai_crew with no goal infers from crew.kickoff(inputs={...})."""
    from agentwall.integrations.crewai import protect_crewai_crew

    try:
        from crewai import Crew  # noqa: F401
    except ImportError:
        pytest.skip("crewai not installed")

    class _FakeCrew:
        agents = []
        tasks = []
        def kickoff(self, inputs=None, **kwargs):
            return "done"

    crew = _FakeCrew()
    wall = protect_crewai_crew(crew, db=db, engine=_engine())
    assert wall.goal == ""

    crew.kickoff(inputs={"task": "Refactor the auth module"})

    assert wall.goal == "Refactor the auth module"
    wall.end_session()


def test_crewai_goal_inferred_from_task_descriptions(db):
    """When no kickoff inputs, goal is inferred from first task's description."""
    from agentwall.integrations.crewai import protect_crewai_crew

    try:
        from crewai import Crew  # noqa: F401
    except ImportError:
        pytest.skip("crewai not installed")

    class _FakeTask:
        description = "Fix authentication bug in login.tsx"

    class _FakeCrew:
        agents = []
        tasks = [_FakeTask()]
        def kickoff(self, inputs=None, **kwargs):
            return "done"

    crew = _FakeCrew()
    wall = protect_crewai_crew(crew, db=db, engine=_engine())
    crew.kickoff()

    assert wall.goal == "Fix authentication bug in login.tsx"
    wall.end_session()


# ── OpenAI goal inference via InputGuardrail ───────────────────────────────

@pytest.mark.asyncio
async def test_openai_goal_inferred_from_runner_input(db):
    """Goal is set automatically when Runner.run fires the input guardrail."""
    try:
        from agents import Agent
    except ImportError:
        pytest.skip("openai-agents not installed")

    from agentwall.integrations.openai_agents import protect_openai_agent
    from unittest.mock import MagicMock

    agent = Agent(name="test", instructions="test", tools=[])
    engine = _engine()
    wall, protected = protect_openai_agent(agent, db=db, engine=engine)

    assert wall.goal == ""
    assert len(protected.input_guardrails) == 1
    assert protected.input_guardrails[0].name == "agentwall_goal_inferrer"

    fake_ctx = MagicMock()
    result = await protected.input_guardrails[0].guardrail_function(
        fake_ctx, protected, "fix authentication bug"
    )

    assert result.tripwire_triggered is False
    assert wall.goal == "fix authentication bug"
    session = SessionManager(db).get(wall.session_id)
    assert session.user_goal == "fix authentication bug"
    wall.end_session()


@pytest.mark.asyncio
async def test_openai_goal_inferred_from_list_input(db):
    """Goal extracted from first user message when input is a list of items."""
    try:
        from agents import Agent
    except ImportError:
        pytest.skip("openai-agents not installed")

    from agentwall.integrations.openai_agents import protect_openai_agent
    from unittest.mock import MagicMock

    agent = Agent(name="test", instructions="test", tools=[])
    wall, protected = protect_openai_agent(agent, db=db, engine=_engine())

    list_input = [{"role": "user", "content": "fix login bug"}]
    fake_ctx = MagicMock()
    await protected.input_guardrails[0].guardrail_function(fake_ctx, protected, list_input)

    assert wall.goal == "fix login bug"
    wall.end_session()


@pytest.mark.asyncio
async def test_openai_explicit_goal_no_guardrail_injected(db):
    """When goal is explicit, no goal-inferrer guardrail is added."""
    try:
        from agents import Agent
    except ImportError:
        pytest.skip("openai-agents not installed")

    from agentwall.integrations.openai_agents import protect_openai_agent

    agent = Agent(name="test", instructions="test", tools=[])
    wall, protected = protect_openai_agent(agent, goal="explicit goal", db=db, engine=_engine())

    assert wall.goal == "explicit goal"
    aw_guardrails = [
        g for g in protected.input_guardrails
        if getattr(g, "name", "") == "agentwall_goal_inferrer"
    ]
    assert len(aw_guardrails) == 0
    wall.end_session()
