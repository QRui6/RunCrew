from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from runcrew.domain.memory import MemoryCandidateDecision, MemoryCandidateStatus
from runcrew.domain.training_cycle import Weekday


MemoryEvaluationCategory = Literal[
    "candidate", "lifecycle", "integrity", "retrieval"
]
MemoryEvaluationScenario = Literal[
    "explicit_high_confidence",
    "explicit_medium_confidence",
    "temporary_expression",
    "negative_expression",
    "ambiguous_expression",
    "unsupported_expression",
    "pending_is_not_memory",
    "confirm_writes_preference",
    "reject_does_not_write",
    "new_candidate_supersedes",
    "expired_candidate_blocked",
    "candidate_tamper_blocked",
    "source_tamper_blocked",
    "role_scoped_retrieval",
    "inactive_memory_excluded",
    "irrelevant_injection_stable_context",
]


class MemoryEvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Memory 评测输入")

    content: str | None = None
    second_content: str | None = None
    decision: MemoryCandidateDecision | None = None


class MemoryEvaluationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Memory 评测观察结果")

    candidate_created: bool = False
    proposed_value: Weekday | None = None
    candidate_confidence: Literal["high", "medium"] | None = None
    candidate_status: MemoryCandidateStatus | None = None
    secondary_candidate_status: MemoryCandidateStatus | None = None
    formal_preference_count: int = Field(default=0, ge=0)
    decision_blocked: bool = False
    execution_item_count: int = Field(default=0, ge=0)
    recovery_preference_count: int = Field(default=0, ge=0)
    recovery_weekly_count: int = Field(default=0, ge=0)
    plan_preference_count: int = Field(default=0, ge=0)
    plan_weekly_count: int = Field(default=0, ge=0)
    exclusion_reasons: list[str] = Field(default_factory=list)
    context_hash_unchanged: bool | None = None


class MemoryEvaluationChecks(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Memory 评测检查项")

    candidate_detection: bool | None = None
    negative_rejection: bool | None = None
    lifecycle_integrity: bool | None = None
    source_integrity: bool | None = None
    confirmation_boundary: bool | None = None
    role_scope: bool | None = None
    irrelevant_injection_resistance: bool | None = None


class MemoryEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Memory 评测用例")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    description: str = Field(min_length=1)
    category: MemoryEvaluationCategory
    scenario: MemoryEvaluationScenario
    input: MemoryEvaluationInput = Field(default_factory=MemoryEvaluationInput)
    expected: MemoryEvaluationObservation


class MemoryEvaluationSuite(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Memory 评测套件")

    suite_version: Literal["memory-manager-eval/1.0"] = "memory-manager-eval/1.0"
    cases: list[MemoryEvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def case_ids_must_be_unique(self) -> MemoryEvaluationSuite:
        identifiers = [case.id for case in self.cases]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Memory 评测用例 ID 不能重复")
        return self


class MemoryEvaluationCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Memory 单用例评测结果")

    case_id: str
    category: MemoryEvaluationCategory
    scenario: MemoryEvaluationScenario
    passed: bool
    schema_valid: bool
    actual: MemoryEvaluationObservation
    checks: MemoryEvaluationChecks
    latency_ms: float = Field(ge=0)
    failure_reasons: list[str] = Field(default_factory=list)


class MemoryEvaluationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Memory 评测指标")

    expectation_pass_rate: float = Field(ge=0, le=1)
    candidate_recall_rate: float = Field(ge=0, le=1)
    negative_rejection_rate: float = Field(ge=0, le=1)
    lifecycle_integrity_rate: float = Field(ge=0, le=1)
    source_integrity_rate: float = Field(ge=0, le=1)
    confirmation_boundary_rate: float = Field(ge=0, le=1)
    role_scope_rate: float = Field(ge=0, le=1)
    irrelevant_injection_resistance_rate: float = Field(ge=0, le=1)
    schema_valid_rate: float = Field(ge=0, le=1)
    unexpected_formal_memory_write_count: int = Field(ge=0)
    p95_latency_ms: float = Field(ge=0)
    category_counts: dict[str, int]


class MemoryEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Memory 评测报告")

    schema_version: Literal["1.0"] = "1.0"
    suite_version: Literal["memory-manager-eval/1.0"]
    suite_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_name: str = Field(min_length=1)
    total_cases: int = Field(ge=1)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    meets_baseline: bool
    metrics: MemoryEvaluationMetrics
    cases: list[MemoryEvaluationCaseResult] = Field(min_length=1)

    @model_validator(mode="after")
    def counts_must_be_consistent(self) -> MemoryEvaluationReport:
        if self.total_cases != len(self.cases):
            raise ValueError("报告用例总数必须与逐用例结果一致")
        if self.passed_cases + self.failed_cases != self.total_cases:
            raise ValueError("通过数与失败数之和必须等于用例总数")
        return self
