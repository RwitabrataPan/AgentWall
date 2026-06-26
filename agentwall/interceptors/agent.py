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
        framework: str | None = None,
        execution_id: str | None = None,
    ) -> None:
        self._agent = agent
        self._goal_ref: list[str] = [goal or ""]
        self._db = db or Database()
        if engine is None:
            from agentwall.security.engine import build_default_engine
            self._engine = build_default_engine(self._db)
        else:
            self._engine = engine

        # Project + execution tracking
        from agentwall.core.execution_manager import ExecutionManager
        self._exec_mgr = ExecutionManager(self._db)
        project = self._exec_mgr.current_project()
        self._project_id = project.id

        if execution_id is not None:
            # Shared execution (e.g. CrewAI multi-agent)
            self._execution_id: str = execution_id
            self._owns_execution = False
        else:
            _model = self._resolve_model()
            execution = self._exec_mgr.create(
                project.id,
                goal or "",
                framework=framework,
                model=_model,
            )
            self._execution_id = execution.id
            self._owns_execution = True

        self._session_mgr = SessionManager(self._db)
        self._session: Session = self._session_mgr.create(
            self._goal_ref[0],
            project_id=self._project_id,
            execution_id=self._execution_id,
        )
        self._interceptor = ToolInterceptor(self._db, self._engine)
        from agentwall.security.goal_tracker import GoalTracker
        self._goal_tracker = GoalTracker(self._session.id, self._db, self._goal_ref)
        if goal:
            self._goal_tracker.set_goal(goal, reason="initial")
        self._closed = False

    def _resolve_model(self) -> str | None:
        try:
            from agentwall.core.config_manager import ConfigManager
            providers = ConfigManager(self._db).list_providers_ordered()
            if providers:
                return providers[0].model
        except Exception:
            pass
        return None

    @property
    def session_id(self) -> str:
        return self._session.id

    @property
    def execution_id(self) -> str:
        return self._execution_id

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
            if self._owns_execution:
                self._exec_mgr.finish(self._execution_id)
            self._closed = True

    def close(self) -> None:
        self.end_session()

    def __enter__(self) -> "ProtectedAgent":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)
