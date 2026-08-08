import asyncio
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from runcrew.providers.fixture import FixtureActivityProvider
from runcrew.services.sync import sync_activities
from runcrew.storage.database import Database
from runcrew.storage.models import ActivityRecord, RawProviderEvent


def test_sync_is_idempotent(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    database.create_schema()
    provider = FixtureActivityProvider(Path("tests/fixtures/coros_activities.json"))

    with database.session() as session:
        first = asyncio.run(
            sync_activities(
                session=session,
                provider=provider,
                days=30,
                detail_limit=1,
                today=date(2026, 8, 8),
            )
        )
        second = asyncio.run(
            sync_activities(
                session=session,
                provider=provider,
                days=30,
                detail_limit=1,
                today=date(2026, 8, 8),
            )
        )

        activity_count = session.scalar(select(func.count()).select_from(ActivityRecord))
        raw_count = session.scalar(select(func.count()).select_from(RawProviderEvent))

    assert first.inserted_count == 2
    assert second.inserted_count == 0
    assert second.updated_count == 2
    assert activity_count == 2
    assert raw_count == 6
    assert first.detail_error_count == 0
