"""Tests for policy templates and policy test endpoint."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentwall.inspector.deps import get_db, get_policy_engine
from agentwall.inspector.server import app
from agentwall.security.policy_engine import PolicyEngine
from agentwall.storage.database import Database


def _make_db():
    tmpdir = tempfile.mkdtemp(prefix="aw_pol_")
    db = Database(path=Path(tmpdir) / "test.db")
    return db, tmpdir


def _client(db: Database) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_policy_engine] = lambda: PolicyEngine(db)
    return TestClient(app)


@pytest.fixture
def client():
    db, tmpdir = _make_db()
    c = _client(db)
    yield c
    app.dependency_overrides.clear()
    db.close()
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_templates_returns_list(client):
    r = client.get("/api/policies/templates")
    assert r.status_code == 200
    templates = r.json()
    assert isinstance(templates, list)
    assert len(templates) >= 5
    names = [t["name"] for t in templates]
    assert "Block SSH Keys" in names
    assert "Protect .env Files" in names
    assert "Protect AWS Credentials" in names


def test_templates_have_config(client):
    r = client.get("/api/policies/templates")
    for tpl in r.json():
        assert "name" in tpl
        assert "config" in tpl
        assert "rules" in tpl["config"]
        assert isinstance(tpl["config"]["rules"], list)
        assert len(tpl["config"]["rules"]) > 0


def test_policy_test_ssh_block(client):
    r = client.post("/api/policies/test", json={
        "config": {
            "rules": [{"tool_type": "filesystem", "pattern": "*/.ssh/id_*", "decision": "block", "reason": "SSH key blocked"}]
        },
        "tool_type": "filesystem",
        "target": "/home/user/.ssh/id_rsa",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["matched"] is True
    assert data["decision"] == "block"
    assert "SSH key blocked" in data["reason"]


def test_policy_test_no_match(client):
    r = client.post("/api/policies/test", json={
        "config": {
            "rules": [{"tool_type": "filesystem", "pattern": "*/.ssh/id_*", "decision": "block", "reason": "SSH key blocked"}]
        },
        "tool_type": "filesystem",
        "target": "/home/user/README.md",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["matched"] is False
    assert data["decision"] is None


def test_policy_test_tool_type_mismatch(client):
    r = client.post("/api/policies/test", json={
        "config": {
            "rules": [{"tool_type": "database", "decision": "block", "reason": "DB blocked"}]
        },
        "tool_type": "filesystem",
        "target": "/anything",
    })
    assert r.status_code == 200
    assert r.json()["matched"] is False


def test_policy_test_warn_decision(client):
    r = client.post("/api/policies/test", json={
        "config": {
            "rules": [{"tool_type": "email", "action": "send", "decision": "warn", "reason": "Email needs approval"}]
        },
        "tool_type": "email",
        "action": "send",
        "target": "",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["matched"] is True
    assert data["decision"] == "warn"
