from agentwall.core.event_manager import EventManager
from agentwall.core.session_manager import SessionManager
from agentwall.storage.database import Database


def _session(db: Database) -> str:
    mgr = SessionManager(db)
    s = mgr.create("Test session")
    return s.id


def test_record_event(db: Database):
    session_id = _session(db)
    mgr = EventManager(db)
    e = mgr.record(session_id, "read_file", {"path": "/home/user/login.tsx"})
    assert e.id
    assert e.tool_name == "read_file"
    assert e.arguments == {"path": "/home/user/login.tsx"}
    assert e.session_id == session_id


def test_record_evaluation(db: Database):
    session_id = _session(db)
    mgr = EventManager(db)
    e = mgr.record(session_id, "bash", {"cmd": "ls"})
    ev = mgr.record_evaluation(e.id, "warn", 60.0, "shell execution")
    assert ev.decision == "warn"
    assert ev.risk_score == 60.0
    assert ev.llm_used is False


def test_record_evaluation_llm_used(db: Database):
    session_id = _session(db)
    mgr = EventManager(db)
    e = mgr.record(session_id, "read_file", {"path": "~/.ssh/id_rsa"})
    ev = mgr.record_evaluation(e.id, "block", 80.0, "sensitive file", llm_used=True)
    assert ev.llm_used is True


def test_get_events(db: Database):
    session_id = _session(db)
    mgr = EventManager(db)
    mgr.record(session_id, "read_file", {"path": "a.py"})
    mgr.record(session_id, "write_file", {"path": "b.py"})
    events = mgr.get_events(session_id)
    assert len(events) == 2


def test_get_events_empty(db: Database):
    session_id = _session(db)
    mgr = EventManager(db)
    assert mgr.get_events(session_id) == []


def test_get_events_with_evaluations(db: Database):
    session_id = _session(db)
    mgr = EventManager(db)
    e = mgr.record(session_id, "read_file", {"path": "login.tsx"})
    mgr.record_evaluation(e.id, "allow", 5.0, "low risk")
    events = mgr.get_events_with_evaluations(session_id)
    assert len(events) == 1
    assert events[0].evaluation is not None
    assert events[0].evaluation.decision == "allow"
