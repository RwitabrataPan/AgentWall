from fastapi import APIRouter
from agentwall import __version__

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok", "version": __version__}
