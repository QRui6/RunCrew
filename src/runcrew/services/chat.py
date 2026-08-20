from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from runcrew.domain.activity import ActivityDetail, ActivitySummary
from runcrew.domain.agent import ReviewAgentRunRequest
from runcrew.domain.chat import ChatConversation, ChatTurnResult
from runcrew.domain.memory import (
    MemoryCandidateDecisionRequest,
    MemoryCandidateDecisionResult,
)
from runcrew.domain.training_review import TrainingReviewRequest, TrainingReviewResult
from runcrew.harness import ReviewAgentHarness
from runcrew.policies.chat import (
    DeepSeekGroundedChatPolicy,
    GroundedChatPolicy,
    OfflineGroundedChatPolicy,
)
from runcrew.policies.deepseek import DeepSeekPolicyConfig
from runcrew.services.training_review import execute_training_review
from runcrew.services.memory_candidates import (
    MemoryCandidateError,
    decide_memory_candidate,
    expire_pending_memory_candidates,
    propose_chat_memory_candidate,
)
from runcrew.storage.database import Database
from runcrew.storage.repositories import (
    ActivityRepository,
    AthletePreferenceRepository,
    ChatRepository,
    MemoryCandidateRepository,
)


class ChatActivityView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    provider: str
    started_at: datetime
    title: str
    distance_km: float | None
    duration: str
    average_pace: str | None
    average_heart_rate: int | None
    detail_available: bool


class ChatBootstrap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activities: list[ChatActivityView]
    conversations: list[ChatConversation]
    deepseek_available: bool
    default_mode: str = "offline"


class ChatServiceError(RuntimeError):
    pass


