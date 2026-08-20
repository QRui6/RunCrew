from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from runcrew.domain.memory import (
    AgentMemoryContext,
    AthletePreference,
    MemoryCandidate,
    WeeklyTrainingMemory,
)


class MemoryControlCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pending_candidates: int = Field(ge=0)
    active_preferences: int = Field(ge=0)
    active_weekly_memories: int = Field(ge=0)
    total_records: int = Field(ge=0)


class MemoryCandidateControlItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: MemoryCandidate
    conversation_title: str = Field(min_length=1, max_length=80)
    source_excerpt: str | None = Field(default=None, max_length=240)
    source_available: bool


class AthletePreferenceControlItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preference: AthletePreference
    effective_now: bool


class WeeklyMemoryControlItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory: WeeklyTrainingMemory
    goal_name: str = Field(min_length=1, max_length=80)


class MemoryGoalContextAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str = Field(min_length=1)
    goal_name: str = Field(min_length=1, max_length=80)
    target_week_start: date
    contexts: list[AgentMemoryContext] = Field(min_length=3, max_length=3)


class MemoryControlOverview(BaseModel):
    model_config = ConfigDict(extra="forbid", title="RunCrew 记忆档案总览")

    schema_version: Literal["memory-control-overview/1.0"] = (
        "memory-control-overview/1.0"
    )
    generated_at: datetime
    counts: MemoryControlCounts
    candidates: list[MemoryCandidateControlItem] = Field(default_factory=list)
    preferences: list[AthletePreferenceControlItem] = Field(default_factory=list)
    weekly_memories: list[WeeklyMemoryControlItem] = Field(default_factory=list)
    goal_contexts: list[MemoryGoalContextAudit] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("记忆档案生成时间必须包含时区。")
        return value


class WeeklyMemoryInvalidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", title="周训练记忆失效确认输入")

    confirmed: Literal[True]
