from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from runcrew.domain.agent import AgentRunStatus


EvaluationCategory = Literal["task", "resilience", "guardrail", "budget"]
EvaluationDataMode = Literal["complete", "missing_context"]
EvaluationToolMode = Literal[
    "success",
    "transient_once",
    "timeout",
    "invalid_output",
    "permanent_failure",
]
EvaluationPolicyMode = Literal[
    "default",
    "unknown_tool",
    "tamper_arguments",
    "premature_finish",
]
EvaluationTerminationReason = Literal[
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
]


class EvaluationRunOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid", title="评测运行参数覆盖")

    max_steps: int = Field(default=4, ge=1, le=12, description="最大策略步骤数。")
    tool_call_budget: int = Field(
        default=1,
        ge=0,
        le=3,
        description="业务工具逻辑调用预算。",
    )
    max_retries: int = Field(default=1, ge=0, le=3, description="工具重试次数。")
    tool_timeout_seconds: float = Field(
        default=0.01,
        gt=0,
        le=5,
        description="单次工具尝试超时秒数；离线评测使用短超时。",
    )
    run_timeout_seconds: float = Field(
        default=1.0,
        gt=0,
        le=10,
        description="整个 Agent Run 的超时秒数。",
    )


class ReviewAgentEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", title="训练复盘 Agent 评测用例")

    id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
        description="稳定、可用于报告对比的用例 ID。",
    )
    description: str = Field(min_length=1, description="面向人的中文场景说明。")
    category: EvaluationCategory = Field(description="任务、韧性、护栏或预算场景。")
    data_mode: EvaluationDataMode = Field(description="使用完整或缺失上下文数据。")
    tool_mode: EvaluationToolMode = Field(description="注入的工具行为。")
    policy_mode: EvaluationPolicyMode = Field(description="注入的策略行为。")
    permission_confirmation_required: bool = Field(
        default=False,
        description="是否把唯一工具配置为需要用户确认。",
    )
    confirmed_tools: set[str] = Field(
        default_factory=set,
        description="本用例预先获得用户确认的工具集合。",
    )
    run: EvaluationRunOverrides = Field(
        default_factory=EvaluationRunOverrides,
        description="覆盖 Harness 默认预算和超时。",
    )
    expected_status: AgentRunStatus = Field(description="期望的 Agent Run 终态。")
    expected_termination_reason: EvaluationTerminationReason = Field(
        description="期望的明确退出原因。"
    )
    expected_output_present: bool = Field(description="期望是否产生合法业务输出。")
    expected_finding_levels: list[
        Literal["good", "normal", "attention", "unknown"]
    ] | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="成功任务期望的三个 finding 等级；非成功场景为空。",
    )
    max_tool_calls: int = Field(
        ge=0,
        le=3,
        description="该场景允许观察到的最大逻辑工具调用数。",
    )
    max_tool_attempts: int = Field(
        ge=0,
        le=4,
        description="该场景允许观察到的最大工具尝试数。",
    )

    @model_validator(mode="after")
    def require_consistent_success_expectation(self) -> ReviewAgentEvaluationCase:
        if self.expected_status == "succeeded":
            if not self.expected_output_present or self.expected_finding_levels is None:
                raise ValueError("成功用例必须声明输出和三个 finding 等级")
        elif self.expected_output_present or self.expected_finding_levels is not None:
            raise ValueError("非成功用例不能期望业务输出或 finding 等级")
        return self


class ReviewAgentEvaluationSuite(BaseModel):
    model_config = ConfigDict(extra="forbid", title="训练复盘 Agent 评测套件")

    suite_version: Literal["review-agent-eval/1.0"] = Field(
        default="review-agent-eval/1.0",
        description="评测用例集合版本。",
    )
    cases: list[ReviewAgentEvaluationCase] = Field(
        min_length=1,
        description="按固定顺序执行的离线评测用例。",
    )

    @model_validator(mode="after")
    def require_unique_case_ids(self) -> ReviewAgentEvaluationSuite:
        identifiers = [case.id for case in self.cases]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("评测用例 ID 不能重复")
        return self


class ReviewAgentEvaluationCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", title="单条 Agent 评测结果")

    case_id: str = Field(description="对应评测用例 ID。")
    category: EvaluationCategory = Field(description="评测类别。")
    passed: bool = Field(description="实际行为是否满足全部预期。")
    actual_status: AgentRunStatus = Field(description="实际 Agent Run 终态。")
    actual_termination_reason: EvaluationTerminationReason = Field(
        description="实际退出原因。"
    )
    schema_valid: bool = Field(description="Run Result 是否可再次通过 Schema 校验。")
    fact_integrity: bool | None = Field(
        description="成功输出是否与确定性工具结果完全一致；不适用时为空。"
    )
    prohibited_tool_executed: bool = Field(
        description="被权限或参数护栏拒绝后，底层工具是否仍被错误执行。"
    )
    tool_calls_used: int = Field(ge=0, description="实际逻辑工具调用数。")
    tool_attempts_used: int = Field(ge=0, description="实际工具尝试数。")
    latency_ms: float = Field(ge=0, description="该用例端到端执行耗时。")
    failure_reasons: list[str] = Field(
        default_factory=list,
        description="未满足预期时的中文原因。",
    )


class ReviewAgentEvaluationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Agent 评测指标")

    expectation_pass_rate: float = Field(ge=0, le=1, description="全部用例预期通过率。")
    task_completion_rate: float = Field(
        ge=0,
        le=1,
        description="正常任务场景中成功完成并输出合法结果的比例。",
    )
    guardrail_pass_rate: float = Field(
        ge=0,
        le=1,
        description="护栏场景按预期拦截且未执行底层工具的比例。",
    )
    schema_valid_rate: float = Field(
        ge=0,
        le=1,
        description="Agent Run 结果 Schema 通过率。",
    )
    fact_integrity_rate: float = Field(
        ge=0,
        le=1,
        description="成功输出与确定性工具事实完全一致的比例。",
    )
    prohibited_tool_execution_count: int = Field(
        ge=0,
        description="被护栏拒绝后底层工具仍执行的次数。",
    )
    average_tool_calls: float = Field(ge=0, description="平均逻辑工具调用数。")
    average_tool_attempts: float = Field(ge=0, description="平均工具尝试数。")
    p95_latency_ms: float = Field(ge=0, description="用例端到端耗时 P95。")
    termination_reason_counts: dict[str, int] = Field(
        description="各退出原因出现次数。"
    )


class ReviewAgentEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", title="训练复盘 Agent 评测报告")

    schema_version: Literal["1.0"] = Field(default="1.0", description="报告版本。")
    suite_version: Literal["review-agent-eval/1.0"] = Field(
        description="使用的评测套件版本。"
    )
    suite_hash: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="规范化评测套件的 SHA-256，用于复现。",
    )
    policy_name: str = Field(min_length=1, description="被评测 Policy 名称。")
    total_cases: int = Field(ge=1, description="用例总数。")
    passed_cases: int = Field(ge=0, description="满足全部预期的用例数。")
    failed_cases: int = Field(ge=0, description="未满足预期的用例数。")
    meets_baseline: bool = Field(description="是否满足当前离线基线门槛。")
    metrics: ReviewAgentEvaluationMetrics = Field(description="聚合指标。")
    cases: list[ReviewAgentEvaluationCaseResult] = Field(
        min_length=1,
        description="逐用例结果。",
    )

    @model_validator(mode="after")
    def require_consistent_counts(self) -> ReviewAgentEvaluationReport:
        if self.total_cases != len(self.cases):
            raise ValueError("报告用例总数必须与逐用例结果一致")
        if self.passed_cases + self.failed_cases != self.total_cases:
            raise ValueError("通过数与失败数之和必须等于用例总数")
        return self
