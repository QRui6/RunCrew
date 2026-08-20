from __future__ import annotations

import asyncio
import json
from datetime import date
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from runcrew.providers.fixture import FixtureActivityProvider
from runcrew.providers.coros import CorosActivityProvider
from runcrew.domain.agent import ReviewAgentRunRequest
from runcrew.domain.coach import CoachAgentRunRequest
from runcrew.domain.memory import AthletePreferenceSubmission
from runcrew.domain.training_review import PlannedSession, TrainingReviewRequest
from runcrew.domain.training_cycle import (
    DailyCheckIn,
    PlanSession,
    PlanSessionPatch,
    TrainingGoal,
)
from runcrew.domain.recovery_assessment import RecoveryAssessmentRequest
from runcrew.domain.training_planning import WeeklyPlanDraftRequest
from runcrew.domain.training_execution import (
    TrainingExecutionDecisionRequest,
    TrainingExecutionRequest,
)
from runcrew.evaluation import (
    evaluate_chat_suite,
    evaluate_coach_agent_suite,
    evaluate_review_agent_suite,
    load_chat_evaluation_suite,
    load_coach_agent_suite,
    load_review_agent_suite,
)
from runcrew.harness import CoachNodeTools, CoachOrchestratorHarness, ReviewAgentHarness
from runcrew.policies import (
    DeepSeekCostBudget,
    DeepSeekGroundedChatPolicy,
    DeepSeekPolicyConfig,
    DeepSeekPolicyError,
    DeepSeekReviewPolicy,
)
from runcrew.services.activity_review import build_activity_review
from runcrew.services.athlete_memory import (
    AthleteMemoryError,
    archive_athlete_preference,
    confirm_athlete_preference,
    preferences_for_display,
)
from runcrew.services.demo_seed import DemoSeedError, prepare_demo_database
from runcrew.services.sync import sync_activities
from runcrew.services.training_review import execute_training_review
from runcrew.services.training_cycle import TrainingCycleError, TrainingCycleService
from runcrew.services.recovery_assessment import (
    RecoveryAssessmentGoalNotFoundError,
    execute_recovery_assessment,
)
from runcrew.services.training_planning import (
    TrainingPlanningError,
    adjustment_request_from_recovery,
    execute_plan_adjustment,
    execute_weekly_plan_draft,
)
from runcrew.services.training_execution import (
    TrainingExecutionError,
    confirm_training_execution,
    execute_training_comparison,
)
from runcrew.storage.database import Database
from runcrew.storage.models import ActivityRecord, RawProviderEvent, SyncRunRecord
from runcrew.storage.repositories import (
    ActivityRepository,
    AthletePreferenceRepository,
    CheckInRepository,
    PlanChangeRepository,
    TrainingGoalRepository,
    TrainingPlanRepository,
    TrainingExecutionConfirmationRepository,
)
from runcrew.web import serve_demo


app = typer.Typer(
    name="runcrew",
    help="RunCrew running data and agent engineering CLI.",
    no_args_is_help=True,
)
activities_app = typer.Typer(help="Inspect and review normalized activities.")
training_app = typer.Typer(help="Run replayable training review skills.")
agent_app = typer.Typer(help="运行带 Trace、预算和退出条件的单 Agent。")
evaluation_app = typer.Typer(help="运行可回放的 Agent 离线评测。")
cycle_app = typer.Typer(help="管理训练目标、周计划、身体反馈和计划变更确认。")
recovery_app = typer.Typer(help="运行确定性的恢复与训练风险评估。")
planning_app = typer.Typer(help="生成可回放的训练周草案与待确认调整提案。")
execution_app = typer.Typer(help="对照训练计划与实际跑步，并管理用户确认。")
coach_app = typer.Typer(help="编排训练执行、恢复评估和计划调整职责节点。")
memory_app = typer.Typer(help="管理经过用户明确确认的长期训练偏好。")
app.add_typer(activities_app, name="activities")
app.add_typer(training_app, name="training")
app.add_typer(agent_app, name="agent")
app.add_typer(evaluation_app, name="eval")
app.add_typer(cycle_app, name="cycle")
app.add_typer(recovery_app, name="recovery")
app.add_typer(planning_app, name="planning")
app.add_typer(execution_app, name="execution")
app.add_typer(coach_app, name="coach")
app.add_typer(memory_app, name="memory")


def database_url(database_path: Path) -> str:
    return f"sqlite:///{database_path.resolve().as_posix()}"


def open_database(database_path: Path) -> Database:
    database = Database(database_url(database_path))
    database.create_schema()
    return database


def training_cycle_service(session: Session) -> TrainingCycleService:
    return TrainingCycleService(
        goals=TrainingGoalRepository(session),
        plans=TrainingPlanRepository(session),
        check_ins=CheckInRepository(session),
        changes=PlanChangeRepository(session),
    )


def echo_domain(value: BaseModel) -> None:
    typer.echo(value.model_dump_json(indent=2))


@memory_app.command("remember-long-run-day")
def remember_long_run_day(
    weekday: Annotated[
        str,
        typer.Option(help="偏好的长跑星期：mon/tue/wed/thu/fri/sat/sun。"),
    ],
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="明确确认把该设置保存为长期偏好。"),
    ] = False,
    valid_until: Annotated[
        str | None,
        typer.Option(help="可选失效时间，ISO 8601 且必须包含时区。"),
    ] = None,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    """保存长期偏好；重复值幂等，新值会替代旧版本。"""
    if not confirm:
        raise typer.BadParameter("必须传入 --confirm 才会写入长期偏好")
    database = open_database(database_path)
    try:
        submission = AthletePreferenceSubmission(
            key="preferred_long_run_weekday",
            value=weekday,
            confirmed=True,
            valid_until=(
                parse_iso_datetime(valid_until, option_name="--valid-until")
                if valid_until
                else None
            ),
        )
        with database.session() as session:
            preference = confirm_athlete_preference(
                submission,
                preferences=AthletePreferenceRepository(session),
                source_ref="cli:remember-long-run-day",
            )
            session.commit()
    except (ValueError, AthleteMemoryError) as error:
        raise typer.BadParameter(str(error)) from error
    echo_domain(preference)


