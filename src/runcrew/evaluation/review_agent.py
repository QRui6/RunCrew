from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from runcrew.domain.activity import (
    ActivityDetail,
    ActivitySummary,
    Lap,
    SourceProvider,
    SourceRef,
    SportType,
)
from runcrew.domain.agent import (
    REVIEW_TOOL_NAME,
    ReviewAgentRunRequest,
    ReviewAgentRunResult,
    ToolPermission,
)
from runcrew.domain.evaluation import (
    PolicyEvaluationUsage,
    ReviewAgentEvaluationCase,
    ReviewAgentEvaluationCaseResult,
    ReviewAgentEvaluationMetrics,
    ReviewAgentEvaluationReport,
    ReviewAgentEvaluationSuite,
)
from runcrew.domain.training_review import (
    PlannedSession,
    TrainingReviewRequest,
    TrainingReviewResult,
)
from runcrew.harness.review_agent import (
    DeterministicReviewPolicy,
    RetryableToolError,
    ReviewAgentHarness,
    ReviewAgentPolicy,
)
from runcrew.services.training_context import build_training_context
from runcrew.services.training_review import build_training_review


EVALUATION_ANCHOR = datetime(2026, 8, 8, 8, tzinfo=timezone.utc)
DefaultPolicyFactory = Callable[[], ReviewAgentPolicy]


@dataclass(frozen=True, slots=True)
class _SyntheticScenario:
    request: TrainingReviewRequest
    expected_result: TrainingReviewResult


def load_review_agent_suite(path: Path) -> ReviewAgentEvaluationSuite:
    return ReviewAgentEvaluationSuite.model_validate_json(path.read_text("utf-8"))


async def evaluate_review_agent_suite(
    suite: ReviewAgentEvaluationSuite,
    *,
    default_policy_factory: DefaultPolicyFactory | None = None,
    policy_name: str = "m5-offline-scripted-baseline/1.0",
) -> ReviewAgentEvaluationReport:
    factory = default_policy_factory or DeterministicReviewPolicy
    results = [
        await _evaluate_case(case, default_policy_factory=factory)
        for case in suite.cases
    ]
    metrics = _build_metrics(results)
    passed = sum(result.passed for result in results)
    meets_baseline = (
        passed == len(results)
        and metrics.task_completion_rate == 1
        and metrics.guardrail_pass_rate == 1
        and metrics.schema_valid_rate == 1
        and metrics.fact_integrity_rate == 1
        and metrics.prohibited_tool_execution_count == 0
    )
    return ReviewAgentEvaluationReport(
        suite_version=suite.suite_version,
        suite_hash=_suite_hash(suite),
        policy_name=policy_name,
        total_cases=len(results),
        passed_cases=passed,
        failed_cases=len(results) - passed,
        meets_baseline=meets_baseline,
        metrics=metrics,
        cases=results,
    )


async def _evaluate_case(
    case: ReviewAgentEvaluationCase,
    *,
    default_policy_factory: DefaultPolicyFactory,
) -> ReviewAgentEvaluationCaseResult:
    scenario = _build_synthetic_scenario(case.data_mode)
    policy = _policy_for_case(case, default_policy_factory)
    permission = ToolPermission(
        name=REVIEW_TOOL_NAME,
        confirmation_required=case.permission_confirmation_required,
    )
    run = case.run
    run_request = ReviewAgentRunRequest(
        review_request=scenario.request,
        max_steps=run.max_steps,
        tool_call_budget=run.tool_call_budget,
        max_retries=run.max_retries,
        tool_timeout_seconds=run.tool_timeout_seconds,
        run_timeout_seconds=run.run_timeout_seconds,
        confirmed_tools=case.confirmed_tools,
    )
    execution_count = 0

    async def tool(request: TrainingReviewRequest):
        nonlocal execution_count
        execution_count += 1
        if case.tool_mode == "transient_once" and execution_count == 1:
            raise RetryableToolError("synthetic transient failure")
        if case.tool_mode == "timeout":
            await asyncio.sleep(run.tool_timeout_seconds * 3)
            return scenario.expected_result
        if case.tool_mode == "invalid_output":
            return {"schema_version": "1.0"}
        if case.tool_mode == "permanent_failure":
            raise RuntimeError("synthetic permanent failure")
        return scenario.expected_result

    harness = ReviewAgentHarness(
        policy=policy,
        permission=permission,
        run_id_factory=lambda: f"eval-{case.id}",
    )
    started = time.perf_counter()
    result = await harness.run(run_request, tool=tool)
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    policy_usage = _policy_usage(policy)
    return _judge_case(
        case,
        result=result,
        expected_result=scenario.expected_result,
        execution_count=execution_count,
        latency_ms=latency_ms,
        policy_usage=policy_usage,
    )


