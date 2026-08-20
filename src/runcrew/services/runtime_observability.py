from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from runcrew.domain.agent import AgentTraceEvent, ReviewAgentRunResult
from runcrew.domain.coach import CoachAgentRunResult, CoachTraceEvent
from runcrew.domain.runtime_observability import (
    RuntimeBudgetSnapshot,
    RuntimeBreakdownItem,
    RuntimeInvocationGroup,
    RuntimeLatencySummary,
    RuntimeMetricGroup,
    RuntimeMetricSet,
    RuntimeMetricsSnapshot,
    RuntimePersistenceOutcome,
    RuntimeRate,
    RuntimeRun,
    RuntimeRunCapture,
    RuntimeRunList,
    RuntimeSpan,
)
from runcrew.storage.database import Database
from runcrew.storage.repositories import RuntimeRunRepository


RETENTION_DAYS = 30
METRIC_SAMPLE_LIMIT = 500
_RUN_EVENTS = {
    "run_started",
    "run_completed",
    "run_failed",
    "run_timed_out",
    "budget_exhausted",
}
_SAFE_ATTRIBUTE_KEYS = {
    "instruction_version",
    "max_steps",
    "tool_call_budget",
    "node_call_budget",
    "action_type",
    "allowed",
    "access",
    "can_persist",
    "can_approve",
    "confirmation_required",
    "guardrail_schema_version",
    "manifest_hash",
    "input_hash_match",
    "rules",
    "error_code",
    "error_type",
    "retryable",
    "validation_error_count",
    "guardrail_rule_id",
    "guardrail_outcome",
    "input_hash",
    "ruleset_version",
    "schema_version",
    "handoff_sequence",
    "context_fields",
    "request_hash",
    "output_schema",
    "reason",
    "required_user_action",
    "requested_timeout_seconds",
    "maximum_timeout_seconds",
    "requested_retries",
    "maximum_retries",
    "model",
    "model_calls",
    "api_attempts",
    "action_parse_errors",
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cache_hit_tokens",
    "cache_miss_tokens",
    "model_latency_ms",
    "estimated_cost_usd",
    "pricing_version",
}


class RuntimeObservabilityError(RuntimeError):
    pass


class RuntimeRunNotFoundError(RuntimeObservabilityError):
    pass


def _canonical_hash(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _scope_hash(scope_ref: str | None) -> str | None:
    if not scope_ref:
        return None
    return hashlib.sha256(scope_ref.encode("utf-8")).hexdigest()


def _safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:200]
    if isinstance(value, list):
        return [_safe_value(item) for item in value[:30]]
    if isinstance(value, dict):
        return {
            str(key)[:80]: _safe_value(item)
            for key, item in list(value.items())[:30]
        }
    return type(value).__name__


def _safe_attributes(details: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _safe_value(value)
        for key, value in details.items()
        if key in _SAFE_ATTRIBUTE_KEYS
    }


def _span_kind(event: str) -> str:
    if event == "policy_action":
        return "policy"
    if "permission_checked" in event:
        return "guardrail"
    if event == "handoff_prepared":
        return "handoff"
    if "retry_scheduled" in event:
        return "retry"
    if "call_" in event:
        return "tool"
    if "validation" in event or "validated" in event:
        return "validation"
    if "confirmation" in event:
        return "approval"
    return "lifecycle"


def _span_status(event: str, details: dict[str, Any]) -> str:
    if "failed" in event or "timed_out" in event or event == "budget_exhausted":
        return "error"
    if details.get("allowed") is False or "confirmation_requested" in event:
        return "blocked"
    return "ok"


def _event_duration(
    events: Sequence[AgentTraceEvent | CoachTraceEvent],
    index: int,
) -> float:
    current = events[index]
    pairs = {
        "tool_call_started": {"tool_call_succeeded", "tool_call_failed"},
        "node_call_started": {"node_call_succeeded", "node_call_failed"},
        "output_validation_started": {"output_validated"},
    }
    terminal_events = pairs.get(current.event)
    if terminal_events is None:
        return 0.0
    for candidate in events[index + 1 :]:
        if candidate.event not in terminal_events:
            continue
        if candidate.tool_name != current.tool_name:
            continue
        if current.attempt is not None and candidate.attempt != current.attempt:
            continue
        candidate_node = getattr(candidate, "node", None)
        current_node = getattr(current, "node", None)
        if current_node is not None and candidate_node != current_node:
            continue
        return round(max(candidate.elapsed_ms - current.elapsed_ms, 0), 3)
    return 0.0


