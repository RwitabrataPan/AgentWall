from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentwall.core.types import RuntimeEvent
    from agentwall.storage.database import Database

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


def _synthesize_goal_from_event(event: "RuntimeEvent") -> str:
    """Build a human-readable candidate goal description from a high-signal event."""
    from agentwall.core.types import ResourceCategory, ToolAction, ToolType

    parts: list[str] = []
    if event.resource_category == ResourceCategory.CREDENTIALS:
        parts.append("access credentials")
    elif event.resource_category == ResourceCategory.SYSTEM:
        parts.append("access system files")

    if event.action == ToolAction.SEND and event.tool_type == ToolType.EMAIL:
        parts.append("send email")
    elif event.action in (ToolAction.SEND, ToolAction.REQUEST) and event.tool_type == ToolType.API:
        parts.append("upload data externally")
    elif event.action == ToolAction.DELETE:
        parts.append("delete resources")

    if event.target and parts:
        parts.append(f"({event.target})")

    return " ".join(parts)


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

    def set_goal(self, goal: str, reason: str = "user_update", confidence: float = 1.0) -> None:
        """Transition to goal. Closes current segment, opens new one."""
        if not goal:
            return
        with self._lock:
            if self._active_segment_id is not None:
                self._close_active()
            self._goal_ref[0] = goal
            self._open(goal, reason, confidence)

    def maybe_infer(self, new_input: str) -> bool:
        """Set or transition goal from new input. Returns True if goal changed."""
        if not new_input:
            return False
        with self._lock:
            current = self._goal_ref[0]
            if not current:
                self.set_goal(new_input, reason="inference", confidence=0.9)
                return True
            if self._is_transition(new_input, current):
                self.set_goal(new_input, reason="heuristic_transition", confidence=0.8)
                return True
        return False

    # ── Public v0.2 API ───────────────────────────────────────────────────────

    def infer_initial_goal(self, text: str, confidence: float = 0.9) -> bool:
        """Set the initial goal from user input. Returns True if goal was set."""
        if not text:
            return False
        with self._lock:
            if not self._goal_ref[0]:
                self.set_goal(text, reason="inference", confidence=confidence)
                return True
        return False

    def detect_transition(self, new_goal: str) -> bool:
        """Return True if *new_goal* represents a transition from the current goal."""
        return self._is_transition(new_goal, self._goal_ref[0])

    def detect_goal_drift(self, event: "RuntimeEvent") -> list[str]:
        """Return drift signal labels if *event* is inconsistent with current goal."""
        from agentwall.security.detectors import GoalDriftDetector
        return GoalDriftDetector().detect(event, [])

    def create_goal_segment(
        self, goal: str, reason: str = "user_update", confidence: float = 1.0
    ) -> None:
        """Explicitly create a new goal segment (public alias for set_goal)."""
        self.set_goal(goal, reason=reason, confidence=confidence)

    def infer_runtime_goal(self, event: "RuntimeEvent") -> bool:
        """Analyze a tool event to detect runtime goal shift.

        Called after each tool execution. Synthesizes a candidate goal from
        high-signal events (credential access, exfiltration) and creates a
        new goal segment if the pattern diverges from the current goal.
        Returns True if a new goal segment was created.
        """
        drift_signals = self.detect_goal_drift(event)
        if not drift_signals:
            return False

        candidate = _synthesize_goal_from_event(event)
        if not candidate:
            return False

        with self._lock:
            current = self._goal_ref[0]
            if not current or self._is_transition(candidate, current):
                self.set_goal(candidate, reason="runtime_inference", confidence=0.7)
                return True
        return False

    # ── Internal ──────────────────────────────────────────────────────────────

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

    def _open(self, goal: str, reason: str, confidence: float = 1.0) -> None:
        from agentwall.core.event_manager import EventManager
        self._active_segment_id = EventManager(self._db).create_goal_segment(
            self._session_id, goal, reason, confidence
        )

    def _close_active(self) -> None:
        if self._active_segment_id is None:
            return
        from agentwall.core.event_manager import EventManager
        EventManager(self._db).close_goal_segment(self._active_segment_id)
        self._active_segment_id = None
