from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import joinedload

from agentwall.inspector.deps import get_db, get_session_manager
from agentwall.core.session_manager import SessionManager
from agentwall.models.schemas import SessionSchema, SessionSummarySchema
from agentwall.storage.models import Session, ToolEvent

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionSummarySchema])
def list_sessions(db=Depends(get_db)):
    with db.session() as s:
        sessions = (
            s.query(Session)
            .options(joinedload(Session.events).joinedload(ToolEvent.evaluation))
            .order_by(Session.created_at.desc())
            .all()
        )
        result = []
        for sess in sessions:
            evals = [e.evaluation for e in sess.events if e.evaluation]
            max_risk = max((e.risk_score for e in evals), default=None)
            threats = sum(1 for e in evals if e.decision in ("warn", "block"))
            result.append(
                SessionSummarySchema(
                    id=sess.id,
                    user_goal=sess.user_goal,
                    created_at=sess.created_at,
                    ended_at=sess.ended_at,
                    meta=sess.meta,
                    event_count=len(sess.events),
                    max_risk=max_risk,
                    threat_count=threats,
                )
            )
    return result


@router.get("/{session_id}", response_model=SessionSchema)
def get_session(session_id: str, mgr: SessionManager = Depends(get_session_manager)):
    row = mgr.get(session_id)
    if not row:
        raise HTTPException(404, detail="Session not found")
    return row


@router.post("/{session_id}/end")
def end_session(session_id: str, mgr: SessionManager = Depends(get_session_manager)):
    mgr.end(session_id)
    return {"ok": True}
