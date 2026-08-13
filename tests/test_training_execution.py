from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from runcrew.cli import app
from runcrew.domain.activity import ActivitySummary, SourceProvider, SourceRef, SportType
from runcrew.domain.training_cycle import PlanSession, TrainingGoal, TrainingPlan
from runcrew.domain.training_execution import (
    ExecutionConfirmationResult,
    TrainingExecutionDecisionRequest,
    TrainingExecutionRequest,
    TrainingExecutionResult,
)
from runcrew.services.training_cycle import TrainingCycleService
from runcrew.services.training_execution import (
    TrainingExecutionError,
    build_training_comparison,
    confirm_training_execution,
)
from runcrew.storage.database import Database
from runcrew.storage.repositories import (
    ActivityRepository,
    CheckInRepository,
    PlanChangeRepository,
    TrainingExecutionConfirmationRepository,
    TrainingGoalRepository,
    TrainingPlanRepository,
)


ANCHOR = datetime(2026, 8, 16, 20, tzinfo=timezone(timedelta(hours=8)))
WEEK_START = date(2026, 8, 10)


def activity(
    identifier: str,
    day: date,
    *,
    distance: float | None = 5000,
    duration: int = 1800,
    sport: SportType = SportType.RUN,
    hour: int = 8,
) -> ActivitySummary:
    return ActivitySummary(
        id=identifier,
        source_ref=SourceRef(
            provider=SourceProvider.FIXTURE,
            external_id=identifier,
            fetched_at=ANCHOR,
            raw_payload_hash=f"hash-{identifier}",
        ),
        sport_type=sport,
        started_at=datetime(day.year, day.month, day.day, hour, tzinfo=ANCHOR.tzinfo),
        duration_seconds=duration,
        distance_meters=distance,
    )


def plan(*sessions: PlanSession, revision: int = 1) -> TrainingPlan:
    return TrainingPlan(
        id="plan-1",
        goal_id="goal-1",
        week_start=WEEK_START,
        status="active",
        revision=revision,
        sessions=list(sessions),
    )


def session(
    identifier: str = "session-1",
    *,
    day: date = date(2026, 8, 13),
    status: str = "planned",
    linked_activity_id: str | None = None,
    session_type: str = "easy",
    distance: float | None = 5000,
    duration: int | None = 1800,
) -> PlanSession:
    return PlanSession(
        id=identifier,
        scheduled_for=day,
        session_type=session_type,
        distance_meters=distance,
        duration_seconds=duration,
        purpose="测试计划课",
        status=status,
        linked_activity_id=linked_activity_id,
    )


def request(**updates) -> TrainingExecutionRequest:
    values = {"plan_id": "plan-1", "as_of": ANCHOR, "provider": "fixture"}
    values.update(updates)
    return TrainingExecutionRequest(**values)


def test_clear_candidate_is_suggested_but_not_confirmed() -> None:
    result = build_training_comparison(
        request(),
        plan=plan(session()),
        activities=[activity("run-1", date(2026, 8, 13))],
    )
    comparison = result.sessions[0]
    assert comparison.outcome == "complete"
    assert comparison.match_state == "suggested"
    assert comparison.requires_user_confirmation is True
    assert comparison.suggested_activity_id == "run-1"


def test_partial_completion_uses_conservative_minimum_ratio() -> None:
    result = build_training_comparison(
        request(),
        plan=plan(session(distance=10000, duration=3600)),
        activities=[
            activity("short-run", date(2026, 8, 13), distance=7000, duration=3300)
        ],
    )
    comparison = result.sessions[0]
    assert comparison.outcome == "partial"
    assert comparison.completion_ratio == 0.7


def test_missing_candidate_is_unmatched_not_automatically_skipped() -> None:
    result = build_training_comparison(
        request(), plan=plan(session()), activities=[]
    )
    comparison = result.sessions[0]
    assert comparison.outcome == "unmatched"
    assert comparison.match_state == "none"
    assert comparison.requires_user_confirmation is True


def test_future_activity_is_excluded_and_future_session_is_upcoming() -> None:
    future_session = session(day=date(2026, 8, 15))
    future_activity = activity("future", date(2026, 8, 15))
    result = build_training_comparison(
        request(as_of=datetime(2026, 8, 14, 20, tzinfo=ANCHOR.tzinfo)),
        plan=plan(future_session),
        activities=[future_activity],
    )
    assert result.sessions[0].outcome == "upcoming"
    assert "future" not in result.unassigned_activity_ids


