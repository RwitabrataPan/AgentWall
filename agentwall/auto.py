"""
Zero-configuration auto-instrumentation for AgentWall.

Imported by agentwall/__init__.py on startup. Patches supported frameworks
when they are available so ``import agentwall`` is sufficient for protection.

Design: one ProtectedAgent session per framework object (executor / crew / agent).
Multiple invoke/kickoff/run calls on the same object share one session.
Sessions end automatically when the object is garbage-collected or the process
exits. For explicit per-run sessions, use the protect_* API directly.

Disable auto-mode: set env var AGENTWALL_AUTO=0 before importing agentwall.
"""
from __future__ import annotations

import atexit
import os
import threading
import weakref
from typing import Any

_lock = threading.Lock()
_db = None
_engine = None
_active_walls: list[weakref.ref] = []
_enabled = os.environ.get("AGENTWALL_AUTO", "1") != "0"


def _get_db():
    global _db
    if _db is None:
        from agentwall.storage.database import Database
        _db = Database()
    return _db


def _get_engine():
    global _engine
    if _engine is None:
        from agentwall.security.engine import build_default_engine
        _engine = build_default_engine(_get_db())
    return _engine


def _register_wall(wall: Any) -> None:
    _active_walls.append(weakref.ref(wall))


def _safe_end(wall: Any) -> None:
    try:
        wall.end_session()
    except Exception:
        pass


@atexit.register
def _shutdown() -> None:
    for ref in _active_walls:
        w = ref()
        if w is not None:
            _safe_end(w)


# ── LangChain ─────────────────────────────────────────────────────────────────

def _try_patch_langchain() -> None:
    try:
        from langchain.agents import AgentExecutor
    except ImportError:
        return
    if getattr(AgentExecutor, "_aw_auto_patched", False):
        return

    orig_init = AgentExecutor.__init__

    def _aw_init(self, *args: Any, **kwargs: Any) -> None:
        orig_init(self, *args, **kwargs)
        if getattr(self, "_aw_auto_protected", False):
            return
        try:
            with _lock:
                db = _get_db()
                engine = _get_engine()
            from agentwall.integrations.langchain import protect_langchain_agent
            wall = protect_langchain_agent(self, db=db, engine=engine)
            self._aw_wall = wall
            self._aw_auto_protected = True
            _register_wall(wall)
            weakref.finalize(self, _safe_end, wall)
        except Exception:
            pass

    AgentExecutor.__init__ = _aw_init
    AgentExecutor._aw_auto_patched = True


# ── CrewAI ────────────────────────────────────────────────────────────────────

def _try_patch_crewai() -> None:
    try:
        from crewai import Crew
    except ImportError:
        return
    if getattr(Crew, "_aw_auto_patched", False):
        return

    orig_init = Crew.__init__

    def _aw_init(self, *args: Any, **kwargs: Any) -> None:
        orig_init(self, *args, **kwargs)
        if getattr(self, "_aw_auto_protected", False):
            return
        try:
            with _lock:
                db = _get_db()
                engine = _get_engine()
            from agentwall.integrations.crewai import protect_crewai_crew
            wall = protect_crewai_crew(self, db=db, engine=engine)
            self._aw_wall = wall
            self._aw_auto_protected = True
            _register_wall(wall)
            weakref.finalize(self, _safe_end, wall)
        except Exception:
            pass

    Crew.__init__ = _aw_init
    Crew._aw_auto_patched = True


# ── OpenAI Agents SDK ─────────────────────────────────────────────────────────

def _try_patch_openai_agents() -> None:
    try:
        from agents import Runner
    except ImportError:
        return
    if getattr(Runner, "_aw_auto_patched", False):
        return

    orig_run = staticmethod(Runner.run.__func__) if hasattr(Runner.run, "__func__") else Runner.run

    @classmethod  # type: ignore[misc]
    async def _aw_run(cls, starting_agent: Any, input: Any, **kwargs: Any) -> Any:
        # Already a protected agent (i.e., created by protect_openai_agent) — pass through
        if getattr(starting_agent, "_aw_is_protected", False):
            return await orig_run(starting_agent, input, **kwargs)

        try:
            with _lock:
                db = _get_db()
                engine = _get_engine()
            from agentwall.integrations.openai_agents import (
                _extract_goal_text,
                protect_openai_agent,
            )
            wall, protected = protect_openai_agent(starting_agent, db=db, engine=engine)
            goal = _extract_goal_text(input)
            if goal:
                wall.maybe_infer_goal(goal)
            try:
                result = await orig_run(protected, input, **kwargs)
            finally:
                wall.end_session()
            return result
        except Exception:
            # Fallback: run unprotected if auto-instrumentation fails
            return await orig_run(starting_agent, input, **kwargs)

    Runner.run = _aw_run
    Runner._aw_auto_patched = True


def setup() -> None:
    """Attempt to patch all supported frameworks. Idempotent. Called at import."""
    if not _enabled:
        return
    _try_patch_langchain()
    _try_patch_crewai()
    _try_patch_openai_agents()
