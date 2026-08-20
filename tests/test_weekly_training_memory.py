from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from runcrew.cli import app
from runcrew.domain.activity import ActivitySummary, SourceProvider, SourceRef, SportType
from runcrew.domain.memory import (
    WeeklyTrainingMemory,
    WeeklyTrainingMemoryBuildRequest,
)
from runcrew.domain.training_cycle import DailyCheckIn, PlanSession, TrainingGoal, TrainingPlan
from runcrew.domain.training_execution import TrainingExecutionConfirmation
from runcrew.domain.training_operations import WeeklyTrainingMemoryBuildSubmission
from runcrew.domain.training_planning import WeeklyPlanDraftRequest
from runcrew.services.training_operations import TrainingOperationsService
from runcrew.services.training_planning import build_weekly_plan_draft
from runcrew.services.weekly_training_memory import (
    WeeklyTrainingMemoryError,
    invalidate_weekly_training_memory,
    refresh_weekly_training_memory,
)
from runcrew.storage.database import Database
from runcrew.storage.repositories import (
    ActivityRepository,
    CheckInRepository,
    PlanChangeRepository,
    TrainingExecutionConfirmationRepository,
    TrainingGoalRepository,
    TrainingPlanRepository,
    WeeklyTrainingMemoryRepository,
)
from runcrew.web import DemoApplication, DemoDashboardService


WEEK_START = date(2026, 8, 10)
AS_OF = datetime(2026, 8, 17, 8, tzinfo=timezone.utc)


def _activity(activity_id: str, day: date, duration: int, distance: float) -> ActivitySummary:
    started_at = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=6)
    return ActivitySummary(
        id=activity_id,
        source_ref=SourceRef(
            provider=SourceProvider.FIXTURE,
            external_id=activity_id,
            fetched_at=started_at + timedelta(hours=1),
            raw_payload_hash=(activity_id[-1] * 64),
        ),
        sport_type=SportType.RUN,
        started_at=started_at,
        duration_seconds=duration,
        distance_meters=distance,
        title="合成周训练",
    )


def _seed_week(database: Database) -> tuple[TrainingGoal, TrainingPlan]:
    goal = TrainingGoal(
        id="goal-weekly-memory",
        name="秋季十公里",
        event_type="10k",
        target_date=date(2026, 10, 18),
        available_weekdays=["tue", "thu", "sun"],
        created_at=AS_OF - timedelta(days=60),
        updated_at=AS_OF - timedelta(days=20),
    )
    plan = TrainingPlan(
        id="plan-weekly-memory",
        goal_id=goal.id,
        week_start=WEEK_START,
        status="completed",
        revision=3,
        source="deterministic",
        sessions=[
            PlanSession(
                id="session-easy",
                scheduled_for=WEEK_START + timedelta(days=1),
                session_type="easy",
                duration_seconds=1800,
                purpose="轻松跑",
            ),
            PlanSession(
                id="session-tempo",
                scheduled_for=WEEK_START + timedelta(days=3),
                session_type="tempo",
                duration_seconds=2400,
                purpose="节奏训练",
            ),
            PlanSession(
                id="session-long",
                scheduled_for=WEEK_START + timedelta(days=6),
                session_type="long_run",
                duration_seconds=3600,
                purpose="长距离耐力",
            ),
        ],
        created_at=AS_OF - timedelta(days=14),
        updated_at=AS_OF - timedelta(days=1),
    )
    easy = _activity("activity-easy-1", WEEK_START + timedelta(days=1), 1860, 5200)
    with database.session() as session:
        TrainingGoalRepository(session).save(goal)
        TrainingPlanRepository(session).save(plan)
        ActivityRepository(session).upsert(easy)
        confirmations = TrainingExecutionConfirmationRepository(session)
        confirmations.save(
            TrainingExecutionConfirmation(
                id="confirmation-easy",
                plan_id=plan.id,
                base_revision=1,
                applied_revision=2,
                session_id="session-easy",
                decision="confirm_match",
                activity_id=easy.id,
                created_at=AS_OF - timedelta(days=5),
            )
        )
        confirmations.save(
            TrainingExecutionConfirmation(
                id="confirmation-tempo",
                plan_id=plan.id,
                base_revision=2,
                applied_revision=3,
                session_id="session-tempo",
                decision="mark_skipped",
                created_at=AS_OF - timedelta(days=3),
            )
        )
        check_ins = CheckInRepository(session)
        check_ins.save(
            DailyCheckIn(
                id="check-in-1",
                day=WEEK_START + timedelta(days=1),
                fatigue=3,
                soreness=2,
                sleep_quality=4,
                readiness=4,
                created_at=AS_OF - timedelta(days=5),
            )
        )
        check_ins.save(
            DailyCheckIn(
                id="check-in-2",
                day=WEEK_START + timedelta(days=4),
                fatigue=4,
                soreness=5,
                sleep_quality=2,
                readiness=2,
                pain_area="小腿",
                pain_severity=3,
                created_at=AS_OF - timedelta(days=2),
            )
        )
        session.commit()
    return goal, plan


