from __future__ import annotations

import functools
import time
from typing import Any, Callable

from agentwall.core.types import (
    Decision,
    DecisionType,
    ResourceCategory,
    RuntimeEvent,
    ToolAction,
    ToolType,
)
from agentwall.interceptors.base import BaseInterceptor
from agentwall.security.engine import SecurityEngine
from agentwall.security.exceptions import AgentWallSecurityException
from agentwall.storage.database import Database
from agentwall.storage.models import ToolEvent


class ToolInterceptor(BaseInterceptor):
    def __init__(self, db: Database, engine: SecurityEngine) -> None:
        self._db = db
        self._engine = engine
        self._event_id_map: dict[int, int] = {}  # id(RuntimeEvent) → db ToolEvent.id

    def before_execute(self, event: RuntimeEvent) -> Decision:
        history = self._fetch_history(event.session_id)  # fetch BEFORE recording
        db_event = self.record_event(event)
        self._event_id_map[id(event)] = db_event.id
        decision = self.evaluate_event(event, history)
        self._persist_evaluation(db_event.id, decision)
        from agentwall.inspector.event_bus import get_bus
        get_bus().publish()
        if decision.type == DecisionType.BLOCK:
            raise AgentWallSecurityException(decision, event)
        return decision

    def after_execute(self, event: RuntimeEvent, result: Any) -> None:
        event_id = self._event_id_map.pop(id(event), None)
        if event_id is None:
            return
        from agentwall.core.event_manager import EventManager
        from agentwall.security.result_analyzer import ResultAnalyzer
        analysis = ResultAnalyzer().analyze(event, result)
        EventManager(self._db).update_evaluation_post(
            event_id,
            post_execution_risk=analysis.post_risk,
            result_classification=analysis.classification.value,
            result_detector_hits=analysis.detector_hits,
            result_metadata=analysis.metadata,
        )
        from agentwall.inspector.event_bus import get_bus
        get_bus().publish()

    def record_event(self, event: RuntimeEvent) -> ToolEvent:
        from agentwall.core.event_manager import EventManager

        return EventManager(self._db).record(
            session_id=event.session_id,
            tool_name=event.tool_name or f"{event.tool_type.value}.{event.action.value}",
            arguments=event.metadata,
            tool_type=event.tool_type.value,
            action=event.action.value,
            target=event.target,
            resource_category=event.resource_category.value,
        )

    def evaluate_event(
        self,
        event: RuntimeEvent,
        history: list[RuntimeEvent] | None = None,
    ) -> Decision:
        return self._engine.evaluate(event, history)

    def _persist_evaluation(self, event_id: int, decision: Decision) -> None:
        from agentwall.core.event_manager import EventManager

        EventManager(self._db).record_evaluation(
            event_id=event_id,
            decision=decision.type.value,
            risk_score=decision.risk_score,
            reason=decision.reason,
            llm_used=decision.llm_used,
            alignment_score=decision.alignment_score,
            detector_hits=decision.detector_hits or [],
            policy_matched=decision.metadata.get("policy_matched"),
        )

    def _fetch_history(self, session_id: str, limit: int = 20) -> list[RuntimeEvent]:
        from agentwall.core.event_manager import EventManager
        from agentwall.core.types import ResourceCategory, ToolAction, ToolType

        rows = EventManager(self._db).get_events(session_id)[-limit:]
        result = []
        for r in rows:
            try:
                result.append(RuntimeEvent(
                    session_id=r.session_id,
                    goal="",
                    tool_type=ToolType(r.tool_type) if r.tool_type else ToolType.FILESYSTEM,
                    action=ToolAction(r.action) if r.action else ToolAction.READ,
                    target=r.target or "",
                    resource_category=(
                        ResourceCategory(r.resource_category)
                        if r.resource_category else ResourceCategory.UNKNOWN
                    ),
                    metadata=r.arguments or {},
                    tool_name=r.tool_name,
                    timestamp=r.timestamp,
                ))
            except (ValueError, KeyError):
                pass
        return result


def protect_tool(
    fn: Callable,
    *,
    tool_type: ToolType,
    session_id: str,
    goal: str | None = None,
    goal_ref: list[str] | None = None,
    interceptor: ToolInterceptor,
    action: ToolAction | None = None,
    resource_category: ResourceCategory = ResourceCategory.UNKNOWN,
) -> Callable:
    resolved_action = action or _default_action(tool_type)
    _ref = goal_ref if goal_ref is not None else [goal or ""]

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        event = RuntimeEvent(
            session_id=session_id,
            goal=_ref[0],
            tool_type=tool_type,
            action=resolved_action,
            target=_extract_target(args, kwargs),
            resource_category=resource_category,
            metadata={
                "args": [str(a) for a in args],
                "kwargs": {k: str(v) for k, v in kwargs.items()},
            },
            tool_name=fn.__name__,
            timestamp=time.time(),
        )
        decision = interceptor.before_execute(event)
        result = fn(*args, **kwargs)
        interceptor.after_execute(event, result)
        return result

    wrapper._aw_tool_type = tool_type
    wrapper._aw_session_id = session_id
    return wrapper


def _default_action(tool_type: ToolType) -> ToolAction:
    return {
        ToolType.FILESYSTEM: ToolAction.READ,
        ToolType.TERMINAL:   ToolAction.EXECUTE,
        ToolType.BROWSER:    ToolAction.REQUEST,
        ToolType.API:        ToolAction.REQUEST,
        ToolType.DATABASE:   ToolAction.QUERY,
        ToolType.EMAIL:      ToolAction.SEND,
    }.get(tool_type, ToolAction.READ)


def _extract_target(args: tuple, kwargs: dict) -> str:
    for key in ("target", "path", "directory", "url", "query", "command", "address", "recipient"):
        if key in kwargs:
            return str(kwargs[key])
    return str(args[0]) if args else ""
