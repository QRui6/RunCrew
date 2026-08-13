from __future__ import annotations

import hashlib
import json
from datetime import datetime, time, timedelta
from typing import Protocol

from runcrew.domain.activity import ActivityDetail, ActivitySummary, SportType
from runcrew.domain.training_cycle import PlanSession, TrainingPlan, utc_now
from runcrew.domain.training_execution import (
    ExecutionCandidate,
    ExecutionConfirmationResult,
    ExecutionEvidence,
    SessionExecutionComparison,
    TrainingExecutionConfirmation,
    TrainingExecutionDecisionRequest,
    TrainingExecutionRequest,
    TrainingExecutionResult,
)


Activity = ActivitySummary | ActivityDetail
RUNNING_SPORTS = {
    SportType.RUN,
    SportType.INDOOR_RUN,
    SportType.TRAIL_RUN,
    SportType.TRACK_RUN,
}


class ExecutionActivityStore(Protocol):
    def between(
        self,
        start: datetime,
        end: datetime,
        *,
        provider: str | None = None,
    ) -> list[Activity]: ...

    def get_by_id(self, activity_id: str) -> Activity | None: ...


class ExecutionPlanStore(Protocol):
    def get(self, plan_id: str) -> TrainingPlan | None: ...

    def save(self, plan: TrainingPlan) -> None: ...


class ExecutionConfirmationStore(Protocol):
    def save(self, confirmation: TrainingExecutionConfirmation) -> None: ...


class TrainingExecutionError(ValueError):
    pass


def execute_training_comparison(
    request: TrainingExecutionRequest,
    *,
    activities: ExecutionActivityStore,
    plans: ExecutionPlanStore,
) -> TrainingExecutionResult:
    plan = plans.get(request.plan_id)
    if plan is None:
        raise TrainingExecutionError("训练计划不存在")
    timezone_info = request.as_of.tzinfo
    window_start = datetime.combine(
        plan.week_start - timedelta(days=request.date_tolerance_days + 1),
        time.max,
        tzinfo=timezone_info,
    )
    window_end = min(
        request.as_of,
        datetime.combine(
            plan.week_start + timedelta(days=6 + request.date_tolerance_days),
            time.max,
            tzinfo=timezone_info,
        ),
    )
    history = activities.between(
        window_start,
        window_end,
        provider=request.provider.value if request.provider is not None else None,
    )
    for session in plan.sessions:
        if session.linked_activity_id is None:
            continue
        linked = activities.get_by_id(session.linked_activity_id)
        if linked is not None and linked.started_at <= request.as_of:
            history.append(linked)
    return build_training_comparison(request, plan=plan, activities=history)


def build_training_comparison(
    request: TrainingExecutionRequest,
    *,
    plan: TrainingPlan,
    activities: list[Activity],
) -> TrainingExecutionResult:
    relevant = sorted(
        {
            activity.id: activity
            for activity in activities
            if activity.sport_type in RUNNING_SPORTS
            and activity.started_at <= request.as_of
            and (
                activity.id
                in {
                    item.linked_activity_id
                    for item in plan.sessions
                    if item.linked_activity_id is not None
                }
                or (
                    abs((_local_day(activity, request) - plan.week_start).days)
                    <= (6 + request.date_tolerance_days)
                    and _local_day(activity, request)
                    >= plan.week_start - timedelta(days=request.date_tolerance_days)
                )
            )
        }.values(),
        key=lambda item: (item.started_at, item.id),
    )
    activities_by_id = {item.id: item for item in relevant}
    input_hash = _hash_payload(
        {
            "request": request.model_dump(mode="json"),
            "plan": _plan_features(plan),
            "activities": [_activity_features(item) for item in relevant],
        }
    )
    linked_ids = {
        session.linked_activity_id
        for session in plan.sessions
        if session.linked_activity_id is not None
    }
    available = [item for item in relevant if item.id not in linked_ids]
    candidate_map = {
        session.id: _candidates(
            session,
            available,
            request.date_tolerance_days,
            request.as_of,
        )
        for session in plan.sessions
        if session.session_type != "rest"
        and session.status == "planned"
        and session.scheduled_for <= request.as_of.date()
    }
    top_activity_counts: dict[str, int] = {}
    for candidates in candidate_map.values():
        if candidates:
            identifier = candidates[0].activity_id
            top_activity_counts[identifier] = top_activity_counts.get(identifier, 0) + 1

    comparisons: list[SessionExecutionComparison] = []
    suggested_ids: set[str] = set()
    for session in plan.sessions:
        comparison = _compare_session(
            session,
            request=request,
            activities_by_id=activities_by_id,
            candidates=candidate_map.get(session.id, []),
            top_activity_counts=top_activity_counts,
        )
        if comparison.match_state == "suggested" and comparison.suggested_activity_id:
            suggested_ids.add(comparison.suggested_activity_id)
        comparisons.append(comparison)
    used_ids = linked_ids | suggested_ids
    unassigned = [item.id for item in relevant if item.id not in used_ids]
    counts: dict[str, int] = {}
    for item in comparisons:
        counts[item.outcome] = counts.get(item.outcome, 0) + 1
    summary = "；".join(
        f"{label}{counts.get(key, 0)}节"
        for key, label in (
            ("complete", "完成"),
            ("partial", "部分完成"),
            ("skipped", "跳过"),
            ("unmatched", "未匹配"),
            ("upcoming", "待执行"),
            ("rest", "休息"),
        )
        if counts.get(key, 0)
    ) or "计划中没有训练课"
    return TrainingExecutionResult(
        input_hash=input_hash,
        plan_id=plan.id,
        plan_revision=plan.revision,
        as_of=request.as_of,
        summary=summary,
        sessions=comparisons,
        unassigned_activity_ids=unassigned,
    )


