from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ActivityRecord(Base):
    __tablename__ = "activities"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_activity_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sport_type: Mapped[str] = mapped_column(String(32), nullable=False)
    activity_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical_json: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class RawProviderEvent(Base):
    __tablename__ = "raw_provider_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255))
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SyncRunRecord(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)


class ChatConversationRecord(Base):
    __tablename__ = "chat_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    target_activity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("activities.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False, default=28)
    review_snapshot_json: Mapped[str | None] = mapped_column(Text)
    review_trace_json: Mapped[str | None] = mapped_column(Text)
    review_input_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ChatMessageRecord(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_conversations.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String(64))
    evidence_refs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    confidence: Mapped[str | None] = mapped_column(String(16))
    missing_data_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    trace_id: Mapped[str | None] = mapped_column(String(64), index=True)
    usage_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class MemoryCandidateRecord(Base):
    __tablename__ = "memory_candidates"
    __table_args__ = (
        UniqueConstraint(
            "source_message_id", "key", name="uq_memory_candidate_message_key"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_conversations.id"), nullable=False, index=True
    )
    source_message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_messages.id"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    candidate_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    canonical_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TrainingGoalRecord(Base):
    __tablename__ = "training_goals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    target_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    canonical_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TrainingPlanRecord(Base):
    __tablename__ = "training_plans"
    __table_args__ = (
        UniqueConstraint("goal_id", "week_start", name="uq_training_plan_goal_week"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    goal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_goals.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    canonical_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DailyCheckInRecord(Base):
    __tablename__ = "daily_check_ins"
    __table_args__ = (UniqueConstraint("day", name="uq_daily_check_in_day"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    canonical_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PlanChangeProposalRecord(Base):
    __tablename__ = "plan_change_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_plans.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    canonical_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserConfirmationRecord(Base):
    __tablename__ = "user_confirmations"
    __table_args__ = (
        UniqueConstraint("proposal_id", name="uq_user_confirmation_proposal"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("plan_change_proposals.id"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AthletePreferenceRecord(Base):
    __tablename__ = "athlete_preferences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    supersedes_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("athlete_preferences.id"), index=True
    )
    canonical_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WeeklyTrainingMemoryRecord(Base):
    __tablename__ = "weekly_training_memories"
    __table_args__ = (
        UniqueConstraint(
            "goal_id", "week_start", "version", name="uq_weekly_memory_goal_week_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    goal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_goals.id"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_plans.id"), nullable=False, index=True
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    supersedes_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("weekly_training_memories.id"), index=True
    )
    canonical_json: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TrainingExecutionConfirmationRecord(Base):
    __tablename__ = "training_execution_confirmations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_plans.id"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_revision: Mapped[int | None] = mapped_column(Integer)
    canonical_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CoachRunRecord(Base):
    __tablename__ = "coach_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    goal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_goals.id"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_plans.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    workflow_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    planning_output_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    proposal_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("plan_change_proposals.id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentRuntimeRunRecord(Base):
    __tablename__ = "agent_runtime_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    workflow_version: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    termination_reason: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    span_count: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    trace_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scope_ref_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    canonical_json: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class AgentRuntimeSpanRecord(Base):
    __tablename__ = "agent_runtime_spans"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_runtime_span_run_sequence"),
    )

    id: Mapped[str] = mapped_column(String(140), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("agent_runtime_runs.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(String(140), index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    tool_name: Mapped[str | None] = mapped_column(String(80), index=True)
    node: Mapped[str | None] = mapped_column(String(64), index=True)
    start_offset_ms: Mapped[float] = mapped_column(Float, nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    canonical_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
