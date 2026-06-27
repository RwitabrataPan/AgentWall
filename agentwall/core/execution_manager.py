from __future__ import annotations

import time
import uuid
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from agentwall.core.project import detect_project_root, project_id_for, project_name_for
from agentwall.storage.database import Database
from agentwall.storage.models import Execution, Project


class ExecutionManager:
    def __init__(self, db: Database, inspector_root: Path | None = None) -> None:
        self._db = db
        self._inspector_root = inspector_root.resolve() if inspector_root is not None else None

    def get_or_create_project(self, root: Path | None = None) -> Project:
        if root is None:
            root = detect_project_root()
        root = root.resolve()  # normalize: same path → same hash always
        pid = project_id_for(root)
        with self._db.session() as db:
            row = db.get(Project, pid)
            if row:
                db.expunge(row)
                return row
            row = Project(
                id=pid,
                name=project_name_for(root),
                root=str(root),
                created_at=time.time(),
            )
            db.add(row)
            try:
                db.commit()
                db.refresh(row)
            except IntegrityError:
                # Race condition: another caller inserted between our get and insert
                db.rollback()
                row = db.query(Project).filter(Project.root == str(root)).first()
            db.expunge(row)
        return row

    def create(
        self,
        project_id: str,
        goal: str,
        *,
        prompt: str | None = None,
        framework: str | None = None,
        model: str | None = None,
        meta: dict | None = None,
    ) -> Execution:
        with self._db.session() as db:
            row = Execution(
                id=str(uuid.uuid4()),
                project_id=project_id,
                goal=goal,
                prompt=prompt,
                framework=framework,
                model=model,
                started_at=time.time(),
                status="running",
                meta=meta or {},
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            db.expunge(row)
        return row

    def finish(self, execution_id: str, *, status: str = "completed") -> None:
        with self._db.session() as db:
            row = db.get(Execution, execution_id)
            if row:
                row.finished_at = time.time()
                row.status = status
                db.commit()
        # Notify Inspector — no-op when agent runs cross-process
        try:
            from agentwall.inspector.event_bus import get_bus
            get_bus().publish()
        except Exception:
            pass

    def get(self, execution_id: str) -> Execution | None:
        with self._db.session() as db:
            row = db.get(Execution, execution_id)
            if row:
                db.expunge(row)
            return row

    def list_for_project(self, project_id: str, limit: int = 100) -> list[Execution]:
        with self._db.session() as db:
            rows = (
                db.query(Execution)
                .filter(Execution.project_id == project_id)
                .order_by(Execution.started_at.desc())
                .limit(limit)
                .all()
            )
            for r in rows:
                db.expunge(r)
            return rows

    def list_all(self, limit: int = 100) -> list[Execution]:
        with self._db.session() as db:
            rows = (
                db.query(Execution)
                .order_by(Execution.started_at.desc())
                .limit(limit)
                .all()
            )
            for r in rows:
                db.expunge(r)
            return rows

    def latest_execution_project(self) -> Project | None:
        """Return the project that owns the newest execution, if any."""
        with self._db.session() as db:
            row = (
                db.query(Project)
                .join(Execution, Execution.project_id == Project.id)
                .order_by(Execution.started_at.desc())
                .first()
            )
            if row:
                db.expunge(row)
            return row

    def inspector_project(self) -> Project:
        """Project context for polling Inspector views.

        Inspector views are anchored to the project where the Inspector process
        was launched when an Inspector root is pinned. Agent-side managers that
        do not receive a pinned root keep using current process project
        detection for backward compatibility.
        """
        if self._inspector_root is not None:
            return self.get_or_create_project(self._inspector_root)
        return self.current_project()

    def current_project_id(self) -> str:
        """Project ID for the current working directory."""
        root = detect_project_root()
        project = self.get_or_create_project(root)
        return project.id

    def current_project(self) -> Project:
        root = detect_project_root()
        return self.get_or_create_project(root)
