from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from runcrew.cli import app
from runcrew.domain.training_cycle import (
    DailyCheckIn,
    PlanSession,
    PlanSessionPatch,
    TrainingGoal,
)
from runcrew.services.training_cycle import TrainingCycleError, TrainingCycleService
from runcrew.storage.database import Database
from runcrew.storage.repositories import (
    CheckInRepository,
    PlanChangeRepository,
    TrainingGoalRepository,
    TrainingPlanRepository,
)


def build_service(database: Database) -> tuple[object, TrainingCycleService]:
    session = database.session()
    return session, TrainingCycleService(
        goals=TrainingGoalRepository(session),
        plans=TrainingPlanRepository(session),
        check_ins=CheckInRepository(session),
        changes=PlanChangeRepository(session),
    )


def test_training_cycle_persists_goal_plan_feedback_and_approval(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'cycle.db').as_posix()}")
    database.create_schema()
    session, service = build_service(database)
    with session:
        goal = TrainingGoal(
            name="秋季10公里跑进50分钟",
            event_type="10k",
            target_date=date(2026, 10, 18),
            target_time_seconds=3000,
            available_weekdays=["tue", "thu", "sat", "sun"],
        )
        service.goals.save(goal)
        plan = service.create_plan(goal_id=goal.id, week_start=date(2026, 8, 10))
        plan = service.add_draft_session(
            plan.id,
            PlanSession(
                id="quality-session",
                scheduled_for=date(2026, 8, 13),
                session_type="interval",
                distance_meters=6000,
                intensity="5组800米",
                purpose="提高10公里专项速度耐力",
            ),
        )
        service.activate_plan(plan.id)
        service.check_ins.save(
            DailyCheckIn(
                day=date(2026, 8, 12),
                fatigue=4,
                soreness=6,
                sleep_quality=2,
                pain_area="右膝外侧",
                pain_severity=4,
                note="上下楼时不适",
            )
        )
        proposal = service.propose_change(
            plan_id=plan.id,
            proposed_by="recovery_agent",
            reason="主观疲劳和疼痛反馈偏高，建议先降低强度",
            changes=[
                PlanSessionPatch(
                    session_id="quality-session",
                    session_type="recovery",
                    distance_meters=3000,
                    intensity="轻松跑，可随时停止",
                    purpose="观察恢复状态，不执行高强度训练",
                )
            ],
            evidence_refs=["check_in:2026-08-12"],
        )
        unchanged = service.plans.get(plan.id)
        assert unchanged is not None
        assert unchanged.sessions[0].session_type == "interval"

        approved, decided, confirmation = service.decide_change(
            proposal_id=proposal.id,
            decision="approve",
            comment="同意先降级一次训练",
        )
        session.commit()

        assert approved.revision == 2
        assert approved.sessions[0].session_type == "recovery"
        assert decided.status == "approved"
        assert confirmation.decision == "approve"

    verify_session, verify_service = build_service(database)
    with verify_session:
        snapshot = verify_service.snapshot(goal.id)
        assert snapshot.active_plan is not None
        assert snapshot.active_plan.revision == 2
        assert snapshot.recent_check_ins[0].pain_area == "右膝外侧"
        assert snapshot.pending_proposals == []


def test_active_plan_cannot_be_directly_modified(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'immutable.db').as_posix()}")
    database.create_schema()
    session, service = build_service(database)
    with session:
        goal = TrainingGoal(
            name="完成首个半马",
            event_type="half_marathon",
            target_date=date(2026, 11, 1),
            available_weekdays=["wed", "sun"],
        )
        service.goals.save(goal)
        plan = service.create_plan(goal_id=goal.id, week_start=date(2026, 8, 10))
        service.add_draft_session(
            plan.id,
            PlanSession(
                scheduled_for=date(2026, 8, 16),
                session_type="long_run",
                distance_meters=12000,
                purpose="建立耐力",
            ),
        )
        service.activate_plan(plan.id)

        with pytest.raises(TrainingCycleError, match="必须提交变更提案"):
            service.add_draft_session(
                plan.id,
                PlanSession(
                    scheduled_for=date(2026, 8, 12),
                    session_type="easy",
                    distance_meters=5000,
                    purpose="轻松跑",
                ),
            )
        with pytest.raises(TrainingCycleError, match="已经存在计划"):
            service.create_plan(goal_id=goal.id, week_start=date(2026, 8, 10))


