from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from runcrew.domain.activity import (
    ActivityDetail,
    ActivitySummary,
    Lap,
    SourceProvider,
    SourceRef,
    SportType,
)
from runcrew.providers.base import ProviderActivity


SPORT_TYPE_MAP = {
    100: SportType.RUN,
    101: SportType.INDOOR_RUN,
    102: SportType.TRAIL_RUN,
    103: SportType.TRACK_RUN,
}


class FixtureActivityProvider:
    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path
        document = json.loads(fixture_path.read_text(encoding="utf-8"))
        self._activities: list[dict[str, Any]] = document["activities"]

    @property
    def name(self) -> str:
        return SourceProvider.FIXTURE.value

    async def list_activities(
        self, start_date: date, end_date: date
    ) -> list[ProviderActivity]:
        envelopes: list[ProviderActivity] = []
        for raw in self._activities:
            started_at = datetime.fromisoformat(raw["started_at"])
            if start_date <= started_at.date() <= end_date:
                envelopes.append(
                    ProviderActivity(
                        activity=self._to_summary(raw),
                        raw_payload=raw,
                    )
                )
        envelopes.sort(key=lambda item: item.activity.started_at, reverse=True)
        return envelopes

    async def get_activity(self, external_id: str) -> ProviderActivity:
        raw = next(
            (item for item in self._activities if item["id"] == external_id),
            None,
        )
        if raw is None:
            raise LookupError(f"Fixture activity not found: {external_id}")
        return ProviderActivity(activity=self._to_detail(raw), raw_payload=raw)

    def _source_ref(self, raw: dict[str, Any]) -> SourceRef:
        serialized = json.dumps(
            raw,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return SourceRef(
            provider=SourceProvider.FIXTURE,
            external_id=raw["id"],
            fetched_at=datetime.now(timezone.utc),
            raw_payload_hash=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        )

    def _to_summary(self, raw: dict[str, Any]) -> ActivitySummary:
        return ActivitySummary(
            source_ref=self._source_ref(raw),
            sport_type=SPORT_TYPE_MAP.get(raw["sport_type_code"], SportType.OTHER),
            started_at=datetime.fromisoformat(raw["started_at"]),
            duration_seconds=raw["duration_seconds"],
            distance_meters=raw.get("distance_meters"),
            average_pace_seconds_per_km=raw.get("average_pace_seconds_per_km"),
            average_heart_rate=raw.get("average_heart_rate"),
            training_load=raw.get("training_load"),
            title=raw.get("title"),
            location=raw.get("location"),
        )

    def _to_detail(self, raw: dict[str, Any]) -> ActivityDetail:
        summary = self._to_summary(raw)
        return ActivityDetail(
            **summary.model_dump(),
            elevation_gain_meters=raw.get("elevation_gain_meters"),
            average_cadence=raw.get("average_cadence"),
            max_heart_rate=raw.get("max_heart_rate"),
            laps=[Lap.model_validate(item) for item in raw.get("laps", [])],
            provider_metadata={"fixture_version": 1},
        )

