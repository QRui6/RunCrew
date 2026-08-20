from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from runcrew.domain.coach import CoachAgentRunRequest, CoachAgentRunResult
from runcrew.domain.memory import (
    MemoryContextBuildRequest,
    AthletePreference,
    AthletePreferenceArchiveSubmission,
    AthletePreferenceSubmission,
    WeeklyTrainingMemory,
    WeeklyTrainingMemoryBuildResult,
)
from runcrew.domain.training_cycle import DailyCheckIn, TrainingGoal, TrainingPlan
from runcrew.domain.training_execution import ExecutionConfirmationResult, TrainingExecutionRequest
from runcrew.domain.training_operations import (
    CheckInSubmission,
    CoachRunAudit,
    CoachRunDecisionRequest,
    CoachRunDecisionResult,
    CoachRunSubmission,
    CoachRunView,
    ExecutionDecisionSubmission,
    TrainingGoalSubmission,
    TrainingOperationsBootstrap,
    TrainingOperationsGoalView,
    TrainingWeekView,
    WeeklyPlanActivationRequest,
    WeeklyPlanActivationResult,
    WeeklyPlanDraftSubmission,
    WeeklyTrainingMemoryBuildSubmission,
    WeekProgressSummary,
)
from runcrew.harness import CoachNodeTools, CoachOrchestratorHarness
from runcrew.services.athlete_memory import (
    AthleteMemoryError,
    archive_athlete_preference,
    confirm_athlete_preference,
    preferences_for_display,
)
from runcrew.services.recovery_assessment import execute_recovery_assessment
from runcrew.services.runtime_observability import RuntimeTraceService
from runcrew.services.training_cycle import TrainingCycleError, TrainingCycleService
from runcrew.services.training_execution import (
    TrainingExecutionError,
    confirm_training_execution,
    execute_training_comparison,
)
from runcrew.services.training_planning import (
    TrainingPlanningError,
    execute_plan_adjustment,
    execute_weekly_plan_draft,
)
from runcrew.services.weekly_training_memory import (
    WeeklyTrainingMemoryError,
    invalidate_weekly_training_memory,
    refresh_weekly_training_memory,
)
from runcrew.services.memory_context import load_agent_memory_context
from runcrew.storage.database import Database
from runcrew.storage.repositories import (
    ActivityRepository,
    AthletePreferenceRepository,
    CheckInRepository,
    CoachRunRepository,
    PlanChangeRepository,
    TrainingGoalRepository,
    TrainingExecutionConfirmationRepository,
    TrainingPlanRepository,
    WeeklyTrainingMemoryRepository,
)


class TrainingOperationsError(RuntimeError):
    pass


