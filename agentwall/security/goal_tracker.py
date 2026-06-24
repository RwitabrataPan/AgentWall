from __future__ import annotations

import threading

# Stop words and action verbs stripped when comparing resource tokens.
# Goal continuity is determined by the subject (resource), not the verb.
_STOP = {
    "fix", "build", "write", "create", "refactor", "test", "add", "remove",
    "debug", "deploy", "implement", "update", "delete", "check", "review",
    "read", "run", "install", "configure", "setup", "make", "get", "do",
    "change", "edit", "modify", "find", "investigate", "analyze", "generate",
    "send", "push", "pull", "fetch", "patch", "complete", "finish", "start",
    "the", "a", "an", "for", "in", "to", "of", "and", "or", "with", "on",
    "that", "this", "which", "is", "are", "was", "be", "been",
}


def _resource_tokens(goal: str) -> set[str]:
    return set(goal.lower().split()) - _STOP


class GoalTracker:
    """Tracks goal segments within a session.

    Transitions detected via two-signal heuristic — no LLM:
    1. Full token overlap < threshold AND
    2. Resource token overlap < threshold (strips action verbs and stop words)

    This prevents pure verb changes ("Build X" → "Write X") from creating
    new segments when the subject resource is unchanged.
    """

    # ponytail: two-signal heuristic, upgrade to cosine/embedding if precision matters
    _TRANSITION_THRESHOLD = 0.4

    def __init__(self, session_id: str, db: "Database", goal_ref: list[str]) -> None:
        self._session_id = session_id
        self._db = db
        self._goal_ref = goal_ref
        self._active_segment_id: str | None = None
        self._lock = threading.RLock()

    @property
    def active_goal(self) -> str:
        return self._goal_ref[0]

    def set_goal(self, goal: str, reason: str = "user_update") -> None:
        """Transition to goal. Closes current segment, opens new one."""
        if not goal:
            return
        with self._lock:
            if self._active_segment_id is not None:
                self._close_active()
            self._goal_ref[0] = goal
            self._open(goal, reason)

    def maybe_infer(self, new_input: str) -> bool:
        """Set or transition goal from new input. Returns True if goal changed."""
        if not new_input:
            return False
        with self._lock:
            current = self._goal_ref[0]
            if not current:
                self.set_goal(new_input, reason="inference")
                return True
            if self._is_transition(new_input, current):
                self.set_goal(new_input, reason="heuristic_transition")
                return True
        return False

    def _is_transition(self, new_goal: str, current_goal: str) -> bool:
        a = set(current_goal.lower().split())
        b = set(new_goal.lower().split())
        if not a or not b:
            return False
        full_overlap = len(a & b) / max(len(a), len(b))
        if full_overlap >= self._TRANSITION_THRESHOLD:
            return False
        # Full overlap is low — check resource tokens before deciding
        a_res = _resource_tokens(current_goal)
        b_res = _resource_tokens(new_goal)
        if not a_res or not b_res:
            return True  # no resource tokens to compare → treat as transition
        res_overlap = len(a_res & b_res) / max(len(a_res), len(b_res))
        return res_overlap < self._TRANSITION_THRESHOLD

    def _open(self, goal: str, reason: str) -> None:
        from agentwall.core.event_manager import EventManager
        self._active_segment_id = EventManager(self._db).create_goal_segment(
            self._session_id, goal, reason
        )

    def _close_active(self) -> None:
        if self._active_segment_id is None:
            return
        from agentwall.core.event_manager import EventManager
        EventManager(self._db).close_goal_segment(self._active_segment_id)
        self._active_segment_id = None
