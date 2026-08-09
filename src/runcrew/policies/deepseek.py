from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Protocol
from urllib.parse import urlparse

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
)

from runcrew.domain.agent import (
    AGENT_ACTION_ADAPTER,
    REVIEW_TOOL_NAME,
    AgentAction,
    FinishAction,
    ReviewAgentContext,
    ToolCallAction,
)
from runcrew.domain.evaluation import PolicyEvaluationUsage
from runcrew.domain.training_review import TrainingReviewRequest


_SYSTEM_INSTRUCTION = """你是 RunCrew 中受 Harness 约束的训练复盘策略层。
你只选择下一步动作，不计算跑步指标，不补充事实，也不执行工具。
当 observation 为空时，只能调用 review_running_training，并原样使用 user_request 作为参数。
当 observation 已存在时，不再调用工具，返回简短结束消息即可。
不得修改活动 ID、训练计划、回看窗口、权限或预算，不得请求其他工具。"""

# 只用于可比较的费用估算；真实调用前仍需核对官方价格页。
_PRICING_USD_PER_MILLION_TOKENS = {
    "deepseek-v4-flash": {"cache_hit": 0.0028, "cache_miss": 0.14, "output": 0.28},
    "deepseek-v4-pro": {"cache_hit": 0.003625, "cache_miss": 0.435, "output": 0.87},
}
_PRICING_BASIS = "deepseek-pricing/2026-08-09"


class DeepSeekPolicyError(RuntimeError):
    """DeepSeek 策略无法产生合法动作；消息不得包含请求或响应正文。"""


