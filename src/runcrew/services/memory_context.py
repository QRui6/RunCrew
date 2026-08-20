from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from runcrew.domain.memory import (
    AgentMemoryContext,
    AthletePreference,
    MemoryContextBudget,
    MemoryContextBuildRequest,
    MemoryContextDecision,
    PlanWeeklyMemoryContextItem,
    PreferenceMemoryContextItem,
    RecoveryWeeklyMemoryContextItem,
    WeeklyMemoryContextItem,
    WeeklyTrainingMemory,
)


@dataclass(frozen=True, slots=True)
class MemoryContextPolicy:
    max_items: int
    max_chars: int


ROLE_POLICIES = {
    "execution": MemoryContextPolicy(max_items=0, max_chars=0),
    "recovery": MemoryContextPolicy(max_items=2, max_chars=1400),
    "plan": MemoryContextPolicy(max_items=5, max_chars=1800),
}


class MemoryContextPreferenceStore(Protocol):
    def list(self, *, limit: int = 50) -> list[AthletePreference]: ...


class MemoryContextWeeklyStore(Protocol):
    def list_for_goal(
        self, goal_id: str, *, include_inactive: bool = False, limit: int = 20
    ) -> list[WeeklyTrainingMemory]: ...


def load_agent_memory_context(
    request: MemoryContextBuildRequest,
    *,
    preferences: MemoryContextPreferenceStore | None,
    weekly_memories: MemoryContextWeeklyStore | None,
) -> AgentMemoryContext:
    return build_agent_memory_context(
        request,
        preferences=preferences.list(limit=50) if preferences is not None else [],
        weekly_memories=(
            weekly_memories.list_for_goal(
                request.goal_id, include_inactive=True, limit=50
            )
            if weekly_memories is not None
            else []
        ),
    )


def build_agent_memory_context(
    request: MemoryContextBuildRequest,
    *,
    preferences: list[AthletePreference],
    weekly_memories: list[WeeklyTrainingMemory],
    policy: MemoryContextPolicy | None = None,
) -> AgentMemoryContext:
    configured = policy or ROLE_POLICIES[request.role]
    decisions: list[MemoryContextDecision] = []
    eligible: list[tuple[str, object, str]] = []

    ordered_preferences = sorted(
        preferences,
        key=lambda item: (item.key, item.updated_at, item.id),
        reverse=True,
    )
    for item in ordered_preferences:
        reason = _preference_exclusion(request, item)
        if reason is not None:
            decisions.append(_excluded("athlete_preference", item.id, item.status, reason))
            continue
        projection = PreferenceMemoryContextItem(
            memory_id=item.id,
            key=item.key,
            value=item.value,
            schema_version=item.schema_version,
        )
        eligible.append(("athlete_preference", projection, item.status))

    ordered_weekly = sorted(
        weekly_memories,
        key=lambda item: (item.week_start, item.version, item.id),
        reverse=True,
    )
    for item in ordered_weekly:
        reason = _weekly_exclusion(request, item)
        if reason is not None:
            decisions.append(
                _excluded("weekly_training_memory", item.id, item.status, reason)
            )
            continue
        projection = _weekly_projection(request.role, item)
        eligible.append(("weekly_training_memory", projection, item.status))

    selected_preferences: list[PreferenceMemoryContextItem] = []
    selected_weekly: list[WeeklyMemoryContextItem] = []
    used_chars = 0
    excluded_by_budget = 0
    for memory_type, projection, status in eligible:
        estimated = _estimated_chars(projection)
        if len(selected_preferences) + len(selected_weekly) >= configured.max_items:
            decisions.append(
                _excluded(
                    memory_type,
                    projection.memory_id,
                    status,
                    "excluded_item_budget",
                    estimated,
                )
            )
            excluded_by_budget += 1
            continue
        if used_chars + estimated > configured.max_chars:
            decisions.append(
                _excluded(
                    memory_type,
                    projection.memory_id,
                    status,
                    "excluded_character_budget",
                    estimated,
                )
            )
            excluded_by_budget += 1
            continue
        selected_order = len(selected_preferences) + len(selected_weekly) + 1
        decisions.append(
            MemoryContextDecision(
                memory_type=memory_type,
                memory_id=projection.memory_id,
                status=status,
                selected=True,
                reason="selected_role_relevant",
                selected_order=selected_order,
                estimated_chars=estimated,
            )
        )
        used_chars += estimated
        if isinstance(projection, PreferenceMemoryContextItem):
            selected_preferences.append(projection)
        else:
            selected_weekly.append(projection)

    budget = MemoryContextBudget(
        max_items=configured.max_items,
        max_chars=configured.max_chars,
        used_items=len(selected_preferences) + len(selected_weekly),
        used_chars=used_chars,
        candidate_count=len(preferences) + len(weekly_memories),
        excluded_by_budget=excluded_by_budget,
    )
    selected_payload = {
        "selection_policy_version": "memory-context-policy/1.0",
        "role": request.role,
        "goal_id": request.goal_id,
        "as_of": request.as_of.isoformat(),
        "target_week_start": (
            request.target_week_start.isoformat() if request.target_week_start else None
        ),
        "selected_preferences": [
            item.model_dump(mode="json") for item in selected_preferences
        ],
        "selected_weekly_memories": [
            item.model_dump(mode="json") for item in selected_weekly
        ],
        "max_items": configured.max_items,
        "max_chars": configured.max_chars,
    }
    context_hash = _hash_payload(selected_payload)
    audit_hash = _hash_payload(
        {
            "context_hash": context_hash,
            "decisions": [item.model_dump(mode="json") for item in decisions],
            "budget": budget.model_dump(mode="json"),
        }
    )
    return AgentMemoryContext(
        role=request.role,
        goal_id=request.goal_id,
        as_of=request.as_of,
        target_week_start=request.target_week_start,
        context_hash=context_hash,
        audit_hash=audit_hash,
        selected_preferences=selected_preferences,
        selected_weekly_memories=selected_weekly,
        decisions=decisions,
        budget=budget,
    )


