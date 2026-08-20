from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from typer.testing import CliRunner

from runcrew.cli import app
from runcrew.domain.memory import (
    AgentMemoryContext,
    AthletePreference,
    MemoryContextBuildRequest,
    WeeklyTrainingMemory,
)
from runcrew.domain.training_cycle import TrainingGoal
from runcrew.domain.training_planning import WeeklyPlanDraftRequest
from runcrew.services.memory_context import (
    MemoryContextPolicy,
    build_agent_memory_context,
)
from runcrew.services.training_planning import build_weekly_plan_draft
from runcrew.storage.database import Database
from runcrew.storage.repositories import AthletePreferenceRepository


AS_OF = datetime(2026, 8, 20, 8, tzinfo=timezone.utc)
TARGET_WEEK = date(2026, 8, 24)


def preference(identifier: str = "preference-active", **updates) -> AthletePreference:
    values = {
        "id": identifier,
        "key": "preferred_long_run_weekday",
        "value": "sun",
        "source_ref": "settings:test",
        "confirmed_at": AS_OF - timedelta(days=20),
        "valid_from": AS_OF - timedelta(days=20),
        "created_at": AS_OF - timedelta(days=20),
        "updated_at": AS_OF - timedelta(days=20),
    }
    values.update(updates)
    return AthletePreference(**values)


def weekly(index: int, **updates) -> WeeklyTrainingMemory:
    week_start = date(2026, 8, 3) + timedelta(days=index * 7)
    values = {
        "id": f"weekly-{index}",
        "goal_id": "goal-1",
        "plan_id": f"plan-{index}",
        "week_start": week_start,
        "week_end": week_start + timedelta(days=6),
        "version": 1,
        "plan_revision": 2,
        "input_hash": str(index + 1) * 64,
        "planned_sessions": 3,
        "confirmed_completed_sessions": 2,
        "confirmed_skipped_sessions": 1,
        "unresolved_sessions": 0,
        "completion_rate": 2 / 3,
        "planned_duration_seconds": 6000,
        "actual_duration_seconds": 5200 + index * 100,
        "actual_distance_meters": 14000 + index * 1000,
        "check_in_days": 2,
        "average_fatigue": 3,
        "average_soreness": 2,
        "average_sleep_quality": 4,
        "average_readiness": 3.5,
        "max_pain_severity": 1,
        "acute_symptom_days": 0,
        "approved_plan_changes": 0,
        "summary": "合成周训练摘要。",
        "source_refs": [f"plan:plan-{index}@revision:2"],
        "generated_at": AS_OF - timedelta(days=2),
        "updated_at": AS_OF - timedelta(days=2),
    }
    values.update(updates)
    return WeeklyTrainingMemory(**values)


def request(role: str) -> MemoryContextBuildRequest:
    return MemoryContextBuildRequest(
        role=role,
        goal_id="goal-1",
        as_of=AS_OF,
        target_week_start=TARGET_WEEK if role == "plan" else None,
    )


def test_role_scoped_context_exposes_only_minimum_fields() -> None:
    memories = [weekly(0), weekly(1)]
    athlete_preference = preference()
    execution = build_agent_memory_context(
        request("execution"),
        preferences=[athlete_preference],
        weekly_memories=memories,
    )
    recovery = build_agent_memory_context(
        request("recovery"),
        preferences=[athlete_preference],
        weekly_memories=memories,
    )
    plan = build_agent_memory_context(
        request("plan"),
        preferences=[athlete_preference],
        weekly_memories=memories,
    )

    assert execution.budget.used_items == 0
    assert {item.reason for item in execution.decisions} == {
        "excluded_role_not_allowed"
    }
    assert recovery.selected_preferences == []
    assert len(recovery.selected_weekly_memories) == 2
    assert recovery.selected_weekly_memories[0].max_pain_severity == 1
    assert len(plan.selected_preferences) == 1
    assert len(plan.selected_weekly_memories) == 2
    plan_payload = plan.selected_weekly_memories[0].model_dump(mode="json")
    assert "max_pain_severity" not in plan_payload
    assert "average_fatigue" not in plan_payload


