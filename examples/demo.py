"""
AgentWall minimal demo — no API key required.

Demonstrates the full execution lifecycle:
  protect_agent() → tool calls → end_session()

Each run creates exactly one Execution in the database.
Run multiple times to build up history in the Inspector.

Usage:
    python examples/demo.py
    python examples/demo.py  # run again — Inspector shows cumulative history
"""
from __future__ import annotations

import time

from agentwall.interceptors import protect_agent
from agentwall.core.types import ToolType


def read_file(path: str) -> str:
    """Simulate reading a source file."""
    return f"# contents of {path}\n\ndef login(user, password):\n    pass\n"


def write_file(path: str, content: str) -> str:
    """Simulate writing a file."""
    return f"wrote {len(content)} bytes to {path}"


def main() -> None:
    print("AgentWall demo — starting protected agent run")

    class _Agent:
        def run(self, task: str) -> str:
            return f"completed: {task}"

    with protect_agent(_Agent(), goal="Fix authentication bug in login.py") as agent:
        print(f"  execution_id : {agent.execution_id}")
        print(f"  session_id   : {agent.session_id}")

        # Wrap tools with AgentWall interception
        safe_read = agent.protect_tool(read_file, tool_type=ToolType.FILESYSTEM)
        safe_write = agent.protect_tool(write_file, tool_type=ToolType.FILESYSTEM)

        # Simulate agent tool calls
        source = safe_read("src/auth/login.py")
        print(f"  read login.py ({len(source)} bytes)")

        fixed = source.replace("pass", 'return user == "admin" and password == "secret"')
        safe_write("src/auth/login.py", fixed)
        print("  wrote fix")

        time.sleep(0.1)  # simulate processing time

    # context manager calls end_session() → finish() → status="completed"
    print(f"  status       : completed")
    print("Demo run complete. Open `agentwall inspect` to view execution history.")


if __name__ == "__main__":
    main()
