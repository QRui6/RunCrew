from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runcrew.domain.agent import (
    AgentBudgetUsage,
    AgentRunError,
    AgentTraceEvent,
    ReviewAgentRunResult,
)
from runcrew.domain.coach import (
    CoachAgentRunResult,
    CoachBudgetUsage,
    CoachRunError,
    CoachTraceEvent,
)
from runcrew.domain.runtime_observability import (
    RuntimeBudgetSnapshot,
    RuntimeMetricsSnapshot,
    RuntimeRun,
    RuntimeRunCapture,
    RuntimeRunList,
    RuntimeSpan,
)
from runcrew.services.runtime_observability import (
    RuntimeRunNotFoundError,
    RuntimeTraceService,
    capture_coach_runtime,
    capture_review_runtime,
)
from runcrew.storage.database import Database
from runcrew.storage.repositories import RuntimeRunRepository
from runcrew.web import DemoApplication, DemoDashboardService


ANCHOR = datetime(2026, 8, 20, 8, tzinfo=timezone.utc)


def review_failure(run_id: str = "review-runtime-1") -> ReviewAgentRunResult:
    return ReviewAgentRunResult(
        run_id=run_id,
        status="failed",
        termination_reason="permission_denied",
        error=AgentRunError(
            code="permission_denied",
            message="工具权限被拒绝。",
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
                state="planning",
                event="policy_action",
                details={
                    "action_type": "call_tool",
                    "prompt": "super-secret-prompt",
                },
            ),
            AgentTraceEvent(
                sequence=3,
                elapsed_ms=2,
                state="planning",
                event="tool_permission_checked",
                tool_name="delete_activity",
                details={
                    "allowed": False,
                    "manifest_hash": "a" * 64,
                    "raw_payload": "private-provider-payload",
                },
            ),
            AgentTraceEvent(
                sequence=4,
                elapsed_ms=3,
                state="failed",
                event="run_failed",
                details={"error_code": "permission_denied"},
            ),
        ],
    )


def coach_failure(run_id: str = "coach-runtime-1") -> CoachAgentRunResult:
    return CoachAgentRunResult(
        run_id=run_id,
        workflow_hash="b" * 64,
        status="failed",
        termination_reason="permission_denied",
        error=CoachRunError(
            code="permission_denied",
            message="职责节点越权。",
            retryable=False,
        ),
        budget=CoachBudgetUsage(
            steps_used=1,
            node_calls_used=0,
            node_attempts_used=0,
        ),
        trace=[
            CoachTraceEvent(
                sequence=1,
                elapsed_ms=0,
                state="created",
                event="run_started",
            ),
            CoachTraceEvent(
                sequence=2,
                elapsed_ms=1,
                state="routing",
                event="policy_action",
                node="execution_agent",
                tool_name="compare_training_execution",
                details={"action_type": "delegate_execution"},
            ),
            CoachTraceEvent(
                sequence=3,
                elapsed_ms=2,
                state="routing",
                event="node_permission_checked",
                node="execution_agent",
                tool_name="compare_training_execution",
                details={"allowed": False, "request_body": "private"},
            ),
            CoachTraceEvent(
                sequence=4,
                elapsed_ms=3,
                state="failed",
                event="run_failed",
                details={"error_code": "permission_denied"},
            ),
        ],
    )


def metric_capture(
    run_id: str,
    *,
    workflow: str,
    status: str,
    termination_reason: str,
    duration_ms: float,
    guardrail_status: str,
    tool_status: str | None,
    retry: bool = False,
) -> RuntimeRunCapture:
    tool_name = (
        "review_running_training"
        if workflow == "review_agent"
        else "compare_training_execution"
    )
    node = None if workflow == "review_agent" else "execution_agent"
    spans = [
        RuntimeSpan(
            span_id=f"{run_id}:root",
            run_id=run_id,
            sequence=0,
            name=f"{workflow}.run",
            kind="run",
            status="ok" if status == "succeeded" else "error",
            start_offset_ms=0,
            duration_ms=duration_ms,
        ),
        RuntimeSpan(
            span_id=f"{run_id}:guardrail",
            run_id=run_id,
            sequence=1,
            parent_span_id=f"{run_id}:root",
            name="tool_permission_checked",
            kind="guardrail",
            status=guardrail_status,
            start_offset_ms=1,
            duration_ms=0,
            node=node,
            tool_name=tool_name,
        ),
    ]
    if tool_status is not None:
        spans.append(
            RuntimeSpan(
                span_id=f"{run_id}:start",
                run_id=run_id,
                sequence=len(spans),
                parent_span_id=f"{run_id}:guardrail",
                name=(
                    "tool_call_started"
                    if workflow == "review_agent"
                    else "node_call_started"
                ),
                kind="tool",
                status="ok",
                start_offset_ms=2,
                duration_ms=duration_ms - 2,
                node=node,
                tool_name=tool_name,
                attempt=1,
            )
        )
        if retry:
            spans.append(
                RuntimeSpan(
                    span_id=f"{run_id}:retry",
                    run_id=run_id,
                    sequence=len(spans),
                    parent_span_id=f"{run_id}:start",
                    name="tool_call_retry_scheduled",
                    kind="retry",
                    status="ok",
                    start_offset_ms=3,
                    duration_ms=0,
                    node=node,
                    tool_name=tool_name,
                    attempt=1,
                )
            )
        spans.append(
            RuntimeSpan(
                span_id=f"{run_id}:terminal",
                run_id=run_id,
                sequence=len(spans),
                parent_span_id=f"{run_id}:start",
                name=(
                    f"tool_call_{tool_status}"
                    if workflow == "review_agent"
                    else f"node_call_{tool_status}"
                ),
                kind="tool",
                status="ok" if tool_status == "succeeded" else "error",
                start_offset_ms=duration_ms,
                duration_ms=0,
                node=node,
                tool_name=tool_name,
                attempt=1,
            )
        )
    run = RuntimeRun(
        run_id=run_id,
        workflow=workflow,
        workflow_version=f"{workflow}/1.0",
        status=status,
        termination_reason=termination_reason,
        duration_ms=duration_ms,
        budget=RuntimeBudgetSnapshot(
            steps_used=1,
            calls_used=1 if tool_status is not None else 0,
            attempts_used=1 if tool_status is not None else 0,
        ),
        span_count=len(spans),
        tool_call_count=1 if tool_status is not None else 0,
        retry_count=int(retry),
        trace_hash=("a" if run_id.endswith("1") else "b") * 64,
        recorded_at=ANCHOR - timedelta(hours=1),
        expires_at=ANCHOR + timedelta(days=29),
    )
    return RuntimeRunCapture(run=run, spans=spans)


