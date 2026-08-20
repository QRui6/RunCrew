from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from typing import Any, Mapping

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from runcrew.domain.activity import ActivityDetail, ActivitySummary
from runcrew.domain.chat import ChatAnswer, ChatConversation, ChatMessage, ChatTurnUsage
from runcrew.domain.memory import (
    AthletePreference,
    MemoryCandidate,
    PreferenceKey,
    WeeklyTrainingMemory,
)
from runcrew.domain.training_cycle import (
    DailyCheckIn,
    PlanChangeProposal,
    TrainingGoal,
    TrainingPlan,
    UserConfirmation,
)
from runcrew.domain.training_execution import TrainingExecutionConfirmation
from runcrew.domain.training_operations import CoachRunAudit, CoachRunSummary
from runcrew.domain.runtime_observability import RuntimeRun, RuntimeRunCapture, RuntimeSpan
from runcrew.storage.models import (
    ActivityRecord,
    AgentRuntimeRunRecord,
    AgentRuntimeSpanRecord,
    AthletePreferenceRecord,
    CoachRunRecord,
    ChatConversationRecord,
    ChatMessageRecord,
    DailyCheckInRecord,
    PlanChangeProposalRecord,
    MemoryCandidateRecord,
    RawProviderEvent,
    SyncRunRecord,
    TrainingGoalRecord,
    TrainingExecutionConfirmationRecord,
    TrainingPlanRecord,
    UserConfirmationRecord,
    WeeklyTrainingMemoryRecord,
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

    def get_message_record(self, message_id: int) -> ChatMessageRecord | None:
        return self.session.get(ChatMessageRecord, message_id)

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
            memory_candidates=(
                self._memory_candidates(record.id) if include_messages else []
            ),
        )

    def _memory_candidates(self, conversation_id: str) -> list[MemoryCandidate]:
        records = self.session.scalars(
            select(MemoryCandidateRecord)
            .where(MemoryCandidateRecord.conversation_id == conversation_id)
            .order_by(MemoryCandidateRecord.created_at, MemoryCandidateRecord.id)
        ).all()
        return [
            MemoryCandidate.model_validate_json(record.canonical_json)
            for record in records
        ]

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


class TrainingGoalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, goal: TrainingGoal) -> None:
        record = self.session.get(TrainingGoalRecord, goal.id)
        if record is None:
            record = TrainingGoalRecord(
                id=goal.id,
                status=goal.status,
                target_date=goal.target_date,
                canonical_json=goal.model_dump_json(),
                created_at=goal.created_at,
                updated_at=goal.updated_at,
            )
            self.session.add(record)
        else:
            record.status = goal.status
            record.target_date = goal.target_date
            record.canonical_json = goal.model_dump_json()
            record.updated_at = goal.updated_at
        self.session.flush()

    def get(self, goal_id: str) -> TrainingGoal | None:
        record = self.session.get(TrainingGoalRecord, goal_id)
        return TrainingGoal.model_validate_json(record.canonical_json) if record else None

    def list(self, *, limit: int = 20) -> list[TrainingGoal]:
        records = self.session.scalars(
            select(TrainingGoalRecord)
            .order_by(desc(TrainingGoalRecord.updated_at))
            .limit(limit)
        ).all()
        return [TrainingGoal.model_validate_json(record.canonical_json) for record in records]


class MemoryCandidateRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, candidate: MemoryCandidate) -> None:
        record = self.session.get(MemoryCandidateRecord, candidate.id)
        if record is None:
            record = MemoryCandidateRecord(id=candidate.id)
            self.session.add(record)
        record.conversation_id = candidate.conversation_id
        record.source_message_id = candidate.source_message_id
        record.key = candidate.key
        record.status = candidate.status
        record.candidate_hash = candidate.candidate_hash
        record.expires_at = candidate.expires_at
        record.canonical_json = candidate.model_dump_json()
        record.created_at = candidate.created_at
        record.decided_at = candidate.decided_at
        self.session.flush()

    def get(self, candidate_id: str) -> MemoryCandidate | None:
        record = self.session.get(MemoryCandidateRecord, candidate_id)
        return (
            MemoryCandidate.model_validate_json(record.canonical_json)
            if record is not None
            else None
        )

    def for_source_message(
        self, source_message_id: int, key: PreferenceKey
    ) -> MemoryCandidate | None:
        record = self.session.scalar(
            select(MemoryCandidateRecord)
            .where(
                MemoryCandidateRecord.source_message_id == source_message_id,
                MemoryCandidateRecord.key == key,
            )
            .limit(1)
        )
        return (
            MemoryCandidate.model_validate_json(record.canonical_json)
            if record is not None
            else None
        )

    def pending_for_key(self, key: PreferenceKey) -> list[MemoryCandidate]:
        records = self.session.scalars(
            select(MemoryCandidateRecord)
            .where(
                MemoryCandidateRecord.key == key,
                MemoryCandidateRecord.status == "pending",
            )
            .order_by(desc(MemoryCandidateRecord.created_at))
        ).all()
        return [
            MemoryCandidate.model_validate_json(record.canonical_json)
            for record in records
        ]

    def list(
        self,
        *,
        conversation_id: str | None = None,
        include_resolved: bool = True,
        limit: int = 50,
    ) -> list[MemoryCandidate]:
        statement = select(MemoryCandidateRecord)
        if conversation_id is not None:
            statement = statement.where(
                MemoryCandidateRecord.conversation_id == conversation_id
            )
        if not include_resolved:
            statement = statement.where(MemoryCandidateRecord.status == "pending")
        records = self.session.scalars(
            statement.order_by(desc(MemoryCandidateRecord.created_at)).limit(limit)
        ).all()
        return [
            MemoryCandidate.model_validate_json(record.canonical_json)
            for record in records
        ]


