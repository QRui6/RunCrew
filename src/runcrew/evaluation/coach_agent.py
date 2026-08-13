from __future__ import annotations

import asyncio
import hashlib
import json
import math
import tempfile
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from runcrew.domain.activity import ActivitySummary, SourceProvider, SourceRef, SportType
from runcrew.domain.coach import (
    CoachAgentRunRequest,
    CoachAgentRunResult,
    CoachFinishAction,
    CoachNodePermission,
    DelegateExecutionAction,
)
from runcrew.domain.coach_evaluation import (
    CoachAgentEvaluationCase,
    CoachAgentEvaluationCaseResult,
    CoachAgentEvaluationMetrics,
    CoachAgentEvaluationReport,
    CoachAgentEvaluationSuite,
)
from runcrew.domain.recovery_assessment import (
    RecoveryAssessmentResult,
    RecoveryEvidence,
    RecoveryPlanAction,
    RecoveryWindowMetrics,
)
from runcrew.domain.training_cycle import (
    DailyCheckIn,
    PlanSession,
    PlanSessionPatch,
    TrainingGoal,
    TrainingPlan,
)
from runcrew.domain.training_execution import TrainingExecutionResult
from runcrew.domain.training_operations import CoachRunDecisionRequest, CoachRunSubmission
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
from runcrew.services.training_cycle import TrainingCycleService
from runcrew.services.training_operations import TrainingOperationsService
from runcrew.services.training_planning import adjustment_request_from_recovery
from runcrew.storage.database import Database
from runcrew.storage.repositories import (
    ActivityRepository,
    CheckInRepository,
    PlanChangeRepository,
    TrainingGoalRepository,
    TrainingPlanRepository,
)


EVALUATION_ANCHOR = datetime(2026, 8, 13, 8, tzinfo=timezone.utc)


def load_coach_agent_suite(path: Path) -> CoachAgentEvaluationSuite:
    return CoachAgentEvaluationSuite.model_validate_json(path.read_text("utf-8"))