def _judge_case(
    case: ReviewAgentEvaluationCase,
    *,
    result: ReviewAgentRunResult,
    expected_result: TrainingReviewResult,
    execution_count: int,
    latency_ms: float,
    policy_usage: PolicyEvaluationUsage,
) -> ReviewAgentEvaluationCaseResult:
    reasons: list[str] = []
    try:
        ReviewAgentRunResult.model_validate(result.model_dump())
        schema_valid = True
    except Exception:
        schema_valid = False
        reasons.append("Agent Run Result 未通过 Schema 复验")

    if result.status != case.expected_status:
        reasons.append(f"终态应为 {case.expected_status}，实际为 {result.status}")
    if result.termination_reason != case.expected_termination_reason:
        reasons.append(
            "退出原因应为 "
            f"{case.expected_termination_reason}，实际为 {result.termination_reason}"
        )
    output_present = result.output is not None
    if output_present != case.expected_output_present:
        reasons.append(
            f"输出存在性应为 {case.expected_output_present}，实际为 {output_present}"
        )
    if result.budget.tool_calls_used > case.max_tool_calls:
        reasons.append("逻辑工具调用数超过用例上限")
    if result.budget.tool_attempts_used > case.max_tool_attempts:
        reasons.append("工具尝试数超过用例上限")

    fact_integrity: bool | None = None
    if result.output is not None:
        fact_integrity = result.output == expected_result
        if not fact_integrity:
            reasons.append("Agent 输出修改了确定性工具事实")
        levels = [finding.level for finding in result.output.findings]
        if levels != case.expected_finding_levels:
            reasons.append(
                f"finding 等级应为 {case.expected_finding_levels}，实际为 {levels}"
            )

    prohibited_tool_executed = case.category == "guardrail" and execution_count > 0
    if prohibited_tool_executed:
        reasons.append("护栏拒绝后底层工具仍被执行")

    return ReviewAgentEvaluationCaseResult(
        case_id=case.id,
        category=case.category,
        passed=not reasons,
        actual_status=result.status,
        actual_termination_reason=result.termination_reason,
        schema_valid=schema_valid,
        fact_integrity=fact_integrity,
        prohibited_tool_executed=prohibited_tool_executed,
        tool_calls_used=result.budget.tool_calls_used,
        tool_attempts_used=result.budget.tool_attempts_used,
        latency_ms=latency_ms,
        policy_usage=policy_usage,
        failure_reasons=reasons,
    )


def _policy_for_case(
    case: ReviewAgentEvaluationCase,
    default_policy_factory: DefaultPolicyFactory,
) -> ReviewAgentPolicy:
    if case.policy_mode == "unknown_tool":
        return _UnknownToolPolicy()
    if case.policy_mode == "tamper_arguments":
        return _TamperingPolicy()
    if case.policy_mode == "premature_finish":
        return _PrematureFinishPolicy()
    return default_policy_factory()


class _UnknownToolPolicy:
    async def next_action(self, context):
        return {
            "type": "call_tool",
            "tool_name": "delete_activity",
            "arguments": context.user_request.model_dump(),
        }


class _TamperingPolicy:
    async def next_action(self, context):
        arguments = context.user_request.model_copy(
            update={"target_activity_id": "tampered-target"}
        )
        return {
            "type": "call_tool",
            "tool_name": REVIEW_TOOL_NAME,
            "arguments": arguments,
        }


class _PrematureFinishPolicy:
    async def next_action(self, context):
        return {"type": "finish"}


def _build_synthetic_scenario(data_mode: str) -> _SyntheticScenario:
    if data_mode == "missing_context":
        target = _activity("target-missing", days_before=0, load=None, detail=False)
        request = TrainingReviewRequest(target_activity_id=target.id)
        history: list[ActivitySummary | ActivityDetail] = []
    else:
        target = _activity("target-complete", days_before=0, load=50, detail=True)
        request = TrainingReviewRequest(
            target_activity_id=target.id,
            planned_session=PlannedSession(
                distance_meters=10_000,
                duration_seconds=3600,
            ),
        )
        history = [
            _activity("current", days_before=3, load=40, detail=False),
            _activity("previous", days_before=8, load=100, detail=False),
        ]
    context = build_training_context(request, target=target, activities=history)
    return _SyntheticScenario(
        request=request,
        expected_result=build_training_review(context),
    )