@memory_app.command("list")
def list_memories(
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    database = open_database(database_path)
    with database.session() as session:
        memories = preferences_for_display(AthletePreferenceRepository(session))
    typer.echo(
        json.dumps(
            [item.model_dump(mode="json") for item in memories],
            ensure_ascii=False,
            indent=2,
        )
    )


@memory_app.command("archive")
def archive_memory(
    preference_id: Annotated[str, typer.Option(help="待停用偏好 ID。")],
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="明确确认停用该长期偏好。"),
    ] = False,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    if not confirm:
        raise typer.BadParameter("必须传入 --confirm 才会停用长期偏好")
    database = open_database(database_path)
    try:
        with database.session() as session:
            preference = archive_athlete_preference(
                preference_id,
                preferences=AthletePreferenceRepository(session),
            )
            session.commit()
    except AthleteMemoryError as error:
        raise typer.BadParameter(str(error)) from error
    echo_domain(preference)


def parse_iso_date(value: str, *, option_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise typer.BadParameter(
            f"{option_name} 必须使用 YYYY-MM-DD 格式。"
        ) from error


def parse_iso_datetime(value: str, *, option_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise typer.BadParameter(
            f"{option_name} 必须使用带时区的 ISO 8601 格式。"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise typer.BadParameter(f"{option_name} 必须包含时区偏移。")
    return parsed


@app.command("init-db")
def init_db(
    database_path: Annotated[
        Path, typer.Option("--db", help="SQLite database path.")
    ] = Path("data/runcrew.db"),
) -> None:
    open_database(database_path)
    typer.echo(f"Initialized database: {database_path.resolve()}")


@app.command("status")
def status_command(
    database_path: Annotated[
        Path, typer.Option("--db", help="SQLite database path.")
    ] = Path("data/runcrew.db"),
) -> None:
    database = open_database(database_path)
    with database.session() as session:
        provider_counts = session.execute(
            select(ActivityRecord.provider, func.count())
            .group_by(ActivityRecord.provider)
            .order_by(ActivityRecord.provider)
        ).all()
        raw_event_count = session.scalar(
            select(func.count()).select_from(RawProviderEvent)
        )
        latest_sync = session.scalar(
            select(SyncRunRecord).order_by(SyncRunRecord.id.desc()).limit(1)
        )
    typer.echo("Activities: " + (", ".join(f"{p}={c}" for p, c in provider_counts) or "0"))
    typer.echo(f"Raw provider events: {raw_event_count or 0}")
    if latest_sync:
        typer.echo(
            "Latest sync: "
            f"provider={latest_sync.provider}, status={latest_sync.status}, "
            f"fetched={latest_sync.fetched_count}, inserted={latest_sync.inserted_count}, "
            f"updated={latest_sync.updated_count}"
        )
    else:
        typer.echo("Latest sync: none")


@cycle_app.command("goal-create")
def cycle_goal_create(
    name: Annotated[str, typer.Option(help="训练目标名称。")],
    event_type: Annotated[
        str, typer.Option(help="5k、10k、half_marathon、marathon 或 general_fitness。")
    ],
    target_date: Annotated[str, typer.Option(help="目标日期，格式 YYYY-MM-DD。")],
    available_weekdays: Annotated[
        str,
        typer.Option(help="可训练星期，逗号分隔，例如 tue,thu,sat,sun。"),
    ],
    target_time_seconds: Annotated[
        int | None, typer.Option(min=1, help="可选目标成绩，单位秒。")
    ] = None,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    database = open_database(database_path)
    try:
        goal = TrainingGoal(
            name=name,
            event_type=event_type,
            target_date=parse_iso_date(target_date, option_name="--target-date"),
            target_time_seconds=target_time_seconds,
            available_weekdays=[
                value.strip() for value in available_weekdays.split(",") if value.strip()
            ],
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    with database.session() as session:
        training_cycle_service(session).create_goal(goal)
        session.commit()
    echo_domain(goal)


@cycle_app.command("plan-create")
def cycle_plan_create(
    goal_id: Annotated[str, typer.Option(help="训练目标内部 ID。")],
    week_start: Annotated[str, typer.Option(help="周一日期，格式 YYYY-MM-DD。")],
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    database = open_database(database_path)
    try:
        with database.session() as session:
            plan = training_cycle_service(session).create_plan(
                goal_id=goal_id,
                week_start=parse_iso_date(week_start, option_name="--week-start"),
            )
            session.commit()
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    echo_domain(plan)


@cycle_app.command("goal-list")
def cycle_goal_list(
    limit: Annotated[int, typer.Option(min=1, max=100)] = 20,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    database = open_database(database_path)
    with database.session() as session:
        goals = TrainingGoalRepository(session).list(limit=limit)
    typer.echo(
        json.dumps(
            [goal.model_dump(mode="json") for goal in goals],
            ensure_ascii=False,
            indent=2,
        )
    )


@cycle_app.command("session-add")
def cycle_session_add(
    plan_id: Annotated[str, typer.Option(help="训练计划内部 ID。")],
    scheduled_for: Annotated[str, typer.Option(help="课表日期，格式 YYYY-MM-DD。")],
    session_type: Annotated[
        str,
        typer.Option(help="easy/long_run/tempo/interval/recovery/rest/test。"),
    ],
    purpose: Annotated[str, typer.Option(help="本次课的训练目的。")],
    distance_km: Annotated[float | None, typer.Option(min=0.001)] = None,
    duration_minutes: Annotated[float | None, typer.Option(min=0.01)] = None,
    intensity: Annotated[str | None, typer.Option()] = None,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    database = open_database(database_path)
    try:
        item = PlanSession(
            scheduled_for=parse_iso_date(
                scheduled_for, option_name="--scheduled-for"
            ),
            session_type=session_type,
            distance_meters=distance_km * 1000 if distance_km is not None else None,
            duration_seconds=round(duration_minutes * 60)
            if duration_minutes is not None
            else None,
            intensity=intensity,
            purpose=purpose,
        )
        with database.session() as session:
            plan = training_cycle_service(session).add_draft_session(plan_id, item)
            session.commit()
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    echo_domain(plan)


@cycle_app.command("plan-activate")
def cycle_plan_activate(
    plan_id: Annotated[str, typer.Option(help="训练计划内部 ID。")],
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    database = open_database(database_path)
    try:
        with database.session() as session:
            plan = training_cycle_service(session).activate_plan(plan_id)
            session.commit()
    except TrainingCycleError as error:
        raise typer.BadParameter(str(error)) from error
    echo_domain(plan)


@cycle_app.command("check-in")
def cycle_check_in(
    day: Annotated[str, typer.Option(help="反馈日期，格式 YYYY-MM-DD。")],
    fatigue: Annotated[int, typer.Option(min=1, max=5)],
    soreness: Annotated[int, typer.Option(min=0, max=10)],
    sleep_quality: Annotated[int, typer.Option(min=1, max=5)],
    readiness: Annotated[int | None, typer.Option(min=1, max=5)] = None,
    pain_area: Annotated[str | None, typer.Option()] = None,
    pain_severity: Annotated[int, typer.Option(min=0, max=10)] = 0,
    acute_symptoms: Annotated[
        str,
        typer.Option(
            help="可选急性症状枚举，逗号分隔；使用 recovery assess --help 查看说明。"
        ),
    ] = "",
    note: Annotated[str | None, typer.Option()] = None,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    database = open_database(database_path)
    try:
        check_in = DailyCheckIn(
            day=parse_iso_date(day, option_name="--day"),
            fatigue=fatigue,
            soreness=soreness,
            sleep_quality=sleep_quality,
            readiness=readiness,
            pain_area=pain_area,
            pain_severity=pain_severity,
            acute_symptoms=[
                value.strip()
                for value in acute_symptoms.split(",")
                if value.strip()
            ],
            note=note,
        )
        with database.session() as session:
            training_cycle_service(session).record_check_in(check_in)
            session.commit()
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    echo_domain(check_in)


@cycle_app.command("change-propose")
def cycle_change_propose(
    plan_id: Annotated[str, typer.Option()],
    session_id: Annotated[str, typer.Option()],
    proposed_by: Annotated[
        str, typer.Option(help="user/coach_orchestrator/plan_agent/recovery_agent。")
    ],
    reason: Annotated[str, typer.Option()],
    session_type: Annotated[str | None, typer.Option()] = None,
    distance_km: Annotated[float | None, typer.Option(min=0.001)] = None,
    duration_minutes: Annotated[float | None, typer.Option(min=0.01)] = None,
    intensity: Annotated[str | None, typer.Option()] = None,
    clear_distance: Annotated[
        bool, typer.Option(help="清除原计划距离。")
    ] = False,
    clear_duration: Annotated[
        bool, typer.Option(help="清除原计划时长。")
    ] = False,
    clear_intensity: Annotated[
        bool, typer.Option(help="清除原计划强度描述。")
    ] = False,
    purpose: Annotated[str | None, typer.Option()] = None,
    scheduled_for: Annotated[
        str | None, typer.Option(help="可选新日期，格式 YYYY-MM-DD。")
    ] = None,
    evidence_refs: Annotated[
        str, typer.Option(help="可选 evidence ID，逗号分隔。")
    ] = "",
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    database = open_database(database_path)
    try:
        change = PlanSessionPatch(
            session_id=session_id,
            scheduled_for=(
                parse_iso_date(scheduled_for, option_name="--scheduled-for")
                if scheduled_for is not None
                else None
            ),
            session_type=session_type,
            distance_meters=distance_km * 1000 if distance_km is not None else None,
            duration_seconds=round(duration_minutes * 60)
            if duration_minutes is not None
            else None,
            intensity=intensity,
            clear_distance=clear_distance,
            clear_duration=clear_duration,
            clear_intensity=clear_intensity,
            purpose=purpose,
        )
        with database.session() as session:
            proposal = training_cycle_service(session).propose_change(
                plan_id=plan_id,
                proposed_by=proposed_by,
                reason=reason,
                changes=[change],
                evidence_refs=[
                    value.strip() for value in evidence_refs.split(",") if value.strip()
                ],
            )
            session.commit()
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    echo_domain(proposal)


@cycle_app.command("change-decide")
def cycle_change_decide(
    proposal_id: Annotated[str, typer.Option()],
    decision: Annotated[str, typer.Option(help="approve 或 reject。")],
    comment: Annotated[str | None, typer.Option()] = None,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    database = open_database(database_path)
    try:
        with database.session() as session:
            plan, proposal, confirmation = training_cycle_service(session).decide_change(
                proposal_id=proposal_id,
                decision=decision,
                comment=comment,
            )
            session.commit()
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "plan": plan.model_dump(mode="json"),
                "proposal": proposal.model_dump(mode="json"),
                "confirmation": confirmation.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@cycle_app.command("snapshot")
def cycle_snapshot(
    goal_id: Annotated[str, typer.Option()],
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    database = open_database(database_path)
    try:
        with database.session() as session:
            snapshot = training_cycle_service(session).snapshot(goal_id)
    except TrainingCycleError as error:
        raise typer.BadParameter(str(error)) from error
    echo_domain(snapshot)


@recovery_app.command("assess")
def recovery_assess(
    goal_id: Annotated[str, typer.Option(help="训练目标内部 ID。")],
    assessed_at: Annotated[
        str | None,
        typer.Option(
            help="可选评估时间，必须为带时区 ISO 8601；不传则使用系统本地时间。"
        ),
    ] = None,
    provider_name: Annotated[
        str | None,
        typer.Option("--provider", help="可选活动来源，例如 coros 或 fixture。"),
    ] = None,
    lookback_days: Annotated[int, typer.Option(min=14, max=28)] = 14,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    """只做训练风险分层，不进行医疗诊断，也不直接修改计划。"""
    database = open_database(database_path)
    try:
        request = RecoveryAssessmentRequest(
            goal_id=goal_id,
            assessed_at=(
                parse_iso_datetime(assessed_at, option_name="--assessed-at")
                if assessed_at
                else datetime.now().astimezone()
            ),
            lookback_days=lookback_days,
            provider=provider_name,
        )
        with database.session() as session:
            result = execute_recovery_assessment(
                request,
                activities=ActivityRepository(session),
                check_ins=CheckInRepository(session),
                plans=TrainingPlanRepository(session),
                goals=TrainingGoalRepository(session),
            )
    except (ValueError, RecoveryAssessmentGoalNotFoundError) as error:
        raise typer.BadParameter(str(error)) from error
    echo_domain(result)


@planning_app.command("draft")
def planning_draft(
    goal_id: Annotated[str, typer.Option(help="训练目标内部 ID。")],
    week_start: Annotated[str, typer.Option(help="待规划周的周一，格式 YYYY-MM-DD。")],
    as_of: Annotated[
        str | None,
        typer.Option(help="可选知识截止时间；不传则使用系统本地时间。"),
    ] = None,
    provider_name: Annotated[
        str | None,
        typer.Option("--provider", help="可选活动来源，例如 coros 或 fixture。"),
    ] = None,
    lookback_days: Annotated[int, typer.Option(min=14, max=56)] = 28,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    """生成草案但不写入数据库，不会覆盖已有周计划。"""
    database = open_database(database_path)
    try:
        request = WeeklyPlanDraftRequest(
            goal_id=goal_id,
            week_start=parse_iso_date(week_start, option_name="--week-start"),
            as_of=(
                parse_iso_datetime(as_of, option_name="--as-of")
                if as_of
                else datetime.now().astimezone()
            ),
            lookback_days=lookback_days,
            provider=provider_name,
        )
        with database.session() as session:
            result = execute_weekly_plan_draft(
                request,
                activities=ActivityRepository(session),
                goals=TrainingGoalRepository(session),
                plans=TrainingPlanRepository(session),
                preferences=AthletePreferenceRepository(session),
            )
    except (ValueError, TrainingPlanningError) as error:
        raise typer.BadParameter(str(error)) from error
    echo_domain(result)


@planning_app.command("adjust")
def planning_adjust(
    goal_id: Annotated[str, typer.Option(help="训练目标内部 ID。")],
    assessed_at: Annotated[
        str | None,
        typer.Option(help="可选评估时间；不传则使用系统本地时间。"),
    ] = None,
    provider_name: Annotated[
        str | None,
        typer.Option("--provider", help="可选活动来源，例如 coros 或 fixture。"),
    ] = None,
    lookback_days: Annotated[int, typer.Option(min=14, max=28)] = 14,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    """先运行恢复 Skill，再生成计划提案参数；全程不保存或批准提案。"""
    database = open_database(database_path)
    try:
        moment = (
            parse_iso_datetime(assessed_at, option_name="--assessed-at")
            if assessed_at
            else datetime.now().astimezone()
        )
        recovery_request = RecoveryAssessmentRequest(
            goal_id=goal_id,
            assessed_at=moment,
            provider=provider_name,
            lookback_days=lookback_days,
        )
        with database.session() as session:
            recovery_result = execute_recovery_assessment(
                recovery_request,
                activities=ActivityRepository(session),
                check_ins=CheckInRepository(session),
                plans=TrainingPlanRepository(session),
                goals=TrainingGoalRepository(session),
            )
            result = execute_plan_adjustment(
                adjustment_request_from_recovery(recovery_result),
                goals=TrainingGoalRepository(session),
                plans=TrainingPlanRepository(session),
            )
    except (
        ValueError,
        RecoveryAssessmentGoalNotFoundError,
        TrainingPlanningError,
    ) as error:
        raise typer.BadParameter(str(error)) from error
    echo_domain(result)


@execution_app.command("compare")
def execution_compare(
    plan_id: Annotated[str, typer.Option(help="训练计划内部 ID。")],
    as_of: Annotated[
        str | None,
        typer.Option(help="可选知识截止时间；不传则使用系统本地时间。"),
    ] = None,
    provider_name: Annotated[
        str | None,
        typer.Option("--provider", help="可选活动来源，例如 coros 或 fixture。"),
    ] = None,
    date_tolerance_days: Annotated[int, typer.Option(min=0, max=3)] = 1,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    """只生成匹配建议，不写入计划，也不自动判定跳过。"""
    database = open_database(database_path)
    try:
        request = TrainingExecutionRequest(
            plan_id=plan_id,
            as_of=(
                parse_iso_datetime(as_of, option_name="--as-of")
                if as_of
                else datetime.now().astimezone()
            ),
            provider=provider_name,
            date_tolerance_days=date_tolerance_days,
        )
        with database.session() as session:
            result = execute_training_comparison(
                request,
                activities=ActivityRepository(session),
                plans=TrainingPlanRepository(session),
            )
    except (ValueError, TrainingExecutionError) as error:
        raise typer.BadParameter(str(error)) from error
    echo_domain(result)


@execution_app.command("decide")
def execution_decide(
    plan_id: Annotated[str, typer.Option(help="训练计划内部 ID。")],
    base_revision: Annotated[int, typer.Option(min=1)],
    session_id: Annotated[str, typer.Option(help="计划课内部 ID。")],
    decision: Annotated[
        str,
        typer.Option(help="confirm_match、mark_skipped 或 clear_execution。"),
    ],
    activity_id: Annotated[
        str | None,
        typer.Option(help="confirm_match 时必填的 RunCrew 内部活动 ID。"),
    ] = None,
    as_of: Annotated[
        str | None,
        typer.Option(help="可选确认时间；不传则使用系统本地时间。"),
    ] = None,
    comment: Annotated[str | None, typer.Option()] = None,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    """显式确认匹配、跳过或清除状态；使用 revision 防止过期写入。"""
    database = open_database(database_path)
    try:
        request = TrainingExecutionDecisionRequest(
            plan_id=plan_id,
            base_revision=base_revision,
            session_id=session_id,
            decision=decision,
            activity_id=activity_id,
            as_of=(
                parse_iso_datetime(as_of, option_name="--as-of")
                if as_of
                else datetime.now().astimezone()
            ),
            comment=comment,
        )
        with database.session() as session:
            result = confirm_training_execution(
                request,
                activities=ActivityRepository(session),
                plans=TrainingPlanRepository(session),
                confirmations=TrainingExecutionConfirmationRepository(session),
            )
            session.commit()
    except (ValueError, TrainingExecutionError) as error:
        raise typer.BadParameter(str(error)) from error
    echo_domain(result)


@coach_app.command("run")
def coach_run(
    goal_id: Annotated[str, typer.Option(help="训练目标内部 ID。")],
    plan_id: Annotated[str, typer.Option(help="要核对的训练计划内部 ID。")],
    as_of: Annotated[
        str | None,
        typer.Option(help="可选知识截止时间；不传则使用系统本地时间。"),
    ] = None,
    provider_name: Annotated[
        str | None,
        typer.Option("--provider", help="可选活动来源，例如 coros 或 fixture。"),
    ] = None,
    date_tolerance_days: Annotated[int, typer.Option(min=0, max=3)] = 1,
    recovery_lookback_days: Annotated[int, typer.Option(min=14, max=28)] = 14,
    max_steps: Annotated[int, typer.Option(min=1, max=12)] = 5,
    node_call_budget: Annotated[int, typer.Option(min=0, max=6)] = 3,
    max_retries: Annotated[int, typer.Option(min=0, max=3)] = 1,
    node_timeout_seconds: Annotated[float, typer.Option(min=0.01, max=60)] = 5.0,
    run_timeout_seconds: Annotated[float, typer.Option(min=0.01, max=120)] = 20.0,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    """运行只读 Coach 工作流；计划节点最多生成草案，不保存或批准变更。"""
    database = open_database(database_path)
    try:
        request = CoachAgentRunRequest(
            goal_id=goal_id,
            plan_id=plan_id,
            as_of=(
                parse_iso_datetime(as_of, option_name="--as-of")
                if as_of
                else datetime.now().astimezone()
            ),
            provider=provider_name,
            date_tolerance_days=date_tolerance_days,
            recovery_lookback_days=recovery_lookback_days,
            max_steps=max_steps,
            node_call_budget=node_call_budget,
            max_retries=max_retries,
            node_timeout_seconds=node_timeout_seconds,
            run_timeout_seconds=run_timeout_seconds,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error

    with database.session() as session:
        activities = ActivityRepository(session)
        plans = TrainingPlanRepository(session)
        goals = TrainingGoalRepository(session)
        check_ins = CheckInRepository(session)

        async def execution_tool(node_request: TrainingExecutionRequest):
            return execute_training_comparison(
                node_request,
                activities=activities,
                plans=plans,
            )

        async def recovery_tool(node_request: RecoveryAssessmentRequest):
            return execute_recovery_assessment(
                node_request,
                activities=activities,
                check_ins=check_ins,
                plans=plans,
                goals=goals,
            )

        async def plan_tool(node_request):
            return execute_plan_adjustment(
                node_request,
                goals=goals,
                plans=plans,
            )

        result = asyncio.run(
            CoachOrchestratorHarness().run(
                request,
                tools=CoachNodeTools(
                    execution=execution_tool,
                    recovery=recovery_tool,
                    planning=plan_tool,
                ),
            )
        )
    echo_domain(result)


@app.command("demo-seed")
def demo_seed_command(
    database_path: Annotated[
        Path,
        typer.Option("--db", help="仅允许写入 data/private/demo 下的合成演示数据库。"),
    ] = Path("data/private/demo/runcrew-demo.db"),
    reset: Annotated[
        bool,
        typer.Option("--reset", help="明确重建已有演示数据库。"),
    ] = False,
    as_of: Annotated[
        str | None,
        typer.Option(help="可选演示锚点时间；默认使用当前本地时间。"),
    ] = None,
) -> None:
    """准备不含真实活动、账号或模型调用的本地求职演示数据库。"""
    private_demo_root = Path("data/private/demo").resolve()
    resolved = database_path.resolve()
    if not resolved.is_relative_to(private_demo_root):
        raise typer.BadParameter("演示数据库必须位于 data/private/demo 目录内")
    try:
        summary = prepare_demo_database(
            resolved,
            reset=reset,
            as_of=(
                parse_iso_datetime(as_of, option_name="--as-of")
                if as_of
                else None
            ),
        )
    except (DemoSeedError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    echo_domain(summary)


@app.command("demo")
def demo_command(
    port: Annotated[
        int,
        typer.Option(min=1024, max=65535, help="本地演示界面端口。"),
    ] = 8766,
    database_path: Annotated[
        Path,
        typer.Option("--db", help="活动与本地对话使用的 SQLite 数据库路径。"),
    ] = Path("data/runcrew.db"),
    evaluation_directory: Annotated[
        Path,
        typer.Option("--eval-dir", help="私有评测报告目录。"),
    ] = Path("data/private/evals"),
    open_browser: Annotated[
        bool,
        typer.Option(
            "--open-browser/--no-open-browser",
            help="服务启动后是否尝试打开默认浏览器。",
        ),
    ] = True,
) -> None:
    """启动只绑定 127.0.0.1 的跑步数据对话与工程观测界面。"""
    serve_demo(
        port=port,
        database_path=database_path,
        evaluation_directory=evaluation_directory,
        open_browser=open_browser,
    )


@app.command("sync")
def sync_command(
    provider_name: Annotated[
        str, typer.Option("--provider", help="Activity provider name.")
    ] = "fixture",
    days: Annotated[int, typer.Option(min=1, help="Number of days to sync.")] = 30,
    detail_limit: Annotated[
        int, typer.Option(min=0, help="Number of activities to hydrate with details.")
    ] = 1,
    fixture_path: Annotated[
        Path, typer.Option("--fixture", help="Fixture JSON used by fixture provider.")
    ] = Path("tests/fixtures/coros_activities.json"),
    database_path: Annotated[
        Path, typer.Option("--db", help="SQLite database path.")
    ] = Path("data/runcrew.db"),
    callback_port: Annotated[
        int, typer.Option(help="Local OAuth callback port for COROS.")
    ] = 8765,
    open_browser: Annotated[
        bool,
        typer.Option(
            "--open-browser/--no-open-browser",
            help="Open the COROS authorization URL in the default browser.",
        ),
    ] = True,
    debug_payload_path: Annotated[
        Path | None,
        typer.Option(
            "--debug-payload",
            help="Private, git-ignored file for capturing a failed COROS payload.",
        ),
    ] = None,
) -> None:
    database = open_database(database_path)
    if provider_name == "fixture":
        provider = FixtureActivityProvider(fixture_path)

        async def execute_sync():
            with database.session() as session:
                return await sync_activities(
                    session=session,
                    provider=provider,
                    days=days,
                    detail_limit=detail_limit,
                )

    elif provider_name == "coros":
        coros_provider = CorosActivityProvider(
            callback_port=callback_port,
            open_browser=open_browser,
            authorization_url_handler=lambda url: typer.echo(
                f"Open this COROS authorization URL:\n{url}"
            ),
            debug_payload_path=debug_payload_path,
        )

        async def execute_sync():
            await coros_provider.connect()
            try:
                with database.session() as session:
                    return await sync_activities(
                        session=session,
                        provider=coros_provider,
                        days=days,
                        detail_limit=detail_limit,
                    )
            finally:
                await coros_provider.aclose()

    else:
        raise typer.BadParameter("Supported providers: fixture, coros")

    result = asyncio.run(execute_sync())
    typer.echo(
        "Sync completed: "
        f"fetched={result.fetched_count}, "
        f"inserted={result.inserted_count}, "
        f"updated={result.updated_count}, "
        f"detailed={result.detailed_count}, "
        f"detail_errors={result.detail_error_count}"
    )


@activities_app.command("list")
def list_activities(
    limit: Annotated[int, typer.Option(min=1, max=100)] = 20,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    database = open_database(database_path)
    with database.session() as session:
        activities = ActivityRepository(session).list(limit=limit)
    if not activities:
        typer.echo("No activities found. Run `runcrew sync --provider fixture` first.")
        return
    for activity in activities:
        distance = (
            f"{activity.distance_meters / 1000:.2f} km"
            if activity.distance_meters is not None
            else "distance unavailable"
        )
        typer.echo(
            f"{activity.started_at.isoformat()} | {activity.sport_type.value} | "
            f"{distance} | {activity.source_ref.external_id}"
        )


@activities_app.command("review")
def review_activity(
    latest: Annotated[
        bool, typer.Option("--latest", help="Review the latest stored activity.")
    ] = False,
    external_id: Annotated[
        str | None, typer.Option("--external-id", help="Provider activity ID.")
    ] = None,
    provider_name: Annotated[
        str | None, typer.Option("--provider", help="Filter by provider.")
    ] = None,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    if not latest and external_id is None:
        raise typer.BadParameter("Pass --latest or --external-id.")
    database = open_database(database_path)
    with database.session() as session:
        repository = ActivityRepository(session)
        activity = (
            repository.latest(provider=provider_name)
            if latest
            else repository.get_by_external_id(
                provider_name or "fixture", external_id or ""
            )
        )
    if activity is None:
        raise typer.BadParameter("Activity not found.")
    typer.echo(build_activity_review(activity).model_dump_json(indent=2))


@training_app.command("review")
def review_training(
    latest: Annotated[
        bool, typer.Option("--latest", help="Review the latest stored activity.")
    ] = False,
    external_id: Annotated[
        str | None, typer.Option("--external-id", help="Provider activity ID.")
    ] = None,
    provider_name: Annotated[
        str | None, typer.Option("--provider", help="Filter by provider.")
    ] = None,
    lookback_days: Annotated[
        int, typer.Option(min=14, max=90, help="History window for replay context.")
    ] = 28,
    planned_distance_km: Annotated[
        float | None,
        typer.Option(min=0.01, help="Optional planned distance in kilometers."),
    ] = None,
    planned_duration_minutes: Annotated[
        float | None,
        typer.Option(min=0.01, help="Optional planned duration in minutes."),
    ] = None,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    if not latest and external_id is None:
        raise typer.BadParameter("Pass --latest or --external-id.")
    database = open_database(database_path)
    with database.session() as session:
        repository = ActivityRepository(session)
        target = (
            repository.latest(provider=provider_name)
            if latest
            else repository.get_by_external_id(
                provider_name or "fixture", external_id or ""
            )
        )
        if target is None:
            raise typer.BadParameter("Activity not found.")

    plan = None
    if planned_distance_km is not None or planned_duration_minutes is not None:
        plan = PlannedSession(
            distance_meters=planned_distance_km * 1000
            if planned_distance_km is not None
            else None,
            duration_seconds=round(planned_duration_minutes * 60)
            if planned_duration_minutes is not None
            else None,
        )
    request = TrainingReviewRequest(
        target_activity_id=target.id,
        lookback_days=lookback_days,
        planned_session=plan,
    )
    with database.session() as session:
        result = execute_training_review(
            request,
            store=ActivityRepository(session),
        )
    typer.echo(result.model_dump_json(indent=2))


@agent_app.command("review")
def run_review_agent(
    latest: Annotated[
        bool, typer.Option("--latest", help="复盘最新一条活动。")
    ] = False,
    external_id: Annotated[
        str | None, typer.Option("--external-id", help="Provider 活动 ID。")
    ] = None,
    provider_name: Annotated[
        str | None, typer.Option("--provider", help="按 Provider 过滤。")
    ] = None,
    lookback_days: Annotated[
        int, typer.Option(min=14, max=90, help="回放使用的历史窗口天数。")
    ] = 28,
    planned_distance_km: Annotated[
        float | None,
        typer.Option(min=0.01, help="可选计划距离，单位为公里。"),
    ] = None,
    planned_duration_minutes: Annotated[
        float | None,
        typer.Option(min=0.01, help="可选计划时长，单位为分钟。"),
    ] = None,
    max_steps: Annotated[
        int, typer.Option(min=1, max=12, help="Agent 最大策略步骤数。")
    ] = 4,
    tool_call_budget: Annotated[
        int, typer.Option(min=0, max=3, help="业务工具逻辑调用预算。")
    ] = 1,
    max_retries: Annotated[
        int, typer.Option(min=0, max=3, help="工具超时或瞬时错误重试次数。")
    ] = 1,
    tool_timeout_seconds: Annotated[
        float, typer.Option(min=0.01, max=60, help="单次工具尝试超时秒数。")
    ] = 5.0,
    run_timeout_seconds: Annotated[
        float, typer.Option(min=0.01, max=120, help="整个 Agent Run 超时秒数。")
    ] = 15.0,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    if not latest and external_id is None:
        raise typer.BadParameter("Pass --latest or --external-id.")
    database = open_database(database_path)
    with database.session() as session:
        repository = ActivityRepository(session)
        target = (
            repository.latest(provider=provider_name)
            if latest
            else repository.get_by_external_id(
                provider_name or "fixture", external_id or ""
            )
        )
    if target is None:
        raise typer.BadParameter("Activity not found.")

    plan = None
    if planned_distance_km is not None or planned_duration_minutes is not None:
        plan = PlannedSession(
            distance_meters=planned_distance_km * 1000
            if planned_distance_km is not None
            else None,
            duration_seconds=round(planned_duration_minutes * 60)
            if planned_duration_minutes is not None
            else None,
        )
    review_request = TrainingReviewRequest(
        target_activity_id=target.id,
        lookback_days=lookback_days,
        planned_session=plan,
    )
    run_request = ReviewAgentRunRequest(
        review_request=review_request,
        max_steps=max_steps,
        tool_call_budget=tool_call_budget,
        max_retries=max_retries,
        tool_timeout_seconds=tool_timeout_seconds,
        run_timeout_seconds=run_timeout_seconds,
    )

    async def review_tool(request: TrainingReviewRequest):
        def execute():
            with database.session() as session:
                return execute_training_review(
                    request,
                    store=ActivityRepository(session),
                )

        return await asyncio.to_thread(execute)

    result = asyncio.run(ReviewAgentHarness().run(run_request, tool=review_tool))
    typer.echo(result.model_dump_json(indent=2))
    if result.status != "succeeded":
        raise typer.Exit(code=1)


@evaluation_app.command("review-agent")
def evaluate_review_agent(
    cases_path: Annotated[
        Path,
        typer.Option("--cases", help="评测用例 JSON 路径。"),
    ] = Path("evals/review_agent/cases.json"),
    output_path: Annotated[
        Path | None,
        typer.Option(
            "--output",
            help="可选报告路径；为保护未来真实评测数据，只允许写入 data/private。",
        ),
    ] = None,
) -> None:
    if not cases_path.is_file():
        raise typer.BadParameter(f"Evaluation suite not found: {cases_path}")
    suite = load_review_agent_suite(cases_path)
    report = asyncio.run(evaluate_review_agent_suite(suite))
    payload = report.model_dump_json(indent=2)
    if output_path is not None:
        private_root = Path("data/private").resolve()
        resolved_output = output_path.resolve()
        if not resolved_output.is_relative_to(private_root):
            raise typer.BadParameter("Evaluation reports must stay under data/private.")
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        resolved_output.write_text(payload + "\n", encoding="utf-8")
    typer.echo(payload)
    if not report.meets_baseline:
        raise typer.Exit(code=1)


@evaluation_app.command("deepseek-smoke")
def evaluate_deepseek_smoke(
    confirm_paid_api: Annotated[
        bool,
        typer.Option(
            "--confirm-paid-api",
            help="明确确认本命令会调用 DeepSeek 并产生少量费用。",
        ),
    ] = False,
    max_estimated_cost_usd: Annotated[
        float | None,
        typer.Option(
            "--max-estimated-cost-usd",
            min=0.000001,
            max=1,
            help="本次 Policy 允许的估算费用上限（美元），必须显式提供。",
        ),
    ] = None,
    cases_path: Annotated[
        Path,
        typer.Option("--cases", help="评测用例 JSON 路径。"),
    ] = Path("evals/review_agent/cases.json"),
    output_path: Annotated[
        Path | None,
        typer.Option("--output", help="可选报告路径，只允许写入 data/private。"),
    ] = None,
) -> None:
    if not confirm_paid_api:
        raise typer.BadParameter("必须显式传入 --confirm-paid-api 才允许外部模型调用。")
    if max_estimated_cost_usd is None:
        raise typer.BadParameter("必须显式设置 --max-estimated-cost-usd。")
    if not cases_path.is_file():
        raise typer.BadParameter(f"Evaluation suite not found: {cases_path}")
    try:
        config = DeepSeekPolicyConfig.from_env().model_copy(
            update={"max_estimated_cost_usd": max_estimated_cost_usd}
        )
    except DeepSeekPolicyError as error:
        raise typer.BadParameter(str(error)) from error

    suite = load_review_agent_suite(cases_path)
    smoke_case = next(
        (case for case in suite.cases if case.id == "complete_training_review"),
        None,
    )
    if smoke_case is None:
        raise typer.BadParameter("Evaluation suite 缺少 complete_training_review。")
    smoke_case = smoke_case.model_copy(
        update={
            "run": smoke_case.run.model_copy(
                update={"run_timeout_seconds": 60.0}
            )
        }
    )
    smoke_suite = suite.model_copy(update={"cases": [smoke_case]})
    report = asyncio.run(
        evaluate_review_agent_suite(
            smoke_suite,
            default_policy_factory=lambda: DeepSeekReviewPolicy(config),
            policy_name=f"{config.model}-live-nonthinking-smoke",
        )
    )
    payload = report.model_dump_json(indent=2)
    if output_path is not None:
        private_root = Path("data/private").resolve()
        resolved_output = output_path.resolve()
        if not resolved_output.is_relative_to(private_root):
            raise typer.BadParameter("Evaluation reports must stay under data/private.")
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        resolved_output.write_text(payload + "\n", encoding="utf-8")
    typer.echo(payload)
    if not report.meets_baseline:
        raise typer.Exit(code=1)


@evaluation_app.command("deepseek-suite")
def evaluate_deepseek_suite(
    confirm_paid_api: Annotated[
        bool,
        typer.Option(
            "--confirm-paid-api",
            help="明确确认本命令会运行完整 DeepSeek 合成评测并产生费用。",
        ),
    ] = False,
    max_total_estimated_cost_usd: Annotated[
        float | None,
        typer.Option(
            "--max-total-estimated-cost-usd",
            min=0.000001,
            max=1,
            help="完整 Suite 共享的估算费用上限（美元），必须显式提供。",
        ),
    ] = None,
    cases_path: Annotated[
        Path,
        typer.Option("--cases", help="评测用例 JSON 路径。"),
    ] = Path("evals/review_agent/cases.json"),
    output_path: Annotated[
        Path | None,
        typer.Option("--output", help="可选报告路径，只允许写入 data/private。"),
    ] = None,
) -> None:
    if not confirm_paid_api:
        raise typer.BadParameter("必须显式传入 --confirm-paid-api 才允许完整模型评测。")
    if max_total_estimated_cost_usd is None:
        raise typer.BadParameter("必须显式设置 --max-total-estimated-cost-usd。")
    if not cases_path.is_file():
        raise typer.BadParameter(f"Evaluation suite not found: {cases_path}")
    try:
        config = DeepSeekPolicyConfig.from_env().model_copy(
            update={"max_estimated_cost_usd": max_total_estimated_cost_usd}
        )
    except DeepSeekPolicyError as error:
        raise typer.BadParameter(str(error)) from error

    cost_budget = DeepSeekCostBudget(max_total_estimated_cost_usd)
    suite = load_review_agent_suite(cases_path)
    report = asyncio.run(
        evaluate_review_agent_suite(
            suite,
            default_policy_factory=lambda: DeepSeekReviewPolicy(
                config,
                cost_budget=cost_budget,
            ),
            policy_name=f"{config.model}-live-nonthinking-suite",
        )
    )
    payload = report.model_dump_json(indent=2)
    if output_path is not None:
        private_root = Path("data/private").resolve()
        resolved_output = output_path.resolve()
        if not resolved_output.is_relative_to(private_root):
            raise typer.BadParameter("Evaluation reports must stay under data/private.")
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        resolved_output.write_text(payload + "\n", encoding="utf-8")
    typer.echo(payload)
    if not report.meets_baseline:
        raise typer.Exit(code=1)


@evaluation_app.command("running-chat")
def evaluate_running_chat(
    cases_path: Annotated[
        Path,
        typer.Option("--cases", help="多轮聊天评测用例 JSON 路径。"),
    ] = Path("evals/running_chat/cases.json"),
    output_path: Annotated[
        Path | None,
        typer.Option("--output", help="可选报告路径，只允许写入 data/private。"),
    ] = None,
) -> None:
    """运行不调用外部模型的自由对话契约基线。"""
    if not cases_path.is_file():
        raise typer.BadParameter(f"Chat evaluation suite not found: {cases_path}")
    suite = load_chat_evaluation_suite(cases_path)
    report = asyncio.run(evaluate_chat_suite(suite))
    payload = report.model_dump_json(indent=2)
    _write_private_evaluation(output_path, payload)
    typer.echo(payload)
    if not report.meets_baseline:
        raise typer.Exit(code=1)


@evaluation_app.command("coach-agent")
def evaluate_coach_agent(
    cases_path: Annotated[
        Path,
        typer.Option("--cases", help="Coach 多 Agent 评测用例 JSON 路径。"),
    ] = Path("evals/coach_agent/cases.json"),
    output_path: Annotated[
        Path | None,
        typer.Option("--output", help="可选报告路径，只允许写入 data/private。"),
    ] = None,
) -> None:
    """运行不调用外部模型的 Coach 多 Agent 版本化评测。"""
    if not cases_path.is_file():
        raise typer.BadParameter(f"Coach evaluation suite not found: {cases_path}")
    suite = load_coach_agent_suite(cases_path)
    report = asyncio.run(evaluate_coach_agent_suite(suite))
    payload = report.model_dump_json(indent=2)
    _write_private_evaluation(output_path, payload)
    typer.echo(payload)
    if not report.meets_baseline:
        raise typer.Exit(code=1)


@evaluation_app.command("deepseek-chat-suite")
def evaluate_deepseek_chat_suite(
    confirm_paid_api: Annotated[
        bool,
        typer.Option(
            "--confirm-paid-api",
            help="明确确认本命令会发送合成聊天上下文并产生少量费用。",
        ),
    ] = False,
    max_total_estimated_cost_usd: Annotated[
        float | None,
        typer.Option(
            "--max-total-estimated-cost-usd",
            min=0.000001,
            max=1,
            help="整套多轮聊天评测共享的估算费用上限（美元）。",
        ),
    ] = None,
    cases_path: Annotated[
        Path,
        typer.Option("--cases", help="多轮聊天评测用例 JSON 路径。"),
    ] = Path("evals/running_chat/cases.json"),
    output_path: Annotated[
        Path | None,
        typer.Option("--output", help="可选报告路径，只允许写入 data/private。"),
    ] = None,
) -> None:
    """在无私人数据的同一套多轮题目上评测真实 DeepSeek。"""
    if not confirm_paid_api:
        raise typer.BadParameter("必须显式传入 --confirm-paid-api 才允许聊天模型评测。")
    if max_total_estimated_cost_usd is None:
        raise typer.BadParameter("必须显式设置 --max-total-estimated-cost-usd。")
    if not cases_path.is_file():
        raise typer.BadParameter(f"Chat evaluation suite not found: {cases_path}")
    try:
        config = DeepSeekPolicyConfig.from_env().model_copy(
            update={"max_estimated_cost_usd": max_total_estimated_cost_usd}
        )
    except DeepSeekPolicyError as error:
        raise typer.BadParameter(str(error)) from error
    cost_budget = DeepSeekCostBudget(max_total_estimated_cost_usd)
    suite = load_chat_evaluation_suite(cases_path)
    report = asyncio.run(
        evaluate_chat_suite(
            suite,
            policy_factory=lambda: DeepSeekGroundedChatPolicy(
                config,
                cost_budget=cost_budget,
            ),
            policy_name=f"{config.model}-live-flexible-chat-suite",
        )
    )
    payload = report.model_dump_json(indent=2)
    _write_private_evaluation(output_path, payload)
    typer.echo(payload)
    if not report.meets_baseline:
        raise typer.Exit(code=1)


def _write_private_evaluation(output_path: Path | None, payload: str) -> None:
    if output_path is None:
        return
    private_root = Path("data/private").resolve()
    resolved_output = output_path.resolve()
    if not resolved_output.is_relative_to(private_root):
        raise typer.BadParameter("Evaluation reports must stay under data/private.")
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(payload + "\n", encoding="utf-8")


if __name__ == "__main__":
    app()
