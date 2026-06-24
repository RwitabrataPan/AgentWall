"""
AgentWall + CrewAI example.

Requires: OPENAI_API_KEY environment variable.
Install:   pip install agentwall crewai

Run:       python examples/crewai/example.py
"""
from __future__ import annotations

import os

from crewai import Agent as CrewAgent, Task, Crew
from crewai.tools import tool

from agentwall.core.types import ToolType
from agentwall.integrations.crewai import protect_crewai_crew
from agentwall.security.exceptions import AgentWallSecurityException


@tool("Read File")
def read_file(path: str) -> str:
    """Read a source file from the filesystem."""
    with open(path) as f:
        return f.read()


@tool("List Directory")
def list_directory(directory: str) -> str:
    """List files in a directory."""
    import os as _os
    return "\n".join(_os.listdir(directory))


def main() -> None:
    developer = CrewAgent(
        role="Senior Developer",
        goal="Fix authentication bugs in the codebase",
        backstory="Expert Python and TypeScript developer.",
        tools=[read_file, list_directory],
        verbose=True,
    )

    task = Task(
        description=(
            "Read the login.tsx file and identify the authentication bug. "
            "Provide the line number and a fix."
        ),
        expected_output="Bug location and fix description.",
        agent=developer,
    )

    crew = Crew(agents=[developer], tasks=[task], verbose=True)

    wall = protect_crewai_crew(
        crew,
        goal="Fix authentication bug in login.tsx",
        tool_type_map={
            "Read File": ToolType.FILESYSTEM,
            "List Directory": ToolType.FILESYSTEM,
        },
    )

    print(f"Session: {wall.session_id}")

    try:
        result = crew.kickoff()
        print("Crew output:", result)
    except AgentWallSecurityException as e:
        print(f"Blocked by AgentWall: {e}")
    finally:
        wall.end_session()
        print(f"Session {wall.session_id} closed.")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY to run this example.")
    else:
        main()