class DeepSeekTransportError(DeepSeekPolicyError):
    """一次 DeepSeek HTTP 调用失败。"""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class DeepSeekPolicyConfig(BaseModel):
    """只保存调用所需配置；SecretStr 防止 Key 被 repr 或错误信息泄露。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key: SecretStr
    base_url: str = "https://api.deepseek.com"
    model: Literal["deepseek-v4-flash", "deepseek-v4-pro"] = (
        "deepseek-v4-flash"
    )
    request_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    max_output_tokens: int = Field(default=512, ge=32, le=4096)
    max_api_retries: int = Field(default=1, ge=0, le=3)
    max_estimated_cost_usd: float = Field(default=0.01, gt=0, le=1)

    @field_validator("api_key")
    @classmethod
    def require_api_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("DEEPSEEK_API_KEY 不能为空")
        return value

    @field_validator("base_url")
    @classmethod
    def require_official_https_endpoint(cls, value: str) -> str:
        normalized = value.rstrip("/")
        parsed = urlparse(normalized)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.deepseek.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("DEEPSEEK_BASE_URL 必须是 DeepSeek 官方 HTTPS 地址")
        return normalized

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
    ) -> DeepSeekPolicyConfig:
        source = os.environ if env is None else env
        api_key = source.get("DEEPSEEK_API_KEY")
        if api_key is None:
            raise DeepSeekPolicyError("缺少 DEEPSEEK_API_KEY，尚未发起模型请求。")
        data: dict[str, Any] = {
            "api_key": api_key,
            "base_url": source.get(
                "DEEPSEEK_BASE_URL",
                "https://api.deepseek.com",
            ),
            "model": source.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        }
        optional_fields = {
            "DEEPSEEK_REQUEST_TIMEOUT_SECONDS": "request_timeout_seconds",
            "DEEPSEEK_MAX_OUTPUT_TOKENS": "max_output_tokens",
            "DEEPSEEK_MAX_API_RETRIES": "max_api_retries",
            "DEEPSEEK_MAX_ESTIMATED_COST_USD": "max_estimated_cost_usd",
        }
        for env_name, field_name in optional_fields.items():
            if env_name in source:
                data[field_name] = source[env_name]
        try:
            return cls.model_validate(data)
        except ValidationError as error:
            raise DeepSeekPolicyError(
                "DeepSeek 环境变量配置无效，尚未发起模型请求。"
            ) from error


class DeepSeekChatTransport(Protocol):
    async def complete(self, payload: dict[str, Any]) -> Any:
        """执行一次 Chat Completions 请求并返回解码后的 JSON。"""


class HttpxDeepSeekTransport:
    """DeepSeek 官方 Chat Completions 的最小 HTTP 传输层。"""

    def __init__(
        self,
        config: DeepSeekPolicyConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport

    async def complete(self, payload: dict[str, Any]) -> Any:
        try:
            async with httpx.AsyncClient(
                timeout=self._config.request_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"{self._config.base_url}/chat/completions",
                    headers={
                        "Authorization": (
                            "Bearer "
                            + self._config.api_key.get_secret_value()
                        ),
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise DeepSeekTransportError(
                "DeepSeek 网络请求失败。",
                retryable=True,
            ) from error
        except httpx.RequestError as error:
            raise DeepSeekTransportError(
                "DeepSeek HTTP 请求无法完成。",
                retryable=True,
            ) from error

        if response.status_code == 429 or response.status_code >= 500:
            raise DeepSeekTransportError(
                f"DeepSeek 暂时不可用（HTTP {response.status_code}）。",
                retryable=True,
            )
        if response.status_code >= 400:
            raise DeepSeekTransportError(
                f"DeepSeek 拒绝请求（HTTP {response.status_code}）。",
                retryable=False,
            )
        if len(response.content) > 1_000_000:
            raise DeepSeekTransportError(
                "DeepSeek 响应超过本地大小限制。",
                retryable=False,
            )
        try:
            return response.json()
        except ValueError as error:
            raise DeepSeekTransportError(
                "DeepSeek 返回了无法解析的 JSON。",
                retryable=True,
            ) from error


class _FunctionCall(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    arguments: str


class _ToolCall(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    type: Literal["function"]
    function: _FunctionCall


class _AssistantMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str | None = None
    tool_calls: list[_ToolCall] | None = None


class _Choice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    finish_reason: Literal[
        "stop",
        "length",
        "content_filter",
        "tool_calls",
        "insufficient_system_resource",
    ]
    index: int
    message: _AssistantMessage


class _CompletionTokenDetails(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reasoning_tokens: int = Field(default=0, ge=0)


class _Usage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_tokens: int = Field(default=0, ge=0)
    prompt_cache_hit_tokens: int = Field(default=0, ge=0)
    prompt_cache_miss_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    completion_tokens_details: _CompletionTokenDetails = Field(
        default_factory=_CompletionTokenDetails
    )


class _ChatCompletion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    choices: list[_Choice] = Field(min_length=1, max_length=1)
    usage: _Usage = Field(default_factory=_Usage)


class DeepSeekPolicyTelemetry(BaseModel):
    """一次 Policy 决策的安全元数据，不保存 Prompt、响应正文或 Tool 参数。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["deepseek"] = "deepseek"
    configured_model: str
    response_model: str | None = None
    thinking_enabled: Literal[False] = False
    api_attempts: int = Field(ge=1)
    parse_errors: int = Field(ge=0)
    latency_ms: float = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    prompt_cache_hit_tokens: int = Field(ge=0)
    prompt_cache_miss_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    estimated_cost_basis: Literal["deepseek-pricing/2026-08-09"] = _PRICING_BASIS
    finish_reason: str | None = None
    action_type: Literal["call_tool", "finish"] | None = None
    outcome: Literal["succeeded", "failed"]

    def to_trace_details(self) -> dict[str, Any]:
        return {
            "policy_provider": self.provider,
            "policy_model": self.response_model or self.configured_model,
            "policy_thinking_enabled": self.thinking_enabled,
            "policy_api_attempts": self.api_attempts,
            "policy_parse_errors": self.parse_errors,
            "policy_latency_ms": self.latency_ms,
            "policy_prompt_tokens": self.prompt_tokens,
            "policy_prompt_cache_hit_tokens": self.prompt_cache_hit_tokens,
            "policy_prompt_cache_miss_tokens": self.prompt_cache_miss_tokens,
            "policy_completion_tokens": self.completion_tokens,
            "policy_reasoning_tokens": self.reasoning_tokens,
            "policy_total_tokens": self.total_tokens,
            "policy_estimated_cost_usd": self.estimated_cost_usd,
            "policy_estimated_cost_basis": self.estimated_cost_basis,
            "policy_finish_reason": self.finish_reason,
            "policy_outcome": self.outcome,
        }


@dataclass(slots=True)
class _UsageAccumulator:
    prompt_tokens: int = 0
    prompt_cache_hit_tokens: int = 0
    prompt_cache_miss_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0

    def add(self, usage: _Usage) -> None:
        self.prompt_tokens += usage.prompt_tokens
        self.prompt_cache_hit_tokens += usage.prompt_cache_hit_tokens
        self.prompt_cache_miss_tokens += usage.prompt_cache_miss_tokens
        self.completion_tokens += usage.completion_tokens
        self.reasoning_tokens += usage.completion_tokens_details.reasoning_tokens
        self.total_tokens += usage.total_tokens


class _RetryableResponseError(DeepSeekPolicyError):
    pass


