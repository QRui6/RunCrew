from __future__ import annotations

from datetime import datetime, timezone
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

