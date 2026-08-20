from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from runcrew.domain.activity import ActivitySummary, SourceProvider, SourceRef, SportType
from runcrew.domain.memory import AthletePreferenceSubmission, WeeklyTrainingMemory
from runcrew.domain.memory_control import (
    MemoryControlOverview,
    WeeklyMemoryInvalidationRequest,
)
from runcrew.domain.training_cycle import TrainingGoal, TrainingPlan
from runcrew.services.chat import ChatService
from runcrew.services.memory_control import MemoryControlService
from runcrew.services.training_operations import TrainingOperationsService
from runcrew.storage.database import Database
from runcrew.storage.repositories import (
    ActivityRepository,
    TrainingGoalRepository,
    TrainingPlanRepository,
    WeeklyTrainingMemoryRepository,
)
from runcrew.web import DemoApplication, DemoDashboardService


NOW = datetime(2026, 8, 20, 8, tzinfo=timezone.utc)


def _seed_memory_control(tmp_path: Path) -> tuple[Path, str, str, str]:
    path = tmp_path / "memory-control.db"
    database = Database(f"sqlite:///{path.as_posix()}")
    database.create_schema()
    goal = TrainingGoal(
        id="goal-memory",
        name="秋季十公里",
        event_type="10k",
        target_date=date(2026, 11, 1),
        available_weekdays=["tue", "thu", "sun"],
        created_at=NOW - timedelta(days=30),
        updated_at=NOW - timedelta(days=30),
    )
    plan = TrainingPlan(
        id="plan-memory",
        goal_id=goal.id,
        week_start=date(2026, 8, 10),
        status="completed",
        created_at=NOW - timedelta(days=10),
        updated_at=NOW - timedelta(days=3),
    )
    weekly = WeeklyTrainingMemory(
        id="weekly-memory",
        goal_id=goal.id,
        plan_id=plan.id,
        week_start=date(2026, 8, 10),
        week_end=date(2026, 8, 16),
        version=1,
        plan_revision=1,
        input_hash="a" * 64,
        planned_sessions=0,
        confirmed_completed_sessions=0,
        confirmed_skipped_sessions=0,
        unresolved_sessions=0,
        planned_duration_seconds=0,
        actual_duration_seconds=0,
        actual_distance_meters=0,
        check_in_days=0,
        acute_symptom_days=0,
        approved_plan_changes=0,
        summary="该周没有已确认的计划训练，保留为空周基线。",
        missing_data=["no_planned_sessions"],
        source_refs=["plan:plan-memory@revision:1"],
        generated_at=NOW - timedelta(days=2),
        updated_at=NOW - timedelta(days=2),
    )
    with database.session() as session:
        ActivityRepository(session).upsert(
            ActivitySummary(
                id="activity-memory",
                source_ref=SourceRef(
                    provider=SourceProvider.FIXTURE,
                    external_id="must-not-leak-external-id",
                    fetched_at=NOW,
                    raw_payload_hash="must-not-leak-payload-hash",
                ),
                sport_type=SportType.RUN,
                started_at=NOW - timedelta(days=1),
                duration_seconds=2400,
                distance_meters=6000,
                average_pace_seconds_per_km=400,
                title="合成轻松跑",
            )
        )
        TrainingGoalRepository(session).save(goal)
        TrainingPlanRepository(session).save(plan)
        WeeklyTrainingMemoryRepository(session).save(weekly)
        session.commit()

    chat = ChatService(database_path=path, clock=lambda: NOW)
    conversation = chat.create_conversation(
        activity_id="activity-memory",
        title="长跑安排讨论",
    )
    result = asyncio.run(
        chat.send_message(
            conversation_id=conversation.id,
            content="以后长跑优先安排在周日",
        )
    )
    candidate_id = result.new_memory_candidates[0].id
    training = TrainingOperationsService(database_path=path, clock=lambda: NOW)
    preference = training.confirm_preference(
        AthletePreferenceSubmission(
            key="preferred_long_run_weekday",
            value="sat",
            confirmed=True,
        )
    )
    return path, candidate_id, preference.id, weekly.id


