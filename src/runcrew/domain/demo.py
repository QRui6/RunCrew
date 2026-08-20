from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DemoSeedSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_version: Literal["runcrew-demo/1.0"] = "runcrew-demo/1.0"
    synthetic_data: Literal[True] = True
    database_path: str = Field(min_length=1)
    generated_at: datetime
    anchor_day: date
    activity_count: int = Field(ge=1)
    goal_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    preference_id: str = Field(min_length=1)
    latest_activity_id: str = Field(min_length=1)
    launch_command: str = Field(min_length=1)

