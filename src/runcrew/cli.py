from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import func, select

from runcrew.providers.fixture import FixtureActivityProvider
from runcrew.providers.coros import CorosActivityProvider
from runcrew.services.activity_review import build_activity_review
from runcrew.services.sync import sync_activities
from runcrew.storage.database import Database
from runcrew.storage.models import ActivityRecord, RawProviderEvent, SyncRunRecord
from runcrew.storage.repositories import ActivityRepository


app = typer.Typer(
    name="runcrew",
    help="RunCrew running data and agent engineering CLI.",
    no_args_is_help=True,
)
activities_app = typer.Typer(help="Inspect and review normalized activities.")
app.add_typer(activities_app, name="activities")


def database_url(database_path: Path) -> str:
    return f"sqlite:///{database_path.resolve().as_posix()}"


def open_database(database_path: Path) -> Database:
    database = Database(database_url(database_path))
    database.create_schema()
    return database


@app.command("init-db")
def init_db(
    database_path: Annotated[
        Path, typer.Option("--db", help="SQLite database path.")
    ] = Path("data/runcrew.db"),
) -> None:
    open_database(database_path)
    typer.echo(f"Initialized database: {database_path.resolve()}")


@app.command("status")
def status_command(
    database_path: Annotated[
        Path, typer.Option("--db", help="SQLite database path.")
    ] = Path("data/runcrew.db"),
) -> None:
    database = open_database(database_path)
    with database.session() as session:
        provider_counts = session.execute(
            select(ActivityRecord.provider, func.count())
            .group_by(ActivityRecord.provider)
            .order_by(ActivityRecord.provider)
        ).all()
        raw_event_count = session.scalar(
            select(func.count()).select_from(RawProviderEvent)
        )
        latest_sync = session.scalar(
            select(SyncRunRecord).order_by(SyncRunRecord.id.desc()).limit(1)
        )
    typer.echo("Activities: " + (", ".join(f"{p}={c}" for p, c in provider_counts) or "0"))
    typer.echo(f"Raw provider events: {raw_event_count or 0}")
    if latest_sync:
        typer.echo(
            "Latest sync: "
            f"provider={latest_sync.provider}, status={latest_sync.status}, "
            f"fetched={latest_sync.fetched_count}, inserted={latest_sync.inserted_count}, "
            f"updated={latest_sync.updated_count}"
        )
    else:
        typer.echo("Latest sync: none")


@app.command("sync")
def sync_command(
    provider_name: Annotated[
        str, typer.Option("--provider", help="Activity provider name.")
    ] = "fixture",
    days: Annotated[int, typer.Option(min=1, help="Number of days to sync.")] = 30,
    detail_limit: Annotated[
        int, typer.Option(min=0, help="Number of activities to hydrate with details.")
    ] = 1,
    fixture_path: Annotated[
        Path, typer.Option("--fixture", help="Fixture JSON used by fixture provider.")
    ] = Path("tests/fixtures/coros_activities.json"),
    database_path: Annotated[
        Path, typer.Option("--db", help="SQLite database path.")
    ] = Path("data/runcrew.db"),
    callback_port: Annotated[
        int, typer.Option(help="Local OAuth callback port for COROS.")
    ] = 8765,
    open_browser: Annotated[
        bool,
        typer.Option(
            "--open-browser/--no-open-browser",
            help="Open the COROS authorization URL in the default browser.",
        ),
    ] = True,
    debug_payload_path: Annotated[
        Path | None,
        typer.Option(
            "--debug-payload",
            help="Private, git-ignored file for capturing a failed COROS payload.",
        ),
    ] = None,
) -> None:
    database = open_database(database_path)
    if provider_name == "fixture":
        provider = FixtureActivityProvider(fixture_path)

        async def execute_sync():
            with database.session() as session:
                return await sync_activities(
                    session=session,
                    provider=provider,
                    days=days,
                    detail_limit=detail_limit,
                )

    elif provider_name == "coros":
        coros_provider = CorosActivityProvider(
            callback_port=callback_port,
            open_browser=open_browser,
            authorization_url_handler=lambda url: typer.echo(
                f"Open this COROS authorization URL:\n{url}"
            ),
            debug_payload_path=debug_payload_path,
        )

        async def execute_sync():
            await coros_provider.connect()
            try:
                with database.session() as session:
                    return await sync_activities(
                        session=session,
                        provider=coros_provider,
                        days=days,
                        detail_limit=detail_limit,
                    )
            finally:
                await coros_provider.aclose()

    else:
        raise typer.BadParameter("Supported providers: fixture, coros")

    result = asyncio.run(execute_sync())
    typer.echo(
        "Sync completed: "
        f"fetched={result.fetched_count}, "
        f"inserted={result.inserted_count}, "
        f"updated={result.updated_count}, "
        f"detailed={result.detailed_count}, "
        f"detail_errors={result.detail_error_count}"
    )


@activities_app.command("list")
def list_activities(
    limit: Annotated[int, typer.Option(min=1, max=100)] = 20,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    database = open_database(database_path)
    with database.session() as session:
        activities = ActivityRepository(session).list(limit=limit)
    if not activities:
        typer.echo("No activities found. Run `runcrew sync --provider fixture` first.")
        return
    for activity in activities:
        distance = (
            f"{activity.distance_meters / 1000:.2f} km"
            if activity.distance_meters is not None
            else "distance unavailable"
        )
        typer.echo(
            f"{activity.started_at.isoformat()} | {activity.sport_type.value} | "
            f"{distance} | {activity.source_ref.external_id}"
        )


@activities_app.command("review")
def review_activity(
    latest: Annotated[
        bool, typer.Option("--latest", help="Review the latest stored activity.")
    ] = False,
    external_id: Annotated[
        str | None, typer.Option("--external-id", help="Provider activity ID.")
    ] = None,
    provider_name: Annotated[
        str | None, typer.Option("--provider", help="Filter by provider.")
    ] = None,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    if not latest and external_id is None:
        raise typer.BadParameter("Pass --latest or --external-id.")
    database = open_database(database_path)
    with database.session() as session:
        repository = ActivityRepository(session)
        activity = (
            repository.latest(provider=provider_name)
            if latest
            else repository.get_by_external_id(
                provider_name or "fixture", external_id or ""
            )
        )
    if activity is None:
        raise typer.BadParameter("Activity not found.")
    typer.echo(build_activity_review(activity).model_dump_json(indent=2))


if __name__ == "__main__":
    app()
