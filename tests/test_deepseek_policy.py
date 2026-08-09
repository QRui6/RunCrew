from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from runcrew.domain.activity import (
    ActivityDetail,
    ActivitySummary,
    Lap,
    SourceProvider,
    SourceRef,
    SportType,
)
from runcrew.domain.agent import (
    REVIEW_TOOL_NAME,
    ReviewAgentContext,
    ReviewAgentRunRequest,
    ToolPermission,
)
from runcrew.domain.training_review import PlannedSession, TrainingReviewRequest
from runcrew.harness import ReviewAgentHarness
from runcrew.evaluation import evaluate_review_agent_suite, load_review_agent_suite
from runcrew.policies import (
    DeepSeekCostBudget,
    DeepSeekPolicyConfig,
    DeepSeekPolicyError,
    DeepSeekReviewPolicy,
    DeepSeekTransportError,
    HttpxDeepSeekTransport,
)
from runcrew.services.training_context import build_training_context
from runcrew.services.training_review import build_training_review


ANCHOR = datetime(2026, 8, 8, 8, tzinfo=timezone.utc)
SECRET = "sk-test-secret-must-never-appear"


class QueueTransport:
    def __init__(self, *items: Any) -> None:
        self.items = list(items)
        self.payloads: list[dict[str, Any]] = []

    async def complete(self, payload: dict[str, Any]) -> Any:
        self.payloads.append(payload)
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def policy_config(**overrides: Any) -> DeepSeekPolicyConfig:
    return DeepSeekPolicyConfig(
        api_key=SECRET,
        max_api_retries=1,
        **overrides,
    )


def review_request(identifier: str = "target") -> TrainingReviewRequest:
    return TrainingReviewRequest(
        target_activity_id=identifier,
        planned_session=PlannedSession(
            distance_meters=10_000,
            duration_seconds=3600,
        ),
    )


def activity(
    identifier: str,
    *,
    days_before: int,
    load: float,
    detail: bool = False,
) -> ActivitySummary | ActivityDetail:
    common = {
        "id": identifier,
        "source_ref": SourceRef(
            provider=SourceProvider.FIXTURE,
            external_id=f"fixture-{identifier}",
            fetched_at=ANCHOR,
            raw_payload_hash=f"hash-{identifier}",
        ),
        "sport_type": SportType.RUN,
        "started_at": ANCHOR - timedelta(days=days_before),
        "duration_seconds": 3600,
        "distance_meters": 10_000,
        "average_pace_seconds_per_km": 360,
        "average_heart_rate": 150,
        "training_load": load,
    }
    if not detail:
        return ActivitySummary(**common)
    return ActivityDetail(
        **common,
        laps=[
            Lap(
                index=index,
                duration_seconds=pace,
                distance_meters=1000,
                average_pace_seconds_per_km=pace,
            )
            for index, pace in enumerate((359, 360, 361, 360), start=1)
        ],
    )


def review_result():
    request = review_request()
    context = build_training_context(
        request,
        target=activity("target", days_before=0, load=50, detail=True),
        activities=[
            activity("current", days_before=3, load=40),
            activity("previous", days_before=8, load=50),
        ],
    )
    return build_training_review(context)


def completion(
    *,
    finish_reason: str,
    tool_name: str | None = None,
    arguments: str | None = None,
    prompt_tokens: int = 20,
    completion_tokens: int = 5,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": "assistant",
        "content": "已完成" if tool_name is None else None,
    }
    if tool_name is not None:
        message["tool_calls"] = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            }
        ]
    return {
        "id": "mock-completion",
        "model": "deepseek-v4-flash",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": message,
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "prompt_cache_hit_tokens": 4,
            "prompt_cache_miss_tokens": prompt_tokens - 4,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "completion_tokens_details": {"reasoning_tokens": 0},
        },
    }


def run_harness(policy: DeepSeekReviewPolicy, tool):
    harness = ReviewAgentHarness(
        policy=policy,
        run_id_factory=lambda: "deepseek-mock-run",
    )
    request = ReviewAgentRunRequest(review_request=review_request())
    return asyncio.run(harness.run(request, tool=tool))


