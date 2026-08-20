from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from pathlib import Path

from runcrew.domain.activity import ActivitySummary, SourceProvider, SourceRef, SportType
from runcrew.domain.memory import (
    AthletePreferenceArchiveSubmission,
    AthletePreferenceSubmission,
)
from runcrew.domain.training_cycle import (
    PlanSession,
    PlanSessionPatch,
    TrainingGoal,
    TrainingPlan,
)
from runcrew.domain.training_operations import (
    CheckInSubmission,
    CoachRunDecisionRequest,
    CoachRunSubmission,
    CoachRunDecisionResult,
    CoachRunView,
    ExecutionDecisionSubmission,
    TrainingGoalSubmission,
    TrainingOperationsBootstrap,
    TrainingWeekView,
    WeeklyPlanActivationRequest,
    WeeklyPlanActivationResult,
    WeeklyPlanDraftSubmission,
)
from runcrew.services.training_cycle import TrainingCycleService
from runcrew.services.training_operations import TrainingOperationsService
from runcrew.storage.database import Database
from runcrew.storage.repositories import (
    ActivityRepository,
    CheckInRepository,
    CoachRunRepository,
    PlanChangeRepository,
    TrainingGoalRepository,
    TrainingPlanRepository,
)
from runcrew.web import DemoApplication, DemoDashboardService


ANCHOR = datetime(2026, 8, 13, 8, tzinfo=timezone.utc)


def seed(database_path: Path) -> Database:
    database = Database(f"sqlite:///{database_path.as_posix()}")
    database.create_schema()
    with database.session() as session:
        TrainingGoalRepository(session).save(
            TrainingGoal(
                id="goal-1",
                name="秋季10公里",
                event_type="10k",
                target_date=date(2026, 10, 18),
                available_weekdays=["thu", "sat"],
            )
        )
        TrainingPlanRepository(session).save(
            TrainingPlan(
                id="plan-1",
                goal_id="goal-1",
                week_start=date(2026, 8, 10),
                status="active",
                sessions=[
                    PlanSession(
                        id="quality-1",
                        scheduled_for=date(2026, 8, 15),
                        session_type="interval",
                        distance_meters=6000,
                        duration_seconds=2400,
                        intensity="高强度",
                        purpose="速度耐力",
                    )
                ],
            )
        )
        ActivityRepository(session).upsert(
            ActivitySummary(
                id="run-1",
                source_ref=SourceRef(
                    provider=SourceProvider.FIXTURE,
                    external_id="private-provider-id",
                    fetched_at=ANCHOR,
                    raw_payload_hash="private-raw-hash",
                ),
                sport_type=SportType.RUN,
                started_at=datetime(2026, 8, 12, 8, tzinfo=timezone.utc),
                duration_seconds=1800,
                distance_meters=5000,
            )
        )
        session.commit()
    return database


def moderate_check_in() -> CheckInSubmission:
    return CheckInSubmission(
        day=ANCHOR.date(),
        fatigue=3,
        soreness=4,
        sleep_quality=3,
        pain_area="右膝",
        pain_severity=3,
        note="跑后略有不适",
    )


def run_submission() -> CoachRunSubmission:
    return CoachRunSubmission(
        goal_id="goal-1",
        plan_id="plan-1",
        as_of=ANCHOR,
        provider="fixture",
    )


def test_operations_bootstrap_and_check_in_are_local_and_scoped(tmp_path: Path) -> None:
    path = tmp_path / "operations.db"
    seed(path)
    service = TrainingOperationsService(database_path=path)

    check_in = service.record_check_in(goal_id="goal-1", submission=moderate_check_in())
    bootstrap = service.bootstrap()

    assert check_in.pain_area == "右膝"
    assert len(bootstrap.goals) == 1
    assert bootstrap.goals[0].active_plan is not None
    assert bootstrap.goals[0].latest_check_in is not None
    assert "private-provider-id" not in bootstrap.model_dump_json()
    assert "private-raw-hash" not in bootstrap.model_dump_json()


