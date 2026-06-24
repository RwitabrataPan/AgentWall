from __future__ import annotations

from typing import Any, Callable

from agentwall.core.session_manager import SessionManager
from agentwall.core.types import ResourceCategory, ToolAction, ToolType
from agentwall.interceptors.tool import ToolInterceptor, protect_tool
from agentwall.security.engine import SecurityEngine
from agentwall.storage.database import Database
from agentwall.storage.models import Session


class ProtectedAgent:
    """Wraps an agent to intercept and evaluate all tool calls.

    Session lifecycle is explicit: call end_session() or close() when done,
    or use as a context manager.

    If *goal* is omitted, call set_goal() before tools fire so the session
    goal is recorded correctly. Framework integrations handle this automatically.
    """

    def __init__(
        self,
        agent: Any,
        *,
        goal: str | None = None,
        db: Database | None = None,
        engine: SecurityEngine | None = None,
    ) -> None:
        self._agent = agent
        self._goal_ref: list[str] = [goal or ""]
        self._db = db or Database()
        if engine is None:
            from agentwall.security.engine import build_default_engine
            self._engine = build_default_engine(self._db)
        else:
            self._engine = engine
        self._session_mgr = SessionManager(self._db)
        self._session: Session = self._session_mgr.create(self._goal_ref[0])
        self._interceptor = ToolInterceptor(self._db, self._engine)
        from agentwall.security.goal_tracker import GoalTracker
        self._goal_tracker = GoalTracker(self._session.id, self._db, self._goal_ref)
        if goal:
            self._goal_tracker.set_goal(goal, reason="initial")
        self._closed = False

    @property
    def session_id(self) -> str:
        return self._session.id

    @property
    def goal(self) -> str:
        return self._goal_ref[0]

    def set_goal(self, goal: str) -> None:
        """Transition to a new goal. Creates a goal segment and updates session DB."""
        self._goal_tracker.set_goal(goal)
        self._session_mgr.update_goal(self._session.id, self._goal_ref[0])

    def maybe_infer_goal(self, new_input: str) -> bool:
        """Infer or transition goal from new input. Returns True if goal changed."""
        changed = self._goal_tracker.maybe_infer(new_input)
        if changed:
            self._session_mgr.update_goal(self._session.id, self._goal_ref[0])
        return changed

    def protect_tool(
        self,
        fn: Callable,
        *,
        tool_type: ToolType,
        action: ToolAction | None = None,
        resource_category: ResourceCategory = ResourceCategory.UNKNOWN,
    ) -> Callable:
        return protect_tool(
            fn,
            tool_type=tool_type,
            session_id=self._session.id,
            goal_ref=self._goal_ref,
            interceptor=self._interceptor,
            action=action,
            resource_category=resource_category,
        )

    def run(self, *args, **kwargs) -> Any:
        return self._agent.run(*args, **kwargs)

    def end_session(self) -> None:
        if not self._closed:
            self._session_mgr.end(self._session.id)
            self._closed = True

    def close(self) -> None:
        self.end_session()

    def __enter__(self) -> "ProtectedAgent":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)
