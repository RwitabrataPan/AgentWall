from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DecisionType(str, Enum):
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"


class ToolType(str, Enum):
    FILESYSTEM = "filesystem"
    TERMINAL = "terminal"
    BROWSER = "browser"
    API = "api"
    DATABASE = "database"
    EMAIL = "email"
    GENERAL = "general"


class ToolAction(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    REQUEST = "request"
    QUERY = "query"
    SEND = "send"
    LIST = "list"
    CREATE = "create"


class ResourceCategory(str, Enum):
    CODE = "code"
    CONFIG = "config"
    CREDENTIALS = "credentials"
    SYSTEM = "system"
    NETWORK = "network"
    USER_DATA = "user_data"
    UNKNOWN = "unknown"


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    session_id: str


@dataclass
class EvalContext:
    user_goal: str
    tool_call: ToolCall
    recent_history: list[ToolCall] = field(default_factory=list)


@dataclass
class Decision:
    type: DecisionType
    risk_score: float
    reason: str
    llm_used: bool = False
    alignment_score: float | None = None
    detector_hits: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class RuntimeEvent:
    session_id: str
    goal: str
    tool_type: ToolType
    action: ToolAction
    target: str
    resource_category: ResourceCategory
    metadata: dict
    tool_name: str = ""
    timestamp: float = field(default_factory=time.time)
