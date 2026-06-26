"""Inspector REST API route tests using FastAPI TestClient."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from agentwall.core.event_manager import EventManager
from agentwall.core.execution_manager import ExecutionManager
from agentwall.core.session_manager import SessionManager
from agentwall.inspector.deps import get_db, get_event_manager, get_execution_manager, get_policy_engine, get_session_manager
from agentwall.inspector.server import app
from agentwall.security.policy_engine import PolicyEngine
from agentwall.storage.database import Database


# ── Fixture: isolated DB per test ─────────────────────────────────────────────

def _make_test_db():
    tmpdir = tempfile.mkdtemp(prefix="aw_insp_")
    db = Database(path=Path(tmpdir) / "test.db")
    return db, tmpdir


def _client(db: Database) -> TestClient:
    """Return a TestClient with the given DB injected into all deps."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_session_manager] = lambda: SessionManager(db)
    app.dependency_overrides[get_event_manager] = lambda: EventManager(db)
    app.dependency_overrides[get_policy_engine] = lambda: PolicyEngine(db)
    app.dependency_overrides[get_execution_manager] = lambda: ExecutionManager(db)
    return TestClient(app)


# ── Health ─────────────────────────────────────────────────────────────────────

def test_health():
    db, tmpdir = _make_test_db()
    try:
        c = _client(db)
        r = c.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Overview ───────────────────────────────────────────────────────────────────

def test_overview_empty():
    db, tmpdir = _make_test_db()
    try:
        r = _client(db).get("/api/overview")
        assert r.status_code == 200
        d = r.json()
        assert d["total_sessions"] == 0
        assert d["total_events"] == 0
        assert d["threat_count"] == 0
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_overview_counts_sessions():
    db, tmpdir = _make_test_db()
    try:
        SessionManager(db).create("goal A")
        SessionManager(db).create("goal B")
        r = _client(db).get("/api/overview")
        assert r.json()["total_sessions"] == 2
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Sessions ───────────────────────────────────────────────────────────────────

def test_list_sessions_empty():
    db, tmpdir = _make_test_db()
    try:
        r = _client(db).get("/api/sessions")
        assert r.status_code == 200
        assert r.json() == []
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_get_session():
    db, tmpdir = _make_test_db()
    try:
        sess = SessionManager(db).create("fix login bug")
        r = _client(db).get(f"/api/sessions/{sess.id}")
        assert r.status_code == 200
        assert r.json()["user_goal"] == "fix login bug"
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_get_session_not_found():
    db, tmpdir = _make_test_db()
    try:
        r = _client(db).get("/api/sessions/no-such-id")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_end_session():
    db, tmpdir = _make_test_db()
    try:
        sess = SessionManager(db).create("task")
        c = _client(db)
        r = c.post(f"/api/sessions/{sess.id}/end")
        assert r.status_code == 200
        r2 = c.get(f"/api/sessions/{sess.id}")
        assert r2.json()["ended_at"] is not None
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_list_sessions_includes_summary_fields():
    db, tmpdir = _make_test_db()
    try:
        SessionManager(db).create("goal")
        r = _client(db).get("/api/sessions")
        s = r.json()[0]
        assert "event_count" in s
        assert "max_risk" in s
        assert "threat_count" in s
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Events ─────────────────────────────────────────────────────────────────────

def test_list_events_empty():
    db, tmpdir = _make_test_db()
    try:
        sess = SessionManager(db).create("goal")
        r = _client(db).get(f"/api/sessions/{sess.id}/events")
        assert r.status_code == 200
        assert r.json() == []
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_list_events_returns_evaluation():
    db, tmpdir = _make_test_db()
    try:
        sess = SessionManager(db).create("goal")
        mgr = EventManager(db)
        ev = mgr.record(
            session_id=sess.id, tool_name="read_file",
            arguments={"path": "/app/main.py"}, tool_type="filesystem",
            action="read", target="/app/main.py", resource_category="code",
        )
        mgr.record_evaluation(
            event_id=ev.id, decision="allow", risk_score=10.0,
            reason="low risk", llm_used=False, alignment_score=None,
            detector_hits=[], policy_matched=None,
        )
        r = _client(db).get(f"/api/sessions/{sess.id}/events")
        events = r.json()
        assert len(events) == 1
        assert events[0]["tool_name"] == "read_file"
        assert events[0]["evaluation"]["decision"] == "allow"
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Goals ──────────────────────────────────────────────────────────────────────

