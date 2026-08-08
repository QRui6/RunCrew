from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RecoverySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measured_at: datetime
    recovery_percent: float | None = Field(default=None, ge=0, le=100)
    estimated_full_recovery_hours: float | None = Field(default=None, ge=0)
    short_term_load: float | None = Field(default=None, ge=0)
    long_term_load: float | None = Field(default=None, ge=0)
    load_ratio: float | None = Field(default=None, ge=0)

    @field_validator("measured_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("measured_at must be timezone-aware")
        return value

