from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from runcrew.domain.activity import (
    ActivityDetail,
    ActivitySummary,
    Lap,
    SourceProvider,
    SourceRef,
    SportType,
)


class CorosPayloadError(ValueError):
    pass


SPORT_CODE_MAP = {
    100: SportType.RUN,
    101: SportType.INDOOR_RUN,
    102: SportType.TRAIL_RUN,
    103: SportType.TRACK_RUN,
}


def unwrap_tool_result(response: Mapping[str, Any]) -> Any:
    result = response.get("result", {})
    if result.get("isError"):
        raise CorosPayloadError("COROS tool returned isError=true")
    texts = [
        item.get("text", "")
        for item in result.get("content", [])
        if item.get("type") == "text"
    ]
    if not texts:
        structured = result.get("structuredContent")
        if structured is not None:
            return structured
        raise CorosPayloadError("COROS tool response did not contain text or structured data")
    return decode_nested_json("\n".join(texts))


def decode_nested_json(value: Any) -> Any:
    current = value
    for _ in range(4):
        if not isinstance(current, str):
            return current
        candidate = current.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate)
        try:
            current = json.loads(candidate)
        except json.JSONDecodeError:
            return current
    return current


def extract_records(payload: Any) -> list[Mapping[str, Any]]:
    payload = decode_nested_json(payload)
    if isinstance(payload, str):
        return parse_formatted_sport_records(payload)
    if isinstance(payload, list):
        if all(isinstance(item, Mapping) for item in payload):
            return list(payload)
    if isinstance(payload, Mapping):
        for key in ("activities", "records", "list", "items", "data", "result"):
            if key in payload:
                try:
                    return extract_records(payload[key])
                except CorosPayloadError:
                    continue
        if _first(payload, "labelId", "label_id", "activityId", "id") is not None:
            return [payload]
        raise CorosPayloadError(
            f"Could not find activity records; top-level keys={sorted(payload.keys())}"
        )
    raise CorosPayloadError(
        f"Expected structured activity data, received {type(payload).__name__}"
    )


def parse_formatted_sport_records(text: str) -> list[Mapping[str, Any]]:
    records: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = re.match(
            r"^\d+\.\s+(.+?)\s+[—-]\s+(\d{4}-\d{2}-\d{2})$",
            line,
        )
        if heading:
            if current:
                records.append(current)
            sport_name, activity_date = heading.groups()
            current = {
                "sportType": _sport_name_to_code(sport_name),
                "date": activity_date,
            }
            continue
        if current is None:
            continue

        if line.startswith("Location:"):
            current["location"] = line.split(":", 1)[1].strip()
        elif line.startswith("Time Window:"):
            timestamps = dict(
                re.findall(r"(startTimestamp|endTimestamp)=(\d+)", line)
            )
            current.update({key: int(value) for key, value in timestamps.items()})
        elif line.startswith("Duration:"):
            match = re.search(
                r"Duration:\s*([^|]+?)\s*\|\s*Distance:\s*([0-9.]+)\s*(km|m)",
                line,
                re.IGNORECASE,
            )
            if match:
                duration, distance, unit = match.groups()
                current["duration"] = duration.strip()
                current["distance"] = f"{distance} {unit}"
        elif line.startswith("Average Pace:"):
            pace = re.search(r"Average Pace:\s*([^|]+?)(?:\s*\||$)", line)
            heart_rate = re.search(r"Avg HR:\s*(\d+)", line)
            if pace:
                current["averagePace"] = pace.group(1).strip()
            if heart_rate:
                current["averageHeartRate"] = int(heart_rate.group(1))
        elif line.startswith("LabelId:"):
            current["labelId"] = line.split(":", 1)[1].strip()

    if current:
        records.append(current)
    valid_records = [
        record
        for record in records
        if record.get("labelId") and record.get("duration")
    ]
    if not valid_records:
        raise CorosPayloadError("Could not parse COROS formatted sport records")
    return valid_records


def extract_detail_object(payload: Any) -> Mapping[str, Any]:
    payload = decode_nested_json(payload)
    if isinstance(payload, list):
        if payload and isinstance(payload[0], Mapping):
            return payload[0]
        raise CorosPayloadError("COROS activity detail list was empty")
    if isinstance(payload, Mapping):
        for key in ("activity", "detail", "data", "result"):
            if key in payload:
                try:
                    return extract_detail_object(payload[key])
                except CorosPayloadError:
                    continue
        return payload
    raise CorosPayloadError(
        f"Expected COROS activity detail object, received {type(payload).__name__}"
    )


def parse_activity_summary(raw: Mapping[str, Any]) -> ActivitySummary:
    external_id = _first(raw, "labelId", "label_id", "activityId", "activity_id", "id")
    if external_id is None:
        raise _missing("activity id", raw)
    started_value = _first(
        raw,
        "startTimestamp",
        "start_timestamp",
        "startTime",
        "start_time",
        "startedAt",
        "started_at",
        "date",
        "sportDate",
    )
    if started_value is None:
        raise _missing("start time", raw)
    duration_value = _first(
        raw,
        "durationSeconds",
        "duration_seconds",
        "duration",
        "workoutTime",
        "workout_time",
        "totalTime",
    )
    if duration_value is None:
        raise _missing("duration", raw)

    serialized = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)
    source_ref = SourceRef(
        provider=SourceProvider.COROS,
        external_id=str(external_id),
        fetched_at=datetime.now(timezone.utc),
        raw_payload_hash=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
    )
    sport_value = _first(raw, "sportType", "sport_type", "sportTypeCode", "type")
    return ActivitySummary(
        source_ref=source_ref,
        sport_type=_parse_sport_type(sport_value),
        started_at=_parse_datetime(started_value),
        duration_seconds=round(_parse_duration_seconds(duration_value)),
        distance_meters=_parse_distance(raw),
        average_pace_seconds_per_km=_parse_pace(
            _first(raw, "averagePace", "average_pace", "avgPace", "pace")
        ),
        average_heart_rate=_optional_int(
            _first(raw, "averageHeartRate", "average_heart_rate", "avgHeartRate", "avgHr")
        ),
        training_load=_optional_float(
            _first(raw, "trainingLoad", "training_load", "load")
        ),
        title=_optional_str(_first(raw, "title", "name", "activityName")),
        location=_optional_str(_first(raw, "location", "city", "place")),
    )


