from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from runcrew.domain.review import ActivityReview, DataQuality


class PlannedSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    distance_meters: float | None = Field(default=None, gt=0)
    duration_seconds: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_a_target(self) -> PlannedSession:
        if self.distance_meters is None and self.duration_seconds is None:
            raise ValueError("planned session requires distance or duration")
        return self


class TrainingReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_activity_id: str = Field(min_length=1)
    lookback_days: int = Field(default=28, ge=14, le=90)
    planned_session: PlannedSession | None = None


class TrainingWindowMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime
    activity_count: int = Field(ge=0)
    distance_meters: float = Field(ge=0)
    duration_seconds: int = Field(ge=0)
    training_load_total: float | None = Field(default=None, ge=0)
    training_load_coverage: float = Field(ge=0, le=1)

    @field_validator("start", "end")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("training window timestamps must be timezone-aware")
        return value


class TrainingFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["training_completion", "load_change", "training_anomaly"]
    level: Literal["good", "normal", "attention", "unknown"]
    message: str = Field(min_length=1)
    evidence: dict[str, Any]

    @field_validator("evidence")
    @classmethod
    def require_evidence(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("every training finding requires evidence")
        return value


class TrainingReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    ruleset_version: Literal["training-review-rules/1.0"] = (
        "training-review-rules/1.0"
    )
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_activity_id: str
    activity_review: ActivityReview
    current_7d: TrainingWindowMetrics
    previous_7d: TrainingWindowMetrics
    findings: list[TrainingFinding] = Field(min_length=3, max_length=3)
    data_quality: DataQuality

