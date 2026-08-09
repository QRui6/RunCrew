from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from pydantic import ValidationError

from runcrew.domain.agent import (
    AGENT_ACTION_ADAPTER,
    REVIEW_TOOL_NAME,
    AgentAction,
    AgentBudgetUsage,
    AgentRunError,
    AgentTraceEvent,
    FinishAction,
    ReviewAgentContext,
    ReviewAgentRunRequest,
    ReviewAgentRunResult,
    ToolCallAction,
    ToolPermission,
)
from runcrew.domain.training_review import TrainingReviewRequest, TrainingReviewResult


class ReviewAgentPolicy(Protocol):
    async def next_action(self, context: ReviewAgentContext) -> AgentAction | Any:
        """基于有界上下文选择下一步动作。"""


class ReviewTool(Protocol):
    async def __call__(
        self, request: TrainingReviewRequest
    ) -> TrainingReviewResult | dict[str, Any]:
        """执行唯一允许的训练复盘 Skill 工具。"""


class RetryableToolError(RuntimeError):
    """表示瞬时工具错误，Harness 可以在预算内重试。"""


class DeterministicReviewPolicy:
    """M4 默认策略；未来 LLM 策略必须实现同一动作接口。"""

    async def next_action(self, context: ReviewAgentContext) -> AgentAction:
        if context.observation is None:
            return ToolCallAction(
                tool_name=REVIEW_TOOL_NAME,
                arguments=context.user_request,
            )
        return FinishAction()


@dataclass(slots=True)
class _Usage:
    steps: int = 0
    tool_calls: int = 0
    tool_attempts: int = 0


class _TraceRecorder:
    def __init__(self) -> None:
        self._started = time.perf_counter()
        self.events: list[AgentTraceEvent] = []

    def add(
        self,
        *,
        state: str,
        event: str,
        attempt: int | None = None,
        tool_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            AgentTraceEvent(
                sequence=len(self.events) + 1,
                elapsed_ms=round((time.perf_counter() - self._started) * 1000, 3),
                state=state,
                event=event,
                attempt=attempt,
                tool_name=tool_name,
                details=details or {},
            )
        )


