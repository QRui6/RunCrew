import asyncio
from datetime import date
from pathlib import Path

from runcrew.domain.activity import ActivityDetail
from runcrew.providers.fixture import FixtureActivityProvider
from runcrew.services.activity_review import build_activity_review


def test_review_is_deterministic_and_evidence_backed() -> None:
    provider = FixtureActivityProvider(Path("tests/fixtures/coros_activities.json"))
    activities = asyncio.run(
        provider.list_activities(date(2026, 8, 1), date(2026, 8, 8))
    )
    detail = asyncio.run(
        provider.get_activity(activities[0].activity.source_ref.external_id)
    )
    assert isinstance(detail.activity, ActivityDetail)

    first = build_activity_review(detail.activity)
    second = build_activity_review(detail.activity)

    assert first == second
    assert first.observations[0].type == "pace_stability"
    assert first.observations[0].evidence["pace_cv"] < 0.05
    assert first.data_quality.confidence == "high"
