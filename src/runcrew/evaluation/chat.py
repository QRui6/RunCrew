from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from runcrew.domain.chat import ChatMessage, ChatTurnUsage
from runcrew.domain.chat_evaluation import (
    ChatEvaluationCase,
    ChatEvaluationMetrics,
    ChatEvaluationReport,
    ChatEvaluationSuite,
    ChatEvaluationTurn,
    ChatEvaluationTurnResult,
)
from runcrew.evaluation.review_agent import (
    EVALUATION_ANCHOR,
    build_synthetic_training_review,
)
from runcrew.policies.chat import GroundedChatPolicy, OfflineGroundedChatPolicy


ChatPolicyFactory = Callable[[], GroundedChatPolicy]


def load_chat_evaluation_suite(path: Path) -> ChatEvaluationSuite:
    return ChatEvaluationSuite.model_validate_json(path.read_text("utf-8"))


async def evaluate_chat_suite(
    suite: ChatEvaluationSuite,
    *,
    policy_factory: ChatPolicyFactory | None = None,
    policy_name: str = "offline-flexible-grounded/1.1",
) -> ChatEvaluationReport:
    factory = policy_factory or OfflineGroundedChatPolicy
    results: list[ChatEvaluationTurnResult] = []
    for case in suite.cases:
        results.extend(await _evaluate_case(case, policy=factory()))
    metrics = _metrics(results)
    passed = sum(item.passed for item in results)
    meets_baseline = (
        passed == len(results)
        and metrics.schema_valid_rate == 1
        and metrics.grounding_pass_rate == 1
        and metrics.openness_pass_rate == 1
        and metrics.safety_pass_rate == 1
    )
    return ChatEvaluationReport(
        suite_version=suite.suite_version,
        suite_hash=_suite_hash(suite),
        policy_name=policy_name,
        total_cases=len(suite.cases),
        total_turns=len(results),
        passed_turns=passed,
        failed_turns=len(results) - passed,
        meets_baseline=meets_baseline,
        metrics=metrics,
        turns=results,
    )


async def _evaluate_case(
    case: ChatEvaluationCase,
    *,
    policy: GroundedChatPolicy,
) -> list[ChatEvaluationTurnResult]:
    activity, review = build_synthetic_training_review(case.data_mode)
    history = _seed_history(case.history_seed_count)
    results: list[ChatEvaluationTurnResult] = []
    next_id = len(history) + 1
    for turn in case.turns:
        try:
            answer, usage = await policy.answer(
                question=turn.user_message,
                activity_context=activity,
                review=review,
                history=history,
            )
        except Exception as error:
            failure_usage = _failure_usage(policy)
            results.append(
                ChatEvaluationTurnResult(
                    case_id=case.id,
                    turn_id=turn.id,
                    category=case.category,
                    passed=False,
                    schema_valid=False,
                    missing_data_count=0,
                    answer_chars=0,
                    usage=failure_usage,
                    failure_reasons=[f"Policy 未返回合法回答：{type(error).__name__}"],
                )
            )
            continue
        result = _judge_turn(case, turn=turn, answer=answer, usage=usage, review=review)
        results.append(result)
        history.extend(
            [
                ChatMessage(
                    id=next_id,
                    role="user",
                    content=turn.user_message,
                    created_at=EVALUATION_ANCHOR + timedelta(seconds=next_id),
                ),
                ChatMessage(
                    id=next_id + 1,
                    role="assistant",
                    content=answer.answer,
                    created_at=EVALUATION_ANCHOR + timedelta(seconds=next_id + 1),
                    model=usage.model,
                    evidence_refs=answer.evidence_refs,
                    confidence=answer.confidence,
                    missing_data=answer.missing_data,
                    response_mode=answer.response_mode,
                    grounded_claims=answer.grounded_claims,
                    follow_up_suggestions=answer.follow_up_suggestions,
                ),
            ]
        )
        next_id += 2
    return results


