from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from typer.testing import CliRunner

from runcrew.cli import app
from runcrew.domain.activity import ActivitySummary, SourceProvider, SourceRef, SportType
from runcrew.domain.recovery_assessment import RecoveryPlanAction
from runcrew.domain.training_cycle import DailyCheckIn, PlanSession, TrainingGoal
from runcrew.domain.training_planning import PlanAdjustmentRequest, WeeklyPlanDraftRequest
from runcrew.services.training_cycle import TrainingCycleService
from runcrew.services.training_planning import (
    build_plan_adjustment,
    build_weekly_plan_draft,
)
from runcrew.storage.database import Database
from runcrew.storage.repositories import (
    ActivityRepository,
    CheckInRepository,
    PlanChangeRepository,
    TrainingGoalRepository,
    TrainingPlanRepository,
)


ANCHOR = datetime(2026, 8, 13, 8, tzinfo=timezone.utc)
WEEK_START = date(2026, 8, 17)


def goal(**updates) -> TrainingGoal:
    values = {
        "id": "goal-1",
        "name": "10公里目标",
        "event_type": "10k",
        "target_date": date(2026, 10, 18),
        "available_weekdays": ["mon", "tue", "wed", "thu", "sat", "sun"],
    }
    values.update(updates)
    return TrainingGoal(**values)


def activity(identifier: str, days_before: int, duration: int = 2400) -> ActivitySummary:
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
        duration_seconds=duration,
        distance_meters=6000,
    )


def draft_request(**updates) -> WeeklyPlanDraftRequest:
    values = {
        "goal_id": "goal-1",
        "week_start": WEEK_START,
        "as_of": ANCHOR,
        "provider": "fixture",
    }
    values.update(updates)
    return WeeklyPlanDraftRequest(**values)


def test_draft_is_replayable_spaced_and_uses_only_available_days() -> None:
    history = [activity(f"run-{index}", index + 1) for index in range(8)]
    first = build_weekly_plan_draft(
        draft_request(), goal=goal(), activities=history, existing_plan=None
    )
    second = build_weekly_plan_draft(
        draft_request(), goal=goal(), activities=list(reversed(history)), existing_plan=None
    )
    assert first == second
    assert first.status == "ready"
    assert first.weekly_plan_draft is not None
    sessions = first.weekly_plan_draft.sessions
    assert [item.scheduled_for.weekday() for item in sessions] == [0, 3, 6]
    assert [item.session_type for item in sessions] == ["easy", "tempo", "long_run"]
    assert first.weekly_plan_draft.requires_user_confirmation is True


def test_missing_history_uses_conservative_template_without_quality_session() -> None:
    result = build_weekly_plan_draft(
        draft_request(), goal=goal(), activities=[], existing_plan=None
    )
    assert result.status == "ready"
    assert result.weekly_plan_draft is not None
    assert result.weekly_plan_draft.total_duration_seconds == 70 * 60
    assert {item.session_type for item in result.weekly_plan_draft.sessions} == {
        "easy",
        "long_run",
    }
    assert result.warnings


def test_future_activity_does_not_change_historical_draft() -> None:
    past = activity("past", 2)
    future = activity("future", -1, duration=9999)
    with_future = build_weekly_plan_draft(
        draft_request(), goal=goal(), activities=[past, future], existing_plan=None
    )
    without_future = build_weekly_plan_draft(
        draft_request(), goal=goal(), activities=[past], existing_plan=None
    )
    assert with_future == without_future


def test_existing_plan_and_event_week_are_blocked() -> None:
    from runcrew.domain.training_cycle import TrainingPlan

    existing = TrainingPlan(goal_id="goal-1", week_start=WEEK_START)
    occupied = build_weekly_plan_draft(
        draft_request(), goal=goal(), activities=[], existing_plan=existing
    )
    event_week = build_weekly_plan_draft(
        draft_request(),
        goal=goal(target_date=WEEK_START + timedelta(days=3)),
        activities=[],
        existing_plan=None,
    )
    assert occupied.status == "blocked"
    assert occupied.missing_data == ["week_already_has_plan"]
    assert event_week.status == "blocked"
    assert event_week.missing_data == ["event_week_requires_manual_plan"]


def test_current_week_and_non_running_history_do_not_create_false_baseline() -> None:
    current_week = build_weekly_plan_draft(
        draft_request(week_start=date(2026, 8, 10)),
        goal=goal(),
        activities=[],
        existing_plan=None,
    )
    other = activity("bike", 2).model_copy(update={"sport_type": SportType.OTHER})
    future_week = build_weekly_plan_draft(
        draft_request(), goal=goal(), activities=[other], existing_plan=None
    )
    assert current_week.status == "blocked"
    assert current_week.missing_data == ["week_not_in_future"]
    assert future_week.weekly_plan_draft is not None
    assert future_week.weekly_plan_draft.total_duration_seconds == 70 * 60


def active_plan_and_session():
    from runcrew.domain.training_cycle import TrainingPlan

    session = PlanSession(
        id="quality-1",
        scheduled_for=date(2026, 8, 15),
        session_type="interval",
        distance_meters=8000,
        duration_seconds=3600,
        intensity="高强度",
        purpose="速度耐力",
    )
    plan = TrainingPlan(
        id="plan-1",
        goal_id="goal-1",
        week_start=date(2026, 8, 10),
        status="active",
        revision=3,
        sessions=[session],
    )
    return plan, session


