from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from runcrew.cli import app
from runcrew.domain.coach import (
    CoachAgentRunRequest,
    CoachFinishAction,
    CoachNodePermission,
    DelegateExecutionAction,
)
from runcrew.domain.recovery_assessment import (
    RecoveryAssessmentResult,
    RecoveryEvidence,
    RecoveryPlanAction,
    RecoveryWindowMetrics,
)
from runcrew.domain.activity import ActivitySummary, SourceProvider, SourceRef, SportType
from runcrew.domain.training_cycle import (
    DailyCheckIn,
    PlanSession,
    PlanSessionPatch,
    TrainingGoal,
    TrainingPlan,
)
from runcrew.domain.training_execution import TrainingExecutionResult
from runcrew.domain.training_planning import (
    PlanChangeProposalDraft,
    PlanningEvidence,
    RecoveryAssessmentSnapshot,
    TrainingPlanningResult,
)
from runcrew.harness.coach import (
    CoachNodeTools,
    CoachOrchestratorHarness,
    RetryableCoachNodeError,
)
from runcrew.services.training_planning import adjustment_request_from_recovery
from runcrew.storage.database import Database
from runcrew.storage.repositories import (
    ActivityRepository,
    CheckInRepository,
    PlanChangeRepository,
    TrainingGoalRepository,
    TrainingPlanRepository,
)


ANCHOR = datetime(2026, 8, 13, 8, tzinfo=timezone.utc)


def run_request(**updates: Any) -> CoachAgentRunRequest:
    values = {
        "goal_id": "goal-1",
        "plan_id": "plan-1",
        "as_of": ANCHOR,
        "provider": "fixture",
    }
    values.update(updates)
    return CoachAgentRunRequest(**values)


def execution_result(*, goal_id: str = "goal-1") -> TrainingExecutionResult:
    return TrainingExecutionResult(
        input_hash="e" * 64,
        goal_id=goal_id,
        plan_id="plan-1",
        plan_revision=2,
        as_of=ANCHOR,
        summary="完成1节",
        sessions=[],
    )


def recovery_result(
    recommendation: str = "proceed",
    action: str = "keep",
) -> RecoveryAssessmentResult:
    target = "session-1" if action.startswith("ask_plan_agent") else None
    return RecoveryAssessmentResult(
        input_hash="b" * 64,
        goal_id="goal-1",
        assessed_at=ANCHOR,
        recommendation=recommendation,
        risk_level={
            "proceed": "low",
            "reduce": "moderate",
            "rest": "high",
            "seek_professional_help": "escalate",
            "insufficient_data": "unknown",
        }[recommendation],
        summary="基于已保存反馈形成保守建议。",
        evidence=[
            RecoveryEvidence(
                id="check-in:1",
                type="check_in",
                message="采用当天身体反馈。",
                rule_source="user_report",
            )
        ],
        confidence="high" if recommendation != "insufficient_data" else "low",
        current_7d=RecoveryWindowMetrics(
            activity_count=1,
            distance_meters=5000,
            duration_seconds=1800,
            training_load_coverage=0,
        ),
        previous_7d=RecoveryWindowMetrics(
            activity_count=1,
            distance_meters=5000,
            duration_seconds=1800,
            training_load_coverage=0,
        ),
        plan_action=RecoveryPlanAction(
            action=action,
            target_session_id=target,
            requires_user_confirmation=action != "keep",
            reason="固定测试动作。",
        ),
    )


def planning_result(recovery: RecoveryAssessmentResult) -> TrainingPlanningResult:
    return TrainingPlanningResult(
        operation="adjust_from_recovery",
        input_hash="c" * 64,
        goal_id="goal-1",
        status="ready",
        summary="只生成待确认提案，不保存、不批准。",
        change_proposal_draft=PlanChangeProposalDraft(
            plan_id="plan-1",
            base_revision=2,
            reason="恢复评估建议降低负荷。",
            changes=[
                PlanSessionPatch(
                    session_id="session-1",
                    duration_seconds=1200,
                    purpose="降低本次负荷",
                )
            ],
            evidence_refs=["check-in:1"],
        ),
        source_recovery_assessment=RecoveryAssessmentSnapshot(
            input_hash=recovery.input_hash,
            recommendation=recovery.recommendation,
            plan_action=recovery.plan_action,
        ),
        evidence=[
            PlanningEvidence(
                id="recovery:r",
                type="recovery_action",
                message="只消费已校验恢复动作。",
                rule_source="recovery_assessment",
            )
        ],
    )


def tools_for(recovery: RecoveryAssessmentResult) -> CoachNodeTools:
    async def execution_tool(_request):
        return execution_result()

    async def recovery_tool(_request):
        return recovery

    async def plan_tool(request):
        assert request == adjustment_request_from_recovery(recovery)
        return planning_result(recovery)

    return CoachNodeTools(
        execution=execution_tool,
        recovery=recovery_tool,
        planning=plan_tool,
    )