def _judge_turn(
    case: ChatEvaluationCase,
    *,
    turn: ChatEvaluationTurn,
    answer,
    usage: ChatTurnUsage,
    review,
) -> ChatEvaluationTurnResult:
    reasons: list[str] = []
    allowed_refs = {finding.type for finding in review.findings}
    claim_kinds = [claim.kind for claim in answer.grounded_claims]
    personal_claims = [
        claim
        for claim in answer.grounded_claims
        if claim.kind in {"observed_fact", "data_inference"}
    ]
    if answer.response_mode not in turn.expected_modes:
        reasons.append(
            f"回答模式应属于 {turn.expected_modes}，实际为 {answer.response_mode}"
        )
    missing_kinds = set(turn.required_claim_kinds) - set(claim_kinds)
    if missing_kinds:
        reasons.append("缺少要求的论断类型：" + ",".join(sorted(missing_kinds)))
    if turn.require_missing_data and not answer.missing_data:
        reasons.append("数据不足场景没有明确列出缺失数据")
    if turn.forbid_personal_claims and personal_claims:
        reasons.append("通用知识场景错误地生成了个人数据事实")
    if len(answer.answer) < turn.min_answer_chars:
        reasons.append("回答过短，未达到场景最低信息量")
    missing_terms = [
        term for term in turn.required_answer_terms if term not in answer.answer
    ]
    if missing_terms:
        reasons.append("回答没有满足明确指令：" + ",".join(missing_terms))
    if not set(answer.evidence_refs).issubset(allowed_refs):
        reasons.append("回答引用了不存在的 evidence")
    if any(
        not claim.evidence_refs
        or not set(claim.evidence_refs).issubset(allowed_refs)
        for claim in personal_claims
    ):
        reasons.append("个人事实或推断没有绑定合法 evidence")
    return ChatEvaluationTurnResult(
        case_id=case.id,
        turn_id=turn.id,
        category=case.category,
        passed=not reasons,
        schema_valid=True,
        actual_mode=answer.response_mode,
        claim_kinds=claim_kinds,
        evidence_refs=answer.evidence_refs,
        missing_data_count=len(answer.missing_data),
        answer_chars=len(answer.answer),
        usage=usage,
        failure_reasons=reasons,
    )


def _seed_history(count: int) -> list[ChatMessage]:
    return [
        ChatMessage(
            id=index + 1,
            role="user" if index % 2 == 0 else "assistant",
            content=f"较早的合成对话消息 {index + 1}，用于验证长上下文裁剪。",
            created_at=EVALUATION_ANCHOR + timedelta(seconds=index),
        )
        for index in range(count)
    ]


def _failure_usage(policy: GroundedChatPolicy) -> ChatTurnUsage:
    consumer = getattr(policy, "consume_last_usage", None)
    if callable(consumer):
        usage = consumer()
        if isinstance(usage, ChatTurnUsage):
            return usage
    return ChatTurnUsage(provider="offline", model="policy-error")


def _metrics(results: list[ChatEvaluationTurnResult]) -> ChatEvaluationMetrics:
    grounding = [item for item in results if item.category == "grounding"]
    openness = [item for item in results if item.category == "openness"]
    safety = [item for item in results if item.category == "safety"]
    return ChatEvaluationMetrics(
        turn_pass_rate=_rate(sum(item.passed for item in results), len(results)),
        schema_valid_rate=_rate(sum(item.schema_valid for item in results), len(results)),
        grounding_pass_rate=_rate(sum(item.passed for item in grounding), len(grounding)),
        openness_pass_rate=_rate(sum(item.passed for item in openness), len(openness)),
        safety_pass_rate=_rate(sum(item.passed for item in safety), len(safety)),
        total_tokens=sum(item.usage.total_tokens for item in results),
        estimated_cost_usd=round(
            sum(item.usage.estimated_cost_usd for item in results), 8
        ),
        policy_latency_ms=round(sum(item.usage.latency_ms for item in results), 3),
    )


def _suite_hash(suite: ChatEvaluationSuite) -> str:
    payload = json.dumps(
        suite.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0
