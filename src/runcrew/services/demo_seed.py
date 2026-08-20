from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from runcrew.domain.activity import (
    ActivityDetail,
    ActivitySummary,
    Lap,
    SourceProvider,
    SourceRef,
    SportType,
)
from runcrew.domain.demo import DemoSeedSummary
from runcrew.domain.memory import AthletePreference
from runcrew.domain.training_cycle import (
    DailyCheckIn,
    PlanSession,
    TrainingGoal,
    TrainingPlan,
)
from runcrew.domain.training_execution import TrainingExecutionConfirmation
from runcrew.storage.database import Database
from runcrew.storage.repositories import (
    ActivityRepository,
    AthletePreferenceRepository,
    CheckInRepository,
    TrainingExecutionConfirmationRepository,
    TrainingGoalRepository,
    TrainingPlanRepository,
)


class DemoSeedError(ValueError):
    pass


def prepare_demo_database(
    database_path: Path,
    *,
    reset: bool = False,
    as_of: datetime | None = None,
) -> DemoSeedSummary:
    """创建完全合成、可重复的求职演示数据库。"""

    resolved = database_path.resolve()
    if resolved.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise DemoSeedError("演示数据库必须使用 .db、.sqlite 或 .sqlite3 后缀")
    if resolved.exists() and not reset:
        raise DemoSeedError("演示数据库已经存在；确认重置时请显式传入 --reset")
    if resolved.exists():
        resolved.unlink()
    resolved.parent.mkdir(parents=True, exist_ok=True)

    anchor = (as_of or datetime.now().astimezone()).replace(microsecond=0)
    if anchor.tzinfo is None or anchor.utcoffset() is None:
        raise DemoSeedError("演示锚点时间必须包含时区")
    week_start = anchor.date() - timedelta(days=anchor.date().weekday())
    completed_day = (
        anchor.date()
        if anchor.date().weekday() == 0
        else anchor.date() - timedelta(days=1)
    )
    long_run_day = week_start + timedelta(days=6)
    quality_day = anchor.date() + timedelta(days=1)
    goal_id = _stable_id("goal", anchor.date().isoformat())
    plan_id = _stable_id("plan", week_start.isoformat())
    preference_id = _stable_id("preference", "preferred_long_run_weekday")
    latest_activity_id = _stable_id("activity", completed_day.isoformat())

    historical = _historical_activities(anchor, completed_day, latest_activity_id)
    current_run = historical[-1]
    planned_sessions = [
        PlanSession(
            id=_stable_id("session", f"{week_start}:completed"),
            scheduled_for=completed_day,
            session_type="easy",
            distance_meters=8000,
            duration_seconds=2700,
            intensity="轻松，可以完整交谈",
            purpose="建立本周有氧训练基础。",
            status="completed",
            linked_activity_id=current_run.id,
        )
    ]
    if quality_day < long_run_day:
        planned_sessions.append(
            PlanSession(
                id=_stable_id("session", f"{week_start}:tempo"),
                scheduled_for=quality_day,
                session_type="tempo",
                duration_seconds=2400,
                intensity="中等偏高但可控",
                purpose="在恢复允许时进行受控节奏刺激。",
            )
        )
    planned_sessions.append(
        PlanSession(
            id=_stable_id("session", f"{week_start}:long"),
            scheduled_for=long_run_day,
            session_type="long_run",
            duration_seconds=3600,
            intensity="低强度耐力，保持可完整交谈",
            purpose="建立有氧耐力，不追求目标配速。",
        )
    )
    current_plan = TrainingPlan(
        id=plan_id,
        goal_id=goal_id,
        week_start=week_start,
        status="active",
        revision=2,
        source="deterministic",
        sessions=planned_sessions,
        created_at=anchor - timedelta(days=5),
        updated_at=anchor - timedelta(days=2),
    )
    goal = TrainingGoal(
        id=goal_id,
        name="十公里稳定完赛 · 演示目标",
        event_type="10k",
        target_date=anchor.date() + timedelta(days=84),
        target_time_seconds=3000,
        available_weekdays=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        created_at=anchor - timedelta(days=35),
        updated_at=anchor - timedelta(days=5),
    )
    preference = AthletePreference(
        id=preference_id,
        key="preferred_long_run_weekday",
        value="sun",
        source_ref="demo-seed:explicit-user-setting",
        confirmed_at=anchor - timedelta(days=30),
        valid_from=anchor - timedelta(days=30),
        created_at=anchor - timedelta(days=30),
        updated_at=anchor - timedelta(days=30),
    )
    check_in = DailyCheckIn(
        id=_stable_id("check-in", anchor.date().isoformat()),
        day=anchor.date(),
        fatigue=4,
        soreness=5,
        sleep_quality=2,
        readiness=2,
        pain_area="小腿后侧",
        pain_severity=3,
        note="演示数据：连续训练后主观疲劳偏高，无急性红旗。",
        created_at=anchor,
    )
    confirmation = TrainingExecutionConfirmation(
        id=_stable_id("execution", current_plan.sessions[0].id),
        plan_id=plan_id,
        base_revision=1,
        applied_revision=2,
        session_id=current_plan.sessions[0].id,
        decision="confirm_match",
        activity_id=current_run.id,
        comment="演示数据：用户确认该活动对应周一轻松跑。",
        created_at=anchor - timedelta(days=1),
    )

    database = Database(f"sqlite:///{resolved.as_posix()}")
    try:
        database.create_schema()
        with database.session() as session:
            activities = ActivityRepository(session)
            for activity in historical:
                activities.upsert(activity)
            TrainingGoalRepository(session).save(goal)
            TrainingPlanRepository(session).save(current_plan)
            AthletePreferenceRepository(session).save(preference)
            CheckInRepository(session).save(check_in)
            TrainingExecutionConfirmationRepository(session).save(confirmation)
            session.commit()
    finally:
        database.engine.dispose()

    return DemoSeedSummary(
        database_path=str(resolved),
        generated_at=datetime.now(timezone.utc),
        anchor_day=anchor.date(),
        activity_count=len(historical),
        goal_id=goal_id,
        plan_id=plan_id,
        preference_id=preference_id,
        latest_activity_id=latest_activity_id,
        launch_command=(
            f'.\\.venv\\Scripts\\runcrew.exe demo --db "{resolved}"'
        ),
    )