def parse_activity_detail(
    raw: Mapping[str, Any], *, fallback_summary: ActivitySummary | None = None
) -> ActivityDetail:
    try:
        summary = parse_activity_summary(raw)
    except CorosPayloadError:
        if fallback_summary is None:
            raise
        summary = fallback_summary.model_copy(deep=True)
        serialized = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)
        summary.source_ref.raw_payload_hash = hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()
        summary.source_ref.fetched_at = datetime.now(timezone.utc)

    lap_values = _first(raw, "laps", "lapList", "lap_list", "segments") or []
    laps = []
    if isinstance(lap_values, Iterable) and not isinstance(lap_values, (str, bytes, Mapping)):
        for index, lap in enumerate(lap_values, start=1):
            if not isinstance(lap, Mapping):
                continue
            duration = _first(lap, "durationSeconds", "duration", "lapTime", "time")
            if duration is None:
                continue
            laps.append(
                Lap(
                    index=_optional_int(_first(lap, "index", "lap", "lapIndex")) or index,
                    duration_seconds=_parse_duration_seconds(duration),
                    distance_meters=_parse_distance(lap),
                    average_pace_seconds_per_km=_parse_pace(
                        _first(lap, "averagePace", "avgPace", "pace")
                    ),
                    average_heart_rate=_optional_int(
                        _first(lap, "averageHeartRate", "avgHeartRate", "avgHr")
                    ),
                    average_cadence=_optional_float(
                        _first(lap, "averageCadence", "avgCadence", "cadence")
                    ),
                )
            )

    return ActivityDetail(
        **summary.model_dump(),
        elevation_gain_meters=_optional_float(
            _first(raw, "elevationGain", "elevation_gain", "totalAscent")
        ),
        average_cadence=_optional_float(
            _first(raw, "averageCadence", "average_cadence", "avgCadence")
        ),
        max_heart_rate=_optional_int(
            _first(raw, "maxHeartRate", "max_heart_rate", "maxHr")
        ),
        laps=laps,
        provider_metadata={
            "sport_type_code": _first(raw, "sportType", "sport_type", "sportTypeCode")
        },
    )


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _missing(field: str, raw: Mapping[str, Any]) -> CorosPayloadError:
    return CorosPayloadError(f"Missing {field}; available keys={sorted(raw.keys())}")


def _parse_sport_type(value: Any) -> SportType:
    try:
        code = int(value)
        return SPORT_CODE_MAP.get(code, SportType.OTHER)
    except (TypeError, ValueError):
        normalized = str(value or "").lower().replace(" ", "_")
        aliases = {
            "run": SportType.RUN,
            "outdoor_run": SportType.RUN,
            "indoor_run": SportType.INDOOR_RUN,
            "trail_run": SportType.TRAIL_RUN,
            "track_run": SportType.TRACK_RUN,
        }
        return aliases.get(normalized, SportType.OTHER)


def _sport_name_to_code(value: str) -> int:
    normalized = value.strip().lower()
    return {
        "outdoor run": 100,
        "indoor run": 101,
        "trail run": 102,
        "track run": 103,
    }.get(normalized, 65535)


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    text = str(value).strip()
    if text.isdigit():
        if len(text) == 8:
            return datetime.strptime(text, "%Y%m%d").replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return _parse_datetime(int(text))
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for date_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, date_format)
                break
            except ValueError:
                continue
        else:
            raise CorosPayloadError("Unsupported COROS datetime format")
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))


def _parse_duration_seconds(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.replace(".", "", 1).isdigit():
        return float(text)
    parts = text.split(":")
    if len(parts) in (2, 3) and all(part.isdigit() for part in parts):
        numbers = [int(part) for part in parts]
        if len(numbers) == 2:
            return numbers[0] * 60 + numbers[1]
        return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
    raise CorosPayloadError("Unsupported COROS duration format")


def _parse_distance(raw: Mapping[str, Any]) -> float | None:
    meters = _first(raw, "distanceMeters", "distance_meters", "totalDistanceMeters")
    if meters is not None:
        return _optional_float(meters)
    kilometers = _first(raw, "distanceKm", "distance_km")
    if kilometers is not None:
        value = _optional_float(kilometers)
        return value * 1000 if value is not None else None
    value = _first(raw, "distance", "totalDistance")
    if value is None:
        return None
    if isinstance(value, str):
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(km|m)?", value.lower())
        if not match:
            return None
        number = float(match.group(1))
        unit = match.group(2)
        if unit == "km":
            return number * 1000
        if unit == "m":
            return number
        return number * 1000 if number < 200 else number
    number = float(value)
    return number * 1000 if number < 200 else number


def _parse_pace(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).lower().replace("/km", "").strip()
    match = re.search(r"(\d+)[\s:'′m]+(\d{1,2})", text)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))
    try:
        return float(text)
    except ValueError:
        return None


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    if isinstance(value, str):
        match = re.search(r"-?[0-9]+(?:\.[0-9]+)?", value.replace(",", ""))
        return float(match.group()) if match else None
    return float(value)


def _optional_int(value: Any) -> int | None:
    parsed = _optional_float(value)
    return round(parsed) if parsed is not None else None


def _optional_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None
