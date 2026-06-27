from __future__ import annotations

from fastapi import APIRouter, Depends

from agentwall.inspector.deps import get_execution_manager
from agentwall.core.execution_manager import ExecutionManager
from agentwall.models.schemas import ProjectSchema

router = APIRouter(prefix="/api/project", tags=["project"])


@router.get("", response_model=ProjectSchema)
def current_project(mgr: ExecutionManager = Depends(get_execution_manager)):
    project = mgr.inspector_project()
    return project
