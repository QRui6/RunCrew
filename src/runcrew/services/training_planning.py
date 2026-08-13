from __future__ import annotations

import hashlib
import itertools
import json
import uuid
from datetime import date, datetime, time, timedelta
from typing import Protocol

from runcrew.domain.activity import ActivityDetail, ActivitySummary, SportType
from runcrew.domain.recovery_assessment import RecoveryAssessmentResult
from runcrew.domain.training_cycle import PlanSession, PlanSessionPatch, TrainingGoal, TrainingPlan
from runcrew.domain.training_planning import (
    PlanAdjustmentRequest,
    PlanChangeProposalDraft,
    PlanningEvidence,
    RecoveryAssessmentSnapshot,
    TrainingPlanningResult,
    WeeklyPlanDraft,
    WeeklyPlanDraftRequest,
)


Activity = ActivitySummary | ActivityDetail
RUNNING_SPORTS = {
    SportType.RUN,
    SportType.INDOOR_RUN,
    SportType.TRAIL_RUN,
    SportType.TRACK_RUN,
}
WEEKDAY_INDEX = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


class PlanningActivityStore(Protocol):
    def between(
        self,
        start: datetime,
        end: datetime,
        *,
        provider: str | None = None,
    ) -> list[Activity]: ...


class PlanningGoalStore(Protocol):
    def get(self, goal_id: str) -> TrainingGoal | None: ...


class PlanningPlanStore(Protocol):
    def for_goal_week(self, goal_id: str, week_start: date) -> TrainingPlan | None: ...

    def active_from_week(
        self, goal_id: str, week_start: date, *, limit: int = 8
    ) -> list[TrainingPlan]: ...


class TrainingPlanningError(ValueError):
    pass


def execute_weekly_plan_draft(
    request: WeeklyPlanDraftRequest,
    *,
    activities: PlanningActivityStore,
    goals: PlanningGoalStore,
    plans: PlanningPlanStore,
) -> TrainingPlanningResult:
    goal = _require_active_goal(goals, request.goal_id)
    cutoff = min(
        request.as_of,
        datetime.combine(request.week_start, time.min, tzinfo=request.as_of.tzinfo),
    )
    history = activities.between(
        cutoff - timedelta(days=request.lookback_days),
        cutoff,
        provider=request.provider.value if request.provider is not None else None,
    )
    existing = plans.for_goal_week(goal.id, request.week_start)
    return build_weekly_plan_draft(
        request,
        goal=goal,
        activities=history,
        existing_plan=existing,
    )