def test_coach_run_persists_audit_but_not_plan_proposal(tmp_path: Path) -> None:
    path = tmp_path / "coach-run.db"
    database = seed(path)
    service = TrainingOperationsService(database_path=path)
    service.record_check_in(goal_id="goal-1", submission=moderate_check_in())

    view = asyncio.run(service.run_coach(run_submission()))
    loaded = service.get_coach_run(view.audit.run_id)

    assert view.audit.status == "awaiting_user_confirmation"
    assert view.audit.result.planning is not None
    assert loaded.audit.run_id == view.audit.run_id
    assert loaded.audit.planning_output_hash == view.audit.result.planning.input_hash
    with database.session() as session:
        assert PlanChangeRepository(session).pending_for_goal("goal-1") == []
        assert TrainingPlanRepository(session).get("plan-1").revision == 1


def test_user_approval_replays_then_applies_revisioned_change(tmp_path: Path) -> None:
    path = tmp_path / "approve.db"
    database = seed(path)
    service = TrainingOperationsService(database_path=path)
    service.record_check_in(goal_id="goal-1", submission=moderate_check_in())
    run = asyncio.run(service.run_coach(run_submission()))

    decided = asyncio.run(
        service.decide_coach_run(
            run_id=run.audit.run_id,
            request=CoachRunDecisionRequest(
                decision="approve", comment="同意本次降低训练量"
            ),
        )
    )

    assert decided.outcome == "approved"
    assert decided.plan.revision == 2
    assert decided.proposal is not None and decided.proposal.status == "approved"
    assert decided.confirmation is not None
    assert decided.audit.proposal_id == decided.proposal.id
    with database.session() as session:
        stored = CoachRunRepository(session).get(run.audit.run_id)
        assert stored is not None and stored.status == "approved"


def test_reject_does_not_create_or_apply_proposal(tmp_path: Path) -> None:
    path = tmp_path / "reject.db"
    database = seed(path)
    service = TrainingOperationsService(database_path=path)
    service.record_check_in(goal_id="goal-1", submission=moderate_check_in())
    run = asyncio.run(service.run_coach(run_submission()))

    decided = asyncio.run(
        service.decide_coach_run(
            run_id=run.audit.run_id,
            request=CoachRunDecisionRequest(decision="reject", comment="今天仍按原计划"),
        )
    )

    assert decided.outcome == "rejected"
    assert decided.proposal is None and decided.confirmation is None
    assert decided.plan.revision == 1
    with database.session() as session:
        assert PlanChangeRepository(session).pending_for_goal("goal-1") == []


def test_changed_plan_makes_coach_draft_stale_instead_of_overwriting(tmp_path: Path) -> None:
    path = tmp_path / "stale.db"
    database = seed(path)
    service = TrainingOperationsService(database_path=path)
    service.record_check_in(goal_id="goal-1", submission=moderate_check_in())
    run = asyncio.run(service.run_coach(run_submission()))

    with database.session() as session:
        cycle = TrainingCycleService(
            goals=TrainingGoalRepository(session),
            plans=TrainingPlanRepository(session),
            check_ins=CheckInRepository(session),
            changes=PlanChangeRepository(session),
        )
        proposal = cycle.propose_change(
            plan_id="plan-1",
            proposed_by="user",
            reason="用户先修改了计划",
            changes=[
                PlanSessionPatch(session_id="quality-1", duration_seconds=2100)
            ],
        )
        cycle.decide_change(proposal_id=proposal.id, decision="approve")
        session.commit()

    decided = asyncio.run(
        service.decide_coach_run(
            run_id=run.audit.run_id,
            request=CoachRunDecisionRequest(decision="approve"),
        )
    )

    assert decided.outcome == "stale"
    assert decided.plan.revision == 2
    assert decided.plan.sessions[0].duration_seconds == 2100
    assert decided.proposal is None


def test_training_api_end_to_end_and_rejects_client_patch_injection(tmp_path: Path) -> None:
    path = tmp_path / "api.db"
    seed(path)
    application = DemoApplication(
        DemoDashboardService(database_path=path, evaluation_directory=tmp_path / "evals")
    )

    bootstrap = application.handle("GET", "/api/training/bootstrap")
    check_in = application.handle(
        "POST",
        "/api/training/goals/goal-1/check-ins",
        moderate_check_in().model_dump_json().encode("utf-8"),
    )
    run = application.handle(
        "POST",
        "/api/training/coach-runs",
        run_submission().model_dump_json().encode("utf-8"),
    )
    run_payload = json.loads(run.body)
    injected = application.handle(
        "POST",
        f"/api/training/coach-runs/{run_payload['audit']['run_id']}/decision",
        json.dumps(
            {
                "decision": "approve",
                "changes": [{"session_id": "quality-1", "duration_seconds": 99999}],
            }
        ).encode(),
    )
    approved = application.handle(
        "POST",
        f"/api/training/coach-runs/{run_payload['audit']['run_id']}/decision",
        json.dumps({"decision": "approve", "comment": "确认"}, ensure_ascii=False).encode(
            "utf-8"
        ),
    )

    assert bootstrap.status == 200
    assert check_in.status == 201
    assert run.status == 201
    assert run_payload["audit"]["status"] == "awaiting_user_confirmation"
    assert injected.status == 400
    assert approved.status == 200
    assert json.loads(approved.body)["outcome"] == "approved"


