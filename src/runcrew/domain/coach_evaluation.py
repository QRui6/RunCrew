from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CoachEvaluationCategory = Literal[
    "task", "resilience", "guardrail", "budget", "approval"
]
CoachEvaluationScenario = Literal[
    "low_risk",
    "reduce",
    "rest",
    "missing_feedback",
    "red_flag",
    "approval_stale",
]
CoachEvaluationPolicyMode = Literal[
    "default", "tamper_handoff", "premature_finish", "invalid_action"
]
CoachEvaluationToolMode = Literal[
    "success",
    "execution_transient_once",
    "execution_timeout",
    "execution_invalid_output",
    "execution_permanent_failure",
    "execution_cross_goal",
    "plan_cross_goal",
    "plan_lineage_tamper",
]
CoachEvaluationPermissionMode = Literal["default", "wrong_execution_access"]
CoachEvaluationStatus = Literal[
    "succeeded",
    "awaiting_user_confirmation",
    "blocked",
    "failed",
    "timed_out",
    "budget_exhausted",
    "stale",
]
CoachEvaluationTermination = Literal[
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
    "stale_replay_blocked",
]


class CoachEvaluationRunOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Coach 评测运行参数覆盖")

    max_steps: int = Field(default=5, ge=1, le=12)
    node_call_budget: int = Field(default=3, ge=0, le=6)
    max_retries: int = Field(default=1, ge=0, le=3)
    node_timeout_seconds: float = Field(default=0.01, gt=0, le=5)
    run_timeout_seconds: float = Field(default=1.0, gt=0, le=30)


class CoachAgentEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Coach 多 Agent 评测用例")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    description: str = Field(min_length=1)
    category: CoachEvaluationCategory
    scenario: CoachEvaluationScenario
    policy_mode: CoachEvaluationPolicyMode = "default"
    tool_mode: CoachEvaluationToolMode = "success"
    permission_mode: CoachEvaluationPermissionMode = "default"
    run: CoachEvaluationRunOverrides = Field(default_factory=CoachEvaluationRunOverrides)
    expected_status: CoachEvaluationStatus
    expected_termination_reason: CoachEvaluationTermination
    expected_required_user_action: str | None = None
    expected_nodes: list[str] = Field(default_factory=list, max_length=6)
    max_node_calls: int = Field(default=3, ge=0, le=6)
    max_node_attempts: int = Field(default=3, ge=0, le=12)
    expect_pre_execution_block: bool = False


class CoachAgentEvaluationSuite(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Coach 多 Agent 评测套件")

    suite_version: Literal["coach-agent-eval/1.0"] = "coach-agent-eval/1.0"
    cases: list[CoachAgentEvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def case_ids_must_be_unique(self) -> CoachAgentEvaluationSuite:
        identifiers = [case.id for case in self.cases]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Coach 评测用例 ID 不能重复")
        return self


class CoachAgentEvaluationCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Coach 多 Agent 单用例结果")

    case_id: str
    category: CoachEvaluationCategory
    passed: bool
    actual_status: CoachEvaluationStatus
    actual_termination_reason: CoachEvaluationTermination
    actual_required_user_action: str | None = None
    actual_nodes: list[str] = Field(default_factory=list)
    schema_valid: bool
    fact_integrity: bool
    lineage_integrity: bool
    confirmation_boundary_valid: bool
    prohibited_node_executed: bool
    node_calls_used: int = Field(ge=0)
    node_attempts_used: int = Field(ge=0)
    latency_ms: float = Field(ge=0)
    failure_reasons: list[str] = Field(default_factory=list)


class CoachAgentEvaluationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Coach 多 Agent 评测指标")

    expectation_pass_rate: float = Field(ge=0, le=1)
    task_completion_rate: float = Field(ge=0, le=1)
    resilience_pass_rate: float = Field(ge=0, le=1)
    guardrail_pass_rate: float = Field(ge=0, le=1)
    approval_guard_pass_rate: float = Field(ge=0, le=1)
    schema_valid_rate: float = Field(ge=0, le=1)
    fact_integrity_rate: float = Field(ge=0, le=1)
    lineage_integrity_rate: float = Field(ge=0, le=1)
    confirmation_boundary_rate: float = Field(ge=0, le=1)
    prohibited_node_execution_count: int = Field(ge=0)
    average_node_calls: float = Field(ge=0)
    average_node_attempts: float = Field(ge=0)
    p95_latency_ms: float = Field(ge=0)
    termination_reason_counts: dict[str, int]


class CoachAgentEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Coach 多 Agent 评测报告")

    schema_version: Literal["1.0"] = "1.0"
    suite_version: Literal["coach-agent-eval/1.0"]
    suite_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_name: str = Field(min_length=1)
    total_cases: int = Field(ge=1)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    meets_baseline: bool
    metrics: CoachAgentEvaluationMetrics
    cases: list[CoachAgentEvaluationCaseResult] = Field(min_length=1)

    @model_validator(mode="after")
    def counts_must_be_consistent(self) -> CoachAgentEvaluationReport:
        if self.total_cases != len(self.cases):
            raise ValueError("报告用例总数必须与逐用例结果一致")
        if self.passed_cases + self.failed_cases != self.total_cases:
            raise ValueError("通过数与失败数之和必须等于用例总数")
        return self