def _historical_activities(
    anchor: datetime,
    completed_day: date,
    latest_activity_id: str,
) -> list[ActivitySummary | ActivityDetail]:
    offsets = [28, 24, 21, 17, 14, 10, 7]
    result: list[ActivitySummary | ActivityDetail] = []
    for index, days_ago in enumerate(offsets, start=1):
        started_at = datetime.combine(
            anchor.date() - timedelta(days=days_ago),
            time(hour=6 + index % 2, minute=20),
            tzinfo=anchor.tzinfo,
        )
        distance = 5000 + (index % 4) * 1000
        pace = 355 - index * 2
        duration = round(distance / 1000 * pace)
        external_id = f"demo-history-{started_at.date().isoformat()}-{index}"
        result.append(
            ActivitySummary(
                id=_stable_id("activity", external_id),
                source_ref=_source_ref(external_id, anchor),
                sport_type=SportType.RUN,
                started_at=started_at,
                duration_seconds=duration,
                distance_meters=distance,
                average_pace_seconds_per_km=pace,
                average_heart_rate=143 + index,
                training_load=48 + index * 5,
                title=f"合成历史跑步 {index}",
            )
        )
    latest_started_at = datetime.combine(
        completed_day,
        time(hour=6, minute=30),
        tzinfo=anchor.tzinfo,
    )
    if latest_started_at > anchor:
        latest_started_at = anchor - timedelta(hours=1)
    lap_paces = [337, 340, 338, 341, 339, 342, 340, 341]
    external_id = f"demo-current-{completed_day.isoformat()}"
    result.append(
        ActivityDetail(
            id=latest_activity_id,
            source_ref=_source_ref(external_id, anchor),
            sport_type=SportType.RUN,
            started_at=latest_started_at,
            duration_seconds=2718,
            distance_meters=8020,
            average_pace_seconds_per_km=338.9,
            average_heart_rate=151,
            training_load=92,
            title="晨间轻松跑 · 演示数据",
            elevation_gain_meters=36,
            average_cadence=176,
            max_heart_rate=166,
            laps=[
                Lap(
                    index=index,
                    duration_seconds=pace,
                    distance_meters=1000,
                    average_pace_seconds_per_km=pace,
                    average_heart_rate=144 + index * 2,
                    average_cadence=175 + index % 3,
                )
                for index, pace in enumerate(lap_paces, start=1)
            ],
            provider_metadata={"fixture_version": "runcrew-demo/1.0"},
        )
    )
    return result


def _source_ref(external_id: str, fetched_at: datetime) -> SourceRef:
    return SourceRef(
        provider=SourceProvider.FIXTURE,
        external_id=external_id,
        fetched_at=fetched_at,
        raw_payload_hash=hashlib.sha256(external_id.encode("utf-8")).hexdigest(),
    )


def _stable_id(kind: str, value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"runcrew-demo:{kind}:{value}"))