def test_deepseek_policy_runs_full_mock_tool_loop_and_records_safe_trace() -> None:
    request = review_request()
    transport = QueueTransport(
        completion(
            finish_reason="tool_calls",
            tool_name=REVIEW_TOOL_NAME,
            arguments=request.model_dump_json(),
        ),
        completion(finish_reason="stop", prompt_tokens=30, completion_tokens=2),
    )
    policy = DeepSeekReviewPolicy(policy_config(), transport=transport)
    expected = review_result()

    async def tool(actual_request):
        assert actual_request == request
        return expected

    result = run_harness(policy, tool)

    assert result.status == "succeeded"
    assert result.output == expected
    assert len(policy.telemetry) == 2
    assert sum(item.total_tokens for item in policy.telemetry) == 57
    policy_events = [event for event in result.trace if event.event == "policy_action"]
    assert [event.details["action_type"] for event in policy_events] == [
        "call_tool",
        "finish",
    ]
    assert policy_events[0].details["policy_model"] == "deepseek-v4-flash"
    assert policy_events[0].details["policy_thinking_enabled"] is False
    assert SECRET not in result.model_dump_json()

    first_payload = transport.payloads[0]
    assert first_payload["thinking"] == {"type": "disabled"}
    assert first_payload["tool_choice"] == "auto"
    assert first_payload["max_tokens"] == 512
    assert first_payload["tools"][0]["function"]["name"] == REVIEW_TOOL_NAME
    assert first_payload["tools"][0]["function"]["strict"] is False
    assert SECRET not in json.dumps(first_payload, ensure_ascii=False)
    context_payload = json.loads(first_payload["messages"][1]["content"].split("\n", 1)[1])
    assert context_payload["user_request"] == request.model_dump(mode="json")
    assert context_payload["observation"] is None

    second_payload = transport.payloads[1]
    assert [message["role"] for message in second_payload["messages"]] == [
        "system",
        "user",
        "assistant",
        "tool",
    ]
    assistant_call = second_payload["messages"][2]["tool_calls"][0]
    tool_result_message = second_payload["messages"][3]
    assert assistant_call["id"] == "call_1"
    assert tool_result_message["tool_call_id"] == "call_1"
    tool_result = json.loads(tool_result_message["content"])
    assert tool_result["observation"]["target_activity_id"] == "target"
    assert tool_result["remaining_tool_calls"] == 0


def test_invalid_tool_arguments_are_retried_and_usage_is_accumulated() -> None:
    request = review_request()
    transport = QueueTransport(
        completion(
            finish_reason="tool_calls",
            tool_name=REVIEW_TOOL_NAME,
            arguments="{not-json",
            prompt_tokens=10,
            completion_tokens=3,
        ),
        completion(
            finish_reason="tool_calls",
            tool_name=REVIEW_TOOL_NAME,
            arguments=request.model_dump_json(),
            prompt_tokens=12,
            completion_tokens=4,
        ),
    )
    policy = DeepSeekReviewPolicy(policy_config(), transport=transport)

    async def tool(actual_request):
        return review_result()

    harness = ReviewAgentHarness(policy=policy, run_id_factory=lambda: "retry-run")
    run_request = ReviewAgentRunRequest(
        review_request=request,
        max_steps=1,
    )
    result = asyncio.run(harness.run(run_request, tool=tool))

    assert result.status == "budget_exhausted"
    assert len(transport.payloads) == 2
    first_decision = next(
        event for event in result.trace if event.event == "policy_action"
    )
    assert first_decision.details["policy_api_attempts"] == 2
    assert first_decision.details["policy_parse_errors"] == 1
    assert first_decision.details["policy_total_tokens"] == 29


def test_harness_blocks_model_argument_tampering_before_tool_execution() -> None:
    tampered = review_request("another-target")
    transport = QueueTransport(
        completion(
            finish_reason="tool_calls",
            tool_name=REVIEW_TOOL_NAME,
            arguments=tampered.model_dump_json(),
        )
    )
    policy = DeepSeekReviewPolicy(policy_config(), transport=transport)
    executed = False

    async def tool(actual_request):
        nonlocal executed
        executed = True
        return review_result()

    result = run_harness(policy, tool)

    assert result.status == "failed"
    assert result.termination_reason == "permission_denied"
    assert executed is False
    assert result.budget.tool_attempts_used == 0
    assert SECRET not in result.model_dump_json()


def test_policy_failure_is_sanitized_and_telemetry_reaches_failure_trace() -> None:
    private_response = "private activity data must not enter trace"
    transport = QueueTransport(
        DeepSeekTransportError(private_response, retryable=True),
        DeepSeekTransportError(private_response, retryable=True),
    )
    policy = DeepSeekReviewPolicy(policy_config(), transport=transport)

    async def tool(actual_request):
        raise AssertionError("policy failure must not execute the tool")

    result = run_harness(policy, tool)

    assert result.termination_reason == "policy_error"
    assert result.trace[-1].details["policy_api_attempts"] == 2
    assert result.trace[-1].details["policy_outcome"] == "failed"
    serialized = result.model_dump_json()
    assert private_response not in serialized
    assert SECRET not in serialized


def test_http_transport_uses_official_endpoint_and_never_embeds_key_in_body() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"ok": True})

    config = policy_config()
    transport = HttpxDeepSeekTransport(
        config,
        transport=httpx.MockTransport(handler),
    )
    response = asyncio.run(transport.complete({"model": config.model}))

    assert response == {"ok": True}
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["authorization"] == f"Bearer {SECRET}"
    assert SECRET not in captured["body"]
    assert SECRET not in repr(config)


