from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from runcrew.domain.activity import ActivityDetail, ActivitySummary
from runcrew.domain.recovery_assessment import (
    RecoveryAssessmentRequest,
    RecoveryWindowMetrics,
)
from runcrew.domain.training_cycle import DailyCheckIn, PlanSession


Activity = ActivitySummary | ActivityDetail


@dataclass(frozen=True, slots=True)
class RecoveryAssessmentContext:
    request: RecoveryAssessmentRequest
    activities: tuple[Activity, ...]
    check_ins: tuple[DailyCheckIn, ...]
    next_session: PlanSession | None
    current_7d: RecoveryWindowMetrics
    previous_7d: RecoveryWindowMetrics
    input_hash: str


def build_recovery_context(
    request: RecoveryAssessmentRequest,
    *,
    activities: list[Activity],
    check_ins: list[DailyCheckIn],
    next_session: PlanSession | None,
) -> RecoveryAssessmentContext:
    start = request.assessed_at - timedelta(days=request.lookback_days)
    activities_by_id = {
        activity.id: activity
        for activity in activities
        if start < activity.started_at <= request.assessed_at
    }
    relevant_activities = tuple(
        sorted(
            activities_by_id.values(),
            key=lambda activity: (activity.started_at, activity.id),
        )
    )
    start_day = start.date()
    end_day = request.assessed_at.date()
    relevant_check_ins = tuple(
        sorted(
            (item for item in check_ins if start_day <= item.day <= end_day),
            key=lambda item: (item.day, item.id),
        )
    )
    current_start = request.assessed_at - timedelta(days=7)
    previous_start = request.assessed_at - timedelta(days=14)
    current = _window_metrics(relevant_activities, current_start, request.assessed_at)
    previous = _window_metrics(relevant_activities, previous_start, current_start)
    payload = {
        "request": request.model_dump(mode="json"),
        "activities": [_activity_features(item) for item in relevant_activities],
        "check_ins": [
            {
                "day": item.day.isoformat(),
                "fatigue": item.fatigue,
                "soreness": item.soreness,
                "sleep_quality": item.sleep_quality,
                "readiness": item.readiness,
                "pain_area": item.pain_area,
                "pain_severity": item.pain_severity,
                "acute_symptoms": item.acute_symptoms,
            }
            for item in relevant_check_ins
        ],
        "next_session": next_session.model_dump(mode="json") if next_session else None,
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return RecoveryAssessmentContext(
        request=request,
        activities=relevant_activities,
        check_ins=relevant_check_ins,
        next_session=next_session,
        current_7d=current,
        previous_7d=previous,
        input_hash=digest,
    )


def _window_metrics(
    activities: tuple[Activity, ...], start: datetime, end: datetime
) -> RecoveryWindowMetrics:
    selected = [item for item in activities if start < item.started_at <= end]
    loads = [item.training_load for item in selected if item.training_load is not None]
    return RecoveryWindowMetrics(
        activity_count=len(selected),
        distance_meters=sum(item.distance_meters or 0 for item in selected),
        duration_seconds=sum(item.duration_seconds for item in selected),
        training_load_total=sum(loads) if loads else None,
        training_load_coverage=len(loads) / len(selected) if selected else 0,
    )


def _activity_features(activity: Activity) -> dict:
    return {
        "id": activity.id,
        "started_at": activity.started_at.isoformat(),
        "duration_seconds": activity.duration_seconds,
        "distance_meters": activity.distance_meters,
        "training_load": activity.training_load,
    }
