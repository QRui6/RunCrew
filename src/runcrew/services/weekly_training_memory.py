from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Protocol

from runcrew.domain.activity import ActivityDetail, ActivitySummary
from runcrew.domain.memory import (
    WeeklyTrainingMemory,
    WeeklyTrainingMemoryBuildRequest,
    WeeklyTrainingMemoryBuildResult,
)
from runcrew.domain.training_cycle import DailyCheckIn, PlanChangeProposal, TrainingPlan
from runcrew.domain.training_execution import TrainingExecutionConfirmation


Activity = ActivitySummary | ActivityDetail


class WeeklyTrainingMemoryError(ValueError):
    pass


class WeeklyMemoryPlanStore(Protocol):
    def for_goal_week(self, goal_id: str, week_start: date) -> TrainingPlan | None: ...


class WeeklyMemoryConfirmationStore(Protocol):
    def for_plan(self, plan_id: str) -> list[TrainingExecutionConfirmation]: ...


class WeeklyMemoryActivityStore(Protocol):
    def get_by_id(self, activity_id: str) -> Activity | None: ...


class WeeklyMemoryCheckInStore(Protocol):
    def between(self, start: date, end: date) -> list[DailyCheckIn]: ...


class WeeklyMemoryPlanChangeStore(Protocol):
    def for_plan(self, plan_id: str) -> list[PlanChangeProposal]: ...


class WeeklyMemoryStore(Protocol):
    def current_for_week(
        self, goal_id: str, week_start: date
    ) -> WeeklyTrainingMemory | None: ...

    def save(self, memory: WeeklyTrainingMemory) -> None: ...

    def get(self, memory_id: str) -> WeeklyTrainingMemory | None: ...

    def latest_for_week(
        self, goal_id: str, week_start: date
    ) -> WeeklyTrainingMemory | None: ...


