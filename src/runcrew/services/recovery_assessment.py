from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Protocol

from runcrew.domain.activity import ActivityDetail, ActivitySummary
from runcrew.domain.recovery_assessment import (
    RecoveryAssessmentRequest,
    RecoveryAssessmentResult,
    RecoveryEvidence,
    RecoveryPlanAction,
)
from runcrew.domain.training_cycle import DailyCheckIn, PlanSession, TrainingPlan
from runcrew.domain.training_cycle import TrainingGoal
from runcrew.services.recovery_context import (
    RecoveryAssessmentContext,
    build_recovery_context,
)


Activity = ActivitySummary | ActivityDetail
CARDIOPULMONARY_RED_FLAGS = {
    "chest_pain_or_pressure",
    "fainting_or_severe_dizziness",
    "unusual_or_severe_shortness_of_breath",
    "new_irregular_heartbeat",
}
STOP_AND_REST_FLAGS = {
    "fever_or_acute_illness",
    "sudden_pain_swelling_or_redness",
}


class RecoveryAssessmentActivityStore(Protocol):
    def between(
        self,
        start: datetime,
        end: datetime,
        *,
        provider: str | None = None,
    ) -> list[Activity]: ...


class RecoveryAssessmentCheckInStore(Protocol):
    def between(self, start: date, end: date) -> list[DailyCheckIn]: ...


class RecoveryAssessmentPlanStore(Protocol):
    def active_from_week(
        self, goal_id: str, week_start: date, *, limit: int = 2
    ) -> list[TrainingPlan]: ...


class RecoveryAssessmentGoalStore(Protocol):
    def get(self, goal_id: str) -> TrainingGoal | None: ...


class RecoveryAssessmentGoalNotFoundError(LookupError):
    pass


def execute_recovery_assessment(
    request: RecoveryAssessmentRequest,
    *,
    activities: RecoveryAssessmentActivityStore,
    check_ins: RecoveryAssessmentCheckInStore,
    plans: RecoveryAssessmentPlanStore,
    goals: RecoveryAssessmentGoalStore,
) -> RecoveryAssessmentResult:
    goal = goals.get(request.goal_id)
    if goal is None or goal.status != "active":
        raise RecoveryAssessmentGoalNotFoundError("训练目标不存在或当前未激活")
    history = activities.between(
        request.assessed_at - timedelta(days=request.lookback_days),
        request.assessed_at,
        provider=request.provider.value if request.provider is not None else None,
    )
    recent_check_ins = check_ins.between(
        (request.assessed_at - timedelta(days=request.lookback_days)).date(),
        request.assessed_at.date(),
    )
    assessed_day = request.assessed_at.date()
    week_start = assessed_day - timedelta(days=assessed_day.weekday())
    relevant_plans = plans.active_from_week(request.goal_id, week_start, limit=2)
    next_session = _next_planned_session(relevant_plans, request.assessed_at.date())
    context = build_recovery_context(
        request,
        activities=history,
        check_ins=recent_check_ins,
        next_session=next_session,
    )
    return build_recovery_assessment(context)


def build_recovery_assessment(
    context: RecoveryAssessmentContext,
) -> RecoveryAssessmentResult:
    latest = context.check_ins[-1] if context.check_ins else None
    missing: list[str] = []
    evidence: list[RecoveryEvidence] = []
    if latest is None:
        missing.append("recent_check_in")
        evidence.append(
            RecoveryEvidence(
                id="missing:recent_check_in",
                type="missing_data",
                message="缺少最近主观身体反馈，不能判断当前恢复状态。",
                values={"requires": "fatigue, soreness, sleep_quality, pain"},
                rule_source="missing_data_policy",
            )
        )
    else:
        evidence.extend(_check_in_evidence(latest))
        if latest.day < context.request.assessed_at.date() - timedelta(days=1):
            missing.append("fresh_check_in")
            evidence.append(
                RecoveryEvidence(
                    id="missing:fresh_check_in",
                    type="missing_data",
                    message="最近身体反馈早于评估日前一天，不能代表当前状态。",
                    values={
                        "latest_check_in_day": latest.day.isoformat(),
                        "assessed_day": context.request.assessed_at.date().isoformat(),
                    },
                    rule_source="missing_data_policy",
                )
            )

    if context.next_session is None:
        missing.append("next_planned_session")
        evidence.append(
            RecoveryEvidence(
                id="missing:next_planned_session",
                type="missing_data",
                message="缺少下一次计划课，无法生成具体课表调整目标。",
                values={"requires": "active plan with a future planned session"},
                rule_source="missing_data_policy",
            )
        )
    else:
        evidence.append(
            RecoveryEvidence(
                id=f"plan_session:{context.next_session.id}",
                type="planned_session",
                message="已找到下一次待执行计划课。",
                values={
                    "session_id": context.next_session.id,
                    "scheduled_for": context.next_session.scheduled_for.isoformat(),
                    "session_type": context.next_session.session_type,
                    "distance_meters": context.next_session.distance_meters,
                    "duration_seconds": context.next_session.duration_seconds,
                },
                rule_source="user_report",
            )
        )

    load_evidence = _load_evidence(context)
    evidence.append(load_evidence)
    if load_evidence.values.get("change_ratio") is None:
        missing.append("comparable_training_volume")

    recommendation, risk, summary = _recommendation(
        context,
        latest,
        check_in_is_fresh="fresh_check_in" not in missing,
    )
    action = _plan_action(
        recommendation=recommendation,
        next_session=context.next_session,
        missing=missing,
    )
    confidence = _confidence(recommendation, latest, missing)
    return RecoveryAssessmentResult(
        input_hash=context.input_hash,
        goal_id=context.request.goal_id,
        assessed_at=context.request.assessed_at,
        recommendation=recommendation,
        risk_level=risk,
        summary=summary,
        evidence=evidence,
        missing_data=sorted(set(missing)),
        confidence=confidence,
        current_7d=context.current_7d,
        previous_7d=context.previous_7d,
        plan_action=action,
    )


