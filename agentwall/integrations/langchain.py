from __future__ import annotations

"""AgentWall integration for LangChain.

Usage (callback-based monitoring)::

    from langchain.agents import AgentExecutor, create_openai_tools_agent
    from langchain_core.tools import tool
    from agentwall.integrations.langchain import protect_langchain_agent
    from agentwall.core.types import ToolType

    @tool
    def read_file(path: str) -> str:
        \"\"\"Read a file from the filesystem.\"\"\"
        with open(path) as f:
            return f.read()

    agent = create_openai_tools_agent(llm, [read_file], prompt)
    executor = AgentExecutor(agent=agent, tools=[read_file])

    wall = protect_langchain_agent(
        executor,
        goal="Fix login bug",
        tool_type_map={"read_file": ToolType.FILESYSTEM},
    )
    result = executor.invoke({"input": "read login.tsx"})
    wall.end_session()
"""

import time
from typing import Any

try:
    from langchain_core.tools import BaseTool
except ImportError as e:
    raise ImportError(
        "langchain-core is required for this integration. "
        "Install with: pip install langchain langchain-openai"
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

def wrap_langchain_tool(
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
    """Patch *tool.func* (sync) or *tool.coroutine* (async) with AgentWall interception.

    LangChain's _run() calls self.func; _arun() calls self.coroutine when set.
    Patching both surfaces ensures ainvoke() paths are intercepted too.
    """
    resolved_action = action or _default_action(tool_type)
    _ref = goal_ref if goal_ref is not None else [goal or ""]

    def _make_event(*args: Any, **kwargs: Any) -> RuntimeEvent:
        return RuntimeEvent(
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

    if tool.coroutine is not None:
        original_coro = tool.coroutine

        async def _wrapped_async(*args: Any, **kwargs: Any) -> Any:
            event = _make_event(*args, **kwargs)
            interceptor.before_execute(event)
            result = await original_coro(*args, **kwargs)
            interceptor.after_execute(event, result)
            return result

        tool.coroutine = _wrapped_async
    else:
        original_func = tool.func

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            event = _make_event(*args, **kwargs)
            interceptor.before_execute(event)
            result = original_func(*args, **kwargs)
            interceptor.after_execute(event, result)
            return result

        tool.func = _wrapped

    return tool


def protect_langchain_agent(
    executor: Any,
    *,
    goal: str | None = None,
    tool_type_map: dict[str, ToolType] | None = None,
    action_map: dict[str, ToolAction] | None = None,
    resource_category_map: dict[str, ResourceCategory] | None = None,
    db: Database | None = None,
    engine: SecurityEngine | None = None,
) -> Any:
    """Wrap all tools in *executor.tools* with AgentWall interception in-place.

    Returns the ProtectedAgent (wall) for session lifecycle management.
    The executor's tools are modified in-place; invoke executor normally.
    """
    from agentwall.interceptors.agent import ProtectedAgent
    from agentwall.security.engine import build_default_engine

    _db = db or Database()
    _engine = engine or build_default_engine(_db)

    class _Stub:
        def run(self, *a: Any, **kw: Any) -> Any:
            raise RuntimeError("Use AgentExecutor.invoke() instead.")

    wall = ProtectedAgent(_Stub(), goal=goal, db=_db, engine=_engine)
    tool_map = tool_type_map or {}
    act_map = action_map or {}
    cat_map = resource_category_map or {}

    for tool in getattr(executor, "tools", []):
        if isinstance(tool, BaseTool):
            tt = tool_map.get(tool.name, ToolType.API)
            wrap_langchain_tool(
                tool,
                tool_type=tt,
                session_id=wall.session_id,
                goal_ref=wall._goal_ref,
                interceptor=wall._interceptor,
                action=act_map.get(tool.name),
                resource_category=cat_map.get(tool.name, ResourceCategory.UNKNOWN),
            )

    if goal is None:
        _original_invoke = getattr(executor, "invoke", None)
        if _original_invoke is not None:
            def _patched_invoke(input, **kwargs):
                if isinstance(input, dict):
                    inferred = (
                        input.get("input")
                        or input.get("query")
                        or input.get("task")
                        or next(iter(input.values()), None)
                    )
                else:
                    inferred = str(input)
                if inferred:
                    wall.maybe_infer_goal(str(inferred))
                return _original_invoke(input, **kwargs)
            executor.invoke = _patched_invoke

    return wall