def test_ambiguous_candidates_and_shared_best_never_auto_select() -> None:
    close = build_training_comparison(
        request(),
        plan=plan(session()),
        activities=[
            activity("run-a", date(2026, 8, 13)),
            activity("run-b", date(2026, 8, 13), distance=4900, hour=18),
        ],
    )
    shared = build_training_comparison(
        request(),
        plan=plan(
            session("session-a"),
            session("session-b", day=date(2026, 8, 14)),
        ),
        activities=[activity("only-run", date(2026, 8, 13))],
    )
    assert close.sessions[0].match_state == "ambiguous"
    assert {item.match_state for item in shared.sessions} == {"ambiguous"}


def test_confirmed_link_is_high_confidence_and_broken_link_is_visible() -> None:
    linked = build_training_comparison(
        request(),
        plan=plan(session(status="completed", linked_activity_id="run-1")),
        activities=[activity("run-1", date(2026, 8, 13))],
    )
    broken = build_training_comparison(
        request(),
        plan=plan(session(status="completed", linked_activity_id="missing")),
        activities=[],
    )
    assert linked.sessions[0].match_state == "confirmed"
    assert linked.sessions[0].confidence == "high"
    assert broken.sessions[0].match_state == "broken_link"
    assert broken.sessions[0].outcome == "unmatched"


def test_replay_is_stable_and_filters_non_running_activity() -> None:
    run = activity("run", date(2026, 8, 13))
    bike = activity("bike", date(2026, 8, 13), sport=SportType.OTHER)
    first = build_training_comparison(
        request(), plan=plan(session()), activities=[run, bike]
    )
    second = build_training_comparison(
        request(), plan=plan(session()), activities=[bike, run]
    )
    assert first == second
    assert "bike" not in first.unassigned_activity_ids


class PlanStore:
    def __init__(self, value: TrainingPlan) -> None:
        self.value = value

    def get(self, plan_id: str):
        return self.value if self.value.id == plan_id else None

    def save(self, value: TrainingPlan) -> None:
        self.value = value


class ActivityStore:
    def __init__(self, values: list[ActivitySummary]) -> None:
        self.values = {item.id: item for item in values}

    def get_by_id(self, activity_id: str):
        return self.values.get(activity_id)

    def between(self, start, end, *, provider=None):
        return [item for item in self.values.values() if start < item.started_at <= end]


class ConfirmationStore:
    def __init__(self) -> None:
        self.values = []

    def save(self, confirmation) -> None:
        self.values.append(confirmation)


def decision(kind: str, **updates) -> TrainingExecutionDecisionRequest:
    values = {
        "plan_id": "plan-1",
        "base_revision": 1,
        "session_id": "session-1",
        "decision": kind,
        "as_of": ANCHOR,
    }
    if kind == "confirm_match":
        values["activity_id"] = "run-1"
    values.update(updates)
    return TrainingExecutionDecisionRequest(**values)


def test_user_can_confirm_match_then_clear_execution() -> None:
    plans = PlanStore(plan(session()))
    activities = ActivityStore([activity("run-1", date(2026, 8, 13))])
    confirmations = ConfirmationStore()
    matched = confirm_training_execution(
        decision("confirm_match"),
        plans=plans,
        activities=activities,
        confirmations=confirmations,
    )
    assert matched.plan.revision == 2
    assert matched.plan.sessions[0].status == "completed"
    assert matched.plan.sessions[0].linked_activity_id == "run-1"

    cleared = confirm_training_execution(
        decision("clear_execution", base_revision=2),
        plans=plans,
        activities=activities,
        confirmations=confirmations,
    )
    assert cleared.plan.revision == 3
    assert cleared.plan.sessions[0].status == "planned"
    assert cleared.plan.sessions[0].linked_activity_id is None


def test_skip_requires_user_action_and_stale_revision_does_not_write() -> None:
    plans = PlanStore(plan(session(), revision=2))
    confirmations = ConfirmationStore()
    stale = confirm_training_execution(
        decision("mark_skipped"),
        plans=plans,
        activities=ActivityStore([]),
        confirmations=confirmations,
    )
    assert stale.confirmation.status == "stale"
    assert plans.value.sessions[0].status == "planned"

    applied = confirm_training_execution(
        decision("mark_skipped", base_revision=2),
        plans=plans,
        activities=ActivityStore([]),
        confirmations=confirmations,
    )
    assert applied.plan.sessions[0].status == "skipped"
    assert applied.plan.revision == 3


