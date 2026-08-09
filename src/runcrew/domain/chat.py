from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ChatRole = Literal["user", "assistant"]
ChatConfidence = Literal["high", "medium", "low"]
ChatResponseMode = Literal[
    "data_analysis",
    "mixed_coaching",
    "general_knowledge",
    "clarification",
    "safety_redirect",
]
ChatClaimKind = Literal[
    "observed_fact",
    "data_inference",
    "general_knowledge",
    "coaching_suggestion",
]


class ChatClaim(BaseModel):
    """回答中的依据说明；正文保持自然，这里只承载可审计的事实边界。"""

    model_config = ConfigDict(extra="forbid", title="跑步对话论断")

    statement: str = Field(min_length=1, max_length=500)
    kind: ChatClaimKind
    evidence_refs: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def require_evidence_for_personal_claims(self) -> ChatClaim:
        if self.kind in {"observed_fact", "data_inference"} and not self.evidence_refs:
            raise ValueError("个人数据事实和数据推断必须引用 evidence")
        return self


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", title="跑步对话消息")

    id: int
    role: ChatRole
    content: str = Field(min_length=1, max_length=4000)
    created_at: datetime
    model: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: ChatConfidence | None = None
    missing_data: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    response_mode: ChatResponseMode | None = None
    grounded_claims: list[ChatClaim] = Field(default_factory=list)
    follow_up_suggestions: list[str] = Field(default_factory=list)


class ChatConversation(BaseModel):
    model_config = ConfigDict(extra="forbid", title="跑步数据对话")

    id: str
    target_activity_id: str
    title: str = Field(min_length=1, max_length=80)
    created_at: datetime
    updated_at: datetime
    review_input_hash: str | None = None
    message_count: int = Field(default=0, ge=0)
    messages: list[ChatMessage] = Field(default_factory=list)


class ChatAnswer(BaseModel):
    """模型或离线策略必须返回的、可验证的回答契约。"""

    model_config = ConfigDict(extra="forbid", title="跑步 Agent 回答")

    answer: str = Field(min_length=1, max_length=5000)
    response_mode: ChatResponseMode = "data_analysis"
    grounded_claims: list[ChatClaim] = Field(default_factory=list, max_length=8)
    evidence_refs: list[str] = Field(default_factory=list, max_length=3)
    confidence: ChatConfidence
    missing_data: list[str] = Field(default_factory=list, max_length=8)
    follow_up_suggestions: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("evidence_refs")
    @classmethod
    def unique_evidence_refs(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    @field_validator("answer")
    @classmethod
    def reject_medical_diagnosis(cls, value: str) -> str:
        prohibited = ("确诊为", "诊断为", "你患有", "处方药", "替代医生")
        if any(phrase in value for phrase in prohibited):
            raise ValueError("回答包含越界医疗诊断表述")
        return value

    @model_validator(mode="after")
    def align_free_answer_with_grounding(self) -> ChatAnswer:
        # 兼容 M6-A2 已保存的回答：旧数据只有聚合 evidence_refs。
        if not self.grounded_claims and self.evidence_refs:
            self.grounded_claims = [
                ChatClaim(
                    statement=self.answer[:500],
                    kind="observed_fact",
                    evidence_refs=self.evidence_refs,
                )
            ]
        claim_refs = list(
            dict.fromkeys(
                ref
                for claim in self.grounded_claims
                for ref in claim.evidence_refs
            )
        )
        if not self.evidence_refs:
            self.evidence_refs = claim_refs
        elif not set(claim_refs).issubset(self.evidence_refs):
            raise ValueError("论断引用必须包含在回答 evidence_refs 中")
        if self.response_mode in {"data_analysis", "mixed_coaching"} and not any(
            claim.kind in {"observed_fact", "data_inference"}
            for claim in self.grounded_claims
        ):
            raise ValueError("数据分析或混合建议至少需要一条有依据的个人数据论断")
        return self


class ChatTurnUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", title="对话轮次用量")

    provider: Literal["offline", "deepseek"]
    model: str
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0, ge=0)


class ChatTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid", title="对话轮次结果")

    conversation: ChatConversation
    answer: ChatAnswer
    usage: ChatTurnUsage
    review_trace: list[dict[str, object]] = Field(default_factory=list)
    context_message_count: int = Field(ge=0)
    context_truncated: bool = False
