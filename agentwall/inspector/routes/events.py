from fastapi import APIRouter, Depends

from agentwall.core.event_manager import EventManager
from agentwall.models.schemas import ToolEventSchema
from agentwall.inspector.deps import get_event_manager

router = APIRouter(prefix="/api/sessions/{session_id}/events", tags=["events"])


@router.get("", response_model=list[ToolEventSchema])
def list_events(session_id: str, mgr: EventManager = Depends(get_event_manager)):
    return mgr.get_events_with_evaluations(session_id)
