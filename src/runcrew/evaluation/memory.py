from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from runcrew.domain.activity import ActivitySummary, SourceProvider, SourceRef, SportType
from runcrew.domain.memory import (
    AthletePreference,
    MemoryCandidateDecisionRequest,
    MemoryContextBuildRequest,
    WeeklyTrainingMemory,
)
from runcrew.domain.memory_evaluation import (
    MemoryEvaluationCase,
    MemoryEvaluationCaseResult,
    MemoryEvaluationChecks,
    MemoryEvaluationMetrics,
    MemoryEvaluationObservation,
    MemoryEvaluationReport,
    MemoryEvaluationSuite,
)
from runcrew.services.memory_candidates import (
    MemoryCandidateError,
    decide_memory_candidate,
    expire_pending_memory_candidates,
    extract_memory_candidate,
    propose_chat_memory_candidate,
)
from runcrew.services.memory_context import build_agent_memory_context
from runcrew.storage.database import Database
from runcrew.storage.models import ChatMessageRecord, MemoryCandidateRecord
from runcrew.storage.repositories import (
    ActivityRepository,
    AthletePreferenceRepository,
    ChatRepository,
    MemoryCandidateRepository,
)


EVALUATION_ANCHOR = datetime(2026, 8, 20, 8, tzinfo=timezone.utc)
TARGET_WEEK = date(2026, 8, 24)


def load_memory_evaluation_suite(path: Path) -> MemoryEvaluationSuite:
    return MemoryEvaluationSuite.model_validate_json(path.read_text("utf-8"))


