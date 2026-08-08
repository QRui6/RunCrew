import json

import pytest

from runcrew.domain.activity import ActivityDetail, SportType
from runcrew.providers.coros.parser import (
    CorosPayloadError,
    extract_records,
    parse_activity_detail,
    parse_activity_summary,
    unwrap_tool_result,
)


def tool_response(payload: object) -> dict:
    nested = json.dumps(json.dumps(payload, ensure_ascii=False), ensure_ascii=False)
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"content": [{"type": "text", "text": nested}]},
    }


def test_tool_error_preserves_reason_but_redacts_url_and_long_id() -> None:
    response = {
        "result": {
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Daily limit reached for 123456789012 at "
                        "https://example.test/private?token=secret"
                    ),
                }
            ],
        }
    }

    with pytest.raises(CorosPayloadError) as captured:
        unwrap_tool_result(response)

    message = str(captured.value)
    assert "Daily limit reached" in message
    assert "123456789012" not in message
    assert "token=secret" not in message


def test_nested_text_payload_is_normalized() -> None:
    payload = {
        "data": [
            {
                "labelId": "coros-1",
                "sportType": 100,
                "startTimestamp": 1786065000,
                "workoutTime": "00:45:18",
                "distance": "8.02 km",
                "avgPace": "5:39/km",
                "avgHr": 151,
            }
        ]
    }
    records = extract_records(unwrap_tool_result(tool_response(payload)))
    activity = parse_activity_summary(records[0])

    assert activity.source_ref.external_id == "coros-1"
    assert activity.sport_type == SportType.RUN
    assert activity.duration_seconds == 2718
    assert activity.distance_meters == 8020
    assert activity.average_pace_seconds_per_km == 339


def test_detail_can_reuse_summary_when_detail_omits_identity_fields() -> None:
    summary = parse_activity_summary(
        {
            "labelId": "coros-1",
            "sportType": 100,
            "startTimestamp": 1786065000,
            "workoutTime": 2718,
            "distance": 8.02,
        }
    )
    detail = parse_activity_detail(
        {
            "averageCadence": 176,
            "maxHeartRate": 166,
            "laps": [
                {
                    "lap": 1,
                    "lapTime": 337,
                    "distance": "1 km",
                    "avgPace": "5:37/km",
                    "avgHr": 145,
                }
            ],
        },
        fallback_summary=summary,
    )

    assert isinstance(detail, ActivityDetail)
    assert detail.average_cadence == 176
    assert detail.laps[0].distance_meters == 1000


def test_formatted_coros_sport_record_is_parsed_without_llm() -> None:
    payload = """Sport Records — 2026-07-10 to 2026-08-08 (1 records)
========================

1. Outdoor Run — 2026-08-07
Location: Example City
Start Coordinates: 30.000000, 120.000000
   Time Window: startTimestamp=1786055400 | endTimestamp=1786058118
   Duration: 45:18 | Distance: 8.02 km
   Average Pace: 5:39 /km | Avg HR: 151 bpm | Calories: 520 kcal
LabelId: private-label-id
"""
    records = extract_records(payload)
    activity = parse_activity_summary(records[0])

    assert activity.source_ref.external_id == "private-label-id"
    assert activity.sport_type == SportType.RUN
    assert activity.duration_seconds == 2718
    assert activity.distance_meters == 8020
    assert activity.average_heart_rate == 151