def test_overview_exposes_source_lifecycle_and_role_scoped_context(
    tmp_path: Path,
) -> None:
    path, candidate_id, preference_id, weekly_id = _seed_memory_control(tmp_path)

    overview = MemoryControlService(
        database_path=path,
        clock=lambda: NOW,
    ).overview()

    assert overview.schema_version == "memory-control-overview/1.0"
    assert overview.counts.pending_candidates == 1
    assert overview.counts.active_preferences == 1
    assert overview.counts.active_weekly_memories == 1
    candidate = next(item for item in overview.candidates if item.candidate.id == candidate_id)
    assert candidate.conversation_title == "长跑安排讨论"
    assert candidate.source_excerpt == "以后长跑优先安排在周日"
    assert candidate.source_available is True
    assert next(
        item for item in overview.preferences if item.preference.id == preference_id
    ).effective_now is True
    assert next(
        item for item in overview.weekly_memories if item.memory.id == weekly_id
    ).goal_name == "秋季十公里"

    contexts = {item.role: item for item in overview.goal_contexts[0].contexts}
    assert contexts["execution"].budget.used_items == 0
    assert contexts["recovery"].selected_weekly_memories[0].memory_id == weekly_id
    assert contexts["plan"].selected_preferences[0].memory_id == preference_id
    assert contexts["plan"].selected_weekly_memories[0].memory_id == weekly_id
    serialized = overview.model_dump_json()
    assert "must-not-leak-external-id" not in serialized
    assert "must-not-leak-payload-hash" not in serialized


def test_memory_control_api_reuses_confirmation_boundaries(tmp_path: Path) -> None:
    path, candidate_id, preference_id, weekly_id = _seed_memory_control(tmp_path)
    memory_service = MemoryControlService(database_path=path, clock=lambda: NOW)
    training_service = TrainingOperationsService(database_path=path, clock=lambda: NOW)
    chat_service = ChatService(database_path=path, clock=lambda: NOW)
    application = DemoApplication(
        DemoDashboardService(database_path=path, evaluation_directory=tmp_path / "evals"),
        chat_service=chat_service,
        training_service=training_service,
        memory_service=memory_service,
    )

    overview_response = application.handle("GET", "/api/memory/overview")
    assert overview_response.status == 200
    overview = json.loads(overview_response.body)
    candidate = next(
        item["candidate"]
        for item in overview["candidates"]
        if item["candidate"]["id"] == candidate_id
    )

    injected = application.handle(
        "POST",
        f"/api/memory/candidates/{candidate_id}/decision",
        json.dumps(
            {
                "decision": "reject",
                "expected_candidate_hash": candidate["candidate_hash"],
                "proposed_value": "mon",
            }
        ).encode(),
    )
    assert injected.status == 400
    rejected = application.handle(
        "POST",
        f"/api/memory/candidates/{candidate_id}/decision",
        json.dumps(
            {
                "decision": "reject",
                "expected_candidate_hash": candidate["candidate_hash"],
            }
        ).encode(),
    )
    assert rejected.status == 200
    assert json.loads(rejected.body)["candidate"]["status"] == "rejected"

    unconfirmed_archive = application.handle(
        "POST",
        f"/api/memory/preferences/{preference_id}/archive",
        b'{"confirmed":false}',
    )
    assert unconfirmed_archive.status == 400
    archived = application.handle(
        "POST",
        f"/api/memory/preferences/{preference_id}/archive",
        b'{"confirmed":true}',
    )
    assert archived.status == 200
    assert json.loads(archived.body)["status"] == "archived"

    unconfirmed_invalidation = application.handle(
        "POST",
        f"/api/memory/weekly-memories/{weekly_id}/invalidate",
        b'{"confirmed":false}',
    )
    assert unconfirmed_invalidation.status == 400
    invalidated = application.handle(
        "POST",
        f"/api/memory/weekly-memories/{weekly_id}/invalidate",
        b'{"confirmed":true}',
    )
    assert invalidated.status == 200
    assert json.loads(invalidated.body)["status"] == "invalidated"


def test_memory_control_assets_and_schemas_are_current(tmp_path: Path) -> None:
    path, _, _, _ = _seed_memory_control(tmp_path)
    application = DemoApplication(
        DemoDashboardService(database_path=path, evaluation_directory=tmp_path / "evals")
    )
    html = application.handle("GET", "/").body.decode("utf-8")
    script = application.handle("GET", "/assets/chat.js").body.decode("utf-8")
    style = application.handle("GET", "/assets/chat.css").body.decode("utf-8")

    assert "记忆档案" in html
    assert "职责可见性" in html
    assert "/api/memory/overview" in script
    assert "/api/memory/weekly-memories/" in script
    assert "renderMemoryControlContexts" in script
    assert "innerHTML" not in script
    assert "/assets/chat.css?v=20260820-4" in html
    assert "/assets/chat.js?v=20260820-4" in html
    assert ".memory-control-summary" in style
    assert "#b9e845" not in style
    assert subprocess.run(
        ["node", "--check", "src/runcrew/web/static/chat.js"],
        check=False,
        capture_output=True,
        text=True,
    ).returncode == 0

    schema_dir = Path("schemas/memory-control")
    assert json.loads((schema_dir / "overview.schema.json").read_text("utf-8")) == (
        MemoryControlOverview.model_json_schema()
    )
    assert json.loads(
        (schema_dir / "weekly-invalidation-input.schema.json").read_text("utf-8")
    ) == WeeklyMemoryInvalidationRequest.model_json_schema()
