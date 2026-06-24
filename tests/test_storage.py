"""Tests for Database layer: WAL mode, schema creation, basic I/O."""
from pathlib import Path
from agentwall.storage.database import Database
from agentwall.storage.models import Session, ToolEvent


def test_database_creates_schema(db: Database):
    with db.session() as s:
        result = s.execute(
            __import__("sqlalchemy").text(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ).fetchall()
        tables = {r[0] for r in result}
    assert {"sessions", "tool_events", "evaluations", "policies", "provider_settings"} <= tables


def test_database_wal_mode(db: Database):
    with db.session() as s:
        mode = s.execute(__import__("sqlalchemy").text("PRAGMA journal_mode")).scalar()
    assert mode == "wal"


def test_database_custom_path():
    import tempfile, shutil
    tmpdir = tempfile.mkdtemp(prefix="agentwall_test_")
    try:
        custom = Path(tmpdir) / "custom" / "db.sqlite"
        db = Database(path=custom)
        assert custom.exists()
        db.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