class DeepSeekReviewPolicy:
    """使用 DeepSeek 选择动作，但把执行权和最终校验留给 Harness。"""

    def __init__(
        self,
        config: DeepSeekPolicyConfig,
        *,
        transport: DeepSeekChatTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = transport or HttpxDeepSeekTransport(config)
        self.telemetry: list[DeepSeekPolicyTelemetry] = []
        self._pending_trace_details: dict[str, Any] = {}
        self._initial_user_message: str | None = None
        self._assistant_tool_call_message: dict[str, Any] | None = None

    async def next_action(self, context: ReviewAgentContext) -> AgentAction:
        if context.step == 0:
            self.telemetry.clear()
            self._pending_trace_details = {}
            self._assistant_tool_call_message = None
            self._initial_user_message = self._context_message(context)
        payload = self._build_payload(context)
        started = time.perf_counter()
        usage = _UsageAccumulator()
        parse_errors = 0
        response_model: str | None = None
        finish_reason: str | None = None
        attempts = 0
        last_error: Exception | None = None

        for attempts in range(1, self.config.max_api_retries + 2):
            try:
                raw_response = await self._transport.complete(payload)
                response = _ChatCompletion.model_validate(raw_response)
                response_model = response.model
                usage.add(response.usage)
                finish_reason = response.choices[0].finish_reason
                action, selected_tool_call = self._parse_action(response)
            except DeepSeekTransportError as error:
                last_error = error
                if error.retryable and attempts <= self.config.max_api_retries:
                    continue
                break
            except (ValidationError, ValueError, _RetryableResponseError) as error:
                parse_errors += 1
                last_error = error
                if attempts <= self.config.max_api_retries:
                    continue
                break
            else:
                call_cost = _estimate_cost_usd(self.config.model, usage)
                previous_cost = sum(
                    item.estimated_cost_usd for item in self.telemetry
                )
                if previous_cost + call_cost > self.config.max_estimated_cost_usd:
                    telemetry = self._record_telemetry(
                        started=started,
                        attempts=attempts,
                        parse_errors=parse_errors,
                        usage=usage,
                        response_model=response_model,
                        finish_reason=finish_reason,
                        action_type=None,
                        outcome="failed",
                    )
                    self._pending_trace_details = telemetry.to_trace_details()
                    raise DeepSeekPolicyError(
                        "DeepSeek 估算费用超过本次 Policy 上限，已停止后续动作。"
                    )
                telemetry = self._record_telemetry(
                    started=started,
                    attempts=attempts,
                    parse_errors=parse_errors,
                    usage=usage,
                    response_model=response_model,
                    finish_reason=finish_reason,
                    action_type=action.type,
                    outcome="succeeded",
                )
                if isinstance(action, ToolCallAction) and selected_tool_call is not None:
                    self._assistant_tool_call_message = {
                        "role": "assistant",
                        "content": response.choices[0].message.content,
                        "tool_calls": [selected_tool_call.model_dump(mode="json")],
                    }
                self._pending_trace_details = telemetry.to_trace_details()
                return action

        telemetry = self._record_telemetry(
            started=started,
            attempts=max(attempts, 1),
            parse_errors=parse_errors,
            usage=usage,
            response_model=response_model,
            finish_reason=finish_reason,
            action_type=None,
            outcome="failed",
        )
        self._pending_trace_details = telemetry.to_trace_details()
        raise DeepSeekPolicyError(
            "DeepSeek 未能在重试预算内返回合法 Agent 动作。"
        ) from last_error

    def consume_trace_details(self) -> dict[str, Any]:
        details = self._pending_trace_details
        self._pending_trace_details = {}
        return details

    def evaluation_usage(self) -> PolicyEvaluationUsage:
        return PolicyEvaluationUsage(
            policy_calls=len(self.telemetry),
            api_attempts=sum(item.api_attempts for item in self.telemetry),
            action_parse_errors=sum(item.parse_errors for item in self.telemetry),
            latency_ms=round(sum(item.latency_ms for item in self.telemetry), 3),
            prompt_tokens=sum(item.prompt_tokens for item in self.telemetry),
            prompt_cache_hit_tokens=sum(
                item.prompt_cache_hit_tokens for item in self.telemetry
            ),
            prompt_cache_miss_tokens=sum(
                item.prompt_cache_miss_tokens for item in self.telemetry
            ),
            completion_tokens=sum(item.completion_tokens for item in self.telemetry),
            reasoning_tokens=sum(item.reasoning_tokens for item in self.telemetry),
            total_tokens=sum(item.total_tokens for item in self.telemetry),
            estimated_cost_usd=round(
                sum(item.estimated_cost_usd for item in self.telemetry),
                8,
            ),
            estimated_cost_basis=(
                _PRICING_BASIS if self.telemetry else None
            ),
        )

    def _build_payload(self, context: ReviewAgentContext) -> dict[str, Any]:
        initial_user_message = self._initial_user_message or self._context_message(context)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_INSTRUCTION},
            {"role": "user", "content": initial_user_message},
        ]
        tool_choice = "auto"
        if context.observation is not None:
            if self._assistant_tool_call_message is not None:
                tool_call_id = self._assistant_tool_call_message["tool_calls"][0]["id"]
                tool_result = {
                    "observation": context.observation.model_dump(mode="json"),
                    "remaining_steps": context.remaining_steps,
                    "remaining_tool_calls": context.remaining_tool_calls,
                }
                messages.extend(
                    [
                        self._assistant_tool_call_message,
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": json.dumps(
                                tool_result,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        },
                    ]
                )
            else:
                # 防御性降级：如果 Policy 从一个已有 Observation 的上下文启动，
                # 不允许在缺少对应 Tool Call 的情况下再次调用工具。
                messages.append(
                    {
                        "role": "user",
                        "content": "训练复盘 Observation 已存在，请结束本次运行。",
                    }
                )
                tool_choice = "none"
        return {
            "model": self.config.model,
            "messages": messages,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": REVIEW_TOOL_NAME,
                        "description": "调用确定性 Training Review Skill，返回带证据的训练复盘。",
                        "parameters": TrainingReviewRequest.model_json_schema(),
                        "strict": False,
                    },
                }
            ],
            "tool_choice": tool_choice,
            "thinking": {"type": "disabled"},
            "max_tokens": self.config.max_output_tokens,
            "stream": False,
        }

    @staticmethod
    def _context_message(context: ReviewAgentContext) -> str:
        context_json = json.dumps(
            context.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return "以下是唯一允许使用的上下文 JSON：\n" + context_json

    @staticmethod
    def _parse_action(
        response: _ChatCompletion,
    ) -> tuple[AgentAction, _ToolCall | None]:
        choice = response.choices[0]
        if choice.finish_reason == "insufficient_system_resource":
            raise _RetryableResponseError("DeepSeek 推理资源暂时不足")
        if choice.finish_reason == "length":
            raise _RetryableResponseError("DeepSeek 输出被 Token 上限截断")
        if choice.finish_reason == "content_filter":
            raise ValueError("DeepSeek 内容过滤阻止了动作输出")

        tool_calls = choice.message.tool_calls or []
        if tool_calls:
            if len(tool_calls) != 1:
                raise _RetryableResponseError("一次策略步骤只能请求一个工具")
            tool_call = tool_calls[0]
            try:
                arguments = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError as error:
                raise _RetryableResponseError("工具参数不是合法 JSON") from error
            return (
                AGENT_ACTION_ADAPTER.validate_python(
                    {
                        "type": "call_tool",
                        "tool_name": tool_call.function.name,
                        "arguments": arguments,
                    }
                ),
                tool_call,
            )

        if choice.finish_reason == "tool_calls":
            raise _RetryableResponseError("响应声明工具调用但没有 Tool Call")
        return FinishAction(), None

    def _record_telemetry(
        self,
        *,
        started: float,
        attempts: int,
        parse_errors: int,
        usage: _UsageAccumulator,
        response_model: str | None,
        finish_reason: str | None,
        action_type: Literal["call_tool", "finish"] | None,
        outcome: Literal["succeeded", "failed"],
    ) -> DeepSeekPolicyTelemetry:
        telemetry = DeepSeekPolicyTelemetry(
            configured_model=self.config.model,
            response_model=response_model,
            api_attempts=attempts,
            parse_errors=parse_errors,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            prompt_tokens=usage.prompt_tokens,
            prompt_cache_hit_tokens=usage.prompt_cache_hit_tokens,
            prompt_cache_miss_tokens=usage.prompt_cache_miss_tokens,
            completion_tokens=usage.completion_tokens,
            reasoning_tokens=usage.reasoning_tokens,
            total_tokens=usage.total_tokens,
            estimated_cost_usd=_estimate_cost_usd(self.config.model, usage),
            finish_reason=finish_reason,
            action_type=action_type,
            outcome=outcome,
        )
        self.telemetry.append(telemetry)
        return telemetry


def _estimate_cost_usd(model: str, usage: _UsageAccumulator) -> float:
    prices = _PRICING_USD_PER_MILLION_TOKENS[model]
    accounted_prompt = (
        usage.prompt_cache_hit_tokens + usage.prompt_cache_miss_tokens
    )
    unclassified_prompt = max(usage.prompt_tokens - accounted_prompt, 0)
    cache_miss_tokens = usage.prompt_cache_miss_tokens + unclassified_prompt
    cost = (
        usage.prompt_cache_hit_tokens * prices["cache_hit"]
        + cache_miss_tokens * prices["cache_miss"]
        + usage.completion_tokens * prices["output"]
    ) / 1_000_000
    return round(cost, 8)