class TrainingOperationsService:
    """把训练闭环暴露给本地产品，同时把 Coach 草案与正式写入隔开。"""

    def __init__(
        self,
        *,
        database_path: Path = Path("data/runcrew.db"),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = database_path
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.database = Database(f"sqlite:///{database_path.resolve().as_posix()}")
        self.database.create_schema()
        self.runtime_traces = RuntimeTraceService(self.database, clock=self._clock)

    def _now(self) -> datetime:
        current = self._clock()
        if current.tzinfo is None or current.utcoffset() is None:
            raise TrainingOperationsError("clock 必须返回包含时区的时间。")
        return current

    def bootstrap(self) -> TrainingOperationsBootstrap:
        with self.database.session() as session:
            goals = TrainingGoalRepository(session).list(limit=20)
            plans = TrainingPlanRepository(session)
            check_ins = CheckInRepository(session).recent(limit=1)
            changes = PlanChangeRepository(session)
            now = self._now()
            current_week = now.astimezone().date()
            current_week -= timedelta(days=current_week.weekday())
            def visible_plan(goal_id: str):
                current = plans.for_goal_week(goal_id, current_week)
                if current is not None and current.status == "active":
                    return current
                future = plans.active_from_week(goal_id, current_week, limit=1)
                return future[0] if future else plans.active_for_goal(goal_id)
            views = [
                TrainingOperationsGoalView(
                    goal=goal,
                    active_plan=visible_plan(goal.id),
                    latest_check_in=check_ins[0] if check_ins else None,
                    pending_proposals=changes.pending_for_goal(goal.id),
                )
                for goal in goals
                if goal.status == "active"
            ]
            recent_runs = CoachRunRepository(session).recent(limit=10)
            providers = sorted(
                {item.source_ref.provider for item in ActivityRepository(session).list(limit=100)},
                key=lambda item: item.value,
            )
            athlete_preferences = preferences_for_display(
                AthletePreferenceRepository(session)
            )
        return TrainingOperationsBootstrap(
            generated_at=now,
            goals=views,
            providers=providers,
            recent_coach_runs=recent_runs,
            athlete_preferences=athlete_preferences,
        )

    def confirm_preference(
        self, submission: AthletePreferenceSubmission
    ) -> AthletePreference:
        with self.database.session() as session:
            try:
                preference = confirm_athlete_preference(
                    submission,
                    preferences=AthletePreferenceRepository(session),
                    source_ref="web:training-preferences",
                    now=self._now(),
                )
            except AthleteMemoryError as error:
                raise TrainingOperationsError(str(error)) from error
            session.commit()
        return preference

    def archive_preference(
        self,
        *,
        preference_id: str,
        submission: AthletePreferenceArchiveSubmission,
    ) -> AthletePreference:
        del submission
        with self.database.session() as session:
            try:
                preference = archive_athlete_preference(
                    preference_id,
                    preferences=AthletePreferenceRepository(session),
                    now=self._now(),
                )
            except AthleteMemoryError as error:
                raise TrainingOperationsError(str(error)) from error
            session.commit()
        return preference

    def create_goal(self, submission: TrainingGoalSubmission) -> TrainingGoal:
        goal = submission.to_domain()
        if goal.target_date <= self._now().astimezone().date():
            raise TrainingOperationsError("目标日期必须晚于今天。")
        with self.database.session() as session:
            self._cycle_service(session).create_goal(goal)
            session.commit()
        return goal

    def draft_week_plan(
        self, *, goal_id: str, submission: WeeklyPlanDraftSubmission
    ):
        request = submission.to_request(goal_id)
        with self.database.session() as session:
            try:
                return execute_weekly_plan_draft(
                    request,
                    activities=ActivityRepository(session),
                    goals=TrainingGoalRepository(session),
                    plans=TrainingPlanRepository(session),
                    preferences=AthletePreferenceRepository(session),
                    weekly_memories=WeeklyTrainingMemoryRepository(session),
                )
            except TrainingPlanningError as error:
                raise TrainingOperationsError(str(error)) from error

    def activate_week_plan(
        self, *, goal_id: str, request: WeeklyPlanActivationRequest
    ) -> WeeklyPlanActivationResult:
        with self.database.session() as session:
            activities = ActivityRepository(session)
            goals = TrainingGoalRepository(session)
            plans = TrainingPlanRepository(session)
            replayed = execute_weekly_plan_draft(
                request.to_request(goal_id),
                activities=activities,
                goals=goals,
                plans=plans,
                preferences=AthletePreferenceRepository(session),
                weekly_memories=WeeklyTrainingMemoryRepository(session),
            )
            if replayed.input_hash != request.expected_input_hash:
                raise TrainingOperationsError(
                    "计划草案所依据的数据已经变化，请重新生成后再确认。"
                )
            draft = replayed.weekly_plan_draft
            if replayed.status != "ready" or draft is None:
                raise TrainingOperationsError(replayed.summary)
            cycle = self._cycle_service(session)
            try:
                plan = cycle.create_plan(goal_id=goal_id, week_start=draft.week_start)
                for planned_session in draft.sessions:
                    plan = cycle.add_draft_session(plan.id, planned_session)
                plan.source = "deterministic"
                plans.save(plan)
                plan = cycle.activate_plan(plan.id)
            except TrainingCycleError as error:
                raise TrainingOperationsError(str(error)) from error
            session.commit()
        return WeeklyPlanActivationResult(plan=plan, replayed_draft=replayed)

    def week_view(
        self,
        *,
        goal_id: str,
        as_of: datetime,
        provider=None,
    ) -> TrainingWeekView:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise TrainingOperationsError("as_of 必须包含时区。")
        with self.database.session() as session:
            goal = TrainingGoalRepository(session).get(goal_id)
            if goal is None or goal.status != "active":
                raise TrainingOperationsError("训练目标不存在或当前未激活。")
            plans = TrainingPlanRepository(session)
            week_start = as_of.date() - timedelta(days=as_of.date().weekday())
            plan = plans.for_goal_week(goal_id, week_start)
            if plan is None or plan.status != "active":
                future = plans.active_from_week(goal_id, week_start, limit=1)
                plan = future[0] if future else plans.active_for_goal(goal_id)
            execution = None
            check_in_days = 0
            if plan is not None and plan.status == "active":
                execution = execute_training_comparison(
                    TrainingExecutionRequest(
                        plan_id=plan.id,
                        as_of=as_of,
                        provider=provider,
                    ),
                    activities=ActivityRepository(session),
                    plans=plans,
                    preferences=AthletePreferenceRepository(session),
                    weekly_memories=WeeklyTrainingMemoryRepository(session),
                )
                check_in_days = len(
                    CheckInRepository(session).between(
                        plan.week_start, plan.week_start + timedelta(days=6)
                    )
                )
            recent_memories = WeeklyTrainingMemoryRepository(session).recent_before(
                goal_id,
                week_start + timedelta(days=7),
                limit=4,
            )
            preference_repository = AthletePreferenceRepository(session)
            memory_repository = WeeklyTrainingMemoryRepository(session)
            memory_contexts = [
                load_agent_memory_context(
                    MemoryContextBuildRequest(
                        role=role,
                        goal_id=goal_id,
                        as_of=as_of,
                        target_week_start=(
                            week_start + timedelta(days=7) if role == "plan" else None
                        ),
                    ),
                    preferences=preference_repository,
                    weekly_memories=memory_repository,
                )
                for role in ("execution", "recovery", "plan")
            ]
        today_ids = (
            [item.id for item in plan.sessions if item.scheduled_for == as_of.date()]
            if plan
            else []
        )
        next_session = (
            next(
                (
                    item.id
                    for item in plan.sessions
                    if item.session_type != "rest"
                    and item.status == "planned"
                    and item.scheduled_for >= as_of.date()
                ),
                None,
            )
            if plan
            else None
        )
        progress = self._week_progress(plan, execution, check_in_days) if plan and execution else None
        return TrainingWeekView(
            generated_at=self._now(),
            goal=goal,
            plan=plan,
            execution=execution,
            today_session_ids=today_ids,
            next_session_id=next_session,
            progress=progress,
            recent_memories=recent_memories,
            memory_contexts=memory_contexts,
        )

    def build_weekly_memory(
        self,
        *,
        goal_id: str,
        submission: WeeklyTrainingMemoryBuildSubmission,
    ) -> WeeklyTrainingMemoryBuildResult:
        with self.database.session() as session:
            try:
                result = refresh_weekly_training_memory(
                    submission.to_request(goal_id),
                    plans=TrainingPlanRepository(session),
                    confirmations=TrainingExecutionConfirmationRepository(session),
                    activities=ActivityRepository(session),
                    check_ins=CheckInRepository(session),
                    plan_changes=PlanChangeRepository(session),
                    memories=WeeklyTrainingMemoryRepository(session),
                )
            except WeeklyTrainingMemoryError as error:
                raise TrainingOperationsError(str(error)) from error
            session.commit()
        return result

    def list_weekly_memories(
        self,
        *,
        goal_id: str,
        include_inactive: bool = False,
        limit: int = 20,
    ) -> list[WeeklyTrainingMemory]:
        with self.database.session() as session:
            return WeeklyTrainingMemoryRepository(session).list_for_goal(
                goal_id,
                include_inactive=include_inactive,
                limit=limit,
            )

    def invalidate_weekly_memory(self, memory_id: str) -> WeeklyTrainingMemory:
        with self.database.session() as session:
            try:
                memory = invalidate_weekly_training_memory(
                    memory_id,
                    memories=WeeklyTrainingMemoryRepository(session),
                    now=self._now(),
                )
            except WeeklyTrainingMemoryError as error:
                raise TrainingOperationsError(str(error)) from error
            session.commit()
        return memory

    def decide_execution(
        self, *, plan_id: str, submission: ExecutionDecisionSubmission
    ) -> ExecutionConfirmationResult:
        with self.database.session() as session:
            try:
                result = confirm_training_execution(
                    submission.to_request(plan_id),
                    plans=TrainingPlanRepository(session),
                    activities=ActivityRepository(session),
                    confirmations=TrainingExecutionConfirmationRepository(session),
                )
            except TrainingExecutionError as error:
                raise TrainingOperationsError(str(error)) from error
            session.commit()
        return result

    def record_check_in(
        self, *, goal_id: str, submission: CheckInSubmission
    ) -> DailyCheckIn:
        with self.database.session() as session:
            goal = TrainingGoalRepository(session).get(goal_id)
            if goal is None or goal.status != "active":
                raise TrainingOperationsError("训练目标不存在或当前未激活。")
            check_in = submission.to_domain()
            CheckInRepository(session).save(check_in)
            session.commit()
        return check_in

    async def run_coach(self, submission: CoachRunSubmission) -> CoachRunView:
        request = submission.to_run_request()
        self._validate_scope(request)
        result = await self._execute(request)
        status = {
            "succeeded": "completed",
            "awaiting_user_confirmation": "awaiting_user_confirmation",
            "blocked": "blocked",
        }.get(result.status, "failed")
        audit = CoachRunAudit(
            run_id=result.run_id,
            goal_id=request.goal_id,
            plan_id=request.plan_id,
            status=status,
            run_request=request,
            result=result,
            planning_output_hash=(
                result.planning.input_hash if result.planning is not None else None
            ),
            created_at=self._now(),
        )
        with self.database.session() as session:
            CoachRunRepository(session).save(audit)
            plan = TrainingPlanRepository(session).get(request.plan_id)
            session.commit()
        assert plan is not None
        return CoachRunView(audit=audit, plan_sessions=plan.sessions)

    def get_coach_run(self, run_id: str) -> CoachRunView:
        with self.database.session() as session:
            audit = CoachRunRepository(session).get(run_id)
            if audit is None:
                raise TrainingOperationsError("Coach 运行记录不存在。")
            plan = TrainingPlanRepository(session).get(audit.plan_id)
        if plan is None:
            raise TrainingOperationsError("Coach 运行绑定的训练计划不存在。")
        return CoachRunView(audit=audit, plan_sessions=plan.sessions)

    async def decide_coach_run(
        self, *, run_id: str, request: CoachRunDecisionRequest
    ) -> CoachRunDecisionResult:
        with self.database.session() as session:
            audit = CoachRunRepository(session).get(run_id)
            plan = TrainingPlanRepository(session).get(audit.plan_id) if audit else None
        if audit is None or plan is None:
            raise TrainingOperationsError("Coach 运行记录不存在或训练计划已丢失。")
        if audit.status != "awaiting_user_confirmation":
            raise TrainingOperationsError("该 Coach 运行当前不能再次审核。")
        draft = (
            audit.result.planning.change_proposal_draft
            if audit.result.planning is not None
            else None
        )
        if draft is None:
            raise TrainingOperationsError("该 Coach 运行没有可审核的计划调整草案。")

        now = self._now()
        if request.decision == "reject":
            audit.status = "rejected"
            audit.decided_at = now
            with self.database.session() as session:
                CoachRunRepository(session).save(audit)
                session.commit()
            return CoachRunDecisionResult(outcome="rejected", audit=audit, plan=plan)

        fresh = await self._execute(audit.run_request)
        fresh_draft = (
            fresh.planning.change_proposal_draft if fresh.planning is not None else None
        )
        stale = (
            fresh.status != "awaiting_user_confirmation"
            or fresh.planning is None
            or fresh_draft is None
            or fresh.planning.input_hash != audit.planning_output_hash
            or fresh_draft != draft
        )
        if stale:
            audit.status = "stale"
            audit.decided_at = now
            with self.database.session() as session:
                CoachRunRepository(session).save(audit)
                current = TrainingPlanRepository(session).get(audit.plan_id)
                session.commit()
            assert current is not None
            return CoachRunDecisionResult(outcome="stale", audit=audit, plan=current)

        with self.database.session() as session:
            cycle = self._cycle_service(session)
            try:
                proposal = cycle.propose_change(
                    plan_id=draft.plan_id,
                    proposed_by="coach_orchestrator",
                    reason=draft.reason,
                    changes=draft.changes,
                    evidence_refs=draft.evidence_refs,
                )
                updated_plan, decided, confirmation = cycle.decide_change(
                    proposal_id=proposal.id,
                    decision="approve",
                    comment=request.comment,
                )
            except TrainingCycleError as error:
                raise TrainingOperationsError(str(error)) from error
            audit.status = "approved" if decided.status == "approved" else "stale"
            audit.proposal_id = proposal.id
            audit.decided_at = now
            CoachRunRepository(session).save(audit)
            session.commit()
        return CoachRunDecisionResult(
            outcome="approved" if decided.status == "approved" else "stale",
            audit=audit,
            plan=updated_plan,
            proposal=decided,
            confirmation=confirmation,
        )

    def _validate_scope(self, request: CoachAgentRunRequest) -> None:
        with self.database.session() as session:
            goal = TrainingGoalRepository(session).get(request.goal_id)
            plan = TrainingPlanRepository(session).get(request.plan_id)
        if goal is None or goal.status != "active":
            raise TrainingOperationsError("训练目标不存在或当前未激活。")
        if plan is None or plan.status != "active":
            raise TrainingOperationsError("训练计划不存在或当前未激活。")
        if plan.goal_id != goal.id:
            raise TrainingOperationsError("训练计划不属于所选训练目标。")

    async def _execute(self, request: CoachAgentRunRequest) -> CoachAgentRunResult:
        self._validate_scope(request)
        with self.database.session() as session:
            activities = ActivityRepository(session)
            plans = TrainingPlanRepository(session)
            goals = TrainingGoalRepository(session)
            check_ins = CheckInRepository(session)

            async def execution_tool(node_request):
                return execute_training_comparison(
                    node_request,
                    activities=activities,
                    plans=plans,
                    preferences=AthletePreferenceRepository(session),
                    weekly_memories=WeeklyTrainingMemoryRepository(session),
                )

            async def recovery_tool(node_request):
                return execute_recovery_assessment(
                    node_request,
                    activities=activities,
                    check_ins=check_ins,
                    plans=plans,
                    goals=goals,
                    preferences=AthletePreferenceRepository(session),
                    weekly_memories=WeeklyTrainingMemoryRepository(session),
                )

            async def plan_tool(node_request):
                return execute_plan_adjustment(node_request, goals=goals, plans=plans)

            result = await CoachOrchestratorHarness().run(
                request,
                tools=CoachNodeTools(
                    execution=execution_tool,
                    recovery=recovery_tool,
                    planning=plan_tool,
                ),
            )
        self.runtime_traces.record_coach(
            result,
            scope_ref=f"{request.goal_id}:{request.plan_id}",
        )
        return result

    @staticmethod
    def _cycle_service(session) -> TrainingCycleService:
        return TrainingCycleService(
            goals=TrainingGoalRepository(session),
            plans=TrainingPlanRepository(session),
            check_ins=CheckInRepository(session),
            changes=PlanChangeRepository(session),
        )

    @staticmethod
    def _week_progress(plan: TrainingPlan, execution, check_in_days: int) -> WeekProgressSummary:
        work_sessions = [item for item in execution.sessions if item.outcome != "rest"]
        due = [
            item
            for item in work_sessions
            if item.outcome != "upcoming"
        ]
        confirmed = [
            item
            for item in due
            if item.match_state == "confirmed" and item.outcome in {"complete", "partial"}
        ]
        pending = [item for item in due if item.requires_user_confirmation]
        skipped = [item for item in due if item.outcome == "skipped"]
        upcoming = [item for item in work_sessions if item.outcome == "upcoming"]
        completion_rate = round(len(confirmed) / len(due), 4) if due else None
        if pending:
            headline = f"有 {len(pending)} 节训练等待核对活动记录"
        elif due and len(confirmed) == len(due):
            headline = "本周到期训练均已确认"
        elif upcoming:
            headline = f"下一阶段还有 {len(upcoming)} 节训练待完成"
        else:
            headline = "本周尚无到期训练"
        return WeekProgressSummary(
            due_sessions=len(due),
            confirmed_sessions=len(confirmed),
            pending_confirmation_sessions=len(pending),
            skipped_sessions=len(skipped),
            upcoming_sessions=len(upcoming),
            completion_rate=completion_rate,
            planned_duration_seconds=sum(
                item.duration_seconds or 0
                for item in plan.sessions
                if item.session_type != "rest"
            ),
            check_in_days=check_in_days,
            headline=headline,
        )
