from __future__ import annotations

from fastapi import APIRouter, Depends

from agentwall.core.config_manager import ConfigManager
from agentwall.core.execution_manager import ExecutionManager
from agentwall.inspector.deps import (
    get_config_manager,
    get_db,
    get_execution_manager,
    get_policy_engine,
)
from agentwall.inspector.routes.executions import build_execution_summaries
from agentwall.inspector.routes.overview import build_overview
from agentwall.models.schemas import InspectorRefreshSchema
from agentwall.security.policy_engine import PolicyEngine

router = APIRouter(prefix="/api", tags=["refresh"])


@router.get("/refresh", response_model=InspectorRefreshSchema)
def refresh(
    db=Depends(get_db),
    mgr: ExecutionManager = Depends(get_execution_manager),
    config: ConfigManager = Depends(get_config_manager),
    policies: PolicyEngine = Depends(get_policy_engine),
):
    project = mgr.inspector_project()
    return {
        "project": project,
        "overview": build_overview(project, db),
        "executions": build_execution_summaries(project.id, mgr, db),
        "providers": config.list_providers_ordered(),
        "policies": policies.list(),
    }