def test_list_goals_empty():
    db, tmpdir = _make_test_db()
    try:
        sess = SessionManager(db).create("goal")
        r = _client(db).get(f"/api/sessions/{sess.id}/goals")
        assert r.status_code == 200
        assert r.json() == []
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_list_goals_returns_segments():
    db, tmpdir = _make_test_db()
    try:
        sess = SessionManager(db).create("initial")
        mgr = EventManager(db)
        mgr.create_goal_segment(sess.id, "fix login bug", "initial")
        r = _client(db).get(f"/api/sessions/{sess.id}/goals")
        goals = r.json()
        assert len(goals) == 1
        assert goals[0]["goal_text"] == "fix login bug"
        assert goals[0]["transition_reason"] == "initial"
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Policies ───────────────────────────────────────────────────────────────────

def test_list_policies_empty():
    db, tmpdir = _make_test_db()
    try:
        r = _client(db).get("/api/policies")
        assert r.status_code == 200
        assert r.json() == []
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_create_policy():
    db, tmpdir = _make_test_db()
    try:
        c = _client(db)
        r = c.post("/api/policies", json={
            "name": "block-ssh",
            "config": {"rules": [{"pattern": "*/.ssh/*", "decision": "block"}]},
            "priority": 10,
        })
        assert r.status_code == 201
        d = r.json()
        assert d["name"] == "block-ssh"
        assert d["priority"] == 10
        assert d["enabled"] is True
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_create_policy_duplicate_returns_400():
    db, tmpdir = _make_test_db()
    try:
        c = _client(db)
        body = {"name": "p", "config": {"rules": []}}
        c.post("/api/policies", json=body)
        r = c.post("/api/policies", json=body)
        assert r.status_code == 400
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_update_policy():
    db, tmpdir = _make_test_db()
    try:
        c = _client(db)
        c.post("/api/policies", json={"name": "p", "config": {"rules": []}})
        r = c.put("/api/policies/p", json={"config": {"rules": [{"decision": "allow"}]}})
        assert r.status_code == 200
        assert r.json()["config"]["rules"][0]["decision"] == "allow"
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_update_policy_not_found():
    db, tmpdir = _make_test_db()
    try:
        r = _client(db).put("/api/policies/no-such", json={"config": {}})
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_set_priority():
    db, tmpdir = _make_test_db()
    try:
        c = _client(db)
        c.post("/api/policies", json={"name": "p", "config": {"rules": []}})
        r = c.patch("/api/policies/p/priority", json={"priority": 99})
        assert r.status_code == 200
        policies = c.get("/api/policies").json()
        assert policies[0]["priority"] == 99
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_enable_disable_policy():
    db, tmpdir = _make_test_db()
    try:
        c = _client(db)
        c.post("/api/policies", json={"name": "p", "config": {"rules": []}})
        r = c.post("/api/policies/p/disable")
        assert r.status_code == 200
        r = c.post("/api/policies/p/enable")
        assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_delete_policy():
    db, tmpdir = _make_test_db()
    try:
        c = _client(db)
        c.post("/api/policies", json={"name": "p", "config": {"rules": []}})
        r = c.delete("/api/policies/p")
        assert r.status_code == 200
        assert c.get("/api/policies").json() == []
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Export ─────────────────────────────────────────────────────────────────────

def test_export_json_empty():
    db, tmpdir = _make_test_db()
    try:
        r = _client(db).get("/api/export")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        assert r.json() == []
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_export_csv():
    db, tmpdir = _make_test_db()
    try:
        r = _client(db).get("/api/export?format=csv")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "event_id" in r.text  # CSV header row
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_export_invalid_format():
    db, tmpdir = _make_test_db()
    try:
        r = _client(db).get("/api/export?format=xml")
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Executions ─────────────────────────────────────────────────────────────────