def test_confirmation_rejects_future_far_or_duplicate_activity() -> None:
    future_plan = PlanStore(plan(session(day=date(2026, 8, 15))))
    with pytest.raises(TrainingExecutionError, match="尚未到"):
        confirm_training_execution(
            decision(
                "mark_skipped",
                as_of=datetime(2026, 8, 14, 20, tzinfo=ANCHOR.tzinfo),
            ),
            plans=future_plan,
            activities=ActivityStore([]),
            confirmations=ConfirmationStore(),
        )

    far = ActivityStore([activity("run-1", date(2026, 8, 5))])
    with pytest.raises(TrainingExecutionError, match="超过3天"):
        confirm_training_execution(
            decision("confirm_match"),
            plans=PlanStore(plan(session())),
            activities=far,
            confirmations=ConfirmationStore(),
        )

    duplicate_plan = plan(
        session("session-1"),
        session(
            "session-2",
            status="completed",
            linked_activity_id="run-1",
            day=date(2026, 8, 14),
        ),
    )
    with pytest.raises(TrainingExecutionError, match="已经关联"):
        confirm_training_execution(
            decision("confirm_match"),
            plans=PlanStore(duplicate_plan),
            activities=ActivityStore([activity("run-1", date(2026, 8, 13))]),
            confirmations=ConfirmationStore(),
        )


def cycle_service(session_) -> TrainingCycleService:
    return TrainingCycleService(
        goals=TrainingGoalRepository(session_),
        plans=TrainingPlanRepository(session_),
        check_ins=CheckInRepository(session_),
        changes=PlanChangeRepository(session_),
    )


def seed(database: Database) -> None:
    with database.session() as database_session:
        TrainingGoalRepository(database_session).save(
            TrainingGoal(
                id="goal-1",
                name="执行对照测试",
                event_type="10k",
                target_date=date(2026, 10, 1),
                available_weekdays=["thu"],
            )
        )
        TrainingPlanRepository(database_session).save(plan(session()))
        ActivityRepository(database_session).upsert(
            activity("run-1", date(2026, 8, 13))
        )
        database_session.commit()


def test_cli_compare_and_decide_persist_auditable_confirmation(tmp_path: Path) -> None:
    path = tmp_path / "execution.db"
    database = Database(f"sqlite:///{path.as_posix()}")
    database.create_schema()
    seed(database)
    runner = CliRunner()
    compared = runner.invoke(
        app,
        [
            "execution",
            "compare",
            "--plan-id",
            "plan-1",
            "--as-of",
            ANCHOR.isoformat(),
            "--provider",
            "fixture",
            "--db",
            str(path),
        ],
    )
    assert compared.exit_code == 0, compared.output
    payload = json.loads(compared.output)
    assert payload["sessions"][0]["match_state"] == "suggested"

    decided = runner.invoke(
        app,
        [
            "execution",
            "decide",
            "--plan-id",
            "plan-1",
            "--base-revision",
            "1",
            "--session-id",
            "session-1",
            "--decision",
            "confirm_match",
            "--activity-id",
            "run-1",
            "--as-of",
            ANCHOR.isoformat(),
            "--db",
            str(path),
        ],
    )
    assert decided.exit_code == 0, decided.output
    decision_payload = json.loads(decided.output)
    assert decision_payload["plan"]["revision"] == 2
    with database.session() as database_session:
        records = TrainingExecutionConfirmationRepository(database_session).for_plan(
            "plan-1"
        )
        assert len(records) == 1
        assert records[0].status == "applied"


def test_exported_execution_schemas_match_models() -> None:
    references = Path("skills/compare-training-execution/references")
    assert json.loads((references / "compare-input.schema.json").read_text("utf-8")) == (
        TrainingExecutionRequest.model_json_schema()
    )
    assert json.loads((references / "decision-input.schema.json").read_text("utf-8")) == (
        TrainingExecutionDecisionRequest.model_json_schema()
    )
    assert json.loads((references / "output.schema.json").read_text("utf-8")) == (
        TrainingExecutionResult.model_json_schema()
    )
    assert json.loads((references / "decision-output.schema.json").read_text("utf-8")) == (
        ExecutionConfirmationResult.model_json_schema()
    )
