from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from runcrew.cli import app
from runcrew.domain.activity import ActivitySummary, SourceProvider, SourceRef, SportType
from runcrew.domain.recovery_assessment import (
    RecoveryAssessmentRequest,
    RecoveryAssessmentResult,
)
from runcrew.domain.training_cycle import DailyCheckIn, PlanSession, TrainingGoal
from runcrew.services.recovery_assessment import (
    RecoveryAssessmentGoalNotFoundError,
    build_recovery_assessment,
    execute_recovery_assessment,
)
from runcrew.services.recovery_context import build_recovery_context
from runcrew.services.training_cycle import TrainingCycleService
from runcrew.storage.database import Database
from runcrew.storage.repositories import (
    ActivityRepository,
    CheckInRepository,
    PlanChangeRepository,
    TrainingGoalRepository,
    TrainingPlanRepository,
)


ANCHOR = datetime(2026, 8, 13, 8, tzinfo=timezone.utc)


def activity(identifier: str, days_before: int, load: float | None) -> ActivitySummary:
    return ActivitySummary(
        id=identifier,
        source_ref=SourceRef(
            provider=SourceProvider.FIXTURE,
            external_id=identifier,
            fetched_at=ANCHOR,
            raw_payload_hash=f"hash-{identifier}",
        ),
        sport_type=SportType.RUN,
        started_at=ANCHOR - timedelta(days=days_before),
        duration_seconds=3600,
        distance_meters=10000,
        training_load=load,
    )


def planned_session() -> PlanSession:
    return PlanSession(
        id="next-quality-session",
        scheduled_for=date(2026, 8, 15),
        session_type="interval",
        distance_meters=6000,
        purpose="提高速度耐力",
    )


def assess(
    check_in: DailyCheckIn | None,
    *,
    activities: list[ActivitySummary] | None = None,
    next_session: PlanSession | None = None,
) -> RecoveryAssessmentResult:
    request = RecoveryAssessmentRequest(
        goal_id="goal-1", assessed_at=ANCHOR, provider="fixture"
    )
    context = build_recovery_context(
        request,
        activities=activities or [],
        check_ins=[check_in] if check_in else [],
        next_session=next_session,
    )
    return build_recovery_assessment(context)


@pytest.mark.parametrize(
    ("check_in", "expected", "risk"),
    [
        (
            DailyCheckIn(
                day=ANCHOR.date(), fatigue=2, soreness=2, sleep_quality=4
            ),
            "proceed",
            "low",
        ),
        (
            DailyCheckIn(
                day=ANCHOR.date(),
                fatigue=3,
                soreness=4,
                sleep_quality=3,
                pain_area="右膝",
                pain_severity=3,
            ),
            "reduce",
            "moderate",
        ),
        (
            DailyCheckIn(
                day=ANCHOR.date(), fatigue=4, soreness=3, sleep_quality=2
            ),
            "rest",
            "high",
        ),
        (
            DailyCheckIn(
                day=ANCHOR.date(),
                fatigue=2,
                soreness=2,
                sleep_quality=4,
                acute_symptoms=["chest_pain_or_pressure"],
            ),
            "seek_professional_help",
            "escalate",
        ),
    ],
)
def test_recovery_rules_cover_all_actionable_levels(
    check_in: DailyCheckIn, expected: str, risk: str
) -> None:
    result = assess(check_in, next_session=planned_session())
    assert result.recommendation == expected
    assert result.risk_level == risk
    assert result.input_hash
    assert all(item.rule_source for item in result.evidence)


def test_missing_or_stale_check_in_never_defaults_to_proceed() -> None:
    missing = assess(None, next_session=planned_session())
    stale = assess(
        DailyCheckIn(
            day=ANCHOR.date() - timedelta(days=3),
            fatigue=1,
            soreness=0,
            sleep_quality=5,
        ),
        next_session=planned_session(),
    )
    assert missing.recommendation == "insufficient_data"
    assert stale.recommendation == "insufficient_data"
    assert "fresh_check_in" in stale.missing_data


def test_red_flag_escalates_even_when_check_in_is_old() -> None:
    result = assess(
        DailyCheckIn(
            day=ANCHOR.date() - timedelta(days=3),
            fatigue=2,
            soreness=1,
            sleep_quality=4,
            acute_symptoms=["fainting_or_severe_dizziness"],
        ),
        next_session=planned_session(),
    )
    assert result.recommendation == "seek_professional_help"
    assert result.confidence == "high"


def test_old_severe_pain_requires_fresh_data_instead_of_current_diagnosis() -> None:
    result = assess(
        DailyCheckIn(
            day=ANCHOR.date() - timedelta(days=3),
            fatigue=2,
            soreness=2,
            sleep_quality=4,
            pain_area="脚踝",
            pain_severity=9,
        ),
        next_session=planned_session(),
    )
    assert result.recommendation == "insufficient_data"
    assert result.risk_level == "unknown"


