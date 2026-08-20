from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from runcrew.cli import app
from runcrew.domain.memory import AthletePreference, AthletePreferenceSubmission
from runcrew.domain.training_cycle import TrainingGoal
from runcrew.domain.training_planning import WeeklyPlanDraftRequest
from runcrew.services.athlete_memory import (
    AthleteMemoryError,
    archive_athlete_preference,
    confirm_athlete_preference,
    preferences_for_display,
)
from runcrew.services.training_planning import build_weekly_plan_draft
from runcrew.services.training_operations import TrainingOperationsService
from runcrew.storage.database import Database
from runcrew.storage.repositories import AthletePreferenceRepository
from runcrew.web import DemoApplication, DemoDashboardService


ANCHOR = datetime(2026, 8, 19, 8, tzinfo=timezone.utc)
WEEK_START = date(2026, 8, 24)


def submission(value: str, *, valid_until: datetime | None = None):
    return AthletePreferenceSubmission(
        key="preferred_long_run_weekday",
        value=value,
        confirmed=True,
        valid_until=valid_until,
    )


def test_preference_write_requires_explicit_confirmation() -> None:
    with pytest.raises(ValidationError):
        AthletePreferenceSubmission.model_validate(
            {
                "key": "preferred_long_run_weekday",
                "value": "sun",
                "confirmed": False,
            }
        )


def test_confirm_is_idempotent_and_new_value_supersedes_old_version(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'memory.db').as_posix()}")
    database.create_schema()
    with database.session() as session:
        repository = AthletePreferenceRepository(session)
        first = confirm_athlete_preference(
            submission("sun"),
            preferences=repository,
            source_ref="test:settings",
            now=ANCHOR,
        )
        repeated = confirm_athlete_preference(
            submission("sun"),
            preferences=repository,
            source_ref="test:settings",
            now=ANCHOR + timedelta(minutes=1),
        )
        replacement = confirm_athlete_preference(
            submission("sat"),
            preferences=repository,
            source_ref="test:settings",
            now=ANCHOR + timedelta(minutes=2),
        )
        session.commit()

    with database.session() as session:
        repository = AthletePreferenceRepository(session)
        stored_first = repository.get(first.id)
        active = repository.active_at(ANCHOR + timedelta(minutes=3))
    assert repeated.id == first.id
    assert replacement.supersedes_id == first.id
    assert stored_first is not None and stored_first.status == "superseded"
    assert [item.id for item in active] == [replacement.id]


def test_expired_preference_is_not_retrieved_and_is_labeled_for_display(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'expiry.db').as_posix()}")
    database.create_schema()
    expires_at = ANCHOR + timedelta(days=1)
    with database.session() as session:
        repository = AthletePreferenceRepository(session)
        preference = confirm_athlete_preference(
            submission("sun", valid_until=expires_at),
            preferences=repository,
            source_ref="test:settings",
            now=ANCHOR,
        )
        session.commit()
    with database.session() as session:
        repository = AthletePreferenceRepository(session)
        assert repository.active_at(expires_at) == []
        displayed = preferences_for_display(repository, as_of=expires_at)
    assert displayed[0].id == preference.id
    assert displayed[0].status == "expired"


def test_archive_is_auditable_and_cannot_be_repeated(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'archive.db').as_posix()}")
    database.create_schema()
    with database.session() as session:
        repository = AthletePreferenceRepository(session)
        preference = confirm_athlete_preference(
            submission("sun"),
            preferences=repository,
            source_ref="test:settings",
            now=ANCHOR,
        )
        archived = archive_athlete_preference(
            preference.id,
            preferences=repository,
            now=ANCHOR + timedelta(minutes=1),
        )
        with pytest.raises(AthleteMemoryError):
            archive_athlete_preference(
                preference.id,
                preferences=repository,
                now=ANCHOR + timedelta(minutes=2),
            )
        session.commit()
    assert archived.status == "archived"


def test_confirmed_preference_changes_long_run_day_and_is_traced() -> None:
    request = WeeklyPlanDraftRequest(
        goal_id="goal-1",
        week_start=WEEK_START,
        as_of=ANCHOR,
    )
    goal = TrainingGoal(
        id="goal-1",
        name="秋季十公里",
        event_type="10k",
        target_date=date(2026, 10, 18),
        available_weekdays=["tue", "thu", "sat", "sun"],
    )
    preference = AthletePreference(
        id="preference-1",
        key="preferred_long_run_weekday",
        value="sat",
        source_ref="test:settings",
        confirmed_at=ANCHOR - timedelta(days=1),
        valid_from=ANCHOR - timedelta(days=1),
        created_at=ANCHOR - timedelta(days=1),
        updated_at=ANCHOR - timedelta(days=1),
    )
    baseline = build_weekly_plan_draft(
        request, goal=goal, activities=[], existing_plan=None
    )
    personalized = build_weekly_plan_draft(
        request,
        goal=goal,
        activities=[],
        existing_plan=None,
        athlete_preferences=[preference],
    )

    assert baseline.input_hash != personalized.input_hash
    assert personalized.weekly_plan_draft is not None
    long_run = next(
        item
        for item in personalized.weekly_plan_draft.sessions
        if item.session_type == "long_run"
    )
    assert long_run.scheduled_for == date(2026, 8, 29)
    evidence = next(
        item for item in personalized.evidence if item.type == "athlete_preference"
    )
    assert evidence.id == "preference:preference-1"
    assert evidence.values["applied"] is True
    assert evidence.values["source_ref"] == "test:settings"


