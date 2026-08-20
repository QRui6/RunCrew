from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from pydantic import ValidationError

from runcrew.domain.coach import (
    COACH_ACTION_ADAPTER,
    EXECUTION_TOOL_NAME,
    PLAN_TOOL_NAME,
    RECOVERY_TOOL_NAME,
    CoachAction,
    CoachAgentRunRequest,
    CoachAgentRunResult,
    CoachBudgetUsage,
    CoachFinishAction,
    CoachHandoff,
    CoachNode,
    CoachNodePermission,
    CoachPolicyContext,
    CoachRunError,
    CoachTraceEvent,
    DelegateExecutionAction,
    DelegatePlanAction,
    DelegateRecoveryAction,
)
from runcrew.domain.recovery_assessment import (
    RecoveryAssessmentRequest,
    RecoveryAssessmentResult,
)
from runcrew.domain.training_execution import (
    TrainingExecutionRequest,
    TrainingExecutionResult,
)
from runcrew.domain.training_planning import PlanAdjustmentRequest, TrainingPlanningResult
from runcrew.services.training_planning import adjustment_request_from_recovery
from runcrew.services.runtime_governance import (
    RuntimeGuardrailEngine,
    guardrail_trace_details,
)
from runcrew.domain.runtime_governance import GuardrailDecision, ToolOutputGuardrailResult


class CoachPolicy(Protocol):
    async def next_action(self, context: CoachPolicyContext) -> CoachAction | Any:
        """只根据最小编排上下文选择下一次委派，不直接读取业务明细。"""


class ExecutionTool(Protocol):
    async def __call__(
        self, request: TrainingExecutionRequest
    ) -> TrainingExecutionResult | dict[str, Any]: ...


class RecoveryTool(Protocol):
    async def __call__(
        self, request: RecoveryAssessmentRequest
    ) -> RecoveryAssessmentResult | dict[str, Any]: ...


class PlanTool(Protocol):
    async def __call__(
        self, request: PlanAdjustmentRequest
    ) -> TrainingPlanningResult | dict[str, Any]: ...


class RetryableCoachNodeError(RuntimeError):
    """节点的瞬时失败；Harness 可以在预算内重试。"""


class DeterministicCoachPolicy:
    """可回放的基线编排策略；未来 LLM Policy 必须遵守同一动作协议。"""

    async def next_action(self, context: CoachPolicyContext) -> CoachAction:
        if not context.execution_completed:
            return DelegateExecutionAction(arguments=context.execution_request)
        if not context.recovery_completed:
            return DelegateRecoveryAction(arguments=context.recovery_request)
        if context.recovery_route in {
            "ask_plan_agent_to_reduce",
            "ask_plan_agent_to_replace_with_rest",
        } and not context.planning_completed:
            if context.plan_request is None:
                raise ValueError("恢复节点要求调整计划，但没有形成合法交接请求")
            return DelegatePlanAction(arguments=context.plan_request)
        return CoachFinishAction()


@dataclass(frozen=True, slots=True)
class ExecutionAgentNode:
    permission: CoachNodePermission

    async def run(self, request: TrainingExecutionRequest, tool: ExecutionTool) -> Any:
        return await tool(request)


@dataclass(frozen=True, slots=True)
class RecoveryAgentNode:
    permission: CoachNodePermission

    async def run(self, request: RecoveryAssessmentRequest, tool: RecoveryTool) -> Any:
        return await tool(request)


@dataclass(frozen=True, slots=True)
class PlanAgentNode:
    permission: CoachNodePermission

    async def run(self, request: PlanAdjustmentRequest, tool: PlanTool) -> Any:
        return await tool(request)


@dataclass(frozen=True, slots=True)
class CoachNodeTools:
    execution: ExecutionTool
    recovery: RecoveryTool
    planning: PlanTool


@dataclass(slots=True)
class _Usage:
    steps: int = 0
    node_calls: int = 0
    node_attempts: int = 0


class _TraceRecorder:
    def __init__(self) -> None:
        self._started = time.perf_counter()
        self.events: list[CoachTraceEvent] = []

    def add(
        self,
        *,
        state: str,
        event: str,
        node: CoachNode | None = None,
        tool_name: str | None = None,
        attempt: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            CoachTraceEvent(
                sequence=len(self.events) + 1,
                elapsed_ms=round((time.perf_counter() - self._started) * 1000, 3),
                state=state,
                event=event,
                node=node,
                tool_name=tool_name,
                attempt=attempt,
                details=details or {},
            )
        )


