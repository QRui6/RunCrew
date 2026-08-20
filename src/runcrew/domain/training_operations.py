from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from runcrew.domain.activity import SourceProvider
from runcrew.domain.coach import CoachAgentRunRequest, CoachAgentRunResult
from runcrew.domain.memory import (
    AthletePreference,
    WeeklyTrainingMemory,
    WeeklyTrainingMemoryBuildRequest,
    WeeklyTrainingMemoryBuildResult,
)
from runcrew.domain.training_cycle import (
    AcuteSymptom,
    DailyCheckIn,
    EventType,
    PlanChangeProposal,
    PlanSession,
    TrainingGoal,
    TrainingPlan,
    UserConfirmation,
    Weekday,
)
from runcrew.domain.training_execution import (
    TrainingExecutionDecisionRequest,
    TrainingExecutionResult,
)
from runcrew.domain.training_planning import TrainingPlanningResult, WeeklyPlanDraftRequest


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
    athlete_preferences: list[AthletePreference] = Field(default_factory=list)


class TrainingGoalSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", title="训练目标创建输入")

    name: str = Field(min_length=1, max_length=80)
    event_type: EventType
    target_date: date
    target_time_seconds: int | None = Field(default=None, gt=0)
    available_weekdays: list[Weekday] = Field(min_length=1, max_length=7)

    def to_domain(self) -> TrainingGoal:
        return TrainingGoal.model_validate(self.model_dump())


class WeeklyPlanDraftSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", title="网页周计划草案输入")

    week_start: date
    as_of: datetime
    lookback_days: int = Field(default=28, ge=14, le=56)
    provider: SourceProvider | None = None

    @field_validator("week_start")
    @classmethod
    def require_monday(cls, value: date) -> date:
        if value.weekday() != 0:
            raise ValueError("训练周必须从星期一开始")
        return value

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of 必须包含时区")
        return value

    def to_request(self, goal_id: str) -> WeeklyPlanDraftRequest:
        return WeeklyPlanDraftRequest(goal_id=goal_id, **self.model_dump())


class WeeklyTrainingMemoryBuildSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", title="周训练记忆生成输入")

    week_start: date
    as_of: datetime

    @field_validator("week_start")
    @classmethod
    def require_memory_monday(cls, value: date) -> date:
        if value.weekday() != 0:
            raise ValueError("周训练记忆必须从星期一开始。")
        return value

    @field_validator("as_of")
    @classmethod
    def require_memory_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of 必须包含时区。")
        return value

    def to_request(self, goal_id: str) -> WeeklyTrainingMemoryBuildRequest:
        return WeeklyTrainingMemoryBuildRequest(goal_id=goal_id, **self.model_dump())


class WeeklyPlanActivationRequest(WeeklyPlanDraftSubmission):
    model_config = ConfigDict(extra="forbid", title="周计划草案确认输入")

    expected_input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    def to_request(self, goal_id: str) -> WeeklyPlanDraftRequest:
        return WeeklyPlanDraftRequest(
            goal_id=goal_id,
            **self.model_dump(exclude={"expected_input_hash"}),
        )


class WeekProgressSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    due_sessions: int = Field(ge=0)
    confirmed_sessions: int = Field(ge=0)
    pending_confirmation_sessions: int = Field(ge=0)
    skipped_sessions: int = Field(ge=0)
    upcoming_sessions: int = Field(ge=0)
    completion_rate: float | None = Field(default=None, ge=0, le=1)
    planned_duration_seconds: int = Field(ge=0)
    check_in_days: int = Field(ge=0)
    headline: str = Field(min_length=1, max_length=200)


class TrainingWeekView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    goal: TrainingGoal
    plan: TrainingPlan | None
    execution: TrainingExecutionResult | None
    today_session_ids: list[str] = Field(default_factory=list)
    next_session_id: str | None = None
    progress: WeekProgressSummary | None = None
    recent_memories: list[WeeklyTrainingMemory] = Field(default_factory=list)


class WeeklyPlanActivationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: TrainingPlan
    replayed_draft: TrainingPlanningResult


class ExecutionDecisionSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", title="网页训练执行确认输入")

    base_revision: int = Field(ge=1)
    session_id: str = Field(min_length=1)
    decision: Literal["confirm_match", "mark_skipped", "clear_execution"]
    as_of: datetime
    activity_id: str | None = None
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of 必须包含时区")
        return value

    def to_request(self, plan_id: str) -> TrainingExecutionDecisionRequest:
        return TrainingExecutionDecisionRequest(plan_id=plan_id, **self.model_dump())


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