def build_weekly_plan_draft(
    request: WeeklyPlanDraftRequest,
    *,
    goal: TrainingGoal,
    activities: list[Activity],
    existing_plan: TrainingPlan | None,
) -> TrainingPlanningResult:
    cutoff = min(
        request.as_of,
        datetime.combine(request.week_start, time.min, tzinfo=request.as_of.tzinfo),
    )
    history_start = cutoff - timedelta(days=request.lookback_days)
    relevant = sorted(
        {
            item.id: item
            for item in activities
            if history_start < item.started_at <= cutoff
            and item.sport_type in RUNNING_SPORTS
        }.values(),
        key=lambda item: (item.started_at, item.id),
    )
    input_hash = _hash_payload(
        {
            "request": request.model_dump(mode="json"),
            "goal": _goal_features(goal),
            "activities": [_activity_features(item) for item in relevant],
            "existing_plan": (
                existing_plan.model_dump(mode="json") if existing_plan else None
            ),
        }
    )
    evidence = _draft_evidence(request, goal, relevant)
    if existing_plan is not None:
        return _blocked_draft(
            request,
            input_hash,
            evidence,
            "这一周已经存在训练计划，计划 Agent 不会覆盖已有计划。",
            "week_already_has_plan",
        )
    current_week_start = request.as_of.date() - timedelta(
        days=request.as_of.date().weekday()
    )
    if request.week_start <= current_week_start:
        return _blocked_draft(
            request,
            input_hash,
            evidence,
            "v1 只生成尚未开始的训练周；进行中或过去的周需人工处理已完成训练。",
            "week_not_in_future",
        )
    if goal.target_date < request.week_start:
        return _blocked_draft(
            request,
            input_hash,
            evidence,
            "目标日期早于待规划训练周，需先更新或结束目标。",
            "goal_target_date_passed",
        )
    if goal.target_date <= request.week_start + timedelta(days=6):
        return _blocked_draft(
            request,
            input_hash,
            evidence,
            "v1 不自动生成比赛周减量与比赛方案，请人工确认比赛安排。",
            "event_week_requires_manual_plan",
        )

    available_dates = [
        request.week_start + timedelta(days=WEEKDAY_INDEX[item])
        for item in goal.available_weekdays
    ]
    if request.week_start <= request.as_of.date() <= request.week_start + timedelta(days=6):
        available_dates = [item for item in available_dates if item >= request.as_of.date()]
    available_dates = sorted(set(available_dates))
    if not available_dates:
        return _blocked_draft(
            request,
            input_hash,
            evidence,
            "本周剩余时间没有可训练日期，不能生成有效草案。",
            "no_available_training_day",
        )

    selected_dates = _select_spaced_dates(available_dates, limit=3)
    baseline_seconds = sum(item.duration_seconds for item in relevant) / (
        request.lookback_days / 7
    )
    sufficient_history = len(relevant) >= 3 and baseline_seconds >= 45 * 60
    warnings: list[str] = []
    if sufficient_history:
        total_seconds = _round_to_five_minutes(baseline_seconds * 1.05)
        total_seconds = max(total_seconds, 45 * 60)
        rationale = (
            "按最近历史周均时长生成，并使用 RunCrew v1 的 5% 保守增量上限；"
            "训练日优先拉开间隔。"
        )
    else:
        total_seconds = {1: 30, 2: 60, 3: 70}[len(selected_dates)] * 60
        rationale = (
            "历史训练不足以可靠推算负荷，采用 RunCrew v1 入门保守时长模板，"
            "不安排间歇或节奏训练。"
        )
        warnings.append("近期规范化活动不足，草案置信度较低；确认前请补充当前周跑量。")
    allocations = _allocate_minutes(total_seconds, len(selected_dates))
    sessions = _build_sessions(
        input_hash=input_hash,
        selected_dates=selected_dates,
        durations=allocations,
        allow_quality=(
            sufficient_history
            and len(relevant) >= 8
            and len(selected_dates) >= 3
            and (goal.target_date - request.week_start).days >= 28
        ),
    )
    total_duration = sum(item.duration_seconds or 0 for item in sessions)
    evidence.append(
        PlanningEvidence(
            id="rule:weekly_duration",
            type="engineering_rule",
            message="周时长采用版本化 RunCrew 保守规则，不是医学标准或个体化教练处方。",
            values={
                "baseline_weekly_duration_seconds": round(baseline_seconds),
                "planned_duration_seconds": total_duration,
                "sufficient_history": sufficient_history,
                "increase_cap_ratio": 0.05 if sufficient_history else None,
            },
            rule_source="runcrew_conservative_rule",
        )
    )
    return TrainingPlanningResult(
        operation="draft_week",
        input_hash=input_hash,
        goal_id=goal.id,
        status="ready",
        summary="已生成待用户确认的周计划草案；未写入数据库。",
        weekly_plan_draft=WeeklyPlanDraft(
            goal_id=goal.id,
            week_start=request.week_start,
            sessions=sessions,
            total_duration_seconds=total_duration,
            rationale=rationale,
        ),
        evidence=evidence,
        warnings=warnings,
    )


def execute_plan_adjustment(
    request: PlanAdjustmentRequest,
    *,
    goals: PlanningGoalStore,
    plans: PlanningPlanStore,
) -> TrainingPlanningResult:
    goal = _require_active_goal(goals, request.goal_id)
    assessed_day = request.assessed_at.date()
    week_start = assessed_day - timedelta(days=assessed_day.weekday())
    active_plans = plans.active_from_week(goal.id, week_start, limit=8)
    target_id = request.plan_action.target_session_id
    matched = [
        (plan, session)
        for plan in active_plans
        for session in plan.sessions
        if session.id == target_id
    ]
    plan, session = matched[0] if len(matched) == 1 else (None, None)
    return build_plan_adjustment(
        request,
        goal=goal,
        active_plan=plan,
        target_session=session,
    )


