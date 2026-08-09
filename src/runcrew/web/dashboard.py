from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from runcrew.domain.activity import ActivityDetail, ActivitySummary
from runcrew.domain.agent import ReviewAgentRunRequest
from runcrew.domain.evaluation import ReviewAgentEvaluationReport
from runcrew.domain.training_review import PlannedSession, TrainingReviewRequest
from runcrew.harness import ReviewAgentHarness
from runcrew.services.training_review import execute_training_review
from runcrew.storage.database import Database
from runcrew.storage.repositories import ActivityRepository


FindingLevel = Literal["good", "normal", "attention", "unknown"]


class DemoActivity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    provider: str
    sport_type: str
    title: str
    distance_km: float | None
    duration: str
    average_pace: str | None
    average_heart_rate: int | None
    lap_count: int
    detail_available: bool


class DemoFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    level: FindingLevel
    message: str
    evidence: dict[str, object]


class DemoTraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int
    elapsed_ms: float
    state: str
    event: str
    tool_name: str | None
    details: dict[str, object]


class DemoAgentRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    termination_reason: str
    steps_used: int
    tool_calls_used: int
    tool_attempts_used: int
    trace: list[DemoTraceEvent]


class DemoPolicyEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    policy_name: str
    suite_version: str | None = None
    suite_hash_short: str | None = None
    passed_cases: int = 0
    total_cases: int = 0
    task_completion_rate: float | None = None
    guardrail_pass_rate: float | None = None
    fact_integrity_rate: float | None = None
    prohibited_tool_execution_count: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0
    p95_latency_ms: float | None = None


class DemoEvaluationComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    same_suite: bool
    baseline: DemoPolicyEvaluation
    deepseek: DemoPolicyEvaluation


class DemoDashboardSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    selected_provider: str | None
    activity: DemoActivity | None
    recent_activities: list[DemoActivity]
    findings: list[DemoFinding]
    confidence: str | None
    missing_fields: list[str]
    input_hash_short: str | None
    agent_run: DemoAgentRun | None
    evaluation: DemoEvaluationComparison
    message: str | None = None