def _check_in_evidence(check_in: DailyCheckIn) -> list[RecoveryEvidence]:
    result = [
        RecoveryEvidence(
            id=f"check_in:{check_in.day.isoformat()}",
            type="check_in",
            message="使用最近一条用户主观身体反馈。",
            values={"day": check_in.day.isoformat()},
            rule_source="user_report",
        ),
        RecoveryEvidence(
            id=f"fatigue:{check_in.day.isoformat()}",
            type="fatigue",
            message="疲劳评分使用 RunCrew 1到5级保守阈值。",
            values={"fatigue": check_in.fatigue, "scale_max": 5},
            rule_source="runcrew_conservative_rule",
        ),
        RecoveryEvidence(
            id=f"sleep:{check_in.day.isoformat()}",
            type="sleep",
            message="睡眠质量使用 RunCrew 1到5级保守阈值。",
            values={"sleep_quality": check_in.sleep_quality, "scale_max": 5},
            rule_source="runcrew_conservative_rule",
        ),
        RecoveryEvidence(
            id=f"pain:{check_in.day.isoformat()}",
            type="pain",
            message="疼痛只作为用户报告的风险信号，不用于诊断。",
            values={
                "pain_area": check_in.pain_area,
                "pain_severity": check_in.pain_severity,
                "soreness": check_in.soreness,
            },
            rule_source="user_report",
        ),
    ]
    if check_in.readiness is not None:
        result.append(
            RecoveryEvidence(
                id=f"readiness:{check_in.day.isoformat()}",
                type="readiness",
                message="准备度是用户主观评分。",
                values={"readiness": check_in.readiness, "scale_max": 5},
                rule_source="user_report",
            )
        )
    for symptom in check_in.acute_symptoms:
        result.append(
            RecoveryEvidence(
                id=f"acute_symptom:{check_in.day.isoformat()}:{symptom}",
                type="acute_symptom",
                message="用户报告了运动安全红旗或应停止训练的急性症状。",
                values={"symptom": symptom},
                rule_source="exercise_safety_red_flag",
            )
        )
    return result


def _load_evidence(context: RecoveryAssessmentContext) -> RecoveryEvidence:
    current = context.current_7d.training_load_total
    previous = context.previous_7d.training_load_total
    method, change = _load_change(context)
    return RecoveryEvidence(
        id="training_volume:7d_vs_previous_7d",
        type="training_volume",
        message=(
            "七天训练量变化使用 RunCrew 保守阈值。"
            if change is not None
            else "缺少连续两个七天窗口的可比较训练量。"
        ),
        values={
            "current_7d": current,
            "previous_7d": previous,
            "change_ratio": round(change, 4) if change is not None else None,
            "method": method,
            "current_duration_seconds": context.current_7d.duration_seconds,
            "previous_duration_seconds": context.previous_7d.duration_seconds,
            "current_coverage": round(context.current_7d.training_load_coverage, 4),
            "previous_coverage": round(context.previous_7d.training_load_coverage, 4),
        },
        rule_source=(
            "runcrew_conservative_rule"
            if change is not None
            else "missing_data_policy"
        ),
    )


