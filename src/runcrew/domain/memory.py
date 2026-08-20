from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from runcrew.domain.training_cycle import Weekday, new_id


PreferenceKey = Literal["preferred_long_run_weekday"]
PreferenceStatus = Literal["active", "superseded", "expired", "archived"]
PreferenceSource = Literal["explicit_user_setting"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AthletePreference(BaseModel):
    """经过用户明确确认、可追溯且有时效边界的长期训练偏好。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    key: PreferenceKey
    value: Weekday
    status: PreferenceStatus = "active"
    source_type: PreferenceSource = "explicit_user_setting"
    source_ref: str = Field(min_length=1, max_length=120)
    confirmed_at: datetime = Field(default_factory=utc_now)
    valid_from: datetime = Field(default_factory=utc_now)
    valid_until: datetime | None = None
    supersedes_id: str | None = None
    schema_version: Literal["athlete-preference/1.0"] = "athlete-preference/1.0"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator(
        "confirmed_at", "valid_from", "valid_until", "created_at", "updated_at"
    )
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("记忆时间必须包含时区")
        return value

    @model_validator(mode="after")
    def validate_lifecycle(self) -> AthletePreference:
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("偏好失效时间必须晚于生效时间")
        if self.supersedes_id == self.id:
            raise ValueError("偏好不能替代自身")
        return self

    def is_effective_at(self, at: datetime) -> bool:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("查询时间必须包含时区")
        return (
            self.status == "active"
            and self.valid_from <= at
            and (self.valid_until is None or at < self.valid_until)
        )


class AthletePreferenceSubmission(BaseModel):
    """产品写入契约；确认字段不允许由服务端或 Agent 隐式补齐。"""

    model_config = ConfigDict(extra="forbid", title="运动员长期偏好确认输入")

    key: PreferenceKey
    value: Weekday
    confirmed: Literal[True]
    valid_until: datetime | None = None

    @field_validator("valid_until")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("偏好失效时间必须包含时区")
        return value


class AthletePreferenceArchiveSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", title="运动员长期偏好停用输入")

    confirmed: Literal[True]


WeeklyMemoryStatus = Literal["active", "superseded", "invalidated"]


class WeeklyTrainingMemory(BaseModel):
    """由正式训练事实确定性生成、可版本替代的周训练记忆。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    goal_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    week_start: date
    week_end: date
    version: int = Field(ge=1)
    status: WeeklyMemoryStatus = "active"
    plan_revision: int = Field(ge=1)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    planned_sessions: int = Field(ge=0)
    confirmed_completed_sessions: int = Field(ge=0)
    confirmed_skipped_sessions: int = Field(ge=0)
    unresolved_sessions: int = Field(ge=0)
    completion_rate: float | None = Field(default=None, ge=0, le=1)
    planned_duration_seconds: int = Field(ge=0)
    actual_duration_seconds: int = Field(ge=0)
    actual_distance_meters: float = Field(ge=0)
    check_in_days: int = Field(ge=0)
    average_fatigue: float | None = Field(default=None, ge=1, le=5)
    average_soreness: float | None = Field(default=None, ge=0, le=10)
    average_sleep_quality: float | None = Field(default=None, ge=1, le=5)
    average_readiness: float | None = Field(default=None, ge=1, le=5)
    max_pain_severity: int | None = Field(default=None, ge=0, le=10)
    acute_symptom_days: int = Field(ge=0)
    approved_plan_changes: int = Field(ge=0)
    summary: str = Field(min_length=1, max_length=500)
    missing_data: list[str] = Field(default_factory=list, max_length=20)
    source_refs: list[str] = Field(min_length=1, max_length=100)
    supersedes_id: str | None = None
    invalidated_at: datetime | None = None
    schema_version: Literal["weekly-training-memory/1.0"] = (
        "weekly-training-memory/1.0"
    )
    ruleset_version: Literal["weekly-training-memory-rules/1.0"] = (
        "weekly-training-memory-rules/1.0"
    )
    generated_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("week_start")
    @classmethod
    def require_monday(cls, value: date) -> date:
        if value.weekday() != 0:
            raise ValueError("周训练记忆必须从星期一开始。")
        return value

    @field_validator("generated_at", "updated_at", "invalidated_at")
    @classmethod
    def require_memory_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("周训练记忆时间必须包含时区。")
        return value

    @model_validator(mode="after")
    def validate_weekly_memory(self) -> WeeklyTrainingMemory:
        if self.week_end != self.week_start + timedelta(days=6):
            raise ValueError("周训练记忆必须覆盖完整的星期一至星期日。")
        if self.supersedes_id == self.id:
            raise ValueError("周训练记忆不能替代自身。")
        if self.status == "invalidated" and self.invalidated_at is None:
            raise ValueError("失效周训练记忆必须记录失效时间。")
        if self.status != "invalidated" and self.invalidated_at is not None:
            raise ValueError("只有失效周训练记忆可以记录失效时间。")
        resolved = (
            self.confirmed_completed_sessions
            + self.confirmed_skipped_sessions
            + self.unresolved_sessions
        )
        if resolved != self.planned_sessions:
            raise ValueError("周训练记忆的训练课统计必须闭合。")
        return self


class WeeklyTrainingMemoryBuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", title="周训练记忆生成输入")

    goal_id: str = Field(min_length=1)
    week_start: date
    as_of: datetime

    @field_validator("week_start")
    @classmethod
    def require_request_monday(cls, value: date) -> date:
        if value.weekday() != 0:
            raise ValueError("周训练记忆必须从星期一开始。")
        return value

    @field_validator("as_of")
    @classmethod
    def require_request_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of 必须包含时区。")
        return value


class WeeklyTrainingMemoryBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid", title="周训练记忆生成结果")

    outcome: Literal["created", "unchanged", "superseded"]
    memory: WeeklyTrainingMemory
