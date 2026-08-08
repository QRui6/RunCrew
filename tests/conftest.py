from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from garmin_fit_sdk import Encoder, Profile


@pytest.fixture
def synthetic_fit_bytes() -> bytes:
    """Build a deterministic, location-free running FIT file for tests."""
    start = datetime(2026, 8, 1, 6, 0, tzinfo=timezone.utc)
    lap_durations = [330.0, 335.0, 332.0, 334.0]
    lap_heart_rates = [145, 151, 154, 157]
    encoder = Encoder()
    encoder.on_mesg(
        Profile["mesg_num"]["FILE_ID"],
        {
            "type": "activity",
            "manufacturer": "development",
            "product": 1,
            "serial_number": 1,
            "time_created": start,
        },
    )

    elapsed = 0.0
    record_count = 0
    for index, (duration, heart_rate) in enumerate(
        zip(lap_durations, lap_heart_rates, strict=True)
    ):
        lap_start = start + timedelta(seconds=elapsed)
        for fraction in (0.0, 0.5, 1.0):
            record_count += 1
            encoder.on_mesg(
                Profile["mesg_num"]["RECORD"],
                {
                    "timestamp": lap_start + timedelta(seconds=duration * fraction),
                    "distance": index * 1000 + fraction * 1000,
                    "heart_rate": heart_rate + round(fraction * 2),
                    "cadence": 172 + index,
                    "enhanced_speed": 1000 / duration,
                    "enhanced_altitude": 20 + index + fraction,
                },
            )
        elapsed += duration
        encoder.on_mesg(
            Profile["mesg_num"]["LAP"],
            {
                "timestamp": start + timedelta(seconds=elapsed),
                "start_time": lap_start,
                "total_elapsed_time": duration,
                "total_timer_time": duration,
                "total_distance": 1000.0,
                "avg_heart_rate": heart_rate,
                "max_heart_rate": heart_rate + 8,
                "avg_cadence": 174 + index,
                "enhanced_avg_speed": 1000 / duration,
            },
        )

    encoder.on_mesg(
        Profile["mesg_num"]["SESSION"],
        {
            "timestamp": start + timedelta(seconds=elapsed),
            "start_time": start,
            "total_elapsed_time": elapsed,
            "total_timer_time": elapsed,
            "total_distance": 4000.0,
            "sport": "running",
            "sub_sport": "generic",
            "first_lap_index": 0,
            "num_laps": len(lap_durations),
            "avg_heart_rate": 152,
            "max_heart_rate": 165,
            "avg_cadence": 176,
            "total_ascent": 18,
            "enhanced_avg_speed": 4000 / elapsed,
        },
    )
    encoder.on_mesg(
        Profile["mesg_num"]["ACTIVITY"],
        {
            "timestamp": start + timedelta(seconds=elapsed),
            "total_timer_time": elapsed,
            "num_sessions": 1,
            "type": "manual",
            "event": "activity",
            "event_type": "stop",
        },
    )
    content = encoder.close()
    assert record_count == 12
    return bytes(content)
