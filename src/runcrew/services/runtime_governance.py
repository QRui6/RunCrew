from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from runcrew.domain.agent import REVIEW_TOOL_NAME
from runcrew.domain.coach import EXECUTION_TOOL_NAME, PLAN_TOOL_NAME, RECOVERY_TOOL_NAME
from runcrew.domain.recovery_assessment import RecoveryAssessmentRequest, RecoveryAssessmentResult
from runcrew.domain.runtime_governance import (
    GuardrailDecision,
    ToolAccessLevel,
    ToolInvocationGuardrailResult,
    ToolManifest,
    ToolOutputGuardrailResult,
    ToolOwnerRole,
)
from runcrew.domain.training_execution import TrainingExecutionRequest, TrainingExecutionResult
from runcrew.domain.training_planning import PlanAdjustmentRequest, TrainingPlanningResult
from runcrew.domain.training_review import TrainingReviewRequest, TrainingReviewResult


ModelT = TypeVar("ModelT", bound=BaseModel)


def canonical_hash(value: Any) -> str:
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


class ToolCapabilityRegistry:
    """只读工具注册表；启动时拒绝重复名称。"""

    def __init__(self, manifests: Iterable[ToolManifest]) -> None:
        registered: dict[str, ToolManifest] = {}
        for manifest in manifests:
            if manifest.tool_name in registered:
                raise ValueError(f"工具重复注册：{manifest.tool_name}")
            registered[manifest.tool_name] = manifest
        self._manifests = registered

    def get(self, tool_name: str) -> ToolManifest | None:
        return self._manifests.get(tool_name)

    def list(self) -> list[ToolManifest]:
        return [self._manifests[name] for name in sorted(self._manifests)]


DEFAULT_TOOL_MANIFESTS = (
    ToolManifest(
        tool_name=REVIEW_TOOL_NAME,
        owner_role="review_agent",
        description="基于规范化活动和近期训练上下文生成可验证训练复盘。",
        input_schema=TrainingReviewRequest.__name__,
        output_schema=TrainingReviewResult.__name__,
        access_level="read",
        side_effect="none",
        risk_level="low",
        idempotent=True,
        maximum_timeout_seconds=60,
        maximum_retries=3,
        sensitive_fields=["target_activity_id"],
    ),
    ToolManifest(
        tool_name=EXECUTION_TOOL_NAME,
        owner_role="execution_agent",
        description="对照已激活训练计划与规范化活动，生成待确认执行判断。",
        input_schema=TrainingExecutionRequest.__name__,
        output_schema=TrainingExecutionResult.__name__,
        access_level="read",
        side_effect="none",
        risk_level="low",
        idempotent=True,
        maximum_timeout_seconds=60,
        maximum_retries=3,
        sensitive_fields=["plan_id"],
    ),
    ToolManifest(
        tool_name=RECOVERY_TOOL_NAME,
        owner_role="recovery_agent",
        description="根据确定性训练与主观反馈上下文评估恢复风险。",
        input_schema=RecoveryAssessmentRequest.__name__,
        output_schema=RecoveryAssessmentResult.__name__,
        access_level="read",
        side_effect="none",
        risk_level="sensitive",
        idempotent=True,
        maximum_timeout_seconds=60,
        maximum_retries=3,
        sensitive_fields=["goal_id", "pain_level", "fatigue_level"],
    ),
    ToolManifest(
        tool_name=PLAN_TOOL_NAME,
        owner_role="plan_agent",
        description="把恢复结论转换为待用户审核的训练计划调整提案。",
        input_schema=PlanAdjustmentRequest.__name__,
        output_schema=TrainingPlanningResult.__name__,
        access_level="prepare_change",
        side_effect="state_proposal",
        risk_level="sensitive",
        idempotent=True,
        maximum_timeout_seconds=60,
        maximum_retries=3,
        sensitive_fields=["goal_id", "evidence_refs"],
    ),
)


def build_default_tool_registry() -> ToolCapabilityRegistry:
    return ToolCapabilityRegistry(DEFAULT_TOOL_MANIFESTS)