def refresh_weekly_training_memory(
    request: WeeklyTrainingMemoryBuildRequest,
    *,
    plans: WeeklyMemoryPlanStore,
    confirmations: WeeklyMemoryConfirmationStore,
    activities: WeeklyMemoryActivityStore,
    check_ins: WeeklyMemoryCheckInStore,
    plan_changes: WeeklyMemoryPlanChangeStore,
    memories: WeeklyMemoryStore,
) -> WeeklyTrainingMemoryBuildResult:
    plan = plans.for_goal_week(request.goal_id, request.week_start)
    if plan is None or plan.status == "draft":
        raise WeeklyTrainingMemoryError("该训练周没有可结算的正式计划。")
    if plan.updated_at > request.as_of:
        raise WeeklyTrainingMemoryError("计划包含评估时点之后的变更，不能用于历史回放。")
    week_end = request.week_start + timedelta(days=6)
    if request.as_of.date() <= week_end:
        raise WeeklyTrainingMemoryError("训练周尚未结束，不能生成正式周训练记忆。")

    applied_confirmations = [
        item
        for item in confirmations.for_plan(plan.id)
        if item.status == "applied" and item.created_at <= request.as_of
    ]
    latest_by_session: dict[str, TrainingExecutionConfirmation] = {}
    for item in sorted(applied_confirmations, key=lambda value: (value.created_at, value.id)):
        latest_by_session[item.session_id] = item

    sessions = [item for item in plan.sessions if item.session_type != "rest"]
    completed = 0
    skipped = 0
    confirmed_activities: list[Activity] = []
    missing_data: set[str] = set()
    used_confirmations: list[TrainingExecutionConfirmation] = []
    for session in sessions:
        confirmation = latest_by_session.get(session.id)
        if confirmation is None or confirmation.decision == "clear_execution":
            continue
        used_confirmations.append(confirmation)
        if confirmation.decision == "mark_skipped":
            skipped += 1
            continue
        assert confirmation.activity_id is not None
        activity = activities.get_by_id(confirmation.activity_id)
        if activity is None or activity.started_at > request.as_of:
            missing_data.add(f"activity:{confirmation.activity_id}")
            continue
        if activity.distance_meters is None:
            missing_data.add(f"activity_distance:{activity.id}")
        completed += 1
        confirmed_activities.append(activity)

    unresolved = len(sessions) - completed - skipped
    if unresolved:
        missing_data.add("unresolved_execution")

    week_check_ins = [
        item
        for item in check_ins.between(request.week_start, week_end)
        if item.created_at <= request.as_of
    ]
    if not week_check_ins:
        missing_data.add("check_ins")
    readiness_values = [
        item.readiness for item in week_check_ins if item.readiness is not None
    ]

    approved_changes = [
        item
        for item in plan_changes.for_plan(plan.id)
        if item.status == "approved"
        and item.decided_at is not None
        and item.decided_at <= request.as_of
    ]
    payload = {
        # as_of 只限制可见事实，不直接进入 Hash；稍后用相同事实刷新时，
        # 不应仅因时钟变化制造没有业务意义的新版本。
        "request": {
            "goal_id": request.goal_id,
            "week_start": request.week_start.isoformat(),
        },
        "plan": plan.model_dump(mode="json"),
        "confirmations": [
            item.model_dump(mode="json") for item in used_confirmations
        ],
        "activities": [
            _activity_features(item) for item in confirmed_activities
        ],
        "check_ins": [item.model_dump(mode="json") for item in week_check_ins],
        "approved_plan_changes": [
            item.model_dump(mode="json") for item in approved_changes
        ],
    }
    input_hash = _hash_payload(payload)
    current = memories.current_for_week(request.goal_id, request.week_start)
    if current is not None and current.input_hash == input_hash:
        return WeeklyTrainingMemoryBuildResult(outcome="unchanged", memory=current)

    latest = memories.latest_for_week(request.goal_id, request.week_start)
    version = latest.version + 1 if latest is not None else 1
    memory_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"runcrew:weekly-memory:{request.goal_id}:{request.week_start}:{version}:{input_hash}",
        )
    )
    completion_rate = completed / len(sessions) if sessions else None
    actual_duration = sum(item.duration_seconds for item in confirmed_activities)
    actual_distance = sum(item.distance_meters or 0 for item in confirmed_activities)
    source_refs = [f"plan:{plan.id}@revision:{plan.revision}"]
    source_refs.extend(f"confirmation:{item.id}" for item in used_confirmations)
    source_refs.extend(f"activity:{item.id}" for item in confirmed_activities)
    source_refs.extend(f"check-in:{item.id}" for item in week_check_ins)
    source_refs.extend(f"plan-change:{item.id}" for item in approved_changes)
    memory = WeeklyTrainingMemory(
        id=memory_id,
        goal_id=request.goal_id,
        plan_id=plan.id,
        week_start=request.week_start,
        week_end=week_end,
        version=version,
        plan_revision=plan.revision,
        input_hash=input_hash,
        planned_sessions=len(sessions),
        confirmed_completed_sessions=completed,
        confirmed_skipped_sessions=skipped,
        unresolved_sessions=unresolved,
        completion_rate=completion_rate,
        planned_duration_seconds=sum(
            item.duration_seconds or 0 for item in sessions
        ),
        actual_duration_seconds=actual_duration,
        actual_distance_meters=actual_distance,
        check_in_days=len(week_check_ins),
        average_fatigue=_average([item.fatigue for item in week_check_ins]),
        average_soreness=_average([item.soreness for item in week_check_ins]),
        average_sleep_quality=_average(
            [item.sleep_quality for item in week_check_ins]
        ),
        average_readiness=_average(readiness_values),
        max_pain_severity=(
            max(item.pain_severity for item in week_check_ins)
            if week_check_ins
            else None
        ),
        acute_symptom_days=sum(bool(item.acute_symptoms) for item in week_check_ins),
        approved_plan_changes=len(approved_changes),
        summary=_summary(len(sessions), completed, skipped, unresolved, len(week_check_ins)),
        missing_data=sorted(missing_data),
        source_refs=sorted(set(source_refs)),
        supersedes_id=latest.id if latest is not None else None,
        generated_at=request.as_of,
        updated_at=request.as_of,
    )
    if current is not None:
        current.status = "superseded"
        current.updated_at = request.as_of
        memories.save(current)
    memories.save(memory)
    return WeeklyTrainingMemoryBuildResult(
        outcome="superseded" if latest is not None else "created",
        memory=memory,
    )


def invalidate_weekly_training_memory(
    memory_id: str,
    *,
    memories: WeeklyMemoryStore,
    now: datetime,
) -> WeeklyTrainingMemory:
    if now.tzinfo is None or now.utcoffset() is None:
        raise WeeklyTrainingMemoryError("失效时间必须包含时区。")
    memory = memories.get(memory_id)
    if memory is None:
        raise WeeklyTrainingMemoryError("周训练记忆不存在。")
    if memory.status != "active":
        raise WeeklyTrainingMemoryError("只有当前生效的周训练记忆可以失效。")
    if now < memory.generated_at:
        raise WeeklyTrainingMemoryError("失效时间不能早于周训练记忆生成时间。")
    memory.status = "invalidated"
    memory.invalidated_at = now
    memory.updated_at = now
    memories.save(memory)
    return memory


def _activity_features(activity: Activity) -> dict[str, object]:
    return {
        "id": activity.id,
        "started_at": activity.started_at.isoformat(),
        "duration_seconds": activity.duration_seconds,
        "distance_meters": activity.distance_meters,
        "provider": activity.source_ref.provider.value,
        "raw_payload_hash": activity.source_ref.raw_payload_hash,
    }


def _hash_payload(payload: dict[str, object]) -> str:
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _average(values: list[int]) -> float | None:
    return round(mean(values), 2) if values else None


def _summary(
    planned: int,
    completed: int,
    skipped: int,
    unresolved: int,
    check_in_days: int,
) -> str:
    return (
        f"本周计划{planned}节，已确认完成{completed}节、跳过{skipped}节、"
        f"待核对{unresolved}节；记录身体反馈{check_in_days}天。"
    )