class DemoDashboardService:
    """只读取规范化活动和私有评测报告，不访问 Provider 原始数据。"""

    def __init__(
        self,
        *,
        database_path: Path = Path("data/runcrew.db"),
        evaluation_directory: Path = Path("data/private/evals"),
    ) -> None:
        self.database_path = database_path
        self.evaluation_directory = evaluation_directory

    def build_snapshot(
        self,
        *,
        provider: str | None = None,
        lookback_days: int = 28,
        planned_distance_km: float | None = None,
        planned_duration_minutes: float | None = None,
    ) -> DemoDashboardSnapshot:
        evaluation = self._evaluation_comparison()
        if not self.database_path.is_file():
            return self._empty_snapshot(provider=provider, evaluation=evaluation)
        database = Database(self._database_url())
        with database.session() as session:
            repository = ActivityRepository(session)
            recent = repository.list(limit=20)
            if provider is not None:
                recent = [
                    item
                    for item in recent
                    if item.source_ref.provider.value == provider
                ]
            target = recent[0] if recent else None

        if target is None:
            return self._empty_snapshot(provider=provider, evaluation=evaluation)

        plan = None
        if planned_distance_km is not None or planned_duration_minutes is not None:
            plan = PlannedSession(
                distance_meters=(
                    planned_distance_km * 1000
                    if planned_distance_km is not None
                    else None
                ),
                duration_seconds=(
                    round(planned_duration_minutes * 60)
                    if planned_duration_minutes is not None
                    else None
                ),
            )
        review_request = TrainingReviewRequest(
            target_activity_id=target.id,
            lookback_days=lookback_days,
            planned_session=plan,
        )
        run_request = ReviewAgentRunRequest(review_request=review_request)

        async def tool(request: TrainingReviewRequest):
            with database.session() as session:
                return execute_training_review(
                    request,
                    store=ActivityRepository(session),
                )

        run_result = asyncio.run(ReviewAgentHarness().run(run_request, tool=tool))
        output = run_result.output
        return DemoDashboardSnapshot(
            generated_at=datetime.now().astimezone(),
            selected_provider=provider,
            activity=self._activity_view(target),
            recent_activities=[self._activity_view(item) for item in recent[:6]],
            findings=(
                [
                    DemoFinding(
                        type=finding.type,
                        level=finding.level,
                        message=finding.message,
                        evidence=finding.evidence,
                    )
                    for finding in output.findings
                ]
                if output is not None
                else []
            ),
            confidence=output.data_quality.confidence if output is not None else None,
            missing_fields=(
                output.data_quality.missing_fields if output is not None else []
            ),
            input_hash_short=(output.input_hash[:12] if output is not None else None),
            agent_run=DemoAgentRun(
                status=run_result.status,
                termination_reason=run_result.termination_reason,
                steps_used=run_result.budget.steps_used,
                tool_calls_used=run_result.budget.tool_calls_used,
                tool_attempts_used=run_result.budget.tool_attempts_used,
                trace=[
                    DemoTraceEvent(
                        sequence=event.sequence,
                        elapsed_ms=event.elapsed_ms,
                        state=event.state,
                        event=event.event,
                        tool_name=event.tool_name,
                        details=event.details,
                    )
                    for event in run_result.trace
                ],
            ),
            evaluation=evaluation,
        )

    @staticmethod
    def _empty_snapshot(
        *,
        provider: str | None,
        evaluation: DemoEvaluationComparison,
    ) -> DemoDashboardSnapshot:
        return DemoDashboardSnapshot(
            generated_at=datetime.now().astimezone(),
            selected_provider=provider,
            activity=None,
            recent_activities=[],
            findings=[],
            confidence=None,
            missing_fields=[],
            input_hash_short=None,
            agent_run=None,
            evaluation=evaluation,
            message="当前筛选条件下没有活动。请先同步 fixture 或 COROS 数据。",
        )

    def _database_url(self) -> str:
        return f"sqlite:///{self.database_path.resolve().as_posix()}"

    @staticmethod
    def _activity_view(activity: ActivitySummary | ActivityDetail) -> DemoActivity:
        return DemoActivity(
            started_at=activity.started_at,
            provider=activity.source_ref.provider.value,
            sport_type=activity.sport_type.value,
            title=activity.title or "未命名跑步",
            distance_km=(
                round(activity.distance_meters / 1000, 2)
                if activity.distance_meters is not None
                else None
            ),
            duration=_format_duration(activity.duration_seconds),
            average_pace=_format_pace(activity.average_pace_seconds_per_km),
            average_heart_rate=activity.average_heart_rate,
            lap_count=len(activity.laps) if isinstance(activity, ActivityDetail) else 0,
            detail_available=isinstance(activity, ActivityDetail),
        )

    def _evaluation_comparison(self) -> DemoEvaluationComparison:
        baseline = self._load_evaluation(
            self.evaluation_directory / "m5-baseline-suite-v1.1.json",
            fallback_name="确定性 Policy",
        )
        deepseek = self._load_evaluation(
            self.evaluation_directory / "deepseek-suite-v1.1-final.json",
            fallback_name="DeepSeek Flash",
        )
        return DemoEvaluationComparison(
            same_suite=(
                baseline.available
                and deepseek.available
                and baseline.suite_version == deepseek.suite_version
                and baseline.suite_hash_short == deepseek.suite_hash_short
            ),
            baseline=baseline,
            deepseek=deepseek,
        )

    @staticmethod
    def _load_evaluation(
        path: Path,
        *,
        fallback_name: str,
    ) -> DemoPolicyEvaluation:
        if not path.is_file():
            return DemoPolicyEvaluation(available=False, policy_name=fallback_name)
        try:
            report = ReviewAgentEvaluationReport.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return DemoPolicyEvaluation(available=False, policy_name=fallback_name)
        metrics = report.metrics
        return DemoPolicyEvaluation(
            available=True,
            policy_name=report.policy_name,
            suite_version=report.suite_version,
            suite_hash_short=report.suite_hash[:12],
            passed_cases=report.passed_cases,
            total_cases=report.total_cases,
            task_completion_rate=metrics.task_completion_rate,
            guardrail_pass_rate=metrics.guardrail_pass_rate,
            fact_integrity_rate=metrics.fact_integrity_rate,
            prohibited_tool_execution_count=(
                metrics.prohibited_tool_execution_count
            ),
            total_tokens=metrics.total_tokens,
            estimated_cost_usd=metrics.estimated_cost_usd,
            p95_latency_ms=metrics.p95_latency_ms,
        )


def _format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{remaining_seconds:02d}"
    return f"{minutes}:{remaining_seconds:02d}"


def _format_pace(seconds_per_km: float | None) -> str | None:
    if seconds_per_km is None:
        return None
    minutes, seconds = divmod(round(seconds_per_km), 60)
    return f"{minutes}:{seconds:02d}/km"
