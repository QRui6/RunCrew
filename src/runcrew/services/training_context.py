from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from runcrew.domain.activity import ActivityDetail, ActivitySummary
from runcrew.domain.training_review import (
    TrainingReviewRequest,
    TrainingWindowMetrics,
)


Activity = ActivitySummary | ActivityDetail


@dataclass(frozen=True, slots=True)
class TrainingContext:
    request: TrainingReviewRequest
    target: Activity
    activities: tuple[Activity, ...]
    current_7d: TrainingWindowMetrics
    previous_7d: TrainingWindowMetrics
    input_hash: str


def build_training_context(
    request: TrainingReviewRequest,
    *,
    target: Activity,
    activities: list[Activity],
) -> TrainingContext:
    if target.id != request.target_activity_id:
        raise ValueError("target activity does not match request")

    anchor = target.started_at
    lookback_start = anchor - timedelta(days=request.lookback_days)
    relevant_by_id = {
        activity.id: activity
        for activity in [*activities, target]
        if lookback_start < activity.started_at <= anchor
    }
    relevant = tuple(
        sorted(
            relevant_by_id.values(),
            key=lambda activity: (activity.started_at, activity.id),
        )
    )
    current_start = anchor - timedelta(days=7)
    previous_start = anchor - timedelta(days=14)
    current = _window_metrics(relevant, current_start, anchor)
    previous = _window_metrics(relevant, previous_start, current_start)
    digest = hashlib.sha256(
        json.dumps(
            _replay_payload(request, target, relevant),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return TrainingContext(
        request=request,
        target=target,
        activities=relevant,
        current_7d=current,
        previous_7d=previous,
        input_hash=digest,
    )


def _window_metrics(
    activities: tuple[Activity, ...],
    start: datetime,
    end: datetime,
) -> TrainingWindowMetrics:
    selected = [
        activity for activity in activities if start < activity.started_at <= end
    ]
    loads = [
        activity.training_load
        for activity in selected
        if activity.training_load is not None
    ]
    return TrainingWindowMetrics(
        start=start,
        end=end,
        activity_count=len(selected),
        distance_meters=sum(activity.distance_meters or 0 for activity in selected),
        duration_seconds=sum(activity.duration_seconds for activity in selected),
        training_load_total=sum(loads) if loads else None,
        training_load_coverage=len(loads) / len(selected) if selected else 0,
    )


def _replay_payload(
    request: TrainingReviewRequest,
    target: Activity,
    activities: tuple[Activity, ...],
) -> dict:
    return {
        "request": request.model_dump(mode="json"),
        "target_id": target.id,
        "activities": [_activity_features(activity) for activity in activities],
    }


def _activity_features(activity: Activity) -> dict:
    features = {
        "id": activity.id,
        "sport_type": activity.sport_type.value,
        "started_at": activity.started_at.isoformat(),
        "duration_seconds": activity.duration_seconds,
        "distance_meters": activity.distance_meters,
        "average_pace_seconds_per_km": activity.average_pace_seconds_per_km,
        "average_heart_rate": activity.average_heart_rate,
        "training_load": activity.training_load,
    }
    if isinstance(activity, ActivityDetail):
        features["laps"] = [
            {
                "index": lap.index,
                "duration_seconds": lap.duration_seconds,
                "distance_meters": lap.distance_meters,
                "average_pace_seconds_per_km": lap.average_pace_seconds_per_km,
                "average_heart_rate": lap.average_heart_rate,
            }
            for lap in activity.laps
        ]
    return features