async def evaluate_coach_agent_suite(
    suite: CoachAgentEvaluationSuite,
    *,
    policy_name: str = "deterministic-coach-policy/1.0",
) -> CoachAgentEvaluationReport:
    results = [await _evaluate_case(case) for case in suite.cases]
    metrics = _build_metrics(results)
    passed = sum(result.passed for result in results)
    meets_baseline = (
        passed == len(results)
        and metrics.task_completion_rate == 1
        and metrics.resilience_pass_rate == 1
        and metrics.guardrail_pass_rate == 1
        and metrics.approval_guard_pass_rate == 1
        and metrics.schema_valid_rate == 1
        and metrics.fact_integrity_rate == 1
        and metrics.lineage_integrity_rate == 1
        and metrics.confirmation_boundary_rate == 1
        and metrics.prohibited_node_execution_count == 0
    )
    return CoachAgentEvaluationReport(
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
    case: CoachAgentEvaluationCase,
) -> CoachAgentEvaluationCaseResult:
    if case.scenario == "approval_stale":
        return await _evaluate_approval_stale(case)

    request = _run_request(case)
    recovery = _recovery_result(case.scenario)
    expected_execution = _execution_result()
    expected_planning = _planning_result(recovery) if case.scenario in {"reduce", "rest"} else None
    calls = {"execution_agent": 0, "recovery_agent": 0, "plan_agent": 0}
    attempts = {"execution_agent": 0, "recovery_agent": 0, "plan_agent": 0}

    async def execution_tool(_request):
        calls["execution_agent"] += 1
        attempts["execution_agent"] += 1
        if case.tool_mode == "execution_transient_once" and attempts["execution_agent"] == 1:
            raise RetryableCoachNodeError("synthetic transient failure")
        if case.tool_mode == "execution_timeout":
            await asyncio.sleep(case.run.node_timeout_seconds * 3)
        if case.tool_mode == "execution_invalid_output":
            return {"invented": True}
        if case.tool_mode == "execution_permanent_failure":
            raise RuntimeError("synthetic permanent failure")
        if case.tool_mode == "execution_cross_goal":
            return expected_execution.model_copy(update={"goal_id": "another-goal"})
        return expected_execution

    async def recovery_tool(_request):
        calls["recovery_agent"] += 1
        attempts["recovery_agent"] += 1
        return recovery

    async def plan_tool(node_request):
        calls["plan_agent"] += 1
        attempts["plan_agent"] += 1
        assert node_request == adjustment_request_from_recovery(recovery)
        result = expected_planning or _planning_result(recovery)
        if case.tool_mode == "plan_cross_goal":
            return result.model_copy(update={"goal_id": "another-goal"})
        if case.tool_mode == "plan_lineage_tamper":
            snapshot = result.source_recovery_assessment.model_copy(
                update={"input_hash": "a" * 64}
            )
            return result.model_copy(update={"source_recovery_assessment": snapshot})
        return result

    permissions = None
    if case.permission_mode == "wrong_execution_access":
        permissions = [
            CoachNodePermission(
                node="execution_agent",
                tool_name="compare_training_execution",
                access="prepare_change",
            )
        ]
    harness = CoachOrchestratorHarness(
        policy=_policy_for_case(case),
        permissions=permissions,
        run_id_factory=lambda: f"eval-{case.id}",
    )
    started = time.perf_counter()
    result = await harness.run(
        request,
        tools=CoachNodeTools(
            execution=execution_tool,
            recovery=recovery_tool,
            planning=plan_tool,
        ),
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    return _judge_harness_case(
        case,
        result=result,
        calls=calls,
        expected_execution=expected_execution,
        expected_recovery=recovery,
        expected_planning=expected_planning,
        latency_ms=latency_ms,
    )


def _policy_for_case(case: CoachAgentEvaluationCase):
    if case.policy_mode == "tamper_handoff":
        return _TamperedHandoffPolicy()
    if case.policy_mode == "premature_finish":
        return _PrematureFinishPolicy()
    if case.policy_mode == "invalid_action":
        return _InvalidActionPolicy()
    return None


class _TamperedHandoffPolicy:
    async def next_action(self, context):
        return DelegateExecutionAction(
            arguments=context.execution_request.model_copy(update={"plan_id": "other-plan"})
        )


class _PrematureFinishPolicy:
    async def next_action(self, _context):
        return CoachFinishAction()


class _InvalidActionPolicy:
    async def next_action(self, _context):
        return {"type": "delegate_unknown", "arguments": {}}


def _judge_harness_case(
    case: CoachAgentEvaluationCase,
    *,
    result: CoachAgentRunResult,
    calls: dict[str, int],
    expected_execution: TrainingExecutionResult,
    expected_recovery: RecoveryAssessmentResult,
    expected_planning: TrainingPlanningResult | None,
    latency_ms: float,
) -> CoachAgentEvaluationCaseResult:
    reasons: list[str] = []
    try:
        CoachAgentRunResult.model_validate(result.model_dump())
        schema_valid = True
    except Exception:
        schema_valid = False
        reasons.append("Coach Run Result 未通过 Schema 复验")
    actual_nodes = [handoff.to_node for handoff in result.handoffs]
    _expect_equal(reasons, "终态", case.expected_status, result.status)
    _expect_equal(
        reasons,
        "退出原因",
        case.expected_termination_reason,
        result.termination_reason,
    )
    _expect_equal(
        reasons,
        "用户动作",
        case.expected_required_user_action,
        result.required_user_action,
    )
    _expect_equal(reasons, "节点顺序", case.expected_nodes, actual_nodes)
    if result.budget.node_calls_used > case.max_node_calls:
        reasons.append("节点逻辑调用数超过用例上限")
    if result.budget.node_attempts_used > case.max_node_attempts:
        reasons.append("节点尝试数超过用例上限")

    facts = (
        (result.execution is None or result.execution == expected_execution)
        and (result.recovery is None or result.recovery == expected_recovery)
        and (result.planning is None or result.planning == expected_planning)
    )
    if not facts:
        reasons.append("最终输出修改或接受了合成节点事实")
    lineage = _lineage_is_valid(result, expected_recovery)
    if not lineage:
        reasons.append("Handoff 或 Recovery→Plan 证据血缘不一致")
    confirmation = _confirmation_boundary_is_valid(result)
    if not confirmation:
        reasons.append("计划调整没有停在未持久化、未批准的用户确认边界")
    prohibited = case.expect_pre_execution_block and sum(calls.values()) > 0
    if prohibited:
        reasons.append("应在节点执行前拒绝，但底层节点仍被调用")
    return CoachAgentEvaluationCaseResult(
        case_id=case.id,
        category=case.category,
        passed=not reasons,
        actual_status=result.status,
        actual_termination_reason=result.termination_reason,
        actual_required_user_action=result.required_user_action,
        actual_nodes=actual_nodes,
        schema_valid=schema_valid,
        fact_integrity=facts,
        lineage_integrity=lineage,
        confirmation_boundary_valid=confirmation,
        prohibited_node_executed=prohibited,
        node_calls_used=result.budget.node_calls_used,
        node_attempts_used=result.budget.node_attempts_used,
        latency_ms=latency_ms,
        failure_reasons=reasons,
    )


async def _evaluate_approval_stale(
    case: CoachAgentEvaluationCase,
) -> CoachAgentEvaluationCaseResult:
    private_root = Path("data/private")
    private_root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="coach-eval-", dir=private_root) as directory:
        database_path = Path(directory) / "stale.db"
        database = _seed_operations_database(database_path)
        service = TrainingOperationsService(database_path=database_path)
        try:
            run = await service.run_coach(
                CoachRunSubmission(
                    goal_id="goal-1",
                    plan_id="plan-1",
                    as_of=EVALUATION_ANCHOR,
                    provider="fixture",
                )
            )
            with database.session() as session:
                cycle = TrainingCycleService(
                    goals=TrainingGoalRepository(session),
                    plans=TrainingPlanRepository(session),
                    check_ins=CheckInRepository(session),
                    changes=PlanChangeRepository(session),
                )
                proposal = cycle.propose_change(
                    plan_id="plan-1",
                    proposed_by="user",
                    reason="合成用户先修改计划",
                    changes=[PlanSessionPatch(session_id="session-1", duration_seconds=2100)],
                )
                cycle.decide_change(proposal_id=proposal.id, decision="approve")
                session.commit()
            decision = await service.decide_coach_run(
                run_id=run.audit.run_id,
                request=CoachRunDecisionRequest(decision="approve"),
            )
            with database.session() as session:
                pending = PlanChangeRepository(session).pending_for_goal("goal-1")
                stored_plan = TrainingPlanRepository(session).get("plan-1")
        finally:
            service.database.engine.dispose()
            database.engine.dispose()
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    facts = (
        decision.outcome == "stale"
        and stored_plan is not None
        and stored_plan.revision == 2
        and stored_plan.sessions[0].duration_seconds == 2100
        and pending == []
        and decision.proposal is None
    )
    reasons: list[str] = []
    _expect_equal(reasons, "终态", case.expected_status, decision.outcome)
    _expect_equal(
        reasons,
        "退出原因",
        case.expected_termination_reason,
        "stale_replay_blocked",
    )
    if not facts:
        reasons.append("批准前重放没有阻止旧草案覆盖新 revision")
    return CoachAgentEvaluationCaseResult(
        case_id=case.id,
        category=case.category,
        passed=not reasons,
        actual_status="stale",
        actual_termination_reason="stale_replay_blocked",
        actual_nodes=[],
        schema_valid=True,
        fact_integrity=facts,
        lineage_integrity=True,
        confirmation_boundary_valid=facts,
        prohibited_node_executed=False,
        node_calls_used=0,
        node_attempts_used=0,
        latency_ms=latency_ms,
        failure_reasons=reasons,
    )