def _preference_exclusion(
    request: MemoryContextBuildRequest, preference: AthletePreference
) -> str | None:
    if request.role != "plan":
        return "excluded_role_not_allowed"
    if preference.status == "superseded":
        return "excluded_superseded"
    if preference.status == "archived":
        return "excluded_archived"
    if preference.status == "expired":
        return "excluded_expired"
    if preference.valid_from > request.as_of or preference.created_at > request.as_of:
        return "excluded_future"
    if preference.valid_until is not None and preference.valid_until <= request.as_of:
        return "excluded_expired"
    return None


def _weekly_exclusion(
    request: MemoryContextBuildRequest, memory: WeeklyTrainingMemory
) -> str | None:
    if memory.goal_id != request.goal_id:
        return "excluded_wrong_goal"
    if request.role == "execution":
        return "excluded_role_not_allowed"
    if memory.status == "superseded":
        return "excluded_superseded"
    if memory.status == "invalidated":
        return "excluded_invalidated"
    if memory.generated_at > request.as_of:
        return "excluded_future"
    boundary = request.target_week_start or request.as_of.date()
    if memory.week_end >= boundary:
        return "excluded_outside_target_window"
    return None


def _weekly_projection(
    role: str, memory: WeeklyTrainingMemory
) -> WeeklyMemoryContextItem:
    common = {
        "role": role,
        "memory_id": memory.id,
        "week_start": memory.week_start,
        "week_end": memory.week_end,
        "version": memory.version,
        "input_hash": memory.input_hash,
        "completion_rate": memory.completion_rate,
        "actual_duration_seconds": memory.actual_duration_seconds,
        "actual_distance_meters": memory.actual_distance_meters,
        "check_in_days": memory.check_in_days,
        "missing_data": memory.missing_data,
    }
    if role == "recovery":
        return RecoveryWeeklyMemoryContextItem(
            **common,
            average_fatigue=memory.average_fatigue,
            average_soreness=memory.average_soreness,
            average_readiness=memory.average_readiness,
            max_pain_severity=memory.max_pain_severity,
            acute_symptom_days=memory.acute_symptom_days,
        )
    return PlanWeeklyMemoryContextItem(**common)


def _excluded(
    memory_type: str,
    memory_id: str,
    status: str,
    reason: str,
    estimated_chars: int = 0,
) -> MemoryContextDecision:
    return MemoryContextDecision(
        memory_type=memory_type,
        memory_id=memory_id,
        status=status,
        selected=False,
        reason=reason,
        estimated_chars=estimated_chars,
    )


def _estimated_chars(value: object) -> int:
    return len(
        json.dumps(
            value.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _hash_payload(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