def evaluate_memory_suite(
    suite: MemoryEvaluationSuite,
    *,
    evaluator_name: str = "deterministic-memory-manager/1.0",
) -> MemoryEvaluationReport:
    results = [_evaluate_case(case) for case in suite.cases]
    metrics = _build_metrics(results)
    passed = sum(result.passed for result in results)
    meets_baseline = (
        passed == len(results)
        and metrics.candidate_recall_rate == 1
        and metrics.negative_rejection_rate == 1
        and metrics.lifecycle_integrity_rate == 1
        and metrics.source_integrity_rate == 1
        and metrics.confirmation_boundary_rate == 1
        and metrics.role_scope_rate == 1
        and metrics.irrelevant_injection_resistance_rate == 1
        and metrics.schema_valid_rate == 1
        and metrics.unexpected_formal_memory_write_count == 0
    )
    return MemoryEvaluationReport(
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


def _evaluate_case(case: MemoryEvaluationCase) -> MemoryEvaluationCaseResult:
    started = time.perf_counter()
    failure_reasons: list[str] = []
    try:
        actual, checks = _run_scenario(case)
        schema_valid = True
    except Exception as error:  # pragma: no cover - defensive report boundary
        actual = MemoryEvaluationObservation()
        checks = MemoryEvaluationChecks()
        schema_valid = True
        failure_reasons.append(f"场景执行异常：{type(error).__name__}: {error}")

    if actual != case.expected:
        failure_reasons.append("实际 Memory 观察结果与版本化期望不一致")
    failed_checks = [
        name
        for name, value in checks.model_dump().items()
        if value is False
    ]
    if failed_checks:
        failure_reasons.append("检查项未通过：" + ", ".join(failed_checks))
    if not schema_valid:
        failure_reasons.append("结果不符合 Memory Evaluation Schema")
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    return MemoryEvaluationCaseResult(
        case_id=case.id,
        category=case.category,
        scenario=case.scenario,
        passed=not failure_reasons,
        schema_valid=schema_valid,
        actual=actual,
        checks=checks,
        latency_ms=latency_ms,
        failure_reasons=failure_reasons,
    )


def _run_scenario(
    case: MemoryEvaluationCase,
) -> tuple[MemoryEvaluationObservation, MemoryEvaluationChecks]:
    if case.category == "candidate":
        return _run_candidate_scenario(case)
    if case.category in {"lifecycle", "integrity"}:
        return _run_persisted_scenario(case)
    return _run_retrieval_scenario(case)


def _run_candidate_scenario(
    case: MemoryEvaluationCase,
) -> tuple[MemoryEvaluationObservation, MemoryEvaluationChecks]:
    content = case.input.content or ""
    candidate = extract_memory_candidate(
        content,
        conversation_id="eval-conversation",
        source_message_id=1,
        now=EVALUATION_ANCHOR,
    )
    actual = MemoryEvaluationObservation(
        candidate_created=candidate is not None,
        proposed_value=candidate.proposed_value if candidate else None,
        candidate_confidence=candidate.confidence if candidate else None,
        candidate_status=candidate.status if candidate else None,
    )
    positive = case.scenario in {
        "explicit_high_confidence",
        "explicit_medium_confidence",
    }
    return actual, MemoryEvaluationChecks(
        candidate_detection=(candidate is not None) if positive else None,
        negative_rejection=(candidate is None) if not positive else None,
        confirmation_boundary=True,
    )


def _run_persisted_scenario(
    case: MemoryEvaluationCase,
) -> tuple[MemoryEvaluationObservation, MemoryEvaluationChecks]:
    with _temporary_database() as database:
        with database.session() as session:
            ActivityRepository(session).upsert(_activity())
            chats = ChatRepository(session)
            conversation = chats.create(
                target_activity_id="activity-eval",
                title="Memory Evaluation",
                lookback_days=28,
            )
            first_message = chats.add_user_message(
                conversation.id,
                case.input.content or "以后长跑优先安排在周日",
            )
            candidates = MemoryCandidateRepository(session)
            first = propose_chat_memory_candidate(
                first_message.content,
                conversation_id=conversation.id,
                source_message_id=first_message.id,
                candidates=candidates,
                now=EVALUATION_ANCHOR,
            )
            if first is None:
                raise RuntimeError("持久化场景没有生成预期候选")
            session.commit()

        decision_blocked = False
        secondary_status = None
        if case.scenario == "new_candidate_supersedes":
            with database.session() as session:
                chats = ChatRepository(session)
                second_message = chats.add_user_message(
                    conversation.id,
                    case.input.second_content or "今后长跑固定在周六",
                )
                second = propose_chat_memory_candidate(
                    second_message.content,
                    conversation_id=conversation.id,
                    source_message_id=second_message.id,
                    candidates=MemoryCandidateRepository(session),
                    now=EVALUATION_ANCHOR + timedelta(minutes=1),
                )
                if second is None:
                    raise RuntimeError("冲突场景没有生成第二个候选")
                session.commit()
                secondary_status = second.status
        elif case.scenario == "expired_candidate_blocked":
            with database.session() as session:
                expire_pending_memory_candidates(
                    candidates=MemoryCandidateRepository(session),
                    now=EVALUATION_ANCHOR + timedelta(days=8),
                )
                session.commit()
            decision_blocked = _attempt_decision(
                database,
                first.id,
                first.candidate_hash,
                decision="confirm",
                now=EVALUATION_ANCHOR + timedelta(days=8),
            )
        elif case.scenario == "candidate_tamper_blocked":
            with database.session() as session:
                record = session.get(MemoryCandidateRecord, first.id)
                assert record is not None
                record.canonical_json = first.model_copy(
                    update={"proposed_value": "mon"}
                ).model_dump_json()
                session.commit()
            decision_blocked = _attempt_decision(
                database,
                first.id,
                first.candidate_hash,
                decision="confirm",
                now=EVALUATION_ANCHOR,
            )
        elif case.scenario == "source_tamper_blocked":
            with database.session() as session:
                source = session.get(ChatMessageRecord, first.source_message_id)
                assert source is not None
                source.content = "原始消息已改变"
                session.commit()
            decision_blocked = _attempt_decision(
                database,
                first.id,
                first.candidate_hash,
                decision="confirm",
                now=EVALUATION_ANCHOR,
            )
        elif case.scenario in {"confirm_writes_preference", "reject_does_not_write"}:
            decision = case.input.decision or (
                "confirm" if case.scenario == "confirm_writes_preference" else "reject"
            )
            _apply_decision(
                database,
                first.id,
                first.candidate_hash,
                decision=decision,
                now=EVALUATION_ANCHOR,
            )

        with database.session() as session:
            current = MemoryCandidateRepository(session).get(first.id)
            preferences = AthletePreferenceRepository(session).list()
        assert current is not None
        actual = MemoryEvaluationObservation(
            candidate_created=True,
            proposed_value=current.proposed_value,
            candidate_confidence=current.confidence,
            candidate_status=current.status,
            secondary_candidate_status=secondary_status,
            formal_preference_count=len(preferences),
            decision_blocked=decision_blocked,
        )
        lifecycle_cases = {
            "pending_is_not_memory",
            "confirm_writes_preference",
            "reject_does_not_write",
            "new_candidate_supersedes",
            "expired_candidate_blocked",
        }
        integrity_case = case.scenario in {
            "candidate_tamper_blocked",
            "source_tamper_blocked",
        }
        confirmation_valid = (
            len(preferences) == 1
            if case.scenario == "confirm_writes_preference"
            else len(preferences) == 0
        )
        return actual, MemoryEvaluationChecks(
            lifecycle_integrity=(actual == case.expected)
            if case.scenario in lifecycle_cases
            else None,
            source_integrity=(decision_blocked and len(preferences) == 0)
            if integrity_case
            else None,
            confirmation_boundary=confirmation_valid,
        )


@contextmanager
def _temporary_database():
    database = Database("sqlite:///:memory:")
    database.create_schema()
    try:
        yield database
    finally:
        database.engine.dispose()


def _attempt_decision(
    database: Database,
    candidate_id: str,
    candidate_hash: str,
    *,
    decision: str,
    now: datetime,
) -> bool:
    try:
        _apply_decision(
            database,
            candidate_id,
            candidate_hash,
            decision=decision,
            now=now,
        )
    except MemoryCandidateError:
        return True
    return False


def _apply_decision(
    database: Database,
    candidate_id: str,
    candidate_hash: str,
    *,
    decision: str,
    now: datetime,
) -> None:
    with database.session() as session:
        decide_memory_candidate(
            candidate_id,
            MemoryCandidateDecisionRequest(
                decision=decision,
                expected_candidate_hash=candidate_hash,
            ),
            candidates=MemoryCandidateRepository(session),
            preferences=AthletePreferenceRepository(session),
            chats=ChatRepository(session),
            now=now,
        )
        session.commit()


def _run_retrieval_scenario(
    case: MemoryEvaluationCase,
) -> tuple[MemoryEvaluationObservation, MemoryEvaluationChecks]:
    active_preference = _preference("preference-active")
    active_weekly = _weekly("weekly-active")
    if case.scenario == "role_scoped_retrieval":
        execution = _context("execution", [active_preference], [active_weekly])
        recovery = _context("recovery", [active_preference], [active_weekly])
        plan = _context("plan", [active_preference], [active_weekly])
        plan_weekly = plan.selected_weekly_memories[0].model_dump(mode="json")
        actual = MemoryEvaluationObservation(
            execution_item_count=execution.budget.used_items,
            recovery_preference_count=len(recovery.selected_preferences),
            recovery_weekly_count=len(recovery.selected_weekly_memories),
            plan_preference_count=len(plan.selected_preferences),
            plan_weekly_count=len(plan.selected_weekly_memories),
        )
        role_scope_valid = (
            actual == case.expected
            and "average_fatigue" not in plan_weekly
            and "max_pain_severity" not in plan_weekly
            and recovery.selected_weekly_memories[0].max_pain_severity == 1
        )
        return actual, MemoryEvaluationChecks(role_scope=role_scope_valid)

    injected_preferences = [
        _preference(
            "preference-expired",
            valid_until=EVALUATION_ANCHOR - timedelta(days=1),
        ),
        _preference("preference-archived", status="archived"),
    ]
    injected_weekly = [
        _weekly(
            "weekly-invalidated",
            status="invalidated",
            invalidated_at=EVALUATION_ANCHOR - timedelta(hours=1),
        ),
        _weekly("weekly-wrong-goal", goal_id="other-goal"),
        _weekly(
            "weekly-future",
            generated_at=EVALUATION_ANCHOR + timedelta(hours=1),
            updated_at=EVALUATION_ANCHOR + timedelta(hours=1),
        ),
    ]
    if case.scenario == "inactive_memory_excluded":
        context = _context("plan", injected_preferences, injected_weekly)
        reasons = sorted({item.reason for item in context.decisions})
        actual = MemoryEvaluationObservation(exclusion_reasons=reasons)
        return actual, MemoryEvaluationChecks(role_scope=actual == case.expected)

    base = _context("plan", [active_preference], [active_weekly])
    injected = _context(
        "plan",
        [active_preference, *injected_preferences],
        [active_weekly, *injected_weekly],
    )
    reasons = sorted(
        {item.reason for item in injected.decisions if not item.selected}
    )
    actual = MemoryEvaluationObservation(
        plan_preference_count=len(injected.selected_preferences),
        plan_weekly_count=len(injected.selected_weekly_memories),
        exclusion_reasons=reasons,
        context_hash_unchanged=base.context_hash == injected.context_hash,
    )
    resistant = (
        actual == case.expected
        and base.context_hash == injected.context_hash
        and base.audit_hash != injected.audit_hash
    )
    return actual, MemoryEvaluationChecks(
        irrelevant_injection_resistance=resistant
    )


def _activity() -> ActivitySummary:
    return ActivitySummary(
        id="activity-eval",
        source_ref=SourceRef(
            provider=SourceProvider.FIXTURE,
            external_id="synthetic-memory-eval",
            fetched_at=EVALUATION_ANCHOR,
            raw_payload_hash="synthetic",
        ),
        sport_type=SportType.RUN,
        started_at=EVALUATION_ANCHOR - timedelta(days=1),
        duration_seconds=2400,
        distance_meters=6000,
        average_pace_seconds_per_km=400,
        title="合成跑步",
    )


def _preference(identifier: str, **updates: object) -> AthletePreference:
    values: dict[str, object] = {
        "id": identifier,
        "key": "preferred_long_run_weekday",
        "value": "sun",
        "source_ref": f"evaluation:{identifier}",
        "confirmed_at": EVALUATION_ANCHOR - timedelta(days=20),
        "valid_from": EVALUATION_ANCHOR - timedelta(days=20),
        "created_at": EVALUATION_ANCHOR - timedelta(days=20),
        "updated_at": EVALUATION_ANCHOR - timedelta(days=20),
    }
    values.update(updates)
    return AthletePreference(**values)


def _weekly(identifier: str, **updates: object) -> WeeklyTrainingMemory:
    week_start = date(2026, 8, 3)
    values: dict[str, object] = {
        "id": identifier,
        "goal_id": "goal-eval",
        "plan_id": "plan-eval",
        "week_start": week_start,
        "week_end": week_start + timedelta(days=6),
        "version": 1,
        "plan_revision": 2,
        "input_hash": hashlib.sha256(identifier.encode("utf-8")).hexdigest(),
        "planned_sessions": 3,
        "confirmed_completed_sessions": 2,
        "confirmed_skipped_sessions": 1,
        "unresolved_sessions": 0,
        "completion_rate": 2 / 3,
        "planned_duration_seconds": 6000,
        "actual_duration_seconds": 5200,
        "actual_distance_meters": 14000,
        "check_in_days": 2,
        "average_fatigue": 3,
        "average_soreness": 2,
        "average_sleep_quality": 4,
        "average_readiness": 3.5,
        "max_pain_severity": 1,
        "acute_symptom_days": 0,
        "approved_plan_changes": 0,
        "summary": "合成周训练摘要。",
        "source_refs": [f"plan:{identifier}@revision:2"],
        "generated_at": EVALUATION_ANCHOR - timedelta(days=2),
        "updated_at": EVALUATION_ANCHOR - timedelta(days=2),
    }
    values.update(updates)
    return WeeklyTrainingMemory(**values)


def _context(
    role: str,
    preferences: list[AthletePreference],
    weekly_memories: list[WeeklyTrainingMemory],
):
    return build_agent_memory_context(
        MemoryContextBuildRequest(
            role=role,
            goal_id="goal-eval",
            as_of=EVALUATION_ANCHOR,
            target_week_start=TARGET_WEEK if role == "plan" else None,
        ),
        preferences=preferences,
        weekly_memories=weekly_memories,
    )


def _build_metrics(
    results: list[MemoryEvaluationCaseResult],
) -> MemoryEvaluationMetrics:
    return MemoryEvaluationMetrics(
        expectation_pass_rate=_round_rate(sum(item.passed for item in results), len(results)),
        candidate_recall_rate=_check_rate(results, "candidate_detection"),
        negative_rejection_rate=_check_rate(results, "negative_rejection"),
        lifecycle_integrity_rate=_check_rate(results, "lifecycle_integrity"),
        source_integrity_rate=_check_rate(results, "source_integrity"),
        confirmation_boundary_rate=_check_rate(results, "confirmation_boundary"),
        role_scope_rate=_check_rate(results, "role_scope"),
        irrelevant_injection_resistance_rate=_check_rate(
            results, "irrelevant_injection_resistance"
        ),
        schema_valid_rate=_round_rate(
            sum(item.schema_valid for item in results), len(results)
        ),
        unexpected_formal_memory_write_count=sum(
            item.actual.formal_preference_count
            for item in results
            if item.scenario != "confirm_writes_preference"
        ),
        p95_latency_ms=_p95([item.latency_ms for item in results]),
        category_counts=dict(Counter(item.category for item in results)),
    )


def _check_rate(results: list[MemoryEvaluationCaseResult], field: str) -> float:
    values = [
        getattr(item.checks, field)
        for item in results
        if getattr(item.checks, field) is not None
    ]
    return _round_rate(sum(value is True for value in values), len(values))


def _round_rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return round(ordered[index], 3)


def _suite_hash(suite: MemoryEvaluationSuite) -> str:
    payload = json.dumps(
        suite.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
