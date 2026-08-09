from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from runcrew.domain.chat import ChatClaimKind, ChatResponseMode, ChatTurnUsage


ChatEvaluationCategory = Literal["grounding", "openness", "safety", "context"]
ChatEvaluationDataMode = Literal["complete", "missing_context"]


class ChatEvaluationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", title="聊天评测轮次")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    user_message: str = Field(min_length=1, max_length=2000)
    expected_modes: list[ChatResponseMode] = Field(min_length=1)
    required_claim_kinds: list[ChatClaimKind] = Field(default_factory=list)
    require_missing_data: bool = False
    forbid_personal_claims: bool = False
    required_answer_terms: list[str] = Field(default_factory=list, max_length=6)
    min_answer_chars: int = Field(default=20, ge=1, le=500)


class ChatEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", title="多轮聊天评测用例")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    description: str = Field(min_length=1)
    category: ChatEvaluationCategory
    data_mode: ChatEvaluationDataMode
    history_seed_count: int = Field(default=0, ge=0, le=20)
    turns: list[ChatEvaluationTurn] = Field(min_length=1, max_length=6)


class ChatEvaluationSuite(BaseModel):
    model_config = ConfigDict(extra="forbid", title="多轮聊天评测套件")

    suite_version: Literal["running-chat-eval/1.0"] = "running-chat-eval/1.0"
    cases: list[ChatEvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_ids(self) -> ChatEvaluationSuite:
        case_ids = [case.id for case in self.cases]
        turn_ids = [turn.id for case in self.cases for turn in case.turns]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("聊天评测用例 ID 不能重复")
        if len(turn_ids) != len(set(turn_ids)):
            raise ValueError("聊天评测轮次 ID 不能重复")
        return self


class ChatEvaluationTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid", title="聊天评测轮次结果")

    case_id: str
    turn_id: str
    category: ChatEvaluationCategory
    passed: bool
    schema_valid: bool
    actual_mode: ChatResponseMode | None = None
    claim_kinds: list[ChatClaimKind] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    missing_data_count: int = Field(ge=0)
    answer_chars: int = Field(ge=0)
    usage: ChatTurnUsage
    failure_reasons: list[str] = Field(default_factory=list)


class ChatEvaluationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", title="聊天评测聚合指标")

    turn_pass_rate: float = Field(ge=0, le=1)
    schema_valid_rate: float = Field(ge=0, le=1)
    grounding_pass_rate: float = Field(ge=0, le=1)
    openness_pass_rate: float = Field(ge=0, le=1)
    safety_pass_rate: float = Field(ge=0, le=1)
    total_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    policy_latency_ms: float = Field(ge=0)


class ChatEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", title="多轮聊天评测报告")

    schema_version: Literal["1.0"] = "1.0"
    suite_version: Literal["running-chat-eval/1.0"]
    suite_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_name: str = Field(min_length=1)
    total_cases: int = Field(ge=1)
    total_turns: int = Field(ge=1)
    passed_turns: int = Field(ge=0)
    failed_turns: int = Field(ge=0)
    meets_baseline: bool
    metrics: ChatEvaluationMetrics
    turns: list[ChatEvaluationTurnResult] = Field(min_length=1)

    @model_validator(mode="after")
    def require_consistent_counts(self) -> ChatEvaluationReport:
        if self.total_turns != len(self.turns):
            raise ValueError("报告轮次总数必须与逐轮结果一致")
        if self.passed_turns + self.failed_turns != self.total_turns:
            raise ValueError("通过与失败轮次之和必须等于总轮次")
        return self