def confirm_training_execution(
    request: TrainingExecutionDecisionRequest,
    *,
    plans: ExecutionPlanStore,
    activities: ExecutionActivityStore,
    confirmations: ExecutionConfirmationStore,
) -> ExecutionConfirmationResult:
    plan = plans.get(request.plan_id)
    if plan is None:
        raise TrainingExecutionError("训练计划不存在")
    target = next((item for item in plan.sessions if item.id == request.session_id), None)
    if target is None:
        raise TrainingExecutionError("计划课不存在")
    if target.session_type == "rest":
        raise TrainingExecutionError("休息日不能关联实际活动或标记为跳过")
    if plan.revision != request.base_revision:
        confirmation = TrainingExecutionConfirmation(
            plan_id=plan.id,
            base_revision=request.base_revision,
            session_id=request.session_id,
            decision=request.decision,
            activity_id=(
                request.activity_id if request.decision == "confirm_match" else None
            ),
            comment=request.comment,
            status="stale",
        )
        confirmations.save(confirmation)
        return ExecutionConfirmationResult(plan=plan, confirmation=confirmation)
    if plan.status != "active":
        raise TrainingExecutionError("只能修改激活计划的执行状态")
    if request.decision in {"confirm_match", "mark_skipped"} and (
        target.scheduled_for > request.as_of.date()
    ):
        raise TrainingExecutionError("尚未到计划课日期，不能确认完成或标记跳过")
    if request.decision == "clear_execution" and (
        target.status == "planned" and target.linked_activity_id is None
    ):
        raise TrainingExecutionError("该计划课尚无执行状态可清除")

    linked_activity_id: str | None = None
    status = "planned"
    if request.decision == "confirm_match":
        activity = activities.get_by_id(request.activity_id or "")
        if activity is None or activity.sport_type not in RUNNING_SPORTS:
            raise TrainingExecutionError("实际跑步活动不存在或类型不受支持")
        if activity.started_at > request.as_of:
            raise TrainingExecutionError("不能确认知识截止时间之后的活动")
        if abs(
            (_local_day_for_timezone(activity, request.as_of) - target.scheduled_for).days
        ) > 3:
            raise TrainingExecutionError("活动日期与计划课相差超过3天，请先核对目标课")
        duplicate = next(
            (
                item.id
                for item in plan.sessions
                if item.id != request.session_id
                and item.linked_activity_id == request.activity_id
            ),
            None,
        )
        if duplicate is not None:
            raise TrainingExecutionError(f"该活动已经关联到计划课：{duplicate}")
        linked_activity_id = activity.id
        status = "completed"
    elif request.decision == "mark_skipped":
        status = "skipped"

    updated_sessions = [
        item.model_copy(
            update={"status": status, "linked_activity_id": linked_activity_id}
        )
        if item.id == request.session_id
        else item
        for item in plan.sessions
    ]
    plan.sessions = updated_sessions
    plan.revision += 1
    plan.updated_at = utc_now()
    plan = TrainingPlan.model_validate(plan.model_dump())
    confirmation = TrainingExecutionConfirmation(
        plan_id=plan.id,
        base_revision=request.base_revision,
        applied_revision=plan.revision,
        session_id=request.session_id,
        decision=request.decision,
        activity_id=(
            linked_activity_id if request.decision == "confirm_match" else None
        ),
        comment=request.comment,
        status="applied",
    )
    plans.save(plan)
    confirmations.save(confirmation)
    return ExecutionConfirmationResult(plan=plan, confirmation=confirmation)