def adjustment_request_from_recovery(
    result: RecoveryAssessmentResult,
) -> PlanAdjustmentRequest:
    return PlanAdjustmentRequest(
        goal_id=result.goal_id,
        assessed_at=result.assessed_at,
        recovery_input_hash=result.input_hash,
        recovery_recommendation=result.recommendation,
        plan_action=result.plan_action,
        evidence_refs=[item.id for item in result.evidence],
    )


def build_plan_adjustment(
    request: PlanAdjustmentRequest,
    *,
    goal: TrainingGoal,
    active_plan: TrainingPlan | None,
    target_session: PlanSession | None,
) -> TrainingPlanningResult:
    input_hash = _hash_payload(
        {
            "request": request.model_dump(mode="json"),
            "goal": _goal_features(goal),
            "active_plan": active_plan.model_dump(mode="json") if active_plan else None,
            "target_session": (
                target_session.model_dump(mode="json") if target_session else None
            ),
        }
    )
    snapshot = RecoveryAssessmentSnapshot(
        input_hash=request.recovery_input_hash,
        recommendation=request.recovery_recommendation,
        plan_action=request.plan_action,
    )
    evidence = [
        PlanningEvidence(
            id=f"recovery:{request.recovery_input_hash}",
            type="recovery_action",
            message="计划调整只消费已经校验的恢复评估动作，不重新判断健康风险。",
            values={
                "recommendation": request.recovery_recommendation,
                "action": request.plan_action.action,
                "target_session_id": request.plan_action.target_session_id,
            },
            rule_source="recovery_assessment",
        )
    ]
    action = request.plan_action.action
    if action == "keep":
        return TrainingPlanningResult(
            operation="adjust_from_recovery",
            input_hash=input_hash,
            goal_id=goal.id,
            status="no_change",
            summary="恢复评估建议保持原计划，因此不生成变更提案。",
            source_recovery_assessment=snapshot,
            evidence=evidence,
        )
    if action in {"wait_for_more_data", "hold_until_professional_review"}:
        missing = (
            ["fresh_recovery_data"]
            if action == "wait_for_more_data"
            else ["professional_review"]
        )
        summary = (
            "恢复数据不足，计划 Agent 不生成调整提案。"
            if action == "wait_for_more_data"
            else "存在升级风险；专业评估前停止自动生成训练调整。"
        )
        return TrainingPlanningResult(
            operation="adjust_from_recovery",
            input_hash=input_hash,
            goal_id=goal.id,
            status="blocked",
            summary=summary,
            source_recovery_assessment=snapshot,
            evidence=evidence,
            missing_data=missing,
        )
    if active_plan is None or target_session is None:
        evidence.append(
            PlanningEvidence(
                id="missing:active_target_session",
                type="missing_data",
                message="恢复动作引用的计划课不在可见的激活计划中。",
                values={"target_session_id": request.plan_action.target_session_id},
                rule_source="missing_data_policy",
            )
        )
        return TrainingPlanningResult(
            operation="adjust_from_recovery",
            input_hash=input_hash,
            goal_id=goal.id,
            status="blocked",
            summary="找不到恢复动作引用的激活计划课，不能生成变更提案。",
            source_recovery_assessment=snapshot,
            evidence=evidence,
            missing_data=["active_target_session"],
        )
    if target_session.scheduled_for < request.assessed_at.date():
        return TrainingPlanningResult(
            operation="adjust_from_recovery",
            input_hash=input_hash,
            goal_id=goal.id,
            status="blocked",
            summary="目标计划课早于恢复评估日期，不能生成追溯性调整提案。",
            source_recovery_assessment=snapshot,
            evidence=evidence,
            missing_data=["future_target_session"],
        )
    if target_session.status != "planned":
        return TrainingPlanningResult(
            operation="adjust_from_recovery",
            input_hash=input_hash,
            goal_id=goal.id,
            status="blocked",
            summary="目标计划课已完成或已跳过，不能再生成调整提案。",
            source_recovery_assessment=snapshot,
            evidence=evidence,
            missing_data=["modifiable_planned_session"],
        )
    if target_session.session_type == "rest":
        return TrainingPlanningResult(
            operation="adjust_from_recovery",
            input_hash=input_hash,
            goal_id=goal.id,
            status="no_change",
            summary="目标课已经是休息日，无需生成进一步降级提案。",
            source_recovery_assessment=snapshot,
            evidence=evidence,
        )

    if action == "ask_plan_agent_to_replace_with_rest":
        patch = PlanSessionPatch(
            session_id=target_session.id,
            session_type="rest",
            clear_distance=True,
            clear_duration=True,
            clear_intensity=True,
            purpose="恢复风险评估建议本次休息；等待用户确认。",
        )
        reason = "根据恢复评估生成把目标训练课改为休息的待确认提案。"
    else:
        patch = _reduction_patch(target_session)
        reason = "根据恢复评估生成降低目标训练课负荷的待确认提案。"
    refs = sorted(set(request.evidence_refs + [f"recovery:{request.recovery_input_hash}"]))
    evidence.append(
        PlanningEvidence(
            id=f"plan:{active_plan.id}:revision:{active_plan.revision}",
            type="current_plan",
            message="提案绑定当前激活计划及其 revision，过期提案不能套用。",
            values={
                "plan_id": active_plan.id,
                "base_revision": active_plan.revision,
                "session_id": target_session.id,
            },
            rule_source="active_plan",
        )
    )
    return TrainingPlanningResult(
        operation="adjust_from_recovery",
        input_hash=input_hash,
        goal_id=goal.id,
        status="ready",
        summary="已生成待用户确认的调整提案参数；未保存、未批准、未修改计划。",
        change_proposal_draft=PlanChangeProposalDraft(
            plan_id=active_plan.id,
            base_revision=active_plan.revision,
            reason=reason,
            changes=[patch],
            evidence_refs=refs,
        ),
        source_recovery_assessment=snapshot,
        evidence=evidence,
    )


