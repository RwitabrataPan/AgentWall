"""Tests for project isolation: project detection, execution grouping, DB migration."""
from __future__ import annotations

import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

from agentwall.core.project import detect_project_root, project_id_for, project_name_for
from agentwall.core.execution_manager import ExecutionManager
from agentwall.storage.database import Database


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    os.environ["AGENTWALL_TEST_DB"] = str(db_path)
    d = Database(db_path)
    yield d
    d.close()
    del os.environ["AGENTWALL_TEST_DB"]


# ── project detection ────────────────────────────────────────────────────────

def test_project_id_deterministic():
    root = Path("/home/user/project-a").resolve()
    assert project_id_for(root) == project_id_for(root)


def test_project_id_differs_per_root():
    a = Path("/home/user/project-a").resolve()
    b = Path("/home/user/project-b").resolve()
    assert project_id_for(a) != project_id_for(b)


def test_project_id_is_16_chars():
    root = Path("/tmp/test").resolve()
    assert len(project_id_for(root)) == 16


def test_project_name_is_dir_name():
    root = Path("/home/user/my-project")
    assert project_name_for(root) == "my-project"


def test_detect_project_root_falls_back_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        root = detect_project_root()
    assert root == tmp_path.resolve()


def test_detect_project_root_uses_git_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake_root = str(tmp_path / "repo")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = fake_root + "\n"
        root = detect_project_root()
    assert root == Path(fake_root).resolve()


# ── ExecutionManager ─────────────────────────────────────────────────────────

def test_get_or_create_project_creates_new(db, tmp_path):
    mgr = ExecutionManager(db)
    root = tmp_path / "proj-a"
    root.mkdir()
    project = mgr.get_or_create_project(root)
    assert project.name == "proj-a"
    assert project.root == str(root.resolve())
    assert len(project.id) == 16


def test_get_or_create_project_idempotent(db, tmp_path):
    mgr = ExecutionManager(db)
    root = tmp_path / "proj-b"
    root.mkdir()
    p1 = mgr.get_or_create_project(root)
    p2 = mgr.get_or_create_project(root)
    assert p1.id == p2.id


def test_get_or_create_project_unresolved_path(db, tmp_path):
    """Unresolved and resolved paths for same dir must return same project."""
    mgr = ExecutionManager(db)
    root = tmp_path / "proj-resolve"
    root.mkdir()
    p1 = mgr.get_or_create_project(root)           # unresolved
    p2 = mgr.get_or_create_project(root.resolve())  # resolved
    assert p1.id == p2.id
    assert p1.root == str(root.resolve())


def test_get_or_create_project_no_duplicate_rows(db, tmp_path):
    """Multiple calls must not produce more than one Project row."""
    from agentwall.storage.models import Project as ProjectModel
    mgr = ExecutionManager(db)
    root = tmp_path / "proj-nodup"
    root.mkdir()
    for _ in range(5):
        mgr.get_or_create_project(root)
    with db.session() as sess:
        count = sess.query(ProjectModel).filter(ProjectModel.root == str(root.resolve())).count()
    assert count == 1


def test_get_or_create_project_concurrent(db, tmp_path):
    """Concurrent calls must not raise and must produce exactly one project."""
    from agentwall.storage.models import Project as ProjectModel
    mgr = ExecutionManager(db)
    root = tmp_path / "proj-concurrent"
    root.mkdir()
    errors = []

    def worker():
        try:
            mgr.get_or_create_project(root)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent get_or_create raised: {errors}"
    with db.session() as sess:
        count = sess.query(ProjectModel).filter(ProjectModel.root == str(root.resolve())).count()
    assert count == 1


def test_get_or_create_project_integrity_error_fallback(db, tmp_path):
    """IntegrityError on INSERT must fall back to existing row, not raise."""
    mgr = ExecutionManager(db)
    root = tmp_path / "proj-race"
    root.mkdir()
    # Insert row first so the race simulation finds it on rollback
    existing = mgr.get_or_create_project(root)

    original_session = db.session

    class _FakeCommit:
        """Context manager that raises IntegrityError on first commit."""
        def __init__(self):
            self._sess = original_session().__enter__()
            self._raised = False

        def __enter__(self):
            return self

        def get(self, model, pk):
            return None  # simulate "not found" to force INSERT path

        def query(self, model):
            return self._sess.query(model)

        def add(self, obj):
            self._sess.add(obj)

        def commit(self):
            if not self._raised:
                self._raised = True
                self._sess.rollback()
                raise IntegrityError("UNIQUE constraint failed: projects.root", {}, None)
            self._sess.commit()

        def rollback(self):
            self._sess.rollback()

        def expunge(self, obj):
            # obj may not be in session after rollback; ignore
            try:
                self._sess.expunge(obj)
            except Exception:
                pass

        def __exit__(self, *args):
            self._sess.__exit__(*args)

    with patch.object(db, "session", return_value=_FakeCommit()):
        recovered = mgr.get_or_create_project(root)

    assert recovered.id == existing.id