def _build_spans(
    *,
    run_id: str,
    workflow: str,
    status: str,
    events: Sequence[AgentTraceEvent | CoachTraceEvent],
) -> list[RuntimeSpan]:
    duration_ms = max((item.elapsed_ms for item in events), default=0)
    root_id = f"{run_id}:root"
    root_status = "ok" if status == "succeeded" else (
        "blocked" if status in {"awaiting_confirmation", "blocked"} else "error"
    )
    spans = [
        RuntimeSpan(
            span_id=root_id,
            run_id=run_id,
            sequence=0,
            name=f"{workflow}.run",
            kind="run",
            status=root_status,
            start_offset_ms=0,
            duration_ms=duration_ms,
        )
    ]
    last_policy = root_id
    last_guardrail = root_id
    last_handoff: dict[str, str] = {}
    active_calls: dict[tuple[str | None, str | None, int | None], str] = {}

    for index, event in enumerate(events):
        if event.event in _RUN_EVENTS:
            continue
        node = getattr(event, "node", None)
        key = (node, event.tool_name, event.attempt)
        kind = _span_kind(event.event)
        if kind == "policy":
            parent_id = root_id
        elif kind == "guardrail":
            parent_id = last_policy
        elif kind == "handoff":
            parent_id = last_policy
        elif kind in {"tool", "retry", "validation"}:
            parent_id = (
                active_calls.get(key)
                or (last_handoff.get(node) if node else None)
                or last_guardrail
                or last_policy
            )
        else:
            parent_id = root_id
        span_id = f"{run_id}:{event.sequence}"
        span = RuntimeSpan(
            span_id=span_id,
            run_id=run_id,
            sequence=len(spans),
            source_sequence=event.sequence,
            parent_span_id=parent_id,
            name=event.event,
            kind=kind,
            status=_span_status(event.event, event.details),
            start_offset_ms=event.elapsed_ms,
            duration_ms=_event_duration(events, index),
            node=node,
            tool_name=event.tool_name,
            attempt=event.attempt,
            attributes=_safe_attributes(event.details),
        )
        spans.append(span)
        if kind == "policy":
            last_policy = span_id
        elif kind == "guardrail":
            last_guardrail = span_id
        elif kind == "handoff" and node:
            last_handoff[node] = span_id
        elif event.event in {"tool_call_started", "node_call_started"}:
            active_calls[key] = span_id
    return spans


def capture_review_runtime(
    result: ReviewAgentRunResult,
    *,
    recorded_at: datetime,
    scope_ref: str | None = None,
) -> RuntimeRunCapture:
    status = result.status
    spans = _build_spans(
        run_id=result.run_id,
        workflow="review_agent",
        status=status,
        events=result.trace,
    )
    run = RuntimeRun(
        run_id=result.run_id,
        workflow="review_agent",
        workflow_version="review-agent-instructions/1.0",
        status=status,
        termination_reason=result.termination_reason,
        duration_ms=max(item.elapsed_ms for item in result.trace),
        budget=RuntimeBudgetSnapshot(
            steps_used=result.budget.steps_used,
            calls_used=result.budget.tool_calls_used,
            attempts_used=result.budget.tool_attempts_used,
        ),
        span_count=len(spans),
        tool_call_count=sum(
            item.event == "tool_call_started" for item in result.trace
        ),
        retry_count=sum(
            item.event == "tool_call_retry_scheduled" for item in result.trace
        ),
        trace_hash=_canonical_hash(result.trace),
        scope_ref_hash=_scope_hash(scope_ref),
        recorded_at=recorded_at,
        expires_at=recorded_at + timedelta(days=RETENTION_DAYS),
    )
    return RuntimeRunCapture(run=run, spans=spans)


