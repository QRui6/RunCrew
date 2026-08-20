from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


RuntimeWorkflow = Literal["review_agent", "coach_orchestrator"]
RuntimeRunStatus = Literal[
    "succeeded",
    "awaiting_confirmation",
    "blocked",
    "failed",
    "timed_out",
    "budget_exhausted",
]
RuntimeSpanKind = Literal[
    "run",
    "policy",
    "guardrail",
    "handoff",
    "tool",
    "retry",
    "validation",
    "approval",
    "lifecycle",
]
RuntimeSpanStatus = Literal["ok", "blocked", "error"]


class RuntimeBudgetSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps_used: int = Field(ge=0)
    calls_used: int = Field(ge=0)
    attempts_used: int = Field(ge=0)


class RuntimeRun(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Agent Runtime Run")

    schema_version: Literal["runtime-run/1.0"] = "runtime-run/1.0"
    run_id: str = Field(min_length=1, max_length=64)
    workflow: RuntimeWorkflow
    workflow_version: str = Field(min_length=1, max_length=80)
    status: RuntimeRunStatus
    termination_reason: str = Field(min_length=1, max_length=80)
    duration_ms: float = Field(ge=0)
    budget: RuntimeBudgetSnapshot
    span_count: int = Field(ge=1)
    tool_call_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    trace_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope_ref_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    recorded_at: datetime
    expires_at: datetime

    @field_validator("recorded_at", "expires_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Runtime 时间必须包含时区")
        return value

    @model_validator(mode="after")
    def expiration_follows_recording(self) -> RuntimeRun:
        if self.expires_at <= self.recorded_at:
            raise ValueError("Runtime 过期时间必须晚于记录时间")
        return self


class RuntimeSpan(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Agent Runtime Span")

    schema_version: Literal["runtime-span/1.0"] = "runtime-span/1.0"
    span_id: str = Field(min_length=1, max_length=140)
    run_id: str = Field(min_length=1, max_length=64)
    sequence: int = Field(ge=0)
    source_sequence: int | None = Field(default=None, ge=1)
    parent_span_id: str | None = Field(default=None, max_length=140)
    name: str = Field(min_length=1, max_length=80)
    kind: RuntimeSpanKind
    status: RuntimeSpanStatus
    start_offset_ms: float = Field(ge=0)
    duration_ms: float = Field(ge=0)
    node: str | None = Field(default=None, max_length=64)
    tool_name: str | None = Field(default=None, max_length=80)
    attempt: int | None = Field(default=None, ge=1)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def cannot_parent_itself(self) -> RuntimeSpan:
        if self.parent_span_id == self.span_id:
            raise ValueError("Span 不能以自身作为父节点")
        return self


class RuntimeRunCapture(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Agent Runtime Run Capture")

    run: RuntimeRun
    spans: list[RuntimeSpan] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_timeline(self) -> RuntimeRunCapture:
        if self.run.span_count != len(self.spans):
            raise ValueError("Run span_count 必须与 Span 数量一致")
        if [item.sequence for item in self.spans] != list(range(len(self.spans))):
            raise ValueError("Runtime Span sequence 必须从0连续递增")
        ids = {item.span_id for item in self.spans}
        if len(ids) != len(self.spans):
            raise ValueError("Runtime Span ID 不能重复")
        roots = [item for item in self.spans if item.parent_span_id is None]
        if len(roots) != 1 or roots[0].kind != "run":
            raise ValueError("Runtime Capture 必须只有一个根 Run Span")
        for item in self.spans:
            if item.run_id != self.run.run_id:
                raise ValueError("Span run_id 必须与 Run 一致")
            if item.parent_span_id is not None and item.parent_span_id not in ids:
                raise ValueError("Span 父节点必须存在于同一 Capture")
        return self


class RuntimeRunList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: list[RuntimeRun]


class RuntimePersistenceOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    persisted: bool
    created: bool = False
    error_type: str | None = None
