from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from runcrew.domain.activity import ActivityDetail, ActivitySummary
from runcrew.domain.chat import ChatAnswer, ChatConversation, ChatMessage, ChatTurnUsage
from runcrew.storage.models import (
    ActivityRecord,
    ChatConversationRecord,
    ChatMessageRecord,
    RawProviderEvent,
    SyncRunRecord,
)


def serialize_raw(payload: Mapping[str, Any]) -> tuple[str, str]:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return serialized, digest


class ActivityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, activity: ActivitySummary | ActivityDetail) -> bool:
        provider = activity.source_ref.provider.value
        external_id = activity.source_ref.external_id
        record = self.session.scalar(
            select(ActivityRecord).where(
                ActivityRecord.provider == provider,
                ActivityRecord.external_id == external_id,
            )
        )
        inserted = record is None
        if record is None:
            record = ActivityRecord(
                id=activity.id,
                provider=provider,
                external_id=external_id,
                started_at=activity.started_at,
                sport_type=activity.sport_type.value,
                activity_kind="detail"
                if isinstance(activity, ActivityDetail)
                else "summary",
                canonical_json="",
                raw_payload_hash=activity.source_ref.raw_payload_hash,
            )
            self.session.add(record)
        else:
            activity.id = record.id
            record.started_at = activity.started_at
            record.sport_type = activity.sport_type.value
            if isinstance(activity, ActivityDetail):
                record.activity_kind = "detail"

        record.canonical_json = activity.model_dump_json()
        record.raw_payload_hash = activity.source_ref.raw_payload_hash
        return inserted

    def list(self, limit: int = 20) -> list[ActivitySummary | ActivityDetail]:
        records = self.session.scalars(
            select(ActivityRecord)
            .order_by(desc(ActivityRecord.started_at))
            .limit(limit)
        ).all()
        return [self._to_domain(record) for record in records]

    def latest(
        self, provider: str | None = None
    ) -> ActivitySummary | ActivityDetail | None:
        statement = select(ActivityRecord)
        if provider is not None:
            statement = statement.where(ActivityRecord.provider == provider)
        record = self.session.scalar(
            statement.order_by(desc(ActivityRecord.started_at)).limit(1)
        )
        return self._to_domain(record) if record else None

    def get_by_id(self, activity_id: str) -> ActivitySummary | ActivityDetail | None:
        record = self.session.get(ActivityRecord, activity_id)
        return self._to_domain(record) if record else None

    def between(
        self,
        start: datetime,
        end: datetime,
        *,
        provider: str | None = None,
    ) -> list[ActivitySummary | ActivityDetail]:
        statement = select(ActivityRecord).where(
            ActivityRecord.started_at > start,
            ActivityRecord.started_at <= end,
        )
        if provider is not None:
            statement = statement.where(ActivityRecord.provider == provider)
        records = self.session.scalars(
            statement.order_by(ActivityRecord.started_at, ActivityRecord.id)
        ).all()
        return [self._to_domain(record) for record in records]

    def get_by_external_id(
        self, provider: str, external_id: str
    ) -> ActivitySummary | ActivityDetail | None:
        record = self.session.scalar(
            select(ActivityRecord).where(
                ActivityRecord.provider == provider,
                ActivityRecord.external_id == external_id,
            )
        )
        return self._to_domain(record) if record else None

    @staticmethod
    def _to_domain(record: ActivityRecord) -> ActivitySummary | ActivityDetail:
        model = ActivityDetail if record.activity_kind == "detail" else ActivitySummary
        return model.model_validate_json(record.canonical_json)


class RawEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        *,
        provider: str,
        operation: str,
        external_id: str | None,
        raw_payload: Mapping[str, Any],
        fetched_at: datetime,
    ) -> str:
        serialized, payload_hash = serialize_raw(raw_payload)
        self.session.add(
            RawProviderEvent(
                provider=provider,
                operation=operation,
                external_id=external_id,
                raw_payload=serialized,
                payload_hash=payload_hash,
                fetched_at=fetched_at,
            )
        )
        return payload_hash


class SyncRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def start(self, provider: str) -> SyncRunRecord:
        record = SyncRunRecord(provider=provider, status="running")
        self.session.add(record)
        self.session.flush()
        return record

    @staticmethod
    def complete(
        record: SyncRunRecord,
        *,
        fetched_count: int,
        inserted_count: int,
        updated_count: int,
    ) -> None:
        record.status = "completed"
        record.completed_at = datetime.now(timezone.utc)
        record.fetched_count = fetched_count
        record.inserted_count = inserted_count
        record.updated_count = updated_count

    @staticmethod
    def fail(record: SyncRunRecord, error: Exception) -> None:
        record.status = "failed"
        record.completed_at = datetime.now(timezone.utc)
        record.error_message = str(error)[:2000]


class ChatRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, target_activity_id: str, title: str, lookback_days: int) -> ChatConversationRecord:
        now = datetime.now(timezone.utc)
        record = ChatConversationRecord(
            id=str(uuid.uuid4()),
            target_activity_id=target_activity_id,
            title=title[:80],
            lookback_days=lookback_days,
            created_at=now,
            updated_at=now,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_record(self, conversation_id: str) -> ChatConversationRecord | None:
        return self.session.get(ChatConversationRecord, conversation_id)

    def list(self, limit: int = 20) -> list[ChatConversation]:
        records = self.session.scalars(
            select(ChatConversationRecord)
            .order_by(desc(ChatConversationRecord.updated_at))
            .limit(limit)
        ).all()
        return [self._to_domain(record, include_messages=False) for record in records]

    def get(self, conversation_id: str) -> ChatConversation | None:
        record = self.get_record(conversation_id)
        return self._to_domain(record) if record is not None else None

    def messages(self, conversation_id: str, *, limit: int = 50) -> list[ChatMessage]:
        records = self.session.scalars(
            select(ChatMessageRecord)
            .where(ChatMessageRecord.conversation_id == conversation_id)
            .order_by(ChatMessageRecord.id.desc())
            .limit(limit)
        ).all()
        return [self._message_to_domain(item) for item in reversed(records)]

    def add_user_message(self, conversation_id: str, content: str) -> ChatMessageRecord:
        return self._add_message(conversation_id=conversation_id, role="user", content=content)

    def add_assistant_message(
        self,
        conversation_id: str,
        answer: ChatAnswer,
        *,
        usage: ChatTurnUsage,
        trace_id: str | None,
    ) -> ChatMessageRecord:
        return self._add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=answer.answer,
            model=usage.model,
            evidence_refs=answer.evidence_refs,
            confidence=answer.confidence,
            missing_data=answer.missing_data,
            trace_id=trace_id,
            usage=usage,
            answer=answer,
        )

    def _add_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        model: str | None = None,
        evidence_refs: list[str] | None = None,
        confidence: str | None = None,
        missing_data: list[str] | None = None,
        trace_id: str | None = None,
        usage: ChatTurnUsage | None = None,
        answer: ChatAnswer | None = None,
    ) -> ChatMessageRecord:
        record = ChatMessageRecord(
            conversation_id=conversation_id,
            role=role,
            content=content,
            model=model,
            evidence_refs_json=json.dumps(evidence_refs or [], ensure_ascii=False),
            confidence=confidence,
            missing_data_json=json.dumps(missing_data or [], ensure_ascii=False),
            trace_id=trace_id,
            usage_json=(
                json.dumps(
                    {
                        "usage": usage.model_dump(mode="json"),
                        "answer": answer.model_dump(mode="json") if answer else None,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                if usage is not None
                else None
            ),
        )
        self.session.add(record)
        conversation = self.get_record(conversation_id)
        if conversation is not None:
            conversation.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return record

    def _to_domain(
        self,
        record: ChatConversationRecord,
        *,
        include_messages: bool = True,
    ) -> ChatConversation:
        messages = self.messages(record.id) if include_messages else []
        message_count = (
            len(messages)
            if include_messages
            else int(
                self.session.scalar(
                    select(func.count())
                    .select_from(ChatMessageRecord)
                    .where(ChatMessageRecord.conversation_id == record.id)
                )
                or 0
            )
        )
        return ChatConversation(
            id=record.id,
            target_activity_id=record.target_activity_id,
            title=record.title,
            created_at=record.created_at,
            updated_at=record.updated_at,
            review_input_hash=record.review_input_hash,
            message_count=message_count,
            messages=messages,
        )

    @staticmethod
    def _message_to_domain(record: ChatMessageRecord) -> ChatMessage:
        answer_metadata: dict[str, Any] = {}
        if record.usage_json:
            parsed_metadata = json.loads(record.usage_json)
            if isinstance(parsed_metadata, dict) and isinstance(
                parsed_metadata.get("answer"), dict
            ):
                answer_metadata = parsed_metadata["answer"]
        return ChatMessage(
            id=record.id,
            role=record.role,
            content=record.content,
            created_at=record.created_at,
            model=record.model,
            evidence_refs=json.loads(record.evidence_refs_json),
            confidence=record.confidence,
            missing_data=json.loads(record.missing_data_json),
            trace_id=record.trace_id,
            response_mode=answer_metadata.get("response_mode"),
            grounded_claims=answer_metadata.get("grounded_claims", []),
            follow_up_suggestions=answer_metadata.get(
                "follow_up_suggestions", []
            ),
        )