def test_review_and_coach_map_to_same_redacted_runtime_contract() -> None:
    review = capture_review_runtime(
        review_failure(), recorded_at=ANCHOR, scope_ref="conversation-private-id"
    )
    coach = capture_coach_runtime(
        coach_failure(), recorded_at=ANCHOR, scope_ref="goal-private:plan-private"
    )

    assert review.run.workflow == "review_agent"
    assert coach.run.workflow == "coach_orchestrator"
    assert review.run.status == coach.run.status == "failed"
    assert review.spans[0].kind == coach.spans[0].kind == "run"
    assert all(
        item.parent_span_id in {span.span_id for span in capture.spans}
        for capture in (review, coach)
        for item in capture.spans[1:]
    )
    serialized = review.model_dump_json() + coach.model_dump_json()
    assert "super-secret-prompt" not in serialized
    assert "private-provider-payload" not in serialized
    assert "conversation-private-id" not in serialized
    assert "goal-private" not in serialized


def test_runtime_repository_is_idempotent_and_rejects_trace_rewrite(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'runtime.db').as_posix()}")
    database.create_schema()
    service = RuntimeTraceService(database, clock=lambda: ANCHOR)

    first = service.record_review(review_failure(), scope_ref="conversation-1")
    repeated = service.record_review(review_failure(), scope_ref="conversation-1")
    detail = service.get("review-runtime-1")
    recent = service.recent()

    assert first.persisted and first.created
    assert repeated.persisted and not repeated.created
    assert detail.run.trace_hash == recent.runs[0].trace_hash
    assert detail.run.scope_ref_hash and len(detail.run.scope_ref_hash) == 64

    changed = review_failure().model_copy(deep=True)
    changed.trace[1].details["action_type"] = "finish"
    conflict = service.record_review(changed, scope_ref="conversation-1")
    assert not conflict.persisted
    assert conflict.error_type == "ValueError"
    assert service.get("review-runtime-1").run.trace_hash == detail.run.trace_hash


def test_expired_runtime_is_removed_during_next_best_effort_write(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'retention.db').as_posix()}")
    database.create_schema()
    current = [ANCHOR]
    service = RuntimeTraceService(database, clock=lambda: current[0])
    service.record_review(review_failure("old-run"))

    current[0] = ANCHOR + timedelta(days=31)
    service.record_coach(coach_failure("fresh-run"))

    assert [item.run_id for item in service.recent().runs] == ["fresh-run"]
    try:
        service.get("old-run")
    except RuntimeRunNotFoundError:
        pass
    else:
        raise AssertionError("过期 Runtime Run 应被清理")


def test_runtime_persistence_failure_does_not_raise_to_agent_caller() -> None:
    class BrokenDatabase:
        def session(self):
            raise RuntimeError("private database failure")

    outcome = RuntimeTraceService(BrokenDatabase(), clock=lambda: ANCHOR).record_review(
        review_failure()
    )

    assert not outcome.persisted
    assert outcome.error_type == "RuntimeError"
    assert "private database failure" not in outcome.model_dump_json()