def _require_active_goal(store: PlanningGoalStore, goal_id: str) -> TrainingGoal:
    goal = store.get(goal_id)
    if goal is None or goal.status != "active":
        raise TrainingPlanningError("训练目标不存在或当前未激活")
    return goal


def _blocked_draft(
    request: WeeklyPlanDraftRequest,
    input_hash: str,
    evidence: list[PlanningEvidence],
    summary: str,
    missing: str,
) -> TrainingPlanningResult:
    evidence.append(
        PlanningEvidence(
            id=f"missing:{missing}",
            type="missing_data",
            message=summary,
            values={"week_start": request.week_start.isoformat()},
            rule_source="missing_data_policy",
        )
    )
    return TrainingPlanningResult(
        operation="draft_week",
        input_hash=input_hash,
        goal_id=request.goal_id,
        status="blocked",
        summary=summary,
        evidence=evidence,
        missing_data=[missing],
    )


def _draft_evidence(
    request: WeeklyPlanDraftRequest,
    goal: TrainingGoal,
    activities: list[Activity],
) -> list[PlanningEvidence]:
    return [
        PlanningEvidence(
            id=f"goal:{goal.id}",
            type="goal",
            message="训练目标和可训练日期来自用户已保存的结构化声明。",
            values={
                "event_type": goal.event_type,
                "target_date": goal.target_date.isoformat(),
                "target_time_seconds": goal.target_time_seconds,
            },
            rule_source="user_goal",
        ),
        PlanningEvidence(
            id="availability:weekly",
            type="availability",
            message="只在用户声明的可训练星期中安排训练。",
            values={"available_weekdays": goal.available_weekdays},
            rule_source="user_goal",
        ),
        PlanningEvidence(
            id=f"history:{request.lookback_days}d",
            type="training_history",
            message="历史基线只使用知识截止时间之前的规范化活动。",
            values={
                "activity_count": len(activities),
                "duration_seconds": sum(item.duration_seconds for item in activities),
                "provider": request.provider.value if request.provider else None,
            },
            rule_source=(
                "normalized_activity" if activities else "missing_data_policy"
            ),
        ),
    ]


