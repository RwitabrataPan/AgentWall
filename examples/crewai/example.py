"""
AgentWall + CrewAI example.

Requires: OPENAI_API_KEY environment variable.
Install:   pip install agentwall-security[crewai]

Run:       python examples/crewai/example.py

Zero-config mode (v0.2.0+):
    import agentwall  # auto-instruments Crew on import
    crew.kickoff()    # done — no protect_* needed

Advanced usage: use protect_crewai_crew() for explicit control.
"""
from __future__ import annotations

import os

from crewai import Agent as CrewAgent, Task, Crew
from crewai.tools import tool

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


def _make_crew() -> Crew:
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
    return Crew(agents=[developer], tasks=[task], verbose=True)


def zero_config_example() -> None:
    """Zero-config: just import agentwall. No protect_* needed."""
    import agentwall  # noqa: F401 — triggers auto-instrumentation

    crew = _make_crew()

    # AgentWall auto-protects this crew. Goal inferred from first task description.
    try:
        result = crew.kickoff()
        print("Crew output:", result)
    except AgentWallSecurityException as e:
        print(f"Blocked by AgentWall: {e}")


def explicit_example() -> None:
    """Advanced: explicit protect_crewai_crew for full control."""
    from agentwall.core.types import ToolType
    from agentwall.integrations.crewai import protect_crewai_crew

    crew = _make_crew()

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
        # Zero-config is the recommended path
        zero_config_example()