def test_stale_proposal_cannot_overwrite_new_revision(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'stale.db').as_posix()}")
    database.create_schema()
    session, service = build_service(database)
    with session:
        goal = TrainingGoal(
            name="10公里稳定完赛",
            event_type="10k",
            target_date=date(2026, 10, 1),
            available_weekdays=["sat"],
        )
        service.goals.save(goal)
        plan = service.create_plan(goal_id=goal.id, week_start=date(2026, 8, 10))
        service.add_draft_session(
            plan.id,
            PlanSession(
                id="session-1",
                scheduled_for=date(2026, 8, 15),
                session_type="easy",
                distance_meters=5000,
                purpose="基础跑",
            ),
        )
        service.activate_plan(plan.id)
        first = service.propose_change(
            plan_id=plan.id,
            proposed_by="plan_agent",
            reason="增加一点距离",
            changes=[PlanSessionPatch(session_id="session-1", distance_meters=6000)],
        )
        stale = service.propose_change(
            plan_id=plan.id,
            proposed_by="recovery_agent",
            reason="降低训练量",
            changes=[PlanSessionPatch(session_id="session-1", distance_meters=4000)],
        )
        service.decide_change(proposal_id=first.id, decision="approve")

        _, stale_result, _ = service.decide_change(
            proposal_id=stale.id, decision="approve"
        )
        current = service.plans.get(plan.id)
        assert current is not None
        assert stale_result.status == "stale"
        assert current.revision == 2
        assert current.sessions[0].distance_meters == 6000


def test_feedback_validation_rejects_unlocated_pain() -> None:
    with pytest.raises(ValidationError, match="疼痛部位"):
        DailyCheckIn(
            day=date(2026, 8, 12),
            fatigue=3,
            soreness=2,
            sleep_quality=3,
            pain_severity=2,
        )


def test_change_to_rest_requires_and_applies_explicit_target_clearing(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="休息日不能设置"):
        PlanSession(
            scheduled_for=date(2026, 8, 15),
            session_type="rest",
            distance_meters=5000,
            purpose="休息",
        )

    database = Database(f"sqlite:///{(tmp_path / 'rest.db').as_posix()}")
    database.create_schema()
    session, service = build_service(database)
    with session:
        goal = TrainingGoal(
            name="恢复测试",
            event_type="general_fitness",
            target_date=date(2026, 9, 1),
            available_weekdays=["sat"],
        )
        service.goals.save(goal)
        plan = service.create_plan(goal_id=goal.id, week_start=date(2026, 8, 10))
        service.add_draft_session(
            plan.id,
            PlanSession(
                id="planned-run",
                scheduled_for=date(2026, 8, 15),
                session_type="easy",
                distance_meters=5000,
                intensity="轻松",
                purpose="基础跑",
            ),
        )
        service.activate_plan(plan.id)
        proposal = service.propose_change(
            plan_id=plan.id,
            proposed_by="recovery_agent",
            reason="疼痛反馈需要停止训练",
            changes=[
                PlanSessionPatch(
                    session_id="planned-run",
                    session_type="rest",
                    clear_distance=True,
                    clear_intensity=True,
                    purpose="休息并观察症状",
                )
            ],
        )
        updated, _, _ = service.decide_change(
            proposal_id=proposal.id, decision="approve"
        )
        assert updated.sessions[0].session_type == "rest"
        assert updated.sessions[0].distance_meters is None
        assert updated.sessions[0].intensity is None


