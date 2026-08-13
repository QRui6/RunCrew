from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from runcrew.domain.activity import SourceProvider
from runcrew.domain.coach import CoachAgentRunRequest, CoachAgentRunResult
from runcrew.domain.training_cycle import (
    AcuteSymptom,
    DailyCheckIn,
    PlanChangeProposal,
    PlanSession,
    TrainingGoal,
    TrainingPlan,
    UserConfirmation,
)


class TrainingOperationsGoalView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: TrainingGoal
    active_plan: TrainingPlan | None
    latest_check_in: DailyCheckIn | None
    pending_proposals: list[PlanChangeProposal] = Field(default_factory=list)


class CoachRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    goal_id: str
    plan_id: str
    status: str
    recommendation: str | None = None
    required_user_action: str | None = None
    proposal_id: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


class TrainingOperationsBootstrap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    goals: list[TrainingOperationsGoalView]
    providers: list[SourceProvider] = Field(default_factory=list)
    recent_coach_runs: list[CoachRunSummary] = Field(default_factory=list)


class CheckInSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", title="训练运营身体反馈提交")

    day: date
    fatigue: int = Field(ge=1, le=5)
    soreness: int = Field(ge=0, le=10)
    sleep_quality: int = Field(ge=1, le=5)
    readiness: int | None = Field(default=None, ge=1, le=5)
    pain_area: str | None = Field(default=None, min_length=1, max_length=80)
    pain_severity: int = Field(default=0, ge=0, le=10)
    acute_symptoms: list[AcuteSymptom] = Field(default_factory=list, max_length=6)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def pain_requires_area(self) -> CheckInSubmission:
        if self.pain_severity > 0 and not self.pain_area:
            raise ValueError("疼痛程度大于0时必须填写疼痛部位")
        return self

    def to_domain(self) -> DailyCheckIn:
        return DailyCheckIn.model_validate(self.model_dump())


class CoachRunSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", title="训练运营 Coach 运行提交")

    goal_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    as_of: datetime
    provider: SourceProvider | None = None

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of 必须包含时区")
        return value

    def to_run_request(self) -> CoachAgentRunRequest:
        return CoachAgentRunRequest(
            goal_id=self.goal_id,
            plan_id=self.plan_id,
            as_of=self.as_of,
            provider=self.provider,
        )


CoachReviewStatus = Literal[
    "completed",
    "awaiting_user_confirmation",
    "blocked",
    "failed",
    "approved",
    "rejected",
    "stale",
]


class CoachRunAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    goal_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    status: CoachReviewStatus
    run_request: CoachAgentRunRequest
    result: CoachAgentRunResult
    planning_output_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    proposal_id: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


class CoachRunDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Coach 计划草案审核提交")

    decision: Literal["approve", "reject"]
    comment: str | None = Field(default=None, max_length=500)


class CoachRunDecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Coach 计划草案审核结果")

    outcome: Literal["approved", "rejected", "stale"]
    audit: CoachRunAudit
    plan: TrainingPlan
    proposal: PlanChangeProposal | None = None
    confirmation: UserConfirmation | None = None


class CoachRunView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit: CoachRunAudit
    plan_sessions: list[PlanSession]
