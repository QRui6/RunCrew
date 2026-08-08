from __future__ import annotations

from datetime import datetime, timezone

import pytest

from runcrew.domain.activity import (
    ActivitySummary,
    SourceProvider,
    SourceRef,
    SportType,
)
from runcrew.providers.fit import FitParseError, parse_fit_activity


def _fallback_summary() -> ActivitySummary:
    return ActivitySummary(
        source_ref=SourceRef(
            provider=SourceProvider.COROS,
            external_id="synthetic-coros-id",
            fetched_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            raw_payload_hash="summary-hash",
        ),
        sport_type=SportType.RUN,
        started_at=datetime(2026, 8, 1, 6, 0, tzinfo=timezone.utc),
        duration_seconds=1400,
        distance_meters=4000,
        average_heart_rate=140,
        title="Synthetic run",
    )


def test_parse_synthetic_fit_maps_session_laps_and_records(
    synthetic_fit_bytes: bytes,
) -> None:
    result = parse_fit_activity(
        synthetic_fit_bytes,
        fallback_summary=_fallback_summary(),
    )

    activity = result.activity
    assert activity.source_ref.provider is SourceProvider.COROS
    assert activity.source_ref.external_id == "synthetic-coros-id"
    assert activity.duration_seconds == 1331
    assert activity.distance_meters == pytest.approx(4000)
    assert activity.average_heart_rate == 152
    assert activity.average_cadence == pytest.approx(176)
    assert activity.max_heart_rate == 165
    assert activity.elevation_gain_meters == pytest.approx(18)
    assert len(activity.laps) == 4
    assert activity.laps[1].duration_seconds == pytest.approx(335)
    assert len(activity.time_series) == 12
    assert activity.provider_metadata["detail_source"] == "fit"
    assert activity.provider_metadata["fit_sha256"] == result.sha256
    assert result.message_counts["record_mesgs"] == 12


def test_parse_fit_rejects_non_fit_content() -> None:
    with pytest.raises(FitParseError, match="not a FIT"):
        parse_fit_activity(b"not-fit", fallback_summary=_fallback_summary())


def test_parse_fit_rejects_corrupt_crc(synthetic_fit_bytes: bytes) -> None:
    corrupt = bytearray(synthetic_fit_bytes)
    corrupt[-1] ^= 0xFF
    with pytest.raises(FitParseError, match="integrity"):
        parse_fit_activity(bytes(corrupt), fallback_summary=_fallback_summary())
