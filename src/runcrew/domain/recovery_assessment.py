from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from runcrew.domain.activity import SourceProvider


class RecoveryAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", title="跑步恢复风险评估输入")

    goal_id: str = Field(min_length=1, description="RunCrew 内部训练目标 ID。")
    assessed_at: datetime = Field(description="评估时间，必须包含时区。")
    lookback_days: int = Field(default=14, ge=14, le=28)
    provider: SourceProvider | None = Field(
        default=None,
        description="可选活动来源过滤；多来源可能重复时应显式指定。",
    )

    @field_validator("assessed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("评估时间必须包含时区")
        return value


class RecoveryWindowMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_count: int = Field(ge=0)
    distance_meters: float = Field(ge=0)
    duration_seconds: int = Field(ge=0)
    training_load_total: float | None = Field(default=None, ge=0)
    training_load_coverage: float = Field(ge=0, le=1)


class RecoveryEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    type: Literal[
        "check_in",
        "acute_symptom",
        "pain",
        "fatigue",
        "sleep",
        "readiness",
        "training_volume",
        "planned_session",
        "missing_data",
    ]
    message: str = Field(min_length=1, max_length=300)
    values: dict[str, Any] = Field(default_factory=dict)
    rule_source: Literal[
        "user_report",
        "runcrew_conservative_rule",
        "exercise_safety_red_flag",
        "missing_data_policy",
    ]


class RecoveryPlanAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal[
        "keep",
        "ask_plan_agent_to_reduce",
        "ask_plan_agent_to_replace_with_rest",
        "hold_until_professional_review",
        "wait_for_more_data",
    ]
    target_session_id: str | None = None
    requires_user_confirmation: bool = True
    reason: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def write_actions_require_target(self) -> RecoveryPlanAction:
        write_actions = {
            "ask_plan_agent_to_reduce",
            "ask_plan_agent_to_replace_with_rest",
        }
        if self.action in write_actions and self.target_session_id is None:
            raise ValueError("计划调整动作必须指定目标计划课")
        if self.action == "keep" and self.requires_user_confirmation:
            raise ValueError("保持原计划不需要用户确认")
        return self


class RecoveryAssessmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", title="跑步恢复风险评估输出")

    schema_version: Literal["1.0"] = "1.0"
    ruleset_version: Literal["recovery-risk-rules/1.0"] = (
        "recovery-risk-rules/1.0"
    )
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    goal_id: str
    assessed_at: datetime
    recommendation: Literal[
        "proceed",
        "reduce",
        "rest",
        "seek_professional_help",
        "insufficient_data",
    ]
    risk_level: Literal["low", "moderate", "high", "escalate", "unknown"]
    summary: str = Field(min_length=1, max_length=500)
    evidence: list[RecoveryEvidence] = Field(min_length=1, max_length=30)
    missing_data: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    current_7d: RecoveryWindowMetrics
    previous_7d: RecoveryWindowMetrics
    plan_action: RecoveryPlanAction

    @field_validator("assessed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("评估时间必须包含时区")
        return value

    @field_validator("summary")
    @classmethod
    def forbid_diagnostic_language(cls, value: str) -> str:
        forbidden = ("确诊", "诊断为", "你患有", "肯定是", "保证不会受伤")
        if any(phrase in value for phrase in forbidden):
            raise ValueError("恢复风险结果不能包含诊断或保证性措辞")
        return value

    @model_validator(mode="after")
    def recommendation_must_match_risk(self) -> RecoveryAssessmentResult:
        expected = {
            "proceed": "low",
            "reduce": "moderate",
            "rest": "high",
            "seek_professional_help": "escalate",
            "insufficient_data": "unknown",
        }
        if self.risk_level != expected[self.recommendation]:
            raise ValueError("recommendation 与 risk_level 不一致")
        return self
