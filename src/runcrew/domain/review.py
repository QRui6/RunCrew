from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    level: Literal["good", "normal", "attention", "unknown"]
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class DataQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    missing_fields: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]


class ActivityReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_id: str
    summary: dict[str, Any]
    observations: list[ReviewObservation]
    data_quality: DataQuality

