from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class DailyHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: date
    resting_heart_rate: int | None = Field(default=None, ge=20, le=200)
    sleep_minutes: int | None = Field(default=None, ge=0, le=1440)
    sleep_score: float | None = Field(default=None, ge=0, le=100)
    hrv_ms: float | None = Field(default=None, ge=0)
    stress_score: float | None = Field(default=None, ge=0, le=100)
    steps: int | None = Field(default=None, ge=0)

