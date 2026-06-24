"""
AgentWall + OpenAI Agents SDK example.

Requires: OPENAI_API_KEY environment variable.
Install:   pip install agentwall openai-agents

Run:       python examples/openai_agents/example.py
"""
from __future__ import annotations

import asyncio
import os

from agents import Agent, Runner, function_tool

from agentwall.core.types import ToolType
from agentwall.integrations.openai_agents import protect_openai_agent
from agentwall.security.exceptions import AgentWallSecurityException


@function_tool
def read_file(path: str) -> str:
    """Read a source file from the filesystem."""
    with open(path) as f:
        return f.read()


@function_tool
def list_directory(directory: str) -> str:
    """List files in a directory."""
    import os as _os
    entries = _os.listdir(directory)
    return "\n".join(entries)


agent = Agent(
    name="code-assistant",
    instructions=(
        "You are a helpful coding assistant. "
        "You help developers fix bugs by reading their source code."
    ),
    tools=[read_file, list_directory],
    model="gpt-4o-mini",
)


async def main() -> None:
    wall, protected_agent = protect_openai_agent(
        agent,
        goal="Fix the authentication bug in login.tsx",
        tool_type_map={
            "read_file": ToolType.FILESYSTEM,
            "list_directory": ToolType.FILESYSTEM,
        },
    )

    print(f"Session: {wall.session_id}")

    try:
        result = await Runner.run(
            protected_agent,
            "List the files in the current directory, then read login.tsx",
        )
        print("Agent output:", result.final_output)
    except AgentWallSecurityException as e:
        print(f"Blocked by AgentWall: {e}")
    finally:
        wall.end_session()
        print(f"Session {wall.session_id} closed.")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY to run this example.")
    else:
        asyncio.run(main())
