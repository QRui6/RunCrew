from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import func, select

from runcrew.providers.fixture import FixtureActivityProvider
from runcrew.providers.coros import CorosActivityProvider
from runcrew.domain.agent import ReviewAgentRunRequest
from runcrew.domain.training_review import PlannedSession, TrainingReviewRequest
from runcrew.evaluation import evaluate_review_agent_suite, load_review_agent_suite
from runcrew.harness import ReviewAgentHarness
from runcrew.policies import (
    DeepSeekCostBudget,
    DeepSeekPolicyConfig,
    DeepSeekPolicyError,
    DeepSeekReviewPolicy,
)
from runcrew.services.activity_review import build_activity_review
from runcrew.services.sync import sync_activities
from runcrew.services.training_review import execute_training_review
from runcrew.storage.database import Database
from runcrew.storage.models import ActivityRecord, RawProviderEvent, SyncRunRecord
from runcrew.storage.repositories import ActivityRepository
from runcrew.web import serve_demo


app = typer.Typer(
    name="runcrew",
    help="RunCrew running data and agent engineering CLI.",
    no_args_is_help=True,
)
activities_app = typer.Typer(help="Inspect and review normalized activities.")
training_app = typer.Typer(help="Run replayable training review skills.")
agent_app = typer.Typer(help="运行带 Trace、预算和退出条件的单 Agent。")
evaluation_app = typer.Typer(help="运行可回放的 Agent 离线评测。")
app.add_typer(activities_app, name="activities")
app.add_typer(training_app, name="training")
app.add_typer(agent_app, name="agent")
app.add_typer(evaluation_app, name="eval")


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


@app.command("demo")
def demo_command(
    port: Annotated[
        int,
        typer.Option(min=1024, max=65535, help="本地演示界面端口。"),
    ] = 8766,
    database_path: Annotated[
        Path,
        typer.Option("--db", help="只读展示使用的 SQLite 数据库路径。"),
    ] = Path("data/runcrew.db"),
    evaluation_directory: Annotated[
        Path,
        typer.Option("--eval-dir", help="私有评测报告目录。"),
    ] = Path("data/private/evals"),
    open_browser: Annotated[
        bool,
        typer.Option(
            "--open-browser/--no-open-browser",
            help="服务启动后是否尝试打开默认浏览器。",
        ),
    ] = True,
) -> None:
    """启动只绑定 127.0.0.1 的本地只读演示界面。"""
    serve_demo(
        port=port,
        database_path=database_path,
        evaluation_directory=evaluation_directory,
        open_browser=open_browser,
    )


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