def _compare_session(
    session: PlanSession,
    *,
    request: TrainingExecutionRequest,
    activities_by_id: dict[str, Activity],
    candidates: list[ExecutionCandidate],
    top_activity_counts: dict[str, int],
) -> SessionExecutionComparison:
    schedule_evidence = ExecutionEvidence(
        id=f"session:{session.id}",
        type="schedule",
        message="计划课状态和目标来自指定 revision 的训练计划。",
        values={
            "scheduled_for": session.scheduled_for.isoformat(),
            "session_type": session.session_type,
            "status": session.status,
            "distance_meters": session.distance_meters,
            "duration_seconds": session.duration_seconds,
        },
        rule_source="active_plan",
    )
    if session.session_type == "rest":
        return SessionExecutionComparison(
            session_id=session.id,
            scheduled_for=session.scheduled_for.isoformat(),
            session_type=session.session_type,
            outcome="rest",
            match_state="none",
            confidence="high",
            requires_user_confirmation=False,
            evidence=[schedule_evidence],
        )
    if session.status == "skipped":
        return SessionExecutionComparison(
            session_id=session.id,
            scheduled_for=session.scheduled_for.isoformat(),
            session_type=session.session_type,
            outcome="skipped",
            match_state="confirmed",
            confidence="high",
            requires_user_confirmation=False,
            evidence=[schedule_evidence],
        )
    if session.linked_activity_id is not None:
        activity = activities_by_id.get(session.linked_activity_id)
        if activity is None:
            return SessionExecutionComparison(
                session_id=session.id,
                scheduled_for=session.scheduled_for.isoformat(),
                session_type=session.session_type,
                outcome="unmatched",
                match_state="broken_link",
                confidence="low",
                requires_user_confirmation=True,
                evidence=[
                    schedule_evidence,
                    ExecutionEvidence(
                        id=f"missing:linked_activity:{session.linked_activity_id}",
                        type="missing_data",
                        message="计划课记录了活动关联，但当前上下文找不到该活动。",
                        values={"activity_id": session.linked_activity_id},
                        rule_source="missing_data_policy",
                    ),
                ],
                warnings=["请检查 Provider 过滤或清除失效关联。"],
            )
        ratio, volume_evidence = _completion(session, activity)
        outcome = (
            "unmatched" if ratio is None else "complete" if ratio >= 0.9 else "partial"
        )
        return SessionExecutionComparison(
            session_id=session.id,
            scheduled_for=session.scheduled_for.isoformat(),
            session_type=session.session_type,
            outcome=outcome,
            match_state="confirmed",
            suggested_activity_id=activity.id,
            completion_ratio=ratio,
            confidence="high" if ratio is not None else "medium",
            requires_user_confirmation=False,
            evidence=[
                schedule_evidence,
                ExecutionEvidence(
                    id=f"confirmed:{session.id}:{activity.id}",
                    type="confirmed_link",
                    message="该活动关联来自用户已确认的计划执行状态。",
                    values={"activity_id": activity.id},
                    rule_source="user_confirmation",
                ),
                volume_evidence,
            ],
            warnings=([] if ratio is not None else ["缺少可比较训练量，无法计算完成比例。"]),
        )
    if session.scheduled_for > request.as_of.date():
        return SessionExecutionComparison(
            session_id=session.id,
            scheduled_for=session.scheduled_for.isoformat(),
            session_type=session.session_type,
            outcome="upcoming",
            match_state="none",
            confidence="high",
            requires_user_confirmation=False,
            evidence=[schedule_evidence],
        )
    if not candidates:
        return SessionExecutionComparison(
            session_id=session.id,
            scheduled_for=session.scheduled_for.isoformat(),
            session_type=session.session_type,
            outcome="unmatched",
            match_state="none",
            confidence="low",
            requires_user_confirmation=True,
            evidence=[
                schedule_evidence,
                ExecutionEvidence(
                    id=f"missing:candidate:{session.id}",
                    type="missing_data",
                    message="时间容差内没有可用跑步活动；不能自动判定为跳过。",
                    values={"date_tolerance_days": request.date_tolerance_days},
                    rule_source="missing_data_policy",
                ),
            ],
        )
    best = candidates[0]
    close_second = len(candidates) > 1 and best.score - candidates[1].score < 0.15
    shared_best = top_activity_counts.get(best.activity_id, 0) > 1
    if best.score < 0.65 or close_second or shared_best:
        reason = (
            "同一活动同时是多节计划课的最佳候选"
            if shared_best
            else "多个候选得分接近或最佳得分不足"
        )
        return SessionExecutionComparison(
            session_id=session.id,
            scheduled_for=session.scheduled_for.isoformat(),
            session_type=session.session_type,
            outcome="unmatched",
            match_state="ambiguous",
            candidates=candidates,
            confidence="low",
            requires_user_confirmation=True,
            evidence=[
                schedule_evidence,
                ExecutionEvidence(
                    id=f"conflict:{session.id}",
                    type="candidate_conflict",
                    message=f"{reason}，系统不自动选择。",
                    values={"candidate_count": len(candidates)},
                    rule_source="runcrew_matching_rule",
                ),
            ],
        )
    completion = _candidate_completion(best)
    outcome = (
        "unmatched"
        if completion is None
        else "complete"
        if completion >= 0.9
        else "partial"
    )
    return SessionExecutionComparison(
        session_id=session.id,
        scheduled_for=session.scheduled_for.isoformat(),
        session_type=session.session_type,
        outcome=outcome,
        match_state="suggested",
        suggested_activity_id=best.activity_id,
        candidates=candidates,
        completion_ratio=completion,
        confidence="medium",
        requires_user_confirmation=True,
        evidence=[
            schedule_evidence,
            ExecutionEvidence(
                id=f"candidate:{session.id}:{best.activity_id}",
                type="date_proximity",
                message="候选活动由日期接近度和可比较训练量确定，尚未写入。",
                values={
                    "activity_id": best.activity_id,
                    "score": best.score,
                    "date_difference_days": best.date_difference_days,
                },
                rule_source="runcrew_matching_rule",
            ),
        ],
    )


