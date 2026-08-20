from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RuntimeGovernanceCategory = Literal[
    "registration",
    "input_integrity",
    "confirmation",
    "output_validation",
    "observability",
]
RuntimeGovernanceScenario = Literal[
    "unknown_tool_blocked",
    "argument_tampering_blocked",
    "confirmation_bypass_blocked",
    "invalid_output_blocked",
    "observability_failure_isolated",
]


class RuntimeGovernanceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocked: bool = False
    tool_executed: bool = False
    output_accepted: bool | None = None
    business_continued: bool = False
    persistence_failed: bool = False
    error_redacted: bool = True
    rule_ids: list[str] = Field(default_factory=list)


class RuntimeGovernanceEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    description: str = Field(min_length=1)
    category: RuntimeGovernanceCategory
    scenario: RuntimeGovernanceScenario
    expected: RuntimeGovernanceObservation


class RuntimeGovernanceEvaluationSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite_version: Literal["runtime-governance-eval/1.0"] = (
        "runtime-governance-eval/1.0"
    )
    cases: list[RuntimeGovernanceEvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def case_ids_are_unique(self) -> RuntimeGovernanceEvaluationSuite:
        identifiers = [case.id for case in self.cases]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Runtime 治理评测用例 ID 不能重复")
        return self


class RuntimeGovernanceCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    category: RuntimeGovernanceCategory
    scenario: RuntimeGovernanceScenario
    passed: bool
    schema_valid: bool
    actual: RuntimeGovernanceObservation
    latency_ms: float = Field(ge=0)
    failure_reasons: list[str] = Field(default_factory=list)


class RuntimeGovernanceEvaluationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectation_pass_rate: float = Field(ge=0, le=1)
    pre_execution_block_rate: float = Field(ge=0, le=1)
    invalid_output_block_rate: float = Field(ge=0, le=1)
    observability_failure_isolation_rate: float = Field(ge=0, le=1)
    prohibited_tool_execution_count: int = Field(ge=0)
    sensitive_error_leak_count: int = Field(ge=0)
    p95_latency_ms: float = Field(ge=0)
    category_counts: dict[str, int]


class RuntimeGovernanceEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    suite_version: Literal["runtime-governance-eval/1.0"]
    suite_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_name: str = Field(min_length=1)
    evidence_scope: Literal["deterministic_synthetic_governance"] = (
        "deterministic_synthetic_governance"
    )
    total_cases: int = Field(ge=1)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    meets_baseline: bool
    metrics: RuntimeGovernanceEvaluationMetrics
    cases: list[RuntimeGovernanceCaseResult] = Field(min_length=1)

    @model_validator(mode="after")
    def counts_are_consistent(self) -> RuntimeGovernanceEvaluationReport:
        if self.total_cases != len(self.cases):
            raise ValueError("Runtime 治理报告总数必须与逐用例结果一致")
        if self.passed_cases + self.failed_cases != self.total_cases:
            raise ValueError("Runtime 治理报告通过数与失败数不一致")
        return self
