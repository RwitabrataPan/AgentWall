"""
AgentWall + LangChain example.

Requires: OPENAI_API_KEY environment variable.
Install:   pip install agentwall-security[langchain]

Run:       python examples/langchain/example.py

Zero-config mode (v0.2.0+):
    import agentwall  # auto-instruments AgentExecutor on import
    executor.invoke({"input": "..."})  # done — no protect_* needed

Advanced usage: use protect_langchain_agent() for explicit control.
"""
from __future__ import annotations

import os

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain import hub
from langchain.agents import AgentExecutor, create_openai_tools_agent

from agentwall.security.exceptions import AgentWallSecurityException


@tool
def read_file(path: str) -> str:
    """Read a source file from the filesystem."""
    with open(path) as f:
        return f.read()


@tool
def list_directory(directory: str) -> str:
    """List files in a directory."""
    import os as _os
    return "\n".join(_os.listdir(directory))


def zero_config_example() -> None:
    """Zero-config: just import agentwall. No protect_* needed."""
    import agentwall  # noqa: F401 — triggers auto-instrumentation

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    tools = [read_file, list_directory]
    prompt = hub.pull("hwchase17/openai-tools-agent")

    agent = create_openai_tools_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

    # AgentWall auto-protects this executor. Goal inferred from input.
    try:
        result = executor.invoke({"input": "Fix the authentication bug in login.tsx"})
        print("Agent output:", result["output"])
    except AgentWallSecurityException as e:
        print(f"Blocked by AgentWall: {e}")


def explicit_example() -> None:
    """Advanced: explicit protect_langchain_agent for full control."""
    from agentwall.core.types import ToolType
    from agentwall.integrations.langchain import protect_langchain_agent

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    tools = [read_file, list_directory]
    prompt = hub.pull("hwchase17/openai-tools-agent")

    agent = create_openai_tools_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

    wall = protect_langchain_agent(
        executor,
        goal="Fix the authentication bug in login.tsx",
        tool_type_map={
            "read_file": ToolType.FILESYSTEM,
            "list_directory": ToolType.FILESYSTEM,
        },
    )

    print(f"Session: {wall.session_id}")

    try:
        result = executor.invoke({"input": "Read login.tsx and find the bug."})
        print("Agent output:", result["output"])
    except AgentWallSecurityException as e:
        print(f"Blocked by AgentWall: {e}")
    finally:
        wall.end_session()
        print(f"Session {wall.session_id} closed.")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY to run this example.")
    else:
        # Zero-config is the recommended path
        zero_config_example()