def test_cycle_cli_creates_goal_and_rejects_invalid_date(tmp_path: Path) -> None:
    database_path = tmp_path / "cli.db"
    runner = CliRunner()
    created = runner.invoke(
        app,
        [
            "cycle",
            "goal-create",
            "--name",
            "秋季10公里",
            "--event-type",
            "10k",
            "--target-date",
            "2026-10-18",
            "--available-weekdays",
            "tue,thu,sun",
            "--db",
            str(database_path),
        ],
    )
    assert created.exit_code == 0, created.output
    assert '"event_type": "10k"' in created.output

    listed = runner.invoke(
        app,
        ["cycle", "goal-list", "--db", str(database_path)],
    )
    assert listed.exit_code == 0, listed.output
    assert "秋季10公里" in listed.output

    rejected = runner.invoke(
        app,
        [
            "cycle",
            "goal-create",
            "--name",
            "错误日期",
            "--event-type",
            "10k",
            "--target-date",
            "2026/10/18",
            "--available-weekdays",
            "sun",
            "--db",
            str(database_path),
        ],
    )
    assert rejected.exit_code != 0
    assert "YYYY-MM-DD" in rejected.output


def test_cycle_cli_runs_goal_plan_feedback_and_change_workflow(tmp_path: Path) -> None:
    database_path = tmp_path / "workflow.db"
    runner = CliRunner()

    goal_result = runner.invoke(
        app,
        [
            "cycle",
            "goal-create",
            "--name",
            "10公里训练闭环",
            "--event-type",
            "10k",
            "--target-date",
            "2026-10-18",
            "--available-weekdays",
            "thu,sun",
            "--db",
            str(database_path),
        ],
    )
    assert goal_result.exit_code == 0, goal_result.output
    goal_id = json.loads(goal_result.output)["id"]

    plan_result = runner.invoke(
        app,
        [
            "cycle",
            "plan-create",
            "--goal-id",
            goal_id,
            "--week-start",
            "2026-08-10",
            "--db",
            str(database_path),
        ],
    )
    assert plan_result.exit_code == 0, plan_result.output
    plan_id = json.loads(plan_result.output)["id"]

    session_result = runner.invoke(
        app,
        [
            "cycle",
            "session-add",
            "--plan-id",
            plan_id,
            "--scheduled-for",
            "2026-08-13",
            "--session-type",
            "interval",
            "--purpose",
            "提高速度耐力",
            "--distance-km",
            "6",
            "--db",
            str(database_path),
        ],
    )
    assert session_result.exit_code == 0, session_result.output
    session_id = json.loads(session_result.output)["sessions"][0]["id"]

    activated = runner.invoke(
        app,
        [
            "cycle",
            "plan-activate",
            "--plan-id",
            plan_id,
            "--db",
            str(database_path),
        ],
    )
    assert activated.exit_code == 0, activated.output

    checked_in = runner.invoke(
        app,
        [
            "cycle",
            "check-in",
            "--day",
            "2026-08-12",
            "--fatigue",
            "4",
            "--soreness",
            "5",
            "--sleep-quality",
            "2",
            "--pain-area",
            "右膝",
            "--pain-severity",
            "3",
            "--db",
            str(database_path),
        ],
    )
    assert checked_in.exit_code == 0, checked_in.output

    proposed = runner.invoke(
        app,
        [
            "cycle",
            "change-propose",
            "--plan-id",
            plan_id,
            "--session-id",
            session_id,
            "--proposed-by",
            "recovery_agent",
            "--reason",
            "疲劳和疼痛反馈偏高",
            "--session-type",
            "recovery",
            "--distance-km",
            "3",
            "--intensity",
            "非常轻松",
            "--evidence-refs",
            "check_in:2026-08-12",
            "--db",
            str(database_path),
        ],
    )
    assert proposed.exit_code == 0, proposed.output
    proposal_id = json.loads(proposed.output)["id"]

    decided = runner.invoke(
        app,
        [
            "cycle",
            "change-decide",
            "--proposal-id",
            proposal_id,
            "--decision",
            "approve",
            "--db",
            str(database_path),
        ],
    )
    assert decided.exit_code == 0, decided.output
    assert json.loads(decided.output)["plan"]["revision"] == 2

    snapshot = runner.invoke(
        app,
        ["cycle", "snapshot", "--goal-id", goal_id, "--db", str(database_path)],
    )
    assert snapshot.exit_code == 0, snapshot.output
    snapshot_payload = json.loads(snapshot.output)
    assert snapshot_payload["active_plan"]["sessions"][0]["session_type"] == "recovery"
    assert snapshot_payload["recent_check_ins"][0]["pain_area"] == "右膝"