def test_list_executions_empty():
    db, tmpdir = _make_test_db()
    try:
        r = _client(db).get("/api/executions")
        assert r.status_code == 200
        assert r.json() == []
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_list_executions_filters_by_current_project():
    """GET /api/executions returns only the current project's executions."""
    db, tmpdir = _make_test_db()
    try:
        mgr = ExecutionManager(db)
        root_a = Path(tmpdir) / "proj-a"
        root_b = Path(tmpdir) / "proj-b"
        root_a.mkdir()
        root_b.mkdir()
        proj_a = mgr.get_or_create_project(root_a)
        proj_b = mgr.get_or_create_project(root_b)
        mgr.create(proj_a.id, "task from project a")
        mgr.create(proj_b.id, "task from project b")

        # Inspector launched from root_a — only proj_a executions appear
        with patch("agentwall.core.execution_manager.detect_project_root", return_value=root_a):
            r = _client(db).get("/api/executions")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["project_id"] == proj_a.id
        assert data[0]["goal"] == "task from project a"
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_list_executions_excludes_other_projects():
    """Executions from projects other than the current one do not appear."""
    db, tmpdir = _make_test_db()
    try:
        mgr = ExecutionManager(db)
        agent_root = Path(tmpdir) / "demo-project"
        inspector_root = Path(tmpdir) / "agentwall-repo"
        agent_root.mkdir()
        inspector_root.mkdir()
        agent_proj = mgr.get_or_create_project(agent_root)
        mgr.create(agent_proj.id, "agent task")

        # Inspector launched from inspector_root — agent's execution must NOT appear
        with patch("agentwall.core.execution_manager.detect_project_root", return_value=inspector_root):
            r = _client(db).get("/api/executions")
        assert r.status_code == 200
        assert r.json() == []
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_list_executions_newest_first():
    db, tmpdir = _make_test_db()
    try:
        import time as _time
        mgr = ExecutionManager(db)
        root = Path(tmpdir) / "proj"
        root.mkdir()
        proj = mgr.get_or_create_project(root)
        e1 = mgr.create(proj.id, "first task")
        _time.sleep(0.01)
        e2 = mgr.create(proj.id, "second task")
        with patch("agentwall.core.execution_manager.detect_project_root", return_value=root):
            r = _client(db).get("/api/executions")
        ids = [e["id"] for e in r.json()]
        assert ids[0] == e2.id
        assert ids[1] == e1.id
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_get_execution_by_id():
    db, tmpdir = _make_test_db()
    try:
        mgr = ExecutionManager(db)
        root = Path(tmpdir) / "proj"
        root.mkdir()
        proj = mgr.get_or_create_project(root)
        ex = mgr.create(proj.id, "deploy model", framework="langchain")
        r = _client(db).get(f"/api/executions/{ex.id}")
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == ex.id
        assert d["goal"] == "deploy model"
        assert d["framework"] == "langchain"
        assert d["status"] == "running"
        assert d["event_count"] == 0
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_get_execution_not_found():
    db, tmpdir = _make_test_db()
    try:
        r = _client(db).get("/api/executions/no-such-id")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)




def test_execution_sessions_endpoint():
    db, tmpdir = _make_test_db()
    try:
        mgr = ExecutionManager(db)
        root = Path(tmpdir) / "proj"
        root.mkdir()
        proj = mgr.get_or_create_project(root)
        ex = mgr.create(proj.id, "task")
        SessionManager(db).create("task", project_id=proj.id, execution_id=ex.id)
        r = _client(db).get(f"/api/executions/{ex.id}/sessions")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["execution_id"] == ex.id
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Execution lifecycle regression (v0.2.4) ────────────────────────────────────

def test_execution_finalized_shows_completed_status():
    """Regression: finished execution must appear as 'completed' via the API."""
    db, tmpdir = _make_test_db()
    try:
        mgr = ExecutionManager(db)
        root = Path(tmpdir) / "proj"
        root.mkdir()
        proj = mgr.get_or_create_project(root)
        ex = mgr.create(proj.id, "run pipeline")
        mgr.finish(ex.id)
        r = _client(db).get(f"/api/executions/{ex.id}")
        assert r.status_code == 200
        assert r.json()["status"] == "completed"
        assert r.json()["finished_at"] is not None
    finally:
        app.dependency_overrides.clear()
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


