from __future__ import annotations

import time
import uuid

from ..storage.database import Database
from ..storage.models import Session


class SessionManager:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(
        self,
        user_goal: str,
        meta: dict | None = None,
        *,
        project_id: str | None = None,
        execution_id: str | None = None,
    ) -> Session:
        session_id = str(uuid.uuid4())
        with self._db.session() as db:
            row = Session(
                id=session_id,
                user_goal=user_goal,
                created_at=time.time(),
                meta=meta or {},
                project_id=project_id,
                execution_id=execution_id,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            db.expunge(row)
        return row

    def get(self, session_id: str) -> Session | None:
        with self._db.session() as db:
            row = db.get(Session, session_id)
            if row:
                db.expunge(row)
            return row

    def end(self, session_id: str) -> None:
        with self._db.session() as db:
            row = db.get(Session, session_id)
            if row:
                row.ended_at = time.time()
                db.commit()

    def update_goal(self, session_id: str, user_goal: str) -> None:
        with self._db.session() as db:
            row = db.get(Session, session_id)
            if row:
                row.user_goal = user_goal
                db.commit()

    def list(self, limit: int = 100) -> list[Session]:
        with self._db.session() as db:
            rows = (
                db.query(Session)
                .order_by(Session.created_at.desc())
                .limit(limit)
                .all()
            )
            for r in rows:
                db.expunge(r)
            return rows
