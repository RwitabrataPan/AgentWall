from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

_DEFAULT_PATH = Path.home() / ".agentwall" / "data.db"


def _set_wal_mode(dbapi_conn, _):
    dbapi_conn.execute("PRAGMA journal_mode=WAL")
    dbapi_conn.execute("PRAGMA foreign_keys=ON")


class Database:
    def __init__(self, path: Path | str | None = None) -> None:
        db_path = Path(path) if path else _DEFAULT_PATH
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        event.listen(self.engine, "connect", _set_wal_mode)
        Base.metadata.create_all(self.engine)
        self._migrate()
        self._factory = sessionmaker(bind=self.engine)

    def _migrate(self) -> None:
        with self.engine.connect() as conn:
            for col, typedef in [
                ("priority", "INTEGER NOT NULL DEFAULT 0"),
                ("enabled", "INTEGER NOT NULL DEFAULT 1"),
            ]:
                try:
                    conn.execute(text(f"ALTER TABLE provider_settings ADD COLUMN {col} {typedef}"))
                    conn.commit()
                except Exception:
                    pass

            for col, typedef in [
                ("tool_type", "TEXT"),
                ("action", "TEXT"),
                ("target", "TEXT"),
                ("resource_category", "TEXT"),
            ]:
                try:
                    conn.execute(text(f"ALTER TABLE tool_events ADD COLUMN {col} {typedef}"))
                    conn.commit()
                except Exception:
                    pass

            for col, typedef in [
                ("alignment_score", "REAL"),
                ("detector_hits", "TEXT"),
                ("policy_matched", "TEXT"),
                ("post_execution_risk", "REAL"),
                ("result_classification", "TEXT"),
                ("result_detector_hits", "TEXT"),
                ("result_metadata", "TEXT"),
            ]:
                try:
                    conn.execute(text(f"ALTER TABLE evaluations ADD COLUMN {col} {typedef}"))
                    conn.commit()
                except Exception:
                    pass

            for col, typedef in [
                ("enabled", "INTEGER NOT NULL DEFAULT 1"),
                ("priority", "INTEGER NOT NULL DEFAULT 0"),
            ]:
                try:
                    conn.execute(text(f"ALTER TABLE policies ADD COLUMN {col} {typedef}"))
                    conn.commit()
                except Exception:
                    pass

            try:
                conn.execute(text("ALTER TABLE goal_segments ADD COLUMN confidence REAL NOT NULL DEFAULT 1.0"))
                conn.commit()
            except Exception:
                pass

    def session(self) -> Session:
        return self._factory()

    def close(self) -> None:
        self.engine.dispose()