def _refresh(database: Database, *, as_of: datetime = AS_OF):
    with database.session() as session:
        result = refresh_weekly_training_memory(
            WeeklyTrainingMemoryBuildRequest(
                goal_id="goal-weekly-memory",
                week_start=WEEK_START,
                as_of=as_of,
            ),
            plans=TrainingPlanRepository(session),
            confirmations=TrainingExecutionConfirmationRepository(session),
            activities=ActivityRepository(session),
            check_ins=CheckInRepository(session),
            plan_changes=PlanChangeRepository(session),
            memories=WeeklyTrainingMemoryRepository(session),
        )
        session.commit()
    return result


def test_weekly_memory_uses_only_confirmed_execution_and_structured_check_ins(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'weekly.db').as_posix()}")
    database.create_schema()
    _seed_week(database)

    result = _refresh(database)
    memory = result.memory

    assert result.outcome == "created"
    assert memory.planned_sessions == 3
    assert memory.confirmed_completed_sessions == 1
    assert memory.confirmed_skipped_sessions == 1
    assert memory.unresolved_sessions == 1
    assert memory.completion_rate == pytest.approx(1 / 3)
    assert memory.actual_duration_seconds == 1860
    assert memory.actual_distance_meters == 5200
    assert memory.check_in_days == 2
    assert memory.average_fatigue == 3.5
    assert memory.average_readiness == 3
    assert memory.max_pain_severity == 3
    assert "unresolved_execution" in memory.missing_data
    assert "activity:activity-easy-1" in memory.source_refs


def test_weekly_memory_is_idempotent_and_new_facts_supersede_old_version(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'versions.db').as_posix()}")
    database.create_schema()
    _, plan = _seed_week(database)
    first = _refresh(database)
    repeated = _refresh(database, as_of=AS_OF + timedelta(minutes=30))
    assert repeated.outcome == "unchanged"
    assert repeated.memory.id == first.memory.id

    long_run = _activity("activity-long-2", WEEK_START + timedelta(days=6), 3700, 10500)
    later = AS_OF + timedelta(hours=1)
    with database.session() as session:
        ActivityRepository(session).upsert(long_run)
        TrainingExecutionConfirmationRepository(session).save(
            TrainingExecutionConfirmation(
                id="confirmation-long",
                plan_id=plan.id,
                base_revision=3,
                applied_revision=4,
                session_id="session-long",
                decision="confirm_match",
                activity_id=long_run.id,
                created_at=later,
            )
        )
        session.commit()
    replacement = _refresh(database, as_of=later + timedelta(minutes=1))

    assert replacement.outcome == "superseded"
    assert replacement.memory.version == 2
    assert replacement.memory.supersedes_id == first.memory.id
    assert replacement.memory.confirmed_completed_sessions == 2
    with database.session() as session:
        old = WeeklyTrainingMemoryRepository(session).get(first.memory.id)
    assert old is not None and old.status == "superseded"


def test_weekly_memory_blocks_unfinished_week_and_future_plan_state(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'boundaries.db').as_posix()}")
    database.create_schema()
    _seed_week(database)
    with pytest.raises(WeeklyTrainingMemoryError, match="尚未结束"):
        _refresh(database, as_of=datetime(2026, 8, 16, 20, tzinfo=timezone.utc))
    with pytest.raises(WeeklyTrainingMemoryError, match="评估时点之后"):
        _refresh(database, as_of=AS_OF - timedelta(days=2))


def test_invalidated_memory_is_excluded_from_planning_context(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'invalidate.db').as_posix()}")
    database.create_schema()
    goal, _ = _seed_week(database)
    created = _refresh(database)
    with database.session() as session:
        repository = WeeklyTrainingMemoryRepository(session)
        invalidated = invalidate_weekly_training_memory(
            created.memory.id,
            memories=repository,
            now=AS_OF + timedelta(hours=1),
        )
        session.commit()
    assert invalidated.status == "invalidated"
    with database.session() as session:
        assert WeeklyTrainingMemoryRepository(session).recent_before(
            goal.id, date(2026, 8, 24)
        ) == []
    regenerated = _refresh(database, as_of=AS_OF + timedelta(hours=2))
    assert regenerated.outcome == "superseded"
    assert regenerated.memory.version == 2
    assert regenerated.memory.supersedes_id == invalidated.id
    with database.session() as session:
        preserved = WeeklyTrainingMemoryRepository(session).get(invalidated.id)
    assert preserved is not None and preserved.status == "invalidated"


