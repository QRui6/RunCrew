from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from runcrew.domain.activity import SourceProvider
from runcrew.domain.memory import AgentMemoryContext
from runcrew.domain.training_cycle import TrainingPlan


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TrainingExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", title="训练执行对照输入")

    plan_id: str = Field(min_length=1, description="RunCrew 内部训练计划 ID。")
    as_of: datetime = Field(description="知识截止时间，必须包含时区。")
    provider: SourceProvider | None = Field(
        default=None,
        description="可选活动来源过滤；多来源可能重复时应显式指定。",
    )
    date_tolerance_days: int = Field(default=1, ge=0, le=3)

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of 必须包含时区")
        return value


class TrainingExecutionDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", title="训练执行人工确认输入")

    plan_id: str = Field(min_length=1)
    base_revision: int = Field(ge=1)
    session_id: str = Field(min_length=1)
    decision: Literal["confirm_match", "mark_skipped", "clear_execution"]
    as_of: datetime = Field(description="确认时点，必须包含时区。")
    activity_id: str | None = None
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of 必须包含时区")
        return value

    @model_validator(mode="after")
    def activity_matches_decision(self) -> TrainingExecutionDecisionRequest:
        if self.decision == "confirm_match" and self.activity_id is None:
            raise ValueError("确认匹配必须提供 activity_id")
        if self.decision != "confirm_match" and self.activity_id is not None:
            raise ValueError("跳过或清除执行状态不能提供 activity_id")
        return self


class ExecutionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_id: str = Field(min_length=1)
    started_at: datetime
    date_difference_days: int = Field(ge=0)
    score: float = Field(ge=0, le=1)
    distance_ratio: float | None = Field(default=None, ge=0)
    duration_ratio: float | None = Field(default=None, ge=0)


class ExecutionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=180)
    type: Literal[
        "schedule",
        "date_proximity",
        "volume_comparison",
        "confirmed_link",
        "candidate_conflict",
        "missing_data",
    ]
    message: str = Field(min_length=1, max_length=300)
    values: dict[str, Any] = Field(default_factory=dict)
    rule_source: Literal[
        "active_plan",
        "normalized_activity",
        "user_confirmation",
        "runcrew_matching_rule",
        "missing_data_policy",
    ]


class SessionExecutionComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    scheduled_for: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    session_type: str = Field(min_length=1)
    outcome: Literal[
        "complete", "partial", "skipped", "unmatched", "upcoming", "rest"
    ]
    match_state: Literal["confirmed", "suggested", "ambiguous", "none", "broken_link"]
    suggested_activity_id: str | None = None
    candidates: list[ExecutionCandidate] = Field(default_factory=list, max_length=10)
    completion_ratio: float | None = Field(default=None, ge=0)
    confidence: Literal["high", "medium", "low"]
    requires_user_confirmation: bool
    evidence: list[ExecutionEvidence] = Field(min_length=1, max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def state_matches_confirmation(self) -> SessionExecutionComparison:
        if self.match_state == "suggested" and not self.requires_user_confirmation:
            raise ValueError("建议匹配必须等待用户确认")
        if self.match_state == "confirmed" and self.requires_user_confirmation:
            raise ValueError("已确认结果不能再次要求确认")
        if self.suggested_activity_id is not None and self.match_state not in {
            "suggested",
            "confirmed",
        }:
            raise ValueError("只有建议或已确认匹配可以包含活动 ID")
        return self


class TrainingExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", title="训练执行对照输出")

    schema_version: Literal["1.0"] = "1.0"
    ruleset_version: Literal["training-execution-rules/1.0"] = (
        "training-execution-rules/1.0"
    )
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    goal_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    plan_revision: int = Field(ge=1)
    as_of: datetime
    summary: str = Field(min_length=1, max_length=500)
    sessions: list[SessionExecutionComparison] = Field(max_length=14)
    unassigned_activity_ids: list[str] = Field(default_factory=list)
    memory_context: AgentMemoryContext | None = None

    @model_validator(mode="after")
    def memory_context_matches_execution(self) -> TrainingExecutionResult:
        if self.memory_context is not None and (
            self.memory_context.role != "execution"
            or self.memory_context.goal_id != self.goal_id
            or self.memory_context.as_of != self.as_of
        ):
            raise ValueError("Execution 结果包含了不属于当前任务的记忆上下文。")
        return self


class TrainingExecutionConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    plan_id: str = Field(min_length=1)
    base_revision: int = Field(ge=1)
    applied_revision: int | None = Field(default=None, ge=2)
    session_id: str = Field(min_length=1)
    decision: Literal["confirm_match", "mark_skipped", "clear_execution"]
    activity_id: str | None = None
    comment: str | None = Field(default=None, max_length=500)
    status: Literal["applied", "stale", "rejected"] = "applied"
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def decision_requires_matching_activity(self) -> TrainingExecutionConfirmation:
        if self.decision == "confirm_match" and self.activity_id is None:
            raise ValueError("确认匹配必须提供 activity_id")
        if self.decision != "confirm_match" and self.activity_id is not None:
            raise ValueError("跳过或清除执行状态不能提供 activity_id")
        if self.status == "applied" and self.applied_revision is None:
            raise ValueError("已应用确认必须记录 applied_revision")
        return self


class ExecutionConfirmationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", title="训练执行人工确认输出")

    plan: TrainingPlan
    confirmation: TrainingExecutionConfirmation
