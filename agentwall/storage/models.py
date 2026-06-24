from __future__ import annotations

import time
import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_goal: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    ended_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    events: Mapped[list[ToolEvent]] = relationship("ToolEvent", back_populates="session")
    goal_segments: Mapped[list[GoalSegment]] = relationship("GoalSegment", back_populates="session")


class ToolEvent(Base):
    __tablename__ = "tool_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    arguments: Mapped[dict] = mapped_column(JSON, nullable=False)
    timestamp: Mapped[float] = mapped_column(Float, default=time.time)
    tool_type: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str | None] = mapped_column(String, nullable=True)
    target: Mapped[str | None] = mapped_column(String, nullable=True)
    resource_category: Mapped[str | None] = mapped_column(String, nullable=True)

    session: Mapped[Session] = relationship("Session", back_populates="events")
    evaluation: Mapped[Evaluation | None] = relationship("Evaluation", back_populates="event", uselist=False)


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("tool_events.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    llm_used: Mapped[bool] = mapped_column(Boolean, default=False)
    timestamp: Mapped[float] = mapped_column(Float, default=time.time)
    alignment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    detector_hits: Mapped[list | None] = mapped_column(JSON, nullable=True)
    policy_matched: Mapped[str | None] = mapped_column(String, nullable=True)
    post_execution_risk: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_classification: Mapped[str | None] = mapped_column(String, nullable=True)
    result_detector_hits: Mapped[list | None] = mapped_column(JSON, nullable=True)
    result_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    event: Mapped[ToolEvent] = relationship("ToolEvent", back_populates="evaluation")


class GoalSegment(Base):
    __tablename__ = "goal_segments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), nullable=False)
    goal_text: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[float] = mapped_column(Float, default=time.time)
    ended_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    transition_reason: Mapped[str] = mapped_column(String, default="initial")

    session: Mapped[Session] = relationship("Session", back_populates="goal_segments")


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)


class ProviderSetting(Base):
    __tablename__ = "provider_settings"

    provider: Mapped[str] = mapped_column(String, primary_key=True)
    model: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
