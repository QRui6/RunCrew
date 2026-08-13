from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from runcrew.domain.activity import SourceProvider
from runcrew.domain.recovery_assessment import RecoveryAssessmentRequest, RecoveryAssessmentResult
from runcrew.domain.training_execution import TrainingExecutionRequest, TrainingExecutionResult
from runcrew.domain.training_planning import PlanAdjustmentRequest, TrainingPlanningResult


EXECUTION_TOOL_NAME = "compare_training_execution"
RECOVERY_TOOL_NAME = "assess_running_recovery"
PLAN_TOOL_NAME = "adjust_running_plan"

CoachNode = Literal["execution_agent", "recovery_agent", "plan_agent"]
CoachRunStatus = Literal[
    "succeeded", "awaiting_user_confirmation", "blocked", "failed", "timed_out", "budget_exhausted"
]


class CoachAgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Coach Orchestrator 运行输入")

    goal_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    as_of: datetime
    provider: SourceProvider | None = None
    date_tolerance_days: int = Field(default=1, ge=0, le=3)
    recovery_lookback_days: int = Field(default=14, ge=14, le=28)
    max_steps: int = Field(default=5, ge=1, le=12)
    node_call_budget: int = Field(default=3, ge=0, le=6)
    max_retries: int = Field(default=1, ge=0, le=3)
    node_timeout_seconds: float = Field(default=5, gt=0, le=60)
    run_timeout_seconds: float = Field(default=20, gt=0, le=120)

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of 必须包含时区")
        return value


class CoachNodePermission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node: CoachNode
    tool_name: Literal[
        "compare_training_execution", "assess_running_recovery", "adjust_running_plan"
    ]
    access: Literal["read", "prepare_change"]
    can_persist: Literal[False] = False
    can_approve: Literal[False] = False


class DelegateExecutionAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["delegate_execution"] = "delegate_execution"
    node: Literal["execution_agent"] = "execution_agent"
    tool_name: Literal["compare_training_execution"] = EXECUTION_TOOL_NAME
    arguments: TrainingExecutionRequest


class DelegateRecoveryAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["delegate_recovery"] = "delegate_recovery"
    node: Literal["recovery_agent"] = "recovery_agent"
    tool_name: Literal["assess_running_recovery"] = RECOVERY_TOOL_NAME
    arguments: RecoveryAssessmentRequest


class DelegatePlanAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["delegate_plan"] = "delegate_plan"
    node: Literal["plan_agent"] = "plan_agent"
    tool_name: Literal["adjust_running_plan"] = PLAN_TOOL_NAME
    arguments: PlanAdjustmentRequest


class CoachFinishAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["finish"] = "finish"


CoachAction = Annotated[
    DelegateExecutionAction | DelegateRecoveryAction | DelegatePlanAction | CoachFinishAction,
    Field(discriminator="type"),
]
COACH_ACTION_ADAPTER = TypeAdapter(CoachAction)


class CoachPolicyContext(BaseModel):
    """只给编排 Policy 的最小状态，不包含活动明细、身体量表或原始数据库。"""

    model_config = ConfigDict(extra="forbid")

    instruction_version: Literal["coach-orchestrator-instructions/1.0"] = (
        "coach-orchestrator-instructions/1.0"
    )
    objective: Literal["汇总训练执行与恢复状态，并在必要时生成待确认计划提案"] = (
        "汇总训练执行与恢复状态，并在必要时生成待确认计划提案"
    )
    permissions: list[CoachNodePermission]
    execution_request: TrainingExecutionRequest
    recovery_request: RecoveryAssessmentRequest
    plan_request: PlanAdjustmentRequest | None = None
    execution_completed: bool = False
    recovery_completed: bool = False
    recovery_route: Literal[
        "unknown",
        "keep",
        "ask_plan_agent_to_reduce",
        "ask_plan_agent_to_replace_with_rest",
        "hold_until_professional_review",
        "wait_for_more_data",
    ] = "unknown"
    planning_completed: bool = False
    step: int = Field(ge=0)
    remaining_steps: int = Field(ge=0)
    remaining_node_calls: int = Field(ge=0)


class CoachHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=1)
    from_node: Literal["coach_orchestrator"] = "coach_orchestrator"
    to_node: CoachNode
    tool_name: str = Field(min_length=1)
    context_fields: list[str] = Field(min_length=1)
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class CoachTraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=1)
    elapsed_ms: float = Field(ge=0)
    state: Literal[
        "created", "routing", "handoff", "calling_node", "validating", "paused", "completed", "failed"
    ]
    event: Literal[
        "run_started",
        "policy_action",
        "handoff_prepared",
        "node_permission_checked",
        "node_call_started",
        "node_call_retry_scheduled",
        "node_call_succeeded",
        "node_call_failed",
        "node_output_validated",
        "user_confirmation_requested",
        "run_completed",
        "run_failed",
        "run_timed_out",
        "budget_exhausted",
    ]
    node: CoachNode | None = None
    tool_name: str | None = None
    attempt: int | None = Field(default=None, ge=1)
    details: dict[str, Any] = Field(default_factory=dict)


class CoachBudgetUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps_used: int = Field(ge=0)
    node_calls_used: int = Field(ge=0)
    node_attempts_used: int = Field(ge=0)


class CoachRunError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "policy_error",
        "permission_denied",
        "invalid_handoff",
        "node_failure",
        "node_timeout",
        "invalid_node_output",
        "premature_finish",
        "step_budget_exhausted",
        "run_timeout",
    ]
    message: str = Field(min_length=1)
    retryable: bool


class CoachAgentRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Coach Orchestrator 运行输出")

    schema_version: Literal["1.0"] = "1.0"
    workflow_version: Literal["coach-weekly-operations/1.0"] = "coach-weekly-operations/1.0"
    run_id: str = Field(min_length=1)
    workflow_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: CoachRunStatus
    termination_reason: Literal[
        "completed",
        "user_confirmation_required",
        "safe_blocked",
        "policy_error",
        "permission_denied",
        "invalid_handoff",
        "node_failure",
        "node_timeout",
        "invalid_node_output",
        "premature_finish",
        "step_budget_exhausted",
        "run_timeout",
    ]
    execution: TrainingExecutionResult | None = None
    recovery: RecoveryAssessmentResult | None = None
    planning: TrainingPlanningResult | None = None
    required_user_action: Literal[
        "review_plan_change",
        "provide_fresh_check_in",
        "provide_training_plan",
        "seek_professional_review",
    ] | None = None
    error: CoachRunError | None = None
    budget: CoachBudgetUsage
    handoffs: list[CoachHandoff] = Field(default_factory=list, max_length=6)
    trace: list[CoachTraceEvent] = Field(min_length=2)

    @model_validator(mode="after")
    def terminal_payload_is_consistent(self) -> CoachAgentRunResult:
        if self.status in {"failed", "timed_out", "budget_exhausted"}:
            if self.error is None:
                raise ValueError("失败运行必须包含错误")
        elif self.error is not None:
            raise ValueError("业务终态不能包含运行错误")
        if self.status == "awaiting_user_confirmation":
            if (
                self.required_user_action != "review_plan_change"
                or self.planning is None
                or self.planning.change_proposal_draft is None
            ):
                raise ValueError("等待确认必须包含计划变更草案")
        if self.status == "succeeded" and self.termination_reason != "completed":
            raise ValueError("成功运行必须以 completed 结束")
        if self.status == "blocked" and self.required_user_action is None:
            raise ValueError("安全阻断必须说明用户下一步动作")
        if self.status == "succeeded" and self.required_user_action is not None:
            raise ValueError("成功运行不能包含待处理用户动作")
        sequences = [item.sequence for item in self.trace]
        if sequences != list(range(1, len(sequences) + 1)):
            raise ValueError("Trace 序号必须连续")
        return self