class _NodeFailure(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def _hash_model(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: item.model_dump(mode="json"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CoachOrchestratorHarness:
    """执行有限的跨职责 Agent Loop，并统一约束权限、交接、预算和中断。"""

    def __init__(
        self,
        *,
        policy: CoachPolicy | None = None,
        permissions: list[CoachNodePermission] | None = None,
        guardrails: RuntimeGuardrailEngine | None = None,
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        configured = permissions or [
            CoachNodePermission(
                node="execution_agent", tool_name=EXECUTION_TOOL_NAME, access="read"
            ),
            CoachNodePermission(
                node="recovery_agent", tool_name=RECOVERY_TOOL_NAME, access="read"
            ),
            CoachNodePermission(
                node="plan_agent", tool_name=PLAN_TOOL_NAME, access="prepare_change"
            ),
        ]
        self.policy = policy or DeterministicCoachPolicy()
        self.permissions = configured
        self._permissions = {item.node: item for item in configured}
        self.execution_node = ExecutionAgentNode(
            self._permissions.get("execution_agent")
            or CoachNodePermission(
                node="execution_agent", tool_name=EXECUTION_TOOL_NAME, access="read"
            )
        )
        self.recovery_node = RecoveryAgentNode(
            self._permissions.get("recovery_agent")
            or CoachNodePermission(
                node="recovery_agent", tool_name=RECOVERY_TOOL_NAME, access="read"
            )
        )
        self.plan_node = PlanAgentNode(
            self._permissions.get("plan_agent")
            or CoachNodePermission(
                node="plan_agent", tool_name=PLAN_TOOL_NAME, access="prepare_change"
            )
        )
        self.guardrails = guardrails or RuntimeGuardrailEngine()
        self.run_id_factory = run_id_factory or (lambda: uuid.uuid4().hex)

    async def run(
        self, request: CoachAgentRunRequest, *, tools: CoachNodeTools
    ) -> CoachAgentRunResult:
        run_id = self.run_id_factory()
        recorder = _TraceRecorder()
        usage = _Usage()
        workflow_hash = _hash_model(
            {
                "workflow_version": "coach-weekly-operations/1.0",
                "request": request,
            }
        )
        recorder.add(
            state="created",
            event="run_started",
            details={
                "instruction_version": "coach-orchestrator-instructions/1.0",
                "max_steps": request.max_steps,
                "node_call_budget": request.node_call_budget,
            },
        )
        state: dict[str, Any] = {
            "execution": None,
            "recovery": None,
            "planning": None,
            "plan_request": None,
            "handoffs": [],
        }
        try:
            async with asyncio.timeout(request.run_timeout_seconds):
                return await self._run_loop(
                    run_id=run_id,
                    workflow_hash=workflow_hash,
                    request=request,
                    tools=tools,
                    recorder=recorder,
                    usage=usage,
                    state=state,
                )
        except TimeoutError:
            return self._failure_result(
                run_id=run_id,
                workflow_hash=workflow_hash,
                code="run_timeout",
                message="Coach 编排运行超过总时间限制，已安全停止。",
                retryable=True,
                recorder=recorder,
                usage=usage,
                state=state,
            )

    async def _run_loop(
        self,
        *,
        run_id: str,
        workflow_hash: str,
        request: CoachAgentRunRequest,
        tools: CoachNodeTools,
        recorder: _TraceRecorder,
        usage: _Usage,
        state: dict[str, Any],
    ) -> CoachAgentRunResult:
        execution_request = TrainingExecutionRequest(
            plan_id=request.plan_id,
            as_of=request.as_of,
            provider=request.provider,
            date_tolerance_days=request.date_tolerance_days,
        )
        recovery_request = RecoveryAssessmentRequest(
            goal_id=request.goal_id,
            assessed_at=request.as_of,
            lookback_days=request.recovery_lookback_days,
            provider=request.provider,
        )

        while True:
            if usage.steps >= request.max_steps:
                return self._failure_result(
                    run_id=run_id,
                    workflow_hash=workflow_hash,
                    code="step_budget_exhausted",
                    message="Coach 已耗尽步骤预算，未继续委派。",
                    retryable=False,
                    recorder=recorder,
                    usage=usage,
                    state=state,
                )
            recovery: RecoveryAssessmentResult | None = state["recovery"]
            context = CoachPolicyContext(
                permissions=self.permissions,
                execution_request=execution_request,
                recovery_request=recovery_request,
                plan_request=state["plan_request"],
                execution_completed=state["execution"] is not None,
                recovery_completed=recovery is not None,
                recovery_route=(recovery.plan_action.action if recovery else "unknown"),
                planning_completed=state["planning"] is not None,
                step=usage.steps,
                remaining_steps=request.max_steps - usage.steps,
                remaining_node_calls=max(request.node_call_budget - usage.node_calls, 0),
            )
            try:
                raw_action = await self.policy.next_action(context)
                action = COACH_ACTION_ADAPTER.validate_python(raw_action)
            except Exception as error:
                return self._failure_result(
                    run_id=run_id,
                    workflow_hash=workflow_hash,
                    code="policy_error",
                    message="Coach Policy 没有返回合法动作，已安全停止。",
                    retryable=False,
                    recorder=recorder,
                    usage=usage,
                    state=state,
                    error_type=type(error).__name__,
                )

            usage.steps += 1
            recorder.add(
                state="routing",
                event="policy_action",
                node=getattr(action, "node", None),
                tool_name=getattr(action, "tool_name", None),
                details={"action_type": action.type},
            )
            if isinstance(action, CoachFinishAction):
                return self._finish_business_result(
                    run_id=run_id,
                    workflow_hash=workflow_hash,
                    recorder=recorder,
                    usage=usage,
                    state=state,
                )

            expected, context_fields = self._expected_handoff(
                action=action,
                execution_request=execution_request,
                recovery_request=recovery_request,
                plan_request=state["plan_request"],
            )
            permission_error = self._validate_permission(
                action,
                expected=expected,
                request=request,
                recorder=recorder,
            )
            if permission_error is not None:
                code, message = permission_error
                return self._failure_result(
                    run_id=run_id,
                    workflow_hash=workflow_hash,
                    code=code,
                    message=message,
                    retryable=False,
                    recorder=recorder,
                    usage=usage,
                    state=state,
                )
            if usage.node_calls >= request.node_call_budget:
                return self._failure_result(
                    run_id=run_id,
                    workflow_hash=workflow_hash,
                    code="step_budget_exhausted",
                    message="Coach 已耗尽节点调用预算，未继续委派。",
                    retryable=False,
                    recorder=recorder,
                    usage=usage,
                    state=state,
                )

            handoff = CoachHandoff(
                sequence=len(state["handoffs"]) + 1,
                to_node=action.node,
                tool_name=action.tool_name,
                context_fields=context_fields,
                request_hash=_hash_model(action.arguments),
            )
            state["handoffs"].append(handoff)
            recorder.add(
                state="handoff",
                event="handoff_prepared",
                node=action.node,
                tool_name=action.tool_name,
                details={
                    "handoff_sequence": handoff.sequence,
                    "context_fields": context_fields,
                    "request_hash": handoff.request_hash,
                },
            )
            usage.node_calls += 1
            try:
                output, output_guardrail = await self._call_node(
                    action=action,
                    tools=tools,
                    request=request,
                    recorder=recorder,
                    usage=usage,
                )
                self._validate_node_scope(action, output, request, state)
            except _NodeFailure as error:
                return self._failure_result(
                    run_id=run_id,
                    workflow_hash=workflow_hash,
                    code=error.code,
                    message=error.message,
                    retryable=error.retryable,
                    recorder=recorder,
                    usage=usage,
                    state=state,
                )

            recorder.add(
                state="validating",
                event="node_output_validated",
                node=action.node,
                tool_name=action.tool_name,
                details={
                    "output_schema": type(output).__name__,
                    "guardrail_rule_id": output_guardrail.decision.rule_id,
                    "guardrail_outcome": output_guardrail.decision.outcome,
                },
            )
            if isinstance(action, DelegateExecutionAction):
                state["execution"] = output
            elif isinstance(action, DelegateRecoveryAction):
                state["recovery"] = output
                state["plan_request"] = adjustment_request_from_recovery(output)
            else:
                state["planning"] = output

    def _expected_handoff(
        self,
        *,
        action: CoachAction,
        execution_request: TrainingExecutionRequest,
        recovery_request: RecoveryAssessmentRequest,
        plan_request: PlanAdjustmentRequest | None,
    ) -> tuple[Any | None, list[str]]:
        if isinstance(action, DelegateExecutionAction):
            return execution_request, [
                "plan_id",
                "as_of",
                "provider",
                "date_tolerance_days",
            ]
        if isinstance(action, DelegateRecoveryAction):
            return recovery_request, ["goal_id", "assessed_at", "provider", "lookback_days"]
        if isinstance(action, DelegatePlanAction):
            return plan_request, [
                "goal_id",
                "assessed_at",
                "recovery_input_hash",
                "recovery_recommendation",
                "plan_action",
                "evidence_refs",
            ]
        return None, []

    def _validate_permission(
        self,
        action: DelegateExecutionAction | DelegateRecoveryAction | DelegatePlanAction,
        *,
        expected: Any,
        request: CoachAgentRunRequest,
        recorder: _TraceRecorder,
    ) -> tuple[str, str] | None:
        permission = self._permissions.get(action.node)
        access = permission.access if permission else (
            "prepare_change" if action.node == "plan_agent" else "read"
        )
        governance = self.guardrails.evaluate_invocation(
            tool_name=action.tool_name,
            owner_role=action.node,
            granted_access=access,
            actual_arguments=action.arguments,
            expected_arguments=expected,
            timeout_seconds=request.node_timeout_seconds,
            max_retries=request.max_retries,
            can_persist=permission.can_persist if permission else False,
            can_approve=permission.can_approve if permission else False,
        )
        permission_matches_action = permission is not None and permission.tool_name == action.tool_name
        if not permission_matches_action and governance.allowed:
            governance = governance.model_copy(
                update={
                    "allowed": False,
                    "decisions": [
                        *governance.decisions,
                        GuardrailDecision(
                            rule_id="tool.permission-binding/1.0",
                            stage="permission",
                            outcome="deny",
                            reason="Harness 权限绑定与动作工具不一致。",
                        )
                    ],
                }
            )
        recorder.add(
            state="routing",
            event="node_permission_checked",
            node=action.node,
            tool_name=action.tool_name,
            details={
                **guardrail_trace_details(governance),
                "access": permission.access if permission else None,
                "can_persist": permission.can_persist if permission else None,
                "can_approve": permission.can_approve if permission else None,
            },
        )
        if governance.allowed and permission_matches_action:
            return None
        if any(
            item.rule_id == "tool.argument-integrity/1.0"
            and item.outcome == "deny"
            for item in governance.decisions
        ):
            return "invalid_handoff", "职责节点收到的参数不是 Harness 生成的最小可信交接。"
        return "permission_denied", "职责节点请求了白名单外的工具或写入权限，调用已拒绝。"

    async def _call_node(
        self,
        *,
        action: DelegateExecutionAction | DelegateRecoveryAction | DelegatePlanAction,
        tools: CoachNodeTools,
        request: CoachAgentRunRequest,
        recorder: _TraceRecorder,
        usage: _Usage,
    ) -> tuple[
        TrainingExecutionResult | RecoveryAssessmentResult | TrainingPlanningResult,
        ToolOutputGuardrailResult,
    ]:
        for attempt in range(1, request.max_retries + 2):
            usage.node_attempts += 1
            recorder.add(
                state="calling_node",
                event="node_call_started",
                node=action.node,
                tool_name=action.tool_name,
                attempt=attempt,
            )
            try:
                async with asyncio.timeout(request.node_timeout_seconds):
                    if isinstance(action, DelegateExecutionAction):
                        raw = await self.execution_node.run(action.arguments, tools.execution)
                        output_model = TrainingExecutionResult
                    elif isinstance(action, DelegateRecoveryAction):
                        raw = await self.recovery_node.run(action.arguments, tools.recovery)
                        output_model = RecoveryAssessmentResult
                    else:
                        raw = await self.plan_node.run(action.arguments, tools.planning)
                        output_model = TrainingPlanningResult
                    output, output_guardrail = self.guardrails.validate_output(
                        tool_name=action.tool_name,
                        raw_output=raw,
                        output_model=output_model,
                    )
                    if output is None:
                        raise _NodeFailure(
                            "invalid_node_output",
                            "职责节点返回内容不符合输出 Schema，已拒绝继续编排。",
                            retryable=False,
                        )
                recorder.add(
                    state="calling_node",
                    event="node_call_succeeded",
                    node=action.node,
                    tool_name=action.tool_name,
                    attempt=attempt,
                )
                return output, output_guardrail
            except _NodeFailure as error:
                recorder.add(
                    state="failed",
                    event="node_call_failed",
                    node=action.node,
                    tool_name=action.tool_name,
                    attempt=attempt,
                    details={
                        "error_type": type(error).__name__,
                        "retryable": error.retryable,
                        "guardrail_rule_id": output_guardrail.decision.rule_id,
                        "guardrail_outcome": output_guardrail.decision.outcome,
                        **output_guardrail.decision.details,
                    },
                )
                raise
            except ValidationError as error:
                recorder.add(
                    state="failed",
                    event="node_call_failed",
                    node=action.node,
                    tool_name=action.tool_name,
                    attempt=attempt,
                    details={"error_type": type(error).__name__, "retryable": False},
                )
                raise _NodeFailure(
                    "invalid_node_output",
                    "职责节点返回内容不符合输出 Schema，已拒绝继续编排。",
                    retryable=False,
                ) from error
            except (RetryableCoachNodeError, TimeoutError) as error:
                retryable = True
                code = "node_timeout" if isinstance(error, TimeoutError) else "node_failure"
                recorder.add(
                    state="failed",
                    event="node_call_failed",
                    node=action.node,
                    tool_name=action.tool_name,
                    attempt=attempt,
                    details={"error_type": type(error).__name__, "retryable": retryable},
                )
                if attempt <= request.max_retries:
                    recorder.add(
                        state="calling_node",
                        event="node_call_retry_scheduled",
                        node=action.node,
                        tool_name=action.tool_name,
                        attempt=attempt,
                    )
                    continue
                message = (
                    "职责节点调用超时，已用尽重试预算。"
                    if code == "node_timeout"
                    else "职责节点暂时失败，已用尽重试预算。"
                )
                raise _NodeFailure(code, message, retryable=True) from error
            except Exception as error:
                recorder.add(
                    state="failed",
                    event="node_call_failed",
                    node=action.node,
                    tool_name=action.tool_name,
                    attempt=attempt,
                    details={"error_type": type(error).__name__, "retryable": False},
                )
                raise _NodeFailure(
                    "node_failure", "职责节点执行失败，已安全停止。", retryable=False
                ) from error
        raise AssertionError("unreachable")

    def _validate_node_scope(
        self,
        action: DelegateExecutionAction | DelegateRecoveryAction | DelegatePlanAction,
        output: TrainingExecutionResult | RecoveryAssessmentResult | TrainingPlanningResult,
        request: CoachAgentRunRequest,
        state: dict[str, Any],
    ) -> None:
        valid = False
        if isinstance(action, DelegateExecutionAction) and isinstance(
            output, TrainingExecutionResult
        ):
            valid = output.plan_id == request.plan_id and output.goal_id == request.goal_id
        elif isinstance(action, DelegateRecoveryAction) and isinstance(
            output, RecoveryAssessmentResult
        ):
            valid = output.goal_id == request.goal_id
        elif isinstance(action, DelegatePlanAction) and isinstance(
            output, TrainingPlanningResult
        ):
            recovery: RecoveryAssessmentResult | None = state["recovery"]
            valid = (
                recovery is not None
                and output.goal_id == request.goal_id
                and output.operation == "adjust_from_recovery"
                and output.source_recovery_assessment is not None
                and output.source_recovery_assessment.input_hash == recovery.input_hash
                and output.source_recovery_assessment.recommendation
                == recovery.recommendation
                and output.source_recovery_assessment.plan_action == recovery.plan_action
            )
        if not valid:
            raise _NodeFailure(
                "invalid_node_output",
                "职责节点输出越过当前目标、计划或上游证据边界，已拒绝继续编排。",
                retryable=False,
            )

    def _finish_business_result(
        self,
        *,
        run_id: str,
        workflow_hash: str,
        recorder: _TraceRecorder,
        usage: _Usage,
        state: dict[str, Any],
    ) -> CoachAgentRunResult:
        execution: TrainingExecutionResult | None = state["execution"]
        recovery: RecoveryAssessmentResult | None = state["recovery"]
        planning: TrainingPlanningResult | None = state["planning"]
        if execution is None or recovery is None:
            return self._failure_result(
                run_id=run_id,
                workflow_hash=workflow_hash,
                code="premature_finish",
                message="Coach 在完成训练执行和恢复评估前请求结束，已拒绝输出。",
                retryable=False,
                recorder=recorder,
                usage=usage,
                state=state,
            )

        route = recovery.plan_action.action
        if route == "keep":
            status, reason, user_action = "succeeded", "completed", None
        elif route == "wait_for_more_data":
            status, reason, user_action = "blocked", "safe_blocked", "provide_fresh_check_in"
        elif route == "hold_until_professional_review":
            status, reason, user_action = (
                "blocked",
                "safe_blocked",
                "seek_professional_review",
            )
        elif planning is None:
            return self._failure_result(
                run_id=run_id,
                workflow_hash=workflow_hash,
                code="premature_finish",
                message="恢复评估要求调整计划，但 Plan Agent 尚未完成。",
                retryable=False,
                recorder=recorder,
                usage=usage,
                state=state,
            )
        elif planning.status == "ready" and planning.change_proposal_draft is not None:
            status, reason, user_action = (
                "awaiting_user_confirmation",
                "user_confirmation_required",
                "review_plan_change",
            )
            recorder.add(
                state="paused",
                event="user_confirmation_requested",
                node="plan_agent",
                tool_name=PLAN_TOOL_NAME,
                details={
                    "plan_id": planning.change_proposal_draft.plan_id,
                    "base_revision": planning.change_proposal_draft.base_revision,
                    "persisted": False,
                    "approved": False,
                },
            )
        else:
            status, reason, user_action = (
                "blocked",
                "safe_blocked",
                "provide_training_plan",
            )
        recorder.add(
            state="completed" if status == "succeeded" else "paused",
            event="run_completed",
            details={"status": status, "termination_reason": reason},
        )
        return CoachAgentRunResult(
            run_id=run_id,
            workflow_hash=workflow_hash,
            status=status,
            termination_reason=reason,
            execution=execution,
            recovery=recovery,
            planning=planning,
            required_user_action=user_action,
            budget=self._budget(usage),
            handoffs=state["handoffs"],
            trace=recorder.events,
        )

    def _failure_result(
        self,
        *,
        run_id: str,
        workflow_hash: str,
        code: str,
        message: str,
        retryable: bool,
        recorder: _TraceRecorder,
        usage: _Usage,
        state: dict[str, Any],
        error_type: str | None = None,
    ) -> CoachAgentRunResult:
        status = (
            "timed_out"
            if code in {"node_timeout", "run_timeout"}
            else "budget_exhausted"
            if code == "step_budget_exhausted"
            else "failed"
        )
        recorder.add(
            state="failed",
            event=(
                "run_timed_out"
                if status == "timed_out"
                else "budget_exhausted"
                if status == "budget_exhausted"
                else "run_failed"
            ),
            details={"code": code, **({"error_type": error_type} if error_type else {})},
        )
        return CoachAgentRunResult(
            run_id=run_id,
            workflow_hash=workflow_hash,
            status=status,
            termination_reason=code,
            execution=state["execution"],
            recovery=state["recovery"],
            planning=state["planning"],
            error=CoachRunError(code=code, message=message, retryable=retryable),
            budget=self._budget(usage),
            handoffs=state["handoffs"],
            trace=recorder.events,
        )

    @staticmethod
    def _budget(usage: _Usage) -> CoachBudgetUsage:
        return CoachBudgetUsage(
            steps_used=usage.steps,
            node_calls_used=usage.node_calls,
            node_attempts_used=usage.node_attempts,
        )
