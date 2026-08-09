from __future__ import annotations

from typing import Any, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from runcrew.domain.training_review import (
    TrainingReviewRequest,
    TrainingReviewResult,
)


REVIEW_TOOL_NAME = "review_running_training"

AgentState = Literal[
    "created",
    "planning",
    "calling_tool",
    "validating",
    "completed",
    "failed",
]
AgentRunStatus = Literal["succeeded", "failed", "timed_out", "budget_exhausted"]


class ToolPermission(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Agent 工具权限")

    name: str = Field(min_length=1, description="允许调用的工具唯一名称。")
    access: Literal["read"] = Field(
        default="read",
        description="当前 M4 只允许只读工具。",
    )
    confirmation_required: bool = Field(
        default=False,
        description="调用此工具前是否必须获得用户明确确认。",
    )


class ReviewAgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", title="训练复盘 Agent 运行请求")

    review_request: TrainingReviewRequest = Field(
        description="传给训练复盘 Skill 的结构化业务请求。"
    )
    max_steps: int = Field(
        default=4,
        ge=1,
        le=12,
        description="一次 Agent Loop 允许执行的最大策略步骤数。",
    )
    tool_call_budget: int = Field(
        default=1,
        ge=0,
        le=3,
        description="允许发起的业务工具调用次数；重试不重复占用逻辑调用额度。",
    )
    max_retries: int = Field(
        default=1,
        ge=0,
        le=3,
        description="单次工具调用发生瞬时错误或超时时允许的最大重试次数。",
    )
    tool_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=60,
        description="每次工具尝试的超时时间。",
    )
    run_timeout_seconds: float = Field(
        default=15.0,
        gt=0,
        le=120,
        description="整个 Agent Run 的总超时时间。",
    )
    confirmed_tools: set[str] = Field(
        default_factory=set,
        description="本次运行中用户已经明确确认可以调用的工具。",
    )


class ToolCallAction(BaseModel):
    model_config = ConfigDict(extra="forbid", title="调用工具动作")

    type: Literal["call_tool"] = "call_tool"
    tool_name: str = Field(min_length=1, description="请求调用的工具名称。")
    arguments: TrainingReviewRequest = Field(description="工具的结构化参数。")


class FinishAction(BaseModel):
    model_config = ConfigDict(extra="forbid", title="结束运行动作")

    type: Literal["finish"] = "finish"


AgentAction = Annotated[ToolCallAction | FinishAction, Field(discriminator="type")]
AGENT_ACTION_ADAPTER = TypeAdapter(AgentAction)


class ReviewAgentContext(BaseModel):
    """传给策略层的有界上下文，不包含 Provider 原始数据或完整数据库。"""

    model_config = ConfigDict(extra="forbid", title="训练复盘 Agent 上下文")

    instruction_version: Literal["review-agent-instructions/1.0"] = Field(
        default="review-agent-instructions/1.0",
        description="约束 Agent 行为的指令版本。",
    )
    objective: Literal["生成一次可验证、带证据的训练复盘"] = Field(
        default="生成一次可验证、带证据的训练复盘",
        description="本次单 Agent 唯一允许完成的目标。",
    )
    user_request: TrainingReviewRequest = Field(description="用户的结构化业务请求。")
    tool_permissions: list[ToolPermission] = Field(
        description="Harness 明确授予的工具权限。"
    )
    observation: TrainingReviewResult | None = Field(
        default=None,
        description="上一轮工具返回且已经通过 Schema 校验的观察结果。",
    )
    step: int = Field(ge=0, description="已经完成的策略步骤数。")
    remaining_steps: int = Field(ge=0, description="剩余策略步骤预算。")
    remaining_tool_calls: int = Field(ge=0, description="剩余逻辑工具调用预算。")


class AgentTraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Agent Trace 事件")

    sequence: int = Field(ge=1, description="事件在本次运行中的递增序号。")
    elapsed_ms: float = Field(ge=0, description="相对本次运行开始的毫秒数。")
    state: AgentState = Field(description="事件发生时的 Agent 状态。")
    event: Literal[
        "run_started",
        "policy_action",
        "tool_permission_checked",
        "tool_call_started",
        "tool_call_retry_scheduled",
        "tool_call_succeeded",
        "tool_call_failed",
        "output_validation_started",
        "output_validated",
        "run_completed",
        "run_failed",
        "run_timed_out",
        "budget_exhausted",
    ] = Field(description="结构化事件类型。")
    attempt: int | None = Field(
        default=None,
        ge=1,
        description="工具尝试序号；非工具事件为空。",
    )
    tool_name: str | None = Field(
        default=None,
        description="相关工具名称；非工具事件为空。",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="经过脱敏的补充信息，不保存原始活动数据和异常正文。",
    )


class AgentRunError(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Agent 运行错误")

    code: Literal[
        "policy_error",
        "permission_denied",
        "confirmation_required",
        "tool_failure",
        "tool_timeout",
        "invalid_tool_output",
        "premature_finish",
        "step_budget_exhausted",
        "run_timeout",
    ] = Field(description="可稳定测试和统计的错误代码。")
    message: str = Field(min_length=1, description="面向用户的中文错误说明。")
    retryable: bool = Field(description="用户重新运行后是否可能恢复。")


class AgentBudgetUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Agent 预算使用情况")

    steps_used: int = Field(ge=0, description="已经执行的策略步骤数。")
    tool_calls_used: int = Field(ge=0, description="已经发起的逻辑工具调用数。")
    tool_attempts_used: int = Field(ge=0, description="包含重试在内的工具尝试次数。")


class ReviewAgentRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", title="训练复盘 Agent 运行结果")

    schema_version: Literal["1.0"] = Field(default="1.0", description="运行结果版本。")
    run_id: str = Field(
        min_length=1,
        description="本次运行的唯一标识；不包含活动外部 ID。",
    )
    status: AgentRunStatus = Field(description="本次运行的终态。")
    termination_reason: Literal[
        "completed",
        "policy_error",
        "permission_denied",
        "confirmation_required",
        "tool_failure",
        "tool_timeout",
        "invalid_tool_output",
        "premature_finish",
        "step_budget_exhausted",
        "run_timeout",
    ] = Field(description="状态机退出循环的明确原因。")
    output: TrainingReviewResult | None = Field(
        default=None,
        description="成功时返回且已经通过 Schema 校验的 Skill 结果。",
    )
    error: AgentRunError | None = Field(
        default=None,
        description="失败、超时或预算耗尽时的结构化错误。",
    )
    budget: AgentBudgetUsage = Field(description="本次运行实际消耗的预算。")
    trace: list[AgentTraceEvent] = Field(
        min_length=2,
        description="按顺序记录决策、工具、验证和退出过程。",
    )

    @model_validator(mode="after")
    def require_consistent_terminal_payload(self) -> ReviewAgentRunResult:
        if self.status == "succeeded":
            if self.termination_reason != "completed" or self.output is None:
                raise ValueError("成功运行必须以 completed 结束并包含输出")
            if self.error is not None:
                raise ValueError("成功运行不能包含错误")
        else:
            if self.output is not None or self.error is None:
                raise ValueError("未成功运行必须不包含输出且必须包含错误")
            if self.error.code != self.termination_reason:
                raise ValueError("错误代码必须与退出原因一致")
        sequences = [event.sequence for event in self.trace]
        if sequences != list(range(1, len(sequences) + 1)):
            raise ValueError("Trace 事件序号必须从 1 连续递增")
        return self
