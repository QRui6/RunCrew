from __future__ import annotations

from datetime import date

from runcrew.domain.training_cycle import (
    DailyCheckIn,
    PlanChangeProposal,
    PlanSession,
    PlanSessionPatch,
    TrainingCycleSnapshot,
    TrainingGoal,
    TrainingPlan,
    UserConfirmation,
    utc_now,
)
from runcrew.storage.repositories import (
    CheckInRepository,
    PlanChangeRepository,
    TrainingGoalRepository,
    TrainingPlanRepository,
)


class TrainingCycleError(ValueError):
    pass


class TrainingCycleService:
    def __init__(
        self,
        *,
        goals: TrainingGoalRepository,
        plans: TrainingPlanRepository,
        check_ins: CheckInRepository,
        changes: PlanChangeRepository,
    ) -> None:
        self.goals = goals
        self.plans = plans
        self.check_ins = check_ins
        self.changes = changes

    def create_goal(self, goal: TrainingGoal) -> TrainingGoal:
        self.goals.save(goal)
        return goal

    def record_check_in(self, check_in: DailyCheckIn) -> DailyCheckIn:
        self.check_ins.save(check_in)
        return check_in

    def create_plan(self, *, goal_id: str, week_start: date) -> TrainingPlan:
        goal = self.goals.get(goal_id)
        if goal is None or goal.status != "active":
            raise TrainingCycleError("只能为存在且有效的训练目标创建计划")
        if self.plans.for_goal_week(goal_id, week_start) is not None:
            raise TrainingCycleError("该训练目标在这一周已经存在计划")
        plan = TrainingPlan(goal_id=goal_id, week_start=week_start)
        self.plans.save(plan)
        return plan

    def add_draft_session(self, plan_id: str, session: PlanSession) -> TrainingPlan:
        plan = self._require_plan(plan_id)
        if plan.status != "draft":
            raise TrainingCycleError("激活后的计划不能直接修改，必须提交变更提案")
        if any(item.id == session.id for item in plan.sessions):
            raise TrainingCycleError("计划课 ID 已存在")
        plan.sessions.append(session)
        plan.updated_at = utc_now()
        plan = TrainingPlan.model_validate(plan.model_dump())
        self.plans.save(plan)
        return plan

    def activate_plan(self, plan_id: str) -> TrainingPlan:
        plan = self._require_plan(plan_id)
        if plan.status != "draft":
            raise TrainingCycleError("只有草稿计划可以激活")
        if not plan.sessions:
            raise TrainingCycleError("空计划不能激活")
        plan.status = "active"
        plan.updated_at = utc_now()
        self.plans.save(plan)
        return plan

    def propose_change(
        self,
        *,
        plan_id: str,
        proposed_by: str,
        reason: str,
        changes: list[PlanSessionPatch],
        evidence_refs: list[str] | None = None,
    ) -> PlanChangeProposal:
        plan = self._require_plan(plan_id)
        if plan.status != "active":
            raise TrainingCycleError("只能为已激活计划提交变更提案")
        session_ids = {session.id for session in plan.sessions}
        unknown = sorted({change.session_id for change in changes} - session_ids)
        if unknown:
            raise TrainingCycleError(f"变更引用了未知计划课：{', '.join(unknown)}")
        proposal = PlanChangeProposal(
            plan_id=plan.id,
            base_revision=plan.revision,
            proposed_by=proposed_by,
            reason=reason,
            changes=changes,
            evidence_refs=evidence_refs or [],
        )
        self.changes.save_proposal(proposal)
        return proposal

    def decide_change(
        self,
        *,
        proposal_id: str,
        decision: str,
        comment: str | None = None,
    ) -> tuple[TrainingPlan, PlanChangeProposal, UserConfirmation]:
        if decision not in {"approve", "reject"}:
            raise TrainingCycleError("decision 必须是 approve 或 reject")
        proposal = self.changes.get_proposal(proposal_id)
        if proposal is None:
            raise TrainingCycleError("变更提案不存在")
        if proposal.status != "pending":
            raise TrainingCycleError("变更提案已经处理，不能重复确认")
        plan = self._require_plan(proposal.plan_id)
        confirmation = UserConfirmation(
            proposal_id=proposal.id,
            decision=decision,
            comment=comment,
        )
        now = utc_now()
        if decision == "reject":
            proposal.status = "rejected"
            proposal.decided_at = now
            self.changes.save_proposal(proposal)
            self.changes.save_confirmation(confirmation)
            return plan, proposal, confirmation
        if plan.revision != proposal.base_revision:
            proposal.status = "stale"
            proposal.decided_at = now
            self.changes.save_proposal(proposal)
            self.changes.save_confirmation(confirmation)
            return plan, proposal, confirmation

        patched_sessions: list[PlanSession] = []
        changes_by_id = {change.session_id: change for change in proposal.changes}
        for session in plan.sessions:
            patch = changes_by_id.get(session.id)
            if patch is None:
                patched_sessions.append(session)
                continue
            updates = patch.model_dump(
                exclude={
                    "session_id",
                    "clear_distance",
                    "clear_duration",
                    "clear_intensity",
                },
                exclude_none=True,
            )
            if patch.clear_distance:
                updates["distance_meters"] = None
            if patch.clear_duration:
                updates["duration_seconds"] = None
            if patch.clear_intensity:
                updates["intensity"] = None
            patched_sessions.append(session.model_copy(update=updates))
        plan.sessions = patched_sessions
        plan.revision += 1
        plan.updated_at = now
        plan = TrainingPlan.model_validate(plan.model_dump())
        proposal.status = "approved"
        proposal.decided_at = now
        self.plans.save(plan)
        self.changes.save_proposal(proposal)
        self.changes.save_confirmation(confirmation)
        return plan, proposal, confirmation

    def snapshot(self, goal_id: str) -> TrainingCycleSnapshot:
        goal = self.goals.get(goal_id)
        if goal is None:
            raise TrainingCycleError("训练目标不存在")
        return TrainingCycleSnapshot(
            goal=goal,
            active_plan=self.plans.active_for_goal(goal_id),
            recent_check_ins=self.check_ins.recent(limit=7),
            pending_proposals=self.changes.pending_for_goal(goal_id),
        )

    def _require_plan(self, plan_id: str) -> TrainingPlan:
        plan = self.plans.get(plan_id)
        if plan is None:
            raise TrainingCycleError("训练计划不存在")
        return plan
