from __future__ import annotations

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
from runcrew.domain.training_review import (
    PlannedSession,
    TrainingReviewRequest,
    TrainingReviewResult,
)
from runcrew.services.training_context import build_training_context
from runcrew.services.training_review import build_training_review
from runcrew.storage.database import Database
from runcrew.storage.repositories import ActivityRepository


ANCHOR = datetime(2026, 8, 8, 8, tzinfo=timezone.utc)


def make_activity(
    identifier: str,
    *,
    days_before: int,
    load: float | None,
    pace: float = 360,
    distance: float = 10_000,
    duration: int = 3600,
    detail: bool = False,
) -> ActivitySummary | ActivityDetail:
    common = {
        "id": identifier,
        "source_ref": SourceRef(
            provider=SourceProvider.FIXTURE,
            external_id=identifier,
            fetched_at=ANCHOR,
            raw_payload_hash=f"hash-{identifier}",
        ),
        "sport_type": SportType.RUN,
        "started_at": ANCHOR - timedelta(days=days_before),
        "duration_seconds": duration,
        "distance_meters": distance,
        "average_pace_seconds_per_km": pace,
        "average_heart_rate": 150,
        "training_load": load,
    }
    if not detail:
        return ActivitySummary(**common)
    return ActivityDetail(
        **common,
        laps=[
            Lap(
                index=index,
                duration_seconds=lap_pace,
                distance_meters=1000,
                average_pace_seconds_per_km=lap_pace,
            )
            for index, lap_pace in enumerate((359, 360, 361, 360), start=1)
        ],
    )


def review_fixture(*, with_plan: bool = True) -> TrainingReviewResult:
    target = make_activity("target", days_before=0, load=50, detail=True)
    activities = [
        make_activity("current", days_before=3, load=40),
        make_activity("previous-a", days_before=8, load=60),
        make_activity("previous-b", days_before=10, load=40),
    ]
    request = TrainingReviewRequest(
        target_activity_id=target.id,
        planned_session=PlannedSession(
            distance_meters=10_000,
            duration_seconds=3600,
        )
        if with_plan
        else None,
    )
    context = build_training_context(request, target=target, activities=activities)
    return build_training_review(context)


def test_training_review_is_replayable_and_every_finding_has_evidence() -> None:
    first = review_fixture()
    second = review_fixture()

    assert first == second
    assert len(first.input_hash) == 64
    assert [finding.type for finding in first.findings] == [
        "training_completion",
        "load_change",
        "training_anomaly",
    ]
    assert all(finding.evidence for finding in first.findings)
    assert first.findings[0].level == "good"
    assert first.findings[0].evidence["completion_ratio"] == 1
    assert first.findings[1].level == "normal"
    assert first.findings[1].evidence["change_ratio"] == -0.1
    assert first.findings[2].evidence["method"] == "lap_pace_cv"
    assert first.data_quality.confidence == "high"


def test_missing_plan_and_history_downgrade_without_inventing_findings() -> None:
    target = make_activity(
        "summary-target", days_before=0, load=None, detail=False
    )
    request = TrainingReviewRequest(target_activity_id=target.id)
    result = build_training_review(
        build_training_context(request, target=target, activities=[])
    )

    assert [finding.level for finding in result.findings] == [
        "unknown",
        "unknown",
        "unknown",
    ]
    assert result.findings[0].evidence["requires"].startswith("planned_session")
    assert result.data_quality.confidence == "low"
    assert result.data_quality.missing_fields == [
        "pace_baseline",
        "planned_session",
        "training_load_history",
    ]


def test_load_spike_and_historical_pace_deviation_are_explicit() -> None:
    target = make_activity(
        "anomaly-target", days_before=0, load=100, pace=400, detail=False
    )
    activities = [
        make_activity("current", days_before=2, load=80, pace=305),
        make_activity("previous", days_before=8, load=50, pace=300),
        make_activity("pace-a", days_before=15, load=None, pace=298),
        make_activity("pace-b", days_before=20, load=None, pace=302),
    ]
    request = TrainingReviewRequest(target_activity_id=target.id)
    result = build_training_review(
        build_training_context(request, target=target, activities=activities)
    )

    assert result.findings[1].level == "attention"
    assert result.findings[1].evidence["change_ratio"] == 2.6
    assert result.findings[2].level == "attention"
    assert result.findings[2].evidence["comparable_activity_count"] == 4


def test_exported_skill_schemas_match_domain_models() -> None:
    references = Path("skills/review-running-training/references")
    assert json.loads((references / "input.schema.json").read_text("utf-8")) == (
        TrainingReviewRequest.model_json_schema()
    )
    assert json.loads((references / "output.schema.json").read_text("utf-8")) == (
        TrainingReviewResult.model_json_schema()
    )


def test_training_review_cli_returns_validated_json(tmp_path: Path) -> None:
    database_path = tmp_path / "runcrew.db"
    database = Database(f"sqlite:///{database_path.as_posix()}")
    database.create_schema()
    with database.session() as session:
        repository = ActivityRepository(session)
        for activity in [
            make_activity("previous", days_before=8, load=50),
            make_activity("current", days_before=3, load=40),
            make_activity("target", days_before=0, load=50, detail=True),
        ]:
            repository.upsert(activity)
        session.commit()

    completed = CliRunner().invoke(
        app,
        [
            "training",
            "review",
            "--latest",
            "--provider",
            "fixture",
            "--planned-distance-km",
            "10",
            "--planned-duration-minutes",
            "60",
            "--db",
            str(database_path),
        ],
    )

    assert completed.exit_code == 0, completed.output
    payload = json.loads(completed.output)
    assert payload["schema_version"] == "1.0"
    assert len(payload["findings"]) == 3
