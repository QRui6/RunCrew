from __future__ import annotations

from statistics import mean, pstdev

from runcrew.domain.activity import ActivityDetail, ActivitySummary
from runcrew.domain.review import ActivityReview, DataQuality, ReviewObservation


def format_duration(seconds: int) -> str:
    hours, remaining = divmod(seconds, 3600)
    minutes, seconds = divmod(remaining, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def format_pace(seconds_per_km: float | None) -> str | None:
    if seconds_per_km is None:
        return None
    rounded = round(seconds_per_km)
    minutes, seconds = divmod(rounded, 60)
    return f"{minutes}:{seconds:02d}/km"


def build_activity_review(
    activity: ActivitySummary | ActivityDetail,
) -> ActivityReview:
    missing_fields = [
        name
        for name, value in {
            "distance_meters": activity.distance_meters,
            "average_pace_seconds_per_km": activity.average_pace_seconds_per_km,
            "average_heart_rate": activity.average_heart_rate,
        }.items()
        if value is None
    ]

    summary = {
        "sport_type": activity.sport_type.value,
        "started_at": activity.started_at.isoformat(),
        "distance_km": round(activity.distance_meters / 1000, 2)
        if activity.distance_meters is not None
        else None,
        "duration": format_duration(activity.duration_seconds),
        "average_pace": format_pace(activity.average_pace_seconds_per_km),
        "average_heart_rate": activity.average_heart_rate,
    }

    observations: list[ReviewObservation] = []
    if isinstance(activity, ActivityDetail):
        lap_paces = [
            lap.average_pace_seconds_per_km
            for lap in activity.laps
            if lap.average_pace_seconds_per_km is not None
        ]
        if len(lap_paces) >= 3:
            pace_cv = pstdev(lap_paces) / mean(lap_paces)
            if pace_cv <= 0.05:
                level = "good"
                message = "分圈配速稳定。"
            elif pace_cv <= 0.10:
                level = "normal"
                message = "分圈配速存在正常波动。"
            else:
                level = "attention"
                message = "分圈配速波动较大，建议结合路线和训练目标复核。"
            observations.append(
                ReviewObservation(
                    type="pace_stability",
                    level=level,
                    message=message,
                    evidence={
                        "lap_count": len(lap_paces),
                        "pace_cv": round(pace_cv, 4),
                    },
                )
            )

    if not observations:
        observations.append(
            ReviewObservation(
                type="data_availability",
                level="unknown",
                message="当前数据不足以判断分圈稳定性。",
                evidence={"requires": "at least 3 laps with pace"},
            )
        )

    if len(missing_fields) == 0:
        confidence = "high"
    elif len(missing_fields) == 1:
        confidence = "medium"
    else:
        confidence = "low"

    return ActivityReview(
        activity_id=activity.id,
        summary=summary,
        observations=observations,
        data_quality=DataQuality(
            missing_fields=missing_fields,
            confidence=confidence,
        ),
    )

