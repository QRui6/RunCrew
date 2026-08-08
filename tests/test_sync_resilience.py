import asyncio
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from runcrew.providers.fixture import FixtureActivityProvider
from runcrew.services.sync import sync_activities
from runcrew.storage.database import Database
from runcrew.storage.models import ActivityRecord, SyncRunRecord


class DetailFailingProvider(FixtureActivityProvider):
    async def get_activity(self, external_id: str):
        raise RuntimeError("provider detail endpoint unavailable")


def test_detail_failure_does_not_discard_activity_list(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    database.create_schema()
    provider = DetailFailingProvider(Path("tests/fixtures/coros_activities.json"))

    with database.session() as session:
        result = asyncio.run(
            sync_activities(
                session=session,
                provider=provider,
                days=30,
                detail_limit=1,
                today=date(2026, 8, 8),
            )
        )
        activity_count = session.scalar(select(func.count()).select_from(ActivityRecord))
        sync_run = session.scalar(
            select(SyncRunRecord).order_by(SyncRunRecord.id.desc()).limit(1)
        )

    assert activity_count == 2
    assert result.detail_error_count == 1
    assert sync_run is not None
    assert sync_run.status == "completed_with_warnings"