def _run_request(case: CoachAgentEvaluationCase) -> CoachAgentRunRequest:
    return CoachAgentRunRequest(
        goal_id="goal-1",
        plan_id="plan-1",
        as_of=EVALUATION_ANCHOR,
        provider="fixture",
        **case.run.model_dump(),
    )


def _execution_result() -> TrainingExecutionResult:
    return TrainingExecutionResult(
        input_hash="e" * 64,
        goal_id="goal-1",
        plan_id="plan-1",
        plan_revision=1,
        as_of=EVALUATION_ANCHOR,
        summary="合成执行对照已完成。",
        sessions=[],
    )


def _recovery_result(scenario: str) -> RecoveryAssessmentResult:
    mapping = {
        "low_risk": ("proceed", "low", "keep", False),
        "reduce": ("reduce", "moderate", "ask_plan_agent_to_reduce", True),
        "rest": ("rest", "high", "ask_plan_agent_to_replace_with_rest", True),
        "missing_feedback": ("insufficient_data", "unknown", "wait_for_more_data", True),
        "red_flag": ("seek_professional_help", "escalate", "hold_until_professional_review", True),
    }
    recommendation, risk, action, confirmation = mapping.get(scenario, mapping["reduce"])
    return RecoveryAssessmentResult(
        input_hash="b" * 64,
        goal_id="goal-1",
        assessed_at=EVALUATION_ANCHOR,
        recommendation=recommendation,
        risk_level=risk,
        summary="合成恢复评估结果。",
        evidence=[
            RecoveryEvidence(
                id="check-in:synthetic",
                type="check_in" if scenario != "missing_feedback" else "missing_data",
                message="无私人数据的固定评测证据。",
                rule_source="user_report" if scenario != "missing_feedback" else "missing_data_policy",
            )
        ],
        missing_data=["fresh_check_in"] if scenario == "missing_feedback" else [],
        confidence="low" if scenario == "missing_feedback" else "high",
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
            target_session_id="session-1" if action.startswith("ask_plan_agent") else None,
            requires_user_confirmation=confirmation,
            reason="合成评测固定动作。",
        ),
    )


