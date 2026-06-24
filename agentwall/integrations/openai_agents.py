from __future__ import annotations

"""AgentWall integration for the OpenAI Agents SDK.

Usage::

    from agents import Agent, Runner, function_tool
    from agentwall.integrations.openai_agents import protect_openai_agent
    from agentwall.core.types import ToolType

    @function_tool
    def read_file(path: str) -> str:
        with open(path) as f:
            return f.read()

    agent = Agent(name="coder", instructions="Fix bugs.", tools=[read_file])
    wall, protected = protect_openai_agent(
        agent,
        goal="Fix login bug",
        tool_type_map={"read_file": ToolType.FILESYSTEM},
    )
    result = await Runner.run(protected, "read login.tsx")
    wall.end_session()
"""

import dataclasses
import json
import time
from typing import Any

try:
    from agents import Agent, FunctionTool
    from agents.tool_context import ToolContext
    from agents.guardrail import GuardrailFunctionOutput, InputGuardrail
except ImportError as e:
    raise ImportError(
        "openai-agents is required for this integration. "
        "Install with: pip install openai-agents"
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


def _extract_goal_text(input: Any) -> str:
    """Extract a plain string from str or list[TResponseInputItem] runner input."""
    if isinstance(input, str):
        return input
    if isinstance(input, list):
        for item in input:
            if isinstance(item, dict):
                content = item.get("content", "")
                if isinstance(content, str) and content:
                    return content
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "input_text":
                            text = block.get("text", "")
                            if text:
                                return text
    return str(input)[:200] if input else ""


def _make_goal_inferrer(wall: Any) -> InputGuardrail:
    """Return a no-op InputGuardrail that captures the run input as the session goal."""
    async def _infer(ctx: Any, agent: Any, input: Any) -> GuardrailFunctionOutput:
        text = _extract_goal_text(input)
        if text:
            wall.maybe_infer_goal(text)
        return GuardrailFunctionOutput(output_info=None, tripwire_triggered=False)

    return InputGuardrail(guardrail_function=_infer, name="agentwall_goal_inferrer")


def wrap_openai_function_tool(
    ft: FunctionTool,
    *,
    tool_type: ToolType,
    session_id: str,
    goal: str | None = None,
    goal_ref: list[str] | None = None,
    interceptor: ToolInterceptor,
    action: ToolAction | None = None,
    resource_category: ResourceCategory = ResourceCategory.UNKNOWN,
) -> FunctionTool:
    """Return a new FunctionTool whose on_invoke_tool is wrapped by AgentWall."""
    original = ft.on_invoke_tool
    resolved_action = action or _default_action(tool_type)
    _ref = goal_ref if goal_ref is not None else [goal or ""]

    async def _wrapped(ctx: ToolContext, args_json: str) -> Any:
        try:
            args_dict = json.loads(args_json)
        except (json.JSONDecodeError, TypeError, ValueError):
            args_dict = {}

        event = RuntimeEvent(
            session_id=session_id,
            goal=_ref[0],
            tool_type=tool_type,
            action=resolved_action,
            target=_extract_target((), args_dict),
            resource_category=resource_category,
            metadata=args_dict,
            tool_name=ft.name,
            timestamp=time.time(),
        )

        interceptor.before_execute(event)  # raises AgentWallSecurityException on BLOCK
        result = await original(ctx, args_json)
        interceptor.after_execute(event, result)
        return result

    return dataclasses.replace(ft, on_invoke_tool=_wrapped)


def protect_openai_agent(
    agent: Agent,
    *,
    goal: str | None = None,
    tool_type_map: dict[str, ToolType] | None = None,
    action_map: dict[str, ToolAction] | None = None,
    resource_category_map: dict[str, ResourceCategory] | None = None,
    db: Database | None = None,
    engine: SecurityEngine | None = None,
) -> tuple[Any, Agent]:
    """Wrap all FunctionTools on *agent* with AgentWall interception.

    Returns:
        (wall, protected_agent) where *wall* is a ProtectedAgent for session
        lifecycle management and *protected_agent* is a cloned Agent with
        AgentWall-wrapped tools. Pass *protected_agent* to Runner.run().
    """
    from agentwall.interceptors.agent import ProtectedAgent
    from agentwall.security.engine import build_default_engine

    _db = db or Database()
    _engine = engine or build_default_engine(_db)

    class _Stub:
        def run(self, *a: Any, **kw: Any) -> Any:
            raise RuntimeError("Use Runner.run(protected_agent, ...) instead.")

    wall = ProtectedAgent(_Stub(), goal=goal, db=_db, engine=_engine)
    tool_map = tool_type_map or {}
    act_map = action_map or {}
    cat_map = resource_category_map or {}

    wrapped_tools = []
    for tool in agent.tools or []:
        if isinstance(tool, FunctionTool):
            tt = tool_map.get(tool.name, ToolType.API)
            wrapped_tools.append(
                wrap_openai_function_tool(
                    tool,
                    tool_type=tt,
                    session_id=wall.session_id,
                    goal_ref=wall._goal_ref,
                    interceptor=wall._interceptor,
                    action=act_map.get(tool.name),
                    resource_category=cat_map.get(tool.name, ResourceCategory.UNKNOWN),
                )
            )
        else:
            wrapped_tools.append(tool)

    protected_agent = dataclasses.replace(agent, tools=wrapped_tools)

    # When goal not provided, inject a guardrail to infer it from the first Runner.run() input.
    # InputGuardrail fires before the first LLM call, receiving the raw user input string.
    if goal is None:
        inferrer = _make_goal_inferrer(wall)
        protected_agent = dataclasses.replace(
            protected_agent,
            input_guardrails=[*protected_agent.input_guardrails, inferrer],
        )

    return wall, protected_agent
