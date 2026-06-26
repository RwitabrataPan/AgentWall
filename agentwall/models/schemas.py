from __future__ import annotations

from pydantic import BaseModel


class ProjectSchema(BaseModel):
    id: str
    name: str
    root: str
    created_at: float

    model_config = {"from_attributes": True}


class ExecutionSummarySchema(BaseModel):
    id: str
    project_id: str
    goal: str
    prompt: str | None = None
    framework: str | None = None
    model: str | None = None
    started_at: float
    finished_at: float | None = None
    status: str
    meta: dict = {}
    # aggregated
    event_count: int = 0
    threat_count: int = 0
    max_risk: float | None = None
    overall_decision: str | None = None

    model_config = {"from_attributes": True}


class SessionSchema(BaseModel):
    id: str
    user_goal: str
    created_at: float
    ended_at: float | None = None
    meta: dict = {}
    project_id: str | None = None
    execution_id: str | None = None

    model_config = {"from_attributes": True}


class SessionSummarySchema(SessionSchema):
    event_count: int = 0
    max_risk: float | None = None
    threat_count: int = 0


class EvaluationSchema(BaseModel):
    id: int
    event_id: int
    decision: str
    risk_score: float
    reason: str
    llm_used: bool
    timestamp: float
    alignment_score: float | None = None
    detector_hits: list[str] | None = None
    policy_matched: str | None = None
    post_execution_risk: float | None = None
    result_classification: str | None = None
    result_detector_hits: list[str] | None = None
    result_metadata: dict | None = None

    model_config = {"from_attributes": True}


class ToolEventSchema(BaseModel):
    id: int
    session_id: str
    tool_name: str
    arguments: dict
    timestamp: float
    tool_type: str | None = None
    action: str | None = None
    target: str | None = None
    resource_category: str | None = None
    evaluation: EvaluationSchema | None = None

    model_config = {"from_attributes": True}


class GoalSegmentSchema(BaseModel):
    id: str
    session_id: str
    goal_text: str
    started_at: float
    ended_at: float | None = None
    transition_reason: str
    confidence: float = 1.0

    model_config = {"from_attributes": True}


class PolicySchema(BaseModel):
    id: int
    name: str
    config: dict
    created_at: float
    enabled: bool = True
    priority: int = 0

    model_config = {"from_attributes": True}


class ProviderSettingSchema(BaseModel):
    provider: str
    model: str
    priority: int = 0
    enabled: bool = True
    config: dict = {}

    model_config = {"from_attributes": True}


class OverviewSchema(BaseModel):
    project_id: str | None = None
    project_name: str | None = None
    active_sessions: int
    total_sessions: int
    active_executions: int = 0
    total_executions: int = 0
    total_events: int
    threat_count: int
    risk_distribution: dict
    avg_risk: float | None = None
    current_provider: str | None = None
    current_model: str | None = None
    top_detectors: list[dict] = []
    top_policies: list[dict] = []
