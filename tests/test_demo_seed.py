from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from runcrew.cli import app
from runcrew.domain.demo import DemoSeedSummary
from runcrew.domain.training_operations import (
    CoachRunSubmission,
    WeeklyPlanDraftSubmission,
)
from runcrew.services.demo_seed import DemoSeedError, prepare_demo_database
from runcrew.services.training_operations import TrainingOperationsService
from runcrew.web import DemoApplication, DemoDashboardService


ANCHOR = datetime(2026, 8, 19, 8, tzinfo=timezone(timedelta(hours=8)))


def test_demo_seed_creates_complete_synthetic_product_state(tmp_path: Path) -> None:
    database_path = tmp_path / "runcrew-demo.db"
    summary = prepare_demo_database(database_path, as_of=ANCHOR)
    service = TrainingOperationsService(database_path=database_path)
    bootstrap = service.bootstrap()

    assert summary.synthetic_data is True
    assert summary.activity_count == 8
    assert len(bootstrap.goals) == 1
    assert bootstrap.goals[0].active_plan is not None
    assert bootstrap.goals[0].active_plan.revision == 2
    assert bootstrap.goals[0].latest_check_in is not None
    assert bootstrap.athlete_preferences[0].value == "sun"
    week_view = service.week_view(
        goal_id=summary.goal_id,
        as_of=ANCHOR,
        provider="fixture",
    )
    assert len(week_view.recent_memories) == 1
    assert week_view.recent_memories[0].confirmed_completed_sessions == 2
    assert "coros" not in json.dumps(
        bootstrap.model_dump(mode="json"), ensure_ascii=False
    ).lower()

    sunday_anchor = ANCHOR + timedelta(days=4)
    sunday_path = tmp_path / "runcrew-demo-sunday.db"
    prepare_demo_database(sunday_path, as_of=sunday_anchor)
    sunday_plan = TrainingOperationsService(
        database_path=sunday_path
    ).bootstrap().goals[0].active_plan
    assert sunday_plan is not None
    assert any(session.status == "completed" for session in sunday_plan.sessions)
    assert any(
        session.status == "planned"
        and session.scheduled_for >= sunday_anchor.date()
        for session in sunday_plan.sessions
    )


def test_demo_seed_refuses_implicit_overwrite_and_reset_is_repeatable(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "runcrew-demo.db"
    first = prepare_demo_database(database_path, as_of=ANCHOR)
    with pytest.raises(DemoSeedError, match="--reset"):
        prepare_demo_database(database_path, as_of=ANCHOR)
    second = prepare_demo_database(database_path, reset=True, as_of=ANCHOR)

    assert first.goal_id == second.goal_id
    assert first.plan_id == second.plan_id
    assert first.latest_activity_id == second.latest_activity_id


def test_demo_product_supports_chat_planning_memory_and_coach(tmp_path: Path) -> None:
    database_path = tmp_path / "runcrew-demo.db"
    summary = prepare_demo_database(database_path, as_of=ANCHOR)
    application = DemoApplication(
        DemoDashboardService(
            database_path=database_path,
            evaluation_directory=tmp_path / "evals",
        )
    )
    chat_bootstrap = json.loads(application.handle("GET", "/api/chat/bootstrap").body)
    assert len(chat_bootstrap["activities"]) == 8
    assert chat_bootstrap["activities"][0]["id"] == summary.latest_activity_id
    assert chat_bootstrap["activities"][0]["detail_available"] is True

    service = TrainingOperationsService(database_path=database_path)
    next_week = ANCHOR.date() - timedelta(days=ANCHOR.date().weekday()) + timedelta(days=7)
    draft = service.draft_week_plan(
        goal_id=summary.goal_id,
        submission=WeeklyPlanDraftSubmission(
            week_start=next_week,
            as_of=ANCHOR,
            provider="fixture",
        ),
    )
    assert draft.status == "ready"
    assert draft.weekly_plan_draft is not None
    long_run = next(
        item
        for item in draft.weekly_plan_draft.sessions
        if item.session_type == "long_run"
    )
    assert long_run.scheduled_for.weekday() == 6
    preference_evidence = next(
        item for item in draft.evidence if item.type == "athlete_preference"
    )
    assert preference_evidence.values["applied"] is True

    coach = asyncio.run(
        service.run_coach(
            CoachRunSubmission(
                goal_id=summary.goal_id,
                plan_id=summary.plan_id,
                as_of=ANCHOR,
                provider="fixture",
            )
        )
    )
    assert coach.audit.status == "awaiting_user_confirmation"
    assert coach.audit.result.execution is not None
    assert coach.audit.result.recovery is not None
    assert coach.audit.result.planning is not None


def test_demo_seed_cli_limits_output_and_requires_reset(tmp_path: Path) -> None:
    runner = CliRunner()
    outside = runner.invoke(
        app,
        ["demo-seed", "--db", str(tmp_path / "outside.db")],
    )
    assert outside.exit_code != 0
    assert "data/private/demo" in outside.output

    relative_path = Path("data/private/demo/test-demo-seed-cli.db")
    resolved = relative_path.resolve()
    if resolved.exists():
        resolved.unlink()
    try:
        created = runner.invoke(
            app,
            [
                "demo-seed",
                "--db",
                str(relative_path),
                "--as-of",
                ANCHOR.isoformat(),
            ],
        )
        repeated = runner.invoke(
            app,
            [
                "demo-seed",
                "--db",
                str(relative_path),
                "--as-of",
                ANCHOR.isoformat(),
            ],
        )
        reset = runner.invoke(
            app,
            [
                "demo-seed",
                "--db",
                str(relative_path),
                "--as-of",
                ANCHOR.isoformat(),
                "--reset",
            ],
        )
        assert created.exit_code == 0, created.output
        assert json.loads(created.output)["synthetic_data"] is True
        assert repeated.exit_code != 0 and "--reset" in repeated.output
        assert reset.exit_code == 0, reset.output
    finally:
        if resolved.exists():
            resolved.unlink()


def test_exported_demo_seed_schema_matches_domain_model() -> None:
    schema = json.loads(
        Path("schemas/demo/seed-output.schema.json").read_text("utf-8")
    )
    assert schema == DemoSeedSummary.model_json_schema()
