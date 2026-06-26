from __future__ import annotations

import time
import uuid
from pathlib import Path

from agentwall.core.project import detect_project_root, project_id_for, project_name_for
from agentwall.storage.database import Database
from agentwall.storage.models import Execution, Project


class ExecutionManager:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get_or_create_project(self, root: Path | None = None) -> Project:
        if root is None:
            root = detect_project_root()
        pid = project_id_for(root)
        with self._db.session() as db:
            row = db.get(Project, pid)
            if not row:
                row = Project(
                    id=pid,
                    name=project_name_for(root),
                    root=str(root),
                    created_at=time.time(),
                )
                db.add(row)
                db.commit()
                db.refresh(row)
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

    def current_project_id(self) -> str:
        """Project ID for the current working directory."""
        root = detect_project_root()
        project = self.get_or_create_project(root)
        return project.id

    def current_project(self) -> Project:
        root = detect_project_root()
        return self.get_or_create_project(root)
