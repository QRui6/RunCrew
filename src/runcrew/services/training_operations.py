from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from runcrew.domain.coach import CoachAgentRunRequest, CoachAgentRunResult
from runcrew.domain.training_cycle import DailyCheckIn
from runcrew.domain.training_operations import (
    CheckInSubmission,
    CoachRunAudit,
    CoachRunDecisionRequest,
    CoachRunDecisionResult,
    CoachRunSubmission,
    CoachRunView,
    TrainingOperationsBootstrap,
    TrainingOperationsGoalView,
)
from runcrew.harness import CoachNodeTools, CoachOrchestratorHarness
from runcrew.services.recovery_assessment import execute_recovery_assessment
from runcrew.services.training_cycle import TrainingCycleError, TrainingCycleService
from runcrew.services.training_execution import execute_training_comparison
from runcrew.services.training_planning import execute_plan_adjustment
from runcrew.storage.database import Database
from runcrew.storage.repositories import (
    ActivityRepository,
    CheckInRepository,
    CoachRunRepository,
    PlanChangeRepository,
    TrainingGoalRepository,
    TrainingPlanRepository,
)


class TrainingOperationsError(RuntimeError):
    pass


class TrainingOperationsService:
    """把训练闭环暴露给本地产品，同时把 Coach 草案与正式写入隔开。"""

    def __init__(self, *, database_path: Path = Path("data/runcrew.db")) -> None:
        self.database_path = database_path
        self.database = Database(f"sqlite:///{database_path.resolve().as_posix()}")
        self.database.create_schema()

    def bootstrap(self) -> TrainingOperationsBootstrap:
        with self.database.session() as session:
            goals = TrainingGoalRepository(session).list(limit=20)
            plans = TrainingPlanRepository(session)
            check_ins = CheckInRepository(session).recent(limit=1)
            changes = PlanChangeRepository(session)
            views = [
                TrainingOperationsGoalView(
                    goal=goal,
                    active_plan=plans.active_for_goal(goal.id),
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
        return TrainingOperationsBootstrap(
            generated_at=datetime.now(timezone.utc),
            goals=views,
            providers=providers,
            recent_coach_runs=recent_runs,
        )

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
            created_at=datetime.now(timezone.utc),
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

        now = datetime.now(timezone.utc)
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
                    node_request, activities=activities, plans=plans
                )

            async def recovery_tool(node_request):
                return execute_recovery_assessment(
                    node_request,
                    activities=activities,
                    check_ins=check_ins,
                    plans=plans,
                    goals=goals,
                )

            async def plan_tool(node_request):
                return execute_plan_adjustment(node_request, goals=goals, plans=plans)

            return await CoachOrchestratorHarness().run(
                request,
                tools=CoachNodeTools(
                    execution=execution_tool,
                    recovery=recovery_tool,
                    planning=plan_tool,
                ),
            )

    @staticmethod
    def _cycle_service(session) -> TrainingCycleService:
        return TrainingCycleService(
            goals=TrainingGoalRepository(session),
            plans=TrainingPlanRepository(session),
            check_ins=CheckInRepository(session),
            changes=PlanChangeRepository(session),
        )
