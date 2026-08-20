from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from runcrew.domain.activity import SourceProvider
from runcrew.domain.recovery_assessment import RecoveryPlanAction
from runcrew.domain.training_cycle import PlanSession, PlanSessionPatch


class WeeklyPlanDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", title="跑步周计划草案输入")

    goal_id: str = Field(min_length=1, description="RunCrew 内部训练目标 ID。")
    week_start: date = Field(description="待规划训练周的周一日期。")
    as_of: datetime = Field(description="生成草案时的知识截止时间，必须包含时区。")
    lookback_days: int = Field(default=28, ge=14, le=56)
    provider: SourceProvider | None = Field(
        default=None,
        description="可选活动来源过滤；多来源可能重复时应显式指定。",
    )

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


class PlanAdjustmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", title="恢复建议转计划调整输入")

    goal_id: str = Field(min_length=1, description="RunCrew 内部训练目标 ID。")
    assessed_at: datetime = Field(description="恢复评估时间，必须包含时区。")
    recovery_input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    recovery_recommendation: Literal[
        "proceed",
        "reduce",
        "rest",
        "seek_professional_help",
        "insufficient_data",
    ]
    plan_action: RecoveryPlanAction
    evidence_refs: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("assessed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("assessed_at 必须包含时区")
        return value

    @model_validator(mode="after")
    def recommendation_matches_action(self) -> PlanAdjustmentRequest:
        expected = {
            "proceed": {"keep"},
            "reduce": {"ask_plan_agent_to_reduce", "wait_for_more_data"},
            "rest": {
                "ask_plan_agent_to_replace_with_rest",
                "wait_for_more_data",
            },
            "seek_professional_help": {"hold_until_professional_review"},
            "insufficient_data": {"wait_for_more_data"},
        }
        if self.plan_action.action not in expected[self.recovery_recommendation]:
            raise ValueError("恢复建议与 plan_action 不一致")
        return self


class PlanningEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=160)
    type: Literal[
        "goal",
        "availability",
        "athlete_preference",
        "training_history",
        "current_plan",
        "recovery_action",
        "engineering_rule",
        "missing_data",
    ]
    message: str = Field(min_length=1, max_length=300)
    values: dict[str, Any] = Field(default_factory=dict)
    rule_source: Literal[
        "user_goal",
        "confirmed_athlete_preference",
        "normalized_activity",
        "active_plan",
        "recovery_assessment",
        "runcrew_conservative_rule",
        "missing_data_policy",
    ]


class WeeklyPlanDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str = Field(min_length=1)
    week_start: date
    sessions: list[PlanSession] = Field(min_length=1, max_length=7)
    total_duration_seconds: int = Field(ge=0)
    rationale: str = Field(min_length=1, max_length=500)
    requires_user_confirmation: Literal[True] = True


class PlanChangeProposalDraft(BaseModel):
    """可交给 TrainingCycleService 的提案参数，不代表已保存或已批准。"""

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1)
    base_revision: int = Field(ge=1)
    proposed_by: Literal["plan_agent"] = "plan_agent"
    reason: str = Field(min_length=1, max_length=500)
    changes: list[PlanSessionPatch] = Field(min_length=1, max_length=14)
    evidence_refs: list[str] = Field(default_factory=list, max_length=30)
    requires_user_confirmation: Literal[True] = True


class RecoveryAssessmentSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    recommendation: Literal[
        "proceed",
        "reduce",
        "rest",
        "seek_professional_help",
        "insufficient_data",
    ]
    plan_action: RecoveryPlanAction


class TrainingPlanningResult(BaseModel):
    model_config = ConfigDict(extra="forbid", title="跑步计划草案或调整提案输出")

    schema_version: Literal["1.0"] = "1.0"
    ruleset_version: Literal["training-plan-rules/1.0"] = (
        "training-plan-rules/1.0"
    )
    operation: Literal["draft_week", "adjust_from_recovery"]
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    goal_id: str = Field(min_length=1)
    status: Literal["ready", "no_change", "blocked"]
    summary: str = Field(min_length=1, max_length=500)
    weekly_plan_draft: WeeklyPlanDraft | None = None
    change_proposal_draft: PlanChangeProposalDraft | None = None
    source_recovery_assessment: RecoveryAssessmentSnapshot | None = None
    evidence: list[PlanningEvidence] = Field(min_length=1, max_length=30)
    missing_data: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def payload_matches_status(self) -> TrainingPlanningResult:
        payload_count = sum(
            item is not None
            for item in (self.weekly_plan_draft, self.change_proposal_draft)
        )
        if self.status == "ready" and payload_count != 1:
            raise ValueError("ready 结果必须且只能包含一种计划草案")
        if self.status != "ready" and payload_count:
            raise ValueError("非 ready 结果不能包含计划草案")
        if self.operation == "draft_week" and self.change_proposal_draft is not None:
            raise ValueError("draft_week 不能返回变更提案")
        if (
            self.operation == "adjust_from_recovery"
            and self.weekly_plan_draft is not None
        ):
            raise ValueError("adjust_from_recovery 不能返回周计划草案")
        return self
