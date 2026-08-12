from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
EventType = Literal["5k", "10k", "half_marathon", "marathon", "general_fitness"]
SessionType = Literal[
    "easy", "long_run", "tempo", "interval", "recovery", "rest", "test"
]


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TrainingGoal(BaseModel):
    """用户明确声明的训练目标，而不是 Agent 猜测出来的目标。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    name: str = Field(min_length=1, max_length=80)
    event_type: EventType
    target_date: date
    target_time_seconds: int | None = Field(default=None, gt=0)
    available_weekdays: list[Weekday] = Field(min_length=1, max_length=7)
    status: Literal["active", "achieved", "abandoned"] = "active"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("available_weekdays")
    @classmethod
    def weekdays_must_be_unique(cls, value: list[Weekday]) -> list[Weekday]:
        if len(value) != len(set(value)):
            raise ValueError("可训练日期不能重复")
        return value

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("时间必须包含时区")
        return value


class PlanSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    scheduled_for: date
    session_type: SessionType
    distance_meters: float | None = Field(default=None, gt=0)
    duration_seconds: int | None = Field(default=None, gt=0)
    intensity: str | None = Field(default=None, min_length=1, max_length=80)
    purpose: str = Field(min_length=1, max_length=240)
    status: Literal["planned", "completed", "skipped"] = "planned"
    linked_activity_id: str | None = None

    @model_validator(mode="after")
    def require_work_for_non_rest_session(self) -> PlanSession:
        if self.session_type == "rest" and (
            self.distance_meters is not None or self.duration_seconds is not None
        ):
            raise ValueError("休息日不能设置训练距离或时长")
        if self.session_type != "rest" and (
            self.distance_meters is None and self.duration_seconds is None
        ):
            raise ValueError("非休息课必须至少提供距离或时长")
        return self


class TrainingPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    goal_id: str = Field(min_length=1)
    week_start: date
    status: Literal["draft", "active", "superseded", "completed"] = "draft"
    revision: int = Field(default=1, ge=1)
    source: Literal["user", "deterministic", "plan_agent"] = "user"
    sessions: list[PlanSession] = Field(default_factory=list, max_length=14)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("week_start")
    @classmethod
    def week_starts_on_monday(cls, value: date) -> date:
        if value.weekday() != 0:
            raise ValueError("训练周必须从星期一开始")
        return value

    @field_validator("sessions")
    @classmethod
    def sessions_must_be_unique(cls, value: list[PlanSession]) -> list[PlanSession]:
        identifiers = [session.id for session in value]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("计划课 ID 不能重复")
        return sorted(value, key=lambda session: (session.scheduled_for, session.id))

    @model_validator(mode="after")
    def sessions_must_stay_in_week(self) -> TrainingPlan:
        week_end = self.week_start + timedelta(days=6)
        outside = [
            session.id
            for session in self.sessions
            if not self.week_start <= session.scheduled_for <= week_end
        ]
        if outside:
            raise ValueError("计划课日期必须位于对应训练周内")
        return self

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("时间必须包含时区")
        return value


class DailyCheckIn(BaseModel):
    """用户主观反馈；仅作为恢复决策输入，不代表医疗诊断。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    day: date
    fatigue: int = Field(ge=1, le=5, description="1为轻松，5为非常疲劳")
    soreness: int = Field(ge=0, le=10)
    sleep_quality: int = Field(ge=1, le=5)
    readiness: int | None = Field(default=None, ge=1, le=5)
    pain_area: str | None = Field(default=None, min_length=1, max_length=80)
    pain_severity: int = Field(default=0, ge=0, le=10)
    note: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def pain_requires_area(self) -> DailyCheckIn:
        if self.pain_severity > 0 and not self.pain_area:
            raise ValueError("疼痛程度大于0时必须填写疼痛部位")
        return self

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("时间必须包含时区")
        return value


class PlanSessionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    scheduled_for: date | None = None
    session_type: SessionType | None = None
    distance_meters: float | None = Field(default=None, gt=0)
    duration_seconds: int | None = Field(default=None, gt=0)
    clear_distance: bool = False
    clear_duration: bool = False
    clear_intensity: bool = False
    intensity: str | None = Field(default=None, min_length=1, max_length=80)
    purpose: str | None = Field(default=None, min_length=1, max_length=240)

    @model_validator(mode="after")
    def require_change(self) -> PlanSessionPatch:
        fields = (
            self.scheduled_for,
            self.session_type,
            self.distance_meters,
            self.duration_seconds,
            self.intensity,
            self.purpose,
        )
        if all(value is None for value in fields) and not any(
            (self.clear_distance, self.clear_duration, self.clear_intensity)
        ):
            raise ValueError("变更提案必须至少修改一个字段")
        if self.distance_meters is not None and self.clear_distance:
            raise ValueError("不能同时设置并清除距离")
        if self.duration_seconds is not None and self.clear_duration:
            raise ValueError("不能同时设置并清除时长")
        if self.intensity is not None and self.clear_intensity:
            raise ValueError("不能同时设置并清除强度")
        return self


class PlanChangeProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    plan_id: str = Field(min_length=1)
    base_revision: int = Field(ge=1)
    proposed_by: Literal[
        "user", "coach_orchestrator", "plan_agent", "recovery_agent"
    ]
    reason: str = Field(min_length=1, max_length=500)
    changes: list[PlanSessionPatch] = Field(min_length=1, max_length=14)
    evidence_refs: list[str] = Field(default_factory=list, max_length=30)
    status: Literal["pending", "approved", "rejected", "stale"] = "pending"
    created_at: datetime = Field(default_factory=utc_now)
    decided_at: datetime | None = None

    @field_validator("created_at", "decided_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("时间必须包含时区")
        return value


class UserConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    proposal_id: str = Field(min_length=1)
    decision: Literal["approve", "reject"]
    comment: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("时间必须包含时区")
        return value


class TrainingCycleSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: TrainingGoal
    active_plan: TrainingPlan | None
    recent_check_ins: list[DailyCheckIn]
    pending_proposals: list[PlanChangeProposal]