@training_app.command("review")
def review_training(
    latest: Annotated[
        bool, typer.Option("--latest", help="Review the latest stored activity.")
    ] = False,
    external_id: Annotated[
        str | None, typer.Option("--external-id", help="Provider activity ID.")
    ] = None,
    provider_name: Annotated[
        str | None, typer.Option("--provider", help="Filter by provider.")
    ] = None,
    lookback_days: Annotated[
        int, typer.Option(min=14, max=90, help="History window for replay context.")
    ] = 28,
    planned_distance_km: Annotated[
        float | None,
        typer.Option(min=0.01, help="Optional planned distance in kilometers."),
    ] = None,
    planned_duration_minutes: Annotated[
        float | None,
        typer.Option(min=0.01, help="Optional planned duration in minutes."),
    ] = None,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    if not latest and external_id is None:
        raise typer.BadParameter("Pass --latest or --external-id.")
    database = open_database(database_path)
    with database.session() as session:
        repository = ActivityRepository(session)
        target = (
            repository.latest(provider=provider_name)
            if latest
            else repository.get_by_external_id(
                provider_name or "fixture", external_id or ""
            )
        )
        if target is None:
            raise typer.BadParameter("Activity not found.")

    plan = None
    if planned_distance_km is not None or planned_duration_minutes is not None:
        plan = PlannedSession(
            distance_meters=planned_distance_km * 1000
            if planned_distance_km is not None
            else None,
            duration_seconds=round(planned_duration_minutes * 60)
            if planned_duration_minutes is not None
            else None,
        )
    request = TrainingReviewRequest(
        target_activity_id=target.id,
        lookback_days=lookback_days,
        planned_session=plan,
    )
    with database.session() as session:
        result = execute_training_review(
            request,
            store=ActivityRepository(session),
        )
    typer.echo(result.model_dump_json(indent=2))


@agent_app.command("review")
def run_review_agent(
    latest: Annotated[
        bool, typer.Option("--latest", help="复盘最新一条活动。")
    ] = False,
    external_id: Annotated[
        str | None, typer.Option("--external-id", help="Provider 活动 ID。")
    ] = None,
    provider_name: Annotated[
        str | None, typer.Option("--provider", help="按 Provider 过滤。")
    ] = None,
    lookback_days: Annotated[
        int, typer.Option(min=14, max=90, help="回放使用的历史窗口天数。")
    ] = 28,
    planned_distance_km: Annotated[
        float | None,
        typer.Option(min=0.01, help="可选计划距离，单位为公里。"),
    ] = None,
    planned_duration_minutes: Annotated[
        float | None,
        typer.Option(min=0.01, help="可选计划时长，单位为分钟。"),
    ] = None,
    max_steps: Annotated[
        int, typer.Option(min=1, max=12, help="Agent 最大策略步骤数。")
    ] = 4,
    tool_call_budget: Annotated[
        int, typer.Option(min=0, max=3, help="业务工具逻辑调用预算。")
    ] = 1,
    max_retries: Annotated[
        int, typer.Option(min=0, max=3, help="工具超时或瞬时错误重试次数。")
    ] = 1,
    tool_timeout_seconds: Annotated[
        float, typer.Option(min=0.01, max=60, help="单次工具尝试超时秒数。")
    ] = 5.0,
    run_timeout_seconds: Annotated[
        float, typer.Option(min=0.01, max=120, help="整个 Agent Run 超时秒数。")
    ] = 15.0,
    database_path: Annotated[Path, typer.Option("--db")] = Path("data/runcrew.db"),
) -> None:
    if not latest and external_id is None:
        raise typer.BadParameter("Pass --latest or --external-id.")
    database = open_database(database_path)
    with database.session() as session:
        repository = ActivityRepository(session)
        target = (
            repository.latest(provider=provider_name)
            if latest
            else repository.get_by_external_id(
                provider_name or "fixture", external_id or ""
            )
        )
    if target is None:
        raise typer.BadParameter("Activity not found.")

    plan = None
    if planned_distance_km is not None or planned_duration_minutes is not None:
        plan = PlannedSession(
            distance_meters=planned_distance_km * 1000
            if planned_distance_km is not None
            else None,
            duration_seconds=round(planned_duration_minutes * 60)
            if planned_duration_minutes is not None
            else None,
        )
    review_request = TrainingReviewRequest(
        target_activity_id=target.id,
        lookback_days=lookback_days,
        planned_session=plan,
    )
    run_request = ReviewAgentRunRequest(
        review_request=review_request,
        max_steps=max_steps,
        tool_call_budget=tool_call_budget,
        max_retries=max_retries,
        tool_timeout_seconds=tool_timeout_seconds,
        run_timeout_seconds=run_timeout_seconds,
    )

    async def review_tool(request: TrainingReviewRequest):
        def execute():
            with database.session() as session:
                return execute_training_review(
                    request,
                    store=ActivityRepository(session),
                )

        return await asyncio.to_thread(execute)

    result = asyncio.run(ReviewAgentHarness().run(run_request, tool=review_tool))
    typer.echo(result.model_dump_json(indent=2))
    if result.status != "succeeded":
        raise typer.Exit(code=1)


@evaluation_app.command("review-agent")
def evaluate_review_agent(
    cases_path: Annotated[
        Path,
        typer.Option("--cases", help="评测用例 JSON 路径。"),
    ] = Path("evals/review_agent/cases.json"),
    output_path: Annotated[
        Path | None,
        typer.Option(
            "--output",
            help="可选报告路径；为保护未来真实评测数据，只允许写入 data/private。",
        ),
    ] = None,
) -> None:
    if not cases_path.is_file():
        raise typer.BadParameter(f"Evaluation suite not found: {cases_path}")
    suite = load_review_agent_suite(cases_path)
    report = asyncio.run(evaluate_review_agent_suite(suite))
    payload = report.model_dump_json(indent=2)
    if output_path is not None:
        private_root = Path("data/private").resolve()
        resolved_output = output_path.resolve()
        if not resolved_output.is_relative_to(private_root):
            raise typer.BadParameter("Evaluation reports must stay under data/private.")
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        resolved_output.write_text(payload + "\n", encoding="utf-8")
    typer.echo(payload)
    if not report.meets_baseline:
        raise typer.Exit(code=1)


@evaluation_app.command("deepseek-smoke")
def evaluate_deepseek_smoke(
    confirm_paid_api: Annotated[
        bool,
        typer.Option(
            "--confirm-paid-api",
            help="明确确认本命令会调用 DeepSeek 并产生少量费用。",
        ),
    ] = False,
    max_estimated_cost_usd: Annotated[
        float | None,
        typer.Option(
            "--max-estimated-cost-usd",
            min=0.000001,
            max=1,
            help="本次 Policy 允许的估算费用上限（美元），必须显式提供。",
        ),
    ] = None,
    cases_path: Annotated[
        Path,
        typer.Option("--cases", help="评测用例 JSON 路径。"),
    ] = Path("evals/review_agent/cases.json"),
    output_path: Annotated[
        Path | None,
        typer.Option("--output", help="可选报告路径，只允许写入 data/private。"),
    ] = None,
) -> None:
    if not confirm_paid_api:
        raise typer.BadParameter("必须显式传入 --confirm-paid-api 才允许外部模型调用。")
    if max_estimated_cost_usd is None:
        raise typer.BadParameter("必须显式设置 --max-estimated-cost-usd。")
    if not cases_path.is_file():
        raise typer.BadParameter(f"Evaluation suite not found: {cases_path}")
    try:
        config = DeepSeekPolicyConfig.from_env().model_copy(
            update={"max_estimated_cost_usd": max_estimated_cost_usd}
        )
    except DeepSeekPolicyError as error:
        raise typer.BadParameter(str(error)) from error

    suite = load_review_agent_suite(cases_path)
    smoke_case = next(
        (case for case in suite.cases if case.id == "complete_training_review"),
        None,
    )
    if smoke_case is None:
        raise typer.BadParameter("Evaluation suite 缺少 complete_training_review。")
    smoke_case = smoke_case.model_copy(
        update={
            "run": smoke_case.run.model_copy(
                update={"run_timeout_seconds": 60.0}
            )
        }
    )
    smoke_suite = suite.model_copy(update={"cases": [smoke_case]})
    report = asyncio.run(
        evaluate_review_agent_suite(
            smoke_suite,
            default_policy_factory=lambda: DeepSeekReviewPolicy(config),
            policy_name=f"{config.model}-live-nonthinking-smoke",
        )
    )
    payload = report.model_dump_json(indent=2)
    if output_path is not None:
        private_root = Path("data/private").resolve()
        resolved_output = output_path.resolve()
        if not resolved_output.is_relative_to(private_root):
            raise typer.BadParameter("Evaluation reports must stay under data/private.")
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        resolved_output.write_text(payload + "\n", encoding="utf-8")
    typer.echo(payload)
    if not report.meets_baseline:
        raise typer.Exit(code=1)


@evaluation_app.command("deepseek-suite")
def evaluate_deepseek_suite(
    confirm_paid_api: Annotated[
        bool,
        typer.Option(
            "--confirm-paid-api",
            help="明确确认本命令会运行完整 DeepSeek 合成评测并产生费用。",
        ),
    ] = False,
    max_total_estimated_cost_usd: Annotated[
        float | None,
        typer.Option(
            "--max-total-estimated-cost-usd",
            min=0.000001,
            max=1,
            help="完整 Suite 共享的估算费用上限（美元），必须显式提供。",
        ),
    ] = None,
    cases_path: Annotated[
        Path,
        typer.Option("--cases", help="评测用例 JSON 路径。"),
    ] = Path("evals/review_agent/cases.json"),
    output_path: Annotated[
        Path | None,
        typer.Option("--output", help="可选报告路径，只允许写入 data/private。"),
    ] = None,
) -> None:
    if not confirm_paid_api:
        raise typer.BadParameter("必须显式传入 --confirm-paid-api 才允许完整模型评测。")
    if max_total_estimated_cost_usd is None:
        raise typer.BadParameter("必须显式设置 --max-total-estimated-cost-usd。")
    if not cases_path.is_file():
        raise typer.BadParameter(f"Evaluation suite not found: {cases_path}")
    try:
        config = DeepSeekPolicyConfig.from_env().model_copy(
            update={"max_estimated_cost_usd": max_total_estimated_cost_usd}
        )
    except DeepSeekPolicyError as error:
        raise typer.BadParameter(str(error)) from error

    cost_budget = DeepSeekCostBudget(max_total_estimated_cost_usd)
    suite = load_review_agent_suite(cases_path)
    report = asyncio.run(
        evaluate_review_agent_suite(
            suite,
            default_policy_factory=lambda: DeepSeekReviewPolicy(
                config,
                cost_budget=cost_budget,
            ),
            policy_name=f"{config.model}-live-nonthinking-suite",
        )
    )
    payload = report.model_dump_json(indent=2)
    if output_path is not None:
        private_root = Path("data/private").resolve()
        resolved_output = output_path.resolve()
        if not resolved_output.is_relative_to(private_root):
            raise typer.BadParameter("Evaluation reports must stay under data/private.")
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        resolved_output.write_text(payload + "\n", encoding="utf-8")
    typer.echo(payload)
    if not report.meets_baseline:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