def _planning_result(recovery: RecoveryAssessmentResult) -> TrainingPlanningResult:
    rest = recovery.plan_action.action == "ask_plan_agent_to_replace_with_rest"
    patch = (
        PlanSessionPatch(
            session_id="session-1",
            session_type="rest",
            clear_distance=True,
            clear_duration=True,
            clear_intensity=True,
            purpose="根据恢复结果安排休息",
        )
        if rest
        else PlanSessionPatch(
            session_id="session-1",
            duration_seconds=1200,
            purpose="根据恢复结果降低训练量",
        )
    )
    return TrainingPlanningResult(
        operation="adjust_from_recovery",
        input_hash="c" * 64,
        goal_id="goal-1",
        status="ready",
        summary="只生成待确认草案。",
        change_proposal_draft=PlanChangeProposalDraft(
            plan_id="plan-1",
            base_revision=1,
            reason="恢复评估要求调整计划。",
            changes=[patch],
            evidence_refs=["check-in:synthetic"],
        ),
        source_recovery_assessment=RecoveryAssessmentSnapshot(
            input_hash=recovery.input_hash,
            recommendation=recovery.recommendation,
            plan_action=recovery.plan_action,
        ),
        evidence=[
            PlanningEvidence(
                id="recovery:synthetic",
                type="recovery_action",
                message="只消费已验证的恢复动作。",
                rule_source="recovery_assessment",
            )
        ],
    )


def _lineage_is_valid(
    result: CoachAgentRunResult, recovery: RecoveryAssessmentResult
) -> bool:
    if [item.sequence for item in result.handoffs] != list(
        range(1, len(result.handoffs) + 1)
    ):
        return False
    if any(len(item.request_hash) != 64 for item in result.handoffs):
        return False
    if result.planning is None:
        return True
    snapshot = result.planning.source_recovery_assessment
    return (
        snapshot is not None
        and snapshot.input_hash == recovery.input_hash
        and snapshot.recommendation == recovery.recommendation
        and snapshot.plan_action == recovery.plan_action
    )


