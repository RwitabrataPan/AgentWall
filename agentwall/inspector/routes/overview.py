from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends

from agentwall.inspector.deps import get_db, get_execution_manager
from agentwall.core.execution_manager import ExecutionManager
from agentwall.models.schemas import OverviewSchema
from agentwall.storage.models import Evaluation, Execution, Session, ToolEvent

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview", response_model=OverviewSchema)
def overview(mgr: ExecutionManager = Depends(get_execution_manager), db=Depends(get_db)):
    project = mgr.inspector_project()
    project_id = project.id

    with db.session() as s:
        # Include legacy sessions (project_id IS NULL) for backward compat
        from sqlalchemy import or_
        project_filter = or_(Session.project_id == project_id, Session.project_id.is_(None))

        active = s.query(Session).filter(
            Session.ended_at.is_(None),
            project_filter,
        ).count()
        total_sessions = s.query(Session).filter(project_filter).count()

        active_executions = s.query(Execution).filter(
            Execution.project_id == project_id,
            Execution.status == "running",
        ).count()
        total_executions = s.query(Execution).filter(Execution.project_id == project_id).count()

        # Get session IDs for this project (including legacy NULL)
        project_session_ids = [
            r[0] for r in s.query(Session.id).filter(project_filter).all()
        ]

        total_events = s.query(ToolEvent).filter(
            ToolEvent.session_id.in_(project_session_ids)
        ).count() if project_session_ids else 0

        evals = s.query(Evaluation).join(ToolEvent).filter(
            ToolEvent.session_id.in_(project_session_ids)
        ).all() if project_session_ids else []

        allow = sum(1 for e in evals if e.decision == "allow")
        warn = sum(1 for e in evals if e.decision == "warn")
        block = sum(1 for e in evals if e.decision == "block")
        threat_count = warn + block

        avg_risk: float | None = None
        if evals:
            avg_risk = round(sum(e.risk_score for e in evals) / len(evals), 1)

        # Top detectors (from detector_hits JSON arrays)
        detector_counter: Counter = Counter()
        for e in evals:
            if e.detector_hits:
                for hit in e.detector_hits:
                    detector_counter[hit] += 1
        top_detectors = [
            {"name": name, "count": count}
            for name, count in detector_counter.most_common(5)
        ]

        # Top policies
        policy_counter: Counter = Counter()
        for e in evals:
            if e.policy_matched:
                policy_counter[e.policy_matched] += 1
        top_policies = [
            {"name": name, "count": count}
            for name, count in policy_counter.most_common(5)
        ]

    # Current provider
    current_provider: str | None = None
    current_model: str | None = None
    try:
        from agentwall.core.config_manager import ConfigManager
        providers = ConfigManager(db).list_providers_ordered()
        if providers:
            current_provider = providers[0].provider
            current_model = providers[0].model
    except Exception:
        pass

    return OverviewSchema(
        project_id=project_id,
        project_name=project.name,
        active_sessions=active,
        total_sessions=total_sessions,
        active_executions=active_executions,
        total_executions=total_executions,
        total_events=total_events,
        threat_count=threat_count,
        risk_distribution={"allow": allow, "warn": warn, "block": block},
        avg_risk=avg_risk,
        current_provider=current_provider,
        current_model=current_model,
        top_detectors=top_detectors,
        top_policies=top_policies,
    )