def capture_coach_runtime(
    result: CoachAgentRunResult,
    *,
    recorded_at: datetime,
    scope_ref: str | None = None,
) -> RuntimeRunCapture:
    status = (
        "awaiting_confirmation"
        if result.status == "awaiting_user_confirmation"
        else result.status
    )
    spans = _build_spans(
        run_id=result.run_id,
        workflow="coach_orchestrator",
        status=status,
        events=result.trace,
    )
    run = RuntimeRun(
        run_id=result.run_id,
        workflow="coach_orchestrator",
        workflow_version=result.workflow_version,
        status=status,
        termination_reason=result.termination_reason,
        duration_ms=max(item.elapsed_ms for item in result.trace),
        budget=RuntimeBudgetSnapshot(
            steps_used=result.budget.steps_used,
            calls_used=result.budget.node_calls_used,
            attempts_used=result.budget.node_attempts_used,
        ),
        span_count=len(spans),
        tool_call_count=sum(
            item.event == "node_call_started" for item in result.trace
        ),
        retry_count=sum(
            item.event == "node_call_retry_scheduled" for item in result.trace
        ),
        trace_hash=_canonical_hash(result.trace),
        scope_ref_hash=_scope_hash(scope_ref),
        recorded_at=recorded_at,
        expires_at=recorded_at + timedelta(days=RETENTION_DAYS),
    )
    return RuntimeRunCapture(run=run, spans=spans)


class RuntimeTraceService:
    """持久化与读取统一 Runtime Trace；写入永不向业务调用方抛错。"""

    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def record_review(
        self, result: ReviewAgentRunResult, *, scope_ref: str | None = None
    ) -> RuntimePersistenceOutcome:
        return self._persist(
            capture_review_runtime(
                result,
                recorded_at=self.clock(),
                scope_ref=scope_ref,
            )
        )

    def record_coach(
        self, result: CoachAgentRunResult, *, scope_ref: str | None = None
    ) -> RuntimePersistenceOutcome:
        return self._persist(
            capture_coach_runtime(
                result,
                recorded_at=self.clock(),
                scope_ref=scope_ref,
            )
        )

    def _persist(self, capture: RuntimeRunCapture) -> RuntimePersistenceOutcome:
        try:
            with self.database.session() as session:
                repository = RuntimeRunRepository(session)
                repository.delete_expired(now=capture.run.recorded_at)
                created = repository.save(capture)
                session.commit()
            return RuntimePersistenceOutcome(
                run_id=capture.run.run_id,
                persisted=True,
                created=created,
            )
        except Exception as error:
            return RuntimePersistenceOutcome(
                run_id=capture.run.run_id,
                persisted=False,
                error_type=type(error).__name__,
            )

    def recent(self, *, limit: int = 20, workflow: str | None = None) -> RuntimeRunList:
        try:
            with self.database.session() as session:
                runs = RuntimeRunRepository(session).recent(
                    limit=limit,
                    workflow=workflow,
                    now=self.clock(),
                )
            return RuntimeRunList(runs=runs)
        except Exception as error:
            raise RuntimeObservabilityError("Runtime 运行记录读取失败。") from error

    def get(self, run_id: str) -> RuntimeRunCapture:
        try:
            with self.database.session() as session:
                capture = RuntimeRunRepository(session).get(
                    run_id,
                    now=self.clock(),
                )
        except Exception as error:
            raise RuntimeObservabilityError("Runtime 运行详情读取失败。") from error
        if capture is None:
            raise RuntimeRunNotFoundError("Runtime 运行记录不存在或已过期。")
        return capture

    def metrics(self, *, window_days: int = 30) -> RuntimeMetricsSnapshot:
        if not 1 <= window_days <= RETENTION_DAYS:
            raise ValueError("Runtime 指标窗口只允许1到30天。")
        ended_at = self.clock()
        started_at = ended_at - timedelta(days=window_days)
        try:
            with self.database.session() as session:
                captures, truncated = RuntimeRunRepository(session).between(
                    started_at=started_at,
                    ended_at=ended_at,
                    limit=METRIC_SAMPLE_LIMIT,
                )
        except Exception as error:
            raise RuntimeObservabilityError("Runtime 指标读取失败。") from error
        return calculate_runtime_metrics(
            captures,
            generated_at=ended_at,
            window_days=window_days,
            truncated=truncated,
        )


def _rate(numerator: int, denominator: int) -> RuntimeRate:
    return RuntimeRate(
        numerator=numerator,
        denominator=denominator,
        value=round(numerator / denominator, 4) if denominator else None,
    )


def _nearest_rank(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 3)


