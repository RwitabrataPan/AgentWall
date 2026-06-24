from __future__ import annotations

"""AgentWall integration for CrewAI.

Usage::

    from crewai import Agent as CrewAgent, Task, Crew
    from crewai.tools import tool
    from agentwall.integrations.crewai import protect_crewai_crew
    from agentwall.core.types import ToolType

    @tool("Read File")
    def read_file(path: str) -> str:
        \"\"\"Read a file from the filesystem.\"\"\"
        with open(path) as f:
            return f.read()

    dev = CrewAgent(role="Developer", goal="Fix bugs", tools=[read_file])
    task = Task(description="Fix the login bug", expected_output="Fixed code", agent=dev)
    crew = Crew(agents=[dev], tasks=[task])

    wall = protect_crewai_crew(
        crew,
        goal="Fix login bug",
        tool_type_map={"Read File": ToolType.FILESYSTEM},
    )
    result = crew.kickoff()
    wall.end_session()
"""

import time
from typing import Any

try:
    from crewai.tools import BaseTool
    from crewai import Crew
except ImportError as e:
    raise ImportError(
        "crewai is required for this integration. "
        "Install with: pip install crewai"
    ) from e

from agentwall.core.types import (
    ResourceCategory,
    RuntimeEvent,
    ToolAction,
    ToolType,
)
from agentwall.interceptors.tool import ToolInterceptor, _default_action, _extract_target
from agentwall.security.engine import SecurityEngine
from agentwall.storage.database import Database


def wrap_crewai_tool(
    tool: BaseTool,
    *,
    tool_type: ToolType,
    session_id: str,
    goal: str | None = None,
    goal_ref: list[str] | None = None,
    interceptor: ToolInterceptor,
    action: ToolAction | None = None,
    resource_category: ResourceCategory = ResourceCategory.UNKNOWN,
) -> BaseTool:
    """Patch *tool.func* with AgentWall interception in-place.

    CrewAI's concrete Tool.run() calls self.func() directly, bypassing _run.
    Patching func intercepts at the correct level while preserving the tool's
    name, description, and args_schema unchanged.
    """
    original_func = tool.func  # the raw Python callable
    resolved_action = action or _default_action(tool_type)
    _ref = goal_ref if goal_ref is not None else [goal or ""]

    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        event = RuntimeEvent(
            session_id=session_id,
            goal=_ref[0],
            tool_type=tool_type,
            action=resolved_action,
            target=_extract_target(args, kwargs),
            resource_category=resource_category,
            metadata={
                "args": [str(a) for a in args],
                "kwargs": {k: str(v) for k, v in kwargs.items()},
            },
            tool_name=tool.name,
            timestamp=time.time(),
        )
        interceptor.before_execute(event)  # raises AgentWallSecurityException on BLOCK
        result = original_func(*args, **kwargs)
        interceptor.after_execute(event, result)
        return result

    tool.func = _wrapped
    return tool


def protect_crewai_crew(
    crew: Crew,
    *,
    goal: str | None = None,
    tool_type_map: dict[str, ToolType] | None = None,
    action_map: dict[str, ToolAction] | None = None,
    resource_category_map: dict[str, ResourceCategory] | None = None,
    db: Database | None = None,
    engine: SecurityEngine | None = None,
) -> Any:
    """Wrap all tools on all agents in *crew* with AgentWall interception.

    Tools are modified in-place. Returns ProtectedAgent for session management.
    Kick off the crew normally after calling this.
    """
    from agentwall.interceptors.agent import ProtectedAgent
    from agentwall.security.engine import build_default_engine

    _db = db or Database()
    _engine = engine or build_default_engine(_db)

    class _Stub:
        def run(self, *a: Any, **kw: Any) -> Any:
            raise RuntimeError("Use crew.kickoff() instead.")

    wall = ProtectedAgent(_Stub(), goal=goal, db=_db, engine=_engine)
    tool_map = tool_type_map or {}
    act_map = action_map or {}
    cat_map = resource_category_map or {}

    for agent in getattr(crew, "agents", []):
        for tool in getattr(agent, "tools", []) or []:
            if isinstance(tool, BaseTool):
                tt = tool_map.get(tool.name, ToolType.API)
                wrap_crewai_tool(
                    tool,
                    tool_type=tt,
                    session_id=wall.session_id,
                    goal_ref=wall._goal_ref,
                    interceptor=wall._interceptor,
                    action=act_map.get(tool.name),
                    resource_category=cat_map.get(tool.name, ResourceCategory.UNKNOWN),
                )

    if goal is None:
        _original_kickoff = getattr(crew, "kickoff", None)
        if _original_kickoff is not None:
            def _patched_kickoff(inputs=None, **kwargs):
                inferred = ""
                if inputs and isinstance(inputs, dict):
                    inferred = str(next(iter(inputs.values()), ""))
                elif inputs:
                    inferred = str(inputs)
                if not inferred:
                    tasks = getattr(crew, "tasks", [])
                    if tasks:
                        inferred = getattr(tasks[0], "description", "")
                if inferred:
                    wall.maybe_infer_goal(inferred)
                return _original_kickoff(inputs=inputs, **kwargs)
            crew.kickoff = _patched_kickoff

    return wall
