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

        # Any failure after exec_mgr.create() would orphan the committed Execution
        # row in "running" state. Catch and mark it "failed" before re-raising.
        try:
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
        except Exception:
            if self._owns_execution:
                try:
                    self._exec_mgr.finish(self._execution_id, status="failed")
                except Exception:
                    pass
            raise

        # Notify Inspector of new execution — no-op when agent runs cross-process
        try:
            from agentwall.inspector.event_bus import get_bus
            get_bus().publish()
        except Exception:
            pass

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

    def end_session(self, *, status: str = "completed") -> None:
        if self._closed:
            return
        self._closed = True  # set first — prevents re-entry even if DB ops fail
        try:
            self._session_mgr.end(self._session.id)
        except Exception:
            pass
        if self._owns_execution:
            try:
                self._exec_mgr.finish(self._execution_id, status=status)
            except Exception:
                pass

    def close(self, *, status: str = "completed") -> None:
        self.end_session(status=status)

    def __enter__(self) -> "ProtectedAgent":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close(status="failed" if exc_type is not None else "completed")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)