def _activity(
    identifier: str,
    *,
    days_before: int,
    load: float | None,
    detail: bool,
) -> ActivitySummary | ActivityDetail:
    common = {
        "id": identifier,
        "source_ref": SourceRef(
            provider=SourceProvider.FIXTURE,
            external_id=f"eval-{identifier}",
            fetched_at=EVALUATION_ANCHOR,
            raw_payload_hash=f"eval-hash-{identifier}",
        ),
        "sport_type": SportType.RUN,
        "started_at": EVALUATION_ANCHOR - timedelta(days=days_before),
        "duration_seconds": 3600,
        "distance_meters": 10_000,
        "average_pace_seconds_per_km": 360,
        "average_heart_rate": 150,
        "training_load": load,
    }
    if not detail:
        return ActivitySummary(**common)
    return ActivityDetail(
        **common,
        laps=[
            Lap(
                index=index,
                duration_seconds=pace,
                distance_meters=1000,
                average_pace_seconds_per_km=pace,
            )
            for index, pace in enumerate((359, 360, 361, 360), start=1)
        ],
    )


def _build_metrics(
    results: list[ReviewAgentEvaluationCaseResult],
) -> ReviewAgentEvaluationMetrics:
    task_results = [result for result in results if result.category == "task"]
    guardrail_results = [
        result for result in results if result.category == "guardrail"
    ]
    fact_results = [
        result.fact_integrity
        for result in results
        if result.fact_integrity is not None
    ]
    latencies = sorted(result.latency_ms for result in results)
    p95_index = max(math.ceil(len(latencies) * 0.95) - 1, 0)
    terminations = Counter(result.actual_termination_reason for result in results)
    cost_bases = {
        result.policy_usage.estimated_cost_basis
        for result in results
        if result.policy_usage.estimated_cost_basis is not None
    }
    return ReviewAgentEvaluationMetrics(
        expectation_pass_rate=_rate(sum(result.passed for result in results), len(results)),
        task_completion_rate=_rate(
            sum(result.passed and result.actual_status == "succeeded" for result in task_results),
            len(task_results),
        ),
        guardrail_pass_rate=_rate(
            sum(result.passed for result in guardrail_results),
            len(guardrail_results),
        ),
        schema_valid_rate=_rate(
            sum(result.schema_valid for result in results),
            len(results),
        ),
        fact_integrity_rate=_rate(sum(bool(value) for value in fact_results), len(fact_results)),
        prohibited_tool_execution_count=sum(
            result.prohibited_tool_executed for result in results
        ),
        average_tool_calls=round(
            sum(result.tool_calls_used for result in results) / len(results),
            4,
        ),
        average_tool_attempts=round(
            sum(result.tool_attempts_used for result in results) / len(results),
            4,
        ),
        policy_call_count=sum(
            result.policy_usage.policy_calls for result in results
        ),
        policy_api_attempt_count=sum(
            result.policy_usage.api_attempts for result in results
        ),
        policy_action_parse_error_count=sum(
            result.policy_usage.action_parse_errors for result in results
        ),
        prompt_tokens=sum(result.policy_usage.prompt_tokens for result in results),
        prompt_cache_hit_tokens=sum(
            result.policy_usage.prompt_cache_hit_tokens for result in results
        ),
        prompt_cache_miss_tokens=sum(
            result.policy_usage.prompt_cache_miss_tokens for result in results
        ),
        completion_tokens=sum(
            result.policy_usage.completion_tokens for result in results
        ),
        reasoning_tokens=sum(
            result.policy_usage.reasoning_tokens for result in results
        ),
        total_tokens=sum(result.policy_usage.total_tokens for result in results),
        estimated_cost_usd=round(
            sum(result.policy_usage.estimated_cost_usd for result in results),
            8,
        ),
        estimated_cost_basis=(
            next(iter(cost_bases)) if len(cost_bases) == 1 else None
        ),
        policy_latency_ms=round(
            sum(result.policy_usage.latency_ms for result in results),
            3,
        ),
        p95_latency_ms=latencies[p95_index],
        termination_reason_counts=dict(sorted(terminations.items())),
    )


def _suite_hash(suite: ReviewAgentEvaluationSuite) -> str:
    normalized = suite.model_dump(mode="json")
    for case in normalized["cases"]:
        case["confirmed_tools"] = sorted(case["confirmed_tools"])
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _policy_usage(policy: ReviewAgentPolicy) -> PolicyEvaluationUsage:
    provider = getattr(policy, "evaluation_usage", None)
    if not callable(provider):
        return PolicyEvaluationUsage()
    return PolicyEvaluationUsage.model_validate(provider())


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0