def test_goal_availability_overrides_conflicting_long_run_preference() -> None:
    request = WeeklyPlanDraftRequest(
        goal_id="goal-1",
        week_start=WEEK_START,
        as_of=ANCHOR,
    )
    goal = TrainingGoal(
        id="goal-1",
        name="秋季十公里",
        event_type="10k",
        target_date=date(2026, 10, 18),
        available_weekdays=["tue", "thu", "sat"],
    )
    preference = AthletePreference(
        key="preferred_long_run_weekday",
        value="sun",
        source_ref="test:settings",
        confirmed_at=ANCHOR - timedelta(days=1),
        valid_from=ANCHOR - timedelta(days=1),
        created_at=ANCHOR - timedelta(days=1),
        updated_at=ANCHOR - timedelta(days=1),
    )
    result = build_weekly_plan_draft(
        request,
        goal=goal,
        activities=[],
        existing_plan=None,
        athlete_preferences=[preference],
    )
    evidence = next(item for item in result.evidence if item.type == "athlete_preference")
    assert evidence.values["applied"] is False
    assert result.weekly_plan_draft is not None
    assert all(
        item.scheduled_for != date(2026, 8, 30)
        for item in result.weekly_plan_draft.sessions
    )


def test_preference_api_requires_confirmation_and_supports_archive(
    tmp_path: Path,
) -> None:
    path = tmp_path / "api-memory.db"
    application = DemoApplication(
        DemoDashboardService(database_path=path, evaluation_directory=tmp_path / "evals"),
        training_service=TrainingOperationsService(
            database_path=path,
            clock=lambda: ANCHOR,
        ),
    )
    rejected = application.handle(
        "POST",
        "/api/training/preferences",
        json.dumps(
            {
                "key": "preferred_long_run_weekday",
                "value": "sun",
                "confirmed": False,
            }
        ).encode(),
    )
    created = application.handle(
        "POST",
        "/api/training/preferences",
        submission("sun").model_dump_json().encode(),
    )
    preference_id = json.loads(created.body)["id"]
    bootstrap = application.handle("GET", "/api/training/bootstrap")
    archived = application.handle(
        "POST",
        f"/api/training/preferences/{preference_id}/archive",
        json.dumps({"confirmed": True}).encode(),
    )

    assert rejected.status == 400
    assert created.status == 201
    assert json.loads(bootstrap.body)["athlete_preferences"][0]["id"] == preference_id
    assert archived.status == 200
    assert json.loads(archived.body)["status"] == "archived"


def test_web_plan_uses_preference_and_replay_rejects_changed_memory(
    tmp_path: Path,
) -> None:
    path = tmp_path / "preference-replay.db"
    application = DemoApplication(
        DemoDashboardService(database_path=path, evaluation_directory=tmp_path / "evals"),
        training_service=TrainingOperationsService(
            database_path=path,
            clock=lambda: ANCHOR,
        ),
    )
    created_goal = application.handle(
        "POST",
        "/api/training/goals",
        json.dumps(
            {
                "name": "秋季十公里",
                "event_type": "10k",
                "target_date": "2026-10-18",
                "target_time_seconds": None,
                "available_weekdays": ["tue", "thu", "sat", "sun"],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
    )
    goal_id = json.loads(created_goal.body)["id"]
    application.handle(
        "POST",
        "/api/training/preferences",
        submission("sat").model_dump_json().encode(),
    )
    draft_input = {
        "week_start": "2026-08-24",
        "as_of": "2026-08-20T00:00:00Z",
        "lookback_days": 28,
        "provider": None,
    }
    drafted = application.handle(
        "POST",
        f"/api/training/goals/{goal_id}/plan-drafts",
        json.dumps(draft_input).encode(),
    )
    draft_payload = json.loads(drafted.body)
    long_run = next(
        item
        for item in draft_payload["weekly_plan_draft"]["sessions"]
        if item["session_type"] == "long_run"
    )
    assert long_run["scheduled_for"] == "2026-08-29"

    application.handle(
        "POST",
        "/api/training/preferences",
        submission("sun").model_dump_json().encode(),
    )
    stale = application.handle(
        "POST",
        f"/api/training/goals/{goal_id}/plans/activate",
        json.dumps(
            {**draft_input, "expected_input_hash": draft_payload["input_hash"]}
        ).encode(),
    )
    assert stale.status == 400
    assert "数据已经变化" in json.loads(stale.body)["error"]


def test_memory_cli_requires_confirmation_and_can_archive(tmp_path: Path) -> None:
    database_path = tmp_path / "memory-cli.db"
    runner = CliRunner()
    rejected = runner.invoke(
        app,
        [
            "memory",
            "remember-long-run-day",
            "--weekday",
            "sun",
            "--db",
            str(database_path),
        ],
    )
    saved = runner.invoke(
        app,
        [
            "memory",
            "remember-long-run-day",
            "--weekday",
            "sun",
            "--confirm",
            "--db",
            str(database_path),
        ],
    )
    preference_id = json.loads(saved.output)["id"]
    listed = runner.invoke(
        app, ["memory", "list", "--db", str(database_path)]
    )
    archived = runner.invoke(
        app,
        [
            "memory",
            "archive",
            "--preference-id",
            preference_id,
            "--confirm",
            "--db",
            str(database_path),
        ],
    )

    assert rejected.exit_code != 0
    assert "--confirm" in rejected.output
    assert saved.exit_code == 0, saved.output
    assert json.loads(listed.output)[0]["value"] == "sun"
    assert json.loads(archived.output)["status"] == "archived"