def test_context_is_replayable_and_excludes_future_data() -> None:
    request = RecoveryAssessmentRequest(goal_id="goal-1", assessed_at=ANCHOR)
    past = DailyCheckIn(
        day=ANCHOR.date(), fatigue=2, soreness=1, sleep_quality=4
    )
    future = DailyCheckIn(
        day=ANCHOR.date() + timedelta(days=1),
        fatigue=5,
        soreness=8,
        sleep_quality=1,
        pain_area="小腿",
        pain_severity=7,
    )
    future_activity = activity("future", -1, 99)
    first = build_recovery_context(
        request,
        activities=[activity("past", 1, 40), future_activity],
        check_ins=[past, future],
        next_session=planned_session(),
    )
    second = build_recovery_context(
        request,
        activities=[future_activity, activity("past", 1, 40)],
        check_ins=[future, past],
        next_session=planned_session(),
    )
    assert first.input_hash == second.input_hash
    assert [item.id for item in first.activities] == ["past"]
    assert [item.day for item in first.check_ins] == [ANCHOR.date()]


def test_training_volume_falls_back_to_duration_proxy() -> None:
    history = [
        activity("previous", 10, None),
        activity("current-a", 2, None),
        activity("current-b", 1, None),
    ]
    result = assess(
        DailyCheckIn(
            day=ANCHOR.date(), fatigue=2, soreness=1, sleep_quality=4
        ),
        activities=history,
        next_session=planned_session(),
    )
    volume = next(item for item in result.evidence if item.type == "training_volume")
    assert volume.values["method"] == "duration_seconds_proxy"
    assert volume.values["change_ratio"] == 1
    assert result.recommendation == "reduce"


def build_cycle_service(session) -> TrainingCycleService:
    return TrainingCycleService(
        goals=TrainingGoalRepository(session),
        plans=TrainingPlanRepository(session),
        check_ins=CheckInRepository(session),
        changes=PlanChangeRepository(session),
    )


def seed_database(database: Database) -> str:
    with database.session() as session:
        goal = TrainingGoal(
            id="goal-1",
            name="10公里目标",
            event_type="10k",
            target_date=date(2026, 10, 18),
            available_weekdays=["thu", "sat"],
        )
        cycle = build_cycle_service(session)
        cycle.create_goal(goal)
        plan = cycle.create_plan(goal_id=goal.id, week_start=date(2026, 8, 10))
        cycle.add_draft_session(plan.id, planned_session())
        cycle.activate_plan(plan.id)
        cycle.record_check_in(
            DailyCheckIn(
                day=ANCHOR.date(), fatigue=3, soreness=3, sleep_quality=3
            )
        )
        ActivityRepository(session).upsert(activity("history", 1, 40))
        session.commit()
    return goal.id


def test_execute_validates_goal_and_reads_persisted_cycle(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'recovery.db').as_posix()}")
    database.create_schema()
    goal_id = seed_database(database)
    request = RecoveryAssessmentRequest(
        goal_id=goal_id, assessed_at=ANCHOR, provider="fixture"
    )
    with database.session() as session:
        result = execute_recovery_assessment(
            request,
            activities=ActivityRepository(session),
            check_ins=CheckInRepository(session),
            plans=TrainingPlanRepository(session),
            goals=TrainingGoalRepository(session),
        )
        with pytest.raises(RecoveryAssessmentGoalNotFoundError):
            execute_recovery_assessment(
                request.model_copy(update={"goal_id": "missing"}),
                activities=ActivityRepository(session),
                check_ins=CheckInRepository(session),
                plans=TrainingPlanRepository(session),
                goals=TrainingGoalRepository(session),
            )
    assert result.goal_id == goal_id
    assert result.plan_action.target_session_id == "next-quality-session"


def test_recovery_cli_returns_validated_json(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'cli.db').as_posix()}")
    database.create_schema()
    goal_id = seed_database(database)
    completed = CliRunner().invoke(
        app,
        [
            "recovery",
            "assess",
            "--goal-id",
            goal_id,
            "--assessed-at",
            ANCHOR.isoformat(),
            "--provider",
            "fixture",
            "--db",
            str(tmp_path / "cli.db"),
        ],
    )
    assert completed.exit_code == 0, completed.output
    payload = json.loads(completed.output)
    assert payload["schema_version"] == "1.0"
    assert payload["recommendation"] in {
        "proceed",
        "reduce",
        "rest",
        "seek_professional_help",
        "insufficient_data",
    }

    missing = CliRunner().invoke(
        app,
        [
            "recovery",
            "assess",
            "--goal-id",
            "missing",
            "--assessed-at",
            ANCHOR.isoformat(),
            "--db",
            str(tmp_path / "cli.db"),
        ],
    )
    assert missing.exit_code != 0
    assert "不存在或当前未激活" in missing.output
    assert "Traceback" not in missing.output


def test_exported_recovery_schemas_match_domain_models() -> None:
    references = Path("skills/assess-running-recovery/references")
    assert json.loads((references / "input.schema.json").read_text("utf-8")) == (
        RecoveryAssessmentRequest.model_json_schema()
    )
    assert json.loads((references / "output.schema.json").read_text("utf-8")) == (
        RecoveryAssessmentResult.model_json_schema()
    )