class ChatService:
    """编排会话持久化、训练复盘 Agent 和受证据约束的回答策略。"""

    def __init__(
        self,
        *,
        database_path: Path = Path("data/runcrew.db"),
        offline_policy: GroundedChatPolicy | None = None,
        deepseek_policy_factory: Callable[[], GroundedChatPolicy] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = database_path
        self.database = Database(
            f"sqlite:///{database_path.resolve().as_posix()}"
        )
        self.database.create_schema()
        self.offline_policy = offline_policy or OfflineGroundedChatPolicy()
        self.deepseek_policy_factory = deepseek_policy_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def bootstrap(self) -> ChatBootstrap:
        with self.database.session() as session:
            expire_pending_memory_candidates(
                candidates=MemoryCandidateRepository(session), now=self.clock()
            )
            activities = ActivityRepository(session).list(limit=30)
            conversations = ChatRepository(session).list(limit=30)
            session.commit()
        return ChatBootstrap(
            activities=[self._activity_view(item) for item in activities],
            conversations=conversations,
            deepseek_available=self._deepseek_available(),
        )

    def create_conversation(
        self,
        *,
        activity_id: str,
        title: str = "新的跑步对话",
        lookback_days: int = 28,
    ) -> ChatConversation:
        if not 14 <= lookback_days <= 90:
            raise ChatServiceError("回看天数必须在14到90天之间。")
        with self.database.session() as session:
            activity = ActivityRepository(session).get_by_id(activity_id)
            if activity is None:
                raise ChatServiceError("所选跑步活动不存在。")
            repository = ChatRepository(session)
            record = repository.create(
                target_activity_id=activity_id,
                title=(title.strip() or "新的跑步对话"),
                lookback_days=lookback_days,
            )
            conversation = repository.get(record.id)
            session.commit()
        assert conversation is not None
        return conversation

    def get_conversation(self, conversation_id: str) -> ChatConversation:
        with self.database.session() as session:
            expire_pending_memory_candidates(
                candidates=MemoryCandidateRepository(session),
                now=self.clock(),
                conversation_id=conversation_id,
            )
            conversation = ChatRepository(session).get(conversation_id)
            session.commit()
        if conversation is None:
            raise ChatServiceError("对话不存在。")
        return conversation

    async def send_message(
        self,
        *,
        conversation_id: str,
        content: str,
        use_deepseek: bool = False,
    ) -> ChatTurnResult:
        question = content.strip()
        if not question:
            raise ChatServiceError("消息不能为空。")
        if len(question) > 2000:
            raise ChatServiceError("单条消息不能超过2000个字符。")

        with self.database.session() as session:
            repository = ChatRepository(session)
            record = repository.get_record(conversation_id)
            if record is None:
                raise ChatServiceError("对话不存在。")
            user_message = repository.add_user_message(conversation_id, question)
            candidate = propose_chat_memory_candidate(
                question,
                conversation_id=conversation_id,
                source_message_id=user_message.id,
                candidates=MemoryCandidateRepository(session),
                now=self.clock(),
            )
            session.commit()

        review, review_trace, trace_id = await self._ensure_review(conversation_id)
        with self.database.session() as session:
            repository = ChatRepository(session)
            record = repository.get_record(conversation_id)
            assert record is not None
            activity = ActivityRepository(session).get_by_id(record.target_activity_id)
            history = repository.messages(conversation_id, limit=50)
        if activity is None:
            raise ChatServiceError("对话绑定的跑步活动已不存在。")

        policy = self._select_policy(use_deepseek)
        answer, usage = await policy.answer(
            question=question,
            activity_context=self._activity_view(activity).model_dump(mode="json"),
            review=review,
            history=history[:-1],
        )
        context_truncated = len(history[:-1]) > 8 or any(
            len(message.content) > 1200 for message in history[:-1][-8:]
        )

        with self.database.session() as session:
            repository = ChatRepository(session)
            repository.add_assistant_message(
                conversation_id,
                answer,
                usage=usage,
                trace_id=trace_id,
            )
            conversation = repository.get(conversation_id)
            session.commit()
        assert conversation is not None
        return ChatTurnResult(
            conversation=conversation,
            answer=answer,
            usage=usage,
            review_trace=review_trace,
            context_message_count=min(len(history[:-1]), 8),
            context_truncated=context_truncated,
            new_memory_candidates=[candidate] if candidate is not None else [],
        )

    def decide_memory_candidate(
        self,
        candidate_id: str,
        request: MemoryCandidateDecisionRequest,
    ) -> MemoryCandidateDecisionResult:
        decided_at = self.clock()
        try:
            with self.database.session() as session:
                expire_pending_memory_candidates(
                    candidates=MemoryCandidateRepository(session), now=decided_at
                )
                session.commit()
            with self.database.session() as session:
                result = decide_memory_candidate(
                    candidate_id,
                    request,
                    candidates=MemoryCandidateRepository(session),
                    preferences=AthletePreferenceRepository(session),
                    chats=ChatRepository(session),
                    now=decided_at,
                )
                session.commit()
            return result
        except MemoryCandidateError as error:
            raise ChatServiceError(str(error)) from error

    async def _ensure_review(
        self,
        conversation_id: str,
    ) -> tuple[TrainingReviewResult, list[dict[str, object]], str]:
        with self.database.session() as session:
            record = ChatRepository(session).get_record(conversation_id)
            if record is None:
                raise ChatServiceError("对话不存在。")
            if record.review_snapshot_json:
                review = TrainingReviewResult.model_validate_json(
                    record.review_snapshot_json
                )
                trace = json.loads(record.review_trace_json or "[]")
                return review, trace, review.input_hash[:12]
            request = TrainingReviewRequest(
                target_activity_id=record.target_activity_id,
                lookback_days=record.lookback_days,
            )

        async def tool(tool_request: TrainingReviewRequest) -> TrainingReviewResult:
            with self.database.session() as session:
                return execute_training_review(
                    tool_request,
                    store=ActivityRepository(session),
                )

        run_result = await ReviewAgentHarness().run(
            ReviewAgentRunRequest(review_request=request),
            tool=tool,
        )
        if run_result.output is None:
            message = run_result.error.message if run_result.error else "训练复盘失败。"
            raise ChatServiceError(message)
        trace = [item.model_dump(mode="json") for item in run_result.trace]
        with self.database.session() as session:
            record = ChatRepository(session).get_record(conversation_id)
            if record is None:
                raise ChatServiceError("对话不存在。")
            record.review_snapshot_json = run_result.output.model_dump_json()
            record.review_trace_json = json.dumps(
                trace, ensure_ascii=False, separators=(",", ":")
            )
            record.review_input_hash = run_result.output.input_hash
            session.commit()
        return run_result.output, trace, run_result.run_id

    def _select_policy(self, use_deepseek: bool) -> GroundedChatPolicy:
        if not use_deepseek:
            return self.offline_policy
        if not self._deepseek_available():
            raise ChatServiceError("本机没有配置 DEEPSEEK_API_KEY，不能启用模型回答。")
        if self.deepseek_policy_factory is not None:
            return self.deepseek_policy_factory()
        return DeepSeekGroundedChatPolicy(DeepSeekPolicyConfig.from_env())

    def _deepseek_available(self) -> bool:
        if self.deepseek_policy_factory is not None:
            return True
        return bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())

    @staticmethod
    def _activity_view(activity: ActivitySummary | ActivityDetail) -> ChatActivityView:
        return ChatActivityView(
            id=activity.id,
            provider=activity.source_ref.provider.value,
            started_at=activity.started_at,
            title=activity.title or "未命名跑步",
            distance_km=(
                round(activity.distance_meters / 1000, 2)
                if activity.distance_meters is not None
                else None
            ),
            duration=_format_duration(activity.duration_seconds),
            average_pace=_format_pace(activity.average_pace_seconds_per_km),
            average_heart_rate=activity.average_heart_rate,
            detail_available=isinstance(activity, ActivityDetail),
        )


def _format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    return (
        f"{hours}:{minutes:02d}:{remaining_seconds:02d}"
        if hours
        else f"{minutes}:{remaining_seconds:02d}"
    )


def _format_pace(seconds_per_km: float | None) -> str | None:
    if seconds_per_km is None:
        return None
    minutes, seconds = divmod(round(seconds_per_km), 60)
    return f"{minutes}:{seconds:02d}/km"
