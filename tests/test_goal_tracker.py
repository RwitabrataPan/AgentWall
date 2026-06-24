from __future__ import annotations

import pytest

from agentwall.core.event_manager import EventManager
from agentwall.security.goal_tracker import GoalTracker


def _tracker(db, initial: str = "") -> GoalTracker:
    from agentwall.core.session_manager import SessionManager
    session = SessionManager(db).create(initial)
    ref: list[str] = [initial]
    return GoalTracker(session.id, db, ref), ref, session.id


def test_initial_set_creates_segment(db):
    tracker, ref, sid = _tracker(db)
    tracker.set_goal("fix login bug", reason="initial")
    assert ref[0] == "fix login bug"
    segs = EventManager(db).get_goal_segments(sid)
    assert len(segs) == 1
    assert segs[0].goal_text == "fix login bug"
    assert segs[0].transition_reason == "initial"
    assert segs[0].ended_at is None


def test_set_goal_updates_goal_ref(db):
    tracker, ref, _ = _tracker(db)
    tracker.set_goal("task one")
    assert ref[0] == "task one"


def test_transition_closes_old_segment_opens_new(db):
    tracker, ref, sid = _tracker(db)
    tracker.set_goal("fix login", reason="initial")
    tracker.set_goal("add billing page", reason="user_update")

    segs = EventManager(db).get_goal_segments(sid)
    assert len(segs) == 2
    assert segs[0].ended_at is not None  # first closed
    assert segs[1].ended_at is None       # second still open
    assert segs[1].goal_text == "add billing page"
    assert segs[1].transition_reason == "user_update"


def test_active_goal_property(db):
    tracker, ref, _ = _tracker(db, "initial goal")
    assert tracker.active_goal == "initial goal"
    tracker.set_goal("new goal")
    assert tracker.active_goal == "new goal"


def test_maybe_infer_sets_empty_goal(db):
    tracker, ref, sid = _tracker(db)
    changed = tracker.maybe_infer("fix authentication bug")
    assert changed is True
    assert ref[0] == "fix authentication bug"
    segs = EventManager(db).get_goal_segments(sid)
    assert len(segs) == 1
    assert segs[0].transition_reason == "inference"


def test_maybe_infer_no_change_when_goal_similar(db):
    tracker, ref, sid = _tracker(db)
    tracker.set_goal("fix the login bug")
    count_before = len(EventManager(db).get_goal_segments(sid))
    changed = tracker.maybe_infer("fix the login bug again")
    # High overlap → no transition
    assert changed is False
    assert ref[0] == "fix the login bug"
    assert len(EventManager(db).get_goal_segments(sid)) == count_before


def test_maybe_infer_transition_on_different_goal(db):
    tracker, ref, sid = _tracker(db)
    tracker.set_goal("fix login bug")
    changed = tracker.maybe_infer("write unit tests for billing module")
    assert changed is True
    assert ref[0] == "write unit tests for billing module"
    segs = EventManager(db).get_goal_segments(sid)
    assert len(segs) == 2
    assert segs[1].transition_reason == "heuristic_transition"


def test_maybe_infer_empty_input_no_change(db):
    tracker, ref, _ = _tracker(db)
    changed = tracker.maybe_infer("")
    assert changed is False
    assert ref[0] == ""


def test_set_goal_empty_string_no_op(db):
    tracker, ref, sid = _tracker(db)
    tracker.set_goal("real goal")
    tracker.set_goal("")  # should be ignored
    assert ref[0] == "real goal"
    segs = EventManager(db).get_goal_segments(sid)
    assert len(segs) == 1


def test_multiple_transitions_persist_all_segments(db):
    tracker, ref, sid = _tracker(db)
    tracker.set_goal("task A", reason="initial")
    tracker.set_goal("task B", reason="user_update")
    tracker.set_goal("task C", reason="user_update")
    segs = EventManager(db).get_goal_segments(sid)
    assert len(segs) == 3
    assert segs[0].ended_at is not None
    assert segs[1].ended_at is not None
    assert segs[2].ended_at is None
    assert [s.goal_text for s in segs] == ["task A", "task B", "task C"]


def test_is_transition_threshold(db):
    tracker, _, _ = _tracker(db)
    # Identical → no transition
    assert not tracker._is_transition("fix the login bug", "fix the login bug")
    # Totally different → transition
    assert tracker._is_transition("deploy kubernetes cluster", "fix login bug")
    # Empty → no transition (guard)
    assert not tracker._is_transition("", "fix login")
    assert not tracker._is_transition("fix login", "")


# ── Resource heuristic ────────────────────────────────────────────────────────

def test_verb_change_same_resource_not_transition(db):
    # "Build login API" → "Write login tests": verb changes, resource (login) stays
    tracker, _, _ = _tracker(db)
    assert not tracker._is_transition("Write login tests", "Build login API")


def test_resource_change_is_transition(db):
    # "Build login API" → "Create billing service": different resource
    tracker, _, _ = _tracker(db)
    assert tracker._is_transition("Create billing service", "Build login API")


def test_same_resource_different_verbs_no_new_segment(db):
    tracker, ref, sid = _tracker(db)
    tracker.set_goal("Build login API", reason="initial")
    changed = tracker.maybe_infer("Write login tests")
    assert changed is False
    segs = EventManager(db).get_goal_segments(sid)
    assert len(segs) == 1  # no new segment


def test_different_resource_creates_new_segment(db):
    tracker, ref, sid = _tracker(db)
    tracker.set_goal("Build login API", reason="initial")
    changed = tracker.maybe_infer("Create billing service")
    assert changed is True
    segs = EventManager(db).get_goal_segments(sid)
    assert len(segs) == 2


# ── Thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_set_goal_safe(db):
    import threading
    tracker, ref, sid = _tracker(db)
    tracker.set_goal("initial goal", reason="initial")

    errors = []

    def _set(goal):
        try:
            tracker.set_goal(goal, reason="user_update")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=_set, args=(f"goal {i}",)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Thread errors: {errors}"
    # One goal must be active (no corruption)
    assert ref[0] != ""


def test_concurrent_maybe_infer_safe(db):
    import threading
    tracker, ref, sid = _tracker(db)
    tracker.set_goal("initial goal", reason="initial")

    errors = []

    def _infer(text):
        try:
            tracker.maybe_infer(text)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=_infer, args=(f"deploy cluster {i}",)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