def test_runtime_read_only_api_lists_timeline_without_private_fields(tmp_path: Path) -> None:
    database_path = tmp_path / "api.db"
    database = Database(f"sqlite:///{database_path.as_posix()}")
    database.create_schema()
    runtime = RuntimeTraceService(database, clock=lambda: ANCHOR)
    runtime.record_review(review_failure(), scope_ref="private-conversation")
    application = DemoApplication(
        DemoDashboardService(database_path=database_path),
        runtime_service=runtime,
    )

    listing = application.handle("GET", "/api/runtime/runs?limit=10")
    detail = application.handle("GET", "/api/runtime/runs/review-runtime-1")
    blocked = application.handle("POST", "/api/runtime/runs")
    missing = application.handle("GET", "/api/runtime/runs/missing")
    metrics = application.handle("GET", "/api/runtime/metrics?window_days=7")
    blocked_metrics = application.handle("POST", "/api/runtime/metrics")
    governance = application.handle("GET", "/api/runtime/governance-evaluation")
    blocked_governance = application.handle(
        "POST", "/api/runtime/governance-evaluation"
    )

    assert listing.status == 200
    assert json.loads(listing.body)["runs"][0]["run_id"] == "review-runtime-1"
    assert detail.status == 200
    assert json.loads(detail.body)["spans"][0]["kind"] == "run"
    assert blocked.status == 405
    assert missing.status == 404
    assert metrics.status == 200
    assert json.loads(metrics.body)["overall"]["run_count"] == 1
    assert blocked_metrics.status == 405
    assert json.loads(governance.body)["passed_cases"] == 5
    assert blocked_governance.status == 405
    assert "private-conversation" not in detail.body.decode("utf-8")
    assert "super-secret-prompt" not in detail.body.decode("utf-8")


def test_runtime_metrics_use_documented_rates_groups_and_nearest_rank(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'metrics.db').as_posix()}")
    database.create_schema()
    captures = [
        metric_capture(
            "metric-1",
            workflow="review_agent",
            status="succeeded",
            termination_reason="completed",
            duration_ms=10,
            guardrail_status="ok",
            tool_status="succeeded",
        ),
        metric_capture(
            "metric-2",
            workflow="coach_orchestrator",
            status="budget_exhausted",
            termination_reason="step_budget_exhausted",
            duration_ms=100,
            guardrail_status="blocked",
            tool_status="failed",
            retry=True,
        ),
    ]
    with database.session() as session:
        repository = RuntimeRunRepository(session)
        for capture in captures:
            repository.save(capture)
        session.commit()

    snapshot = RuntimeTraceService(database, clock=lambda: ANCHOR).metrics(
        window_days=7
    )

    assert snapshot.overall.run_success.value == 0.5
    assert snapshot.overall.guardrail_rejection.value == 0.5
    assert snapshot.overall.tool_success.value == 0.5
    assert snapshot.overall.retry.value == 0.5
    assert snapshot.overall.budget_exhaustion.value == 0.5
    assert snapshot.overall.latency.p50_ms == 10
    assert snapshot.overall.latency.p95_ms == 100
    assert [item.key for item in snapshot.workflows] == [
        "coach_orchestrator",
        "review_agent",
    ]
    assert {item.key for item in snapshot.tools} == {
        "compare_training_execution",
        "review_running_training",
    }
    assert {item.key for item in snapshot.roles} == {
        "execution_agent",
        "review_agent",
    }
    assert "best-effort" in snapshot.coverage_note


def test_runtime_metrics_zero_sample_is_explicit_not_fake_zero(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'empty-metrics.db').as_posix()}")
    database.create_schema()

    snapshot = RuntimeTraceService(database, clock=lambda: ANCHOR).metrics()

    assert snapshot.overall.run_count == 0
    assert snapshot.overall.run_success.value is None
    assert snapshot.overall.latency.p50_ms is None
    assert snapshot.termination_reasons == []


def test_engineering_observability_page_is_read_only_and_dom_safe(tmp_path: Path) -> None:
    database_path = tmp_path / "engineering.db"
    database = Database(f"sqlite:///{database_path.as_posix()}")
    database.create_schema()
    application = DemoApplication(DemoDashboardService(database_path=database_path))

    html = application.handle("GET", "/engineering").body.decode("utf-8")
    script = application.handle("GET", "/assets/app.js").body.decode("utf-8")
    style = application.handle("GET", "/assets/styles.css").body.decode("utf-8")

    assert "运行观测" in html
    assert "本地只读" in html
    assert "/api/runtime/metrics" in script
    assert "/api/runtime/runs" in script
    assert "/api/runtime/governance-evaluation" in script
    assert "innerHTML" not in script
    assert "trace-drawer" in style
    assert "/assets/styles.css?v=20260820-5" in html
    assert subprocess.run(
        ["node", "--check", "src/runcrew/web/static/app.js"],
        check=False,
        capture_output=True,
        text=True,
    ).returncode == 0


def test_runtime_observability_schemas_are_current() -> None:
    directory = Path("schemas/runtime-observability")
    assert json.loads((directory / "run.schema.json").read_text("utf-8")) == RuntimeRun.model_json_schema()
    assert json.loads((directory / "span.schema.json").read_text("utf-8")) == RuntimeSpan.model_json_schema()
    assert json.loads((directory / "capture.schema.json").read_text("utf-8")) == RuntimeRunCapture.model_json_schema()
    assert json.loads((directory / "run-list.schema.json").read_text("utf-8")) == RuntimeRunList.model_json_schema()
    assert json.loads((directory / "metrics.schema.json").read_text("utf-8")) == RuntimeMetricsSnapshot.model_json_schema()
