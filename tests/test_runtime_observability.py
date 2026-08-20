from __future__ import annotations

import json
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

    assert listing.status == 200
    assert json.loads(listing.body)["runs"][0]["run_id"] == "review-runtime-1"
    assert detail.status == 200
    assert json.loads(detail.body)["spans"][0]["kind"] == "run"
    assert blocked.status == 405
    assert missing.status == 404
    assert "private-conversation" not in detail.body.decode("utf-8")
    assert "super-secret-prompt" not in detail.body.decode("utf-8")


def test_runtime_observability_schemas_are_current() -> None:
    directory = Path("schemas/runtime-observability")
    assert json.loads((directory / "run.schema.json").read_text("utf-8")) == RuntimeRun.model_json_schema()
    assert json.loads((directory / "span.schema.json").read_text("utf-8")) == RuntimeSpan.model_json_schema()
    assert json.loads((directory / "capture.schema.json").read_text("utf-8")) == RuntimeRunCapture.model_json_schema()
    assert json.loads((directory / "run-list.schema.json").read_text("utf-8")) == RuntimeRunList.model_json_schema()
