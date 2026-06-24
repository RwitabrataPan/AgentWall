from agentwall.core.session_manager import SessionManager
from agentwall.storage.database import Database


def test_create_session(db: Database):
    mgr = SessionManager(db)
    s = mgr.create("Fix login bug")
    assert s.id
    assert s.user_goal == "Fix login bug"
    assert s.ended_at is None


def test_get_session(db: Database):
    mgr = SessionManager(db)
    created = mgr.create("Deploy feature")
    fetched = mgr.get(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.user_goal == "Deploy feature"


def test_get_missing_session(db: Database):
    mgr = SessionManager(db)
    assert mgr.get("nonexistent-id") is None


def test_end_session(db: Database):
    mgr = SessionManager(db)
    s = mgr.create("Test task")
    mgr.end(s.id)
    updated = mgr.get(s.id)
    assert updated is not None
    assert updated.ended_at is not None


def test_list_sessions(db: Database):
    mgr = SessionManager(db)
    mgr.create("Task 1")
    mgr.create("Task 2")
    sessions = mgr.list()
    assert len(sessions) == 2


def test_session_with_meta(db: Database):
    mgr = SessionManager(db)
    s = mgr.create("Task", meta={"framework": "langchain"})
    fetched = mgr.get(s.id)
    assert fetched is not None
    assert fetched.meta == {"framework": "langchain"}
