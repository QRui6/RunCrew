from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from runcrew.domain.review import ActivityReview, DataQuality


class PlannedSession(BaseModel):
    model_config = ConfigDict(extra="forbid", title="计划训练目标")

    distance_meters: float | None = Field(
        default=None,
        gt=0,
        description="计划完成的距离，单位为米。",
    )
    duration_seconds: int | None = Field(
        default=None,
        gt=0,
        description="计划训练的持续时间，单位为秒。",
    )

    @model_validator(mode="after")
    def require_a_target(self) -> PlannedSession:
        if self.distance_meters is None and self.duration_seconds is None:
            raise ValueError("计划训练必须至少提供距离或时长")
        return self


class TrainingReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", title="训练复盘输入")

    target_activity_id: str = Field(
        min_length=1,
        description="需要复盘的 RunCrew 内部活动 ID。",
    )
    lookback_days: int = Field(
        default=28,
        ge=14,
        le=90,
        description="构建历史上下文时向前回看的天数。",
    )
    planned_session: PlannedSession | None = Field(
        default=None,
        description="用户明确提供的本次训练计划；没有计划时必须留空。",
    )


class TrainingWindowMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", title="训练时间窗口指标")

    start: datetime = Field(description="时间窗口起点，必须包含时区。")
    end: datetime = Field(description="时间窗口终点，必须包含时区。")
    activity_count: int = Field(ge=0, description="窗口内的活动数量。")
    distance_meters: float = Field(ge=0, description="窗口内累计距离，单位为米。")
    duration_seconds: int = Field(ge=0, description="窗口内累计时长，单位为秒。")
    training_load_total: float | None = Field(
        default=None,
        ge=0,
        description="窗口内可获得的训练负荷之和；没有负荷数据时为空。",
    )
    training_load_coverage: float = Field(
        ge=0,
        le=1,
        description="包含训练负荷字段的活动占比。",
    )

    @field_validator("start", "end")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("训练时间窗口必须包含时区")
        return value


class TrainingFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", title="训练复盘结论")

    type: Literal["training_completion", "load_change", "training_anomaly"] = Field(
        description="结论类型：训练完成度、负荷变化或训练异常。"
    )
    level: Literal["good", "normal", "attention", "unknown"] = Field(
        description="结论等级；数据不足时必须使用 unknown。"
    )
    message: str = Field(min_length=1, description="面向用户的简短结论。")
    evidence: dict[str, Any] = Field(description="支持该结论的结构化证据。")

    @field_validator("evidence")
    @classmethod
    def require_evidence(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("每条训练复盘结论都必须包含证据")
        return value


class TrainingReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid", title="训练复盘输出")

    schema_version: Literal["1.0"] = Field(
        default="1.0",
        description="输出 Schema 版本。",
    )
    ruleset_version: Literal["training-review-rules/1.0"] = Field(
        default="training-review-rules/1.0",
        description="生成结论所使用的确定性规则版本。",
    )
    input_hash: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="规范化输入的 SHA-256，用于确定性回放。",
    )
    target_activity_id: str = Field(description="本次复盘对应的 RunCrew 活动 ID。")
    activity_review: ActivityReview = Field(description="目标活动的单次活动复盘。")
    current_7d: TrainingWindowMetrics = Field(description="截至目标活动的最近七天指标。")
    previous_7d: TrainingWindowMetrics = Field(description="此前七天的对照指标。")
    findings: list[TrainingFinding] = Field(
        min_length=3,
        max_length=3,
        description="固定包含训练完成度、负荷变化和训练异常三类结论。",
    )
    data_quality: DataQuality = Field(description="整体缺失字段与结论置信度。")