def test_create_execution(db, tmp_path):
    mgr = ExecutionManager(db)
    root = tmp_path / "proj-c"
    root.mkdir()
    project = mgr.get_or_create_project(root)
    ex = mgr.create(project.id, "Fix login bug", framework="openai-agents", model="gpt-4o")
    assert ex.id
    assert ex.goal == "Fix login bug"
    assert ex.framework == "openai-agents"
    assert ex.status == "running"
    assert ex.finished_at is None


def test_finish_execution(db, tmp_path):
    mgr = ExecutionManager(db)
    root = tmp_path / "proj-d"
    root.mkdir()
    project = mgr.get_or_create_project(root)
    ex = mgr.create(project.id, "task")
    mgr.finish(ex.id)
    fetched = mgr.get(ex.id)
    assert fetched.status == "completed"
    assert fetched.finished_at is not None


def test_list_for_project_filters_by_project(db, tmp_path):
    mgr = ExecutionManager(db)
    root_a = tmp_path / "proj-e"
    root_b = tmp_path / "proj-f"
    root_a.mkdir()
    root_b.mkdir()
    proj_a = mgr.get_or_create_project(root_a)
    proj_b = mgr.get_or_create_project(root_b)
    mgr.create(proj_a.id, "task-a1")
    mgr.create(proj_a.id, "task-a2")
    mgr.create(proj_b.id, "task-b1")

    a_execs = mgr.list_for_project(proj_a.id)
    b_execs = mgr.list_for_project(proj_b.id)
    assert len(a_execs) == 2
    assert len(b_execs) == 1
    assert all(e.project_id == proj_a.id for e in a_execs)


def test_latest_execution_project_returns_newest_execution_owner(db, tmp_path):
    """Inspector polling context must follow the newest producer project."""
    import time as _time

    mgr = ExecutionManager(db)
    root_a = tmp_path / "proj-latest-a"
    root_b = tmp_path / "proj-latest-b"
    root_a.mkdir()
    root_b.mkdir()
    proj_a = mgr.get_or_create_project(root_a)
    proj_b = mgr.get_or_create_project(root_b)

    mgr.create(proj_a.id, "older task")
    _time.sleep(0.01)
    newest = mgr.create(proj_b.id, "newer task")

    latest_project = mgr.latest_execution_project()
    assert latest_project is not None
    assert latest_project.id == newest.project_id
    assert latest_project.id == proj_b.id


def test_inspector_project_falls_back_to_current_project_without_executions(db, tmp_path, monkeypatch):
    """Empty databases still expose the Inspector process project."""
    mgr = ExecutionManager(db)
    root = tmp_path / "empty-project"
    root.mkdir()

    monkeypatch.chdir(root)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        project = mgr.inspector_project()

    assert project.root == str(root.resolve())


def test_inspector_project_uses_latest_execution_over_cwd(db, tmp_path, monkeypatch):
    """A cross-process agent project must not be hidden by Inspector CWD."""
    mgr = ExecutionManager(db)
    inspector_root = tmp_path / "inspector-project"
    agent_root = tmp_path / "agent-project"
    inspector_root.mkdir()
    agent_root.mkdir()
    agent_project = mgr.get_or_create_project(agent_root)
    mgr.create(agent_project.id, "agent task")

    monkeypatch.chdir(inspector_root)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        project = mgr.inspector_project()

    assert project.id == agent_project.id


# ── ProtectedAgent project wiring ────────────────────────────────────────────

def test_protected_agent_creates_execution(db, tmp_path, monkeypatch):
    from agentwall.interceptors.agent import ProtectedAgent
    from agentwall.security.engine import SecurityEngine
    from agentwall.core.types import DecisionType, Decision

    class _Stub:
        def run(self, *a, **kw):
            pass

    engine = SecurityEngine()
    monkeypatch.chdir(tmp_path)
    wall = ProtectedAgent(_Stub(), goal="test task", db=db, engine=engine)

    # execution must exist in DB
    mgr = ExecutionManager(db)
    ex = mgr.get(wall.execution_id)
    assert ex is not None
    assert ex.goal == "test task"
    assert ex.status == "running"
    wall.end_session()


def test_protected_agent_finishes_execution_on_end(db, tmp_path, monkeypatch):
    from agentwall.interceptors.agent import ProtectedAgent
    from agentwall.security.engine import SecurityEngine

    class _Stub:
        def run(self, *a, **kw):
            pass

    engine = SecurityEngine()
    monkeypatch.chdir(tmp_path)
    wall = ProtectedAgent(_Stub(), goal="finish test", db=db, engine=engine)
    eid = wall.execution_id
    wall.end_session()

    mgr = ExecutionManager(db)
    ex = mgr.get(eid)
    assert ex.status == "completed"
    assert ex.finished_at is not None


