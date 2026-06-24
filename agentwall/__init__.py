from importlib.metadata import version

__version__ = version("agentwall-security")

from agentwall.interceptors import protect_agent, protect_tool

__all__ = ["protect_agent", "protect_tool"]