def test_future_expired_superseded_and_invalidated_memories_are_audited() -> None:
    invalidated = weekly(
        0,
        id="weekly-invalidated",
        status="invalidated",
        invalidated_at=AS_OF - timedelta(hours=1),
    )
    superseded = weekly(0, id="weekly-superseded", status="superseded")
    future = weekly(1, id="weekly-future", generated_at=AS_OF + timedelta(hours=1))
    wrong_goal = weekly(0, id="weekly-wrong-goal", goal_id="other-goal")
    expired = preference(
        "preference-expired",
        valid_until=AS_OF - timedelta(days=1),
    )
    archived = preference("preference-archived", status="archived")
    context = build_agent_memory_context(
        request("plan"),
        preferences=[expired, archived],
        weekly_memories=[invalidated, superseded, future, wrong_goal],
    )

    assert context.budget.used_items == 0
    reasons = {item.memory_id: item.reason for item in context.decisions}
    assert reasons["preference-expired"] == "excluded_expired"
    assert reasons["preference-archived"] == "excluded_archived"
    assert reasons["weekly-invalidated"] == "excluded_invalidated"
    assert reasons["weekly-superseded"] == "excluded_superseded"
    assert reasons["weekly-future"] == "excluded_future"
    assert reasons["weekly-wrong-goal"] == "excluded_wrong_goal"


def test_budget_is_enforced_and_excluded_records_do_not_change_context_hash() -> None:
    active = weekly(0)
    base = build_agent_memory_context(
        request("plan"), preferences=[], weekly_memories=[active]
    )
    with_irrelevant = build_agent_memory_context(
        request("plan"),
        preferences=[],
        weekly_memories=[
            active,
            weekly(
                0,
                id="ignored-invalidated",
                status="invalidated",
                invalidated_at=AS_OF - timedelta(hours=1),
            ),
        ],
    )
    constrained = build_agent_memory_context(
        request("plan"),
        preferences=[],
        weekly_memories=[active],
        policy=MemoryContextPolicy(max_items=1, max_chars=1),
    )

    assert base.context_hash == with_irrelevant.context_hash
    assert base.audit_hash != with_irrelevant.audit_hash
    assert constrained.budget.used_items == 0
    assert constrained.budget.excluded_by_budget == 1
    assert constrained.decisions[0].reason == "excluded_character_budget"


def test_planning_result_records_context_hash_and_selection_audit() -> None:
    memory = weekly(0)
    athlete_preference = preference()
    context = build_agent_memory_context(
        request("plan"),
        preferences=[athlete_preference],
        weekly_memories=[memory],
    )
    goal = TrainingGoal(
        id="goal-1",
        name="秋季十公里",
        event_type="10k",
        target_date=date(2026, 10, 18),
        available_weekdays=["tue", "thu", "sun"],
    )
    result = build_weekly_plan_draft(
        WeeklyPlanDraftRequest(
            goal_id=goal.id,
            week_start=TARGET_WEEK,
            as_of=AS_OF,
        ),
        goal=goal,
        activities=[],
        existing_plan=None,
        athlete_preferences=[athlete_preference],
        weekly_training_memories=[memory],
        memory_context=context,
    )

    assert result.memory_context == context
    evidence = next(item for item in result.evidence if item.type == "memory_context")
    assert evidence.values["context_hash"] == context.context_hash
    assert evidence.values["selected_count"] == 2


def test_memory_context_cli_and_exported_schemas(tmp_path: Path) -> None:
    database_path = tmp_path / "context.db"
    database = Database(f"sqlite:///{database_path.as_posix()}")
    database.create_schema()
    with database.session() as session:
        AthletePreferenceRepository(session).save(preference())
        session.commit()

    result = CliRunner().invoke(
        app,
        [
            "memory",
            "context",
            "--role",
            "plan",
            "--goal-id",
            "goal-1",
            "--as-of",
            AS_OF.isoformat(),
            "--target-week-start",
            TARGET_WEEK.isoformat(),
            "--db",
            str(database_path),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["role"] == "plan"
    assert payload["budget"]["used_items"] == 1

    schema_dir = Path("schemas/memory-context")
    assert json.loads((schema_dir / "request.schema.json").read_text("utf-8")) == (
        MemoryContextBuildRequest.model_json_schema()
    )
    assert json.loads((schema_dir / "output.schema.json").read_text("utf-8")) == (
        AgentMemoryContext.model_json_schema()
    )
