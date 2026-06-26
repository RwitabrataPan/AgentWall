from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import joinedload

from agentwall.inspector.deps import get_db, get_execution_manager
from agentwall.core.execution_manager import ExecutionManager
from agentwall.models.schemas import ExecutionSummarySchema, SessionSchema, ToolEventSchema
from agentwall.storage.models import Evaluation, Execution, Session, ToolEvent

router = APIRouter(prefix="/api/executions", tags=["executions"])


def _summarise(execution: Execution, db_session) -> ExecutionSummarySchema:
    sessions = (
        db_session.query(Session)
        .filter(Session.execution_id == execution.id)
        .options(joinedload(Session.events).joinedload(ToolEvent.evaluation))
        .all()
    )
    all_evals: list[Evaluation] = []
    event_count = 0
    for sess in sessions:
        event_count += len(sess.events)
        all_evals.extend(e.evaluation for e in sess.events if e.evaluation)

    max_risk = max((e.risk_score for e in all_evals), default=None)
    threat_count = sum(1 for e in all_evals if e.decision in ("warn", "block"))

    decisions = [e.decision for e in all_evals]
    if "block" in decisions:
        overall = "block"
    elif "warn" in decisions:
        overall = "warn"
    elif decisions:
        overall = "allow"
    else:
        overall = None

    return ExecutionSummarySchema(
        id=execution.id,
        project_id=execution.project_id,
        goal=execution.goal,
        prompt=execution.prompt,
        framework=execution.framework,
        model=execution.model,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        status=execution.status,
        meta=execution.meta or {},
        event_count=event_count,
        threat_count=threat_count,
        max_risk=max_risk,
        overall_decision=overall,
    )


@router.get("", response_model=list[ExecutionSummarySchema])
def list_executions(mgr: ExecutionManager = Depends(get_execution_manager), db=Depends(get_db)):
    executions = mgr.list_all()
    with db.session() as s:
        return [_summarise(ex, s) for ex in executions]


@router.get("/{execution_id}", response_model=ExecutionSummarySchema)
def get_execution(execution_id: str, mgr: ExecutionManager = Depends(get_execution_manager), db=Depends(get_db)):
    ex = mgr.get(execution_id)
    if not ex:
        raise HTTPException(404, detail="Execution not found")
    with db.session() as s:
        ex_row = s.get(Execution, execution_id)
        if not ex_row:
            raise HTTPException(404, detail="Execution not found")
        return _summarise(ex_row, s)


@router.get("/{execution_id}/sessions", response_model=list[SessionSchema])
def get_execution_sessions(execution_id: str, db=Depends(get_db)):
    with db.session() as s:
        sessions = (
            s.query(Session)
            .filter(Session.execution_id == execution_id)
            .order_by(Session.created_at)
            .all()
        )
        result = []
        for sess in sessions:
            s.expunge(sess)
            result.append(SessionSchema.model_validate(sess))
    return result


@router.get("/{execution_id}/events", response_model=list[ToolEventSchema])
def get_execution_events(execution_id: str, db=Depends(get_db)):
    with db.session() as s:
        sessions = s.query(Session).filter(Session.execution_id == execution_id).all()
        session_ids = [sess.id for sess in sessions]
        if not session_ids:
            return []
        events = (
            s.query(ToolEvent)
            .filter(ToolEvent.session_id.in_(session_ids))
            .options(joinedload(ToolEvent.evaluation))
            .order_by(ToolEvent.timestamp)
            .all()
        )
        result = []
        for ev in events:
            s.expunge(ev)
            result.append(ToolEventSchema.model_validate(ev))
    return result