def _select_spaced_dates(candidates: list[date], *, limit: int) -> list[date]:
    count = min(limit, len(candidates))
    if count <= 1:
        return candidates[:count]
    combinations = list(itertools.combinations(candidates, count))

    def score(items: tuple[date, ...]) -> tuple[int, int, tuple[int, ...]]:
        gaps = [(right - left).days for left, right in zip(items, items[1:])]
        return (
            min(gaps),
            (items[-1] - items[0]).days,
            tuple(-item.toordinal() for item in items),
        )

    return list(max(combinations, key=score))


def _round_to_five_minutes(seconds: float) -> int:
    return max(5 * 60, round(seconds / (5 * 60)) * 5 * 60)


def _allocate_minutes(total_seconds: int, count: int) -> list[int]:
    ratios = {1: [1.0], 2: [0.4, 0.6], 3: [0.3, 0.3, 0.4]}[count]
    durations = [_round_to_five_minutes(total_seconds * ratio) for ratio in ratios]
    difference = total_seconds - sum(durations)
    durations[-1] = max(5 * 60, durations[-1] + difference)
    return durations


def _build_sessions(
    *,
    input_hash: str,
    selected_dates: list[date],
    durations: list[int],
    allow_quality: bool,
) -> list[PlanSession]:
    result: list[PlanSession] = []
    for index, (scheduled_for, duration) in enumerate(zip(selected_dates, durations)):
        if index == len(selected_dates) - 1 and len(selected_dates) >= 2:
            session_type = "long_run"
            intensity = "低强度耐力，保持可完整交谈"
            purpose = "建立有氧耐力；按轻松体感完成，不追求目标配速。"
        elif allow_quality and index == 1:
            session_type = "tempo"
            intensity = "中等偏高但可控；不做冲刺，状态异常立即降级"
            purpose = "在已有连续训练基础上加入一次受控节奏刺激。"
        else:
            session_type = "easy"
            intensity = "轻松，可以完整交谈"
            purpose = "积累低强度跑步时间并观察恢复反应。"
        identifier = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"runcrew:{input_hash}:{scheduled_for.isoformat()}:{session_type}",
            )
        )
        result.append(
            PlanSession(
                id=identifier,
                scheduled_for=scheduled_for,
                session_type=session_type,
                duration_seconds=duration,
                intensity=intensity,
                purpose=purpose,
            )
        )
    return result


def _reduction_patch(session: PlanSession) -> PlanSessionPatch:
    updates: dict = {
        "session_id": session.id,
        "session_type": "recovery",
        "intensity": "低强度，保持可完整交谈；不做速度目标",
        "purpose": "根据恢复评估降低本次训练负荷；等待用户确认。",
    }
    if session.distance_meters is not None:
        updates["distance_meters"] = round(session.distance_meters * 0.6, 1)
    else:
        updates["clear_distance"] = True
    if session.duration_seconds is not None:
        updates["duration_seconds"] = max(5 * 60, round(session.duration_seconds * 0.6))
    else:
        updates["clear_duration"] = True
    return PlanSessionPatch(**updates)


def _hash_payload(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _goal_features(goal: TrainingGoal) -> dict:
    return {
        "id": goal.id,
        "event_type": goal.event_type,
        "target_date": goal.target_date.isoformat(),
        "target_time_seconds": goal.target_time_seconds,
        "available_weekdays": sorted(goal.available_weekdays),
        "status": goal.status,
    }


def _activity_features(activity: Activity) -> dict:
    return {
        "id": activity.id,
        "started_at": activity.started_at.isoformat(),
        "duration_seconds": activity.duration_seconds,
        "distance_meters": activity.distance_meters,
        "training_load": activity.training_load,
    }