def _recommendation(
    context: RecoveryAssessmentContext,
    latest: DailyCheckIn | None,
    *,
    check_in_is_fresh: bool,
) -> tuple[str, str, str]:
    if latest is None:
        return (
            "insufficient_data",
            "unknown",
            "缺少足够新的身体反馈，当前不能判断是否适合按原计划训练。",
        )
    symptoms = set(latest.acute_symptoms)
    if symptoms & CARDIOPULMONARY_RED_FLAGS:
        return (
            "seek_professional_help",
            "escalate",
            "存在需要停止训练建议并寻求专业评估的风险信号。",
        )
    if not check_in_is_fresh:
        return (
            "insufficient_data",
            "unknown",
            "缺少足够新的身体反馈，当前不能判断是否适合按原计划训练。",
        )
    if latest.pain_severity >= 8:
        return (
            "seek_professional_help",
            "escalate",
            "当前严重疼痛评分达到停止自动训练建议并寻求专业评估的阈值。",
        )
    if symptoms & STOP_AND_REST_FLAGS or latest.pain_severity >= 5:
        return (
            "rest",
            "high",
            "当前风险信号不适合继续原训练课，建议先休息并观察。",
        )
    if latest.fatigue == 5 or (
        latest.fatigue >= 4 and latest.sleep_quality <= 2
    ):
        return (
            "rest",
            "high",
            "高疲劳与较差睡眠组合达到 RunCrew 的保守休息阈值。",
        )
    _, load_change = _load_change(context)
    moderate_signals = sum(
        (
            latest.pain_severity >= 3,
            latest.soreness >= 6,
            latest.fatigue >= 4,
            latest.sleep_quality <= 2,
            latest.readiness is not None and latest.readiness <= 2,
            load_change is not None and load_change > 0.3,
        )
    )
    if moderate_signals >= 1:
        return (
            "reduce",
            "moderate",
            "至少一项恢复或训练负荷信号达到保守降级阈值。",
        )
    return (
        "proceed",
        "low",
        "现有主观反馈未触发当前规则的休息、降级或升级阈值。",
    )


def _load_change(context: RecoveryAssessmentContext) -> tuple[str | None, float | None]:
    current = context.current_7d.training_load_total
    previous = context.previous_7d.training_load_total
    if (
        current is None
        or previous is None
        or previous <= 0
        or context.current_7d.training_load_coverage < 0.8
        or context.previous_7d.training_load_coverage < 0.8
    ):
        if context.previous_7d.duration_seconds <= 0:
            return None, None
        return (
            "duration_seconds_proxy",
            context.current_7d.duration_seconds
            / context.previous_7d.duration_seconds
            - 1,
        )
    return "training_load_total", current / previous - 1


def _plan_action(
    *,
    recommendation: str,
    next_session: PlanSession | None,
    missing: list[str],
) -> RecoveryPlanAction:
    target_id = next_session.id if next_session else None
    mapping = {
        "proceed": ("keep", "保持当前课表，不产生写入操作。"),
        "reduce": (
            "ask_plan_agent_to_reduce",
            "请求计划 Agent 生成降级提案，仍需用户确认。",
        ),
        "rest": (
            "ask_plan_agent_to_replace_with_rest",
            "请求计划 Agent 生成改为休息的提案，仍需用户确认。",
        ),
        "seek_professional_help": (
            "hold_until_professional_review",
            "停止自动训练建议，在专业评估前不执行原计划。",
        ),
        "insufficient_data": (
            "wait_for_more_data",
            "补充最近身体反馈后重新评估。",
        ),
    }
    action, reason = mapping[recommendation]
    if next_session is None and action in {
        "ask_plan_agent_to_reduce",
        "ask_plan_agent_to_replace_with_rest",
    }:
        action = "wait_for_more_data"
        reason = "缺少下一次计划课，先补充课表再生成调整提案。"
    return RecoveryPlanAction(
        action=action,
        target_session_id=target_id,
        requires_user_confirmation=action != "keep",
        reason=reason,
    )


def _confidence(
    recommendation: str, latest: DailyCheckIn | None, missing: list[str]
) -> str:
    if latest is None:
        return "low"
    if recommendation == "seek_professional_help":
        return "high"
    critical_missing = {"next_planned_session", "comparable_training_volume"}
    count = len(set(missing) & critical_missing)
    return "high" if count == 0 else "medium" if count == 1 else "low"


def _next_planned_session(
    plans: list[TrainingPlan], assessed_day: date
) -> PlanSession | None:
    candidates = [
        item
        for plan in plans
        for item in plan.sessions
        if item.status == "planned" and item.scheduled_for >= assessed_day
    ]
    return min(candidates, key=lambda item: (item.scheduled_for, item.id)) if candidates else None
