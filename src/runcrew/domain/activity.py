from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SourceProvider(StrEnum):
    COROS = "coros"
    FIT = "fit"
    KEEP = "keep"
    MANUAL = "manual"
    FIXTURE = "fixture"


class SportType(StrEnum):
    RUN = "run"
    INDOOR_RUN = "indoor_run"
    TRAIL_RUN = "trail_run"
    TRACK_RUN = "track_run"
    OTHER = "other"


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: SourceProvider
    external_id: str = Field(min_length=1)
    fetched_at: datetime
    raw_payload_hash: str = Field(min_length=8)

    @field_validator("fetched_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("fetched_at must be timezone-aware")
        return value


class Lap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)
    duration_seconds: float = Field(gt=0)
    distance_meters: float | None = Field(default=None, ge=0)
    average_pace_seconds_per_km: float | None = Field(default=None, gt=0)
    average_heart_rate: int | None = Field(default=None, ge=20, le=260)
    average_cadence: float | None = Field(default=None, ge=0, le=300)


class MetricPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    heart_rate: int | None = Field(default=None, ge=20, le=260)
    pace_seconds_per_km: float | None = Field(default=None, gt=0)
    cadence: float | None = Field(default=None, ge=0, le=300)
    elevation_meters: float | None = None

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value


class ActivitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    source_ref: SourceRef
    sport_type: SportType
    started_at: datetime
    duration_seconds: int = Field(gt=0)
    distance_meters: float | None = Field(default=None, ge=0)
    average_pace_seconds_per_km: float | None = Field(default=None, gt=0)
    average_heart_rate: int | None = Field(default=None, ge=20, le=260)
    training_load: float | None = Field(default=None, ge=0)
    title: str | None = None
    location: str | None = None

    @field_validator("started_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def derive_or_check_pace(self) -> ActivitySummary:
        if (
            self.average_pace_seconds_per_km is None
            and self.distance_meters is not None
            and self.distance_meters > 0
        ):
            self.average_pace_seconds_per_km = (
                self.duration_seconds / (self.distance_meters / 1000)
            )
        return self


class ActivityDetail(ActivitySummary):
    elevation_gain_meters: float | None = Field(default=None, ge=0)
    average_cadence: float | None = Field(default=None, ge=0, le=300)
    max_heart_rate: int | None = Field(default=None, ge=20, le=260)
    laps: list[Lap] = Field(default_factory=list)
    time_series: list[MetricPoint] = Field(default_factory=list)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)