def test_environment_config_fails_closed_without_leaking_secret() -> None:
    with pytest.raises(DeepSeekPolicyError, match="缺少 DEEPSEEK_API_KEY"):
        DeepSeekPolicyConfig.from_env({})

    with pytest.raises(DeepSeekPolicyError) as captured:
        DeepSeekPolicyConfig.from_env(
            {
                "DEEPSEEK_API_KEY": SECRET,
                "DEEPSEEK_BASE_URL": "http://attacker.example",
            }
        )
    assert SECRET not in str(captured.value)


def test_evaluation_aggregates_deepseek_policy_usage_without_real_api() -> None:
    suite = load_review_agent_suite(Path("evals/review_agent/cases.json"))
    smoke_suite = suite.model_copy(update={"cases": [suite.cases[0]]})
    request = review_request("target-complete")

    def factory():
        return DeepSeekReviewPolicy(
            policy_config(),
            transport=QueueTransport(
                completion(
                    finish_reason="tool_calls",
                    tool_name=REVIEW_TOOL_NAME,
                    arguments=request.model_dump_json(),
                ),
                completion(
                    finish_reason="stop",
                    prompt_tokens=30,
                    completion_tokens=2,
                ),
            ),
        )

    report = asyncio.run(
        evaluate_review_agent_suite(
            smoke_suite,
            default_policy_factory=factory,
            policy_name="deepseek-v4-flash-mock",
        )
    )

    assert report.meets_baseline is True
    assert report.schema_version == "1.1"
    assert report.metrics.policy_call_count == 2
    assert report.metrics.policy_api_attempt_count == 2
    assert report.metrics.policy_action_parse_error_count == 0
    assert report.metrics.total_tokens == 57
    assert report.metrics.estimated_cost_usd > 0
    assert report.metrics.estimated_cost_usd == pytest.approx(0.00000786)
    assert report.metrics.estimated_cost_basis == "deepseek-pricing/2026-08-09"
    assert report.cases[0].policy_usage.total_tokens == 57


def test_estimated_cost_cap_stops_before_tool_execution() -> None:
    request = review_request()
    transport = QueueTransport(
        completion(
            finish_reason="tool_calls",
            tool_name=REVIEW_TOOL_NAME,
            arguments=request.model_dump_json(),
        )
    )
    policy = DeepSeekReviewPolicy(
        policy_config(max_estimated_cost_usd=0.000001),
        transport=transport,
    )
    executed = False

    async def tool(actual_request):
        nonlocal executed
        executed = True
        return review_result()

    result = run_harness(policy, tool)

    assert result.termination_reason == "policy_error"
    assert executed is False
    assert result.trace[-1].details["policy_estimated_cost_usd"] > 0.000001
    assert result.trace[-1].details["policy_outcome"] == "failed"


def test_cost_budget_is_shared_across_policy_instances() -> None:
    request = review_request()
    shared_budget = DeepSeekCostBudget(max_estimated_cost_usd=0.000005)

    def make_policy() -> tuple[DeepSeekReviewPolicy, QueueTransport]:
        transport = QueueTransport(
            completion(
                finish_reason="tool_calls",
                tool_name=REVIEW_TOOL_NAME,
                arguments=request.model_dump_json(),
            )
        )
        policy = DeepSeekReviewPolicy(
            policy_config(max_estimated_cost_usd=0.000005),
            cost_budget=shared_budget,
            transport=transport,
        )
        return policy, transport

    context = ReviewAgentContext(
        user_request=request,
        tool_permissions=[ToolPermission(name=REVIEW_TOOL_NAME)],
        step=0,
        remaining_steps=4,
        remaining_tool_calls=1,
    )

    first_policy, first_transport = make_policy()
    first_action = asyncio.run(first_policy.next_action(context))

    assert first_action.type == "call_tool"
    assert len(first_transport.payloads) == 1
    assert shared_budget.consumed_estimated_cost_usd == pytest.approx(0.00000365)

    second_policy, second_transport = make_policy()
    with pytest.raises(DeepSeekPolicyError, match="共享估算费用超过上限"):
        asyncio.run(second_policy.next_action(context))

    assert len(second_transport.payloads) == 1
    assert second_policy.telemetry[-1].outcome == "failed"
    assert second_policy.telemetry[-1].estimated_cost_usd == pytest.approx(0.00000365)
    assert shared_budget.consumed_estimated_cost_usd > 0.000005

    third_policy, third_transport = make_policy()
    with pytest.raises(DeepSeekPolicyError, match="共享估算费用预算已经耗尽"):
        asyncio.run(third_policy.next_action(context))

    assert third_transport.payloads == []
