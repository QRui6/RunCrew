from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from runcrew.domain.activity import (
    ActivitySummary,
    SourceProvider,
    SourceRef,
    SportType,
)


def source_ref() -> SourceRef:
    return SourceRef(
        provider=SourceProvider.FIXTURE,
        external_id="activity-1",
        fetched_at=datetime.now(timezone.utc),
        raw_payload_hash="a" * 64,
    )


def test_activity_derives_average_pace() -> None:
    activity = ActivitySummary(
        source_ref=source_ref(),
        sport_type=SportType.RUN,
        started_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        duration_seconds=1800,
        distance_meters=5000,
    )
    assert activity.average_pace_seconds_per_km == 360


def test_activity_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        ActivitySummary(
            source_ref=source_ref(),
            sport_type=SportType.RUN,
            started_at=datetime(2026, 8, 1),
            duration_seconds=1800,
            distance_meters=5000,
        )

