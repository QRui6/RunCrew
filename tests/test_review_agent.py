from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from typer.testing import CliRunner

from runcrew.cli import app
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
from runcrew.domain.training_review import PlannedSession, TrainingReviewRequest
from runcrew.harness import RetryableToolError, ReviewAgentHarness
from runcrew.services.training_context import build_training_context
from runcrew.services.training_review import build_training_review
from runcrew.storage.database import Database
from runcrew.storage.repositories import ActivityRepository


ANCHOR = datetime(2026, 8, 8, 8, tzinfo=timezone.utc)


def make_activity(
    identifier: str,
    *,
    days_before: int,
    load: float | None,
    detail: bool = False,
) -> ActivitySummary | ActivityDetail:
    common = {
        "id": identifier,
        "source_ref": SourceRef(
            provider=SourceProvider.FIXTURE,
            external_id=identifier,
            fetched_at=ANCHOR,
            raw_payload_hash=f"hash-{identifier}",
        ),
        "sport_type": SportType.RUN,
        "started_at": ANCHOR - timedelta(days=days_before),
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


def review_request() -> TrainingReviewRequest:
    return TrainingReviewRequest(
        target_activity_id="target",
        planned_session=PlannedSession(
            distance_meters=10_000,
            duration_seconds=3600,
        ),
    )


def review_result():
    target = make_activity("target", days_before=0, load=50, detail=True)
    history = [
        make_activity("current", days_before=3, load=40),
        make_activity("previous", days_before=8, load=50),
    ]
    request = review_request()
    return build_training_review(
        build_training_context(request, target=target, activities=history)
    )


def run_agent(request: ReviewAgentRunRequest, tool, **harness_kwargs):
    harness = ReviewAgentHarness(
        run_id_factory=lambda: "test-run",
        **harness_kwargs,
    )
    return asyncio.run(harness.run(request, tool=tool))


def test_agent_loop_calls_one_allowlisted_skill_and_validates_output() -> None:
    expected = review_result()

    async def tool(request):
        assert request == review_request()
        return expected

    result = run_agent(ReviewAgentRunRequest(review_request=review_request()), tool)

    assert result.status == "succeeded"
    assert result.termination_reason == "completed"
    assert result.output == expected
    assert result.error is None
    assert result.budget.steps_used == 2
    assert result.budget.tool_calls_used == 1
    assert result.budget.tool_attempts_used == 1
    assert [event.event for event in result.trace] == [
        "run_started",
        "policy_action",
        "tool_permission_checked",
        "tool_call_started",
        "tool_call_succeeded",
        "policy_action",
        "output_validation_started",
        "output_validated",
        "run_completed",
    ]


def test_transient_tool_failure_is_retried_with_trace() -> None:
    calls = 0

    async def flaky_tool(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RetryableToolError("private upstream detail must not enter trace")
        return review_result()

    result = run_agent(
        ReviewAgentRunRequest(review_request=review_request(), max_retries=1),
        flaky_tool,
    )

    assert result.status == "succeeded"
    assert calls == 2
    assert result.budget.tool_calls_used == 1
    assert result.budget.tool_attempts_used == 2
    retry_event = next(
        event for event in result.trace if event.event == "tool_call_retry_scheduled"
    )
    assert retry_event.details == {"reason": "transient_error"}
    assert "private upstream" not in result.model_dump_json()


def test_invalid_tool_output_is_rejected_without_retry() -> None:
    async def invalid_tool(request):
        return {"schema_version": "1.0"}

    result = run_agent(
        ReviewAgentRunRequest(review_request=review_request(), max_retries=2),
        invalid_tool,
    )

    assert result.status == "failed"
    assert result.termination_reason == "invalid_tool_output"
    assert result.budget.tool_attempts_used == 1
    assert result.error is not None and result.error.retryable is False


def test_tool_timeout_stops_after_configured_retries() -> None:
    async def slow_tool(request):
        await asyncio.sleep(0.05)
        return review_result()

    result = run_agent(
        ReviewAgentRunRequest(
            review_request=review_request(),
            tool_timeout_seconds=0.001,
            run_timeout_seconds=1,
            max_retries=1,
        ),
        slow_tool,
    )

    assert result.status == "timed_out"
    assert result.termination_reason == "tool_timeout"
    assert result.budget.tool_attempts_used == 2
    assert result.error is not None and result.error.retryable is True


def test_step_budget_prevents_an_unbounded_loop() -> None:
    async def tool(request):
        return review_result()

    result = run_agent(
        ReviewAgentRunRequest(review_request=review_request(), max_steps=1),
        tool,
    )

    assert result.status == "budget_exhausted"
    assert result.termination_reason == "step_budget_exhausted"
    assert result.output is None


def test_total_run_timeout_covers_a_stalled_policy() -> None:
    class SlowPolicy:
        async def next_action(self, context):
            await asyncio.sleep(0.05)
            return {"type": "finish"}

    async def tool(request):
        raise AssertionError("stalled policy must not reach the tool")

    result = run_agent(
        ReviewAgentRunRequest(
            review_request=review_request(),
            run_timeout_seconds=0.001,
        ),
        tool,
        policy=SlowPolicy(),
    )

    assert result.status == "timed_out"
    assert result.termination_reason == "run_timeout"
    assert result.budget.steps_used == 0


def test_tool_budget_and_argument_integrity_are_enforced() -> None:
    async def tool(request):
        raise AssertionError("blocked tool call must not execute")

    no_budget = run_agent(
        ReviewAgentRunRequest(
            review_request=review_request(),
            tool_call_budget=0,
        ),
        tool,
    )
    assert no_budget.status == "budget_exhausted"
    assert no_budget.budget.tool_attempts_used == 0

    class TamperingPolicy:
        async def next_action(self, context):
            arguments = context.user_request.model_copy(
                update={"target_activity_id": "another-activity"}
            )
            return {
                "type": "call_tool",
                "tool_name": REVIEW_TOOL_NAME,
                "arguments": arguments,
            }

    tampered = run_agent(
        ReviewAgentRunRequest(review_request=review_request()),
        tool,
        policy=TamperingPolicy(),
    )
    assert tampered.status == "failed"
    assert tampered.termination_reason == "permission_denied"
    assert tampered.budget.tool_attempts_used == 0


def test_unknown_tool_and_missing_confirmation_are_blocked() -> None:
    class UnknownToolPolicy:
        async def next_action(self, context):
            return {
                "type": "call_tool",
                "tool_name": "delete_activity",
                "arguments": context.user_request.model_dump(),
            }

    async def tool(request):
        raise AssertionError("blocked tool must not execute")

    denied = run_agent(
        ReviewAgentRunRequest(review_request=review_request()),
        tool,
        policy=UnknownToolPolicy(),
    )
    assert denied.termination_reason == "permission_denied"
    assert denied.budget.tool_attempts_used == 0

    confirmation = run_agent(
        ReviewAgentRunRequest(review_request=review_request()),
        tool,
        permission=ToolPermission(
            name=REVIEW_TOOL_NAME,
            confirmation_required=True,
        ),
    )
    assert confirmation.termination_reason == "confirmation_required"
    assert confirmation.budget.tool_attempts_used == 0


def test_exported_agent_schemas_match_domain_models() -> None:
    references = Path("skills/review-running-training/references")
    assert json.loads(
        (references / "agent-run-input.schema.json").read_text("utf-8")
    ) == ReviewAgentRunRequest.model_json_schema()
    assert json.loads(
        (references / "agent-run-output.schema.json").read_text("utf-8")
    ) == ReviewAgentRunResult.model_json_schema()


def test_agent_review_cli_returns_trace_and_validated_output(tmp_path: Path) -> None:
    database_path = tmp_path / "runcrew.db"
    database = Database(f"sqlite:///{database_path.as_posix()}")
    database.create_schema()
    with database.session() as session:
        repository = ActivityRepository(session)
        for activity in [
            make_activity("previous", days_before=8, load=50),
            make_activity("current", days_before=3, load=40),
            make_activity("target", days_before=0, load=50, detail=True),
        ]:
            repository.upsert(activity)
        session.commit()

    completed = CliRunner().invoke(
        app,
        [
            "agent",
            "review",
            "--latest",
            "--provider",
            "fixture",
            "--planned-distance-km",
            "10",
            "--planned-duration-minutes",
            "60",
            "--db",
            str(database_path),
        ],
    )

    assert completed.exit_code == 0, completed.output
    payload = json.loads(completed.output)
    assert payload["status"] == "succeeded"
    assert payload["output"]["schema_version"] == "1.0"
    assert payload["trace"][-1]["event"] == "run_completed"
