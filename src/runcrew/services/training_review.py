from __future__ import annotations

from statistics import median

from runcrew.domain.review import ActivityReview, DataQuality
from runcrew.domain.training_review import (
    TrainingFinding,
    TrainingReviewResult,
)
from runcrew.services.activity_review import build_activity_review
from runcrew.services.training_context import TrainingContext


def build_training_review(context: TrainingContext) -> TrainingReviewResult:
    activity_review = build_activity_review(context.target)
    completion = _completion_finding(context)
    load_change = _load_change_finding(context)
    anomaly = _anomaly_finding(context, activity_review)
    findings = [completion, load_change, anomaly]

    missing = list(activity_review.data_quality.missing_fields)
    if completion.level == "unknown":
        missing.append("planned_session")
    if load_change.level == "unknown":
        missing.append("training_load_history")
    if anomaly.level == "unknown":
        missing.append("pace_baseline")
    missing = sorted(set(missing))
    confidence = "high" if not missing else "medium" if len(missing) <= 2 else "low"

    return TrainingReviewResult(
        input_hash=context.input_hash,
        target_activity_id=context.target.id,
        activity_review=activity_review,
        current_7d=context.current_7d,
        previous_7d=context.previous_7d,
        findings=findings,
        data_quality=DataQuality(
            missing_fields=missing,
            confidence=confidence,
        ),
    )


def _completion_finding(context: TrainingContext) -> TrainingFinding:
    plan = context.request.planned_session
    if plan is None:
        return TrainingFinding(
            type="training_completion",
            level="unknown",
            message="缺少本次计划目标，无法判断训练完成度。",
            evidence={"requires": "planned_session.distance_meters or duration_seconds"},
        )

    ratios: list[float] = []
    evidence = {
        "actual_distance_meters": context.target.distance_meters,
        "actual_duration_seconds": context.target.duration_seconds,
        "planned_distance_meters": plan.distance_meters,
        "planned_duration_seconds": plan.duration_seconds,
    }
    if plan.distance_meters is not None and context.target.distance_meters is not None:
        ratios.append(context.target.distance_meters / plan.distance_meters)
    if plan.duration_seconds is not None:
        ratios.append(context.target.duration_seconds / plan.duration_seconds)
    if not ratios:
        return TrainingFinding(
            type="training_completion",
            level="unknown",
            message="实际活动缺少与计划匹配的字段，无法判断训练完成度。",
            evidence={**evidence, "requires": "matching actual distance or duration"},
        )

    ratio = sum(ratios) / len(ratios)
    evidence["completion_ratio"] = round(ratio, 4)
    if 0.9 <= ratio <= 1.1:
        level = "good"
        message = "训练完成度与计划目标一致。"
    elif 0.75 <= ratio <= 1.25:
        level = "normal"
        message = "训练完成度与计划存在可见偏差。"
    else:
        level = "attention"
        message = "训练完成度明显偏离计划，需要结合执行原因复核。"
    return TrainingFinding(
        type="training_completion",
        level=level,
        message=message,
        evidence=evidence,
    )


def _load_change_finding(context: TrainingContext) -> TrainingFinding:
    current = context.current_7d
    previous = context.previous_7d
    evidence = {
        "current_7d_training_load": current.training_load_total,
        "previous_7d_training_load": previous.training_load_total,
        "current_7d_coverage": round(current.training_load_coverage, 4),
        "previous_7d_coverage": round(previous.training_load_coverage, 4),
    }
    if (
        current.training_load_total is None
        or previous.training_load_total is None
        or previous.training_load_total <= 0
    ):
        return TrainingFinding(
            type="load_change",
            level="unknown",
            message="连续两个七天窗口的训练负荷不足，无法判断变化。",
            evidence={**evidence, "requires": "training load in both 7-day windows"},
        )

    change = current.training_load_total / previous.training_load_total - 1
    evidence["change_ratio"] = round(change, 4)
    if -0.4 <= change <= 0.2:
        level = "normal"
        message = "七天训练负荷变化处于当前规则的正常区间。"
    else:
        level = "attention"
        message = "七天训练负荷变化超出当前规则区间，需要结合训练阶段复核。"
    return TrainingFinding(
        type="load_change",
        level=level,
        message=message,
        evidence=evidence,
    )


def _anomaly_finding(
    context: TrainingContext,
    activity_review: ActivityReview,
) -> TrainingFinding:
    pace_observation = next(
        (
            observation
            for observation in activity_review.observations
            if observation.type == "pace_stability"
        ),
        None,
    )
    if pace_observation is not None:
        return TrainingFinding(
            type="training_anomaly",
            level=pace_observation.level,
            message=pace_observation.message,
            evidence={
                "method": "lap_pace_cv",
                **pace_observation.evidence,
            },
        )

    prior_paces = [
        activity.average_pace_seconds_per_km
        for activity in context.activities
        if activity.id != context.target.id
        and activity.sport_type == context.target.sport_type
        and activity.average_pace_seconds_per_km is not None
    ]
    target_pace = context.target.average_pace_seconds_per_km
    if target_pace is None or len(prior_paces) < 3:
        return TrainingFinding(
            type="training_anomaly",
            level="unknown",
            message="缺少分圈或同类型历史配速，无法判断本次训练异常。",
            evidence={
                "comparable_activity_count": len(prior_paces),
                "requires": "3 laps with pace or 3 prior same-sport activities",
            },
        )

    baseline = median(prior_paces)
    deviation = target_pace / baseline - 1
    level = "attention" if abs(deviation) > 0.1 else "normal"
    message = (
        "本次平均配速明显偏离近期同类型活动。"
        if level == "attention"
        else "本次平均配速未明显偏离近期同类型活动。"
    )
    return TrainingFinding(
        type="training_anomaly",
        level=level,
        message=message,
        evidence={
            "method": "same_sport_median_pace",
            "target_pace_seconds_per_km": round(target_pace, 2),
            "baseline_pace_seconds_per_km": round(baseline, 2),
            "deviation_ratio": round(deviation, 4),
            "comparable_activity_count": len(prior_paces),
        },
    )
