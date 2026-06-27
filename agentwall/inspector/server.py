from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes.events import router as events_router
from .routes.executions import router as executions_router
from .routes.export import router as export_router
from .routes.goals import router as goals_router
from .routes.health import router as health_router
from .routes.overview import router as overview_router
from .routes.policies import router as policies_router
from .routes.projects import router as projects_router
from .routes.providers import router as providers_router
from .routes.refresh import router as refresh_router
from .routes.sessions import router as sessions_router
from .routes.ws import router as ws_router

@asynccontextmanager
async def _lifespan(app: FastAPI):
    from agentwall.inspector.event_bus import get_bus
    from agentwall.inspector.deps import get_inspector_project_root
    get_inspector_project_root()
    get_bus().set_loop(asyncio.get_event_loop())
    yield


from agentwall import __version__

app = FastAPI(title="AgentWall Inspector", version=__version__, docs_url="/api/docs", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (
    health_router,
    overview_router,
    projects_router,
    executions_router,
    sessions_router,
    events_router,
    goals_router,
    policies_router,
    providers_router,
    refresh_router,
    export_router,
    ws_router,
):
    app.include_router(r)

_UI_DIST = Path(__file__).parent / "ui" / "dist"
if _UI_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_UI_DIST), html=True), name="ui")
