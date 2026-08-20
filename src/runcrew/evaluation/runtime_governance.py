from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path

from runcrew.domain.agent import (
    REVIEW_TOOL_NAME,
    AgentBudgetUsage,
    AgentRunError,
    AgentTraceEvent,
    ReviewAgentRunResult,
)
from runcrew.domain.runtime_evaluation import (
    RuntimeGovernanceCaseResult,
    RuntimeGovernanceEvaluationCase,
    RuntimeGovernanceEvaluationMetrics,
    RuntimeGovernanceEvaluationReport,
    RuntimeGovernanceEvaluationSuite,
    RuntimeGovernanceObservation,
)
from runcrew.domain.training_review import TrainingReviewRequest, TrainingReviewResult
from runcrew.services.runtime_governance import RuntimeGuardrailEngine
from runcrew.services.runtime_observability import RuntimeTraceService


def load_runtime_governance_suite(path: Path) -> RuntimeGovernanceEvaluationSuite:
    return RuntimeGovernanceEvaluationSuite.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def evaluate_runtime_governance_suite(
    suite: RuntimeGovernanceEvaluationSuite,
    *,
    evaluator_name: str = "deterministic-runtime-governance/1.0",
) -> RuntimeGovernanceEvaluationReport:
    results = [_evaluate_case(case) for case in suite.cases]
    passed = sum(item.passed for item in results)
    metrics = _metrics(results)
    meets_baseline = (
        passed == len(results)
        and metrics.pre_execution_block_rate == 1
        and metrics.invalid_output_block_rate == 1
        and metrics.observability_failure_isolation_rate == 1
        and metrics.prohibited_tool_execution_count == 0
        and metrics.sensitive_error_leak_count == 0
    )
    return RuntimeGovernanceEvaluationReport(
        suite_version=suite.suite_version,
        suite_hash=_suite_hash(suite),
        evaluator_name=evaluator_name,
        total_cases=len(results),
        passed_cases=passed,
        failed_cases=len(results) - passed,
        meets_baseline=meets_baseline,
        metrics=metrics,
        cases=results,
    )


def _evaluate_case(
    case: RuntimeGovernanceEvaluationCase,
) -> RuntimeGovernanceCaseResult:
    started = time.perf_counter()
    failures: list[str] = []
    try:
        actual = _run_scenario(case)
        schema_valid = True
    except Exception as error:  # pragma: no cover - defensive report boundary
        actual = RuntimeGovernanceObservation(error_redacted=False)
        schema_valid = False
        failures.append(f"场景执行异常：{type(error).__name__}")
    if actual != case.expected:
        failures.append("实际治理观察结果与版本化期望不一致")
    return RuntimeGovernanceCaseResult(
        case_id=case.id,
        category=case.category,
        scenario=case.scenario,
        passed=not failures,
        schema_valid=schema_valid,
        actual=actual,
        latency_ms=round((time.perf_counter() - started) * 1000, 3),
        failure_reasons=failures,
    )


def _run_scenario(
    case: RuntimeGovernanceEvaluationCase,
) -> RuntimeGovernanceObservation:
    if case.scenario == "invalid_output_blocked":
        _, decision = RuntimeGuardrailEngine().validate_output(
            tool_name=REVIEW_TOOL_NAME,
            raw_output={},
            output_model=TrainingReviewResult,
        )
        return RuntimeGovernanceObservation(
            blocked=not decision.allowed,
            tool_executed=True,
            output_accepted=decision.allowed,
            rule_ids=[decision.decision.rule_id],
        )
    if case.scenario == "observability_failure_isolated":
        class BrokenDatabase:
            def session(self):
                raise RuntimeError("private database failure")

        outcome = RuntimeTraceService(BrokenDatabase()).record_review(
            _failed_review_result()
        )
        serialized = outcome.model_dump_json()
        return RuntimeGovernanceObservation(
            business_continued=True,
            persistence_failed=not outcome.persisted,
            error_redacted="private database failure" not in serialized,
        )

    expected = TrainingReviewRequest(target_activity_id="synthetic-activity")
    actual = expected
    tool_name = REVIEW_TOOL_NAME
    confirmation_required = False
    if case.scenario == "unknown_tool_blocked":
        tool_name = "delete_activity"
    elif case.scenario == "argument_tampering_blocked":
        actual = TrainingReviewRequest(target_activity_id="tampered-activity")
    elif case.scenario == "confirmation_bypass_blocked":
        confirmation_required = True
    decision = RuntimeGuardrailEngine().evaluate_invocation(
        tool_name=tool_name,
        owner_role="review_agent",
        granted_access="read",
        actual_arguments=actual,
        expected_arguments=expected,
        timeout_seconds=5,
        max_retries=1,
        confirmation_required=confirmation_required,
        confirmed=False,
    )
    return RuntimeGovernanceObservation(
        blocked=not decision.allowed,
        tool_executed=False,
        rule_ids=[
            item.rule_id for item in decision.decisions if item.outcome != "allow"
        ],
    )


def _failed_review_result() -> ReviewAgentRunResult:
    return ReviewAgentRunResult(
        run_id="runtime-eval-observability",
        status="failed",
        termination_reason="permission_denied",
        error=AgentRunError(
            code="permission_denied",
            message="合成治理场景。",
            retryable=False,
        ),
        budget=AgentBudgetUsage(
            steps_used=1,
            tool_calls_used=0,
            tool_attempts_used=0,
        ),
        trace=[
            AgentTraceEvent(
                sequence=1,
                elapsed_ms=0,
                state="created",
                event="run_started",
            ),
            AgentTraceEvent(
                sequence=2,
                elapsed_ms=1,
                state="failed",
                event="run_failed",
                details={"error_code": "permission_denied"},
            ),
        ],
    )


def _metrics(
    results: list[RuntimeGovernanceCaseResult],
) -> RuntimeGovernanceEvaluationMetrics:
    pre_execution = [
        item
        for item in results
        if item.category in {"registration", "input_integrity", "confirmation"}
    ]
    invalid_output = [item for item in results if item.category == "output_validation"]
    observability = [item for item in results if item.category == "observability"]

    def rate(items: list[RuntimeGovernanceCaseResult], predicate) -> float:
        return round(sum(predicate(item) for item in items) / len(items), 4) if items else 0

    ordered_latency = sorted(item.latency_ms for item in results)
    p95_index = max(0, math.ceil(0.95 * len(ordered_latency)) - 1)
    return RuntimeGovernanceEvaluationMetrics(
        expectation_pass_rate=round(sum(item.passed for item in results) / len(results), 4),
        pre_execution_block_rate=rate(
            pre_execution,
            lambda item: item.actual.blocked and not item.actual.tool_executed,
        ),
        invalid_output_block_rate=rate(
            invalid_output,
            lambda item: item.actual.blocked and item.actual.output_accepted is False,
        ),
        observability_failure_isolation_rate=rate(
            observability,
            lambda item: (
                item.actual.business_continued
                and item.actual.persistence_failed
                and item.actual.error_redacted
            ),
        ),
        prohibited_tool_execution_count=sum(
            item.actual.tool_executed for item in pre_execution
        ),
        sensitive_error_leak_count=sum(
            not item.actual.error_redacted for item in observability
        ),
        p95_latency_ms=ordered_latency[p95_index],
        category_counts=dict(Counter(item.category for item in results)),
    )


def _suite_hash(suite: RuntimeGovernanceEvaluationSuite) -> str:
    payload = json.dumps(
        suite.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