def adjustment_request(action: str, recommendation: str) -> PlanAdjustmentRequest:
    target = "quality-1" if action.startswith("ask_plan_agent") else None
    return PlanAdjustmentRequest(
        goal_id="goal-1",
        assessed_at=ANCHOR,
        recovery_input_hash="a" * 64,
        recovery_recommendation=recommendation,
        plan_action=RecoveryPlanAction(
            action=action,
            target_session_id=target,
            requires_user_confirmation=action != "keep",
            reason="恢复评估动作",
        ),
        evidence_refs=["fatigue:2026-08-13"],
    )


def test_reduce_generates_non_increasing_revision_bound_proposal() -> None:
    plan, session = active_plan_and_session()
    result = build_plan_adjustment(
        adjustment_request("ask_plan_agent_to_reduce", "reduce"),
        goal=goal(),
        active_plan=plan,
        target_session=session,
    )
    assert result.status == "ready"
    assert result.change_proposal_draft is not None
    draft = result.change_proposal_draft
    change = draft.changes[0]
    assert draft.base_revision == 3
    assert draft.requires_user_confirmation is True
    assert change.distance_meters == 4800
    assert change.duration_seconds == 2160
    assert change.session_type == "recovery"


def test_rest_clears_workload_and_keep_or_escalation_never_proposes() -> None:
    plan, session = active_plan_and_session()
    rest = build_plan_adjustment(
        adjustment_request("ask_plan_agent_to_replace_with_rest", "rest"),
        goal=goal(),
        active_plan=plan,
        target_session=session,
    )
    assert rest.change_proposal_draft is not None
    patch = rest.change_proposal_draft.changes[0]
    assert patch.session_type == "rest"
    assert patch.clear_distance and patch.clear_duration and patch.clear_intensity

    keep = build_plan_adjustment(
        adjustment_request("keep", "proceed"),
        goal=goal(),
        active_plan=None,
        target_session=None,
    )
    escalation = build_plan_adjustment(
        adjustment_request("hold_until_professional_review", "seek_professional_help"),
        goal=goal(),
        active_plan=None,
        target_session=None,
    )
    assert keep.status == "no_change" and keep.change_proposal_draft is None
    assert escalation.status == "blocked"
    assert escalation.missing_data == ["professional_review"]


def test_past_or_already_resting_target_never_creates_proposal() -> None:
    plan, session = active_plan_and_session()
    past = session.model_copy(update={"scheduled_for": date(2026, 8, 12)})
    past_result = build_plan_adjustment(
        adjustment_request("ask_plan_agent_to_reduce", "reduce"),
        goal=goal(),
        active_plan=plan.model_copy(update={"sessions": [past]}),
        target_session=past,
    )
    resting = PlanSession(
        id="quality-1",
        scheduled_for=date(2026, 8, 15),
        session_type="rest",
        purpose="休息",
    )
    rest_result = build_plan_adjustment(
        adjustment_request("ask_plan_agent_to_replace_with_rest", "rest"),
        goal=goal(),
        active_plan=plan.model_copy(update={"sessions": [resting]}),
        target_session=resting,
    )
    assert past_result.status == "blocked"
    assert past_result.missing_data == ["future_target_session"]
    assert rest_result.status == "no_change"
    assert rest_result.change_proposal_draft is None


def cycle_service(session) -> TrainingCycleService:
    return TrainingCycleService(
        goals=TrainingGoalRepository(session),
        plans=TrainingPlanRepository(session),
        check_ins=CheckInRepository(session),
        changes=PlanChangeRepository(session),
    )


def seed(database: Database) -> None:
    with database.session() as session:
        cycle = cycle_service(session)
        cycle.create_goal(goal(available_weekdays=["thu", "sat"]))
        plan = cycle.create_plan(goal_id="goal-1", week_start=date(2026, 8, 10))
        cycle.add_draft_session(plan.id, active_plan_and_session()[1])
        cycle.activate_plan(plan.id)
        cycle.record_check_in(
            DailyCheckIn(
                day=ANCHOR.date(),
                fatigue=3,
                soreness=3,
                sleep_quality=3,
                pain_area="右膝",
                pain_severity=3,
            )
        )
        ActivityRepository(session).upsert(activity("history", 5))
        session.commit()


def test_planning_cli_composes_recovery_without_writing_proposal(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'planning.db').as_posix()}")
    database.create_schema()
    seed(database)
    runner = CliRunner()
    completed = runner.invoke(
        app,
        [
            "planning",
            "adjust",
            "--goal-id",
            "goal-1",
            "--assessed-at",
            ANCHOR.isoformat(),
            "--provider",
            "fixture",
            "--db",
            str(tmp_path / "planning.db"),
        ],
    )
    assert completed.exit_code == 0, completed.output
    payload = json.loads(completed.output)
    assert payload["source_recovery_assessment"]["recommendation"] == "reduce"
    assert payload["change_proposal_draft"]["proposed_by"] == "plan_agent"
    with database.session() as session:
        assert PlanChangeRepository(session).pending_for_goal("goal-1") == []


def test_exported_planning_schemas_match_domain_models() -> None:
    from runcrew.domain.training_planning import TrainingPlanningResult

    references = Path("skills/draft-running-plan/references")
    assert json.loads((references / "draft-input.schema.json").read_text("utf-8")) == (
        WeeklyPlanDraftRequest.model_json_schema()
    )
    assert json.loads((references / "adjust-input.schema.json").read_text("utf-8")) == (
        PlanAdjustmentRequest.model_json_schema()
    )
    assert json.loads((references / "output.schema.json").read_text("utf-8")) == (
        TrainingPlanningResult.model_json_schema()
    )