def test_training_write_routes_reject_unsupported_methods(tmp_path: Path) -> None:
    path = tmp_path / "methods.db"
    seed(path)
    application = DemoApplication(
        DemoDashboardService(database_path=path, evaluation_directory=tmp_path / "evals")
    )

    assert application.handle("DELETE", "/api/training/coach-runs/anything").status == 405
    assert application.handle("PUT", "/api/training/goals/goal-1/check-ins").status == 405


def test_web_user_can_create_preview_replay_and_activate_week_plan(tmp_path: Path) -> None:
    path = tmp_path / "onboarding.db"
    application = DemoApplication(
        DemoDashboardService(database_path=path, evaluation_directory=tmp_path / "evals")
    )
    created = application.handle(
        "POST",
        "/api/training/goals",
        json.dumps(
            {
                "name": "秋季十公里",
                "event_type": "10k",
                "target_date": "2026-10-18",
                "target_time_seconds": 3000,
                "available_weekdays": ["tue", "thu", "sat"],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
    )
    assert created.status == 201
    goal_id = json.loads(created.body)["id"]
    draft_input = {
        "week_start": "2026-08-24",
        "as_of": "2026-08-16T08:00:00Z",
        "lookback_days": 28,
        "provider": None,
    }
    drafted = application.handle(
        "POST",
        f"/api/training/goals/{goal_id}/plan-drafts",
        json.dumps(draft_input).encode("utf-8"),
    )
    draft_payload = json.loads(drafted.body)
    assert drafted.status == 200
    assert draft_payload["status"] == "ready"
    assert draft_payload["weekly_plan_draft"]["requires_user_confirmation"] is True

    stale = application.handle(
        "POST",
        f"/api/training/goals/{goal_id}/plans/activate",
        json.dumps({**draft_input, "expected_input_hash": "0" * 64}).encode("utf-8"),
    )
    assert stale.status == 400
    activated = application.handle(
        "POST",
        f"/api/training/goals/{goal_id}/plans/activate",
        json.dumps(
            {**draft_input, "expected_input_hash": draft_payload["input_hash"]}
        ).encode("utf-8"),
    )
    activated_payload = json.loads(activated.body)
    assert activated.status == 201
    assert activated_payload["plan"]["status"] == "active"
    assert activated_payload["plan"]["source"] == "deterministic"

    week = application.handle(
        "GET",
        f"/api/training/goals/{goal_id}/week?as_of=2026-08-24T08:00:00Z",
    )
    week_payload = json.loads(week.body)
    assert week.status == 200
    assert week_payload["plan"]["id"] == activated_payload["plan"]["id"]
    assert week_payload["progress"]["upcoming_sessions"] == 3


def test_web_execution_match_requires_user_confirmation_and_updates_week(tmp_path: Path) -> None:
    path = tmp_path / "execution-loop.db"
    database = seed(path)
    with database.session() as session:
        ActivityRepository(session).upsert(
            ActivitySummary(
                id="run-match",
                source_ref=SourceRef(
                    provider=SourceProvider.FIXTURE,
                    external_id="match-provider-id",
                    fetched_at=ANCHOR,
                    raw_payload_hash="match-raw-hash",
                ),
                sport_type=SportType.RUN,
                started_at=datetime(2026, 8, 15, 8, tzinfo=timezone.utc),
                duration_seconds=2380,
                distance_meters=5980,
            )
        )
        session.commit()
    application = DemoApplication(
        DemoDashboardService(database_path=path, evaluation_directory=tmp_path / "evals")
    )
    before = application.handle(
        "GET",
        "/api/training/goals/goal-1/week?as_of=2026-08-16T08:00:00Z&provider=fixture",
    )
    before_payload = json.loads(before.body)
    comparison = before_payload["execution"]["sessions"][0]
    assert comparison["match_state"] == "suggested"
    assert comparison["requires_user_confirmation"] is True

    decision = application.handle(
        "POST",
        "/api/training/plans/plan-1/execution-decisions",
        json.dumps(
            {
                "base_revision": before_payload["plan"]["revision"],
                "session_id": "quality-1",
                "decision": "confirm_match",
                "as_of": "2026-08-16T08:00:00Z",
                "activity_id": "run-match",
                "comment": "确认是本次计划训练",
            },
            ensure_ascii=False,
        ).encode("utf-8"),
    )
    assert decision.status == 200
    assert json.loads(decision.body)["confirmation"]["status"] == "applied"

    after = application.handle(
        "GET",
        "/api/training/goals/goal-1/week?as_of=2026-08-16T08:00:00Z&provider=fixture",
    )
    after_payload = json.loads(after.body)
    assert after_payload["execution"]["sessions"][0]["match_state"] == "confirmed"
    assert after_payload["progress"]["confirmed_sessions"] == 1
    assert after_payload["progress"]["completion_rate"] == 1.0


def test_training_ui_assets_and_exported_schemas_are_current(tmp_path: Path) -> None:
    path = tmp_path / "assets.db"
    seed(path)
    application = DemoApplication(
        DemoDashboardService(database_path=path, evaluation_directory=tmp_path / "evals")
    )
    html = application.handle("GET", "/").body.decode("utf-8")
    script = application.handle("GET", "/assets/chat.js").body.decode("utf-8")
    style = application.handle("GET", "/assets/chat.css?v=20260819-1").body.decode("utf-8")
    assert "训练闭环" in html
    assert "今日训练与执行" in html
    assert "新建训练目标" in html
    assert "预览保守周计划" in html
    assert "跑后反馈" in html
    assert "运行跨职责评估" in html
    assert "长期训练偏好" in html
    assert "/api/training/preferences" in script
    assert "/api/training/coach-runs" in script
    assert "window.confirm" in script
    assert "innerHTML" not in script
    assert "个人跑步办公室" in html
    assert "智能体协作" in html
    assert "回答依据" in html
    assert "训练索引" in html
    assert "TRAINING INDEX" in html
    assert 'class="run-summary"' in html
    assert 'id="metric-distance"' in html
    assert 'id="crew-overview"' in html
    assert "setCrewOverview" in script
    assert "renderRunHeader" in script
    assert "toggleContext" in script
    assert 'id="context-panel" class="context-panel" aria-label="回答依据" hidden' in html
    assert "/assets/chat.css?v=20260819-1" in html
    assert "grid-template-rows: 68px minmax(0, 1fr)" in style
    assert "position: sticky" in style
    assert ".workspace {" in style and "overflow: hidden" in style
    assert "grid-template-rows: auto auto minmax(0, 1fr) auto" in style
    assert "max(10px, env(safe-area-inset-bottom))" in style
    assert "--ivory" in style
    assert "#b9e845" not in style

    references = Path("schemas/training-operations")
    expected = {
        "bootstrap.schema.json": TrainingOperationsBootstrap,
        "athlete-preference-input.schema.json": AthletePreferenceSubmission,
        "athlete-preference-archive-input.schema.json": AthletePreferenceArchiveSubmission,
        "check-in-input.schema.json": CheckInSubmission,
        "coach-run-input.schema.json": CoachRunSubmission,
        "coach-run-output.schema.json": CoachRunView,
        "decision-input.schema.json": CoachRunDecisionRequest,
        "decision-output.schema.json": CoachRunDecisionResult,
        "goal-input.schema.json": TrainingGoalSubmission,
        "plan-draft-input.schema.json": WeeklyPlanDraftSubmission,
        "plan-activation-input.schema.json": WeeklyPlanActivationRequest,
        "plan-activation-output.schema.json": WeeklyPlanActivationResult,
        "week-view.schema.json": TrainingWeekView,
        "execution-decision-input.schema.json": ExecutionDecisionSubmission,
    }
    for name, model in expected.items():
        assert json.loads((references / name).read_text("utf-8")) == model.model_json_schema()
