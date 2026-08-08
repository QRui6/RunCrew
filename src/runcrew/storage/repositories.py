from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from runcrew.domain.activity import ActivityDetail, ActivitySummary
from runcrew.storage.models import ActivityRecord, RawProviderEvent, SyncRunRecord


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