def test_low_risk_routes_two_nodes_and_finishes_without_plan_change() -> None:
    result = asyncio.run(
        CoachOrchestratorHarness(run_id_factory=lambda: "run-1").run(
            run_request(), tools=tools_for(recovery_result())
        )
    )
    assert result.status == "succeeded"
    assert result.required_user_action is None
    assert result.planning is None
    assert [item.to_node for item in result.handoffs] == [
        "execution_agent",
        "recovery_agent",
    ]
    assert result.budget.node_calls_used == 2
    assert all(len(item.request_hash) == 64 for item in result.handoffs)
    permission_events = [
        item for item in result.trace if item.event == "node_permission_checked"
    ]
    assert permission_events
    assert all(item.details["input_hash_match"] is True for item in permission_events)
    assert all(item.details["manifest_hash"] for item in permission_events)
    assert all(
        item.details["guardrail_rule_id"] == "tool.output-schema/1.0"
        for item in result.trace
        if item.event == "node_output_validated"
    )


def test_reduce_routes_plan_and_stops_at_user_confirmation() -> None:
    recovery = recovery_result("reduce", "ask_plan_agent_to_reduce")
    result = asyncio.run(
        CoachOrchestratorHarness(run_id_factory=lambda: "run-2").run(
            run_request(), tools=tools_for(recovery)
        )
    )
    assert result.status == "awaiting_user_confirmation"
    assert result.required_user_action == "review_plan_change"
    assert result.planning is not None
    assert result.planning.change_proposal_draft is not None
    assert [item.to_node for item in result.handoffs] == [
        "execution_agent",
        "recovery_agent",
        "plan_agent",
    ]
    confirmation = [
        item for item in result.trace if item.event == "user_confirmation_requested"
    ]
    assert confirmation[0].details["persisted"] is False
    assert confirmation[0].details["approved"] is False


def test_missing_feedback_and_red_flag_block_without_calling_plan() -> None:
    cases = [
        ("insufficient_data", "wait_for_more_data", "provide_fresh_check_in"),
        (
            "seek_professional_help",
            "hold_until_professional_review",
            "seek_professional_review",
        ),
    ]
    for recommendation, action, expected_user_action in cases:
        recovery = recovery_result(recommendation, action)
        result = asyncio.run(
            CoachOrchestratorHarness().run(run_request(), tools=tools_for(recovery))
        )
        assert result.status == "blocked"
        assert result.required_user_action == expected_user_action
        assert result.planning is None
        assert result.budget.node_calls_used == 2


def test_policy_receives_minimal_state_not_raw_node_outputs() -> None:
    seen: list[set[str]] = []

    class InspectingPolicy:
        async def next_action(self, context):
            seen.append(set(context.model_dump().keys()))
            if not context.execution_completed:
                return DelegateExecutionAction(arguments=context.execution_request)
            return CoachFinishAction()

    result = asyncio.run(
        CoachOrchestratorHarness(policy=InspectingPolicy()).run(
            run_request(), tools=tools_for(recovery_result())
        )
    )
    assert result.status == "failed"
    assert result.error is not None and result.error.code == "premature_finish"
    assert all("execution" not in fields and "recovery" not in fields for fields in seen)


def test_tampered_handoff_is_rejected_before_tool_call() -> None:
    calls = 0

    class TamperingPolicy:
        async def next_action(self, context):
            return DelegateExecutionAction(
                arguments=context.execution_request.model_copy(update={"plan_id": "other"})
            )

    async def execution_tool(_request):
        nonlocal calls
        calls += 1
        return execution_result()

    base = tools_for(recovery_result())
    result = asyncio.run(
        CoachOrchestratorHarness(policy=TamperingPolicy()).run(
            run_request(),
            tools=CoachNodeTools(
                execution=execution_tool,
                recovery=base.recovery,
                planning=base.planning,
            ),
        )
    )
    assert result.error is not None and result.error.code == "invalid_handoff"
    assert calls == 0


def test_wrong_permission_and_cross_goal_output_fail_closed() -> None:
    permission_result = asyncio.run(
        CoachOrchestratorHarness(
            permissions=[
                CoachNodePermission(
                    node="execution_agent",
                    tool_name="compare_training_execution",
                    access="prepare_change",
                )
            ]
        ).run(run_request(), tools=tools_for(recovery_result()))
    )
    assert permission_result.error is not None
    assert permission_result.error.code == "permission_denied"

    async def wrong_execution(_request):
        return execution_result(goal_id="another-goal")

    base = tools_for(recovery_result())
    scope_result = asyncio.run(
        CoachOrchestratorHarness().run(
            run_request(),
            tools=CoachNodeTools(
                execution=wrong_execution,
                recovery=base.recovery,
                planning=base.planning,
            ),
        )
    )
    assert scope_result.error is not None
    assert scope_result.error.code == "invalid_node_output"


