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
from runcrew.evaluation import evaluate_review_agent_suite, load_review_agent_suite
from runcrew.storage.database import Database
from runcrew.storage.repositories import ActivityRepository
from runcrew.web import DemoApplication, DemoDashboardService


ANCHOR = datetime(2026, 8, 8, 8, tzinfo=timezone.utc)


def activity(
    identifier: str,
    *,
    days_before: int,
    detail: bool = False,
) -> ActivitySummary | ActivityDetail:
    common = {
        "id": identifier,
        "source_ref": SourceRef(
            provider=SourceProvider.FIXTURE,
            external_id=f"private-external-{identifier}",
            fetched_at=ANCHOR,
            raw_payload_hash=f"hash-{identifier}",
        ),
        "sport_type": SportType.RUN,
        "started_at": ANCHOR - timedelta(days=days_before),
        "duration_seconds": 3600,
        "distance_meters": 10_000,
        "average_pace_seconds_per_km": 360,
        "average_heart_rate": 150,
        "training_load": 50,
        "title": "测试跑步",
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


def create_demo_data(tmp_path: Path) -> tuple[Path, Path]:
    database_path = tmp_path / "demo.db"
    database = Database(f"sqlite:///{database_path.as_posix()}")
    database.create_schema()
    with database.session() as session:
        repository = ActivityRepository(session)
        repository.upsert(activity("target", days_before=0, detail=True))
        repository.upsert(activity("history", days_before=8))
        session.commit()

    evaluation_directory = tmp_path / "evals"
    evaluation_directory.mkdir()
    suite = load_review_agent_suite(Path("evals/review_agent/cases.json"))
    baseline = asyncio.run(evaluate_review_agent_suite(suite))
    deepseek = baseline.model_copy(
        update={
            "policy_name": "deepseek-v4-flash-test",
            "metrics": baseline.metrics.model_copy(
                update={
                    "policy_call_count": 12,
                    "policy_api_attempt_count": 12,
                    "total_tokens": 1000,
                    "estimated_cost_usd": 0.0001,
                    "estimated_cost_basis": "test-pricing",
                    "policy_latency_ms": 2000,
                    "p95_latency_ms": 500,
                }
            ),
        }
    )
    (evaluation_directory / "m5-baseline-suite-v1.1.json").write_text(
        baseline.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (evaluation_directory / "deepseek-suite-v1.1-final.json").write_text(
        deepseek.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return database_path, evaluation_directory


def test_dashboard_snapshot_replays_agent_without_exposing_provider_ids(
    tmp_path: Path,
) -> None:
    database_path, evaluation_directory = create_demo_data(tmp_path)
    service = DemoDashboardService(
        database_path=database_path,
        evaluation_directory=evaluation_directory,
    )

    snapshot = service.build_snapshot(
        provider="fixture",
        planned_distance_km=10,
        planned_duration_minutes=60,
    )

    assert snapshot.activity is not None
    assert snapshot.activity.distance_km == 10
    assert snapshot.activity.lap_count == 4
    assert snapshot.agent_run is not None
    assert snapshot.agent_run.status == "succeeded"
    assert snapshot.agent_run.steps_used == 2
    assert snapshot.agent_run.tool_calls_used == 1
    assert len(snapshot.findings) == 3
    assert all(finding.evidence for finding in snapshot.findings)
    assert snapshot.evaluation.same_suite is True
    assert snapshot.evaluation.baseline.passed_cases == 12
    assert snapshot.evaluation.deepseek.total_tokens == 1000
    serialized = snapshot.model_dump_json()
    assert "private-external-target" not in serialized
    assert "raw_payload_hash" not in serialized


def test_demo_application_serves_static_ui_and_read_only_json(tmp_path: Path) -> None:
    database_path, evaluation_directory = create_demo_data(tmp_path)
    application = DemoApplication(
        DemoDashboardService(
            database_path=database_path,
            evaluation_directory=evaluation_directory,
        )
    )

    page = application.handle("GET", "/")
    assert page.status == 200
    assert page.content_type.startswith("text/html")
    assert "RunCrew" in page.body.decode("utf-8")

    api = application.handle(
        "GET",
        "/api/dashboard?provider=fixture&planned_distance_km=10",
    )
    assert api.status == 200
    payload = json.loads(api.body)
    assert payload["agent_run"]["termination_reason"] == "completed"
    assert payload["evaluation"]["same_suite"] is True

    invalid = application.handle("GET", "/api/dashboard?provider=unknown")
    assert invalid.status == 400
    assert "provider" in json.loads(invalid.body)["error"]

    blocked = application.handle("POST", "/api/dashboard")
    assert blocked.status == 405
    assert blocked.headers["Cache-Control"] == "no-store"


def test_demo_cli_is_discoverable_without_starting_server() -> None:
    completed = CliRunner().invoke(app, ["demo", "--help"])

    assert completed.exit_code == 0, completed.output
    assert "127.0.0.1" in completed.output
    assert "--no-open-browser" in completed.output


def test_dashboard_does_not_create_a_missing_database(tmp_path: Path) -> None:
    database_path = tmp_path / "must-not-be-created.db"
    service = DemoDashboardService(
        database_path=database_path,
        evaluation_directory=tmp_path / "missing-evals",
    )

    snapshot = service.build_snapshot()

    assert snapshot.activity is None
    assert snapshot.message is not None
    assert database_path.exists() is False
