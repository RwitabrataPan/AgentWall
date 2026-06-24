from __future__ import annotations

from fastapi import APIRouter, Depends

from agentwall.inspector.deps import get_db
from agentwall.models.schemas import OverviewSchema
from agentwall.storage.models import Evaluation, Session, ToolEvent

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview", response_model=OverviewSchema)
def overview(db=Depends(get_db)):
    with db.session() as s:
        active = s.query(Session).filter(Session.ended_at.is_(None)).count()
        total_sessions = s.query(Session).count()
        total_events = s.query(ToolEvent).count()
        allow = s.query(Evaluation).filter(Evaluation.decision == "allow").count()
        warn = s.query(Evaluation).filter(Evaluation.decision == "warn").count()
        block = s.query(Evaluation).filter(Evaluation.decision == "block").count()

    return OverviewSchema(
        active_sessions=active,
        total_sessions=total_sessions,
        total_events=total_events,
        threat_count=warn + block,
        risk_distribution={"allow": allow, "warn": warn, "block": block},
    )
