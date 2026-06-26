from importlib.metadata import version

__version__ = version("agentwall-security")

from agentwall.interceptors import protect_agent, protect_tool
from agentwall.core.types import ToolType, ToolAction, ResourceCategory
from agentwall.security.exceptions import AgentWallSecurityException

# Zero-configuration auto-instrumentation — patches supported frameworks on import.
# Disable by setting AGENTWALL_AUTO=0 before importing agentwall.
try:
    from agentwall import auto as _auto
    _auto.setup()
except Exception:
    pass

__all__ = [
    "protect_agent",
    "protect_tool",
    "ToolType",
    "ToolAction",
    "ResourceCategory",
    "AgentWallSecurityException",
]
