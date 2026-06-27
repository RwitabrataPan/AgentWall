from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from agentwall.core.config_manager import ConfigManager
from agentwall.core.event_manager import EventManager
from agentwall.core.execution_manager import ExecutionManager
from agentwall.core.project import detect_project_root
from agentwall.core.session_manager import SessionManager
from agentwall.security.policy_engine import PolicyEngine
from agentwall.storage.database import Database


@lru_cache(maxsize=1)
def get_db() -> Database:
    return Database()


@lru_cache(maxsize=1)
def get_inspector_project_root() -> Path:
    return detect_project_root()


def get_session_manager() -> SessionManager:
    return SessionManager(get_db())


def get_event_manager() -> EventManager:
    return EventManager(get_db())


def get_config_manager() -> ConfigManager:
    return ConfigManager(get_db())


def get_policy_engine() -> PolicyEngine:
    return PolicyEngine(get_db())


def get_execution_manager() -> ExecutionManager:
    return ExecutionManager(get_db(), inspector_root=get_inspector_project_root())