def _candidates(
    session: PlanSession,
    activities: list[Activity],
    tolerance: int,
    as_of: datetime,
) -> list[ExecutionCandidate]:
    result: list[ExecutionCandidate] = []
    for activity in activities:
        difference = abs(
            (
                activity.started_at.astimezone(as_of.tzinfo).date()
                - session.scheduled_for
            ).days
        )
        if difference > tolerance:
            continue
        distance_ratio = _ratio(activity.distance_meters, session.distance_meters)
        duration_ratio = _ratio(activity.duration_seconds, session.duration_seconds)
        comparisons = [
            ratio for ratio in (distance_ratio, duration_ratio) if ratio is not None
        ]
        volume_score = (
            sum(min(item, 1 / item) for item in comparisons if item > 0)
            / len(comparisons)
            if comparisons
            else None
        )
        date_score = 1 - difference / (tolerance + 1)
        score = (
            0.55 * date_score + 0.45 * volume_score
            if volume_score is not None
            else 0.65 * date_score
        )
        result.append(
            ExecutionCandidate(
                activity_id=activity.id,
                started_at=activity.started_at,
                date_difference_days=difference,
                score=round(score, 4),
                distance_ratio=(round(distance_ratio, 4) if distance_ratio else None),
                duration_ratio=(round(duration_ratio, 4) if duration_ratio else None),
            )
        )
    return sorted(result, key=lambda item: (-item.score, item.started_at, item.activity_id))


def _completion(
    session: PlanSession, activity: Activity
) -> tuple[float | None, ExecutionEvidence]:
    ratios = [
        item
        for item in (
            _ratio(activity.distance_meters, session.distance_meters),
            _ratio(activity.duration_seconds, session.duration_seconds),
        )
        if item is not None
    ]
    completion = min(ratios) if ratios else None
    return (
        round(completion, 4) if completion is not None else None,
        ExecutionEvidence(
            id=f"volume:{session.id}:{activity.id}",
            type="volume_comparison",
            message=(
                "按计划中可比较的距离或时长计算保守完成比例。"
                if ratios
                else "计划目标与实际活动缺少可比较训练量。"
            ),
            values={
                "activity_id": activity.id,
                "distance_ratio": _ratio(
                    activity.distance_meters, session.distance_meters
                ),
                "duration_ratio": _ratio(
                    activity.duration_seconds, session.duration_seconds
                ),
            },
            rule_source=(
                "runcrew_matching_rule" if ratios else "missing_data_policy"
            ),
        ),
    )


def _candidate_completion(candidate: ExecutionCandidate) -> float | None:
    ratios = [
        item
        for item in (candidate.distance_ratio, candidate.duration_ratio)
        if item is not None
    ]
    return min(ratios) if ratios else None


def _ratio(actual: float | int | None, planned: float | int | None) -> float | None:
    if actual is None or planned is None or planned <= 0:
        return None
    return actual / planned


def _activity_features(activity: Activity) -> dict:
    return {
        "id": activity.id,
        "sport_type": activity.sport_type,
        "started_at": activity.started_at.isoformat(),
        "duration_seconds": activity.duration_seconds,
        "distance_meters": activity.distance_meters,
    }


def _plan_features(plan: TrainingPlan) -> dict:
    return {
        "id": plan.id,
        "goal_id": plan.goal_id,
        "week_start": plan.week_start.isoformat(),
        "status": plan.status,
        "revision": plan.revision,
        "sessions": [item.model_dump(mode="json") for item in plan.sessions],
    }


def _local_day(activity: Activity, request: TrainingExecutionRequest):
    return _local_day_for_timezone(activity, request.as_of)


def _local_day_for_timezone(activity: Activity, anchor: datetime):
    return activity.started_at.astimezone(anchor.tzinfo).date()


def _hash_payload(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