def test_planning_hash_and_evidence_include_active_weekly_memories() -> None:
    request = WeeklyPlanDraftRequest(
        goal_id="goal",
        week_start=date(2026, 8, 31),
        as_of=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )
    goal = TrainingGoal(
        id="goal",
        name="十公里",
        event_type="10k",
        target_date=date(2026, 11, 1),
        available_weekdays=["tue", "thu", "sun"],
    )

    def memory(index: int, duration: int) -> WeeklyTrainingMemory:
        start = date(2026, 8, 3) + timedelta(days=index * 7)
        return WeeklyTrainingMemory(
            id=f"memory-{index}",
            goal_id=goal.id,
            plan_id=f"plan-{index}",
            week_start=start,
            week_end=start + timedelta(days=6),
            version=1,
            plan_revision=2,
            input_hash=str(index + 1) * 64,
            planned_sessions=3,
            confirmed_completed_sessions=3,
            confirmed_skipped_sessions=0,
            unresolved_sessions=0,
            completion_rate=1,
            planned_duration_seconds=duration,
            actual_duration_seconds=duration,
            actual_distance_meters=15000,
            check_in_days=2,
            average_fatigue=3,
            average_soreness=2,
            average_sleep_quality=4,
            average_readiness=4,
            max_pain_severity=0,
            acute_symptom_days=0,
            approved_plan_changes=0,
            summary="稳定完成训练。",
            source_refs=[f"plan:plan-{index}@revision:2"],
            generated_at=request.as_of - timedelta(days=1),
            updated_at=request.as_of - timedelta(days=1),
        )

    without_memory = build_weekly_plan_draft(
        request,
        goal=goal,
        activities=[],
        existing_plan=None,
    )
    with_memory = build_weekly_plan_draft(
        request,
        goal=goal,
        activities=[],
        existing_plan=None,
        weekly_training_memories=[memory(0, 3600), memory(1, 4200)],
    )

    assert without_memory.input_hash != with_memory.input_hash
    evidence = next(
        item for item in with_memory.evidence if item.type == "weekly_training_memory"
    )
    assert evidence.rule_source == "confirmed_training_memory"
    weekly_rule = next(
        item
        for item in with_memory.evidence
        if item.id == "rule:weekly_duration"
    )
    assert weekly_rule.values["baseline_source"] == "weekly_training_memory"

    activity_fallback = build_weekly_plan_draft(
        request,
        goal=goal,
        activities=[
            _activity("fallback-1", date(2026, 8, 1), 3600, 8000),
            _activity("fallback-2", date(2026, 8, 8), 3600, 8000),
            _activity("fallback-3", date(2026, 8, 15), 3600, 8000),
        ],
        existing_plan=None,
        weekly_training_memories=[memory(0, 3600)],
    )
    fallback_rule = next(
        item for item in activity_fallback.evidence if item.id == "rule:weekly_duration"
    )
    assert fallback_rule.values["baseline_source"] == "normalized_activity"
    assert fallback_rule.values["sufficient_history"] is True


def test_weekly_memory_api_cli_and_schema(tmp_path: Path) -> None:
    path = tmp_path / "interfaces.db"
    database = Database(f"sqlite:///{path.as_posix()}")
    database.create_schema()
    goal, _ = _seed_week(database)
    training_service = TrainingOperationsService(database_path=path, clock=lambda: AS_OF)
    application = DemoApplication(
        DemoDashboardService(database_path=path, evaluation_directory=tmp_path / "evals"),
        training_service=training_service,
    )
    payload = {"week_start": WEEK_START.isoformat(), "as_of": AS_OF.isoformat()}
    created = application.handle(
        "POST",
        f"/api/training/goals/{goal.id}/weekly-memories",
        json.dumps(payload).encode(),
    )
    listed = application.handle(
        "GET", f"/api/training/goals/{goal.id}/weekly-memories"
    )
    assert created.status == 201
    assert json.loads(created.body)["memory"]["version"] == 1
    assert len(json.loads(listed.body)) == 1

    runner = CliRunner()
    cli = runner.invoke(
        app,
        [
            "memory",
            "build-week",
            "--goal-id",
            goal.id,
            "--week-start",
            WEEK_START.isoformat(),
            "--as-of",
            AS_OF.isoformat(),
            "--db",
            str(path),
        ],
    )
    assert cli.exit_code == 0, cli.output
    assert json.loads(cli.output)["outcome"] == "unchanged"

    schema = json.loads(
        Path("schemas/training-operations/weekly-memory.schema.json").read_text("utf-8")
    )
    assert schema == WeeklyTrainingMemory.model_json_schema()


def test_training_operations_build_submission_contract() -> None:
    submission = WeeklyTrainingMemoryBuildSubmission(
        week_start=WEEK_START,
        as_of=AS_OF,
    )
    assert submission.to_request("goal").goal_id == "goal"
