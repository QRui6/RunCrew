from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ToolOwnerRole = Literal[
    "review_agent",
    "execution_agent",
    "recovery_agent",
    "plan_agent",
]
ToolAccessLevel = Literal["read", "prepare_change", "commit_change"]
ToolSideEffect = Literal["none", "state_proposal", "state_mutation"]
ToolRiskLevel = Literal["low", "sensitive", "critical"]
GuardrailStage = Literal[
    "registration",
    "permission",
    "confirmation",
    "input_integrity",
    "runtime_limits",
    "output_validation",
]
GuardrailOutcome = Literal["allow", "deny", "require_confirmation"]


class ToolManifest(BaseModel):
    """Agent 工具的静态能力声明，不包含凭据或真实业务数据。"""

    model_config = ConfigDict(extra="forbid", title="Agent Tool Manifest")

    schema_version: Literal["tool-manifest/1.0"] = "tool-manifest/1.0"
    tool_name: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    owner_role: ToolOwnerRole
    description: str = Field(min_length=1, max_length=200)
    input_schema: str = Field(min_length=1)
    output_schema: str = Field(min_length=1)
    access_level: ToolAccessLevel
    side_effect: ToolSideEffect
    risk_level: ToolRiskLevel
    confirmation_required: bool = False
    can_persist: bool = False
    can_approve: bool = False
    idempotent: bool
    maximum_timeout_seconds: float = Field(gt=0, le=120)
    maximum_retries: int = Field(ge=0, le=5)
    sensitive_fields: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def enforce_capability_invariants(self) -> ToolManifest:
        if self.side_effect == "none" and self.can_persist:
            raise ValueError("无副作用工具不能声明持久化能力")
        if self.access_level == "prepare_change" and (
            self.can_persist or self.can_approve
        ):
            raise ValueError("提案工具不能持久化或批准变更")
        if self.side_effect == "state_mutation":
            if self.access_level != "commit_change" or not self.can_persist:
                raise ValueError("状态写入工具必须声明 commit_change 与持久化能力")
            if not self.confirmation_required:
                raise ValueError("状态写入工具必须要求人工确认")
        if self.can_approve and not self.confirmation_required:
            raise ValueError("具备审批能力的工具必须要求人工确认")
        if self.risk_level == "critical" and not self.confirmation_required:
            raise ValueError("关键风险工具必须要求人工确认")
        if len(self.sensitive_fields) != len(set(self.sensitive_fields)):
            raise ValueError("敏感字段名称不能重复")
        return self


class GuardrailDecision(BaseModel):
    """一条可稳定测试的治理规则决策。"""

    model_config = ConfigDict(extra="forbid", title="Runtime Guardrail Decision")

    rule_id: str = Field(min_length=1, pattern=r"^[a-z0-9_.-]+/\d+\.\d+$")
    stage: GuardrailStage
    outcome: GuardrailOutcome
    reason: str = Field(min_length=1, max_length=300)
    details: dict[str, Any] = Field(default_factory=dict)


class ToolInvocationGuardrailResult(BaseModel):
    """工具执行前的完整、脱敏治理结果。"""

    model_config = ConfigDict(extra="forbid", title="Tool Invocation Guardrail Result")

    schema_version: Literal["runtime-guardrail-result/1.0"] = (
        "runtime-guardrail-result/1.0"
    )
    tool_name: str = Field(min_length=1)
    allowed: bool
    manifest_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    input_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    expected_input_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    decisions: list[GuardrailDecision] = Field(min_length=1)

    @model_validator(mode="after")
    def allowed_matches_decisions(self) -> ToolInvocationGuardrailResult:
        expected = all(item.outcome == "allow" for item in self.decisions)
        if self.allowed != expected:
            raise ValueError("allowed 必须与全部 Guardrail 决策一致")
        return self


class ToolOutputGuardrailResult(BaseModel):
    """工具返回值的 Schema 治理结果，不保存返回正文。"""

    model_config = ConfigDict(extra="forbid", title="Tool Output Guardrail Result")

    schema_version: Literal["runtime-output-guardrail/1.0"] = (
        "runtime-output-guardrail/1.0"
    )
    tool_name: str = Field(min_length=1)
    allowed: bool
    output_schema: str = Field(min_length=1)
    decision: GuardrailDecision

    @model_validator(mode="after")
    def allowed_matches_decision(self) -> ToolOutputGuardrailResult:
        if self.allowed != (self.decision.outcome == "allow"):
            raise ValueError("allowed 必须与输出 Guardrail 决策一致")
        return self
