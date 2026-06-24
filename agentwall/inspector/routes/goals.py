from __future__ import annotations

from fastapi import APIRouter, Depends

from agentwall.core.event_manager import EventManager
from agentwall.inspector.deps import get_event_manager
from agentwall.models.schemas import GoalSegmentSchema

router = APIRouter(prefix="/api/sessions/{session_id}/goals", tags=["goals"])


@router.get("", response_model=list[GoalSegmentSchema])
def list_goal_segments(session_id: str, mgr: EventManager = Depends(get_event_manager)):
    return mgr.get_goal_segments(session_id)
