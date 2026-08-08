from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from garmin_fit_sdk import Decoder, Stream

from runcrew.domain.activity import (
    ActivityDetail,
    ActivitySummary,
    Lap,
    MetricPoint,
    SportType,
)


class FitParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FitParseResult:
    activity: ActivityDetail
    sha256: str
    message_counts: dict[str, int]


def parse_fit_activity(
    content: bytes,
    *,
    fallback_summary: ActivitySummary,
) -> FitParseResult:
    if not content:
        raise FitParseError("FIT content is empty")
    if not Decoder(Stream.from_byte_array(bytearray(content))).is_fit():
        raise FitParseError("Downloaded file is not a FIT file")
    if not Decoder(Stream.from_byte_array(bytearray(content))).check_integrity():
        raise FitParseError("FIT file integrity check failed")

    decoder = Decoder(Stream.from_byte_array(bytearray(content)))
    messages, errors = decoder.read()
    if errors:
        error_types = sorted({type(error).__name__ for error in errors})
        raise FitParseError(
            "FIT decoder reported errors: " + ", ".join(error_types)
        )

    message_counts = {
        key: len(value)
        for key, value in messages.items()
        if isinstance(value, list)
    }
    sessions = _messages(messages, "session_mesgs")
    laps = _messages(messages, "lap_mesgs")
    records = _messages(messages, "record_mesgs")
    if not sessions:
        raise FitParseError("FIT file does not contain a session message")
    session = sessions[-1]

    detail_laps = [
        parsed
        for index, lap in enumerate(laps, start=1)
        if (parsed := _parse_lap(lap, index)) is not None
    ]
    time_series = [
        parsed
        for record in records
        if (parsed := _parse_record(record)) is not None
    ]
    duration_seconds = round(
        _number(session, "total_timer_time", "total_elapsed_time")
        or fallback_summary.duration_seconds
    )
    distance_meters = (
        _number(session, "total_distance") or fallback_summary.distance_meters
    )
    average_pace = (
        duration_seconds / (distance_meters / 1000)
        if distance_meters and distance_meters > 0
        else fallback_summary.average_pace_seconds_per_km
    )

    source_ref = fallback_summary.source_ref.model_copy(deep=True)
    source_ref.fetched_at = datetime.now(timezone.utc)
    source_ref.raw_payload_hash = hashlib.sha256(content).hexdigest()
    detail = ActivityDetail(
        **fallback_summary.model_dump(
            exclude={
                "source_ref",
                "sport_type",
                "started_at",
                "duration_seconds",
                "distance_meters",
                "average_pace_seconds_per_km",
                "average_heart_rate",
            }
        ),
        source_ref=source_ref,
        sport_type=_sport_type(session, fallback_summary.sport_type),
        started_at=_datetime(session.get("start_time")) or fallback_summary.started_at,
        duration_seconds=duration_seconds,
        distance_meters=distance_meters,
        average_pace_seconds_per_km=average_pace,
        average_heart_rate=_integer(session, "avg_heart_rate")
        or fallback_summary.average_heart_rate,
        elevation_gain_meters=_number(session, "total_ascent"),
        average_cadence=_number(
            session, "avg_running_cadence", "avg_cadence"
        ),
        max_heart_rate=_integer(session, "max_heart_rate"),
        laps=detail_laps,
        time_series=time_series,
        provider_metadata={
            "detail_source": "fit",
            "fit_sha256": source_ref.raw_payload_hash,
            "fit_message_counts": message_counts,
            "fit_decoder": "garmin-fit-sdk",
        },
    )
    return FitParseResult(
        activity=detail,
        sha256=source_ref.raw_payload_hash,
        message_counts=message_counts,
    )


def _messages(messages: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = messages.get(key, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _parse_lap(raw: Mapping[str, Any], index: int) -> Lap | None:
    duration = _number(raw, "total_timer_time", "total_elapsed_time")
    if duration is None or duration <= 0:
        return None
    distance = _number(raw, "total_distance")
    pace = (
        duration / (distance / 1000)
        if distance is not None and distance > 0
        else _pace_from_speed(raw, "enhanced_avg_speed", "avg_speed")
    )
    return Lap(
        index=index,
        duration_seconds=duration,
        distance_meters=distance,
        average_pace_seconds_per_km=pace,
        average_heart_rate=_integer(raw, "avg_heart_rate"),
        average_cadence=_number(raw, "avg_running_cadence", "avg_cadence"),
    )


def _parse_record(raw: Mapping[str, Any]) -> MetricPoint | None:
    timestamp = _datetime(raw.get("timestamp"))
    if timestamp is None:
        return None
    return MetricPoint(
        timestamp=timestamp,
        heart_rate=_integer(raw, "heart_rate"),
        pace_seconds_per_km=_pace_from_speed(
            raw, "enhanced_speed", "speed"
        ),
        cadence=_number(raw, "cadence"),
        elevation_meters=_number(raw, "enhanced_altitude", "altitude"),
    )


def _sport_type(raw: Mapping[str, Any], fallback: SportType) -> SportType:
    sport = str(raw.get("sport", "")).lower()
    sub_sport = str(raw.get("sub_sport", "")).lower()
    if sport not in {"running", "run"}:
        return fallback
    if "trail" in sub_sport:
        return SportType.TRAIL_RUN
    if sub_sport in {"treadmill", "indoor_running"}:
        return SportType.INDOOR_RUN
    if "track" in sub_sport:
        return SportType.TRACK_RUN
    return SportType.RUN


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _number(raw: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _integer(raw: Mapping[str, Any], *keys: str) -> int | None:
    value = _number(raw, *keys)
    return round(value) if value is not None else None


def _pace_from_speed(raw: Mapping[str, Any], *keys: str) -> float | None:
    speed = _number(raw, *keys)
    if speed is None or speed <= 0:
        return None
    return 1000 / speed

