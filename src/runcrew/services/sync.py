from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from runcrew.providers.base import ActivityProvider
from runcrew.storage.repositories import (
    ActivityRepository,
    RawEventRepository,
    SyncRunRepository,
)


@dataclass(frozen=True, slots=True)
class SyncResult:
    fetched_count: int
    inserted_count: int
    updated_count: int
    detailed_count: int
    detail_error_count: int


async def sync_activities(
    *,
    session: Session,
    provider: ActivityProvider,
    days: int,
    detail_limit: int = 1,
    today: date | None = None,
) -> SyncResult:
    if days < 1:
        raise ValueError("days must be at least 1")
    if detail_limit < 0:
        raise ValueError("detail_limit cannot be negative")

    today = today or date.today()
    start_date = today - timedelta(days=days - 1)
    activities = ActivityRepository(session)
    raw_events = RawEventRepository(session)
    sync_runs = SyncRunRepository(session)
    run = sync_runs.start(provider.name)
    session.commit()

    inserted_count = 0
    updated_count = 0
    detailed_count = 0
    detail_errors: list[str] = []
    try:
        envelopes = await provider.list_activities(start_date, today)
        for envelope in envelopes:
            activity = envelope.activity
            raw_events.add(
                provider=provider.name,
                operation="list_activities",
                external_id=activity.source_ref.external_id,
                raw_payload=envelope.raw_payload,
                fetched_at=activity.source_ref.fetched_at,
            )
            if activities.upsert(activity):
                inserted_count += 1
            else:
                updated_count += 1

        # List data is independently useful. Commit it before optional detail
        # hydration so a provider-side detail failure cannot discard the batch.
        session.commit()

        for envelope in envelopes[:detail_limit]:
            try:
                detail_envelope = await provider.get_activity(
                    envelope.activity.source_ref.external_id
                )
                detail = detail_envelope.activity
                raw_events.add(
                    provider=provider.name,
                    operation="get_activity",
                    external_id=detail.source_ref.external_id,
                    raw_payload=detail_envelope.raw_payload,
                    fetched_at=detail.source_ref.fetched_at,
                )
                activities.upsert(detail)
                detailed_count += 1
            except Exception as error:
                detail_errors.append(
                    f"{envelope.activity.source_ref.external_id}: {error}"
                )

        run = session.get(type(run), run.id)
        assert run is not None
        sync_runs.complete(
            run,
            fetched_count=len(envelopes),
            inserted_count=inserted_count,
            updated_count=updated_count,
        )
        if detail_errors:
            run.status = "completed_with_warnings"
            run.error_message = " | ".join(detail_errors)[:2000]
        session.commit()
    except Exception as error:
        session.rollback()
        run = session.get(type(run), run.id)
        if run is not None:
            sync_runs.fail(run, error)
            session.commit()
        raise

    return SyncResult(
        fetched_count=len(envelopes),
        inserted_count=inserted_count,
        updated_count=updated_count,
        detailed_count=detailed_count,
        detail_error_count=len(detail_errors),
    )