class _ToolExecutionFailure(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class ReviewAgentHarness:
    """执行单 Agent 有限循环，并统一约束权限、预算、重试、超时和 Trace。"""

    def __init__(
        self,
        *,
        policy: ReviewAgentPolicy | None = None,
        permission: ToolPermission | None = None,
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.policy = policy or DeterministicReviewPolicy()
        self.permission = permission or ToolPermission(
            name=REVIEW_TOOL_NAME,
            access="read",
            confirmation_required=False,
        )
        self.run_id_factory = run_id_factory or (lambda: uuid.uuid4().hex)

    async def run(
        self,
        request: ReviewAgentRunRequest,
        *,
        tool: ReviewTool,
    ) -> ReviewAgentRunResult:
        run_id = self.run_id_factory()
        recorder = _TraceRecorder()
        usage = _Usage()
        recorder.add(
            state="created",
            event="run_started",
            details={
                "instruction_version": "review-agent-instructions/1.0",
                "max_steps": request.max_steps,
                "tool_call_budget": request.tool_call_budget,
            },
        )
        try:
            async with asyncio.timeout(request.run_timeout_seconds):
                return await self._run_loop(
                    run_id=run_id,
                    request=request,
                    tool=tool,
                    recorder=recorder,
                    usage=usage,
                )
        except TimeoutError:
            policy_details = self._consume_policy_trace_details()
            return self._failure_result(
                run_id=run_id,
                code="run_timeout",
                message="Agent 运行超过总时间限制，已安全停止。",
                retryable=True,
                recorder=recorder,
                usage=usage,
                extra_details=policy_details,
            )

    async def _run_loop(
        self,
        *,
        run_id: str,
        request: ReviewAgentRunRequest,
        tool: ReviewTool,
        recorder: _TraceRecorder,
        usage: _Usage,
    ) -> ReviewAgentRunResult:
        observation: TrainingReviewResult | None = None
        while True:
            if usage.steps >= request.max_steps:
                return self._failure_result(
                    run_id=run_id,
                    code="step_budget_exhausted",
                    message="Agent 已耗尽步骤预算，未继续执行。",
                    retryable=False,
                    recorder=recorder,
                    usage=usage,
                )

            context = ReviewAgentContext(
                user_request=request.review_request,
                tool_permissions=[self.permission],
                observation=observation,
                step=usage.steps,
                remaining_steps=request.max_steps - usage.steps,
                remaining_tool_calls=max(
                    request.tool_call_budget - usage.tool_calls,
                    0,
                ),
            )
            try:
                raw_action = await self.policy.next_action(context)
                action = AGENT_ACTION_ADAPTER.validate_python(raw_action)
            except Exception as error:
                policy_details = self._consume_policy_trace_details()
                return self._failure_result(
                    run_id=run_id,
                    code="policy_error",
                    message="Agent 策略没有返回合法动作，已安全停止。",
                    retryable=False,
                    recorder=recorder,
                    usage=usage,
                    error_type=type(error).__name__,
                    extra_details=policy_details,
                )

            policy_details = self._consume_policy_trace_details()
            usage.steps += 1
            recorder.add(
                state="planning",
                event="policy_action",
                details={"action_type": action.type, **policy_details},
            )

            if isinstance(action, FinishAction):
                if observation is None:
                    return self._failure_result(
                        run_id=run_id,
                        code="premature_finish",
                        message="Agent 在获得训练复盘结果前请求结束，已拒绝输出。",
                        retryable=False,
                        recorder=recorder,
                        usage=usage,
                    )
                return self._success_result(
                    run_id=run_id,
                    output=observation,
                    recorder=recorder,
                    usage=usage,
                )

            permission_failure = self._check_permission(action, request, recorder)
            if permission_failure is not None:
                code, message = permission_failure
                return self._failure_result(
                    run_id=run_id,
                    code=code,
                    message=message,
                    retryable=False,
                    recorder=recorder,
                    usage=usage,
                )
            if action.arguments != request.review_request:
                return self._failure_result(
                    run_id=run_id,
                    code="permission_denied",
                    message="Agent 尝试修改用户已经确认的复盘参数，调用已拒绝。",
                    retryable=False,
                    recorder=recorder,
                    usage=usage,
                )
            if usage.tool_calls >= request.tool_call_budget:
                return self._failure_result(
                    run_id=run_id,
                    code="step_budget_exhausted",
                    message="Agent 已耗尽工具调用预算，未继续执行。",
                    retryable=False,
                    recorder=recorder,
                    usage=usage,
                )

            usage.tool_calls += 1
            try:
                observation = await self._execute_tool(
                    action=action,
                    request=request,
                    tool=tool,
                    recorder=recorder,
                    usage=usage,
                )
            except _ToolExecutionFailure as error:
                return self._failure_result(
                    run_id=run_id,
                    code=error.code,
                    message=error.message,
                    retryable=error.retryable,
                    recorder=recorder,
                    usage=usage,
                )

    def _check_permission(
        self,
        action: ToolCallAction,
        request: ReviewAgentRunRequest,
        recorder: _TraceRecorder,
    ) -> tuple[str, str] | None:
        allowed = action.tool_name == self.permission.name == REVIEW_TOOL_NAME
        recorder.add(
            state="planning",
            event="tool_permission_checked",
            tool_name=action.tool_name,
            details={
                "allowed": allowed,
                "access": self.permission.access,
                "confirmation_required": self.permission.confirmation_required,
            },
        )
        if not allowed:
            return "permission_denied", "Agent 请求了白名单以外的工具，调用已拒绝。"
        if (
            self.permission.confirmation_required
            and action.tool_name not in request.confirmed_tools
        ):
            return "confirmation_required", "该工具需要用户确认，本次运行未获得确认。"
        return None

    async def _execute_tool(
        self,
        *,
        action: ToolCallAction,
        request: ReviewAgentRunRequest,
        tool: ReviewTool,
        recorder: _TraceRecorder,
        usage: _Usage,
    ) -> TrainingReviewResult:
        for attempt in range(1, request.max_retries + 2):
            usage.tool_attempts += 1
            recorder.add(
                state="calling_tool",
                event="tool_call_started",
                attempt=attempt,
                tool_name=action.tool_name,
            )
            try:
                raw_result = await asyncio.wait_for(
                    tool(action.arguments),
                    timeout=request.tool_timeout_seconds,
                )
            except (RetryableToolError, TimeoutError) as error:
                timed_out = isinstance(error, TimeoutError)
                if attempt <= request.max_retries:
                    recorder.add(
                        state="calling_tool",
                        event="tool_call_retry_scheduled",
                        attempt=attempt,
                        tool_name=action.tool_name,
                        details={
                            "reason": "timeout" if timed_out else "transient_error"
                        },
                    )
                    continue
                recorder.add(
                    state="calling_tool",
                    event="tool_call_failed",
                    attempt=attempt,
                    tool_name=action.tool_name,
                    details={
                        "error_code": "tool_timeout" if timed_out else "tool_failure",
                        "error_type": type(error).__name__,
                    },
                )
                if timed_out:
                    raise _ToolExecutionFailure(
                        "tool_timeout",
                        "训练复盘工具多次超时，Agent 已安全停止。",
                        retryable=True,
                    ) from error
                raise _ToolExecutionFailure(
                    "tool_failure",
                    "训练复盘工具发生瞬时错误且重试仍未成功。",
                    retryable=True,
                ) from error
            except Exception as error:
                recorder.add(
                    state="calling_tool",
                    event="tool_call_failed",
                    attempt=attempt,
                    tool_name=action.tool_name,
                    details={
                        "error_code": "tool_failure",
                        "error_type": type(error).__name__,
                    },
                )
                raise _ToolExecutionFailure(
                    "tool_failure",
                    "训练复盘工具发生不可重试错误，Agent 已安全停止。",
                    retryable=False,
                ) from error

            try:
                result = TrainingReviewResult.model_validate(raw_result)
            except ValidationError as error:
                recorder.add(
                    state="validating",
                    event="tool_call_failed",
                    attempt=attempt,
                    tool_name=action.tool_name,
                    details={
                        "error_code": "invalid_tool_output",
                        "validation_error_count": error.error_count(),
                    },
                )
                raise _ToolExecutionFailure(
                    "invalid_tool_output",
                    "训练复盘工具输出未通过 Schema 校验，Agent 已拒绝使用。",
                    retryable=False,
                ) from error
            if result.target_activity_id != request.review_request.target_activity_id:
                recorder.add(
                    state="validating",
                    event="tool_call_failed",
                    attempt=attempt,
                    tool_name=action.tool_name,
                    details={"error_code": "invalid_tool_output"},
                )
                raise _ToolExecutionFailure(
                    "invalid_tool_output",
                    "训练复盘工具返回了错误的目标活动，Agent 已拒绝使用。",
                    retryable=False,
                )
            recorder.add(
                state="calling_tool",
                event="tool_call_succeeded",
                attempt=attempt,
                tool_name=action.tool_name,
                details={
                    "input_hash": result.input_hash,
                    "ruleset_version": result.ruleset_version,
                },
            )
            return result
        raise AssertionError("tool retry loop exited unexpectedly")

    def _success_result(
        self,
        *,
        run_id: str,
        output: TrainingReviewResult,
        recorder: _TraceRecorder,
        usage: _Usage,
    ) -> ReviewAgentRunResult:
        recorder.add(
            state="validating",
            event="output_validation_started",
            details={"schema_version": output.schema_version},
        )
        validated_output = TrainingReviewResult.model_validate(output.model_dump())
        recorder.add(
            state="validating",
            event="output_validated",
            details={"input_hash": validated_output.input_hash},
        )
        recorder.add(
            state="completed",
            event="run_completed",
            details={"termination_reason": "completed"},
        )
        return ReviewAgentRunResult(
            run_id=run_id,
            status="succeeded",
            termination_reason="completed",
            output=validated_output,
            budget=self._budget(usage),
            trace=recorder.events,
        )

    def _failure_result(
        self,
        *,
        run_id: str,
        code: str,
        message: str,
        retryable: bool,
        recorder: _TraceRecorder,
        usage: _Usage,
        error_type: str | None = None,
        extra_details: dict[str, Any] | None = None,
    ) -> ReviewAgentRunResult:
        if code == "step_budget_exhausted":
            status = "budget_exhausted"
            event = "budget_exhausted"
        elif code in {"tool_timeout", "run_timeout"}:
            status = "timed_out"
            event = "run_timed_out"
        else:
            status = "failed"
            event = "run_failed"
        details: dict[str, Any] = {"error_code": code}
        if error_type is not None:
            details["error_type"] = error_type
        if extra_details:
            details.update(extra_details)
        recorder.add(
            state="failed",
            event=event,
            details=details,
        )
        return ReviewAgentRunResult(
            run_id=run_id,
            status=status,
            termination_reason=code,
            error=AgentRunError(
                code=code,
                message=message,
                retryable=retryable,
            ),
            budget=self._budget(usage),
            trace=recorder.events,
        )

    @staticmethod
    def _budget(usage: _Usage) -> AgentBudgetUsage:
        return AgentBudgetUsage(
            steps_used=usage.steps,
            tool_calls_used=usage.tool_calls,
            tool_attempts_used=usage.tool_attempts,
        )

    def _consume_policy_trace_details(self) -> dict[str, Any]:
        consume = getattr(self.policy, "consume_trace_details", None)
        if not callable(consume):
            return {}
        try:
            candidate = consume()
        except Exception:
            return {"policy_telemetry_error": "unavailable"}
        if not isinstance(candidate, dict):
            return {"policy_telemetry_error": "invalid_type"}
        allowed_keys = {
            "policy_provider",
            "policy_model",
            "policy_thinking_enabled",
            "policy_api_attempts",
            "policy_parse_errors",
            "policy_latency_ms",
            "policy_prompt_tokens",
            "policy_prompt_cache_hit_tokens",
            "policy_prompt_cache_miss_tokens",
            "policy_completion_tokens",
            "policy_reasoning_tokens",
            "policy_total_tokens",
            "policy_estimated_cost_usd",
            "policy_estimated_cost_basis",
            "policy_finish_reason",
            "policy_outcome",
        }
        return {
            key: value
            for key, value in candidate.items()
            if key in allowed_keys
            and (value is None or isinstance(value, str | int | float | bool))
        }