class AthletePreferenceRepository:
    """单用户本地偏好仓库；同一 key 只允许一个可用的当前版本。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, preference: AthletePreference) -> None:
        record = self.session.get(AthletePreferenceRecord, preference.id)
        if record is None:
            record = AthletePreferenceRecord(id=preference.id)
            self.session.add(record)
        record.key = preference.key
        record.status = preference.status
        record.valid_from = preference.valid_from
        record.valid_until = preference.valid_until
        record.supersedes_id = preference.supersedes_id
        record.canonical_json = preference.model_dump_json()
        record.created_at = preference.created_at
        record.updated_at = preference.updated_at
        self.session.flush()

    def get(self, preference_id: str) -> AthletePreference | None:
        record = self.session.get(AthletePreferenceRecord, preference_id)
        return (
            AthletePreference.model_validate_json(record.canonical_json)
            if record
            else None
        )

    def current_for_key(self, key: PreferenceKey) -> AthletePreference | None:
        record = self.session.scalar(
            select(AthletePreferenceRecord)
            .where(
                AthletePreferenceRecord.key == key,
                AthletePreferenceRecord.status == "active",
            )
            .order_by(desc(AthletePreferenceRecord.updated_at))
            .limit(1)
        )
        return (
            AthletePreference.model_validate_json(record.canonical_json)
            if record
            else None
        )

    def active_at(self, at: datetime) -> list[AthletePreference]:
        records = self.session.scalars(
            select(AthletePreferenceRecord)
            .where(AthletePreferenceRecord.status == "active")
            .order_by(AthletePreferenceRecord.key, desc(AthletePreferenceRecord.updated_at))
        ).all()
        preferences = [
            AthletePreference.model_validate_json(record.canonical_json)
            for record in records
        ]
        return [item for item in preferences if item.is_effective_at(at)]

    def list(self, *, limit: int = 50) -> list[AthletePreference]:
        records = self.session.scalars(
            select(AthletePreferenceRecord)
            .order_by(desc(AthletePreferenceRecord.updated_at))
            .limit(limit)
        ).all()
        return [
            AthletePreference.model_validate_json(record.canonical_json)
            for record in records
        ]


class WeeklyTrainingMemoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, memory: WeeklyTrainingMemory) -> None:
        record = self.session.get(WeeklyTrainingMemoryRecord, memory.id)
        if record is None:
            record = WeeklyTrainingMemoryRecord(id=memory.id)
            self.session.add(record)
        record.goal_id = memory.goal_id
        record.plan_id = memory.plan_id
        record.week_start = memory.week_start
        record.version = memory.version
        record.status = memory.status
        record.input_hash = memory.input_hash
        record.supersedes_id = memory.supersedes_id
        record.canonical_json = memory.model_dump_json()
        record.generated_at = memory.generated_at
        record.updated_at = memory.updated_at
        self.session.flush()

    def get(self, memory_id: str) -> WeeklyTrainingMemory | None:
        record = self.session.get(WeeklyTrainingMemoryRecord, memory_id)
        return (
            WeeklyTrainingMemory.model_validate_json(record.canonical_json)
            if record
            else None
        )

    def current_for_week(
        self, goal_id: str, week_start: date
    ) -> WeeklyTrainingMemory | None:
        record = self.session.scalar(
            select(WeeklyTrainingMemoryRecord)
            .where(
                WeeklyTrainingMemoryRecord.goal_id == goal_id,
                WeeklyTrainingMemoryRecord.week_start == week_start,
                WeeklyTrainingMemoryRecord.status == "active",
            )
            .order_by(desc(WeeklyTrainingMemoryRecord.version))
            .limit(1)
        )
        return (
            WeeklyTrainingMemory.model_validate_json(record.canonical_json)
            if record
            else None
        )

    def latest_for_week(
        self, goal_id: str, week_start: date
    ) -> WeeklyTrainingMemory | None:
        record = self.session.scalar(
            select(WeeklyTrainingMemoryRecord)
            .where(
                WeeklyTrainingMemoryRecord.goal_id == goal_id,
                WeeklyTrainingMemoryRecord.week_start == week_start,
            )
            .order_by(desc(WeeklyTrainingMemoryRecord.version))
            .limit(1)
        )
        return (
            WeeklyTrainingMemory.model_validate_json(record.canonical_json)
            if record
            else None
        )

    def recent_before(
        self, goal_id: str, before: date, *, limit: int = 4
    ) -> list[WeeklyTrainingMemory]:
        records = self.session.scalars(
            select(WeeklyTrainingMemoryRecord)
            .where(
                WeeklyTrainingMemoryRecord.goal_id == goal_id,
                WeeklyTrainingMemoryRecord.week_start < before,
                WeeklyTrainingMemoryRecord.status == "active",
            )
            .order_by(
                desc(WeeklyTrainingMemoryRecord.week_start),
                desc(WeeklyTrainingMemoryRecord.version),
            )
            .limit(limit)
        ).all()
        return [
            WeeklyTrainingMemory.model_validate_json(record.canonical_json)
            for record in records
        ]

    def list_for_goal(
        self, goal_id: str, *, include_inactive: bool = False, limit: int = 20
    ) -> list[WeeklyTrainingMemory]:
        statement = select(WeeklyTrainingMemoryRecord).where(
            WeeklyTrainingMemoryRecord.goal_id == goal_id
        )
        if not include_inactive:
            statement = statement.where(WeeklyTrainingMemoryRecord.status == "active")
        records = self.session.scalars(
            statement.order_by(
                desc(WeeklyTrainingMemoryRecord.week_start),
                desc(WeeklyTrainingMemoryRecord.version),
            ).limit(limit)
        ).all()
        return [
            WeeklyTrainingMemory.model_validate_json(record.canonical_json)
            for record in records
        ]


class TrainingPlanRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, plan: TrainingPlan) -> None:
        record = self.session.get(TrainingPlanRecord, plan.id)
        if record is None:
            record = TrainingPlanRecord(
                id=plan.id,
                goal_id=plan.goal_id,
                status=plan.status,
                week_start=plan.week_start,
                revision=plan.revision,
                canonical_json=plan.model_dump_json(),
                created_at=plan.created_at,
                updated_at=plan.updated_at,
            )
            self.session.add(record)
        else:
            record.status = plan.status
            record.week_start = plan.week_start
            record.revision = plan.revision
            record.canonical_json = plan.model_dump_json()
            record.updated_at = plan.updated_at
        self.session.flush()

    def get(self, plan_id: str) -> TrainingPlan | None:
        record = self.session.get(TrainingPlanRecord, plan_id)
        return TrainingPlan.model_validate_json(record.canonical_json) if record else None

    def for_goal_week(self, goal_id: str, week_start: date) -> TrainingPlan | None:
        record = self.session.scalar(
            select(TrainingPlanRecord).where(
                TrainingPlanRecord.goal_id == goal_id,
                TrainingPlanRecord.week_start == week_start,
            )
        )
        return TrainingPlan.model_validate_json(record.canonical_json) if record else None

    def active_for_goal(self, goal_id: str) -> TrainingPlan | None:
        record = self.session.scalar(
            select(TrainingPlanRecord)
            .where(
                TrainingPlanRecord.goal_id == goal_id,
                TrainingPlanRecord.status == "active",
            )
            .order_by(desc(TrainingPlanRecord.updated_at))
            .limit(1)
        )
        return TrainingPlan.model_validate_json(record.canonical_json) if record else None

    def active_from_week(
        self, goal_id: str, week_start: date, *, limit: int = 2
    ) -> list[TrainingPlan]:
        records = self.session.scalars(
            select(TrainingPlanRecord)
            .where(
                TrainingPlanRecord.goal_id == goal_id,
                TrainingPlanRecord.status == "active",
                TrainingPlanRecord.week_start >= week_start,
            )
            .order_by(TrainingPlanRecord.week_start, TrainingPlanRecord.id)
            .limit(limit)
        ).all()
        return [TrainingPlan.model_validate_json(record.canonical_json) for record in records]


class CheckInRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, check_in: DailyCheckIn) -> None:
        record = self.session.scalar(
            select(DailyCheckInRecord).where(DailyCheckInRecord.day == check_in.day)
        )
        if record is None:
            record = DailyCheckInRecord(
                id=check_in.id,
                day=check_in.day,
                canonical_json=check_in.model_dump_json(),
                created_at=check_in.created_at,
            )
            self.session.add(record)
        else:
            check_in.id = record.id
            record.canonical_json = check_in.model_dump_json()
        self.session.flush()

    def recent(self, *, limit: int = 7) -> list[DailyCheckIn]:
        records = self.session.scalars(
            select(DailyCheckInRecord)
            .order_by(desc(DailyCheckInRecord.day))
            .limit(limit)
        ).all()
        return [DailyCheckIn.model_validate_json(record.canonical_json) for record in records]

    def between(self, start: date, end: date) -> list[DailyCheckIn]:
        records = self.session.scalars(
            select(DailyCheckInRecord)
            .where(
                DailyCheckInRecord.day >= start,
                DailyCheckInRecord.day <= end,
            )
            .order_by(DailyCheckInRecord.day, DailyCheckInRecord.id)
        ).all()
        return [DailyCheckIn.model_validate_json(record.canonical_json) for record in records]


class PlanChangeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save_proposal(self, proposal: PlanChangeProposal) -> None:
        record = self.session.get(PlanChangeProposalRecord, proposal.id)
        if record is None:
            record = PlanChangeProposalRecord(
                id=proposal.id,
                plan_id=proposal.plan_id,
                status=proposal.status,
                base_revision=proposal.base_revision,
                canonical_json=proposal.model_dump_json(),
                created_at=proposal.created_at,
            )
            self.session.add(record)
        else:
            record.status = proposal.status
            record.canonical_json = proposal.model_dump_json()
        self.session.flush()

    def get_proposal(self, proposal_id: str) -> PlanChangeProposal | None:
        record = self.session.get(PlanChangeProposalRecord, proposal_id)
        return (
            PlanChangeProposal.model_validate_json(record.canonical_json)
            if record
            else None
        )

    def save_confirmation(self, confirmation: UserConfirmation) -> None:
        self.session.add(
            UserConfirmationRecord(
                id=confirmation.id,
                proposal_id=confirmation.proposal_id,
                decision=confirmation.decision,
                canonical_json=confirmation.model_dump_json(),
                created_at=confirmation.created_at,
            )
        )
        self.session.flush()

    def pending_for_goal(self, goal_id: str) -> list[PlanChangeProposal]:
        records = self.session.scalars(
            select(PlanChangeProposalRecord)
            .join(
                TrainingPlanRecord,
                TrainingPlanRecord.id == PlanChangeProposalRecord.plan_id,
            )
            .where(
                TrainingPlanRecord.goal_id == goal_id,
                PlanChangeProposalRecord.status == "pending",
            )
            .order_by(PlanChangeProposalRecord.created_at)
        ).all()
        return [
            PlanChangeProposal.model_validate_json(record.canonical_json)
            for record in records
        ]

    def for_plan(self, plan_id: str) -> list[PlanChangeProposal]:
        records = self.session.scalars(
            select(PlanChangeProposalRecord)
            .where(PlanChangeProposalRecord.plan_id == plan_id)
            .order_by(
                PlanChangeProposalRecord.created_at,
                PlanChangeProposalRecord.id,
            )
        ).all()
        return [
            PlanChangeProposal.model_validate_json(record.canonical_json)
            for record in records
        ]


class TrainingExecutionConfirmationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, confirmation: TrainingExecutionConfirmation) -> None:
        self.session.add(
            TrainingExecutionConfirmationRecord(
                id=confirmation.id,
                plan_id=confirmation.plan_id,
                session_id=confirmation.session_id,
                decision=confirmation.decision,
                status=confirmation.status,
                base_revision=confirmation.base_revision,
                applied_revision=confirmation.applied_revision,
                canonical_json=confirmation.model_dump_json(),
                created_at=confirmation.created_at,
            )
        )
        self.session.flush()

    def for_plan(self, plan_id: str) -> list[TrainingExecutionConfirmation]:
        records = self.session.scalars(
            select(TrainingExecutionConfirmationRecord)
            .where(TrainingExecutionConfirmationRecord.plan_id == plan_id)
            .order_by(
                TrainingExecutionConfirmationRecord.created_at,
                TrainingExecutionConfirmationRecord.id,
            )
        ).all()
        return [
            TrainingExecutionConfirmation.model_validate_json(record.canonical_json)
            for record in records
        ]


class CoachRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, audit: CoachRunAudit) -> None:
        record = self.session.get(CoachRunRecord, audit.run_id)
        if record is None:
            record = CoachRunRecord(
                id=audit.run_id,
                goal_id=audit.goal_id,
                plan_id=audit.plan_id,
                status=audit.status,
                workflow_hash=audit.result.workflow_hash,
                planning_output_hash=audit.planning_output_hash,
                request_json=audit.run_request.model_dump_json(),
                result_json=audit.result.model_dump_json(),
                proposal_id=audit.proposal_id,
                created_at=audit.created_at,
                decided_at=audit.decided_at,
            )
            self.session.add(record)
        else:
            record.status = audit.status
            record.planning_output_hash = audit.planning_output_hash
            record.proposal_id = audit.proposal_id
            record.decided_at = audit.decided_at
        self.session.flush()

    def get(self, run_id: str) -> CoachRunAudit | None:
        record = self.session.get(CoachRunRecord, run_id)
        return self._to_domain(record) if record else None

    def recent(self, *, limit: int = 10) -> list[CoachRunSummary]:
        records = self.session.scalars(
            select(CoachRunRecord)
            .order_by(desc(CoachRunRecord.created_at))
            .limit(limit)
        ).all()
        return [
            CoachRunSummary(
                run_id=record.id,
                goal_id=record.goal_id,
                plan_id=record.plan_id,
                status=record.status,
                recommendation=(
                    audit.result.recovery.recommendation
                    if audit.result.recovery is not None
                    else None
                ),
                required_user_action=audit.result.required_user_action,
                proposal_id=record.proposal_id,
                created_at=record.created_at,
                decided_at=record.decided_at,
            )
            for record in records
            for audit in [self._to_domain(record)]
        ]

    @staticmethod
    def _to_domain(record: CoachRunRecord) -> CoachRunAudit:
        from runcrew.domain.coach import CoachAgentRunRequest, CoachAgentRunResult

        return CoachRunAudit(
            run_id=record.id,
            goal_id=record.goal_id,
            plan_id=record.plan_id,
            status=record.status,
            run_request=CoachAgentRunRequest.model_validate_json(record.request_json),
            result=CoachAgentRunResult.model_validate_json(record.result_json),
            planning_output_hash=record.planning_output_hash,
            proposal_id=record.proposal_id,
            created_at=record.created_at,
            decided_at=record.decided_at,
        )


class RuntimeRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, capture: RuntimeRunCapture) -> bool:
        existing = self.session.get(AgentRuntimeRunRecord, capture.run.run_id)
        if existing is not None:
            if existing.trace_hash != capture.run.trace_hash:
                raise ValueError("相同 Runtime run_id 的 Trace Hash 不一致")
            return False
        run = capture.run
        self.session.add(
            AgentRuntimeRunRecord(
                id=run.run_id,
                workflow=run.workflow,
                workflow_version=run.workflow_version,
                status=run.status,
                termination_reason=run.termination_reason,
                duration_ms=run.duration_ms,
                span_count=run.span_count,
                tool_call_count=run.tool_call_count,
                retry_count=run.retry_count,
                trace_hash=run.trace_hash,
                scope_ref_hash=run.scope_ref_hash,
                canonical_json=run.model_dump_json(),
                recorded_at=run.recorded_at,
                expires_at=run.expires_at,
            )
        )
        for span in capture.spans:
            self.session.add(
                AgentRuntimeSpanRecord(
                    id=span.span_id,
                    run_id=span.run_id,
                    sequence=span.sequence,
                    parent_span_id=span.parent_span_id,
                    kind=span.kind,
                    status=span.status,
                    tool_name=span.tool_name,
                    node=span.node,
                    start_offset_ms=span.start_offset_ms,
                    duration_ms=span.duration_ms,
                    canonical_json=span.model_dump_json(),
                )
            )
        self.session.flush()
        return True

    def get(self, run_id: str, *, now: datetime | None = None) -> RuntimeRunCapture | None:
        record = self.session.get(AgentRuntimeRunRecord, run_id)
        if record is None:
            return None
        run = RuntimeRun.model_validate_json(record.canonical_json)
        if now is not None and run.expires_at <= now:
            return None
        spans = self.session.scalars(
            select(AgentRuntimeSpanRecord)
            .where(AgentRuntimeSpanRecord.run_id == run_id)
            .order_by(AgentRuntimeSpanRecord.sequence)
        ).all()
        return RuntimeRunCapture(
            run=run,
            spans=[
                RuntimeSpan.model_validate_json(item.canonical_json) for item in spans
            ],
        )

    def recent(
        self,
        *,
        limit: int = 20,
        workflow: str | None = None,
        now: datetime | None = None,
    ) -> list[RuntimeRun]:
        statement = select(AgentRuntimeRunRecord)
        if workflow is not None:
            statement = statement.where(AgentRuntimeRunRecord.workflow == workflow)
        if now is not None:
            statement = statement.where(AgentRuntimeRunRecord.expires_at > now)
        records = self.session.scalars(
            statement.order_by(desc(AgentRuntimeRunRecord.recorded_at)).limit(limit)
        ).all()
        return [RuntimeRun.model_validate_json(item.canonical_json) for item in records]

    def delete_expired(self, *, now: datetime) -> int:
        run_ids = self.session.scalars(
            select(AgentRuntimeRunRecord.id).where(
                AgentRuntimeRunRecord.expires_at <= now
            )
        ).all()
        if not run_ids:
            return 0
        self.session.execute(
            delete(AgentRuntimeSpanRecord).where(
                AgentRuntimeSpanRecord.run_id.in_(run_ids)
            )
        )
        self.session.execute(
            delete(AgentRuntimeRunRecord).where(AgentRuntimeRunRecord.id.in_(run_ids))
        )
        self.session.flush()
        return len(run_ids)
