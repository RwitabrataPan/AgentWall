from __future__ import annotations

import time

from ..storage.database import Database
from ..storage.models import Evaluation, GoalSegment, ToolEvent


class EventManager:
    def __init__(self, db: Database) -> None:
        self._db = db

    def record(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict,
        *,
        tool_type: str | None = None,
        action: str | None = None,
        target: str | None = None,
        resource_category: str | None = None,
    ) -> ToolEvent:
        with self._db.session() as db:
            row = ToolEvent(
                session_id=session_id,
                tool_name=tool_name,
                arguments=arguments,
                timestamp=time.time(),
                tool_type=tool_type,
                action=action,
                target=target,
                resource_category=resource_category,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            db.expunge(row)
        return row

    def record_evaluation(
        self,
        event_id: int,
        decision: str,
        risk_score: float,
        reason: str,
        llm_used: bool = False,
        alignment_score: float | None = None,
        detector_hits: list[str] | None = None,
        policy_matched: str | None = None,
    ) -> Evaluation:
        with self._db.session() as db:
            row = Evaluation(
                event_id=event_id,
                decision=decision,
                risk_score=risk_score,
                reason=reason,
                llm_used=llm_used,
                timestamp=time.time(),
                alignment_score=alignment_score,
                detector_hits=detector_hits,
                policy_matched=policy_matched,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            db.expunge(row)
        return row

    def update_evaluation_post(
        self,
        event_id: int,
        post_execution_risk: float,
        result_classification: str,
        result_detector_hits: list[str],
        result_metadata: dict,
    ) -> None:
        with self._db.session() as db:
            db.query(Evaluation).filter(Evaluation.event_id == event_id).update({
                "post_execution_risk": post_execution_risk,
                "result_classification": result_classification,
                "result_detector_hits": result_detector_hits,
                "result_metadata": result_metadata,
            })
            db.commit()

    def get_events(self, session_id: str) -> list[ToolEvent]:
        with self._db.session() as db:
            rows = (
                db.query(ToolEvent)
                .filter(ToolEvent.session_id == session_id)
                .order_by(ToolEvent.timestamp)
                .all()
            )
            for r in rows:
                db.expunge(r)
            return rows

    def get_events_with_evaluations(self, session_id: str) -> list[ToolEvent]:
        from sqlalchemy.orm import joinedload

        with self._db.session() as db:
            rows = (
                db.query(ToolEvent)
                .options(joinedload(ToolEvent.evaluation))
                .filter(ToolEvent.session_id == session_id)
                .order_by(ToolEvent.timestamp)
                .all()
            )
            for r in rows:
                if r.evaluation:
                    db.expunge(r.evaluation)
                db.expunge(r)
            return rows

    def create_goal_segment(self, session_id: str, goal: str, reason: str = "initial") -> str:
        with self._db.session() as db:
            seg = GoalSegment(
                session_id=session_id,
                goal_text=goal,
                started_at=time.time(),
                transition_reason=reason,
            )
            db.add(seg)
            db.commit()
            db.refresh(seg)
            seg_id = seg.id
        return seg_id

    def close_goal_segment(self, segment_id: str) -> None:
        with self._db.session() as db:
            db.query(GoalSegment).filter(GoalSegment.id == segment_id).update(
                {"ended_at": time.time()}
            )
            db.commit()

    def get_goal_segments(self, session_id: str) -> list[GoalSegment]:
        with self._db.session() as db:
            rows = (
                db.query(GoalSegment)
                .filter(GoalSegment.session_id == session_id)
                .order_by(GoalSegment.started_at)
                .all()
            )
            for r in rows:
                db.expunge(r)
            return rows