def test_project_isolation_separate_projects(db, tmp_path, monkeypatch):
    """Sessions from different projects don't mix."""
    from agentwall.interceptors.agent import ProtectedAgent
    from agentwall.security.engine import SecurityEngine

    class _Stub:
        def run(self, *a, **kw): pass

    engine = SecurityEngine()
    proj_a = tmp_path / "proj-a"
    proj_b = tmp_path / "proj-b"
    proj_a.mkdir()
    proj_b.mkdir()

    mgr = ExecutionManager(db)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""

        monkeypatch.chdir(proj_a)
        wall_a = ProtectedAgent(_Stub(), goal="task-a", db=db, engine=engine)
        wall_a.end_session()

        monkeypatch.chdir(proj_b)
        wall_b = ProtectedAgent(_Stub(), goal="task-b", db=db, engine=engine)
        wall_b.end_session()

    execs_a = mgr.list_for_project(mgr.get_or_create_project(proj_a).id)
    execs_b = mgr.list_for_project(mgr.get_or_create_project(proj_b).id)

    assert len(execs_a) == 1
    assert len(execs_b) == 1
    assert execs_a[0].id != execs_b[0].id


# ── Runtime validation regression (v0.2.4) ───────────────────────────────────

def test_default_db_path():
    """Database() with no args must resolve to ~/.agentwall/data.db."""
    from agentwall.storage.database import _DEFAULT_PATH
    assert _DEFAULT_PATH == Path.home() / ".agentwall" / "data.db"


def test_single_database_used(tmp_path):
    """Two Database() instances with same path share the same file."""
    db_path = tmp_path / "shared.db"
    db1 = Database(db_path)
    db2 = Database(db_path)
    mgr1 = ExecutionManager(db1)
    mgr2 = ExecutionManager(db2)
    root = tmp_path / "proj"
    root.mkdir()
    proj = mgr1.get_or_create_project(root)
    mgr1.create(proj.id, "task from db1")
    execs = mgr2.list_all()
    assert len(execs) == 1
    assert execs[0].goal == "task from db1"
    db1.close()
    db2.close()


def test_seven_consecutive_runs_all_completed(db, tmp_path, monkeypatch):
    """Regression: 7 consecutive runs must produce 7 completed executions and 0 running."""
    from agentwall.interceptors.agent import ProtectedAgent
    from agentwall.security.engine import SecurityEngine

    class _Stub:
        def run(self, *a, **kw): return "done"

    engine = SecurityEngine()
    monkeypatch.chdir(tmp_path)
    mgr = ExecutionManager(db)

    for i in range(7):
        with ProtectedAgent(_Stub(), goal=f"task {i+1}", db=db, engine=engine):
            pass  # context manager finalizes execution

    executions = mgr.list_all()
    assert len(executions) == 7
    assert all(e.status == "completed" for e in executions), [e.status for e in executions]
    assert all(e.finished_at is not None for e in executions)


def test_no_running_executions_after_clean_run(db, tmp_path, monkeypatch):
    """Active execution count must return to zero after agent exits normally."""
    from agentwall.interceptors.agent import ProtectedAgent
    from agentwall.security.engine import SecurityEngine

    class _Stub:
        def run(self, *a, **kw): return "done"

    engine = SecurityEngine()
    monkeypatch.chdir(tmp_path)
    mgr = ExecutionManager(db)

    with ProtectedAgent(_Stub(), goal="clean run", db=db, engine=engine):
        pass

    running = [e for e in mgr.list_all() if e.status == "running"]
    assert running == [], f"Orphaned running executions: {[e.id for e in running]}"


def test_finish_publishes_to_event_bus(db, tmp_path):
    """ExecutionManager.finish() must publish to EventBus for same-process Inspector updates."""
    from unittest.mock import MagicMock, patch
    root = tmp_path / "proj"
    root.mkdir()
    mgr = ExecutionManager(db)
    proj = mgr.get_or_create_project(root)
    ex = mgr.create(proj.id, "notify test")

    mock_bus = MagicMock()
    with patch("agentwall.inspector.event_bus.get_bus", return_value=mock_bus):
        mgr.finish(ex.id)

    mock_bus.publish.assert_called_once()


def test_execution_ordering_newest_first(db, tmp_path):
    """list_all() must return executions newest-first."""
    import time as _time
    root = tmp_path / "proj"
    root.mkdir()
    mgr = ExecutionManager(db)
    proj = mgr.get_or_create_project(root)
    e1 = mgr.create(proj.id, "first")
    _time.sleep(0.01)
    e2 = mgr.create(proj.id, "second")
    _time.sleep(0.01)
    e3 = mgr.create(proj.id, "third")
    rows = mgr.list_all()
    assert rows[0].id == e3.id
    assert rows[1].id == e2.id
    assert rows[2].id == e1.id