class RuntimeGuardrailEngine:
    """在工具执行前后作出统一、脱敏且可回放的治理决策。"""

    def __init__(self, registry: ToolCapabilityRegistry | None = None) -> None:
        self.registry = registry or build_default_tool_registry()

    def evaluate_invocation(
        self,
        *,
        tool_name: str,
        owner_role: ToolOwnerRole,
        granted_access: ToolAccessLevel,
        actual_arguments: Any,
        expected_arguments: Any,
        timeout_seconds: float,
        max_retries: int,
        confirmation_required: bool = False,
        confirmed: bool = False,
        can_persist: bool = False,
        can_approve: bool = False,
    ) -> ToolInvocationGuardrailResult:
        manifest = self.registry.get(tool_name)
        if manifest is None:
            return ToolInvocationGuardrailResult(
                tool_name=tool_name,
                allowed=False,
                decisions=[
                    GuardrailDecision(
                        rule_id="tool.registered/1.0",
                        stage="registration",
                        outcome="deny",
                        reason="工具未注册，调用已拒绝。",
                    )
                ],
            )

        manifest_hash = canonical_hash(manifest)
        input_hash = canonical_hash(actual_arguments)
        expected_input_hash = canonical_hash(expected_arguments)
        decisions = [
            GuardrailDecision(
                rule_id="tool.registered/1.0",
                stage="registration",
                outcome="allow",
                reason="工具存在于只读能力注册表。",
            ),
            GuardrailDecision(
                rule_id="tool.owner-role/1.0",
                stage="permission",
                outcome="allow" if owner_role == manifest.owner_role else "deny",
                reason=(
                    "调用角色与工具责任角色一致。"
                    if owner_role == manifest.owner_role
                    else "调用角色不拥有该工具。"
                ),
                details={"owner_role": manifest.owner_role},
            ),
            GuardrailDecision(
                rule_id="tool.access-level/1.0",
                stage="permission",
                outcome=(
                    "allow" if granted_access == manifest.access_level else "deny"
                ),
                reason=(
                    "授予的访问级别与工具声明一致。"
                    if granted_access == manifest.access_level
                    else "授予的访问级别与工具声明不一致。"
                ),
                details={"manifest_access": manifest.access_level},
            ),
            GuardrailDecision(
                rule_id="tool.capability-ceiling/1.0",
                stage="permission",
                outcome=(
                    "allow"
                    if (not can_persist or manifest.can_persist)
                    and (not can_approve or manifest.can_approve)
                    else "deny"
                ),
                reason=(
                    "持久化与审批能力未越过 Manifest 上限。"
                    if (not can_persist or manifest.can_persist)
                    and (not can_approve or manifest.can_approve)
                    else "持久化或审批能力与 Manifest 不一致。"
                ),
                details={
                    "manifest_can_persist": manifest.can_persist,
                    "manifest_can_approve": manifest.can_approve,
                },
            ),
        ]

        requires_confirmation = manifest.confirmation_required or confirmation_required
        decisions.append(
            GuardrailDecision(
                rule_id="tool.confirmation/1.0",
                stage="confirmation",
                outcome=(
                    "require_confirmation"
                    if requires_confirmation and not confirmed
                    else "allow"
                ),
                reason=(
                    "工具调用缺少要求的用户确认。"
                    if requires_confirmation and not confirmed
                    else "工具不需要确认或已经获得确认。"
                ),
                details={"confirmation_required": requires_confirmation},
            )
        )
        decisions.append(
            GuardrailDecision(
                rule_id="tool.argument-integrity/1.0",
                stage="input_integrity",
                outcome="allow" if input_hash == expected_input_hash else "deny",
                reason=(
                    "工具参数与 Harness 可信输入一致。"
                    if input_hash == expected_input_hash
                    else "工具参数与 Harness 可信输入不一致。"
                ),
            )
        )
        within_limits = (
            timeout_seconds <= manifest.maximum_timeout_seconds
            and max_retries <= manifest.maximum_retries
        )
        decisions.append(
            GuardrailDecision(
                rule_id="tool.runtime-limits/1.0",
                stage="runtime_limits",
                outcome="allow" if within_limits else "deny",
                reason=(
                    "调用超时与重试预算在 Manifest 上限内。"
                    if within_limits
                    else "调用超时或重试预算超过 Manifest 上限。"
                ),
                details={
                    "requested_timeout_seconds": timeout_seconds,
                    "maximum_timeout_seconds": manifest.maximum_timeout_seconds,
                    "requested_retries": max_retries,
                    "maximum_retries": manifest.maximum_retries,
                },
            )
        )
        return ToolInvocationGuardrailResult(
            tool_name=tool_name,
            allowed=all(item.outcome == "allow" for item in decisions),
            manifest_hash=manifest_hash,
            input_hash=input_hash,
            expected_input_hash=expected_input_hash,
            decisions=decisions,
        )

    def validate_output(
        self,
        *,
        tool_name: str,
        raw_output: Any,
        output_model: type[ModelT],
    ) -> tuple[ModelT | None, ToolOutputGuardrailResult]:
        manifest = self.registry.get(tool_name)
        declared_schema = manifest.output_schema if manifest else output_model.__name__
        if manifest is None or declared_schema != output_model.__name__:
            return None, ToolOutputGuardrailResult(
                tool_name=tool_name,
                allowed=False,
                output_schema=declared_schema,
                decision=GuardrailDecision(
                    rule_id="tool.output-schema/1.0",
                    stage="output_validation",
                    outcome="deny",
                    reason="工具未注册或输出 Schema 与 Manifest 不一致。",
                ),
            )
        try:
            output = output_model.model_validate(raw_output)
        except ValidationError as error:
            return None, ToolOutputGuardrailResult(
                tool_name=tool_name,
                allowed=False,
                output_schema=declared_schema,
                decision=GuardrailDecision(
                    rule_id="tool.output-schema/1.0",
                    stage="output_validation",
                    outcome="deny",
                    reason="工具输出未通过声明的 Schema 校验。",
                    details={"validation_error_count": error.error_count()},
                ),
            )
        return output, ToolOutputGuardrailResult(
            tool_name=tool_name,
            allowed=True,
            output_schema=declared_schema,
            decision=GuardrailDecision(
                rule_id="tool.output-schema/1.0",
                stage="output_validation",
                outcome="allow",
                reason="工具输出通过 Manifest 声明的 Schema 校验。",
            ),
        )


def guardrail_trace_details(result: ToolInvocationGuardrailResult) -> dict[str, Any]:
    """生成可直接写入既有 Trace 的脱敏摘要。"""

    return {
        "allowed": result.allowed,
        "guardrail_schema_version": result.schema_version,
        "manifest_hash": result.manifest_hash,
        "input_hash_match": (
            result.input_hash == result.expected_input_hash
            if result.input_hash is not None and result.expected_input_hash is not None
            else None
        ),
        "rules": [
            {"rule_id": item.rule_id, "outcome": item.outcome}
            for item in result.decisions
        ],
    }