def _confirmation_boundary_is_valid(result: CoachAgentRunResult) -> bool:
    confirmations = [
        event for event in result.trace if event.event == "user_confirmation_requested"
    ]
    if result.status == "awaiting_user_confirmation":
        return (
            result.planning is not None
            and result.planning.change_proposal_draft is not None
            and len(confirmations) == 1
            and confirmations[0].details.get("persisted") is False
            and confirmations[0].details.get("approved") is False
        )
    return not confirmations


def _seed_operations_database(path: Path) -> Database:
    database = Database(f"sqlite:///{path.as_posix()}")
    database.create_schema()
    with database.session() as session:
        TrainingGoalRepository(session).save(
            TrainingGoal(
                id="goal-1",
                name="合成10公里目标",
                event_type="10k",
                target_date=date(2026, 10, 18),
                available_weekdays=["thu", "sat"],
            )
        )
        TrainingPlanRepository(session).save(
            TrainingPlan(
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
                        purpose="合成速度耐力课",
                    )
                ],
            )
        )
        CheckInRepository(session).save(
            DailyCheckIn(
                day=EVALUATION_ANCHOR.date(),
                fatigue=3,
                soreness=4,
                sleep_quality=3,
                pain_area="合成疼痛部位",
                pain_severity=3,
            )
        )
        ActivityRepository(session).upsert(
            ActivitySummary(
                id="activity-1",
                source_ref=SourceRef(
                    provider=SourceProvider.FIXTURE,
                    external_id="synthetic-activity",
                    fetched_at=EVALUATION_ANCHOR,
                    raw_payload_hash="synthetic-raw-hash",
                ),
                sport_type=SportType.RUN,
                started_at=datetime(2026, 8, 12, 8, tzinfo=timezone.utc),
                duration_seconds=1800,
                distance_meters=5000,
            )
        )
        session.commit()
    return database


def _build_metrics(
    results: list[CoachAgentEvaluationCaseResult],
) -> CoachAgentEvaluationMetrics:
    by_category = {
        category: [result for result in results if result.category == category]
        for category in ("task", "resilience", "guardrail", "budget", "approval")
    }
    latencies = sorted(result.latency_ms for result in results)
    p95_index = max(math.ceil(len(latencies) * 0.95) - 1, 0)
    terminations = Counter(result.actual_termination_reason for result in results)
    resilience = by_category["resilience"] + by_category["budget"]
    return CoachAgentEvaluationMetrics(
        expectation_pass_rate=_rate(sum(result.passed for result in results), len(results)),
        task_completion_rate=_pass_rate(by_category["task"]),
        resilience_pass_rate=_pass_rate(resilience),
        guardrail_pass_rate=_pass_rate(by_category["guardrail"]),
        approval_guard_pass_rate=_pass_rate(by_category["approval"]),
        schema_valid_rate=_rate(sum(result.schema_valid for result in results), len(results)),
        fact_integrity_rate=_rate(sum(result.fact_integrity for result in results), len(results)),
        lineage_integrity_rate=_rate(sum(result.lineage_integrity for result in results), len(results)),
        confirmation_boundary_rate=_rate(
            sum(result.confirmation_boundary_valid for result in results), len(results)
        ),
        prohibited_node_execution_count=sum(
            result.prohibited_node_executed for result in results
        ),
        average_node_calls=round(
            sum(result.node_calls_used for result in results) / len(results), 4
        ),
        average_node_attempts=round(
            sum(result.node_attempts_used for result in results) / len(results), 4
        ),
        p95_latency_ms=latencies[p95_index],
        termination_reason_counts=dict(sorted(terminations.items())),
    )


def _suite_hash(suite: CoachAgentEvaluationSuite) -> str:
    payload = json.dumps(
        suite.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _expect_equal(reasons: list[str], label: str, expected: Any, actual: Any) -> None:
    if expected != actual:
        reasons.append(f"{label}应为 {expected}，实际为 {actual}")


def _pass_rate(results: list[CoachAgentEvaluationCaseResult]) -> float:
    return _rate(sum(result.passed for result in results), len(results))


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0
