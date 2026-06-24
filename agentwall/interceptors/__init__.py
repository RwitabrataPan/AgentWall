from agentwall.interceptors.agent import ProtectedAgent
from agentwall.interceptors.base import BaseInterceptor
from agentwall.interceptors.tool import ToolInterceptor, protect_tool
from agentwall.security.engine import SecurityEngine
from agentwall.storage.database import Database


def protect_agent(
    agent,
    *,
    goal: str | None = None,
    db: Database | None = None,
    engine: SecurityEngine | None = None,
) -> ProtectedAgent:
    return ProtectedAgent(agent, goal=goal, db=db, engine=engine)


__all__ = [
    "protect_agent",
    "protect_tool",
    "ProtectedAgent",
    "BaseInterceptor",
    "ToolInterceptor",
]