def test_retry_budget_and_node_call_budget_are_enforced() -> None:
    attempts = 0

    async def flaky_execution(_request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RetryableCoachNodeError("temporary")
        return execution_result()

    base = tools_for(recovery_result())
    retried = asyncio.run(
        CoachOrchestratorHarness().run(
            run_request(),
            tools=CoachNodeTools(
                execution=flaky_execution,
                recovery=base.recovery,
                planning=base.planning,
            ),
        )
    )
    assert retried.status == "succeeded"
    assert retried.budget.node_attempts_used == 3

    exhausted = asyncio.run(
        CoachOrchestratorHarness().run(
            run_request(node_call_budget=1), tools=tools_for(recovery_result())
        )
    )
    assert exhausted.status == "budget_exhausted"
    assert exhausted.error is not None
    assert exhausted.error.code == "step_budget_exhausted"


def test_invalid_node_schema_and_timeout_fail_closed() -> None:
    async def invalid_execution(_request):
        return {"invented": True}

    async def slow_execution(_request):
        await asyncio.sleep(0.02)
        return execution_result()

    base = tools_for(recovery_result())
    invalid = asyncio.run(
        CoachOrchestratorHarness().run(
            run_request(),
            tools=CoachNodeTools(
                execution=invalid_execution,
                recovery=base.recovery,
                planning=base.planning,
            ),
        )
    )
    timed_out = asyncio.run(
        CoachOrchestratorHarness().run(
            run_request(node_timeout_seconds=0.001, max_retries=0),
            tools=CoachNodeTools(
                execution=slow_execution,
                recovery=base.recovery,
                planning=base.planning,
            ),
        )
    )
    assert invalid.error is not None and invalid.error.code == "invalid_node_output"
    assert timed_out.status == "timed_out"
    assert timed_out.error is not None and timed_out.error.code == "node_timeout"


def test_workflow_hash_is_stable_and_exported_schemas_match_models() -> None:
    first = asyncio.run(
        CoachOrchestratorHarness().run(run_request(), tools=tools_for(recovery_result()))
    )
    second = asyncio.run(
        CoachOrchestratorHarness().run(run_request(), tools=tools_for(recovery_result()))
    )
    assert first.workflow_hash == second.workflow_hash
    references = Path("schemas/coach-orchestrator")
    assert json.loads((references / "input.schema.json").read_text("utf-8")) == (
        CoachAgentRunRequest.model_json_schema()
    )
    from runcrew.domain.coach import CoachAgentRunResult

    assert json.loads((references / "output.schema.json").read_text("utf-8")) == (
        CoachAgentRunResult.model_json_schema()
    )


def test_coach_cli_uses_real_services_but_does_not_persist_proposal(tmp_path: Path) -> None:
    database_path = tmp_path / "coach.db"
    database = Database(f"sqlite:///{database_path.as_posix()}")
    database.create_schema()
    plan = TrainingPlan(
        id="plan-1",
        goal_id="goal-1",
        week_start=date(2026, 8, 10),
        status="active",
        sessions=[
            PlanSession(
                id="session-1",
                scheduled_for=date(2026, 8, 15),
                session_type="interval",
                distance_meters=6000,
                duration_seconds=2400,
                intensity="高强度",
                purpose="速度耐力",
            )
        ],
    )
    activity = ActivitySummary(
        id="run-1",
        source_ref=SourceRef(
            provider=SourceProvider.FIXTURE,
            external_id="run-1",
            fetched_at=ANCHOR,
            raw_payload_hash="raw-hash-1",
        ),
        sport_type=SportType.RUN,
        started_at=datetime(2026, 8, 12, 8, tzinfo=timezone.utc),
        duration_seconds=1800,
        distance_meters=5000,
    )
    with database.session() as session:
        TrainingGoalRepository(session).save(
            TrainingGoal(
                id="goal-1",
                name="10公里目标",
                event_type="10k",
                target_date=date(2026, 10, 18),
                available_weekdays=["thu", "sat"],
            )
        )
        TrainingPlanRepository(session).save(plan)
        CheckInRepository(session).save(
            DailyCheckIn(
                day=ANCHOR.date(),
                fatigue=3,
                soreness=4,
                sleep_quality=3,
                pain_area="右膝",
                pain_severity=3,
            )
        )
        ActivityRepository(session).upsert(activity)
        session.commit()

    completed = CliRunner().invoke(
        app,
        [
            "coach",
            "run",
            "--goal-id",
            "goal-1",
            "--plan-id",
            "plan-1",
            "--as-of",
            ANCHOR.isoformat(),
            "--provider",
            "fixture",
            "--db",
            str(database_path),
        ],
    )
    assert completed.exit_code == 0, completed.output
    payload = json.loads(completed.output)
    assert payload["status"] == "awaiting_user_confirmation"
    assert payload["required_user_action"] == "review_plan_change"
    assert payload["planning"]["change_proposal_draft"]["plan_id"] == "plan-1"
    with database.session() as session:
        assert PlanChangeRepository(session).pending_for_goal("goal-1") == []
        stored_plan = TrainingPlanRepository(session).get("plan-1")
        assert stored_plan is not None and stored_plan.revision == 1