def _metric_set(captures: Sequence[RuntimeRunCapture]) -> RuntimeMetricSet:
    spans = [span for capture in captures for span in capture.spans]
    guardrails = [span for span in spans if span.kind == "guardrail"]
    attempts = [
        span
        for span in spans
        if span.name in {"tool_call_started", "node_call_started"}
    ]
    successes = [
        span
        for span in spans
        if span.name in {"tool_call_succeeded", "node_call_succeeded"}
    ]
    retries = [span for span in spans if span.kind == "retry"]
    durations = [capture.run.duration_ms for capture in captures]
    return RuntimeMetricSet(
        run_count=len(captures),
        run_success=_rate(
            sum(capture.run.status == "succeeded" for capture in captures),
            len(captures),
        ),
        guardrail_rejection=_rate(
            sum(span.status == "blocked" for span in guardrails),
            len(guardrails),
        ),
        tool_success=_rate(len(successes), len(attempts)),
        retry=_rate(len(retries), len(attempts)),
        budget_exhaustion=_rate(
            sum(capture.run.status == "budget_exhausted" for capture in captures),
            len(captures),
        ),
        latency=RuntimeLatencySummary(
            sample_count=len(durations),
            p50_ms=_nearest_rank(durations, 0.5),
            p95_ms=_nearest_rank(durations, 0.95),
            maximum_ms=round(max(durations), 3) if durations else None,
        ),
    )


def _invocation_groups(
    captures: Sequence[RuntimeRunCapture],
    *,
    dimension: str,
) -> list[RuntimeInvocationGroup]:
    counters: dict[str, Counter[str]] = defaultdict(Counter)
    for capture in captures:
        for span in capture.spans:
            if dimension == "tool":
                key = span.tool_name
            else:
                key = span.node or (
                    "review_agent" if capture.run.workflow == "review_agent" else None
                )
            if key is None:
                continue
            if span.name in {"tool_call_started", "node_call_started"}:
                counters[key]["attempt"] += 1
            if span.name in {"tool_call_succeeded", "node_call_succeeded"}:
                counters[key]["success"] += 1
            if span.kind == "retry":
                counters[key]["retry"] += 1
            if span.kind == "guardrail":
                counters[key]["guardrail"] += 1
                if span.status == "blocked":
                    counters[key]["rejected"] += 1
    return [
        RuntimeInvocationGroup(
            key=key,
            attempt_count=counts["attempt"],
            success=_rate(counts["success"], counts["attempt"]),
            retry=_rate(counts["retry"], counts["attempt"]),
            guardrail_rejection=_rate(
                counts["rejected"], counts["guardrail"]
            ),
        )
        for key, counts in sorted(counters.items())
    ]


def calculate_runtime_metrics(
    captures: Sequence[RuntimeRunCapture],
    *,
    generated_at: datetime,
    window_days: int,
    truncated: bool = False,
) -> RuntimeMetricsSnapshot:
    started_at = generated_at - timedelta(days=window_days)
    grouped_workflows: dict[str, list[RuntimeRunCapture]] = defaultdict(list)
    grouped_versions: dict[str, list[RuntimeRunCapture]] = defaultdict(list)
    termination_counts: Counter[str] = Counter()
    for capture in captures:
        grouped_workflows[capture.run.workflow].append(capture)
        grouped_versions[capture.run.workflow_version].append(capture)
        termination_counts[capture.run.termination_reason] += 1
    total = len(captures)
    return RuntimeMetricsSnapshot(
        generated_at=generated_at,
        window_days=window_days,
        window_started_at=started_at,
        window_ended_at=generated_at,
        sample_limit=METRIC_SAMPLE_LIMIT,
        truncated=truncated,
        coverage_note=(
            "仅统计成功写入且仍在30天保留期内的 Review/Coach Runtime；"
            "best-effort 写入失败与离线评测运行不在本样本中。"
        ),
        overall=_metric_set(captures),
        workflows=[
            RuntimeMetricGroup(
                dimension="workflow",
                key=key,
                metrics=_metric_set(items),
            )
            for key, items in sorted(grouped_workflows.items())
        ],
        workflow_versions=[
            RuntimeMetricGroup(
                dimension="workflow_version",
                key=key,
                metrics=_metric_set(items),
            )
            for key, items in sorted(grouped_versions.items())
        ],
        tools=_invocation_groups(captures, dimension="tool"),
        roles=_invocation_groups(captures, dimension="role"),
        termination_reasons=[
            RuntimeBreakdownItem(
                key=key,
                count=count,
                rate=round(count / total, 4) if total else 0,
            )
            for key, count in sorted(termination_counts.items())
        ],
    )
